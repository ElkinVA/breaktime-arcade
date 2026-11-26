from __future__ import annotations

import base64
import subprocess
from typing import Any

import pytest
from autonomy import windows_notify


class Completed:
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self.stdout = ""
        self.stderr = ""


def test_toast_is_encoded_and_reports_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(windows_notify, "_is_wsl", lambda: True)
    monkeypatch.setattr(windows_notify, "_powershell", lambda: "/powershell.exe")
    seen: list[list[str]] = []

    def run(args: list[str], **kwargs: Any) -> Completed:
        seen.append(args)
        assert "ANTHROPIC_AUTH_TOKEN" not in kwargs["env"]
        assert "ANTHROPIC_BASE_URL" not in kwargs["env"]
        return Completed(0)

    monkeypatch.setattr(windows_notify.subprocess, "run", run)
    result = windows_notify.send_toast("Gate", "Owner action required")

    assert result.status == "sent"
    encoded = seen[0][-1]
    script = base64.b64decode(encoded).decode("utf-16-le")
    assert "Gate" in script
    assert "Owner action required" in script


def test_toast_skips_on_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(windows_notify, "_is_wsl", lambda: True)
    monkeypatch.setattr(windows_notify, "_powershell", lambda: "/powershell.exe")
    monkeypatch.setattr(
        windows_notify.subprocess,
        "run",
        lambda *args, **kwargs: Completed(1),
    )
    assert windows_notify.send_toast("Gate", "message").status == "skipped"


def test_toast_skips_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(windows_notify, "_is_wsl", lambda: True)
    monkeypatch.setattr(windows_notify, "_powershell", lambda: "/powershell.exe")

    def timeout(*args: Any, **kwargs: Any) -> Completed:
        raise subprocess.TimeoutExpired(cmd="powershell", timeout=10)

    monkeypatch.setattr(windows_notify.subprocess, "run", timeout)
    assert windows_notify.send_toast("Gate", "message").status == "skipped"


def test_toast_skips_when_interop_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(windows_notify, "_is_wsl", lambda: False)
    assert windows_notify.send_toast("Gate", "message").status == "skipped"


def test_toast_skips_on_unencodable_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(windows_notify, "_is_wsl", lambda: True)
    monkeypatch.setattr(windows_notify, "_powershell", lambda: "/powershell.exe")
    result = windows_notify.send_toast("Gate \ud800", "message")
    assert result.status == "skipped"


def test_script_escapes_powershell_quotes() -> None:
    script = windows_notify._script("Owner's gate", "don't panic")
    assert "Owner''s gate" in script
    assert "don''t panic" in script


def test_script_escapes_xml_metacharacters() -> None:
    script = windows_notify._script("A < B & C", "x > y")
    assert "&lt;" in script
    assert "&amp;" in script
    assert "&gt;" in script
