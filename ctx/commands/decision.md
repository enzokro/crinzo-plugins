---
description: Show full decision record with context.
allowed-tools: Bash, Read, Glob
---

# Decision Record

Show complete decision record including Thinking Traces and Delivered.

## Protocol

1. Parse $ARGUMENTS for sequence number.

2. Get decision:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/ctx.py" decision $SEQ
```

## Output Format

```
[015] auth-refactor (3d ago, complete)
  Path: User credentials → validation → session token
  Delta: src/auth/*.ts
  Tags: #pattern/session-token-flow (+2)
  Builds on: 008

Thinking Traces:
Chose token refresh over re-auth because...
Examined session.ts lines 45-78...
Found existing pattern in auth-utils.ts...

Delivered:
Modified src/auth/session.ts to implement token refresh.
Added refresh endpoint in src/api/auth.ts.
```

## Usage

```
/ctx:decision 015    # Show decision 015
/ctx:decision 3      # Show decision 003 (zero-padded)
```

## Constraints

- Read-only
- Returns full Thinking Traces and Delivered sections
