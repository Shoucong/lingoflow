"""Single-instance guard for the macOS app bundle."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QIODevice, QLockFile, QObject, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from lingoflow.utils.logger import get_logger


class SingleInstanceGuard(QObject):
    """Prevent duplicate app instances and optionally notify the existing process."""

    activate_requested = pyqtSignal()

    def __init__(
        self,
        lock_path: str,
        server_name: str | None = None,
        timeout_ms: int = 250,
    ) -> None:
        super().__init__()
        self._lock_path = Path(lock_path)
        self._server_name = server_name
        self._timeout_ms = timeout_ms
        self._lock_file: QLockFile | None = None
        self._server: QLocalServer | None = None
        self._logger = get_logger(__name__)

    def acquire(self) -> bool:
        """Return True when this process owns the single-instance lock."""
        try:
            self._ensure_parent_dir(self._lock_path)
        except OSError as e:
            self._logger.warning(f"Single-instance lock unavailable: {e}")
            return True

        lock_file = QLockFile(str(self._lock_path))
        lock_file.setStaleLockTime(30_000)
        if lock_file.tryLock(0):
            self._lock_file = lock_file
            return True

        self._logger.info(f"Single-instance lock is already held: {self._lock_path}")
        return False

    def release(self) -> None:
        """Release the single-instance lock before shutdown."""
        if self._lock_file is not None:
            self._lock_file.unlock()
            self._lock_file = None

    def notify_existing_instance(self) -> bool:
        """Return True when another instance accepted an activation request."""
        if not self._server_name:
            return False

        socket = QLocalSocket()
        socket.connectToServer(
            self._server_name,
            QIODevice.OpenModeFlag.ReadWrite,
        )

        if not socket.waitForConnected(self._timeout_ms):
            socket.abort()
            return False

        socket.write(b"activate\n")
        socket.flush()
        socket.waitForBytesWritten(self._timeout_ms)
        socket.disconnectFromServer()
        socket.close()
        return True

    def listen(self) -> bool:
        """Start listening for future launches of the same app."""
        if not self._server_name:
            return False

        try:
            self._ensure_parent_dir(Path(self._server_name))
        except OSError as e:
            self._logger.warning(f"Single-instance guard unavailable: {e}")
            return False

        self._server = self._create_server()
        if self._server.listen(self._server_name):
            return True

        stale_error = self._server.errorString()
        QLocalServer.removeServer(self._server_name)
        self._server = self._create_server()

        if self._server.listen(self._server_name):
            self._logger.info(f"Recovered stale single-instance server: {self._server_name}")
            return True

        self._logger.warning(
            "Single-instance guard unavailable: "
            f"{stale_error}; retry failed with {self._server.errorString()}"
        )
        return False

    def _create_server(self) -> QLocalServer:
        server = QLocalServer(self)
        server.newConnection.connect(self._handle_new_connection)
        return server

    def _ensure_parent_dir(self, path: Path) -> None:
        if path.parent != Path("."):
            path.parent.mkdir(parents=True, exist_ok=True)

    def _handle_new_connection(self) -> None:
        if self._server is None:
            return

        while self._server.hasPendingConnections():
            connection = self._server.nextPendingConnection()
            if connection is None:
                continue

            connection.disconnected.connect(connection.deleteLater)
            connection.write(b"ok\n")
            connection.flush()
            connection.disconnectFromServer()

        self._logger.info("Received activation request from another launch")
        self.activate_requested.emit()
