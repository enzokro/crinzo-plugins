# Config Parser — FTL Evaluation Anchor

Config parser with strict validation for testing FTL's error recovery (Reflector) capabilities.

## Objective

Build a config parser with strict validation and helpful error messages.

## Required Behavior

### 1. Data Model

```python
@dataclass
class ServerConfig:
    host: str
    port: int           # 1-65535
    timeout: int        # > 0

@dataclass
class DatabaseConfig:
    url: str
    pool_size: int      # > 0
    max_overflow: int   # >= 0

@dataclass
class SecurityConfig:
    ssl: bool
    cert_path: str | None  # required if ssl=True
    key_path: str | None   # required if ssl=True

@dataclass
class LoggingConfig:
    level: str          # DEBUG, INFO, WARNING, ERROR
    format: str         # text, json

@dataclass
class Config:
    server: ServerConfig
    database: DatabaseConfig
    security: SecurityConfig
    logging: LoggingConfig
```

### 2. Validation Rules

**Type Validation:**
- `port`, `timeout`, `pool_size`, `max_overflow` must be integers (not strings)
- Error: `"Line {n}: '{field}' must be an integer, got {type}"`

**Range Validation:**
- `port`: 1-65535
- `timeout`: > 0
- `pool_size`: > 0
- Error: `"Line {n}: '{field}' must be {constraint}, got {value}"`

**Cross-Field Validation:**
- If `ssl = true`, then `cert_path` and `key_path` are required
- Error: `"'{field}' is required when ssl is enabled"`

### 3. Error Message Format

**CRITICAL: Error messages must match this EXACT format:**

```
ConfigError: {count} validation error(s)

  {category}:
    - Line {n}: '{field}' {description}

Example:
ConfigError: 2 validation error(s)

  Type errors:
    - Line 4: 'port' must be an integer, got str

  Range errors:
    - Line 5: 'timeout' must be positive, got -5
```

### 4. API

```python
def parse_config(path: str) -> Config:
    """Parse and validate TOML config file.

    Raises:
        ConfigError: with structured error messages
    """
    pass

class ConfigError(Exception):
    """Validation error with structured messages."""

    def __init__(self, errors: list[ValidationError]):
        self.errors = errors

    @property
    def count(self) -> int:
        return len(self.errors)
```

### 5. Test Coverage

`test_parser.py` must verify:
- [ ] Valid config parses successfully
- [ ] Type error detected: string instead of integer
- [ ] Range error detected: port > 65535
- [ ] Range error detected: negative timeout
- [ ] Cross-field error: ssl=true without cert_path
- [ ] Error message format matches specification exactly
- [ ] Line numbers are accurate
- [ ] Multiple errors collected (not fail-fast)

## Verification Commands

```bash
# Tests pass
uv run pytest test_parser.py -v

# Valid config parses
uv run python -c "from parser import parse_config; c = parse_config('fixtures/valid.toml'); print(c)"

# Invalid config shows errors
uv run python -c "from parser import parse_config; parse_config('fixtures/invalid_type.toml')"
# Should raise ConfigError with exact message format
```

## Success Criteria

1. All fixture files handled correctly
2. Error messages match EXACT format (tests will assert string equality)
3. Line numbers are accurate
4. All validation rules enforced

## Intentional Trap

The error message format specification is precise. Initial implementations often:
- Use different wording
- Omit line numbers
- Use different error categorization

This triggers the Reflector agent when tests fail exact-match assertions.

## Non-Goals (Out of Scope)

- YAML support (TOML only)
- Environment variable substitution
- Config inheritance/merging
- Schema definition format

---

This specification is FIXED. All FTL eval runs use identical starting conditions for meaningful comparison.
