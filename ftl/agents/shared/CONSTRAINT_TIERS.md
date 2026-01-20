---
version: 1.0
---

# Constraint Tiers

| Tier | Meaning | Agent Action |
|------|---------|--------------|
| **Essential** | Violation blocks task | BLOCK immediately |
| **Quality** | Best practice | Note in output |
| **Style** | Preference | Apply if budget allows |

## Per-Agent Essential Constraints

### Explorer
- Execute ONLY the specified mode
- Output MUST be valid JSON (raw, no markdown wrappers)
- Include `status` field in all output

### Planner
- Every task verifiable using only its Delta files
- Task ordering respects dependencies (no cycles)
- Delta must be specific file paths, not globs

### Builder
- Tool budget from workspace XML is absolute limit
- Framework idioms: required MUST appear, forbidden MUST NOT
- Block if same error appears twice (already retried)
- Block if error not in prior_knowledge (discovery needed)
- Modify ONLY files listed in workspace `delta` array; BLOCK if scope insufficient

### Observer
- Run automated analysis pipeline first (foundation before judgment)
- Every CONFIRMED block MUST produce a failure entry
- Document rationale when overriding automation decisions

## Blocking is Success

BLOCK status is not failure—it's successful discovery of unknowns. See [ONTOLOGY.md#block-status](ONTOLOGY.md#block-status).
