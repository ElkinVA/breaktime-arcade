"""Small allow-list HTML sanitiser for staff-edited content pages.

Rich text is never trusted: only a handful of formatting tags survive, text is
escaped, unsafe link schemes are dropped and ``script``/``style`` bodies are
discarded entirely. The result is safe to render as HTML; the CRM UI still
shows the raw stored value escaped as an extra layer.
"""

from __future__ import annotations

from html import escape
from html.parser import HTMLParser
from urllib.parse import urlsplit

ALLOWED_TAGS = frozenset(
    {
        "p",
        "br",
        "strong",
        "b",
        "em",
        "i",
        "u",
        "s",
        "ul",
        "ol",
        "li",
        "h2",
        "h3",
        "blockquote",
        "code",
        "pre",
        "a",
    }
)
VOID_TAGS = frozenset({"br"})
ALLOWED_ATTRIBUTES: dict[str, frozenset[str]] = {"a": frozenset({"href", "title"})}
SAFE_SCHEMES = frozenset({"http", "https", "mailto"})
SUPPRESSED_TAGS = frozenset({"script", "style"})


def _safe_href(raw: str) -> str | None:
    """Allow fragment/same-site links and a short list of absolute schemes."""
    candidate = raw.strip()
    if not candidate:
        return None
    if candidate.startswith("#"):
        return candidate
    if candidate.startswith("/") and not candidate.startswith("//"):
        return candidate
    parts = urlsplit(candidate)
    if parts.scheme.lower() in SAFE_SCHEMES:
        return candidate
    return None


class _AllowlistSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._stack: list[str] = []
        self._suppress_depth = 0

    def _render_attrs(self, tag: str, attrs: list[tuple[str, str | None]]) -> str:
        rendered: list[str] = []
        allowed = ALLOWED_ATTRIBUTES.get(tag, frozenset())
        for name, value in attrs:
            if name not in allowed:
                continue
            raw = value or ""
            if name == "href":
                safe = _safe_href(raw)
                if safe is not None:
                    rendered.append(f' href="{escape(safe, quote=True)}"')
            else:
                rendered.append(f' {name}="{escape(raw, quote=True)}"')
        if tag == "a":
            rendered.append(' rel="nofollow noopener"')
        return "".join(rendered)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in SUPPRESSED_TAGS:
            self._suppress_depth += 1
            return
        if self._suppress_depth or tag not in ALLOWED_TAGS:
            return
        attributes = self._render_attrs(tag, attrs)
        self._parts.append(f"<{tag}{attributes}>")
        if tag not in VOID_TAGS:
            self._stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if self._suppress_depth or tag in SUPPRESSED_TAGS or tag not in ALLOWED_TAGS:
            return
        attributes = self._render_attrs(tag, attrs)
        self._parts.append(f"<{tag}{attributes}>")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in SUPPRESSED_TAGS:
            if self._suppress_depth:
                self._suppress_depth -= 1
            return
        if self._suppress_depth or tag not in ALLOWED_TAGS or tag in VOID_TAGS:
            return
        if tag not in self._stack:
            return
        while self._stack:
            opened = self._stack.pop()
            self._parts.append(f"</{opened}>")
            if opened == tag:
                break

    def handle_data(self, data: str) -> None:
        if self._suppress_depth:
            return
        self._parts.append(escape(data, quote=False))

    def handle_comment(self, data: str) -> None:
        return

    def handle_decl(self, decl: str) -> None:
        return

    def close(self) -> None:
        super().close()
        while self._stack:
            self._parts.append(f"</{self._stack.pop()}>")

    def result(self) -> str:
        return "".join(self._parts)


def sanitize_html(value: str) -> str:
    """Return markup restricted to :data:`ALLOWED_TAGS` with escaped text."""
    if not value:
        return ""
    parser = _AllowlistSanitizer()
    parser.feed(value)
    parser.close()
    return parser.result()


__all__ = ["ALLOWED_TAGS", "SAFE_SCHEMES", "sanitize_html"]
