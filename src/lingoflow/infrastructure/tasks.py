"""Small cancellable background task helpers."""

from __future__ import annotations

import itertools
import threading
import time
from collections import deque
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
    _on_done: Callable[["BackgroundTask"], None] | None = None

    def start(self, target: Callable[["BackgroundTask"], None]) -> None:
        """Start the task on a daemon thread."""

        def run() -> None:
            try:
                with self._lock:
                    if self.cancel_event.is_set():
                        self.state = TaskState.CANCELLED
                        return
                    self.state = TaskState.RUNNING
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
            finally:
                self._finish()

        self._thread = threading.Thread(
            target=run,
            name=f"LingoFlow-{self.name}-{self.task_id}",
            daemon=True,
        )
        self._thread.start()

    def _finish(self) -> None:
        with self._lock:
            callback, self._on_done = self._on_done, None
        if callback:
            callback(self)

    def cancel(self) -> None:
        """Request task cancellation."""
        self.cancel_event.set()
        with self._lock:
            if self.state in {TaskState.PENDING, TaskState.RUNNING}:
                self.state = TaskState.CANCELLED
        if self._thread is None:
            self._finish()

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
        self.recent = deque(maxlen=100)

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
        task._on_done = self._finished
        with self._lock:
            self._tasks[task.task_id] = task
        return task

    def _finished(self, task: BackgroundTask) -> None:
        with self._lock:
            self._tasks.pop(task.task_id, None)
            self.recent.append((task.task_id, task.name, task.state.value))

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._tasks)

    def shutdown(self, timeout: float = 1.0) -> None:
        with self._lock:
            tasks = list(self._tasks.values())
        self.cancel_all()
        deadline = time.monotonic() + timeout
        for task in tasks:
            if task._thread and task._thread is not threading.current_thread():
                task._thread.join(max(0.0, deadline - time.monotonic()))

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
