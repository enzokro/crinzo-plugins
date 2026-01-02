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
python3 "${CLAUDE_PLUGIN_ROOT}/lib/ctx.py" signal "$SIGN" "$PATTERN"
```

3. Confirm result.

## Usage

```
/ctx:signal + #pattern/session-token-flow    # Pattern worked well
/ctx:signal - #constraint/max-batch-size     # Constraint caused issues
```

## Output Format

```
Signal added: #pattern/session-token-flow -> net +2
```

## Storage

Signals stored in `.ctx/signals.json`:
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

- Only writes to .ctx/signals.json
- Does not modify workspace files
