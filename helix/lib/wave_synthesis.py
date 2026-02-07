#!/usr/bin/env python3
"""Cross-wave synthesis: detect convergent issues, emit warnings.

After each parallel wave completes, compares builder summaries to detect
when multiple builders independently discovered the same issue. Synthesizes
convergent findings into WARNING directives for the next wave.

Also collects parent deliveries for dependency-aware context propagation.
"""

import json
import sys
from pathlib import Path
from typing import List, Optional

# Support both module and script execution
try:
    from lib.memory.embeddings import embed, cosine
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from memory.embeddings import embed, cosine

CONVERGENCE_THRESHOLD = 0.65
MIN_CONVERGENT_COUNT = 2


def _union_find_clusters(items: list, similarity_fn, threshold: float) -> list[list[int]]:
    """Union-find clustering based on pairwise similarity.

    Args:
        items: List of items to cluster
        similarity_fn: (item_a, item_b) -> float
        threshold: Minimum similarity to merge clusters

    Returns: List of clusters (each cluster is a list of indices)
    """
    n = len(items)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(n):
        for j in range(i + 1, n):
            if similarity_fn(items[i], items[j]) >= threshold:
                union(i, j)

    clusters = {}
    for i in range(n):
        root = find(i)
        clusters.setdefault(root, []).append(i)

    return list(clusters.values())


def synthesize_wave_warnings(
    wave_results: list,
    threshold: float = CONVERGENCE_THRESHOLD,
    min_count: int = MIN_CONVERGENT_COUNT
) -> list[str]:
    """Detect convergent issues across wave results and format as warnings.

    Args:
        wave_results: List of dicts with at least "summary" and optionally
                      "task_id", "insight", "outcome" fields
        threshold: Cosine similarity threshold for convergence detection
        min_count: Minimum cluster size to emit a warning

    Returns: List of WARNING strings for injection into next wave
    """
    # Filter to results with summaries
    summaries = []
    for r in wave_results:
        text = r.get("summary", "") or ""
        insight = r.get("insight", "") or ""
        combined = f"{text} {insight}".strip()
        if combined:
            summaries.append({"text": combined, "task_id": r.get("task_id", "?"), "result": r})

    if len(summaries) < min_count:
        return []

    # Embed all summaries
    embeddings = []
    valid = []
    for s in summaries:
        emb = embed(s["text"], is_query=False)
        if emb:
            embeddings.append(emb)
            valid.append(s)

    if len(valid) < min_count:
        return []

    # Cluster by similarity
    def sim_fn(a, b):
        return cosine(a, b)

    clusters = _union_find_clusters(embeddings, sim_fn, threshold)

    # Format warnings for convergent clusters
    warnings = []
    for cluster in clusters:
        if len(cluster) < min_count:
            continue

        # Build warning from cluster members
        task_ids = [valid[i]["task_id"] for i in cluster]
        texts = [valid[i]["text"][:150] for i in cluster]

        # Use first summary as representative, note all task IDs
        warning = (
            f"CONVERGENT ISSUE (tasks {', '.join(task_ids)}): "
            f"Multiple builders encountered similar issue. "
            f"Representative: {texts[0]}"
        )
        warnings.append(warning)

    return warnings


def collect_parent_deliveries(
    wave_results: list,
    task_blockers: dict
) -> dict[str, str]:
    """Map next-wave task_id -> formatted PARENT_DELIVERIES from completed blockers.

    Args:
        wave_results: List of dicts with "task_id", "summary", "outcome" fields
        task_blockers: Dict mapping next-wave task_id -> list of blocker task_ids

    Returns: Dict mapping next-wave task_id -> formatted parent delivery string
    """
    # Index wave results by task_id (both "task-N" and "N" formats)
    result_by_id = {}
    for r in wave_results:
        tid = r.get("task_id")
        if tid:
            result_by_id[tid] = r
            # Normalize: index under both formats for cross-format lookup
            if tid.startswith("task-"):
                result_by_id[tid.removeprefix("task-")] = r
            else:
                result_by_id[f"task-{tid}"] = r

    deliveries = {}
    for next_task_id, blocker_ids in task_blockers.items():
        parts = []
        for bid in blocker_ids:
            result = result_by_id.get(bid)
            if result and result.get("outcome") == "delivered":
                summary = result.get("summary", "")[:200]
                if summary:
                    parts.append(f"[{bid}] {summary}")
        if parts:
            deliveries[next_task_id] = "\n".join(parts)

    return deliveries


# CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Cross-wave synthesis utilities")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    p_synth = subparsers.add_parser("synthesize", help="Detect convergent issues in wave results")
    p_synth.add_argument("--results", required=True, help="JSON array of wave result dicts")
    p_synth.add_argument("--threshold", type=float, default=CONVERGENCE_THRESHOLD)
    p_synth.add_argument("--min-count", type=int, default=MIN_CONVERGENT_COUNT)

    p_parent = subparsers.add_parser("parent-deliveries", help="Collect parent deliveries for next wave")
    p_parent.add_argument("--results", required=True, help="JSON array of wave result dicts")
    p_parent.add_argument("--blockers", required=True, help="JSON dict: next_task_id -> [blocker_ids]")

    args = parser.parse_args()

    if args.cmd == "synthesize":
        results = json.loads(args.results)
        warnings = synthesize_wave_warnings(results, args.threshold, args.min_count)
        print(json.dumps({"warnings": warnings, "count": len(warnings)}))

    elif args.cmd == "parent-deliveries":
        results = json.loads(args.results)
        blockers = json.loads(args.blockers)
        deliveries = collect_parent_deliveries(results, blockers)
        print(json.dumps(deliveries))
