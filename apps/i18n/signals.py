"""Инвалидация кеша активных языков при изменении Language."""

from __future__ import annotations

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.i18n.models import Language
from apps.i18n.services.language_registry import invalidate_language_cache


@receiver(post_save, sender=Language)
@receiver(post_delete, sender=Language)
def invalidate_active_language_cache(sender: type[Language], **kwargs: object) -> None:
    # Инвалидируем после commit: иначе конкурентный запрос может повторно
    # заполнить кэш старым состоянием до фиксации транзакции.
    transaction.on_commit(invalidate_language_cache)
