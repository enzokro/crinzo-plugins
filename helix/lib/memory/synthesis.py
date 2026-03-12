"""Cross-session pattern synthesis.

Reads session_log to detect recurring patterns (repeated blockers,
convergent failure modes) and returns candidate insights for storage.
The slow feedback loop: session_log -> pattern detection -> insight candidates.
"""

from collections import Counter
from datetime import datetime, timedelta, timezone
import re

try:
    from ..db.connection import get_db
except ImportError:
    from db.connection import get_db


def _utcnow():
    """Return current UTC time as naive datetime (no tzinfo)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

# Named constants
SYNTHESIS_THRESHOLD = 3       # Minimum blocked occurrences to trigger
SYNTHESIS_LOOKBACK_DAYS = 30  # Window for pattern detection
SYNTHESIS_COVERAGE_SIM = 0.70 # Existing insight must exceed this to count as "already covered"
CLUSTER_SIM_THRESHOLD = 0.60  # Single-linkage merge threshold for summary clustering
MIN_CLUSTER_CONFIDENCE = 1.5  # tightness * sqrt(count) floor — filters weak patterns


def _extract_common_terms(summaries, top_n=5):
    """Extract most common meaningful terms from summaries."""
    # Simple word frequency, filtering stopwords and short words
    stopwords = {"the", "a", "an", "is", "was", "were", "are", "be", "been",
                 "being", "have", "has", "had", "do", "does", "did", "will",
                 "would", "could", "should", "may", "might", "shall", "can",
                 "to", "of", "in", "for", "on", "with", "at", "by", "from",
                 "as", "into", "through", "during", "before", "after", "and",
                 "but", "or", "nor", "not", "no", "so", "if", "then", "than",
                 "that", "this", "these", "those", "it", "its", "when", "where"}
    words = []
    for s in summaries:
        if not s:
            continue
        tokens = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]{2,}', s.lower())
        words.extend(t for t in tokens if t not in stopwords)
    counter = Counter(words)
    return [term for term, _ in counter.most_common(top_n)]


def _cluster_summaries(summaries):
    """Cluster summaries by semantic similarity.

    Returns list of clusters:
        [{representative: str, members: [str], tightness: float, confidence: float}]
    """
    valid = [s for s in summaries if s and s.strip()]
    if not valid:
        return []
    if len(valid) < 2:
        return [{"representative": valid[0], "members": valid,
                 "tightness": 1.0, "confidence": 1.0}]

    import numpy as np
    try:
        from .embeddings import embed
    except ImportError:
        from embeddings import embed

    # Embed all summaries
    embs = []
    embedded_summaries = []
    for s in valid:
        e = embed(s, is_query=False)
        if e is not None:
            embs.append(e)
            embedded_summaries.append(s)

    if len(embedded_summaries) < 2:
        return [{"representative": embedded_summaries[0] if embedded_summaries else valid[0],
                 "members": embedded_summaries or valid,
                 "tightness": 0.5, "confidence": 0.5}]

    mat = np.array(embs, dtype=np.float32)
    # Normalize rows for cosine similarity (handles mock embeddings that aren't pre-normalized)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms = np.where(norms > 0, norms, 1.0)
    mat = mat / norms
    # Pairwise cosine (vectors L2-normalized)
    sim_matrix = mat @ mat.T
    n = len(embedded_summaries)

    # Single-linkage agglomerative: merge pairs above threshold
    cluster_ids = list(range(n))
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            if sim_matrix[i, j] >= CLUSTER_SIM_THRESHOLD:
                pairs.append((float(sim_matrix[i, j]), i, j))
    pairs.sort(reverse=True)

    for _, i, j in pairs:
        ci, cj = cluster_ids[i], cluster_ids[j]
        if ci != cj:
            for k in range(n):
                if cluster_ids[k] == cj:
                    cluster_ids[k] = ci

    # Collect clusters
    from collections import defaultdict
    clusters_map = defaultdict(list)
    for idx, cid in enumerate(cluster_ids):
        clusters_map[cid].append(idx)

    result = []
    for indices in clusters_map.values():
        members = [embedded_summaries[i] for i in indices]
        cluster_embs = mat[indices]
        centroid = cluster_embs.mean(axis=0)
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroid = centroid / norm

        # Representative: closest to centroid
        dists = cluster_embs @ centroid
        rep_idx = indices[int(np.argmax(dists))]

        # Tightness: avg pairwise similarity
        if len(indices) > 1:
            sub_sim = sim_matrix[np.ix_(indices, indices)]
            mask = np.ones_like(sub_sim, dtype=bool)
            np.fill_diagonal(mask, False)
            tightness = float(sub_sim[mask].mean())
        else:
            tightness = 1.0

        confidence = tightness * (len(indices) ** 0.5)
        result.append({
            "representative": embedded_summaries[rep_idx],
            "members": members,
            "tightness": round(tightness, 3),
            "confidence": round(confidence, 3),
        })

    return result


def synthesize_session(session_threshold=SYNTHESIS_THRESHOLD,
                       lookback_days=SYNTHESIS_LOOKBACK_DAYS):
    """Analyze session_log for cross-session patterns.

    Returns list of dicts:
        {type: "new"|"reinforcement", content: str, evidence: list,
         tags: list, existing_name: str|None}
    """
    db = get_db()
    cutoff = (_utcnow() - timedelta(days=lookback_days)).isoformat()

    rows = db.execute(
        "SELECT outcome, summary, agent_type, created_at FROM session_log "
        "WHERE created_at > ? ORDER BY created_at DESC",
        (cutoff,)
    ).fetchall()

    if not rows:
        return []

    # Group failures by agent_type
    failures = {}
    total_by_type = Counter()
    for row in rows:
        agent_type = row["agent_type"] or "unknown"
        total_by_type[agent_type] += 1
        if row["outcome"] in ("blocked", "crashed"):
            failures.setdefault(agent_type, []).append(row["summary"] or "")

    candidates = []
    for agent_type, summaries in failures.items():
        if len(summaries) < session_threshold:
            continue

        try:
            clusters = _cluster_summaries(summaries)
        except Exception:
            clusters = [{"representative": summaries[0], "members": summaries,
                         "tightness": 0.5, "confidence": len(summaries) ** 0.5 * 0.5}]

        total = total_by_type[agent_type]

        for cluster in clusters:
            if cluster["confidence"] < MIN_CLUSTER_CONFIDENCE:
                continue

            rep = cluster["representative"]
            pattern_content = (
                f"When {agent_type} agents work on tasks like \"{rep[:100]}\", "
                f"tasks frequently block ({len(cluster['members'])} of {total} recent sessions). "
                f"Consider smaller task scope and explicit verification for this area."
            )

            # Check if existing insight covers this pattern
            try:
                try:
                    from ..memory.core import recall
                except ImportError:
                    from memory.core import recall
                matches = recall(pattern_content, limit=1, min_relevance=0.30)
                if matches and matches[0].get("_relevance", 0) >= SYNTHESIS_COVERAGE_SIM:
                    candidates.append({
                        "type": "reinforcement",
                        "content": pattern_content,
                        "evidence": cluster["members"][:5],
                        "tags": ["strategic", "cross-session"],
                        "existing_name": matches[0]["name"],
                    })
                else:
                    candidates.append({
                        "type": "new",
                        "content": pattern_content,
                        "evidence": cluster["members"][:5],
                        "tags": ["strategic", "cross-session", "derived"],
                        "existing_name": None,
                    })
            except Exception:
                # On recall failure, treat as new (conservative)
                candidates.append({
                    "type": "new",
                    "content": pattern_content,
                    "evidence": cluster["members"][:5],
                    "tags": ["strategic", "cross-session", "derived"],
                    "existing_name": None,
                })

    return candidates
