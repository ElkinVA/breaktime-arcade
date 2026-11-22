"""Read-mostly admin for import drafts (CRM UI is implemented separately)."""

from __future__ import annotations

from django.contrib import admin

from apps.pipeline.models import GameImportDraft


@admin.register(GameImportDraft)
class GameImportDraftAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("package_hash", "status", "game", "version", "created_at")
    list_filter = ("status",)
    search_fields = ("package_hash", "original_filename")
    readonly_fields = (
        "package_hash",
        "original_filename",
        "size_bytes",
        "manifest",
        "diagnostics",
        "validation_report",
        "import_report",
        "injection_report",
        "e2e_report",
        "conflicts",
        "created_at",
        "updated_at",
    )
