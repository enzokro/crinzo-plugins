# Task Manager Refactor — FTL Evaluation Anchor

Existing code evolution scenario for testing FTL's ability to preserve functionality while adding features.

## Objective

Extend and refactor the existing task manager to add priorities, due dates, and filtering.

## Starting State

**IMPORTANT:** This template starts with WORKING CODE and PASSING TESTS.

The existing `task_manager.py` and `test_task_manager.py` files contain a functional implementation. All 16 existing tests pass. FTL must preserve this functionality.

## Required Extensions

### 1. Priority Levels

Add priority support to tasks:

```python
from enum import Enum

class Priority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4
```

Modify `Task` to include:
- `priority: Priority = Priority.MEDIUM`

Modify `TaskManager.add()` to accept optional priority:
- `add(title: str, priority: Priority = Priority.MEDIUM) -> Task`

### 2. Due Dates

Add due date support:

Modify `Task` to include:
- `due_date: datetime | None = None`

Modify `TaskManager.add()` to accept optional due date:
- `add(title: str, priority: Priority = Priority.MEDIUM, due_date: datetime | None = None) -> Task`

Add method:
- `is_overdue(self) -> bool` on Task (True if due_date < now and not done)

### 3. Filtering

Add filtering methods to `TaskManager`:

```python
def list_by_priority(self, priority: Priority) -> list[Task]:
    """List tasks with specific priority."""

def list_overdue(self) -> list[Task]:
    """List tasks that are overdue."""

def list_due_before(self, date: datetime) -> list[Task]:
    """List tasks due before the given date."""
```

### 4. Sorting

Add sorting methods to `TaskManager`:

```python
def list_sorted_by_due_date(self, pending_only: bool = False) -> list[Task]:
    """List tasks sorted by due date (None values last)."""

def list_sorted_by_priority(self, pending_only: bool = False) -> list[Task]:
    """List tasks sorted by priority (URGENT first)."""

def list_sorted_by_created(self, pending_only: bool = False) -> list[Task]:
    """List tasks sorted by creation time (oldest first)."""
```

## Constraints

### CRITICAL: Preserve Existing API

1. **All 16 existing tests must continue to pass**
2. Existing method signatures must remain compatible:
   - `add(title: str)` must still work (priority defaults to MEDIUM)
   - All other methods unchanged
3. Task dataclass must remain backward compatible

### New Tests Required

Add tests in `test_task_manager.py` for:
- [ ] Task creation with priority
- [ ] Task creation with due date
- [ ] Priority filtering
- [ ] Overdue detection
- [ ] Due date filtering
- [ ] All three sort methods
- [ ] Default priority is MEDIUM
- [ ] is_overdue returns False when done

## Verification Commands

```bash
# ALL tests pass (existing + new)
uv run pytest test_task_manager.py -v

# Existing tests specifically
uv run pytest test_task_manager.py -v -k "TestTask"
```

## Success Criteria

1. All 16 original tests pass unchanged
2. New features work correctly
3. API is backward compatible
4. Code is cleanly integrated (not bolted on)

## Non-Goals (Out of Scope)

- Persistence (database, file)
- Categories/tags
- Subtasks
- Recurring tasks
- User assignment

---

This specification is FIXED. All FTL eval runs use identical starting conditions for meaningful comparison.
