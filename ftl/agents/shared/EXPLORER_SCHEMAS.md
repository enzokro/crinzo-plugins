---
version: 1.0
---

# Explorer Output Schemas

JSON Schema definitions for each explorer mode output. All modes write directly to the `explorer_result` table via:

```bash
python3 lib/exploration.py write-result --session {session_id} --mode {mode} <<< '{json}'
```

Results are aggregated to the `exploration` table using `aggregate-session --session {session_id}`.

See [ONTOLOGY.md](ONTOLOGY.md#vocabulary-disambiguation) for terminology.

---

## Common Fields

All explorer outputs share these required fields:

```json
{
  "mode": "structure | pattern | memory | delta",
  "status": "ok | partial | error"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `mode` | string | YES | One of: structure, pattern, memory, delta |
| `status` | string | YES | ok = complete, partial = some data missing, error = critical failure |

---

## Structure Mode Schema

**Purpose**: Map codebase topology (WHERE does code live?)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["mode", "status", "directories"],
  "properties": {
    "mode": {"const": "structure"},
    "status": {"enum": ["ok", "partial", "error"]},
    "directories": {
      "type": "object",
      "description": "Key directories and whether they exist",
      "additionalProperties": {"type": "boolean"}
    },
    "entry_points": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Main entry files (main.py, __main__.py, etc.)"
    },
    "config_files": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Configuration files found (pyproject.toml, etc.)"
    },
    "test_pattern": {
      "type": ["string", "null"],
      "description": "Test file naming pattern (e.g., tests/test_*.py)"
    },
    "file_count": {
      "type": "integer",
      "minimum": 0,
      "description": "Total Python files in codebase"
    },
    "language": {
      "type": "string",
      "description": "Primary language detected"
    }
  }
}
```

**Example**:
```json
{
  "mode": "structure",
  "status": "ok",
  "directories": {"lib": true, "tests": true, "scripts": false, "src": false},
  "entry_points": ["main.py", "lib/__main__.py"],
  "config_files": ["pyproject.toml"],
  "test_pattern": "tests/test_*.py",
  "file_count": 25,
  "language": "python"
}
```

---

## Pattern Mode Schema

**Purpose**: Detect framework and extract idioms (HOW is code written?)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["mode", "status", "framework"],
  "properties": {
    "mode": {"const": "pattern"},
    "status": {"enum": ["ok", "partial", "error"]},
    "framework": {
      "type": "string",
      "description": "Detected framework (none, FastAPI, FastHTML, Flask, etc.)"
    },
    "confidence": {
      "type": "number",
      "minimum": 0.0,
      "maximum": 1.0,
      "default": 0.5,
      "description": "Framework detection confidence (optional, default 0.5; see ONTOLOGY.md#framework-confidence)"
    },
    "idioms": {
      "type": "object",
      "properties": {
        "required": {
          "type": "array",
          "items": {"type": "string"},
          "description": "Patterns Builder MUST use"
        },
        "forbidden": {
          "type": "array",
          "items": {"type": "string"},
          "description": "Patterns Builder MUST NOT use"
        }
      }
    },
    "style": {
      "type": "object",
      "properties": {
        "type_hints": {"type": "boolean"},
        "docstrings": {"enum": ["none", "sparse", "thorough"]}
      }
    },
    "readme_sections": {
      "type": "integer",
      "description": "Number of sections in README.md"
    }
  }
}
```

**Example**:
```json
{
  "mode": "pattern",
  "status": "ok",
  "framework": "FastHTML",
  "confidence": 0.85,
  "idioms": {
    "required": ["@rt decorator for routes", "Return component trees"],
    "forbidden": ["Raw HTML strings", "Direct Response() with HTML"]
  },
  "style": {"type_hints": true, "docstrings": "sparse"},
  "readme_sections": 3
}
```

---

## Memory Mode Schema

**Purpose**: Retrieve relevant historical context (WHAT happened before?)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["mode", "status"],
  "properties": {
    "mode": {"const": "memory"},
    "status": {"enum": ["ok", "partial", "error"]},
    "failures": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["name", "trigger"],
        "properties": {
          "name": {"type": "string", "description": "Failure identifier (kebab-case)"},
          "cost": {"type": "integer", "description": "Token cost when failure occurred"},
          "trigger": {"type": "string", "description": "Error message or condition"},
          "fix": {"type": "string", "description": "Solution that worked"},
          "_relevance": {"type": "number", "description": "Semantic relevance to objective (0.0-1.0)"},
          "_score": {"type": "number", "description": "Composite importance score"},
          "related": {"type": "array", "items": {"type": "string"}}
        }
      }
    },
    "patterns": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["name", "insight"],
        "properties": {
          "name": {"type": "string"},
          "saved": {"type": "integer", "description": "Tokens saved when pattern applied"},
          "insight": {"type": "string", "description": "Non-obvious learning"},
          "_relevance": {"type": "number"},
          "_score": {"type": "number"}
        }
      }
    },
    "similar_campaigns": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "objective": {"type": "string"},
          "similarity": {"type": "number"},
          "outcome": {"enum": ["complete", "partial", "blocked"]},
          "patterns_from": {"type": "array", "items": {"type": "string"}}
        }
      }
    },
    "total_in_memory": {
      "type": "object",
      "properties": {
        "failures": {"type": "integer"},
        "patterns": {"type": "integer"}
      }
    }
  }
}
```

**Example**:
```json
{
  "mode": "memory",
  "status": "ok",
  "failures": [
    {
      "name": "partial-code-context-budget-exhaustion",
      "cost": 3000,
      "trigger": "Budget exhausted before implementation",
      "fix": "Ensure code_context includes target function lines",
      "_relevance": 0.72,
      "_score": 8.34,
      "related": ["missing-fixture-error"]
    }
  ],
  "patterns": [
    {
      "name": "verify-function-location-before-build",
      "saved": 1500,
      "insight": "Planner must locate target function",
      "_relevance": 0.65,
      "_score": 6.89
    }
  ],
  "similar_campaigns": [
    {
      "objective": "Add export functionality...",
      "similarity": 0.78,
      "outcome": "complete",
      "patterns_from": ["streaming-file-response"]
    }
  ],
  "total_in_memory": {"failures": 3, "patterns": 4}
}
```

---

## Delta Mode Schema

**Purpose**: Identify files/functions that will change (WHAT will change?)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["mode", "status", "candidates"],
  "properties": {
    "mode": {"const": "delta"},
    "status": {"enum": ["ok", "partial", "error"]},
    "search_terms": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Keywords extracted from objective"
    },
    "candidates": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["path", "relevance"],
        "properties": {
          "path": {"type": "string", "description": "File path relative to root"},
          "lines": {"type": "integer", "description": "Total lines in file"},
          "functions": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "name": {"type": "string"},
                "line": {"type": "integer"}
              }
            }
          },
          "relevance": {
            "enum": ["high", "medium", "low"],
            "description": "Match quality: high=function name, medium=file name, low=body"
          },
          "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "default": 0.5,
            "description": "Candidate confidence (optional, default 0.5)"
          }
        }
      }
    }
  }
}
```

**Example**:
```json
{
  "mode": "delta",
  "status": "ok",
  "search_terms": ["campaign", "complete", "history"],
  "candidates": [
    {
      "path": "lib/campaign.py",
      "lines": 256,
      "functions": [
        {"name": "complete", "line": 106},
        {"name": "history", "line": 143}
      ],
      "relevance": "high",
      "confidence": 0.85
    }
  ]
}
```

---

## Validation

When writing to database via `write-result`, minimal validation is performed:

1. `mode` field exists and matches expected value
2. `status` field exists and is valid enum
3. Mode-specific required fields present

Aggregation via `aggregate-session` combines all mode results for a session.

Schemas above are for documentation; strict validation is not enforced at runtime.

---

## Cross-References

- [explorer.md](../explorer.md) - Explorer agent specification
- [ONTOLOGY.md](ONTOLOGY.md) - Terminology definitions
- [OUTPUT_TEMPLATES.md](OUTPUT_TEMPLATES.md) - General output format rules
