"""CRM game card: read-only records/epochs section (§2.16.2).

The staff board must be an exact read-only projection of the public
leaderboard: same ordering, same ranks, with an epoch selector for archives.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StaffRole, User, UserProfile
from apps.catalog.models import Game, GameVersion, Genre
from apps.gameplay.models import GameResult, GameSession, LeaderboardEntry
from apps.leaderboards.services.queries import get_leaderboard

PASSWORD = "correct horse battery staple"
PAGE_SIZE = 25


def _game(
    *,
    technical_id: str = "records_game",
    epoch: int = 1,
    direction: str = "higher_is_better",
) -> Game:
    genre, _created = Genre.objects.get_or_create(code="records_genre")
    game = Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=f"slug-{technical_id}",
        primary_genre=genre,
        status=Game.STATUS_PUBLISHED,
        published_at=timezone.now(),
        score_direction=direction,
        leaderboard_epoch=epoch,
    )
    version = GameVersion.objects.create(
        game=game,
        semver="1.0.0",
        package_hash="a" * 64,
        runtime_hash="b" * 64,
        sdk_version="1.1.0",
        size_bytes=1000,
        manifest={},
        supported_languages=["en"],
    )
    game.current_version = version
    game.save(update_fields=["current_version"])
    return game


def _user(login: str, nickname: str) -> User:
    user = User.objects.create_user(login=login, password=PASSWORD)
    UserProfile.objects.create(
        user=user,
        nickname=nickname,
        nickname_skeleton=nickname.lower(),
    )
    return user


def _entry(
    game: Game,
    user: User,
    value: int,
    *,
    epoch: int,
    achieved_at: datetime | None = None,
    trust_level: str = GameResult.TRUST_CLIENT_REPORTED,
    is_public: bool = True,
) -> LeaderboardEntry:
    now = timezone.now()
    session = GameSession.objects.create(
        game=game,
        game_version=game.current_version,
        subject_type=GameSession.SUBJECT_USER,
        subject_id=user.id,
        mode=GameSession.MODE_USER,
        state=GameSession.STATE_FINISHED,
        seed=f"seed-{user.pk}-{epoch}-{value}",
        max_session_seconds=1800,
        activated_at=now - timedelta(seconds=30),
        last_heartbeat_at=now,
        finished_at=now,
    )
    result = GameResult.objects.create(
        session=session,
        game=game,
        game_version=game.current_version,
        subject_type=GameResult.SUBJECT_USER,
        user=user,
        epoch=epoch,
        value=value,
        unit=game.score_unit,
        duration_ms=30_000,
        trust_level=trust_level,
        is_public=is_public,
        idempotency_key=f"key-{user.pk}-{epoch}-{value}",
    )
    reached = achieved_at or now
    GameResult.objects.filter(pk=result.pk).update(created_at=reached)
    result.refresh_from_db()
    return LeaderboardEntry.objects.create(
        game=game,
        epoch=epoch,
        user=user,
        best_result=result,
        value=value,
        achieved_at=result.created_at,
        trust_level=trust_level,
        is_public=is_public,
    )


def _staff_client(*, role: str = StaffRole.OWNER) -> Client:
    staff = User.objects.create_user(
        login=f"staff_{role or 'none'}",
        password=PASSWORD,
        is_staff=True,
        crm_role=role,
    )
    User.objects.filter(pk=staff.pk).update(totp_confirmed_at=timezone.now())
    client = Client()
    client.force_login(staff)
    session = client.session
    session["ba_2fa_verified"] = True
    session.save()
    return client


def _detail_url(game: Game) -> str:
    return reverse("crm:game_detail", args=[game.id])


_ROW_RE = re.compile(r'<tr[^>]*data-testid="crm-record-row"[^>]*>(.*?)</tr>', re.S)
_SECTION_RE = re.compile(r'data-testid="crm-game-records".*?</section>', re.S)


def _rows(content: str) -> list[str]:
    return _ROW_RE.findall(content)


def _cell(row: str, name: str) -> str:
    match = re.search(rf'data-testid="crm-record-{name}"[^>]*>(.*?)</td>', row, re.S)
    return match.group(1).strip() if match else ""


@pytest.mark.django_db
def test_current_epoch_order_matches_public_leaderboard_and_renders_dates() -> None:
    game = _game(technical_id="parity_game", epoch=1)
    base = timezone.now() - timedelta(days=1)
    alice = _user("alice", "Alice")
    bob = _user("bob", "Bob")
    carol = _user("carol", "Carol")
    _entry(game, bob, 100, epoch=1, achieved_at=base + timedelta(seconds=20))
    _entry(game, alice, 100, epoch=1, achieved_at=base + timedelta(seconds=10))
    _entry(
        game,
        carol,
        75,
        epoch=1,
        achieved_at=base + timedelta(seconds=30),
        trust_level=GameResult.TRUST_REPLAY_VERIFIED,
    )

    public = get_leaderboard(game, limit=100, user=None)
    response = _staff_client(role=StaffRole.EDITOR).get(_detail_url(game))

    assert response.status_code == 200
    content = response.content.decode()
    rows = _rows(content)
    # Tie-break on achieved_at is part of the public board contract.
    assert [_cell(row, "rank") for row in rows] == ["1", "2", "3"]
    assert [int(_cell(row, "value")) for row in rows] == [100, 100, 75]
    assert [_cell(row, "nickname") for row in rows] == ["Alice", "Bob", "Carol"]
    assert [_cell(row, "trust") for row in rows] == [
        "Client reported",
        "Client reported",
        "Replay verified",
    ]
    expected = [(entry["rank"], entry["nickname"], entry["value"]) for entry in public["entries"]]
    assert [
        (int(_cell(row, "rank")), _cell(row, "nickname"), int(_cell(row, "value"))) for row in rows
    ] == expected
    # The date cell must be actually rendered, not silently dropped by the
    # template's ``date`` filter (it requires a datetime, not an ISO string).
    dates = [_cell(row, "achieved-at") for row in rows]
    assert all(dates)
    assert dates[0] == timezone.localtime(
        LeaderboardEntry.objects.get(game=game, user=alice).achieved_at
    ).strftime("%Y-%m-%d %H:%M")


@pytest.mark.django_db
def test_epoch_selector_lists_archives_and_archive_board_is_read_only() -> None:
    game = _game(technical_id="epochs_game", epoch=2)
    current_user = _user("current", "Current Player")
    archive_user = _user("archive", "Archive Player")
    _entry(game, current_user, 500, epoch=2)
    _entry(game, archive_user, 300, epoch=1)

    client = _staff_client(role=StaffRole.OWNER)

    current = client.get(_detail_url(game)).content.decode()
    assert 'data-testid="crm-records-epoch-select"' in current
    assert '<option value="2" selected>' in current
    assert '<option value="1">' in current
    assert "Current Player" in current
    assert "Archive Player" not in current
    assert 'data-testid="crm-records-archive"' not in current

    archive = client.get(_detail_url(game), {"epoch": 1}).content.decode()
    rows = _rows(archive)
    assert [int(_cell(row, "value")) for row in rows] == [300]
    assert [_cell(row, "nickname") for row in rows] == ["Archive Player"]
    assert [_cell(row, "rank") for row in rows] == ["1"]
    assert "Current Player" not in archive
    assert 'data-testid="crm-records-archive"' in archive
    assert '<option value="1" selected>' in archive
    # The archive view exposes no write/moderate controls.
    section = _SECTION_RE.search(archive)
    assert section is not None
    assert '<form method="post"' not in section.group(0)


@pytest.mark.django_db
def test_records_pagination_is_bounded_and_clamped() -> None:
    game = _game(technical_id="paged_records_game", epoch=1)
    base = timezone.now() - timedelta(days=2)
    for index in range(30):
        user = _user(f"paged_{index}", f"Paged {index}")
        _entry(
            game,
            user,
            10_000 - index,
            epoch=1,
            achieved_at=base + timedelta(seconds=index),
        )

    client = _staff_client(role=StaffRole.OWNER)
    first = client.get(_detail_url(game))
    assert first.status_code == 200
    assert first.context["records"].page_obj.paginator.count == 30
    assert first.context["records"].page_obj.paginator.num_pages == 2
    first_rows = _rows(first.content.decode())
    assert len(first_rows) == PAGE_SIZE
    assert [_cell(row, "rank") for row in first_rows] == [str(n) for n in range(1, 26)]

    second = client.get(_detail_url(game), {"page": 2})
    second_rows = _rows(second.content.decode())
    assert [_cell(row, "rank") for row in second_rows] == [str(n) for n in range(26, 31)]

    beyond = client.get(_detail_url(game), {"page": 999})
    beyond_rows = _rows(beyond.content.decode())
    assert [_cell(row, "rank") for row in beyond_rows] == [str(n) for n in range(26, 31)]

    for query in ("0", "-1", "abc", ""):
        clamped = client.get(_detail_url(game), {"page": query})
        clamped_rows = _rows(clamped.content.decode())
        assert clamped_rows
        assert clamped_rows[0] == first_rows[0]


@pytest.mark.django_db
def test_empty_records_state_without_entries() -> None:
    game = _game(technical_id="empty_records_game", epoch=1)
    client = _staff_client(role=StaffRole.EDITOR)

    response = client.get(_detail_url(game))

    assert response.status_code == 200
    content = response.content.decode()
    assert 'data-testid="crm-records-empty"' in content
    assert _rows(content) == []
    assert 'data-testid="crm-records-epoch-select"' not in content
    # An unknown/hand-edited epoch must not break the read-only screen.
    unknown = client.get(_detail_url(game), {"epoch": "not-a-number"})
    assert unknown.status_code == 200
    assert 'data-testid="crm-records-empty"' in unknown.content.decode()


@pytest.mark.django_db
def test_records_tab_is_guarded_by_games_view_role() -> None:
    game = _game(technical_id="guarded_records_game", epoch=1)
    _entry(game, _user("guarded", "Guarded"), 10, epoch=1)
    url = _detail_url(game)

    anonymous = Client().get(url)
    assert anonymous.status_code == 302
    assert anonymous.url == reverse("crm:login")

    plain = User.objects.create_user(login="plain_user", password=PASSWORD)
    non_staff = Client()
    non_staff.force_login(plain)
    assert non_staff.get(url).status_code == 302

    for denied_role in ("", StaffRole.MODERATOR, StaffRole.OBSERVER):
        response = _staff_client(role=denied_role).get(url)
        assert response.status_code == 403

    allowed = _staff_client(role=StaffRole.EDITOR)
    assert allowed.get(url).status_code == 200
    # The records tab itself is GET-only.
    assert allowed.post(url).status_code == 405
