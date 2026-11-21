from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from apps.catalog.models import Game, GameTranslation, Genre
from apps.i18n.models import Language


@pytest.mark.django_db
def test_game_translation_public_name_is_limited_to_60_chars() -> None:
    genre = Genre.objects.create(code="name_limit")
    game = Game.objects.create(
        technical_id="name_limit",
        host_label="name-limit.games.test",
        slug="name-limit",
        primary_genre=genre,
    )
    language = Language.objects.create(code="xx", name="Test")

    translation = GameTranslation(
        game=game,
        language=language,
        name="x" * 60,
        slug="name-limit",
        short_description="short",
        description="description",
    )
    translation.full_clean()
    translation.save()

    translation.name = "x" * 61
    with pytest.raises(ValidationError):
        translation.full_clean()
