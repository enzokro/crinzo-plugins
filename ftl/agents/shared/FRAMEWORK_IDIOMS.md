---
version: 1.1
---

# Framework Idioms Reference

Framework detection and idioms are data-driven via `lib/framework_registry.py`.

**To add a new framework**: Add entry to `FRAMEWORK_PATTERNS` and `FRAMEWORK_IDIOMS` in registry. No agent prompt changes needed.

See [ONTOLOGY.md](ONTOLOGY.md#framework-confidence) for confidence thresholds and enforcement rules.

## Registry CLI

```bash
# Detect framework in codebase
python3 "$(cat .ftl/plugin_root)/lib/framework_registry.py" detect

# Get idioms for framework
python3 "$(cat .ftl/plugin_root)/lib/framework_registry.py" idioms fasthtml

# Get complexity weight for planner
python3 "$(cat .ftl/plugin_root)/lib/framework_registry.py" weight fastapi

# List registered frameworks
python3 "$(cat .ftl/plugin_root)/lib/framework_registry.py" list
```

## Detection Priority

1. README.md contains "## Framework Idioms" section → 0.95 confidence
2. Framework import in >50% of .py files → 0.85 confidence
3. Framework import in any .py file → 0.75 confidence
4. Framework in pyproject.toml → 0.65 confidence
5. No detection → 0.0 (no idiom enforcement)

## Idiom Compliance Checking

| Agent | Check Point | Action on Violation |
|-------|-------------|---------------------|
| Explorer | Pattern detection | Report in exploration.json |
| Planner | Task design | Include idioms in plan.json |
| Builder | PLAN + QUALITY states | BLOCK (if confidence >= 0.6) |
| Observer | Pattern extraction | Note systemic idiom issues |

---

## Per-Framework Idioms

Framework-specific idioms are defined in `lib/framework_registry.py`:

```bash
# View all registered frameworks
python3 "$(cat .ftl/plugin_root)/lib/framework_registry.py" list

# View idioms for a specific framework
python3 "$(cat .ftl/plugin_root)/lib/framework_registry.py" idioms fasthtml
```

**To add a new framework**: Add entries to `FRAMEWORK_PATTERNS` and `FRAMEWORK_IDIOMS` in the registry. No documentation updates needed.
