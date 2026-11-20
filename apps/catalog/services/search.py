"""Поисковые выражения каталога: unaccent и обновление вектора."""

from __future__ import annotations

from typing import Any

from django.contrib.postgres.search import SearchVector
from django.db.models import Func

from apps.catalog.models import GameTranslation


class Unaccent(Func):
    function = "unaccent"
    arity = 1


def translation_search_vector() -> Any:
    return (
        SearchVector(Unaccent("name"), weight="A", config="simple")
        + SearchVector(Unaccent("short_description"), weight="B", config="simple")
        + SearchVector(Unaccent("description"), weight="C", config="simple")
    )


def refresh_search_vectors() -> int:
    return GameTranslation.objects.update(search_vector=translation_search_vector())
