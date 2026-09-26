"""
macOS permission checks and System Settings helpers.

The app needs multiple privacy permissions on macOS. Some can be checked with
public APIs, while Input Monitoring does not expose a reliable app-level
preflight API here, so it remains a guided manual check.
"""

import platform
import subprocess
from dataclasses import dataclass
from enum import Enum

from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)


class PermissionState(Enum):
    """Permission check state."""

    GRANTED = "granted"
    MISSING = "missing"
    MANUAL = "manual"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PermissionCheck:
    """Status for one macOS privacy permission."""

    key: str
    name: str
    purpose: str
    state: PermissionState
    detail: str
    settings_url: str

    @property
    def is_ready(self) -> bool:
        """Return whether this permission is usable."""
        return self.state in {PermissionState.GRANTED, PermissionState.MANUAL}


class MacOSPermissionService:
    """Best-effort macOS permission checking and prompting."""

    ACCESSIBILITY_URL = (
        "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
    )
    INPUT_MONITORING_URL = (
        "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
    )
    SCREEN_RECORDING_URL = (
        "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
    )

    @staticmethod
    def is_supported() -> bool:
        """Return whether macOS permissions apply on this platform."""
        return platform.system() == "Darwin"

    def get_checks(self) -> list[PermissionCheck]:
        """Return current permission statuses."""
        return [
            self.check_accessibility(),
            self.check_input_monitoring(),
            self.check_screen_recording(),
        ]

    def required_permissions_ready(self) -> bool:
        """Return whether all checkable permissions are ready."""
        return all(check.is_ready for check in self.get_checks())

    def check_accessibility(self) -> PermissionCheck:
        """Check Accessibility permission, used for copying selected text."""
        try:
            import Quartz
            from ApplicationServices import AXIsProcessTrustedWithOptions

            ax_granted = bool(AXIsProcessTrustedWithOptions({"AXTrustedCheckOptionPrompt": False}))
            post_granted = (
                bool(Quartz.CGPreflightPostEventAccess())
                if hasattr(Quartz, "CGPreflightPostEventAccess")
                else ax_granted
            )
            granted = ax_granted and post_granted
            if granted:
                return PermissionCheck(
                    key="accessibility",
                    name="辅助功能",
                    purpose="读取其他应用中选中的文字。",
                    state=PermissionState.GRANTED,
                    detail="已允许",
                    settings_url=self.ACCESSIBILITY_URL,
                )

            detail = "划词翻译需要此权限。"
            if ax_granted and not post_granted:
                detail = "尚不能发送键盘事件，请在系统设置中关闭再重新打开 LingoFlow。"
            return PermissionCheck(
                key="accessibility",
                name="辅助功能",
                purpose="读取其他应用中选中的文字。",
                state=PermissionState.MISSING,
                detail=detail,
                settings_url=self.ACCESSIBILITY_URL,
            )
        except Exception as e:
            logger.warning(f"Could not check Accessibility permission: {e}")
            return PermissionCheck(
                key="accessibility",
                name="辅助功能",
                purpose="读取其他应用中选中的文字。",
                state=PermissionState.UNKNOWN,
                detail="无法自动检查。",
                settings_url=self.ACCESSIBILITY_URL,
            )

    def request_accessibility(self) -> None:
        """Ask macOS to show the Accessibility trust prompt when possible."""
        try:
            import Quartz
            from ApplicationServices import AXIsProcessTrustedWithOptions

            AXIsProcessTrustedWithOptions({"AXTrustedCheckOptionPrompt": True})
            if hasattr(Quartz, "CGRequestPostEventAccess"):
                Quartz.CGRequestPostEventAccess()
        except Exception as e:
            logger.warning(f"Could not request Accessibility permission: {e}")
            self.open_settings(self.ACCESSIBILITY_URL)

    def check_input_monitoring(self) -> PermissionCheck:
        """Check Input Monitoring permission, used for native hotkeys."""
        try:
            import Quartz

            if hasattr(Quartz, "CGPreflightListenEventAccess"):
                granted = bool(Quartz.CGPreflightListenEventAccess())
                if granted:
                    return PermissionCheck(
                        key="input_monitoring",
                        name="输入监控",
                        purpose="在其他应用中阅读时响应全局快捷键。",
                        state=PermissionState.GRANTED,
                        detail="已允许",
                        settings_url=self.INPUT_MONITORING_URL,
                    )

                return PermissionCheck(
                    key="input_monitoring",
                    name="输入监控",
                    purpose="在其他应用中阅读时响应全局快捷键。",
                    state=PermissionState.MISSING,
                    detail="翻译与截图快捷键需要此权限。",
                    settings_url=self.INPUT_MONITORING_URL,
                )
        except Exception as e:
            logger.warning(f"Could not check Input Monitoring permission: {e}")

        return PermissionCheck(
            key="input_monitoring",
            name="输入监控",
            purpose="在其他应用中阅读时响应全局快捷键。",
            state=PermissionState.UNKNOWN,
            detail="无法自动检查，请确认已在系统设置中启用 LingoFlow。",
            settings_url=self.INPUT_MONITORING_URL,
        )

    def request_input_monitoring(self) -> None:
        """Ask macOS to show the Input Monitoring prompt when possible."""
        try:
            import Quartz

            if hasattr(Quartz, "CGRequestListenEventAccess"):
                Quartz.CGRequestListenEventAccess()
            else:
                self.open_settings(self.INPUT_MONITORING_URL)
        except Exception as e:
            logger.warning(f"Could not request Input Monitoring permission: {e}")
            self.open_settings(self.INPUT_MONITORING_URL)

    def check_screen_recording(self) -> PermissionCheck:
        """Check Screen Recording permission, used for OCR screenshots."""
        try:
            import Quartz

            granted = bool(Quartz.CGPreflightScreenCaptureAccess())
            if granted:
                return PermissionCheck(
                    key="screen_recording",
                    name="屏幕录制",
                    purpose="截取所选屏幕区域用于文字识别。",
                    state=PermissionState.GRANTED,
                    detail="已允许",
                    settings_url=self.SCREEN_RECORDING_URL,
                )

            return PermissionCheck(
                key="screen_recording",
                name="屏幕录制",
                purpose="截取所选屏幕区域用于文字识别。",
                state=PermissionState.MISSING,
                detail="截图识别翻译需要此权限。",
                settings_url=self.SCREEN_RECORDING_URL,
            )
        except Exception as e:
            logger.warning(f"Could not check Screen Recording permission: {e}")
            return PermissionCheck(
                key="screen_recording",
                name="屏幕录制",
                purpose="截取所选屏幕区域用于文字识别。",
                state=PermissionState.UNKNOWN,
                detail="无法自动检查。",
                settings_url=self.SCREEN_RECORDING_URL,
            )

    def request_screen_recording(self) -> None:
        """Ask macOS to show the Screen Recording prompt when possible."""
        try:
            import Quartz

            Quartz.CGRequestScreenCaptureAccess()
        except Exception as e:
            logger.warning(f"Could not request Screen Recording permission: {e}")
            self.open_settings(self.SCREEN_RECORDING_URL)

    def open_settings(self, url: str) -> None:
        """Open a macOS Privacy & Security pane."""
        try:
            subprocess.run(["open", url], check=False, timeout=3.0)
        except Exception as e:
            logger.warning(f"Could not open System Settings URL '{url}': {e}")
