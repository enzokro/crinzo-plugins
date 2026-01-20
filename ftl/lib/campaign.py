#!/usr/bin/env python3
"""Campaign operations with fastsql database backend.

Provides campaign lifecycle management, task DAG scheduling,
similarity search, and adaptive re-planning support.
"""

from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
import json
import argparse
import sys
import hashlib

# Support both standalone execution and module import
try:
    from lib.db import get_db, init_db, Campaign, Archive, db_write_lock
    from lib.db.embeddings import embed, embed_to_blob, cosine_similarity_blob, similarity
    from lib.phase import error_boundary
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from db import get_db, init_db, Campaign, Archive, db_write_lock
    from db.embeddings import embed, embed_to_blob, cosine_similarity_blob, similarity
    from phase import error_boundary


def _ensure_db():
    """Ensure database is initialized on first use."""
    init_db()
    return get_db()


def _get_active_campaign():
    """Get the currently active campaign, if any."""
    db = _ensure_db()
    campaigns = db.t.campaign
    rows = list(campaigns.rows_where("status = ?", ["active"]))
    if rows:
        # Return most recent active campaign
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return rows[0]
    return None


# =============================================================================
# Request-scoped cache (no-op for database backend)
# =============================================================================

@contextmanager
def campaign_session():
    """Context manager for batched campaign operations (no-op with DB)."""
    yield


# =============================================================================
# Core Campaign Operations
# =============================================================================

def create(objective: str, framework: str = None) -> dict:
    """Create new campaign.

    Args:
        objective: Campaign objective
        framework: Optional framework name

    Returns:
        Campaign dict with id and objective
    """
    db = _ensure_db()
    campaigns = db.t.campaign

    # Generate embedding for objective
    emb = embed(objective)
    emb_blob = embed_to_blob(emb) if emb else None

    campaign = Campaign(
        objective=objective,
        framework=framework,
        status="active",
        created_at=datetime.now().isoformat(),
        completed_at=None,
        tasks="[]",
        summary="{}",
        fingerprint="{}",
        patterns_extracted="[]",
        objective_embedding=emb_blob
    )

    result = campaigns.insert(campaign)
    now = datetime.now().isoformat()

    return {
        "id": result.id,
        "objective": objective,
        "status": "active",
        "tasks": [],
        "framework": framework,
        "created_at": now
    }


def add_tasks(plan: dict) -> None:
    """Add tasks from planner output.

    Args:
        plan: Plan dict with tasks[]

    Raises:
        ValueError: If no active campaign, cycle detected, or dangling dependency
    """
    with error_boundary("add_tasks"):
        campaign = _get_active_campaign()
        if not campaign:
            raise ValueError("No active campaign")

        tasks = plan.get("tasks", [])

        # Detect cycles before registering
        cycle = _detect_cycle(tasks)
        if cycle:
            cycle_str = " -> ".join(str(s) for s in cycle)
            raise ValueError(f"Cycle detected in task dependencies: {cycle_str}")

        # Validate no dangling dependencies (deps must reference existing task seqs)
        task_seqs = {_normalize_seq(t["seq"]) for t in tasks}
        for task in tasks:
            deps = _get_deps(task)
            for dep in deps:
                if dep not in task_seqs:
                    raise ValueError(
                        f"Dangling dependency: task {task['seq']} depends on {dep}, "
                        f"which does not exist in the plan. Valid seqs: {sorted(task_seqs)}"
                    )

        db = _ensure_db()
        campaigns = db.t.campaign

        # Build task entries with status
        task_entries = [
            {
                "seq": t["seq"],
                "slug": t["slug"],
                "type": t.get("type", "BUILD"),
                "depends": t.get("depends", "none"),
                "status": "pending"
            }
            for t in tasks
        ]

        # Use lock to prevent concurrent overwrites
        # Note: fastsql provides single-operation atomicity; explicit transactions
        # conflict with its auto-commit behavior
        with db_write_lock:
            # Re-fetch campaign inside lock to ensure freshness (TOCTOU protection)
            campaign = _get_active_campaign()
            if not campaign:
                raise ValueError("No active campaign")

            campaigns.update({
                "framework": plan.get("framework"),
                "tasks": json.dumps(task_entries)
            }, campaign["id"])


def update_task(seq, status: str) -> None:
    """Update task status.

    Args:
        seq: Task sequence number (int or string)
        status: New status (pending, in_progress, complete, blocked)

    Raises:
        ValueError: If no active campaign or task seq not found
    """
    with error_boundary("update_task"):
        campaign = _get_active_campaign()
        if not campaign:
            raise ValueError("No active campaign")

        db = _ensure_db()
        campaigns = db.t.campaign

        seq_normalized = _normalize_seq(seq)

        # Use lock to prevent cross-thread races on read-modify-write
        with db_write_lock:
            # Re-read inside lock for fresh state
            campaign_rows = list(campaigns.rows_where("id = ?", [campaign["id"]]))
            if not campaign_rows:
                raise ValueError("Campaign disappeared during update")

            campaign = campaign_rows[0]
            tasks = json.loads(campaign["tasks"])

            found = False
            for task in tasks:
                if _normalize_seq(task["seq"]) == seq_normalized:
                    task["status"] = status
                    task["updated_at"] = datetime.now().isoformat()
                    found = True
                    break

            if not found:
                raise ValueError(f"Task seq {seq} not found in campaign")

            # Single atomic update (fastsql provides single-op atomicity)
            campaigns.update({"tasks": json.dumps(tasks)}, campaign["id"])


def next_task() -> dict | None:
    """Get next pending task.

    Returns:
        Task dict or None if no pending tasks
    """
    campaign = _get_active_campaign()
    if not campaign:
        return None

    tasks = json.loads(campaign["tasks"])
    for task in tasks:
        if task.get("status") == "pending":
            return task
    return None


def ready_tasks() -> list:
    """Get all tasks ready for execution (pending with all deps complete).

    Returns:
        List of task dicts ready for parallel execution
    """
    campaign = _get_active_campaign()
    if not campaign:
        return []

    tasks = json.loads(campaign["tasks"])

    # Build set of completed seqs
    completed_seqs = {
        _normalize_seq(t["seq"])
        for t in tasks
        if t.get("status") == "complete"
    }

    ready = []
    for task in tasks:
        if task.get("status") != "pending":
            continue

        deps = _get_deps(task)
        if all(d in completed_seqs for d in deps):
            ready.append(task)

    return ready


def cascade_status() -> dict:
    """Detect if campaign is stuck due to blocked parent cascade.

    Returns:
        Status dict with state, counts, and unreachable tasks
    """
    campaign = _get_active_campaign()
    if not campaign:
        return {"state": "none"}

    tasks = json.loads(campaign["tasks"])
    if not tasks:
        return {"state": "complete", "ready": 0, "pending": 0, "complete": 0, "blocked": 0, "unreachable": []}

    # Count by status
    counts = {
        "complete": sum(1 for t in tasks if t.get("status") == "complete"),
        "blocked": sum(1 for t in tasks if t.get("status") == "blocked"),
        "pending": sum(1 for t in tasks if t.get("status") == "pending"),
    }

    ready = ready_tasks()
    counts["ready"] = len(ready)

    if ready:
        return {"state": "in_progress", **counts, "unreachable": []}

    if counts["pending"] == 0:
        return {"state": "complete", **counts, "unreachable": []}

    # Check for cascade
    blocked_seqs = {
        _normalize_seq(t["seq"])
        for t in tasks
        if t.get("status") == "blocked"
    }

    unreachable = []
    for t in tasks:
        if t.get("status") != "pending":
            continue

        deps = _get_deps(t)
        blocking_parents = [str(d) for d in deps if d in blocked_seqs]

        if blocking_parents:
            unreachable.append({
                "seq": t["seq"],
                "blocked_by": blocking_parents
            })

    if unreachable:
        return {"state": "stuck", **counts, "unreachable": unreachable}

    return {"state": "all_blocked", **counts, "unreachable": []}


def propagate_blocks() -> list:
    """Mark all unreachable tasks as blocked due to parent cascade.

    Returns:
        List of task seqs that were marked blocked
    """
    with error_boundary("propagate_blocks"):
        all_propagated = []
        db = _ensure_db()
        campaigns = db.t.campaign

        while True:
            # Use lock to prevent cross-thread races on read-modify-write
            with db_write_lock:
                # Get active campaign
                rows = list(campaigns.rows_where("status = ?", ["active"]))
                if not rows:
                    break

                rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
                campaign = rows[0]
                tasks = json.loads(campaign["tasks"])

                if not tasks:
                    break

                # Compute cascade status
                completed_seqs = {_normalize_seq(t["seq"]) for t in tasks if t.get("status") == "complete"}
                blocked_seqs = {_normalize_seq(t["seq"]) for t in tasks if t.get("status") == "blocked"}

                # Find ready tasks (pending with all deps complete)
                ready = []
                for task in tasks:
                    if task.get("status") != "pending":
                        continue
                    deps = _get_deps(task)
                    if all(d in completed_seqs for d in deps):
                        ready.append(task)

                # If tasks are ready, not stuck
                if ready:
                    break

                # Check for unreachable tasks (pending with blocked deps)
                unreachable = []
                for t in tasks:
                    if t.get("status") != "pending":
                        continue
                    deps = _get_deps(t)
                    blocking_parents = [str(d) for d in deps if d in blocked_seqs]
                    if blocking_parents:
                        unreachable.append({"seq": t["seq"], "blocked_by": blocking_parents})

                if not unreachable:
                    break

                # Propagate blocks
                unreachable_map = {u["seq"]: u["blocked_by"] for u in unreachable}
                propagated = []
                now = datetime.now().isoformat()

                for task in tasks:
                    if task["seq"] in unreachable_map:
                        task["status"] = "blocked"
                        task["blocked_by"] = unreachable_map[task["seq"]]
                        task["updated_at"] = now
                        propagated.append(task["seq"])

                # Single atomic update (fastsql provides atomicity for single ops)
                campaigns.update({"tasks": json.dumps(tasks)}, campaign["id"])
                all_propagated.extend(propagated)

                # If nothing was propagated, we're done
                if not propagated:
                    break

        return all_propagated


def status() -> dict:
    """Get campaign status.

    Returns:
        Campaign dict or {"status": "none"} if no campaign
    """
    campaign = _get_active_campaign()
    if not campaign:
        return {"status": "none"}

    return {
        "status": campaign["status"],
        "objective": campaign["objective"],
        "framework": campaign.get("framework"),
        "created_at": campaign.get("created_at"),
        "tasks": json.loads(campaign["tasks"]),
        "summary": json.loads(campaign.get("summary") or "{}"),
    }


def active() -> dict | None:
    """Get active campaign or None."""
    campaign = _get_active_campaign()
    if not campaign:
        return None

    return {
        "id": campaign["id"],
        "status": campaign["status"],
        "objective": campaign["objective"],
        "framework": campaign.get("framework"),
        "created_at": campaign.get("created_at"),
        "tasks": json.loads(campaign["tasks"]),
    }


def complete(summary: str = None, patterns_extracted: list = None) -> dict:
    """Complete campaign and archive it.

    Args:
        summary: Optional summary text
        patterns_extracted: Optional list of pattern names extracted

    Returns:
        Final campaign dict
    """
    with error_boundary("campaign_complete"):
        campaign = _get_active_campaign()
        if not campaign:
            raise ValueError("No active campaign")

        db = _ensure_db()
        campaigns = db.t.campaign
        archives = db.t.archive

        completed_at = datetime.now().isoformat()
        tasks = json.loads(campaign["tasks"])

        # Calculate summary - ensure it's always a dict to avoid double-encoding
        if summary is not None:
            if isinstance(summary, dict):
                summary_data = summary
            elif isinstance(summary, str):
                # Try to parse as JSON, fall back to wrapping in dict
                try:
                    parsed = json.loads(summary)
                    summary_data = parsed if isinstance(parsed, dict) else {"text": summary}
                except json.JSONDecodeError:
                    summary_data = {"text": summary}
            else:
                summary_data = {"value": summary}
        else:
            summary_data = {
                "total": len(tasks),
                "complete": sum(1 for t in tasks if t.get("status") == "complete"),
                "blocked": sum(1 for t in tasks if t.get("status") == "blocked"),
            }

        # Generate fingerprint
        fp = fingerprint({"objective": campaign["objective"], "framework": campaign.get("framework"), "tasks": tasks})

        # Determine outcome
        if isinstance(summary_data, dict):
            total = summary_data.get("total", 0)
            complete_count = summary_data.get("complete", 0)
            outcome = "complete" if complete_count == total else "partial"
        else:
            outcome = "complete"

        # Use lock for atomic operations (fastsql provides single-op atomicity)
        with db_write_lock:
            # Update campaign
            campaigns.update({
                "status": "complete",
                "completed_at": completed_at,
                "summary": json.dumps(summary_data),
                "fingerprint": json.dumps(fp),
                "patterns_extracted": json.dumps(patterns_extracted or [])
            }, campaign["id"])

            # Create archive entry in database
            archives.insert(Archive(
                campaign_id=campaign["id"],
                objective=campaign["objective"],
                objective_preview=campaign["objective"][:100],
                framework=campaign.get("framework"),
                completed_at=completed_at,
                fingerprint=json.dumps(fp),
                objective_embedding=campaign.get("objective_embedding"),
                outcome=outcome,
                summary=json.dumps(summary_data),
                patterns_extracted=json.dumps(patterns_extracted or [])
            ))

        return {
            "status": "complete",
            "objective": campaign["objective"],
            "completed_at": completed_at,
            "summary": summary_data,
            "fingerprint": fp,
        }


def history() -> dict:
    """Get archived campaign history.

    Returns:
        Dict with archives list
    """
    db = _ensure_db()
    archives = db.t.archive

    result = []
    for row in archives.rows:
        result.append({
            "objective": row["objective"],
            "completed_at": row.get("completed_at"),
            "summary": json.loads(row.get("summary") or "{}"),
        })

    # Sort by completed_at descending
    result.sort(key=lambda x: x.get("completed_at", ""), reverse=True)
    return {"archives": result}


def export_history(output_file: str, start_date: str = None, end_date: str = None) -> dict:
    """Export campaign history to JSON file.

    Args:
        output_file: Path to output JSON file
        start_date: Optional start date (YYYY-MM-DD)
        end_date: Optional end date (YYYY-MM-DD)

    Returns:
        Dict with campaigns list
    """
    db = _ensure_db()
    archives = db.t.archive
    campaigns_table = db.t.campaign

    campaign_list = []

    # Get completed campaigns
    for row in campaigns_table.rows_where("status = ?", ["complete"]):
        completed_at = row.get("completed_at", "")
        if completed_at:
            campaign_date = completed_at[:10]
        else:
            campaign_date = ""

        if start_date and campaign_date < start_date:
            continue
        if end_date and campaign_date > end_date:
            continue

        campaign_list.append({
            "objective": row["objective"],
            "framework": row.get("framework"),
            "completed_at": completed_at,
            "tasks": json.loads(row["tasks"]),
            "summary": json.loads(row.get("summary") or "{}"),
            "fingerprint": json.loads(row.get("fingerprint") or "{}"),
        })

    result = {"campaigns": campaign_list}

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2))

    return result


def fingerprint(campaign: dict = None) -> dict:
    """Generate fingerprint for campaign similarity matching.

    Args:
        campaign: Campaign dict (if None, uses active campaign)

    Returns:
        Fingerprint dict
    """
    if campaign is None:
        active_camp = _get_active_campaign()
        if not active_camp:
            return {}
        campaign = {
            "objective": active_camp["objective"],
            "framework": active_camp.get("framework"),
            "tasks": json.loads(active_camp["tasks"])
        }

    tasks = campaign.get("tasks", [])

    # Collect delta files from exploration
    delta_files = []
    try:
        db = _ensure_db()
        explorations = db.t.exploration
        exp_rows = list(explorations.rows)
        if exp_rows:
            exp_rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
            delta = json.loads(exp_rows[0].get("delta") or "{}")
            candidates = delta.get("candidates", [])
            # Support both "file" and "path" field names for delta candidates
            delta_files = sorted(set(
                c.get("path", c.get("file", ""))
                for c in candidates
                if c.get("path") or c.get("file")
            ))
    except Exception as e:
        import logging
        logging.warning(f"Failed to extract delta files for fingerprint: {e}")

    objective = campaign.get("objective", "")
    obj_hash = hashlib.md5(objective.encode()).hexdigest()[:8]

    return {
        "framework": campaign.get("framework") or "none",
        "task_count": len(tasks),
        "task_types": sorted(set(t.get("type", "BUILD") for t in tasks)),
        "delta_files": delta_files[:20],
        "objective_hash": obj_hash,
        "objective_preview": objective[:100],
    }


def find_similar(
    current_fingerprint: dict = None,
    threshold: float = 0.5,  # Aligned with spec (was 0.6)
    max_results: int = 5
) -> list:
    """Find campaigns similar to the current one.

    Args:
        current_fingerprint: Fingerprint to compare (if None, uses active)
        threshold: Minimum similarity score
        max_results: Maximum number of results

    Returns:
        List of similar campaigns with similarity scores
    """
    if current_fingerprint is None:
        current_fingerprint = fingerprint()

    if not current_fingerprint:
        return []

    current_framework = current_fingerprint.get("framework", "none")
    current_objective = current_fingerprint.get("objective_preview", "")
    current_delta = set(current_fingerprint.get("delta_files", []))

    # Get current embedding
    current_emb = embed(current_objective)
    current_emb_blob = embed_to_blob(current_emb) if current_emb else None

    db = _ensure_db()
    archives = db.t.archive

    results = []

    for row in archives.rows:
        arch_fp = json.loads(row.get("fingerprint") or "{}")
        if not arch_fp:
            arch_fp = {
                "framework": row.get("framework") or "none",
                "task_count": 0,
                "objective_preview": row.get("objective_preview", "")[:100],
            }

        # Framework must match
        arch_framework = arch_fp.get("framework", "none")
        if current_framework != "none" and arch_framework != current_framework:
            continue

        # Calculate similarity
        sim = 0.0

        # Objective embedding similarity (weight: 0.6)
        arch_emb_blob = row.get("objective_embedding")
        if current_emb_blob and arch_emb_blob:
            sim += 0.6 * cosine_similarity_blob(current_emb_blob, arch_emb_blob)
        else:
            arch_objective = arch_fp.get("objective_preview", row.get("objective", "")[:100])
            sim += 0.6 * similarity(current_objective, arch_objective)

        # Delta file overlap (weight: 0.3)
        arch_delta = set(arch_fp.get("delta_files", []))
        if current_delta and arch_delta:
            overlap = len(current_delta & arch_delta) / max(len(current_delta | arch_delta), 1)
            sim += 0.3 * overlap

        # Task count similarity (weight: 0.1)
        current_tasks = current_fingerprint.get("task_count", 0)
        arch_tasks = arch_fp.get("task_count", 0)
        if current_tasks > 0 and arch_tasks > 0:
            task_sim = 1.0 - abs(current_tasks - arch_tasks) / max(current_tasks, arch_tasks)
            sim += 0.1 * task_sim

        if sim >= threshold:
            results.append({
                "archive": str(row["id"]),
                "similarity": round(sim, 3),
                "fingerprint": arch_fp,
                "outcome": row.get("outcome", "complete"),
                "objective": row.get("objective", "")[:100],
                "patterns_from": json.loads(row.get("patterns_extracted") or "[]"),
            })

    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:max_results]


def get_replan_input() -> dict:
    """Generate input for adaptive re-planning.

    Returns:
        Context dict for Planner to generate revised plan
    """
    campaign = _get_active_campaign()
    if not campaign:
        return {}

    tasks = json.loads(campaign["tasks"])
    completed = [t for t in tasks if t.get("status") == "complete"]
    blocked = [t for t in tasks if t.get("status") == "blocked"]
    pending = [t for t in tasks if t.get("status") == "pending"]

    # Collect delivery evidence
    completed_evidence = []
    for task in completed:
        try:
            from lib.workspace import parse
            ws = parse(f"{task['seq']}-{task.get('slug', '')}")
            completed_evidence.append({
                "seq": task["seq"],
                "slug": task.get("slug", ""),
                "delivered": ws.get("delivered", "")[:200]
            })
        except Exception:
            completed_evidence.append({
                "seq": task["seq"],
                "slug": task.get("slug", ""),
                "delivered": "(no workspace)"
            })

    # Collect block reasons
    blocked_reasons = []
    for task in blocked:
        try:
            from lib.workspace import parse
            ws = parse(f"{task['seq']}-{task.get('slug', '')}")
            delivered = ws.get("delivered", "")
            reason = delivered.replace("BLOCKED: ", "")[:100] if "BLOCKED:" in delivered else delivered[:100]
            blocked_reasons.append({
                "seq": task["seq"],
                "slug": task.get("slug", ""),
                "reason": reason
            })
        except Exception:
            blocked_reasons.append({
                "seq": task["seq"],
                "slug": task.get("slug", ""),
                "reason": "(no workspace)"
            })

    return {
        "mode": "replan",
        "objective": campaign["objective"],
        "framework": campaign.get("framework"),
        "completed_count": len(completed),
        "blocked_count": len(blocked),
        "pending_count": len(pending),
        "completed_tasks": completed_evidence,
        "blocked_tasks": blocked_reasons,
        "remaining_tasks": [
            {
                "seq": t["seq"],
                "slug": t.get("slug", ""),
                "type": t.get("type", "BUILD"),
                "depends": t.get("depends", "none")
            }
            for t in pending
        ]
    }


def merge_revised_plan(revised_plan_path: str) -> dict:
    """Merge revised plan into active campaign.

    Args:
        revised_plan_path: Path to revised plan JSON

    Returns:
        {"merged": int, "unchanged": int}
    """
    import copy

    revised_path = Path(revised_plan_path)
    if not revised_path.exists():
        return {"error": "Revised plan not found", "merged": 0, "unchanged": 0}

    try:
        revised = json.loads(revised_path.read_text())
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON: {e}", "merged": 0, "unchanged": 0}

    with error_boundary("merge_revised_plan"):
        campaign = _get_active_campaign()
        if not campaign:
            return {"error": "No active campaign", "merged": 0, "unchanged": 0}

        db = _ensure_db()
        campaigns = db.t.campaign

        tasks = json.loads(campaign["tasks"])

        # Validate and build revised tasks dict, skipping malformed entries
        revised_tasks = {}
        for t in revised.get("tasks", []):
            if not isinstance(t, dict) or "seq" not in t:
                continue  # Skip malformed task entries
            revised_tasks[t["seq"]] = t

        # Work on deep copy to ensure atomicity - original state preserved if cycle detected
        tasks_copy = copy.deepcopy(tasks)
        merged_count = 0
        unchanged_count = 0
        now = datetime.now().isoformat()

        for task in tasks_copy:
            seq = task["seq"]
            if seq not in revised_tasks:
                unchanged_count += 1
                continue

            revised_task = revised_tasks[seq]
            current_status = task.get("status", "pending")

            if current_status == "complete":
                unchanged_count += 1
                continue

            new_depends = revised_task.get("depends", task.get("depends", "none"))
            old_depends = task.get("depends", "none")

            if current_status == "blocked" or new_depends != old_depends:
                task["status"] = "pending"
                task["depends"] = new_depends
                task["revised_at"] = now
                # Clear orphaned blocked_by metadata from previous cascade
                task.pop("blocked_by", None)
                merged_count += 1
            else:
                unchanged_count += 1

        # Validate no cycles introduced by dependency changes BEFORE committing
        cycle = _detect_cycle([{"seq": t["seq"], "depends": t.get("depends", "none")} for t in tasks_copy])
        if cycle:
            cycle_str = " -> ".join(str(s) for s in cycle)
            # Return error without modifying original state - atomicity preserved
            return {"error": f"Cycle detected after merge: {cycle_str}", "merged": 0, "unchanged": 0}

        # Validate no dangling dependencies (deps must reference existing task seqs)
        task_seqs = {_normalize_seq(t["seq"]) for t in tasks_copy}
        for task in tasks_copy:
            deps = _get_deps(task)
            for dep in deps:
                if dep not in task_seqs:
                    return {
                        "error": f"Dangling dependency: task {task['seq']} depends on {dep}, "
                                 f"which does not exist. Valid seqs: {sorted(task_seqs)}",
                        "merged": 0,
                        "unchanged": 0
                    }

        # Use lock for atomic persist (fastsql provides single-op atomicity)
        with db_write_lock:
            campaigns.update({"tasks": json.dumps(tasks_copy)}, campaign["id"])

        return {"merged": merged_count, "unchanged": unchanged_count}


# =============================================================================
# Helper Functions
# =============================================================================

def _normalize_seq(seq) -> int | str:
    """Normalize seq to int for comparison."""
    try:
        return int(seq)
    except (ValueError, TypeError):
        return seq


def _get_deps(task: dict) -> list:
    """Extract normalized dependency list from task."""
    depends = task.get("depends", "none")
    if depends == "none" or depends is None:
        return []
    if isinstance(depends, str):
        return [_normalize_seq(depends)]
    return [_normalize_seq(d) for d in depends if d and d != "none"]


def _detect_cycle(tasks: list) -> list | None:
    """Detect cycle in task dependencies using DFS."""
    task_seqs = {_normalize_seq(t["seq"]) for t in tasks}
    deps = {_normalize_seq(t["seq"]): _get_deps(t) for t in tasks}

    visited = set()
    path = []
    path_set = set()

    def dfs(seq):
        if seq in path_set:
            cycle_start = path.index(seq)
            return path[cycle_start:] + [seq]
        if seq in visited:
            return None

        path.append(seq)
        path_set.add(seq)

        for dep in deps.get(seq, []):
            if dep in task_seqs:
                result = dfs(dep)
                if result:
                    return result

        path.pop()
        path_set.remove(seq)
        visited.add(seq)
        return None

    for seq in task_seqs:
        if seq not in visited:
            result = dfs(seq)
            if result:
                return result

    return None


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="FTL campaign operations")
    subparsers = parser.add_subparsers(dest="command")

    # create command
    c = subparsers.add_parser("create", help="Create new campaign")
    c.add_argument("objective", help="Campaign objective")
    c.add_argument("--framework", help="Framework name")

    # add-tasks command
    at = subparsers.add_parser("add-tasks", help="Add tasks from plan (stdin)")

    # update-task command
    ut = subparsers.add_parser("update-task", help="Update task status")
    ut.add_argument("seq", help="Task sequence number")
    ut.add_argument("status", help="New status")

    # next-task command
    subparsers.add_parser("next-task", help="Get next pending task")

    # ready-tasks command
    subparsers.add_parser("ready-tasks", help="Get all tasks ready for parallel execution")

    # cascade-status command
    subparsers.add_parser("cascade-status", help="Check if campaign is stuck")

    # propagate-blocks command
    subparsers.add_parser("propagate-blocks", help="Mark unreachable tasks as blocked")

    # status command
    subparsers.add_parser("status", help="Get campaign status")

    # complete command
    comp = subparsers.add_parser("complete", help="Complete campaign")
    comp.add_argument("--summary", help="Summary text")

    # active command
    subparsers.add_parser("active", help="Check if campaign is active")

    # history command
    subparsers.add_parser("history", help="List archived campaigns")

    # export command
    exp = subparsers.add_parser("export", help="Export campaign history to file")
    exp.add_argument("output_file", help="Output JSON file path")
    exp.add_argument("--start", dest="start", help="Start date (YYYY-MM-DD)")
    exp.add_argument("--end", dest="end", help="End date (YYYY-MM-DD)")

    # fingerprint command
    subparsers.add_parser("fingerprint", help="Generate fingerprint for current campaign")

    # find-similar command
    sim = subparsers.add_parser("find-similar", help="Find similar archived campaigns")
    sim.add_argument("--threshold", type=float, default=0.5, help="Similarity threshold (default: 0.5)")
    sim.add_argument("--max", type=int, default=5, help="Maximum results")

    # get-replan-input command
    subparsers.add_parser("get-replan-input", help="Get input for adaptive re-planning")

    # merge-revised-plan command
    mrp = subparsers.add_parser("merge-revised-plan", help="Merge revised plan into campaign")
    mrp.add_argument("plan_path", help="Path to revised plan JSON")

    args = parser.parse_args()

    if args.command == "create":
        result = create(args.objective, args.framework)
        print(json.dumps(result, indent=2))

    elif args.command == "add-tasks":
        plan = json.load(sys.stdin)
        add_tasks(plan)
        print("Tasks added")

    elif args.command == "update-task":
        update_task(args.seq, args.status)
        print(f"Task {args.seq} -> {args.status}")

    elif args.command == "next-task":
        task = next_task()
        if task:
            print(json.dumps(task, indent=2))
        else:
            print("null")

    elif args.command == "ready-tasks":
        tasks = ready_tasks()
        print(json.dumps(tasks, indent=2))

    elif args.command == "cascade-status":
        result = cascade_status()
        print(json.dumps(result, indent=2))

    elif args.command == "propagate-blocks":
        propagated = propagate_blocks()
        if propagated:
            print(f"Propagated blocks to: {', '.join(propagated)}")
        else:
            print("No blocks to propagate")

    elif args.command == "status":
        result = status()
        print(json.dumps(result, indent=2))

    elif args.command == "complete":
        result = complete(args.summary)
        print(json.dumps(result, indent=2))

    elif args.command == "active":
        result = active()
        if result:
            print(json.dumps(result, indent=2))
        else:
            print("null")

    elif args.command == "history":
        result = history()
        print(json.dumps(result, indent=2))

    elif args.command == "export":
        result = export_history(args.output_file, args.start, args.end)
        print(json.dumps(result, indent=2))

    elif args.command == "fingerprint":
        result = fingerprint()
        print(json.dumps(result, indent=2))

    elif args.command == "find-similar":
        result = find_similar(threshold=args.threshold, max_results=args.max)
        print(json.dumps(result, indent=2))

    elif args.command == "get-replan-input":
        result = get_replan_input()
        print(json.dumps(result, indent=2))

    elif args.command == "merge-revised-plan":
        result = merge_revised_plan(args.plan_path)
        print(json.dumps(result, indent=2))

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
