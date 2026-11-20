"""Типы для кастомных полей; runtime-реализация — в fields.py."""

from collections.abc import Sequence
from typing import Any

from django.db import models

class CitextField(models.CharField[str, str]):
    def db_type(self, connection: Any) -> str: ...
    def deconstruct(self) -> tuple[str, str, Sequence[Any], dict[str, Any]]: ...

class UUID7(models.Func):
    function: str
    output_field: models.UUIDField[Any, Any]
    def __init__(self) -> None: ...
