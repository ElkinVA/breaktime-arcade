"""CRM SEO diagnostics for published games (§2.19)."""

from __future__ import annotations

import re

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StaffRole, User
from apps.catalog.models import Game, GameAsset, GameTranslation, GameVersion, Genre
from apps.crm.services.seo_diagnostics import (
    DESCRIPTION_MISSING,
    DUPLICATE_GAMES_LIMIT,
    ISSUE_LIST_LIMIT,
    META_DESCRIPTION_MISSING,
    MISSING_TRANSLATION,
    UNSUPPORTED_LANGUAGE,
    build_seo_diagnostics,
    duplicate_title_issues,
    empty_description_issues,
    incomplete_translation_issues,
    missing_alt_issues,
)
from apps.i18n.models import Language
from apps.i18n.services.language_registry import (
    get_active_language_codes_safely,
    invalidate_language_cache,
)

PASSWORD = "correct horse battery staple"


def _genre() -> Genre:
    genre, _created = Genre.objects.get_or_create(code="puzzle")
    return genre


def _game(
    technical_id: str,
    *,
    status: str = Game.STATUS_PUBLISHED,
    supported_languages: tuple[str, ...] = ("en",),
) -> Game:
    game = Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=f"slug-{technical_id}",
        primary_genre=_genre(),
        status=status,
        published_at=timezone.now() if status == Game.STATUS_PUBLISHED else None,
    )
    version = GameVersion.objects.create(
        game=game,
        semver="1.0.0",
        package_hash="a" * 64,
        runtime_hash="b" * 64,
        sdk_version="1.1.0",
        size_bytes=1000,
        manifest={},
        supported_languages=list(supported_languages),
        validation_report={"ok": True, "summary": {"blocker": 0}},
        e2e_report={"passed": True},
    )
    game.current_version = version
    game.save(update_fields=["current_version"])
    return game


def _translation(
    game: Game,
    code: str,
    *,
    name: str | None = None,
    description: str = "Long enough localized description",
    short_description: str = "Short description",
    seo_title: str = "",
    seo_description: str = "",
) -> GameTranslation:
    return GameTranslation.objects.create(
        game=game,
        language=Language.objects.get(code=code),
        name=name if name is not None else f"{game.technical_id} {code}",
        slug=f"slug-{game.technical_id}-{code}",
        short_description=short_description,
        description=description,
        seo_title=seo_title,
        seo_description=seo_description,
    )


def _asset(game: Game, alt: dict[str, str], *, sort_order: int = 0) -> GameAsset:
    return GameAsset.objects.create(
        game=game,
        type=GameAsset.TYPE_COVER,
        file=f"games/assets/{game.technical_id}-{sort_order}.png",
        alt=alt,
        sort_order=sort_order,
    )


def _staff(role: str) -> User:
    staff = User.objects.create_user(
        login=f"staff_{role}",
        password=PASSWORD,
        is_staff=True,
        crm_role=role,
    )
    User.objects.filter(pk=staff.pk).update(totp_confirmed_at=timezone.now())
    staff.refresh_from_db()
    return staff


def _staff_client(role: str) -> Client:
    client = Client()
    client.force_login(_staff(role))
    session = client.session
    session["ba_2fa_verified"] = True
    session.save()
    return client


@pytest.mark.django_db
def test_empty_description_query_flags_blank_localized_description() -> None:
    broken = _game("broken_descriptions")
    _translation(broken, "en", description="")
    missing_meta = _game("missing_meta")
    _translation(
        missing_meta,
        "en",
        short_description="",
        seo_description="",
    )
    healthy = _game("healthy_descriptions")
    _translation(
        healthy,
        "en",
        description="A long description",
        short_description="A short description",
        seo_description="A meta description",
    )
    draft = _game("draft_descriptions", status=Game.STATUS_DRAFT)
    _translation(draft, "en", description="")

    issues = empty_description_issues(["en"])

    assert {(issue.game.pk, issue.reason) for issue in issues} == {
        (broken.pk, DESCRIPTION_MISSING),
        (missing_meta.pk, META_DESCRIPTION_MISSING),
    }


@pytest.mark.django_db
def test_duplicate_title_query_groups_by_language() -> None:
    first = _game("dup_one")
    _translation(first, "en", name="Same Title", seo_title="Same Title")
    second = _game("dup_two")
    _translation(second, "en", name="Same Title", seo_title="same title")
    unique = _game("unique_one")
    _translation(unique, "en", name="Unique Title")
    other_language = _game("dup_other_language")
    _translation(other_language, "de", name="Same Title")
    draft = _game("dup_draft", status=Game.STATUS_DRAFT)
    _translation(draft, "en", name="Same Title")

    issues = duplicate_title_issues(["en", "de"])

    assert len(issues) == 1
    issue = issues[0]
    assert issue.language_code == "en"
    assert issue.title == "Same Title"
    assert {game.pk for game in issue.games} == {first.pk, second.pk}


@pytest.mark.django_db
def test_missing_alt_query_reports_each_language() -> None:
    game = _game("alt_game")
    _asset(game, {"en": "Cover"})
    _asset(game, {"en": "  "}, sort_order=1)
    draft = _game("alt_draft", status=Game.STATUS_DRAFT)
    _asset(draft, {})

    issues = missing_alt_issues(["en", "de"])

    assert {(issue.game.pk, issue.language_code, issue.sort_order) for issue in issues} == {
        (game.pk, "de", 0),
        (game.pk, "en", 1),
        (game.pk, "de", 1),
    }


@pytest.mark.django_db
def test_incomplete_translation_query_reports_missing_languages() -> None:
    game = _game("translation_game", supported_languages=("en", "de"))
    _translation(game, "en")
    unsupported = _game("unsupported_language_game", supported_languages=("en",))
    _translation(unsupported, "en")
    _translation(unsupported, "de")
    draft = _game(
        "translation_draft",
        status=Game.STATUS_DRAFT,
        supported_languages=("en",),
    )
    _translation(draft, "en")

    issues = incomplete_translation_issues(["en", "de"])

    assert {(issue.game.pk, issue.language_code, issue.reason) for issue in issues} == {
        (game.pk, "de", MISSING_TRANSLATION),
        (unsupported.pk, "de", UNSUPPORTED_LANGUAGE),
    }


@pytest.mark.django_db
def test_build_seo_diagnostics_adds_per_language_summary() -> None:
    game = _game("summary_game", supported_languages=("en",))
    _translation(game, "en", name="Summary title", description="")
    _asset(game, {})
    duplicate = _game("summary_duplicate")
    _translation(duplicate, "en", name="Summary title")

    diagnostics = build_seo_diagnostics(["en", "de"])

    assert diagnostics.language_codes == ("en", "de")
    summaries = {row.language_code: row for row in diagnostics.summaries}
    assert summaries["en"].empty_descriptions == 1
    assert summaries["en"].duplicate_titles == 1
    assert summaries["en"].missing_alt == 1
    assert summaries["en"].incomplete_translations == 0
    assert summaries["de"].incomplete_translations == 2
    assert diagnostics.total_issues == len(diagnostics.descriptions) + len(
        diagnostics.duplicate_titles
    ) + len(diagnostics.missing_alt) + len(diagnostics.incomplete_translations)


@pytest.mark.django_db
def test_screen_lists_offending_games_with_links() -> None:
    game = _game("screen_game")
    _translation(game, "en", description="")
    _asset(game, {})
    client = _staff_client(StaffRole.OWNER)

    response = client.get(reverse("crm:seo_diagnostics"))

    assert response.status_code == 200
    content = response.content.decode()
    assert game.technical_id in content
    assert reverse("crm:game_detail", args=[game.id]) in content
    assert "en" in content
    assert 'data-testid="crm-seo-description-issue"' in content
    assert 'data-testid="crm-seo-alt-issue"' in content


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (StaffRole.OWNER, 200),
        (StaffRole.EDITOR, 200),
        (StaffRole.MODERATOR, 403),
        (StaffRole.OBSERVER, 403),
    ],
)
def test_screen_is_gated_by_games_view_capability(role: str, expected: int) -> None:
    client = _staff_client(role)
    response = client.get(reverse("crm:seo_diagnostics"))
    assert response.status_code == expected


@pytest.mark.django_db
def test_screen_redirects_anonymous_to_staff_login() -> None:
    response = Client().get(reverse("crm:seo_diagnostics"))
    assert response.status_code == 302
    assert response.url == reverse("crm:login")


def _summary_row(content: str, code: str) -> tuple[int, int, int, int, int]:
    """Extract (descriptions, duplicates, alt, translations, total) for a language."""
    pattern = re.compile(
        rf'data-testid="crm-seo-language-code">{re.escape(code)}</td>'
        r'.*?data-testid="crm-seo-count-descriptions">(\d+)</td>'
        r'.*?data-testid="crm-seo-count-duplicates">(\d+)</td>'
        r'.*?data-testid="crm-seo-count-alt">(\d+)</td>'
        r'.*?data-testid="crm-seo-count-translations">(\d+)</td>'
        r'.*?data-testid="crm-seo-count-total">(\d+)</td>',
        re.DOTALL,
    )
    match = pattern.search(content)
    assert match is not None, f"summary row for {code!r} is missing"
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
        int(match.group(4)),
        int(match.group(5)),
    )


@pytest.mark.django_db
def test_screen_bounds_lists_for_large_catalog_and_keeps_summary_exact() -> None:
    """A 1000+ game catalog must not render an unbounded diagnostics page."""
    invalidate_language_cache()
    active = get_active_language_codes_safely()
    assert "en" in active

    total_games = 1001
    common_title = "Shared catalog title"
    published_at = timezone.now()
    genre = _genre()
    games = Game.objects.bulk_create(
        [
            Game(
                technical_id=f"bulk_{index:04d}",
                host_label=f"bulk-{index:04d}.games.test",
                slug=f"slug-bulk-{index:04d}",
                primary_genre=genre,
                status=Game.STATUS_PUBLISHED,
                published_at=published_at,
            )
            for index in range(total_games)
        ]
    )
    versions = GameVersion.objects.bulk_create(
        [
            GameVersion(
                game=game,
                semver="1.0.0",
                package_hash="a" * 64,
                runtime_hash="b" * 64,
                sdk_version="1.1.0",
                size_bytes=1000,
                manifest={},
                supported_languages=["en"],
                validation_report={"ok": True, "summary": {"blocker": 0}},
                e2e_report={"passed": True},
            )
            for game in games
        ]
    )
    for game, version in zip(games, versions, strict=True):
        game.current_version = version
    Game.objects.bulk_update(games, ["current_version"])

    en = Language.objects.get(code="en")
    GameTranslation.objects.bulk_create(
        [
            GameTranslation(
                game=game,
                language=en,
                name=common_title,
                slug=f"slug-{game.technical_id}-en",
                short_description="Short description",
                description="",
                seo_description="",
            )
            for game in games
        ]
    )
    GameAsset.objects.bulk_create(
        [
            GameAsset(
                game=game,
                type=GameAsset.TYPE_COVER,
                file=f"games/assets/{game.technical_id}.png",
                alt={},
                sort_order=0,
            )
            for game in games
        ]
    )

    client = _staff_client(StaffRole.OWNER)
    response = client.get(reverse("crm:seo_diagnostics"))

    assert response.status_code == 200
    content = response.content.decode()

    # Every diagnostic category renders a bounded number of entries even though
    # the catalog produces thousands of findings.
    assert content.count('data-testid="crm-seo-description-issue"') == ISSUE_LIST_LIMIT
    assert content.count('data-testid="crm-seo-alt-issue"') == ISSUE_LIST_LIMIT
    assert content.count('data-testid="crm-seo-translation-issue"') == ISSUE_LIST_LIMIT
    assert content.count('data-testid="crm-seo-duplicate-issue"') == 1
    assert content.count('data-testid="crm-seo-game-link"') <= (
        3 * ISSUE_LIST_LIMIT + DUPLICATE_GAMES_LIMIT
    )
    assert len(response.content) < 500_000
    assert 'data-testid="crm-seo-descriptions-truncated"' in content
    assert 'data-testid="crm-seo-alt-truncated"' in content
    assert 'data-testid="crm-seo-translations-truncated"' in content
    assert 'data-testid="crm-seo-duplicates-games-hidden"' in content

    # The per-language summary is still computed from the complete issue sets.
    assert _summary_row(content, "en") == (
        total_games,
        1,
        total_games,
        0,
        2 * total_games + 1,
    )
    assert _summary_row(content, "de") == (
        0,
        0,
        total_games,
        total_games,
        2 * total_games,
    )
    expected_total = total_games + 1
    expected_total += total_games * len(active)
    expected_total += total_games * (len(active) - 1)
    assert f"Проблем: {expected_total}" in content
