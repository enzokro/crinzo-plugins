---
name: tether-config
description: Tether configuration.
---

# Config

```yaml
workspace_path: workspace/
sequence_padding: 3
default_route: full
assess_model: haiku
build_model: inherit
```

| Setting | Default | Purpose |
|---------|---------|---------|
| workspace_path | workspace/ | Task file location |
| sequence_padding | 3 | Digits in NNN (3 = 001) |
| default_route | full | Fallback when uncertain |
| assess_model | haiku | Fast routing |
| build_model | inherit | Implementation |
