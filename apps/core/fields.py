"""Типы БД: citext и серверный генератор uuidv7() (PostgreSQL 18)."""
from __future__ import annotations

from typing import Any

from django.db import models
from django.db.models import Func


class CitextField(models.CharField):
    """Регистронезависимый текст; требует расширения citext."""

    def db_type(self, connection: Any) -> str:
        return "citext"

    def deconstruct(self) -> tuple[str, str, list[Any], dict[str, Any]]:
        name, _path, args, kwargs = super().deconstruct()
        return name, "apps.core.fields.CitextField", args, kwargs


class UUID7(Func):
    """DEFAULT uuidv7() на уровне БД."""

    function = "uuidv7"
    output_field = models.UUIDField()

    def __init__(self) -> None:
        super().__init__()
