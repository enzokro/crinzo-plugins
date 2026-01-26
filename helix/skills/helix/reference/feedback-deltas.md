# Feedback Delta Tables

## Base Deltas (Orchestrator Judgment)

| Situation | Delta | Rationale |
|-----------|-------|-----------|
| Clear success, memory was relevant | +0.7 | Strong signal |
| Success, memory was tangential | +0.3 | Weak signal |
| Success, no memories used | 0 | No feedback |
| Failure, memory may have misled | -0.5 | Moderate penalty |
| Failure, memory was irrelevant | -0.2 | Light penalty |

## Memory Relevance Classification

| Condition | Classification | Delta Multiplier |
|-----------|---------------|------------------|
| Memory trigger matches task objective (cosine > 0.7) | **Relevant** | 1.0x |
| Memory's failure type matches task's error | **Relevant** | 1.0x |
| Memory mentions same files as task | **Tangential** | 0.5x |
| Memory mentions same framework | **Tangential** | 0.5x |
| Memory was injected but unrelated to outcome | **Irrelevant** | 0.3x |

## Formula

```
final_delta = base_delta x multiplier
```

## CLI

```bash
python3 "$HELIX/lib/memory/core.py" feedback \
    --names '["memory-name-1", "memory-name-2"]' \
    --delta 0.5
```
