"""Small access/redirect helpers shared by CRM views."""

from __future__ import annotations

from django.urls import reverse


def safe_next_path(raw: str, *, default: str | None = None) -> str:
    """Accept only same-site absolute paths as post-login/step-up targets.

    Backslashes and control characters are rejected because browsers may
    normalise them into an off-site ``//host`` URL.
    """
    fallback = default or reverse("crm:dashboard")
    candidate = (raw or "").strip()
    if not candidate.startswith("/") or candidate.startswith("//"):
        return fallback
    if "\\" in candidate or any(ord(char) < 32 for char in candidate):
        return fallback
    return candidate
