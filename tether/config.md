---
name: tether-config
description: Configuration settings for tether plugin behavior
---

# Tether Configuration

Settings that control tether behavior. Edit values below to customize.

## Settings

```yaml
# Path where workspace files are stored (relative to project root)
workspace_path: workspace/

# Number of digits for sequence numbers (e.g., 3 = 001, 4 = 0001)
sequence_padding: 3

# Default routing when assess is uncertain (full | direct)
default_route: full

# Model for assess phase (lightweight routing)
assess_model: haiku

# Model for anchor and build phases
build_model: inherit
```

## Usage

These settings establish defaults for tether's behavior. Individual agents may override specific settings via their own frontmatter.

### workspace_path

Where task files are created and queried. Default `workspace/` keeps cognitive artifacts in project root.

### sequence_padding

Controls task numbering format. Default 3 supports 999 tasks before overflow.

### default_route

When assess cannot determine routing with certainty, fall back to this route. `full` is safer (creates workspace file), `direct` is faster (skips anchor phase).

### Model Settings

- `assess_model`: Used for quick routing decisions. Haiku is fast and cost-effective.
- `build_model`: Used for anchor and build phases. `inherit` uses the conversation's model.
