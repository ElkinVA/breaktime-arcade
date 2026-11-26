"""Best-effort Windows toast notifications from WSL.

The toast is an owner-facing signal, not a control dependency.  A missing
PowerShell interop, a disabled toast subsystem or a non-zero exit is reported
as ``skipped``; the gate/status/report path never depends on it.
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from devcontrol.telegram import sanitize_text

POWERSHELL_APP_ID = (
    "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe"
)
DEFAULT_TIMEOUT = 10
_SAFE_ENV_KEYS = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LANG",
        "LC_ALL",
        "TERM",
        "WSL_DISTRO_NAME",
        "WSL_INTEROP",
        "WSLENV",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "COMSPEC",
    }
)


@dataclass(frozen=True)
class ToastResult:
    status: str
    reason: str | None = None


def _powershell() -> str | None:
    return shutil.which("powershell.exe") or shutil.which("powershell")


def _is_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text(encoding="utf-8").lower()
    except OSError:
        return False


def available() -> bool:
    return _is_wsl() and _powershell() is not None


def _script(title: str, message: str) -> str:
    safe_title = escape(sanitize_text(title)[:120]).replace("'", "''")
    safe_message = escape(sanitize_text(message)[:1200]).replace("'", "''")
    toast_xml = (
        '<toast><visual><binding template="ToastText02">'
        f'<text id="1">{safe_title}</text><text id="2">{safe_message}</text>'
        "</binding></visual></toast>"
    )
    lines = [
        "[Windows.UI.Notifications.ToastNotificationManager, "
        "Windows.UI.Notifications, ContentType = WindowsRuntime] > $null",
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, "
        "ContentType = WindowsRuntime] > $null",
        "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument",
        f"$xml.LoadXml('{toast_xml}')",
        "$toast = New-Object Windows.UI.Notifications.ToastNotification $xml",
        "[Windows.UI.Notifications.ToastNotificationManager]::"
        f"CreateToastNotifier('{POWERSHELL_APP_ID}').Show($toast)",
    ]
    return "\n".join(lines) + "\n"


def send_toast(title: str, message: str, *, timeout: int = DEFAULT_TIMEOUT) -> ToastResult:
    """Show a toast if WSL/Windows interop is available; never raise."""
    powershell = _powershell()
    if not _is_wsl() or powershell is None:
        return ToastResult("skipped", "Windows PowerShell interop is unavailable")
    try:
        encoded = base64.b64encode(_script(title, message).encode("utf-16-le")).decode("ascii")
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-EncodedCommand",
                encoded,
            ],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=timeout,
            env={key: value for key, value in os.environ.items() if key in _SAFE_ENV_KEYS},
        )
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        return ToastResult("skipped", type(exc).__name__)
    if completed.returncode != 0:
        return ToastResult("skipped", f"powershell exit {completed.returncode}")
    return ToastResult("sent")
