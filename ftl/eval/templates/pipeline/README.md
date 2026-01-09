# Data Pipeline — FTL Evaluation Anchor

CSV data pipeline for testing FTL's data flow tracking, lineage chains, and Path specification accuracy.

---

## REQUIRED TASK BREAKDOWN (Spec-First TDD)

**The planner MUST create exactly these 5 tasks. Do NOT merge, split, reorder, or add tasks.**

| Task | Type | Slug | Description | Delta | Verify |
|------|------|------|-------------|-------|--------|
| 000 | SPEC | test-spec | Complete test_pipeline.py: fill in assertions for all tests | test_pipeline.py | `uv run pytest test_pipeline.py --collect-only` |
| 001 | BUILD | parse-validate | Implement parse_csv + validate_record | pipeline.py, test_pipeline.py | `uv run pytest test_pipeline.py -k "parse or valid" -v` |
| 002 | BUILD | transform | Implement transform_employee | pipeline.py, test_pipeline.py | `uv run pytest test_pipeline.py -k transform -v` |
| 003 | BUILD | aggregate | Implement aggregate_by_department + generate_report | pipeline.py, test_pipeline.py | `uv run pytest test_pipeline.py -k "aggregate or report" -v` |
| 004 | VERIFY | integration | All tests pass | any | `uv run pytest test_pipeline.py -v` |

**Dependencies:** 000 → 001 → 002 → 003 → 004 (sequential)

**Mutable Tests:** BUILD tasks include test_pipeline.py in Delta. Builders may adjust test assertions if behavioral CONTRACT is preserved.

---

## Objective

Build a CSV data pipeline with validation, transformation, and aggregation.

## Required Behavior

### 1. Data Flow

```
Input: data/sample.csv
→ Parse: CSV to typed Employee records
→ Validate: reject invalid records, collect errors
→ Transform: normalize names, compute derived fields
→ Aggregate: group by department, compute statistics
→ Output: JSON report matching data/expected.json
```

### 2. Data Model

```python
class Employee:
    id: int
    name: str           # normalized: title case
    email: str          # validated: contains @
    age: int            # validated: positive
    department: str
    salary: int
    hire_date: date
```

### 3. Pipeline Functions

| Function | Input | Output |
|----------|-------|--------|
| `parse_csv(path)` | CSV file path | list[dict] |
| `validate_record(record)` | dict | tuple[Employee, list[Error]] |
| `transform_employee(emp)` | Employee | Employee (normalized) |
| `aggregate_by_department(employees)` | list[Employee] | dict[str, DeptStats] |
| `generate_report(valid, invalid, aggregates)` | ... | dict (JSON-serializable) |

### 4. Validation Rules

- `email`: must contain `@`, cannot be empty
- `age`: must be positive integer
- All fields: required (no empty strings)

### 5. Transformation Rules

- `name`: convert to title case
- `salary`: round to nearest 100

### 6. Aggregation

Per department:
- `count`: number of employees
- `avg_salary`: mean salary (2 decimal places)
- `avg_age`: mean age (2 decimal places)
- `employees`: list of names (sorted alphabetically)

### 7. Test Coverage

`test_pipeline.py` must verify:
- [ ] CSV parsing produces correct record count
- [ ] Invalid email is rejected with error
- [ ] Negative age is rejected with error
- [ ] Empty email is rejected with error
- [ ] Name normalization works (title case)
- [ ] Department aggregation produces correct counts
- [ ] Average calculations are accurate
- [ ] Final report matches expected.json structure

## Verification Commands

```bash
# Tests pass
uv run pytest test_pipeline.py -v

# Pipeline runs end-to-end
uv run python -c "from pipeline import run_pipeline; print(run_pipeline('data/sample.csv'))"
```

## Success Criteria

1. All validation errors detected
2. Aggregations match expected.json
3. All tests pass
4. Pipeline is composable (each stage independent)

## Non-Goals (Out of Scope)

- Streaming/chunked processing
- Multiple input formats
- Database output
- Parallel processing

---

This specification is FIXED. All FTL eval runs use identical starting conditions for meaningful comparison.
