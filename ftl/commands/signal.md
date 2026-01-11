---
description: Mark failure/discovery outcome for tracking.
allowed-tools: Bash, Read, Write
user-invocable: false
---

# Signal Outcome

Mark a failure or discovery as working (+) or problematic (-). Signals track effectiveness.

## Protocol

1. Parse $ARGUMENTS:
   - First arg: `+` or `-`
   - Second arg: entity ID (e.g., `f001` or `d003`)

2. Add signal:
```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$FTL_LIB/memory.py" signal "$SIGN" "$ID"
```

3. Confirm result.

## Usage

```
/ftl:signal + f001    # Failure fix worked well
/ftl:signal - d003    # Discovery didn't help
```

## Output Format

```
Signal: f001 -> 2
```

## Storage

Signals stored on entities in `.ftl/memory.json`:
```json
{
  "failures": [
    {
      "id": "f001",
      "name": "failure-name",
      "signal": 2
    }
  ]
}
```

## Constraints

- Only writes to .ftl/memory.json
- Does not modify workspace files
