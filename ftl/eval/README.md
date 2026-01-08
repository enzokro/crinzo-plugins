# FTL Evaluation Harness

FTL evaluating itself using FTL's own patterns.

## Quick Start

```bash
./eval.sh status                    # See what exists
./eval.sh run anki v13              # Run evaluation
./eval.sh compare anki-v12 anki-v13 # Compare runs
./eval.sh reflect anki-v13          # Generate prompts
./eval.sh integrate L001            # Create decision record
```

## The Flow

```
run → capture → reflect → learn → integrate
                   ↑                    ↓
                   └──── FTL improves ──┘
```

1. **Run**: Execute campaign against template (`./eval.sh run anki v13`)
2. **Capture**: Extract metrics.json + transcript.md (auto after run)
3. **Reflect**: Generate prompts; update `reflections/*.md`
4. **Learn**: Extract insights → add to `chronicle.md`
5. **Integrate**: Create decision records from learnings

## Directory Structure

```
ftl/eval/
├── eval.sh                 # Unified entry point
├── integrate.sh            # Create decision records
├── chronicle.md            # Narrative log of runs and learnings
├── README.md               # This file
│
├── scripts/                # Helper scripts (called by eval.sh)
│   ├── run.sh             # Full eval loop
│   ├── run_suite.sh       # All templates for a version
│   ├── setup.sh           # Create test environment
│   ├── campaign.sh        # Run Claude campaign
│   ├── collect.sh         # Collect agent logs
│   └── propagate.sh       # Sync plugin to cache
│
├── instruments/            # Python analysis tools
│   ├── capture.py         # metrics.json + transcript.md
│   ├── prompt.py          # Reflection prompts (questions, not scores)
│   └── compare.py         # Delta analysis
│
├── templates/              # Test environments
│   ├── anki/
│   ├── pipeline/
│   ├── errors/
│   └── refactor/
│
├── reflections/            # Human-driven observation
│   ├── questions.md       # Active curiosities
│   ├── understandings.md  # Beliefs with uncertainty
│   ├── surprises.md       # Unexpected findings
│   └── journal.md         # Freeform notes
│
├── evidence/               # Captured artifacts
│   ├── runs/{run-id}/     # metrics.json, transcript.md
│   └── comparisons/       # Delta reports
│
├── results/                # Raw agent logs
└── decisions/              # Integrated learning records
```

## Commands

| Command | Description |
|---------|-------------|
| `run <template> <version>` | Full eval: propagate → setup → campaign → collect |
| `capture <run-id>` | Extract evidence from results |
| `compare <old> <new>` | Delta analysis between runs |
| `reflect <run-id>` | Generate reflection prompts |
| `learn` | Review reflections, guidance for chronicle |
| `integrate <learning-id>` | Create decision record from learning |
| `status` | Show available runs, evidence, learnings |

## Templates

| Template | Objective | Tests |
|----------|-----------|-------|
| `anki` | Flashcard app with spaced repetition | Protocol fidelity, no learners |
| `pipeline` | CSV data pipeline | Multi-task lineage |
| `errors` | Config parser with validation | Error recovery |
| `refactor` | Task manager enhancement | Existing tests pass |

## Chronicle Format

Each chronicle entry captures:

```markdown
## 2026-01-06: anki-v12 — Ontology Refactor

**Change**: What was modified
**Run**: agents | tokens | cache | protocol

**Compared to <prev>**: delta summary

**Learning L00X**: Insight
- Mechanism
- Implication
- Applied to

**Open**: Questions raised
```

## Reflection Files

- **questions.md**: Active curiosities, answered questions
- **understandings.md**: Beliefs with confidence (1-10), evidence, would-update-if
- **surprises.md**: Unexpected findings worth noting
- **journal.md**: Freeform observations

## Philosophy

Six dimensions of orchestration quality:

1. **Cognitive Efficiency** — Tokens → useful output
2. **Structural Fidelity** — Protocol adherence
3. **Decision Quality** — Right choices at branch points
4. **Pattern Emergence** — Knowledge extracted and reused
5. **Error Recovery** — Graceful failure handling
6. **Knowledge Accumulation** — System gets smarter

The harness measures (1-2) directly. It surfaces (3-6) through reflection prompts—tooling prompts, humans notice.

## Learnings

| ID | Insight | Source |
|----|---------|--------|
| L001 | Ontological framing > imperative prohibition | anki-v10 → v12 |

See `chronicle.md` for full context.
