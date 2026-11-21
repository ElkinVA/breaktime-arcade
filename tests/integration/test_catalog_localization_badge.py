"""Покрытие локализации: сервис и бейдж на карточке/странице игры (§2.15)."""

from __future__ import annotations

import pytest
from django.core.cache import caches
from django.test import Client, override_settings
from django.utils import timezone

from apps.catalog.models import Game, GameVersion, Genre
from apps.catalog.services.localization import (
    effective_languages,
    localization_coverage,
)
from apps.i18n.models import Language

LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "throttle": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    caches["default"].clear()
    caches["throttle"].clear()
    yield
    caches["default"].clear()
    caches["throttle"].clear()


def _active_codes() -> list[str]:
    return list(
        Language.objects.filter(is_active=True)
        .order_by("sort_order", "code")
        .values_list("code", flat=True)
    )


def _game(technical_id: str, *, supported_languages: list[str] | None = None) -> Game:
    genre, _ = Genre.objects.get_or_create(code=f"genre_{technical_id}")
    game = Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=f"slug-{technical_id}",
        primary_genre=genre,
        status=Game.STATUS_PUBLISHED,
        published_at=timezone.now(),
    )
    if supported_languages is not None:
        version = GameVersion.objects.create(
            game=game,
            semver="1.0.0",
            package_hash="a" * 64,
            runtime_hash="b" * 64,
            sdk_version="1.1.0",
            size_bytes=1,
            manifest={},
            supported_languages=supported_languages,
        )
        game.current_version = version
        game.save(update_fields=["current_version"])
    return game


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_localization_coverage_full_partial_and_no_version() -> None:
    active = _active_codes()
    assert len(active) > 1

    full = _game("loc_full", supported_languages=active)
    partial = _game("loc_partial", supported_languages=active[:2])
    no_version = _game("loc_no_version")

    full_coverage = localization_coverage(full)
    assert full_coverage is not None
    assert full_coverage.covered == len(active)
    assert full_coverage.total == len(active)
    assert full_coverage.is_full

    partial_coverage = localization_coverage(partial)
    assert partial_coverage is not None
    assert partial_coverage.covered == 2
    assert partial_coverage.total == len(active)
    assert not partial_coverage.is_full

    assert localization_coverage(no_version) is None
    assert effective_languages(no_version.current_version, active) == ()


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_effective_languages_are_intersected_with_active_site_languages() -> None:
    active = _active_codes()

    # Язык, которого нет среди активных, не увеличивает покрытие.
    extra = _game("loc_extra", supported_languages=[*active, "xx-unknown"])
    assert effective_languages(extra.current_version, active) == tuple(active)
    extra_coverage = localization_coverage(extra)
    assert extra_coverage is not None
    assert extra_coverage.is_full

    # Пакет только с неактивными языками покрывает 0 из M.
    unknown = _game("loc_unknown", supported_languages=["xx-unknown"])
    unknown_coverage = localization_coverage(unknown)
    assert unknown_coverage is not None
    assert unknown_coverage.covered == 0
    assert unknown_coverage.total == len(active)
    assert not unknown_coverage.is_full


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_cards_and_detail_render_full_and_partial_badges() -> None:
    active = _active_codes()
    _game("badge_full", supported_languages=active)
    _game("badge_partial", supported_languages=active[:3])

    listing = Client().get("/en/games/")
    assert listing.status_code == 200
    content = listing.content.decode()
    assert content.count('data-testid="card-localization"') == 2
    assert 'data-testid="card-localization">Full localization<' in content
    assert f'data-testid="card-localization">Partial: 3 of {len(active)}<' in content

    full_detail = Client().get("/en/games/slug-badge_full/")
    assert full_detail.status_code == 200
    assert 'data-testid="game-localization">Full localization<' in full_detail.content.decode()

    partial_detail = Client().get("/en/games/slug-badge_partial/")
    assert partial_detail.status_code == 200
    assert (
        f'data-testid="game-localization">Partial: 3 of {len(active)}<'
        in partial_detail.content.decode()
    )


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_game_without_current_version_renders_no_badge() -> None:
    _game("badge_no_version")

    listing = Client().get("/en/games/")
    assert listing.status_code == 200
    assert 'data-testid="card-localization"' not in listing.content.decode()

    detail = Client().get("/en/games/slug-badge_no_version/")
    assert detail.status_code == 200
    assert 'data-testid="game-localization"' not in detail.content.decode()
