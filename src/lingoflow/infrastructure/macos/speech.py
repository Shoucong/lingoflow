"""Nonblocking, single-playback access to the macOS speech synthesizer."""

from __future__ import annotations

from PyQt6.QtCore import QObject, QProcess, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication

from lingoflow.core.speech import SpeechRequest, choose_voice, parse_voices


class MacOSSpeechService(QObject):
    voices_changed = pyqtSignal(object)
    state_changed = pyqtSignal()
    failed = pyqtSignal(str, str)  # owner, user-facing message

    def __init__(self, parent=None, program: str = "/usr/bin/say"):
        super().__init__(parent)
        self.program = program
        self.voices = []
        self.current: SpeechRequest | None = None
        self.pending: SpeechRequest | None = None
        self._closed = False
        self._voices_loaded = False
        self._listing = QProcess(self)
        self._listing.finished.connect(self._voices_finished)
        self._listing.errorOccurred.connect(self._voices_error)
        self._listing_timeout = QTimer(self)
        self._listing_timeout.setSingleShot(True)
        self._listing_timeout.timeout.connect(self._voices_timeout)
        self._player = QProcess(self)
        self._player.started.connect(self._player_started)
        self._player.finished.connect(self._player_finished)
        self._player.errorOccurred.connect(self._player_error)

    @classmethod
    def shared(cls) -> MacOSSpeechService:
        app = QApplication.instance()
        service = getattr(app, "_lingoflow_speech", None)
        if service is None:
            service = cls(app)
            app._lingoflow_speech = service
            app.aboutToQuit.connect(service.shutdown)
        return service

    def refresh_voices(self) -> None:
        if self._closed or self._listing.state() != QProcess.ProcessState.NotRunning:
            return
        self._listing.start(self.program, ["-v", "?"])
        self._listing_timeout.start(5000)

    def speak(self, request: SpeechRequest) -> None:
        if self._closed or not request.text.strip():
            return
        self.pending = request
        if self._player.state() != QProcess.ProcessState.NotRunning:
            self._player.kill()
        elif self._voices_loaded:
            self._start_pending()
        else:
            self.refresh_voices()
        self.state_changed.emit()

    def stop(self, owner: str | None = None) -> None:
        if owner is None or (self.pending and self.pending.owner == owner):
            self.pending = None
        if owner is None or (self.current and self.current.owner == owner):
            self.current = None
            if self._player.state() != QProcess.ProcessState.NotRunning:
                self._player.kill()
        self.state_changed.emit()

    def is_active(self, owner: str, kind: str) -> bool:
        return any(
            request and request.owner == owner and request.kind == kind
            for request in (self.current, self.pending)
        )

    def _voices_finished(self, exit_code: int, _exit_status) -> None:
        self._listing_timeout.stop()
        if self._closed:
            return
        if exit_code != 0:
            self._fail_pending("Could not list system voices. Check macOS speech settings.")
            return
        output = bytes(self._listing.readAllStandardOutput()).decode("utf-8", errors="replace")
        self.voices = parse_voices(output)
        self._voices_loaded = True
        self.voices_changed.emit(self.voices)
        self._start_pending()

    def _voices_error(self, _error) -> None:
        self._listing_timeout.stop()
        self._fail_pending("The macOS speech command could not be started.")

    def _voices_timeout(self) -> None:
        self._listing.kill()
        self._fail_pending("Listing system voices timed out. Try again.")

    def _fail_pending(self, message: str) -> None:
        owner = self.pending.owner if self.pending else ""
        self.pending = None
        self.failed.emit(owner, message)
        self.state_changed.emit()

    def _start_pending(self) -> None:
        if (
            self._closed
            or not self.pending
            or self._player.state() != QProcess.ProcessState.NotRunning
        ):
            return
        request = self.pending
        try:
            voice = choose_voice(self.voices, request.locale, request.voice)
        except ValueError as error:
            self._fail_pending(str(error))
            return
        self.pending = None
        self.current = request
        self._player.start(self.program, ["-v", voice.name, "-r", str(request.rate), "-f", "-"])
        self.state_changed.emit()

    def _player_started(self) -> None:
        if self.current:
            self._player.write(self.current.text.encode("utf-8"))
            self._player.closeWriteChannel()
        else:
            self._player.kill()

    def _player_finished(self, code: int, _status) -> None:
        request = self.current
        self.current = None
        if code != 0 and request and not self.pending:
            self.failed.emit(request.owner, "Speech could not be completed. Try another voice.")
        self.state_changed.emit()
        self._start_pending()

    def _player_error(self, error) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            request = self.current
            self.current = None
            if request:
                self.failed.emit(request.owner, "The macOS speech command could not be started.")
            self.state_changed.emit()

    def shutdown(self) -> None:
        self._closed = True
        self.pending = None
        self.current = None
        self._listing_timeout.stop()
        for process in (self._listing, self._player):
            if process.state() != QProcess.ProcessState.NotRunning:
                process.kill()
                process.waitForFinished(500)
