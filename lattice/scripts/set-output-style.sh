#!/bin/bash
# Inject Ranked Memory output style as session context

cat <<'EOF'
{
  "hookSpecificOutput": {
    "additionalContext": "# Active Output Style: Ranked Memory\n\nFor all lattice plugin work, apply these principles:\n\nOrder communicates relevance. Numbers attribute. Signals quantify.\n\n| Principle | Expression |\n|-----------|------------|\n| **Position is ranking** | First result is most relevant; order matters |\n| **Attribution is mandatory** | Every fact traces to `[NNN]` |\n| **Signals not opinions** | `(net +3)` not \"this worked well\" |\n| **Quote, don't paraphrase** | Excerpt Thinking Traces with quotation marks |\n| **Absence is information** | \"No decisions match\" is valid, useful output |\n\n## Return Format\n\n```\n[015] auth-refactor (3d ago, complete)\n  Path: [transformation]\n  Delta: [scope]\n  Tags: #pattern/name (+N)\n\n  Thinking Traces (excerpt):\n  \"[quoted excerpt]\"\n```\n\n- Decision number is identifier\n- Time relative unless precision needed\n- Tags include signal in parentheses\n- No results: state directly, no apology\n- Top 5-10 only; relevance cutoff, not low ranking"
  }
}
EOF
