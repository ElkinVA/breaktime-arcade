from __future__ import annotations

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StaffRole, User
from apps.catalog.models import Game, GameTranslation, GameVersion, Genre
from apps.crm.services.games import (
    GameFilters,
    build_game_list_page,
    load_game_card,
    parse_filters,
)
from apps.i18n.models import Language

PASSWORD = "correct horse battery staple"


def _genre(code: str) -> Genre:
    genre, _created = Genre.objects.get_or_create(code=code)
    return genre


def _game(
    *,
    technical_id: str,
    genre: str = "puzzle",
    status: str = Game.STATUS_DRAFT,
) -> Game:
    return Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=f"slug-{technical_id}",
        primary_genre=_genre(genre),
        status=status,
        published_at=timezone.now() if status == Game.STATUS_PUBLISHED else None,
    )


def _version(
    game: Game,
    semver: str,
    *,
    languages: tuple[str, ...] = ("en",),
    blockers: int = 0,
    autotest_passed: bool = False,
) -> GameVersion:
    return GameVersion.objects.create(
        game=game,
        semver=semver,
        package_hash=("a" * 64),
        runtime_hash=("b" * 64),
        sdk_version="1.1.0",
        size_bytes=1000,
        manifest={},
        supported_languages=list(languages),
        validation_report={"ok": blockers == 0, "summary": {"blocker": blockers}},
        e2e_report={"passed": autotest_passed},
    )


def _translation(game: Game, name: str) -> GameTranslation:
    return GameTranslation.objects.create(
        game=game,
        language=Language.objects.get(code="en"),
        name=name,
        slug=f"slug-{game.technical_id}",
        short_description="Short",
        description="Description",
    )


def _set_current(game: Game, version: GameVersion) -> Game:
    game.current_version = version
    game.save(update_fields=["current_version"])
    return game


def _staff(role: str = StaffRole.OWNER) -> User:
    staff = User.objects.create_user(
        login="staff",
        password=PASSWORD,
        is_staff=True,
        crm_role=role,
    )
    User.objects.filter(pk=staff.pk).update(totp_confirmed_at=timezone.now())
    staff.refresh_from_db()
    return staff


def _staff_client(*, verified_2fa: bool = True, role: str = StaffRole.OWNER) -> Client:
    staff = _staff(role)
    client = Client()
    client.force_login(staff)
    if verified_2fa:
        session = client.session
        session["ba_2fa_verified"] = True
        session.save()
    return client


def _elevate_step_up(client: Client) -> None:
    session = client.session
    session["crm_step_up_at"] = timezone.now().isoformat()
    session.save()


@pytest.mark.django_db
def test_crm_login_uses_staff_login_flow() -> None:
    anonymous = Client()
    response = anonymous.get(reverse("crm:login"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("accounts:login"))
    assert "next=" in response.url

    user = User.objects.create_user(login="plain", password=PASSWORD)
    non_staff = Client()
    non_staff.force_login(user)
    response = non_staff.get(reverse("crm:login"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("accounts:login"))


@pytest.mark.django_db
def test_anonymous_and_non_staff_are_redirected_from_inventory() -> None:
    game = _game(technical_id="locked_game")

    anonymous = Client()
    for url in (reverse("crm:games"), reverse("crm:game_detail", args=[game.id])):
        response = anonymous.get(url)
        assert response.status_code == 302
        assert response.url == reverse("crm:login")

    user = User.objects.create_user(login="plain", password=PASSWORD)
    non_staff = Client()
    non_staff.force_login(user)
    for url in (reverse("crm:games"), reverse("crm:game_detail", args=[game.id])):
        response = non_staff.get(url)
        assert response.status_code == 302
        assert response.url == reverse("crm:login")


@pytest.mark.django_db
def test_staff_without_verified_2fa_is_sent_to_staff_login() -> None:
    _game(technical_id="needs_2fa")
    client = _staff_client(verified_2fa=False)

    response = client.get(reverse("crm:games"))

    assert response.status_code == 302
    assert response.url.startswith(reverse("accounts:login"))


@pytest.mark.django_db
def test_staff_games_list_counters_filters_and_links() -> None:
    published = _game(
        technical_id="published_game",
        genre="puzzle",
        status=Game.STATUS_PUBLISHED,
    )
    published_version = _version(published, "1.2.3", languages=("en", "de"))
    _set_current(published, published_version)
    draft = _game(technical_id="draft_game", genre="arcade")
    _set_current(draft, _version(draft, "0.1.0"))

    client = _staff_client()
    response = client.get(reverse("crm:games"))

    assert response.status_code == 200
    content = response.content.decode()
    assert 'data-testid="crm-games-total">2<' in content
    assert 'data-testid="crm-games-published">1<' in content
    assert 'data-testid="crm-games-draft">1<' in content
    assert "published_game" in content
    assert "draft_game" in content
    assert "v1.2.3" in content
    assert f'href="{reverse("crm:game_detail", args=[published.id])}"' in content
    assert 'data-testid="crm-game-localization">2/' in content

    only_drafts = client.get(reverse("crm:games"), {"status": Game.STATUS_DRAFT})
    draft_content = only_drafts.content.decode()
    assert "draft_game" in draft_content
    assert "published_game" not in draft_content
    assert 'data-testid="crm-games-total">2<' in draft_content

    only_puzzle = client.get(reverse("crm:games"), {"genre": "puzzle"})
    puzzle_content = only_puzzle.content.decode()
    assert "published_game" in puzzle_content
    assert "draft_game" not in puzzle_content

    combined = client.get(
        reverse("crm:games"),
        {"status": Game.STATUS_PUBLISHED, "genre": "arcade"},
    )
    assert 'data-testid="crm-games-empty"' in combined.content.decode()


@pytest.mark.django_db
def test_staff_game_card_shows_status_versions_and_safe_actions() -> None:
    game = _game(
        technical_id="card_game",
        genre="puzzle",
        status=Game.STATUS_PUBLISHED,
    )
    first = _version(game, "1.0.0", languages=("en",), autotest_passed=True)
    second = _version(game, "2.0.0", languages=("en", "de"), autotest_passed=True)
    _set_current(game, second)

    client = _staff_client()
    response = client.get(reverse("crm:game_detail", args=[game.id]))

    assert response.status_code == 200
    content = response.content.decode()
    assert 'data-testid="crm-card-status">Опубликована<' in content
    assert 'data-testid="crm-card-current-version">' in content
    assert "v2.0.0" in content
    assert "v1.0.0" in content
    assert content.count('data-testid="crm-version-row"') == 2
    assert 'data-testid="crm-publish-form"' in content
    assert 'data-testid="crm-rollback-form"' in content
    assert reverse("crm:game_publish", args=[game.id]) in content
    assert reverse("crm:game_rollback", args=[game.id]) in content
    # No platform or package secrets are rendered on the card.
    assert settings.SECRET_KEY not in content
    assert first.package_hash not in content
    assert first.runtime_hash not in content


@pytest.mark.django_db
def test_publish_and_rollback_are_post_only_and_switch_current_version() -> None:
    game = _game(technical_id="action_game", status=Game.STATUS_PUBLISHED)
    old = _version(game, "1.0.0", autotest_passed=True)
    new = _version(game, "2.0.0", autotest_passed=True)
    _set_current(game, new)
    client = _staff_client()
    _elevate_step_up(client)

    publish_url = reverse("crm:game_publish", args=[game.id])
    rollback_url = reverse("crm:game_rollback", args=[game.id])

    assert client.get(publish_url).status_code == 405
    assert client.get(rollback_url).status_code == 405

    response = client.post(publish_url, {"version_id": str(old.id)})
    assert response.status_code == 302
    game.refresh_from_db()
    assert game.current_version_id == old.id

    response = client.post(rollback_url, {"version_id": str(new.id)})
    assert response.status_code == 302
    game.refresh_from_db()
    assert game.current_version_id == new.id

    invalid = client.post(publish_url, {"version_id": "not-a-uuid"})
    assert invalid.status_code == 302
    game.refresh_from_db()
    assert game.current_version_id == new.id


@pytest.mark.django_db
def test_non_staff_cannot_publish_or_rollback() -> None:
    game = _game(technical_id="guarded_game", status=Game.STATUS_PUBLISHED)
    old = _version(game, "1.0.0", autotest_passed=True)
    new = _version(game, "2.0.0", autotest_passed=True)
    _set_current(game, new)

    user = User.objects.create_user(login="plain", password=PASSWORD)
    client = Client()
    client.force_login(user)

    response = client.post(
        reverse("crm:game_publish", args=[game.id]),
        {"version_id": str(old.id)},
    )
    assert response.status_code == 302
    assert response.url == reverse("crm:login")
    game.refresh_from_db()
    assert game.current_version_id == new.id


def test_parse_filters_rejects_unknown_values() -> None:
    filters = parse_filters({"status": "unknown", "genre": "x" * 64})
    assert filters.status == ""
    assert filters.genre == "x" * 32

    valid = parse_filters({"status": Game.STATUS_PUBLISHED, "genre": "arcade"})
    assert valid.status == Game.STATUS_PUBLISHED
    assert valid.genre == "arcade"


@pytest.mark.django_db
def test_game_list_uses_bounded_queries(django_assert_num_queries) -> None:
    for index in range(3):
        game = _game(technical_id=f"list_game_{index}", genre="puzzle")
        _translation(game, f"List game {index}")
        _set_current(game, _version(game, "1.0.0", languages=("en", "de")))

    with django_assert_num_queries(5):
        page = build_game_list_page(GameFilters(), ("en", "de", "nl"))

    assert page.counters.total == 3
    assert all(row.version is not None for row in page.rows)
    assert all(row.localization is not None for row in page.rows)


@pytest.mark.django_db
def test_game_card_uses_bounded_queries(django_assert_num_queries) -> None:
    game = _game(technical_id="query_card_game", status=Game.STATUS_PUBLISHED)
    _translation(game, "Query card game")
    old = _version(game, "1.0.0")
    _set_current(game, _version(game, "2.0.0"))

    with django_assert_num_queries(4):
        card = load_game_card(game.id, ("en", "de"))

    assert card is not None
    assert card.current_version is not None
    assert card.current_version.semver == "2.0.0"
    assert {row.version.semver for row in card.versions} == {"1.0.0", "2.0.0"}
    assert old.game_id == game.id
