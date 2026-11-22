"""Static security scan of package text files (BA-GAME-2.2 §4, §2.14.2).

The scan is intentionally conservative and does not guarantee detection of
malicious behaviour; the manual review of the first version of every game is
mandatory (§2.14.2) and cannot be disabled.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from apps.pipeline.validation.codes import (
    V_ABSOLUTE_PATH,
    V_EXTERNAL_URL,
    V_FORBIDDEN_API,
    Diagnostic,
)
from apps.pipeline.validation.report import ValidationReport
from apps.pipeline.validation.text import iter_text_files, read_text, relative

SDK_PATH = "js/ba-sdk.js"

_FORBIDDEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("eval", re.compile(r"(?<![\w.])eval\s*\(")),
    ("new Function", re.compile(r"\bnew\s+Function\s*\(")),
    ("string timer", re.compile(r"\b(?:setTimeout|setInterval)\s*\(\s*[\"']")),
    ("service worker", re.compile(r"\bserviceWorker\b")),
    ("SharedArrayBuffer", re.compile(r"\bSharedArrayBuffer\b")),
    ("document.cookie", re.compile(r"\bdocument\s*\.\s*cookie\b")),
    ("localStorage", re.compile(r"\blocalStorage\b")),
    ("sessionStorage", re.compile(r"\bsessionStorage\b")),
    ("IndexedDB", re.compile(r"\bindexedDB\b")),
    ("window.top", re.compile(r"\bwindow\s*\.\s*top\b")),
    ("top.location", re.compile(r"(?<![\w.])top\s*\.\s*location\b")),
    ("parent.location", re.compile(r"\bparent\s*\.\s*location\b")),
    ("parent.document", re.compile(r"\bparent\s*\.\s*document\b")),
    ("postMessage", re.compile(r"\bpostMessage\s*\(")),
    ("alert", re.compile(r"(?<![\w.])alert\s*\(")),
    ("confirm", re.compile(r"(?<![\w.])confirm\s*\(")),
    ("prompt", re.compile(r"(?<![\w.])prompt\s*\(")),
    ("window.open", re.compile(r"\bwindow\s*\.\s*open\s*\(")),
    ("target=_blank", re.compile(r"\btarget\s*=\s*[\"']_blank[\"']", re.IGNORECASE)),
    ("navigator.clipboard", re.compile(r"\bnavigator\s*\.\s*clipboard\b")),
    ("geolocation", re.compile(r"\bgeolocation\b")),
    ("camera/microphone", re.compile(r"\bgetUserMedia\b")),
    ("webrtc", re.compile(r"\bRTCPeerConnection\b")),
    ("payments", re.compile(r"\bPaymentRequest\b")),
    ("notifications", re.compile(r"\bNotification\s*\(")),
)

_EXTERNAL_URL_RE = re.compile(r"(?:https?:)?//[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_ABSOLUTE_ATTR_RE = re.compile(r"\b(?:src|href|action)\s*=\s*[\"']/(?!/)", re.IGNORECASE)
_ABSOLUTE_URL_RE = re.compile(r"\burl\s*\(\s*[\"']?/(?!/)", re.IGNORECASE)
_BASE_TAG_RE = re.compile(r"<\s*base\b", re.IGNORECASE)

_SCAN_SUFFIXES = frozenset({".html", ".css", ".js", ".mjs", ".json"})


@dataclass(slots=True)
class SecurityResult:
    diagnostics: list[Diagnostic] = field(default_factory=list)


def scan_root(root: Path) -> SecurityResult:
    report = ValidationReport()
    for path in iter_text_files(root):
        if path.suffix.lower() not in _SCAN_SUFFIXES:
            continue
        name = relative(root, path)
        if name == SDK_PATH:
            # §2.14.3: the packaged SDK is always replaced and is not trusted.
            continue
        try:
            text = read_text(path)
        except OSError, UnicodeDecodeError:
            continue
        for label, pattern in _FORBIDDEN_PATTERNS:
            match = pattern.search(text)
            if match:
                report.add(
                    V_FORBIDDEN_API,
                    f"Запрещённый API: {label}",
                    file=name,
                    hint="Удалите запрещённый API; связь с порталом — только через SDK.",
                    meta={"pattern": label, "position": match.start()},
                )
        match = _EXTERNAL_URL_RE.search(text)
        if match:
            report.add(
                V_EXTERNAL_URL,
                "Внешний URL запрещён",
                file=name,
                hint="Все ресурсы должны быть внутри пакета.",
                meta={"value": match.group(0)},
            )
        if _BASE_TAG_RE.search(text):
            report.add(V_ABSOLUTE_PATH, "Тег <base> запрещён", file=name)
        if _ABSOLUTE_ATTR_RE.search(text) or _ABSOLUTE_URL_RE.search(text):
            report.add(
                V_ABSOLUTE_PATH,
                "Абсолютные пути запрещены",
                file=name,
                hint="Используйте относительные пути.",
            )
    return SecurityResult(diagnostics=report.diagnostics)
