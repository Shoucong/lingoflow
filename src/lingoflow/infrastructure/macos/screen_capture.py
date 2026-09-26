"""Cancellable owner of the macOS screenshot subprocess."""

import subprocess
import threading
import time

from lingoflow.core.errors import ScreenCaptureError


class ScreenCaptureRunner:
    def __init__(self):
        self._gate = threading.Lock()
        self._operation_lock = threading.Lock()
        self.process = None
        self._cancel_event = None

    def cancel(self):
        with self._operation_lock:
            process, cancelled = self.process, self._cancel_event
        if cancelled:
            cancelled.set()
        if process and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass

    def run(self, arguments, timeout: float, cancel_check=None):
        while not self._gate.acquire(timeout=0.05):
            if cancel_check and cancel_check():
                return subprocess.CompletedProcess(arguments, -1, "", "")
        process = None
        cancelled = threading.Event()
        try:
            if cancel_check and cancel_check():
                return subprocess.CompletedProcess(arguments, -1, "", "")
            process = subprocess.Popen(
                arguments,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            with self._operation_lock:
                self.process, self._cancel_event = process, cancelled
            deadline = time.monotonic() + timeout
            while True:
                if cancelled.is_set() or (cancel_check and cancel_check()):
                    return subprocess.CompletedProcess(arguments, -1, "", "")
                if time.monotonic() >= deadline:
                    raise ScreenCaptureError("Screen capture timed out.")
                try:
                    stdout, stderr = process.communicate(timeout=0.1)
                    if cancelled.is_set() or (cancel_check and cancel_check()):
                        return subprocess.CompletedProcess(arguments, -1, "", "")
                    return subprocess.CompletedProcess(
                        arguments, process.returncode, stdout, stderr
                    )
                except subprocess.TimeoutExpired:
                    continue
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.communicate()
            with self._operation_lock:
                self.process = self._cancel_event = None
            self._gate.release()
