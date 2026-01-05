---
description: Mark pattern outcome for evolution tracking.
allowed-tools: Bash, Read, Write
---

# Signal Outcome

Mark a pattern as successful (+) or problematic (-). Signals influence future ranking.

## Protocol

1. Parse $ARGUMENTS:
   - First arg: `+` or `-`
   - Second arg: pattern name (e.g., `#pattern/session-token-flow`)

2. Add signal:
```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$FTL_LIB/context_graph.py" signal "$SIGN" "$PATTERN"
```

3. Confirm result.

## Usage

```
/ftl:signal + #pattern/session-token-flow    # Pattern worked well
/ftl:signal - #constraint/max-batch-size     # Constraint caused issues
```

## Output Format

```
Signal added: #pattern/session-token-flow -> net +2
```

## Storage

Signals stored in `.ftl/signals.json`:
```json
{
  "#pattern/session-token-flow": {
    "signals": ["+", "+"],
    "net": 2,
    "last": 1704153600
  }
}
```

## Effect on Ranking

```
signal_factor = 1 + (net_signals * 0.2)
```

- net +5 = 2.0x weight
- net -5 = 0x weight (effectively hidden)

## Constraints

- Only writes to .ftl/signals.json
- Does not modify workspace files
