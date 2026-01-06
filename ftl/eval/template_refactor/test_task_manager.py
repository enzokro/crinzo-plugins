"""Tests for TaskManager - EXISTING tests that must continue to pass.

FTL must preserve all existing functionality while adding new features.
These tests verify the original API contract.
"""
import pytest
from task_manager import Task, TaskManager


class TestTaskCreation:
    """Tests for task creation."""

    def test_add_task_returns_task(self):
        """Adding a task returns the created task."""
        tm = TaskManager()
        task = tm.add("Buy groceries")
        assert isinstance(task, Task)
        assert task.title == "Buy groceries"

    def test_add_task_assigns_id(self):
        """Each task gets a unique ID."""
        tm = TaskManager()
        t1 = tm.add("Task 1")
        t2 = tm.add("Task 2")
        assert t1.id == 1
        assert t2.id == 2

    def test_new_task_is_not_done(self):
        """New tasks start as not done."""
        tm = TaskManager()
        task = tm.add("New task")
        assert task.done is False

    def test_new_task_has_created_at(self):
        """New tasks have a creation timestamp."""
        tm = TaskManager()
        task = tm.add("Timestamped task")
        assert task.created_at is not None


class TestTaskCompletion:
    """Tests for completing tasks."""

    def test_complete_existing_task(self):
        """Completing an existing task returns True."""
        tm = TaskManager()
        task = tm.add("Complete me")
        result = tm.complete(task.id)
        assert result is True
        assert task.done is True

    def test_complete_nonexistent_task(self):
        """Completing a nonexistent task returns False."""
        tm = TaskManager()
        result = tm.complete(999)
        assert result is False


class TestTaskDeletion:
    """Tests for deleting tasks."""

    def test_delete_existing_task(self):
        """Deleting an existing task returns True."""
        tm = TaskManager()
        task = tm.add("Delete me")
        result = tm.delete(task.id)
        assert result is True
        assert tm.get(task.id) is None

    def test_delete_nonexistent_task(self):
        """Deleting a nonexistent task returns False."""
        tm = TaskManager()
        result = tm.delete(999)
        assert result is False


class TestTaskRetrieval:
    """Tests for retrieving tasks."""

    def test_get_existing_task(self):
        """Getting an existing task returns it."""
        tm = TaskManager()
        task = tm.add("Find me")
        found = tm.get(task.id)
        assert found is task

    def test_get_nonexistent_task(self):
        """Getting a nonexistent task returns None."""
        tm = TaskManager()
        found = tm.get(999)
        assert found is None


class TestTaskListing:
    """Tests for listing tasks."""

    def test_list_all_empty(self):
        """Listing all tasks when empty returns empty list."""
        tm = TaskManager()
        assert tm.list_all() == []

    def test_list_all_with_tasks(self):
        """Listing all tasks returns all tasks."""
        tm = TaskManager()
        t1 = tm.add("Task 1")
        t2 = tm.add("Task 2")
        all_tasks = tm.list_all()
        assert len(all_tasks) == 2
        assert t1 in all_tasks
        assert t2 in all_tasks

    def test_list_pending(self):
        """Listing pending tasks excludes completed ones."""
        tm = TaskManager()
        t1 = tm.add("Pending")
        t2 = tm.add("Done")
        tm.complete(t2.id)
        pending = tm.list_pending()
        assert len(pending) == 1
        assert t1 in pending
        assert t2 not in pending

    def test_list_completed(self):
        """Listing completed tasks excludes pending ones."""
        tm = TaskManager()
        t1 = tm.add("Pending")
        t2 = tm.add("Done")
        tm.complete(t2.id)
        completed = tm.list_completed()
        assert len(completed) == 1
        assert t2 in completed
        assert t1 not in completed
