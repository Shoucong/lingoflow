from __future__ import annotations

import threading

from lingoflow.infrastructure.tasks import BackgroundTask, TaskRunner, TaskState


def join_task(task: BackgroundTask) -> None:
    assert task._thread is not None
    task._thread.join(timeout=2.0)
    assert not task._thread.is_alive()


def test_task_runner_marks_successful_task_completed() -> None:
    runner = TaskRunner()
    called = threading.Event()

    task = runner.start("success", lambda current: called.set())
    join_task(task)

    assert called.is_set()
    assert task.state == TaskState.COMPLETED


def test_task_cancelled_before_start_never_runs_target() -> None:
    runner = TaskRunner()
    called = threading.Event()
    task = runner.create("cancelled")

    task.cancel()
    task.start(lambda current: called.set())
    join_task(task)

    assert not called.is_set()
    assert task.state == TaskState.CANCELLED


def test_task_runner_marks_failed_task_failed() -> None:
    runner = TaskRunner()

    def fail(_: BackgroundTask) -> None:
        raise RuntimeError("boom")

    task = runner.start("failed", fail)
    join_task(task)

    assert task.state == TaskState.FAILED


def test_task_runner_cancel_all_requests_cancellation() -> None:
    runner = TaskRunner()
    started = threading.Event()
    release = threading.Event()

    def wait_for_cancel(_: BackgroundTask) -> None:
        started.set()
        release.wait(timeout=2.0)

    task = runner.start("waiting", wait_for_cancel)
    assert started.wait(timeout=2.0)

    runner.cancel_all()
    release.set()
    join_task(task)

    assert task.is_cancelled()
    assert task.state == TaskState.CANCELLED
