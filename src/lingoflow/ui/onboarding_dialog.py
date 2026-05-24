"""
First-run onboarding for macOS permissions.
"""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from lingoflow.infrastructure.macos_permissions import (
    MacOSPermissionService,
    PermissionCheck,
    PermissionState,
)
from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)


class OnboardingDialog(QDialog):
    """Guide the user through required macOS permissions."""

    def __init__(self, permission_service: MacOSPermissionService, parent=None):
        super().__init__(parent)
        self.permission_service = permission_service
        self.completed_successfully = False
        self._rows: dict[str, dict[str, QLabel | QPushButton]] = {}

        self._setup_window()
        self._setup_ui()
        self._refresh_checks()

    def _setup_window(self) -> None:
        """Configure dialog window."""
        self.setWindowTitle("Set up LingoFlow")
        self.setMinimumWidth(620)
        self.setModal(True)

    def _setup_ui(self) -> None:
        """Build dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        title = QLabel("Set up LingoFlow")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(title)

        intro = QLabel(
            "LingoFlow needs a few macOS permissions before hotkeys, selected-text "
            "translation, and OCR can work reliably."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.permission_grid = QGridLayout()
        self.permission_grid.setHorizontalSpacing(12)
        self.permission_grid.setVerticalSpacing(10)
        layout.addLayout(self.permission_grid)

        note = QLabel(
            "After changing permissions in System Settings, restart LingoFlow if macOS asks you to."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: gray;")
        layout.addWidget(note)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(separator)

        button_layout = QHBoxLayout()

        self.recheck_btn = QPushButton("Recheck")
        self.recheck_btn.clicked.connect(self._refresh_checks)
        button_layout.addWidget(self.recheck_btn)

        button_layout.addStretch()

        self.skip_btn = QPushButton("Continue Later")
        self.skip_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.skip_btn)

        self.continue_btn = QPushButton("Continue")
        self.continue_btn.setDefault(True)
        self.continue_btn.clicked.connect(self._continue)
        button_layout.addWidget(self.continue_btn)

        layout.addLayout(button_layout)

    def _refresh_checks(self) -> None:
        """Refresh permission statuses."""
        checks = self.permission_service.get_checks()

        for row, check in enumerate(checks):
            if check.key not in self._rows:
                self._create_row(row, check)
            self._update_row(check)

        ready = all(check.is_ready for check in checks)
        self.continue_btn.setText("Continue" if ready else "Continue Anyway")

    def _create_row(self, row: int, check: PermissionCheck) -> None:
        """Create one permission row."""
        status_label = QLabel()
        status_label.setMinimumWidth(115)

        name_label = QLabel(check.name)
        name_label.setStyleSheet("font-weight: 600;")

        purpose_label = QLabel()
        purpose_label.setWordWrap(True)

        request_btn = QPushButton("Request")
        request_btn.clicked.connect(lambda _, key=check.key: self._request_permission(key))

        settings_btn = QPushButton("Open Settings")
        settings_btn.clicked.connect(lambda _, url=check.settings_url: self.permission_service.open_settings(url))

        self.permission_grid.addWidget(status_label, row, 0, alignment=Qt.AlignmentFlag.AlignTop)
        self.permission_grid.addWidget(name_label, row, 1, alignment=Qt.AlignmentFlag.AlignTop)
        self.permission_grid.addWidget(purpose_label, row, 2)
        self.permission_grid.addWidget(request_btn, row, 3, alignment=Qt.AlignmentFlag.AlignTop)
        self.permission_grid.addWidget(settings_btn, row, 4, alignment=Qt.AlignmentFlag.AlignTop)

        self._rows[check.key] = {
            "status": status_label,
            "purpose": purpose_label,
            "request": request_btn,
        }

    def _update_row(self, check: PermissionCheck) -> None:
        """Update one permission row."""
        row = self._rows[check.key]
        status_label = row["status"]
        purpose_label = row["purpose"]
        request_btn = row["request"]

        if check.state == PermissionState.GRANTED:
            status_label.setText("Granted")
            status_label.setStyleSheet("color: green; font-weight: 600;")
        elif check.state == PermissionState.MISSING:
            status_label.setText("Needs setup")
            status_label.setStyleSheet("color: #b26a00; font-weight: 600;")
        elif check.state == PermissionState.MANUAL:
            status_label.setText("Manual check")
            status_label.setStyleSheet("color: #555; font-weight: 600;")
        else:
            status_label.setText("Unknown")
            status_label.setStyleSheet("color: #b26a00; font-weight: 600;")

        purpose_label.setText(f"{check.purpose}\n{check.detail}")
        request_btn.setVisible(check.key in {"accessibility", "input_monitoring", "screen_recording"})
        request_btn.setEnabled(check.state != PermissionState.GRANTED)

    def _request_permission(self, key: str) -> None:
        """Ask macOS for a permission prompt where supported."""
        self.hide()
        QApplication.processEvents()

        if key == "accessibility":
            self.permission_service.request_accessibility()
        elif key == "input_monitoring":
            self.permission_service.request_input_monitoring()
        elif key == "screen_recording":
            self.permission_service.request_screen_recording()

        QTimer.singleShot(1500, self._show_after_permission_request)

    def _show_after_permission_request(self) -> None:
        """Bring setup back after macOS has had a chance to show its prompt."""
        self._refresh_checks()
        self.show()
        self.raise_()
        self.activateWindow()

    def _continue(self) -> None:
        """Continue when permissions are ready, or confirm continuing anyway."""
        checks = self.permission_service.get_checks()
        missing = [check for check in checks if not check.is_ready]

        if missing:
            names = ", ".join(check.name for check in missing)
            reply = QMessageBox.question(
                self,
                "Continue without all permissions?",
                f"These permissions are still missing: {names}.\n\n"
                "Some LingoFlow features may not work until they are enabled.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            self.completed_successfully = False
        else:
            self.completed_successfully = True

        self.accept()
