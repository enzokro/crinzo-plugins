"""Shared hook entry point for stdin-JSON hooks."""
import json
import sys


def run_hook(process_fn):
    """Read stdin JSON, call process_fn, print result JSON. Never crashes."""
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            print("{}")
            return
        result = process_fn(json.loads(raw))
        print(json.dumps(result))
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON: {e}"}), file=sys.stderr)
        print("{}")
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        print("{}")
