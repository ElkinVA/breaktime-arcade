"""Safe report downloads for the CRM wizard (§2.14.7, §2.16.3).

The download name is derived from the draft UUID only, never from the uploaded
filename, so header injection and path traversal are not possible. Responses
are always attachments with a nosniff header.
"""

from __future__ import annotations

from django.http import HttpResponse

from apps.crm.services.reports import REPORT_FORMATS, render_report
from apps.pipeline.models import GameImportDraft


class ReportFormatError(ValueError):
    """Unknown report format requested by the caller."""


def report_download_name(draft: GameImportDraft, report_format: str) -> str:
    return f"draft-{draft.id}-report.{report_format}"


def report_response(draft: GameImportDraft, report_format: str) -> HttpResponse:
    """Build a staff-only attachment response for a persisted draft."""
    token = report_format.strip().lower()
    if token not in REPORT_FORMATS:
        raise ReportFormatError(token)
    content, content_type = render_report(draft, token)
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{report_download_name(draft, token)}"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response
