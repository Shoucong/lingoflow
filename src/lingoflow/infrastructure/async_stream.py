"""Drive cancellable async HTTP streams from existing background workers."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass, field
from typing import TypeVar

T = TypeVar("T")


class RequestCancelledError(Exception):
    """An explicit cancellation, rather than a network failure."""


@dataclass(eq=False)
class _Request:
    loop: asyncio.AbstractEventLoop
    cancelled: threading.Event = field(default_factory=threading.Event)
    task: asyncio.Task | None = None

    def cancel(self) -> None:
        self.cancelled.set()
        try:
            self.loop.call_soon_threadsafe(self._cancel_task)
        except RuntimeError:
            # A concurrent normal completion may already have closed the loop.
            pass

    def _cancel_task(self) -> None:
        if self.task and not self.task.done():
            self.task.cancel()


class AsyncStreamRunner:
    """Each request owns its loop, cancellation flag, task and transport context."""

    def __init__(self):
        self._active: set[_Request] = set()
        self._lock = threading.Lock()

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._active)

    def iterate(self, factory: Callable[[], AsyncIterator[T]]) -> Iterator[T]:
        loop = asyncio.new_event_loop()
        request = _Request(loop)
        stream = factory()
        with self._lock:
            self._active.add(request)
        try:
            while True:
                if request.cancelled.is_set():
                    raise RequestCancelledError()
                request.task = loop.create_task(anext(stream))
                try:
                    result = loop.run_until_complete(request.task)
                except StopAsyncIteration:
                    return
                except asyncio.CancelledError as error:
                    raise RequestCancelledError() from error
                yield result
        finally:
            request.task = None
            with self._lock:
                self._active.discard(request)
            try:
                loop.run_until_complete(stream.aclose())
                loop.run_until_complete(loop.shutdown_asyncgens())
            finally:
                # Closing nested HTTP iterators can schedule one last async-generator
                # cleanup task. Drain it before discarding this request's event loop.
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.close()

    def cancel_all(self) -> None:
        with self._lock:
            requests = list(self._active)
        for request in requests:
            request.cancel()
