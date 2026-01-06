"""Task Manager - Basic working implementation.

This is the EXISTING code that FTL must preserve and extend.
All existing tests must continue to pass after modifications.
"""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Task:
    """A task with basic properties."""

    id: int
    title: str
    done: bool = False
    created_at: datetime = field(default_factory=datetime.now)


class TaskManager:
    """Manages a collection of tasks."""

    def __init__(self):
        self.tasks: dict[int, Task] = {}
        self.next_id: int = 1

    def add(self, title: str) -> Task:
        """Add a new task and return it."""
        task = Task(id=self.next_id, title=title)
        self.tasks[self.next_id] = task
        self.next_id += 1
        return task

    def complete(self, id: int) -> bool:
        """Mark a task as complete. Returns True if found."""
        if id in self.tasks:
            self.tasks[id].done = True
            return True
        return False

    def delete(self, id: int) -> bool:
        """Delete a task. Returns True if found."""
        if id in self.tasks:
            del self.tasks[id]
            return True
        return False

    def get(self, id: int) -> Task | None:
        """Get a task by ID."""
        return self.tasks.get(id)

    def list_all(self) -> list[Task]:
        """List all tasks."""
        return list(self.tasks.values())

    def list_pending(self) -> list[Task]:
        """List tasks that are not done."""
        return [t for t in self.tasks.values() if not t.done]

    def list_completed(self) -> list[Task]:
        """List tasks that are done."""
        return [t for t in self.tasks.values() if t.done]
