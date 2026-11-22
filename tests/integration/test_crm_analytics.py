"""Local date-filtered analytics dashboard and safe CSV/JSON exports (§2.18)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StaffRole, User
from apps.catalog.models import Game, GameVersion, Genre
from apps.core.services.export_safety import csv_cell
from apps.gameplay.models import GameDailyStats, GameSession
from apps.ratings.models import GameRatingVote

PASSWORD = "correct horse battery staple"
START = date(2026, 1, 1)
END = date(2026, 1, 31)


def _staff(login: str, role: str) -> User:
    user = User.objects.create_user(
        login=login,
        password=PASSWORD,
        is_staff=True,
        crm_role=role,
    )
    User.objects.filter(pk=user.pk).update(totp_confirmed_at=timezone.now())
    user.refresh_from_db()
    return user


def _client(user: User) -> Client:
    client = Client()
    client.force_login(user)
    session = client.session
    session["ba_2fa_verified"] = True
    session.save()
    return client


def _game(
    technical_id: str,
    *,
    status: str = Game.STATUS_PUBLISHED,
    slug: str | None = None,
    published_at: datetime | None = None,
    package_hash: str = "a" * 64,
    runtime_hash: str = "b" * 64,
) -> Game:
    genre, _ = Genre.objects.get_or_create(code="arcade")
    game = Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=slug or f"slug-{technical_id}",
        primary_genre=genre,
        status=status,
        published_at=published_at,
    )
    version = GameVersion.objects.create(
        game=game,
        semver="1.0.0",
        package_hash=package_hash,
        runtime_hash=runtime_hash,
        sdk_version="1.1.0",
        size_bytes=1000,
        manifest={},
        supported_languages=["en"],
    )
    game.current_version = version
    game.save(update_fields=["current_version"])
    return game


def _session(
    game: Game,
    *,
    created_at: datetime,
    mode: str = GameSession.MODE_USER,
    state: str = GameSession.STATE_ACTIVE,
) -> GameSession:
    subject_type = (
        GameSession.SUBJECT_ANON if mode == GameSession.MODE_GUEST else GameSession.SUBJECT_USER
    )
    session = GameSession.objects.create(
        game=game,
        game_version=game.current_version,
        subject_type=subject_type,
        subject_id=uuid4(),
        mode=mode,
        state=state,
        seed=f"seed-{uuid4()}",
        max_session_seconds=1800,
    )
    GameSession.objects.filter(pk=session.pk).update(created_at=created_at)
    return session


def _vote(
    game: Game,
    user: User,
    *,
    value: int,
    created_at: datetime,
    is_valid: bool = True,
) -> GameRatingVote:
    vote = GameRatingVote.objects.create(
        game=game,
        user=user,
        value=value,
        is_valid=is_valid,
    )
    GameRatingVote.objects.filter(pk=vote.pk).update(created_at=created_at)
    return vote


def _complaint(game: Game, *, status: str, created_at: datetime):
    from apps.moderation.models import Complaint

    resolution = "done" if status == Complaint.STATUS_RESOLVED else ""
    complaint = Complaint.objects.create(
        game=game,
        subject="Complaint",
        category=Complaint.CATEGORY_OTHER,
        status=status,
        resolution=resolution,
    )
    Complaint.objects.filter(pk=complaint.pk).update(created_at=created_at)
    return complaint


@pytest.mark.django_db
def test_analytics_dashboard_metrics_and_inclusive_date_bounds() -> None:
    game_a = _game(
        "analytics_a",
        published_at=datetime(2026, 1, 10, 12, tzinfo=UTC),
    )
    game_b = _game(
        "analytics_b",
        published_at=datetime(2025, 12, 1, 12, tzinfo=UTC),
    )
    hidden = _game(
        "hidden_analytics",
        status=Game.STATUS_HIDDEN,
        published_at=datetime(2026, 1, 10, 12, tzinfo=UTC),
    )
    draft = _game(
        "draft_analytics",
        status=Game.STATUS_DRAFT,
        published_at=None,
    )

    _session(
        game_a,
        created_at=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
        state=GameSession.STATE_FINISHED,
    )
    _session(
        game_a,
        created_at=datetime(2026, 1, 31, 23, 59, 59, tzinfo=UTC),
        mode=GameSession.MODE_GUEST,
    )
    _session(
        game_a,
        created_at=datetime(2026, 1, 15, 12, tzinfo=UTC),
        mode=GameSession.MODE_PREVIEW,
    )
    _session(
        game_a,
        created_at=datetime(2026, 1, 15, 12, tzinfo=UTC),
        mode=GameSession.MODE_AUTOTEST,
    )
    _session(
        game_a,
        created_at=datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC),
    )

    GameDailyStats.objects.create(
        game=game_a, date=date(2026, 1, 15), sessions=5, unique_sessions=4, completions=3
    )
    GameDailyStats.objects.create(
        game=game_b, date=date(2026, 1, 16), sessions=3, unique_sessions=2, completions=1
    )
    GameDailyStats.objects.create(
        game=hidden, date=date(2026, 1, 15), sessions=100, unique_sessions=90, completions=10
    )
    GameDailyStats.objects.create(
        game=draft, date=date(2026, 1, 15), sessions=50, unique_sessions=40, completions=5
    )

    voter_one = User.objects.create_user(login="analytics_voter_one", password=PASSWORD)
    voter_two = User.objects.create_user(login="analytics_voter_two", password=PASSWORD)
    voter_out = User.objects.create_user(login="analytics_voter_out", password=PASSWORD)
    voter_invalid = User.objects.create_user(login="analytics_voter_invalid", password=PASSWORD)
    _vote(
        game_a,
        voter_one,
        value=5,
        created_at=datetime(2026, 1, 15, 10, tzinfo=UTC),
    )
    _vote(
        game_a,
        voter_two,
        value=3,
        created_at=datetime(2026, 1, 15, 11, tzinfo=UTC),
    )
    _vote(
        game_a,
        voter_out,
        value=1,
        created_at=datetime(2026, 2, 1, 0, 0, tzinfo=UTC),
    )
    _vote(
        game_a,
        voter_invalid,
        value=2,
        created_at=datetime(2026, 1, 15, 12, tzinfo=UTC),
        is_valid=False,
    )

    from apps.moderation.models import Complaint

    _complaint(
        game_a,
        status=Complaint.STATUS_NEW,
        created_at=datetime(2026, 1, 15, 10, tzinfo=UTC),
    )
    _complaint(
        game_a,
        status=Complaint.STATUS_ASSIGNED,
        created_at=datetime(2026, 1, 16, 10, tzinfo=UTC),
    )
    _complaint(
        game_a,
        status=Complaint.STATUS_RESOLVED,
        created_at=datetime(2026, 1, 17, 10, tzinfo=UTC),
    )
    _complaint(
        game_a,
        status=Complaint.STATUS_NEW,
        created_at=datetime(2026, 2, 2, 10, tzinfo=UTC),
    )

    analyst = _staff("analytics_observer", StaffRole.OBSERVER)
    client = _client(analyst)
    response = client.get(
        reverse("crm:analytics"),
        {"date_from": START.isoformat(), "date_to": END.isoformat()},
    )

    assert response.status_code == 200
    body = response.content.decode()
    assert 'data-testid="analytics-published-games">2<' in body
    assert 'data-testid="analytics-new-games">1<' in body
    assert 'data-testid="analytics-sessions">2<' in body
    assert 'data-testid="analytics-user-sessions">1<' in body
    assert 'data-testid="analytics-guest-sessions">1<' in body
    assert 'data-testid="analytics-finished">1<' in body
    assert 'data-testid="analytics-completion-rate">50.0<' in body
    assert 'data-testid="analytics-plays">8<' in body
    assert 'data-testid="analytics-rating-votes">2<' in body
    assert 'data-testid="analytics-average-rating">4.0<' in body
    assert 'data-testid="analytics-complaints">3<' in body
    assert 'data-testid="analytics-open-complaints">2<' in body
    assert 'data-testid="analytics-resolved-complaints">1<' in body
    assert "analytics_a" in body
    assert "analytics_b" in body
    assert "hidden_analytics" not in body
    assert "draft_analytics" not in body


@pytest.mark.django_db
def test_analytics_rejects_invalid_or_unbounded_ranges() -> None:
    analyst = _staff("analytics_range_observer", StaffRole.OBSERVER)
    client = _client(analyst)

    reversed_range = client.get(
        reverse("crm:analytics"),
        {"date_from": "2026-02-01", "date_to": "2026-01-01"},
    )
    assert reversed_range.status_code == 400

    too_large = client.get(
        reverse("crm:analytics"),
        {"date_from": "2025-01-01", "date_to": "2026-01-31"},
    )
    assert too_large.status_code == 400

    invalid_date = client.get(
        reverse("crm:analytics"),
        {"date_from": "2026-13-01", "date_to": "2026-01-31"},
    )
    assert invalid_date.status_code == 400

    export_range = client.get(
        reverse("crm:analytics_export"),
        {"format": "csv", "date_from": "2026-02-01", "date_to": "2026-01-01"},
    )
    assert export_range.status_code == 400

    bad_format = client.get(
        reverse("crm:analytics_export"),
        {"format": "xlsx", "date_from": START.isoformat(), "date_to": END.isoformat()},
    )
    assert bad_format.status_code == 400


@pytest.mark.parametrize("value", ["=1+1", "+SUM(A1)", "-2+3", "@cmd", "\tcell", "\rcell"])
def test_csv_cell_neutralises_formulas(value: str) -> None:
    assert csv_cell(value) == "'" + value


@pytest.mark.django_db
def test_analytics_exports_are_formula_safe_and_free_of_sensitive_data() -> None:
    published = _game(
        "export_game",
        slug="=SUM(A1:A2)",
        published_at=datetime(2026, 1, 10, 12, tzinfo=UTC),
        package_hash="c" * 64,
        runtime_hash="d" * 64,
    )
    unresolved = _game(
        "secret_unreleased",
        status=Game.STATUS_DRAFT,
        published_at=None,
        package_hash="e" * 64,
        runtime_hash="f" * 64,
    )
    GameDailyStats.objects.create(
        game=published, date=date(2026, 1, 15), sessions=5, unique_sessions=4, completions=3
    )
    GameDailyStats.objects.create(
        game=unresolved, date=date(2026, 1, 15), sessions=99, unique_sessions=88, completions=77
    )
    voter = User.objects.create_user(login="private_voter_login", password=PASSWORD)
    _vote(
        published,
        voter,
        value=5,
        created_at=datetime(2026, 1, 15, 10, tzinfo=UTC),
    )

    analyst = _staff("analytics_export_observer", StaffRole.OBSERVER)
    client = _client(analyst)

    csv_response = client.get(
        reverse("crm:analytics_export"),
        {"format": "csv", "date_from": START.isoformat(), "date_to": END.isoformat()},
    )
    assert csv_response.status_code == 200
    assert csv_response["Content-Type"].startswith("text/csv")
    assert csv_response["Content-Disposition"].startswith("attachment;")
    assert csv_response["X-Content-Type-Options"] == "nosniff"
    assert csv_response["Cache-Control"] == "private, no-store"
    csv_body = csv_response.content.decode()
    assert "export_game" in csv_body
    assert "'=SUM(A1:A2)" in csv_body
    assert ",=SUM(A1:A2)" not in csv_body
    assert "secret_unreleased" not in csv_body
    assert "private_voter_login" not in csv_body
    assert "c" * 64 not in csv_body
    assert "d" * 64 not in csv_body
    assert "package_hash" not in csv_body
    assert "runtime_hash" not in csv_body

    json_response = client.get(
        reverse("crm:analytics_export"),
        {"format": "json", "date_from": START.isoformat(), "date_to": END.isoformat()},
    )
    assert json_response.status_code == 200
    payload = json.loads(json_response.content)
    assert payload["games"]["published"] == 1
    assert payload["sessions"]["total"] == 0
    assert payload["top_games"][0]["technical_id"] == "export_game"
    assert payload["top_games"][0]["slug"] == "'=SUM(A1:A2)"
    serialised = json.dumps(payload)
    assert '"=SUM(A1:A2)' not in serialised
    assert "secret_unreleased" not in serialised
    assert "private_voter_login" not in serialised
    assert "package_hash" not in serialised
    assert "runtime_hash" not in serialised


@pytest.mark.django_db
def test_analytics_dashboard_defaults_to_last_30_days() -> None:
    analyst = _staff("analytics_default_observer", StaffRole.OBSERVER)
    client = _client(analyst)

    response = client.get(reverse("crm:analytics"))

    assert response.status_code == 200
    body = response.content.decode()
    today = timezone.now().astimezone(UTC).date()
    assert f'value="{today.isoformat()}"' in body
