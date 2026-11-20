"""Кастомное хранилище статики для совместимости с Tailwind v4.

ManifestStaticFilesStorage Django парсит CSS и пытается найти все @import
как локальные файлы. Tailwind v4 использует bare-импорт @import "tailwindcss"
(без расширения), что вызывает ValueError. Это хранилище корректно игнорирует
такие импорты, возвращая исходное имя вместо хешированного.

Норматив: BA-PLAT-4.2 §2.7, §2.20.
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.staticfiles.storage import ManifestStaticFilesStorage

logger = logging.getLogger(__name__)


class BAStaticFilesStorage(ManifestStaticFilesStorage):
    """Хранилище статики с безопасной обработкой внешних CSS-импортов."""

    def hashed_name(
        self,
        name: str,
        content: Any | None = None,
        filename: str | None = None,
    ) -> str:
        try:
            return super().hashed_name(name, content, filename)
        except ValueError as exc:
            # Внешние импорты (например, @import "tailwindcss") не должны хешироваться.
            # Возвращаем исходное имя и логируем для диагностики.
            logger.debug(
                "Static file %s skipped hashing (external import or missing): %s",
                name,
                exc,
            )
            return name

    def _url(
        self,
        hashed_name_func: Any,
        name: str,
        force: bool = False,
        hashed_files: dict[str, str] | None = None,
    ) -> str:
        try:
            return str(
                super()._url(hashed_name_func, name, force, hashed_files)  # type: ignore[misc]
            )
        except ValueError:
            # Fallback для ссылок из CSS, указывающих на внешние ресурсы.
            return name
