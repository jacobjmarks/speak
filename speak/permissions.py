"""OS permissions Speak needs before it can work. Only macOS gates these; elsewhere nothing is required."""
import logging
import subprocess
from typing import NamedTuple

from .platform_utils import IS_MAC


log = logging.getLogger(__name__)

class Permission(NamedTuple):
    id: str
    title: str
    why: str
    pane: str  # System Settings > Privacy & Security pane


REQUIRED = (
    Permission("microphone", "Microphone", "To hear you while you dictate.", "Privacy_Microphone"),
    Permission("input_monitoring", "Input Monitoring", "To notice your dictation shortcut in any app.",
               "Privacy_ListenEvent"),
    Permission("accessibility", "Accessibility", "To type the result into the app you're using.",
               "Privacy_Accessibility"),
) if IS_MAC else ()


def granted(permission_id: str) -> bool:
    try:
        if permission_id == "microphone":
            import AVFoundation

            # 3 = authorized
            return AVFoundation.AVCaptureDevice.authorizationStatusForMediaType_(AVFoundation.AVMediaTypeAudio) == 3
        if permission_id == "input_monitoring":
            from Quartz import CGPreflightListenEventAccess

            return bool(CGPreflightListenEventAccess())
        if permission_id == "accessibility":
            from ApplicationServices import AXIsProcessTrusted

            return bool(AXIsProcessTrusted())
    except Exception:
        return True  # can't tell; don't block the app on it
    return True


def missing() -> list:
    return [p for p in REQUIRED if not granted(p.id)]


def request(permission_id: str) -> None:
    """Show macOS's own prompt (once per permission, and never for one already answered)."""
    try:
        if permission_id == "microphone":
            import AVFoundation

            status = AVFoundation.AVCaptureDevice.authorizationStatusForMediaType_(AVFoundation.AVMediaTypeAudio)
            if status == 0:  # not determined yet
                AVFoundation.AVCaptureDevice.requestAccessForMediaType_completionHandler_(
                    AVFoundation.AVMediaTypeAudio, lambda ok: None)
            else:
                open_settings(permission_id)  # already answered; only Settings can change it
        elif permission_id == "input_monitoring":
            from Quartz import CGRequestListenEventAccess

            if not CGRequestListenEventAccess():
                # macOS prompts once per app only; after that this fails silently. Only Settings can change it.
                open_settings(permission_id)
        elif permission_id == "accessibility":
            from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt

            AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
    except Exception:
        log.warning("Could not request %s access", permission_id, exc_info=True)
        open_settings(permission_id)


def open_settings(permission_id: str) -> None:
    pane = next((p.pane for p in REQUIRED if p.id == permission_id), "")
    subprocess.Popen(["open", f"x-apple.systempreferences:com.apple.preference.security?{pane}"])
