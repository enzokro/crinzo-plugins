#!/bin/bash
# Inject Bounded Execution output style as session context

cat <<'EOF'
{
  "hookSpecificOutput": {
    "additionalContext": "# Active Output Style: Bounded Execution\n\nFor all tether plugin work, apply these principles:\n\nStructure communicates. State signals. Scope constrains.\n\n| Principle | Expression |\n|-----------|------------|\n| **Structure over narrative** | Key-value blocks; prose adds nothing status doesn't |\n| **State as signal** | `active`, `complete`, `blocked` — the return IS the message |\n| **Scope is boundary** | Delta defines what exists; outside Delta doesn't |\n| **Lineage is explicit** | `from-NNN` in filename, not implicit reference |\n| **Traces capture, don't justify** | Working memory, not persuasion |\n\n## Return Format\n\n```\nRoute: full | direct | clarify\nStatus: complete | blocked\nWorkspace: [path]\nDelivered: [what]\nVerified: pass | skip | fail\n```\n\n- No preamble before structure\n- Omit explanation unless `blocked`\n- Failed verification: error, not apology\n- Empty fields explicit: `Verify: none discovered`\n- One line per fact"
  }
}
EOF
