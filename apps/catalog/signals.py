"""Обновление persisted search_vector при сохранении перевода."""

from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.catalog.models import GameTranslation
from apps.catalog.services.search import translation_search_vector


@receiver(post_save, sender=GameTranslation)
def update_game_translation_search_vector(
    sender: type[GameTranslation],
    instance: GameTranslation,
    **kwargs: object,
) -> None:
    del sender, kwargs
    GameTranslation.objects.filter(pk=instance.pk).update(search_vector=translation_search_vector())
