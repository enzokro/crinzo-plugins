#!/usr/bin/env python3
"""FTL Campaign Agent Log Analyzer.

Usage: python3 analyze.py results/v8
       python3 analyze.py results/v8 --json
       python3 analyze.py results/v8 --detailed
"""
import json
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime


def classify_agent(first_user_msg: str) -> str:
    """Classify agent by first user message content."""
    if not first_user_msg:
        return "unknown"
    msg = first_user_msg.lower()

    if msg.startswith("warmup"):
        return "warmup"
    if msg.startswith("objective:"):
        return "planner"
    if msg.startswith("synthesize") or "campaign completed" in msg:
        return "synthesizer"
    if "campaign:" in msg and "task:" in msg[:300]:
        return "router"
    if "workspace:" in msg or ".ftl/workspace/" in msg:
        if "_active" in msg[:600]:
            return "builder"
        elif "_complete" in msg[:600]:
            return "learner"
    return "unknown"


def parse_agent(filepath: Path) -> dict:
    """Parse single agent log file with full detail."""
    result = {
        "file": filepath.name,
        "type": "unknown",
        "model": "unknown",
        "tokens": {
            "input": 0,
            "cache_read": 0,
            "cache_create": 0,
            "output": 0,
            "total": 0,
        },
        "api_calls": 0,
        "tools": defaultdict(int),
        "tool_calls": 0,
        "first_reads": [],
        "cache_hit": False,
        "errors": [],
        "duration_estimate": 0,
    }
    first_user = None
    read_calls = []
    bash_commands = []
    timestamps = []

    with open(filepath, "r") as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
            except json.JSONDecodeError:
                continue

            # Track timestamps
            if "timestamp" in entry:
                timestamps.append(entry["timestamp"])

            # Extract first user message
            if first_user is None and entry.get("type") == "user":
                content = entry.get("message", {}).get("content", [])
                if isinstance(content, str):
                    first_user = content[:600]
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            first_user = block.get("text", "")[:600]
                            break

            # Extract assistant info
            if entry.get("type") == "assistant":
                msg = entry.get("message", {})

                # Model
                if msg.get("model") and result["model"] == "unknown":
                    result["model"] = msg["model"]

                # Tokens
                usage = msg.get("usage", {})
                if usage:
                    result["api_calls"] += 1
                    result["tokens"]["input"] += usage.get("input_tokens", 0)
                    result["tokens"]["cache_read"] += usage.get("cache_read_input_tokens", 0)
                    result["tokens"]["cache_create"] += usage.get("cache_creation_input_tokens", 0)
                    result["tokens"]["output"] += usage.get("output_tokens", 0)

                # Tool calls
                content = msg.get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            tool_name = block.get("name", "unknown")
                            result["tools"][tool_name] += 1
                            result["tool_calls"] += 1

                            if tool_name == "Read":
                                fp = block.get("input", {}).get("file_path", "")
                                read_calls.append(fp.split("/")[-1] if fp else "unknown")
                            elif tool_name == "Bash":
                                cmd = block.get("input", {}).get("command", "")[:80]
                                bash_commands.append(cmd)

            # Track errors
            if entry.get("type") == "error":
                result["errors"].append(entry.get("message", "unknown error"))

    result["type"] = classify_agent(first_user or "")
    result["tokens"]["total"] = sum(result["tokens"].values())
    result["first_reads"] = read_calls[:10]
    result["bash_commands"] = bash_commands[:10]
    result["tools"] = dict(result["tools"])

    # Cache hit detection (router should read context files first)
    result["cache_hit"] = any(
        "context" in r.lower() or "state" in r.lower()
        for r in read_calls[:2]
    )

    return result


def analyze_directory(dir_path: Path) -> dict:
    """Analyze all agent logs in directory."""
    results = {
        "version": dir_path.name,
        "analyzed_at": datetime.now().isoformat(),
        "agents": [],
        "by_type": {},
        "by_model": defaultdict(lambda: {"count": 0, "tokens": 0}),
        "tools_summary": defaultdict(int),
        "totals": {
            "tokens": 0,
            "tokens_by_category": {"input": 0, "cache_read": 0, "cache_create": 0, "output": 0},
            "api_calls": 0,
            "tool_calls": 0,
            "agents": 0,
        },
        "issues": [],
        "findings": [],
    }

    type_data = defaultdict(lambda: {
        "count": 0,
        "tokens": 0,
        "cache_hits": 0,
        "tokens_by_category": {"input": 0, "cache_read": 0, "cache_create": 0, "output": 0},
        "models": defaultdict(int),
        "avg_api_calls": 0,
        "total_api_calls": 0,
    })

    for filepath in sorted(dir_path.glob("agent-*.jsonl")):
        agent = parse_agent(filepath)

        # Skip warmup agents and tiny logs
        if agent["tokens"]["total"] < 1000 or agent["type"] == "warmup":
            continue

        results["agents"].append(agent)
        atype = agent["type"]

        # Aggregate by type
        type_data[atype]["count"] += 1
        type_data[atype]["tokens"] += agent["tokens"]["total"]
        type_data[atype]["total_api_calls"] += agent["api_calls"]
        for cat in ["input", "cache_read", "cache_create", "output"]:
            type_data[atype]["tokens_by_category"][cat] += agent["tokens"][cat]
        if agent["cache_hit"]:
            type_data[atype]["cache_hits"] += 1
        type_data[atype]["models"][agent["model"]] += 1

        # Aggregate by model
        results["by_model"][agent["model"]]["count"] += 1
        results["by_model"][agent["model"]]["tokens"] += agent["tokens"]["total"]

        # Tools summary
        for tool, count in agent["tools"].items():
            results["tools_summary"][tool] += count

        # Totals
        results["totals"]["tokens"] += agent["tokens"]["total"]
        results["totals"]["api_calls"] += agent["api_calls"]
        results["totals"]["tool_calls"] += agent["tool_calls"]
        results["totals"]["agents"] += 1
        for cat in ["input", "cache_read", "cache_create", "output"]:
            results["totals"]["tokens_by_category"][cat] += agent["tokens"][cat]

        # Track errors
        if agent["errors"]:
            results["issues"].append({
                "agent": agent["file"],
                "type": atype,
                "errors": agent["errors"]
            })

    # Compute averages
    for atype, data in type_data.items():
        if data["count"] > 0:
            data["avg_api_calls"] = data["total_api_calls"] / data["count"]
            data["models"] = dict(data["models"])
            data["tokens_by_category"] = dict(data["tokens_by_category"])

    results["by_type"] = {k: dict(v) for k, v in type_data.items()}
    results["by_model"] = dict(results["by_model"])
    results["tools_summary"] = dict(results["tools_summary"])

    # Generate findings
    results["findings"] = generate_findings(results)

    return results


def generate_findings(results: dict) -> list:
    """Generate actionable findings from analysis."""
    findings = []

    # Check for learner presence (should be 0 in campaigns)
    learner_count = results["by_type"].get("learner", {}).get("count", 0)
    if learner_count > 0:
        learner_tokens = results["by_type"]["learner"]["tokens"]
        pct = learner_tokens / results["totals"]["tokens"] * 100
        findings.append({
            "severity": "HIGH",
            "category": "orchestration",
            "issue": "Learner agents spawned in campaign",
            "detail": f"{learner_count} learners consumed {learner_tokens:,} tokens ({pct:.1f}%)",
            "expected": "0 learners (synthesizer handles pattern extraction)",
            "action": "Check 'Two Workflows' ontology section in SKILL.md"
        })

    # Check router cache hits
    router_data = results["by_type"].get("router", {})
    if router_data.get("count", 0) > 0:
        cache_hits = router_data.get("cache_hits", 0)
        total = router_data["count"]
        if cache_hits < total:
            findings.append({
                "severity": "MEDIUM",
                "category": "caching",
                "issue": "Router cache misses",
                "detail": f"{cache_hits}/{total} routers read cache files first",
                "expected": "All routers should read session_context.md + workspace_state.md first",
                "action": "Check router.md 'First Step: Load Cached Context' instruction"
            })
        else:
            findings.append({
                "severity": "OK",
                "category": "caching",
                "issue": "Router caching working",
                "detail": f"{cache_hits}/{total} routers read cache files correctly",
            })

    # Check expected agent counts
    planner_count = results["by_type"].get("planner", {}).get("count", 0)
    router_count = results["by_type"].get("router", {}).get("count", 0)
    builder_count = results["by_type"].get("builder", {}).get("count", 0)
    synth_count = results["by_type"].get("synthesizer", {}).get("count", 0)

    if planner_count != 1:
        findings.append({
            "severity": "HIGH",
            "category": "orchestration",
            "issue": f"Expected 1 planner, found {planner_count}",
        })

    if synth_count != 1:
        findings.append({
            "severity": "HIGH",
            "category": "orchestration",
            "issue": f"Expected 1 synthesizer, found {synth_count}",
        })

    if router_count != builder_count:
        findings.append({
            "severity": "MEDIUM",
            "category": "orchestration",
            "issue": f"Router/builder mismatch: {router_count} routers, {builder_count} builders",
            "expected": "Equal number of routers and builders (1:1 mapping)",
        })

    # Check cache efficiency
    total_tokens = results["totals"]["tokens"]
    cache_read = results["totals"]["tokens_by_category"]["cache_read"]
    if total_tokens > 0:
        cache_pct = cache_read / total_tokens * 100
        if cache_pct > 30:
            findings.append({
                "severity": "OK",
                "category": "efficiency",
                "issue": "Good cache utilization",
                "detail": f"{cache_pct:.1f}% of tokens from cache reads",
            })
        else:
            findings.append({
                "severity": "LOW",
                "category": "efficiency",
                "issue": "Low cache utilization",
                "detail": f"Only {cache_pct:.1f}% of tokens from cache reads",
                "action": "Review caching strategy"
            })

    # Check for unknown agents
    unknown_count = results["by_type"].get("unknown", {}).get("count", 0)
    if unknown_count > 0:
        findings.append({
            "severity": "MEDIUM",
            "category": "classification",
            "issue": f"{unknown_count} agents could not be classified",
            "action": "Review agent classification logic or prompt patterns"
        })

    return findings


def print_report(results: dict, detailed: bool = False):
    """Print human-readable report."""
    print("=" * 75)
    print(f"FTL CAMPAIGN ANALYSIS: {results['version']}")
    print("=" * 75)

    # Agent summary
    print(f"\n### AGENT SUMMARY")
    print(f"{'Type':<12} | {'Count':>5} | {'Tokens':>12} | {'Cache':>7} | {'Avg APIs':>8}")
    print("-" * 60)

    for atype in ["planner", "router", "builder", "learner", "synthesizer", "unknown"]:
        data = results["by_type"].get(atype, {})
        if data.get("count", 0) > 0:
            cache = f"{data.get('cache_hits', 0)}/{data['count']}"
            avg_api = f"{data.get('avg_api_calls', 0):.1f}"
            marker = " !!!" if atype == "learner" else ""
            print(f"{atype:<12} | {data['count']:>5} | {data['tokens']:>12,} | {cache:>7} | {avg_api:>8}{marker}")

    print("-" * 60)
    print(f"{'TOTAL':<12} | {results['totals']['agents']:>5} | {results['totals']['tokens']:>12,}")

    # Token breakdown
    print(f"\n### TOKEN BREAKDOWN")
    cats = results["totals"]["tokens_by_category"]
    total = results["totals"]["tokens"]
    for cat, val in cats.items():
        pct = val / total * 100 if total > 0 else 0
        print(f"  {cat:<15}: {val:>12,} ({pct:>5.1f}%)")

    # Model usage
    print(f"\n### MODEL USAGE")
    for model, data in sorted(results["by_model"].items()):
        print(f"  {model}: {data['count']} agents, {data['tokens']:,} tokens")

    # Tool usage
    if detailed:
        print(f"\n### TOOL USAGE")
        for tool, count in sorted(results["tools_summary"].items(), key=lambda x: -x[1]):
            print(f"  {tool:<20}: {count:>5}")

    # Per-agent detail
    if detailed:
        print(f"\n### AGENT DETAILS")
        for agent in results["agents"]:
            print(f"\n  {agent['file']}")
            print(f"    Type: {agent['type']}, Model: {agent['model']}")
            print(f"    Tokens: {agent['tokens']['total']:,} (in:{agent['tokens']['input']:,} cache:{agent['tokens']['cache_read']:,} out:{agent['tokens']['output']:,})")
            print(f"    API calls: {agent['api_calls']}, Tool calls: {agent['tool_calls']}")
            print(f"    Cache hit: {'Yes' if agent['cache_hit'] else 'No'}")
            if agent["first_reads"]:
                print(f"    First reads: {', '.join(agent['first_reads'][:5])}")
            if agent.get("errors"):
                print(f"    ERRORS: {agent['errors']}")

    # Findings
    print(f"\n### FINDINGS")
    print("-" * 60)

    high = [f for f in results["findings"] if f.get("severity") == "HIGH"]
    medium = [f for f in results["findings"] if f.get("severity") == "MEDIUM"]
    low = [f for f in results["findings"] if f.get("severity") == "LOW"]
    ok = [f for f in results["findings"] if f.get("severity") == "OK"]

    for finding in high:
        print(f"\n[HIGH] {finding['issue']}")
        if finding.get("detail"):
            print(f"       {finding['detail']}")
        if finding.get("expected"):
            print(f"       Expected: {finding['expected']}")
        if finding.get("action"):
            print(f"       Action: {finding['action']}")

    for finding in medium:
        print(f"\n[MEDIUM] {finding['issue']}")
        if finding.get("detail"):
            print(f"         {finding['detail']}")
        if finding.get("action"):
            print(f"         Action: {finding['action']}")

    for finding in low:
        print(f"\n[LOW] {finding['issue']}")
        if finding.get("detail"):
            print(f"      {finding['detail']}")

    for finding in ok:
        print(f"\n[OK] {finding['issue']}")
        if finding.get("detail"):
            print(f"     {finding['detail']}")

    # Issues
    if results["issues"]:
        print(f"\n### ERRORS DETECTED")
        for issue in results["issues"]:
            print(f"  {issue['agent']} ({issue['type']}): {issue['errors']}")

    # Summary
    print(f"\n### SUMMARY")
    print("-" * 60)
    high_count = len([f for f in results["findings"] if f.get("severity") == "HIGH"])
    medium_count = len([f for f in results["findings"] if f.get("severity") == "MEDIUM"])

    if high_count > 0:
        print(f"STATUS: NEEDS ATTENTION - {high_count} high severity issue(s)")
    elif medium_count > 0:
        print(f"STATUS: ACCEPTABLE - {medium_count} medium severity issue(s)")
    else:
        print(f"STATUS: GOOD - No significant issues")

    learner_tokens = results["by_type"].get("learner", {}).get("tokens", 0)
    if learner_tokens > 0:
        print(f"\nLearner waste: {learner_tokens:,} tokens could be saved")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 analyze.py <results_dir> [--json] [--detailed]")
        sys.exit(1)

    dir_path = Path(sys.argv[1])
    if not dir_path.exists():
        print(f"Error: {dir_path} does not exist")
        sys.exit(1)

    results = analyze_directory(dir_path)

    if "--json" in sys.argv:
        print(json.dumps(results, indent=2, default=str))
    else:
        detailed = "--detailed" in sys.argv
        print_report(results, detailed=detailed)
