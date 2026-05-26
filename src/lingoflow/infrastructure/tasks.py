"""Small cancellable background task helpers."""

from __future__ import annotations

import itertools
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)


class TaskState(Enum):
    """Lifecycle state for a background task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class BackgroundTask:
    """A cancellable unit of background work."""

    task_id: int
    name: str
    cancel_event: threading.Event = field(default_factory=threading.Event)
    state: TaskState = TaskState.PENDING
    _thread: threading.Thread | None = None
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def start(self, target: Callable[["BackgroundTask"], None]) -> None:
        """Start the task on a daemon thread."""

        def run() -> None:
            with self._lock:
                if self.cancel_event.is_set():
                    self.state = TaskState.CANCELLED
                    return
                self.state = TaskState.RUNNING

            try:
                target(self)
                with self._lock:
                    if self.cancel_event.is_set():
                        self.state = TaskState.CANCELLED
                    elif self.state == TaskState.RUNNING:
                        self.state = TaskState.COMPLETED
            except Exception:
                with self._lock:
                    self.state = TaskState.FAILED
                logger.exception(f"Background task failed: {self.name}#{self.task_id}")

        self._thread = threading.Thread(
            target=run,
            name=f"LingoFlow-{self.name}-{self.task_id}",
            daemon=True,
        )
        self._thread.start()

    def cancel(self) -> None:
        """Request task cancellation."""
        self.cancel_event.set()
        with self._lock:
            if self.state in {TaskState.PENDING, TaskState.RUNNING}:
                self.state = TaskState.CANCELLED

    def is_cancelled(self) -> bool:
        """Return whether cancellation was requested."""
        return self.cancel_event.is_set()

    def is_active(self) -> bool:
        """Return whether the task may still produce output."""
        return self.state in {TaskState.PENDING, TaskState.RUNNING}


class TaskRunner:
    """Create and track cancellable background tasks."""

    def __init__(self) -> None:
        self._ids = itertools.count(1)
        self._tasks: dict[int, BackgroundTask] = {}
        self._lock = threading.RLock()

    def start(
        self,
        name: str,
        target: Callable[[BackgroundTask], None],
    ) -> BackgroundTask:
        """Start a tracked background task."""
        task = self.create(name)
        task.start(target)
        return task

    def create(self, name: str) -> BackgroundTask:
        """Create a tracked task without starting it yet."""
        task = BackgroundTask(task_id=next(self._ids), name=name)
        with self._lock:
            self._tasks[task.task_id] = task
        return task

    def cancel(self, task: BackgroundTask | None) -> None:
        """Cancel a task if present."""
        if task is not None:
            task.cancel()

    def cancel_all(self) -> None:
        """Cancel all known tasks."""
        with self._lock:
            tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
