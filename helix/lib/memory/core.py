#!/usr/bin/env python3
"""Memory: the persistence layer for learning.

Core API:
- store(trigger, resolution, type) -> name
- recall(query, limit) -> memories ranked by relevance x effectiveness x recency
- feedback(utilized, injected) -> closes the loop (THE critical function)
- chunk(task, outcome, approach) -> extract reusable rule from success (SOAR)
- relate(a, b, type) -> creates connection
- connected(name) -> related memories via graph traversal
- health() -> system status
- prune() -> removes ineffective memories
- decay() -> find dormant memories
- consolidate() -> merge similar memories
- get(name) -> retrieve specific memory

Scoring formula:
    score = (0.5 * relevance) + (0.3 * effectiveness) + (0.2 * recency)
    effectiveness = helped / (helped + failed) if total > 0 else 0.5
    recency = 2^(-days_since_use / 7)
"""

import json
import math
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List

# Constants
DECAY_HALF_LIFE_DAYS = 7
DUPLICATE_THRESHOLD = 0.85
SCORE_WEIGHTS = {
    'relevance': 0.5,
    'effectiveness': 0.3,
    'recency': 0.2,
}

# Support both module and script execution
try:
    from ..db.connection import get_db, write_lock
    from .embeddings import embed, to_blob, from_blob, cosine, is_available
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from db.connection import get_db, write_lock
    sys.path.insert(0, str(Path(__file__).parent))
    from embeddings import embed, to_blob, from_blob, cosine, is_available


def _slug(text: str) -> str:
    """Create kebab-case slug."""
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:50] if len(s) > 50 else s


def _extract_file_patterns(trigger: str, resolution: str) -> List[str]:
    """Extract file path patterns from memory text.

    Used for structured matching - complements semantic search
    when file paths don't have natural language semantics.
    """
    text = f"{trigger} {resolution}"
    patterns = set()

    # Match common source file extensions
    file_pattern = r'[\w\-./]+\.(py|js|ts|tsx|jsx|go|rs|java|rb|php|vue|svelte|md|json|yaml|yml|toml|sql|sh|css|scss|html)'
    for match in re.findall(file_pattern, text, re.IGNORECASE):
        # Get the full match by re-searching
        for full_match in re.finditer(file_pattern, text, re.IGNORECASE):
            patterns.add(full_match.group(0))

    # Match directory patterns like src/auth, lib/memory, etc.
    dir_pattern = r'(?:src|lib|app|components|utils|services|api|tests?|scripts?)/[\w\-/]+'
    for match in re.findall(dir_pattern, text):
        patterns.add(match)

    return list(patterns)


def _effectiveness(row) -> float:
    """Calculate effectiveness from helped/failed."""
    h, f = row["helped"] or 0, row["failed"] or 0
    return h / (h + f) if (h + f) > 0 else 0.5


def _recency_score(last_used: Optional[str], created_at: str) -> float:
    """Calculate recency score with exponential decay (ACT-R pattern).

    Returns value between 0 and 1:
    - 1.0 = used today
    - 0.5 = not used in DECAY_HALF_LIFE_DAYS
    - approaches 0 = ancient and unused
    """
    ref_date = last_used or created_at
    if not ref_date:
        return 0.5

    try:
        ref = datetime.fromisoformat(ref_date.replace("Z", "+00:00"))
        now = datetime.now()
        if ref.tzinfo:
            now = datetime.now(ref.tzinfo)
        days_ago = (now - ref).days
        return math.pow(2, -days_ago / DECAY_HALF_LIFE_DAYS)
    except:
        return 0.5


def _to_dict(row) -> dict:
    """Convert database row to memory dict."""
    return {
        "name": row["name"],
        "type": row["type"],
        "trigger": row["trigger"],
        "resolution": row["resolution"],
        "helped": row["helped"] or 0,
        "failed": row["failed"] or 0,
        "effectiveness": round(_effectiveness(row), 3),
        "created_at": row["created_at"],
        "last_used": row["last_used"],
        "source": row["source"]
    }


def store(
    trigger: str,
    resolution: str,
    type: str = "failure",
    source: str = ""
) -> dict:
    """Store a memory. Returns {status, name, reason}.

    Performs semantic deduplication - similar memories are merged.
    """
    if type not in ("failure", "pattern"):
        return {"status": "rejected", "name": "", "reason": "type must be failure or pattern"}

    if len(trigger.strip()) < 10:
        return {"status": "rejected", "name": "", "reason": "trigger too short"}

    if not resolution.strip():
        return {"status": "rejected", "name": "", "reason": "resolution empty"}

    # Check for semantic duplicate
    if is_available():
        new_emb = embed(trigger)
        if new_emb:
            db = get_db()
            for row in db.execute("SELECT name, embedding FROM memory WHERE type=? AND embedding IS NOT NULL", (type,)):
                if cosine(new_emb, from_blob(row["embedding"])) >= DUPLICATE_THRESHOLD:
                    return {"status": "merged", "name": row["name"], "reason": "similar exists"}

    name = _slug(trigger)
    if not name:
        name = f"{type}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    emb_blob = None
    e = embed(trigger + " " + resolution)
    if e:
        emb_blob = to_blob(e)

    # Extract file patterns for structured matching
    file_patterns = _extract_file_patterns(trigger, resolution)
    file_patterns_json = json.dumps(file_patterns) if file_patterns else None

    db = get_db()
    now = datetime.now().isoformat()

    with write_lock():
        try:
            db.execute(
                "INSERT INTO memory (name, type, trigger, resolution, embedding, created_at, source, file_patterns) VALUES (?,?,?,?,?,?,?,?)",
                (name, type, trigger.strip(), resolution.strip(), emb_blob, now, source, file_patterns_json)
            )
            db.commit()
            return {"status": "added", "name": name, "reason": ""}
        except Exception as e:
            if "UNIQUE" in str(e):
                name = f"{name}-{datetime.now().strftime('%H%M%S')}"
                db.execute(
                    "INSERT INTO memory (name, type, trigger, resolution, embedding, created_at, source, file_patterns) VALUES (?,?,?,?,?,?,?,?)",
                    (name, type, trigger.strip(), resolution.strip(), emb_blob, now, source, file_patterns_json)
                )
                db.commit()
                return {"status": "added", "name": name, "reason": "", "file_patterns": file_patterns}
            raise


def recall(
    query: str,
    type: Optional[str] = None,
    limit: int = 5,
    min_effectiveness: float = 0.0
) -> List[dict]:
    """Recall memories by semantic similarity.

    Returns list with _relevance, _recency, _score fields.
    Scored by: (0.5 * relevance) + (0.3 * effectiveness) + (0.2 * recency)
    """
    db = get_db()
    sql = "SELECT * FROM memory WHERE embedding IS NOT NULL"
    params = []
    if type:
        sql += " AND type=?"
        params.append(type)

    rows = db.execute(sql, params).fetchall()
    if not rows:
        return []

    q_emb = embed(query)
    if q_emb is None:
        # Fallback: by effectiveness
        rows = db.execute(
            f"SELECT * FROM memory {'WHERE type=?' if type else ''} ORDER BY (helped*1.0/(helped+failed+1)) DESC LIMIT ?",
            ([type, limit] if type else [limit])
        ).fetchall()
        return [_to_dict(r) for r in rows]

    scored = []
    for r in rows:
        eff = _effectiveness(r)
        if eff < min_effectiveness:
            continue
        rel = cosine(q_emb, from_blob(r["embedding"]))
        rec = _recency_score(r["last_used"], r["created_at"])

        # ACT-R inspired activation
        score = (SCORE_WEIGHTS['relevance'] * rel) + \
                (SCORE_WEIGHTS['effectiveness'] * eff) + \
                (SCORE_WEIGHTS['recency'] * rec)

        m = _to_dict(r)
        m["_relevance"] = round(rel, 3)
        m["_recency"] = round(rec, 3)
        m["_score"] = round(score, 3)
        scored.append((score, m))

    scored.sort(key=lambda x: -x[0])
    return [m for _, m in scored[:limit]]


def recall_by_file_patterns(
    delta_files: List[str],
    limit: int = 3
) -> List[dict]:
    """Query memories by file path patterns.

    Uses structured file_patterns column for matching, not semantic search.
    Complements recall() for cases where file paths don't have
    natural language semantics (e.g., "src/auth/jwt.py" vs "authentication").

    Args:
        delta_files: List of file paths to match against
        limit: Maximum memories to return

    Returns:
        List of matching memories, sorted by effectiveness
    """
    db = get_db()
    matches = []
    seen_names = set()

    for delta_file in delta_files:
        # Extract components for matching
        try:
            from pathlib import Path
            parts = Path(delta_file).parts
            filename = Path(delta_file).name
            stem = Path(delta_file).stem
            # Last two path components for partial matching
            partial_path = "/".join(parts[-2:]) if len(parts) >= 2 else filename
        except Exception:
            filename = delta_file.split("/")[-1] if "/" in delta_file else delta_file
            stem = filename.rsplit(".", 1)[0] if "." in filename else filename
            partial_path = delta_file

        # Query for pattern matches in file_patterns JSON column
        # SQLite's LIKE works on JSON strings
        rows = db.execute("""
            SELECT * FROM memory
            WHERE file_patterns IS NOT NULL
              AND (
                file_patterns LIKE ? OR
                file_patterns LIKE ? OR
                file_patterns LIKE ?
              )
            ORDER BY (helped * 1.0 / (helped + failed + 1)) DESC
            LIMIT ?
        """, (
            f'%{filename}%',
            f'%{stem}%',
            f'%{partial_path}%',
            limit * 2  # Get more than needed for deduplication
        )).fetchall()

        for row in rows:
            name = row["name"]
            if name not in seen_names:
                seen_names.add(name)
                matches.append(_to_dict(row))

    # Sort by effectiveness and limit
    matches.sort(key=lambda m: m.get("effectiveness", 0.5), reverse=True)
    return matches[:limit]


def feedback(utilized: List[str], injected: List[str]) -> dict:
    """Update effectiveness based on what was actually used.

    DEPRECATED: Prefer feedback_from_verification() which uses objective
    verification outcomes instead of self-reported utilization.

    Args:
        utilized: Memory names that ACTUALLY HELPED (honest reporting!)
        injected: Memory names that were provided

    Result:
        - utilized memories get helped++, last_used updated
        - injected-but-not-utilized get failed++
    """
    db = get_db()
    now = datetime.now().isoformat()
    helped = 0
    unhelpful = 0
    missing = []

    util_set = set(utilized)
    inj_set = set(injected)

    with write_lock():
        for name in inj_set:
            row = db.execute("SELECT id FROM memory WHERE name=?", (name,)).fetchone()
            if not row:
                missing.append(name)
                continue

            if name in util_set:
                db.execute("UPDATE memory SET helped=helped+1, last_used=? WHERE name=?", (now, name))
                helped += 1
            else:
                db.execute("UPDATE memory SET failed=failed+1 WHERE name=?", (name,))
                unhelpful += 1

        db.commit()

    return {"helped": helped, "unhelpful": unhelpful, "missing": missing}


def feedback_from_verification(
    task_id: str,
    verify_passed: bool,
    injected: List[str],
    task_objective: str = ""
) -> dict:
    """Close feedback loop based on verification outcome.

    This replaces self-reported UTILIZED with objective verification.
    The verification command (e.g., pytest) is ground truth - if it passes
    and memories were injected, those memories get credit.

    This approach is immune to builder dishonesty:
    - Builder can't inflate by claiming all memories helped
    - Builder can't deflate by claiming none helped
    - Credit is based on objective verification result

    Args:
        task_id: The task that completed
        verify_passed: Whether the verify command succeeded (exit 0)
        injected: Memory names that were injected for this task
        task_objective: Optional objective for logging

    Returns:
        {
            "credited": N,           # Memories that got credit
            "task_id": str,
            "verify_passed": bool,
            "injected_count": N
        }

    Attribution logic:
        - Success (verify passed): Give partial credit (0.5) to all injected
          memories. We can't know which memory specifically helped, but the
          task succeeded with this context.
        - Failure (verify failed): No penalty. We don't know if the failure
          was due to memories or something else. Avoids punishing memories
          for unrelated issues.
    """
    db = get_db()
    now = datetime.now().isoformat()
    credited = 0

    with write_lock():
        for name in injected:
            row = db.execute("SELECT id FROM memory WHERE name=?", (name,)).fetchone()
            if not row:
                continue

            if verify_passed:
                # Success: give partial credit (0.5) to all injected memories
                # Weight 0.5 because we can't attribute precisely
                db.execute("""
                    UPDATE memory
                    SET helped = helped + 0.5,
                        last_used = ?
                    WHERE name = ?
                """, (now, name))
                credited += 1
            # Failure: no penalty - we don't know which memory (if any) caused it
            # Just don't update anything

        db.commit()

    return {
        "credited": credited,
        "task_id": task_id,
        "verify_passed": verify_passed,
        "injected_count": len(injected)
    }


def chunk(
    task_objective: str,
    outcome: str,
    approach: str,
    source: str = "chunked"
) -> dict:
    """Extract a reusable rule from a successful task completion.

    Implements the SOAR chunking pattern - when deliberate problem-solving
    succeeds, compile that experience into a rule that can fire directly
    next time.

    This is how expertise develops: slow deliberation -> fast intuition.
    """
    if not outcome.lower().startswith("success"):
        return {"status": "skipped", "reason": "only chunk successful outcomes"}

    trigger = f"Task: {task_objective}"
    resolution = f"Approach that worked: {approach}"

    # Check if similar pattern exists - strengthen instead of duplicate
    existing = recall(trigger, type="pattern", limit=3)
    for m in existing:
        if m.get("_relevance", 0) > DUPLICATE_THRESHOLD:
            db = get_db()
            with write_lock():
                db.execute(
                    "UPDATE memory SET helped=helped+1, last_used=? WHERE name=?",
                    (datetime.now().isoformat(), m["name"])
                )
                db.commit()
            return {
                "status": "strengthened",
                "name": m["name"],
                "reason": "similar pattern exists, reinforced it"
            }

    return store(
        trigger=trigger,
        resolution=resolution,
        type="pattern",
        source=source
    )


def relate(from_name: str, to_name: str, rel_type: str, weight: float = 1.0) -> dict:
    """Create relationship between memories."""
    db = get_db()

    for n in [from_name, to_name]:
        if not db.execute("SELECT 1 FROM memory WHERE name=?", (n,)).fetchone():
            return {"status": "rejected", "reason": f"memory not found: {n}"}

    now = datetime.now().isoformat()
    with write_lock():
        try:
            db.execute(
                "INSERT INTO memory_edge (from_name, to_name, rel_type, weight, created_at) VALUES (?,?,?,?,?)",
                (from_name, to_name, rel_type, weight, now)
            )
            db.commit()
            return {"status": "added"}
        except:
            return {"status": "exists"}


def connected(name: str, max_hops: int = 2) -> List[dict]:
    """Find connected memories via graph traversal."""
    db = get_db()
    if not db.execute("SELECT 1 FROM memory WHERE name=?", (name,)).fetchone():
        return []

    visited = {name}
    results = []
    frontier = [name]

    for hop in range(1, max_hops + 1):
        next_frontier = []
        for current in frontier:
            edges = db.execute(
                "SELECT to_name, rel_type, weight FROM memory_edge WHERE from_name=? "
                "UNION SELECT from_name, rel_type, weight FROM memory_edge WHERE to_name=?",
                (current, current)
            ).fetchall()

            for e in edges:
                neighbor = e["to_name"] if e["to_name"] != current else e["from_name"]
                if neighbor in visited or e["weight"] < 0.5:
                    continue
                visited.add(neighbor)
                next_frontier.append(neighbor)

                row = db.execute("SELECT * FROM memory WHERE name=?", (neighbor,)).fetchone()
                if row:
                    m = _to_dict(row)
                    m["_hop"] = hop
                    m["_via"] = e["rel_type"]
                    results.append(m)

        frontier = next_frontier

    return results


def prune(min_effectiveness: float = 0.25, min_uses: int = 3) -> dict:
    """Remove memories that have proven unhelpful."""
    db = get_db()
    rows = db.execute("SELECT name, helped, failed FROM memory WHERE (helped+failed)>=?", (min_uses,)).fetchall()

    to_remove = []
    for r in rows:
        if _effectiveness(r) < min_effectiveness:
            to_remove.append(r["name"])

    with write_lock():
        for n in to_remove:
            db.execute("DELETE FROM memory WHERE name=?", (n,))
            db.execute("DELETE FROM memory_edge WHERE from_name=? OR to_name=?", (n, n))
        db.commit()

    remaining = db.execute("SELECT COUNT(*) as c FROM memory").fetchone()["c"]
    return {"pruned": len(to_remove), "remaining": remaining}


def decay(threshold_days: int = 30, min_uses: int = 2) -> dict:
    """Find memories that haven't been used - candidates for decay.

    Implements Mem0 pattern of "dynamic forgetting" - memories that
    aren't accessed lose relevance over time.
    """
    db = get_db()
    cutoff = (datetime.now() - timedelta(days=threshold_days)).isoformat()

    rows = db.execute("""
        SELECT name, helped, failed, last_used, created_at
        FROM memory
        WHERE (last_used IS NULL OR last_used < ?)
          AND (helped + failed) < ?
    """, (cutoff, min_uses)).fetchall()

    dormant = [r["name"] for r in rows]
    return {
        "candidates_for_decay": dormant,
        "count": len(dormant),
        "threshold_days": threshold_days,
        "min_uses_to_survive": min_uses
    }


def consolidate(similarity_threshold: float = 0.9) -> dict:
    """Merge highly similar memories to prevent bloat.

    Implements Mem0 consolidation pattern - near-duplicate memories
    merge into one stronger memory.
    """
    if not is_available():
        return {"status": "skipped", "reason": "embeddings unavailable"}

    db = get_db()
    rows = db.execute("SELECT * FROM memory WHERE embedding IS NOT NULL").fetchall()

    merged_count = 0
    seen = set()

    for i, r1 in enumerate(rows):
        if r1["name"] in seen:
            continue
        emb1 = from_blob(r1["embedding"])

        for r2 in rows[i+1:]:
            if r2["name"] in seen:
                continue
            if r1["type"] != r2["type"]:
                continue

            emb2 = from_blob(r2["embedding"])
            sim = cosine(emb1, emb2)

            if sim >= similarity_threshold:
                h1, f1 = r1["helped"] or 0, r1["failed"] or 0
                h2, f2 = r2["helped"] or 0, r2["failed"] or 0

                if (h1 + f1) >= (h2 + f2):
                    keep, remove = r1, r2
                else:
                    keep, remove = r2, r1

                with write_lock():
                    db.execute(
                        "UPDATE memory SET helped=helped+?, failed=failed+? WHERE name=?",
                        (remove["helped"] or 0, remove["failed"] or 0, keep["name"])
                    )
                    db.execute(
                        "UPDATE memory_edge SET from_name=? WHERE from_name=?",
                        (keep["name"], remove["name"])
                    )
                    db.execute(
                        "UPDATE memory_edge SET to_name=? WHERE to_name=?",
                        (keep["name"], remove["name"])
                    )
                    db.execute("DELETE FROM memory WHERE name=?", (remove["name"],))
                    db.commit()

                seen.add(remove["name"])
                merged_count += 1

    return {"merged": merged_count, "remaining": len(rows) - merged_count}


def health() -> dict:
    """Check learning system health."""
    db = get_db()

    total = db.execute("SELECT COUNT(*) as c FROM memory").fetchone()["c"]
    by_type = {}
    for row in db.execute("SELECT type, COUNT(*) as c, SUM(helped) as h, SUM(failed) as f FROM memory GROUP BY type"):
        by_type[row["type"]] = {"count": row["c"], "helped": row["h"] or 0, "failed": row["f"] or 0}

    with_feedback = db.execute("SELECT COUNT(*) as c FROM memory WHERE (helped+failed)>0").fetchone()["c"]
    edges = db.execute("SELECT COUNT(*) as c FROM memory_edge").fetchone()["c"]

    total_h = sum(t["helped"] for t in by_type.values())
    total_f = sum(t["failed"] for t in by_type.values())
    effectiveness = total_h / (total_h + total_f) if (total_h + total_f) > 0 else 0.5

    loop_closed = total > 0 and with_feedback > 0
    issues = []
    if total == 0:
        issues.append("No memories yet")
    elif with_feedback == 0:
        issues.append("No feedback recorded - learning loop not closed")
    if not is_available():
        issues.append("Embeddings unavailable - install sentence-transformers")

    return {
        "status": "HEALTHY" if loop_closed and not issues else "NEEDS_ATTENTION",
        "total": total,
        "by_type": by_type,
        "effectiveness": round(effectiveness, 3),
        "with_feedback": with_feedback,
        "relationships": edges,
        "issues": issues
    }


def get(name: str) -> Optional[dict]:
    """Get specific memory by name."""
    db = get_db()
    row = db.execute("SELECT * FROM memory WHERE name=?", (name,)).fetchone()
    return _to_dict(row) if row else None


# CLI
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Helix memory operations")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("store")
    s.add_argument("--trigger", required=True)
    s.add_argument("--resolution", required=True)
    s.add_argument("--type", default="failure")
    s.add_argument("--source", default="")

    s = sub.add_parser("recall")
    s.add_argument("query")
    s.add_argument("--type", default=None)
    s.add_argument("--limit", type=int, default=5)

    s = sub.add_parser("feedback")
    s.add_argument("--utilized", required=True)
    s.add_argument("--injected", required=True)

    s = sub.add_parser("feedback-verify", help="Feedback from verification outcome")
    s.add_argument("--task-id", required=True)
    s.add_argument("--verify-passed", type=lambda x: x.lower() == "true", required=True)
    s.add_argument("--injected", required=True)

    s = sub.add_parser("relate")
    s.add_argument("--from", dest="from_name", required=True)
    s.add_argument("--to", dest="to_name", required=True)
    s.add_argument("--type", dest="rel_type", required=True)

    s = sub.add_parser("connected")
    s.add_argument("name")

    sub.add_parser("prune")
    sub.add_parser("health")

    s = sub.add_parser("decay")
    s.add_argument("--days", type=int, default=30)
    s.add_argument("--min-uses", type=int, default=2)

    s = sub.add_parser("chunk")
    s.add_argument("--task", required=True)
    s.add_argument("--outcome", required=True)
    s.add_argument("--approach", required=True)
    s.add_argument("--source", default="chunked")

    sub.add_parser("consolidate")

    s = sub.add_parser("get")
    s.add_argument("name")

    args = p.parse_args()

    if args.cmd == "store":
        r = store(args.trigger, args.resolution, args.type, args.source)
    elif args.cmd == "recall":
        r = recall(args.query, args.type, args.limit)
    elif args.cmd == "feedback":
        r = feedback(json.loads(args.utilized), json.loads(args.injected))
    elif args.cmd == "feedback-verify":
        r = feedback_from_verification(
            task_id=args.task_id,
            verify_passed=args.verify_passed,
            injected=json.loads(args.injected)
        )
    elif args.cmd == "relate":
        r = relate(args.from_name, args.to_name, args.rel_type)
    elif args.cmd == "connected":
        r = connected(args.name)
    elif args.cmd == "prune":
        r = prune()
    elif args.cmd == "health":
        r = health()
    elif args.cmd == "decay":
        r = decay(args.days, args.min_uses)
    elif args.cmd == "chunk":
        r = chunk(args.task, args.outcome, args.approach, args.source)
    elif args.cmd == "consolidate":
        r = consolidate()
    elif args.cmd == "get":
        r = get(args.name)
        if r is None:
            r = {"error": "not found"}

    print(json.dumps(r, indent=2))
