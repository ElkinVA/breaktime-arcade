"""CRM rating moderation and complaint handling (§2.9.4, §2.16, §2.23)."""

from __future__ import annotations

import json

import pyotp
import pytest
from django.db import connection
from django.middleware.csrf import get_token
from django.test import Client, RequestFactory, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StaffRole, User
from apps.catalog.models import Game, GameTranslation, Genre
from apps.crm.models import AdminAuditLog
from apps.i18n.models import Language
from apps.moderation.models import Complaint
from apps.moderation.services.complaints import (
    assign_complaint,
    create_complaint,
    reject_complaint,
    resolve_complaint,
)
from apps.moderation.services.ratings import set_rating_visibility
from apps.ratings.models import GameRatingAggregate, GameRatingVote
from apps.ratings.services.aggregates import recalculate

PASSWORD = "correct horse battery staple"
LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "throttle": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    from django.core.cache import caches

    caches["default"].clear()
    caches["throttle"].clear()
    yield
    caches["default"].clear()
    caches["throttle"].clear()


def _user(login: str) -> User:
    return User.objects.create_user(login=login, password=PASSWORD)


def _staff(login: str, role: str, *, secret: str = "") -> User:
    user = User.objects.create_user(
        login=login,
        password=PASSWORD,
        is_staff=True,
        crm_role=role,
    )
    User.objects.filter(pk=user.pk).update(
        totp_confirmed_at=timezone.now(),
        totp_secret=secret,
    )
    user.refresh_from_db()
    return user


def _client(user: User) -> Client:
    client = Client()
    client.force_login(user)
    session = client.session
    session["ba_2fa_verified"] = True
    session.save()
    return client


def _elevate(client: Client) -> None:
    session = client.session
    session["crm_step_up_at"] = timezone.now().isoformat()
    session.save()


def _csrf(client: Client) -> str:
    """Return a token matching a cookie the test client will send."""
    token = get_token(RequestFactory().get("/"))
    client.cookies["csrftoken"] = token
    return token


def _game(technical_id: str = "moderation_game") -> Game:
    genre, _ = Genre.objects.get_or_create(code="arcade")
    game = Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=f"slug-{technical_id}",
        primary_genre=genre,
        status=Game.STATUS_PUBLISHED,
        published_at=timezone.now(),
    )
    language = Language.objects.get(code="en")
    GameTranslation.objects.create(
        game=game,
        language=language,
        name="Moderation Game",
        slug=game.slug,
        short_description="Short",
        description="Description",
    )
    return game


def _vote(game: Game, user: User, value: int) -> GameRatingVote:
    return GameRatingVote.objects.create(
        game=game,
        user=user,
        value=value,
        changed_at=timezone.now(),
        change_window_started_at=timezone.now(),
    )


def _complaint(
    game: Game,
    reporter: User,
    *,
    subject: str = "Накрутка оценок",
    rating: GameRatingVote | None = None,
) -> Complaint:
    result = create_complaint(
        game=game,
        reporter=reporter,
        subject=subject,
        category=Complaint.CATEGORY_ABUSE,
        rating=rating,
    )
    assert result.ok is True
    assert result.complaint is not None
    return result.complaint


@pytest.mark.django_db
def test_hide_and_restore_rating_updates_aggregates_and_public_displays() -> None:
    game = _game()
    alice = _user("alice_voter")
    bob = _user("bob_voter")
    high = _vote(game, alice, 5)
    low = _vote(game, bob, 3)
    aggregate = recalculate(game)
    assert aggregate.count == 2
    assert float(aggregate.average) == 4.0

    moderator = _staff("rating_moderator", StaffRole.MODERATOR)
    client = _client(moderator)
    _elevate(client)

    hidden = client.post(
        reverse("crm:rating_hide", args=[high.id]),
        {"reason": "Накрутка голосов"},
    )
    assert hidden.status_code == 302

    high.refresh_from_db()
    assert high.is_valid is False
    assert high.moderated_by_id == moderator.id
    assert high.reason == "Накрутка голосов"
    assert high.moderated_at is not None
    # The underlying vote row is preserved, only its visibility changed.
    assert GameRatingVote.objects.filter(pk=high.id).exists()

    aggregate.refresh_from_db()
    assert aggregate.count == 1
    assert float(aggregate.average) == 3.0
    assert aggregate.distribution["5"] == 0
    assert aggregate.distribution["3"] == 1

    card_page = client.get(reverse("catalog:game_list"))
    card_body = card_page.content.decode()
    assert 'data-testid="card-rating-average">3.00' in card_body
    detail_page = client.get(reverse("catalog:game_detail", args=[game.slug]))
    detail_body = detail_page.content.decode()
    assert 'data-testid="rating-average">3.00' in detail_body
    assert 'data-testid="rating-count">1' in detail_body

    hidden_audit = AdminAuditLog.objects.get(action=AdminAuditLog.ACTION_RATING_HIDDEN)
    assert hidden_audit.actor_id == moderator.id
    assert hidden_audit.object_type == "rating"
    assert hidden_audit.object_id == high.id
    assert hidden_audit.reason == "Накрутка голосов"
    assert hidden_audit.before_data is not None
    assert hidden_audit.before_data["is_valid"] is True
    assert hidden_audit.after_data is not None
    assert hidden_audit.after_data["is_valid"] is False

    restored = client.post(
        reverse("crm:rating_restore", args=[high.id]),
        {"reason": "Апелляция удовлетворена"},
    )
    assert restored.status_code == 302
    high.refresh_from_db()
    assert high.is_valid is True
    assert high.reason == "Апелляция удовлетворена"
    aggregate.refresh_from_db()
    assert aggregate.count == 2
    assert float(aggregate.average) == 4.0
    assert AdminAuditLog.objects.filter(
        action=AdminAuditLog.ACTION_RATING_RESTORED,
        object_id=high.id,
        actor_id=moderator.id,
    ).exists()
    assert low.is_valid is True


@pytest.mark.django_db
def test_rating_moderation_requires_role_reason_and_step_up() -> None:
    game = _game("step_up_game")
    voter = _user("step_up_voter")
    vote = _vote(game, voter, 4)
    recalculate(game)

    editor = _staff("editor_actor", StaffRole.EDITOR)
    editor_client = _client(editor)
    _elevate(editor_client)
    denied = editor_client.post(
        reverse("crm:rating_hide", args=[vote.id]),
        {"reason": "Нельзя"},
    )
    assert denied.status_code == 403
    vote.refresh_from_db()
    assert vote.is_valid is True
    assert AdminAuditLog.objects.count() == 0

    observer = _staff("observer_actor", StaffRole.OBSERVER)
    observer_client = _client(observer)
    _elevate(observer_client)
    assert (
        observer_client.post(
            reverse("crm:rating_hide", args=[vote.id]),
            {"reason": "Нельзя"},
        ).status_code
        == 403
    )

    moderator = _staff("no_step_up_moderator", StaffRole.MODERATOR)
    client = _client(moderator)

    no_step_up = client.post(
        reverse("crm:rating_hide", args=[vote.id]),
        {"reason": "Нет подтверждения"},
    )
    assert no_step_up.status_code == 302
    assert no_step_up.url.startswith(reverse("crm:step_up"))
    vote.refresh_from_db()
    assert vote.is_valid is True
    assert AdminAuditLog.objects.count() == 0

    wrong_credentials = client.post(
        reverse("crm:rating_hide", args=[vote.id]),
        {"reason": "Неверные данные", "password": "wrong", "totp_code": "000000"},
    )
    assert wrong_credentials.status_code == 302
    assert wrong_credentials.url == reverse("crm:moderation")
    vote.refresh_from_db()
    assert vote.is_valid is True
    assert AdminAuditLog.objects.count() == 0

    secret = pyotp.random_base32()
    User.objects.filter(pk=moderator.pk).update(totp_secret=secret)
    moderator.refresh_from_db()
    confirmed = client.post(
        reverse("crm:rating_hide", args=[vote.id]),
        {
            "reason": "Подтверждённое решение",
            "password": PASSWORD,
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert confirmed.status_code == 302
    vote.refresh_from_db()
    assert vote.is_valid is False
    assert AdminAuditLog.objects.filter(action=AdminAuditLog.ACTION_RATING_HIDDEN).count() == 1


@pytest.mark.django_db
def test_missing_reason_or_repeat_decision_does_not_change_state() -> None:
    game = _game("reason_game")
    voter = _user("reason_voter")
    vote = _vote(game, voter, 5)
    recalculate(game)
    moderator = _staff("reason_moderator", StaffRole.MODERATOR)
    client = _client(moderator)
    _elevate(client)

    missing = client.post(reverse("crm:rating_hide", args=[vote.id]), {"reason": "  "})
    assert missing.status_code == 302
    vote.refresh_from_db()
    assert vote.is_valid is True
    assert AdminAuditLog.objects.count() == 0

    assert (
        client.post(
            reverse("crm:rating_hide", args=[vote.id]),
            {"reason": "Причина"},
        ).status_code
        == 302
    )
    assert AdminAuditLog.objects.count() == 1

    repeat = client.post(
        reverse("crm:rating_hide", args=[vote.id]),
        {"reason": "Повтор"},
    )
    assert repeat.status_code == 302
    vote.refresh_from_db()
    assert vote.is_valid is False
    assert AdminAuditLog.objects.count() == 1


@pytest.mark.django_db
def test_moderation_service_denies_non_moderators_without_side_effects() -> None:
    game = _game("service_denied_game")
    vote = _vote(game, _user("service_voter"), 4)
    editor = _staff("service_editor", StaffRole.EDITOR)
    observer = _staff("service_observer", StaffRole.OBSERVER)
    complaint = _complaint(game, _user("service_reporter"))

    hide = set_rating_visibility(
        actor=editor,
        vote_id=vote.id,
        visible=False,
        reason="Недостаточно прав",
    )
    assert hide.ok is False
    assert hide.reason == "forbidden"
    vote.refresh_from_db()
    assert vote.is_valid is True

    assign = assign_complaint(actor=observer, complaint_id=complaint.id)
    assert assign.ok is False
    assert assign.reason == "forbidden"
    close = resolve_complaint(
        actor=editor,
        complaint_id=complaint.id,
        resolution="Недостаточно прав",
    )
    assert close.ok is False
    assert close.reason == "forbidden"
    complaint.refresh_from_db()
    assert complaint.status == Complaint.STATUS_NEW
    assert AdminAuditLog.objects.count() == 0


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_public_report_intake_records_subject_reporter_and_target() -> None:
    game = _game("report_game")
    reporter = _user("report_reporter")
    vote = _vote(game, reporter, 2)
    client = _client(reporter)
    token = _csrf(client)

    game_report = client.post(
        "/api/v1/reports",
        data=json.dumps(
            {
                "game_id": game.technical_id,
                "category": Complaint.CATEGORY_ABUSE,
                "subject": "Оскорбительное описание",
            }
        ),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert game_report.status_code == 201
    payload = game_report.json()
    assert payload["status"] == Complaint.STATUS_NEW
    stored = Complaint.objects.get(pk=payload["id"])
    assert stored.target_type == Complaint.TARGET_GAME
    assert stored.game_id == game.pk
    assert stored.rating_id is None
    assert stored.reporter_id == reporter.id
    assert stored.subject == "Оскорбительное описание"
    assert stored.category == Complaint.CATEGORY_ABUSE
    assert stored.resolution == ""

    rating_report = client.post(
        "/api/v1/reports",
        data=json.dumps(
            {
                "game_id": game.technical_id,
                "rating_id": str(vote.id),
                "category": Complaint.CATEGORY_INCORRECT,
                "subject": "Некорректная оценка",
            }
        ),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert rating_report.status_code == 201
    rating_complaint = Complaint.objects.get(pk=rating_report.json()["id"])
    assert rating_complaint.target_type == Complaint.TARGET_RATING
    assert rating_complaint.rating_id == vote.id
    assert rating_complaint.game_id == game.pk

    guest = Client()
    guest_token = _csrf(guest)
    anonymous_report = guest.post(
        "/api/v1/reports",
        data=json.dumps(
            {
                "game_id": game.technical_id,
                "category": Complaint.CATEGORY_SPAM,
                "subject": "Спам",
            }
        ),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=guest_token,
    )
    assert anonymous_report.status_code == 201
    anonymous = Complaint.objects.get(pk=anonymous_report.json()["id"])
    assert anonymous.reporter_id is None

    unknown = client.post(
        "/api/v1/reports",
        data=json.dumps(
            {
                "game_id": "missing_game",
                "category": Complaint.CATEGORY_OTHER,
                "subject": "Нет игры",
            }
        ),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert unknown.status_code == 400
    assert unknown.json()["code"] == "E_INVALID_REQUEST"


@pytest.mark.django_db
def test_rating_queue_filters_and_summary() -> None:
    first = _game("filter_game_one")
    second = _game("filter_game_two")
    voters = [_user(f"filter_voter_{index}") for index in range(4)]
    five = _vote(first, voters[0], 5)
    three = _vote(first, voters[1], 3)
    _vote(first, voters[2], 4)
    _vote(second, voters[3], 2)
    GameRatingVote.objects.filter(pk=three.pk).update(is_valid=False)

    moderator = _staff("filter_moderator", StaffRole.MODERATOR)
    client = _client(moderator)

    response = client.get(reverse("crm:moderation"))
    assert response.status_code == 200
    summary = response.context["rating_summary"]
    assert summary.count == 4
    assert summary.average == pytest.approx(3.5)
    assert summary.distribution == {1: 0, 2: 1, 3: 1, 4: 1, 5: 1}
    body = response.content.decode()
    assert 'data-testid="crm-moderation-rating-average">3.50' in body
    assert 'data-testid="crm-moderation-rating-count">4' in body
    assert 'data-testid="crm-moderation-distribution-2">1' in body
    assert 'data-testid="crm-moderation-distribution-5">1' in body
    assert body.count('data-testid="crm-moderation-vote"') == 4

    by_game = client.get(reverse("crm:moderation"), {"game": "filter_game_one"})
    game_summary = by_game.context["rating_summary"]
    assert game_summary.count == 3
    assert game_summary.average == pytest.approx(4.0)
    assert game_summary.distribution == {1: 0, 2: 0, 3: 1, 4: 1, 5: 1}

    by_value = client.get(reverse("crm:moderation"), {"value": "5"})
    value_summary = by_value.context["rating_summary"]
    assert value_summary.count == 1
    assert value_summary.average == pytest.approx(5.0)
    assert value_summary.distribution == {1: 0, 2: 0, 3: 0, 4: 0, 5: 1}
    assert list(by_value.context["votes"]) == [five]

    hidden = client.get(reverse("crm:moderation"), {"status": "hidden"})
    hidden_summary = hidden.context["rating_summary"]
    assert hidden_summary.count == 1
    assert hidden_summary.average == pytest.approx(3.0)
    assert list(hidden.context["votes"]) == [three]

    valid = client.get(reverse("crm:moderation"), {"status": "valid"})
    valid_summary = valid.context["rating_summary"]
    assert valid_summary.count == 3
    assert valid_summary.average == pytest.approx(11 / 3)

    combined = client.get(
        reverse("crm:moderation"),
        {"game": "filter_game_one", "value": "3", "status": "hidden"},
    )
    combined_summary = combined.context["rating_summary"]
    assert combined_summary.count == 1
    assert list(combined.context["votes"]) == [three]

    ignored = client.get(reverse("crm:moderation"), {"value": "9", "status": "unknown"})
    assert ignored.context["rating_filters"].value is None
    assert ignored.context["rating_filters"].status == ""
    assert ignored.context["rating_summary"].count == 4


@pytest.mark.django_db
def test_moderation_queues_paginate_while_summary_stays_complete() -> None:
    game = _game("pagination_game")
    voters = [User.objects.create_user(login=f"pagination_voter_{index}") for index in range(120)]
    GameRatingVote.objects.bulk_create(
        [
            GameRatingVote(
                game=game,
                user=voter,
                value=(index % 5) + 1,
                changed_at=timezone.now(),
                change_window_started_at=timezone.now(),
            )
            for index, voter in enumerate(voters)
        ],
        batch_size=60,
    )
    Complaint.objects.bulk_create(
        [
            Complaint(
                game=game,
                category=Complaint.CATEGORY_ABUSE,
                subject=f"Жалоба {index}",
                status=Complaint.STATUS_NEW,
            )
            for index in range(120)
        ],
        batch_size=60,
    )
    moderator = _staff("pagination_moderator", StaffRole.MODERATOR)
    client = _client(moderator)

    first = client.get(reverse("crm:moderation"))
    assert first.status_code == 200
    assert first.context["rating_page_obj"].number == 1
    assert len(first.context["votes"]) == 50
    assert first.content.decode().count('data-testid="crm-moderation-vote"') == 50
    # The summary covers all 120 filtered votes, not just the first page.
    assert first.context["rating_summary"].count == 120
    assert first.context["rating_summary"].average == pytest.approx(3.0)
    assert sum(first.context["rating_summary"].distribution.values()) == 120

    second = client.get(reverse("crm:moderation"), {"ratings_page": "2"})
    assert second.status_code == 200
    assert second.context["rating_page_obj"].number == 2
    assert len(second.context["votes"]) == 50
    assert second.content.decode().count('data-testid="crm-moderation-vote"') == 50
    assert second.context["rating_summary"].count == 120
    assert second.context["rating_summary"].average == pytest.approx(3.0)
    expected_votes = list(
        GameRatingVote.objects.filter(game=game).order_by("-created_at", "-id")[50:100]
    )
    assert [vote.id for vote in second.context["votes"]] == [vote.id for vote in expected_votes]

    # A bare page parameter advances both queues together.
    both = client.get(reverse("crm:moderation"), {"page": "2"})
    assert both.context["rating_page_obj"].number == 2
    assert both.context["complaints_page_obj"].number == 2

    # Game/status filters survive pagination navigation.
    filtered = client.get(
        reverse("crm:moderation"),
        {"game": "pagination_game", "status": "valid", "ratings_page": "2"},
    )
    assert filtered.status_code == 200
    filtered_body = filtered.content.decode()
    assert filtered.context["rating_filters"].game == "pagination_game"
    assert filtered.context["rating_filters"].status == "valid"
    assert "game=pagination_game" in filtered_body
    assert "status=valid" in filtered_body
    assert "ratings_page=1" in filtered_body
    assert filtered.context["rating_summary"].count == 120

    # Complaint ordering is stable across the page boundary.
    page_one_complaints = client.get(reverse("crm:moderation"))
    assert page_one_complaints.context["complaints_page_obj"].number == 1
    assert len(page_one_complaints.context["complaints"]) == 50
    page_two_complaints = client.get(
        reverse("crm:moderation"),
        {"complaints_page": "2"},
    )
    assert page_two_complaints.status_code == 200
    assert page_two_complaints.context["complaints_page_obj"].number == 2
    assert len(page_two_complaints.context["complaints"]) == 50
    assert (
        page_two_complaints.content.decode().count('data-testid="crm-moderation-complaint"') == 50
    )
    expected_complaints = list(Complaint.objects.order_by("-created_at", "-id")[50:100])
    assert [item.id for item in page_two_complaints.context["complaints"]] == [
        item.id for item in expected_complaints
    ]
    assert "complaints_page=1" in page_two_complaints.content.decode()


@pytest.mark.django_db
def test_rating_queue_summary_queries_do_not_scale_with_votes() -> None:
    game = _game("scale_game")
    moderator = _staff("scale_moderator", StaffRole.MODERATOR)
    client = _client(moderator)
    for index in range(2):
        _vote(game, _user(f"scale_voter_{index}"), (index % 5) + 1)

    # Warm one-time caches (languages, permissions) before measuring.
    assert client.get(reverse("crm:moderation")).status_code == 200

    with CaptureQueriesContext(connection) as few_votes:
        assert client.get(reverse("crm:moderation")).status_code == 200

    for index in range(2, 12):
        _vote(game, _user(f"scale_voter_{index}"), (index % 5) + 1)

    with CaptureQueriesContext(connection) as many_votes:
        assert client.get(reverse("crm:moderation")).status_code == 200

    assert len(many_votes.captured_queries) == len(few_votes.captured_queries)


@pytest.mark.django_db
def test_rating_visibility_filters_reflect_hide_and_restore() -> None:
    game = _game("visibility_filter_game")
    vote = _vote(game, _user("visibility_filter_voter"), 4)
    recalculate(game)
    moderator = _staff("visibility_filter_moderator", StaffRole.MODERATOR)
    client = _client(moderator)
    _elevate(client)

    hidden = client.post(reverse("crm:rating_hide", args=[vote.id]), {"reason": "Нарушение"})
    assert hidden.status_code == 302
    hidden_queue = client.get(reverse("crm:moderation"), {"status": "hidden"})
    assert hidden_queue.context["rating_summary"].count == 1
    assert hidden_queue.context["rating_summary"].average == pytest.approx(4.0)
    assert list(hidden_queue.context["votes"]) == [vote]
    assert AdminAuditLog.objects.filter(
        action=AdminAuditLog.ACTION_RATING_HIDDEN,
        object_id=vote.id,
    ).exists()

    valid_before = client.get(reverse("crm:moderation"), {"status": "valid"})
    assert valid_before.context["rating_summary"].count == 0

    restored = client.post(
        reverse("crm:rating_restore", args=[vote.id]),
        {"reason": "Апелляция удовлетворена"},
    )
    assert restored.status_code == 302
    valid_after = client.get(reverse("crm:moderation"), {"status": "valid"})
    assert valid_after.context["rating_summary"].count == 1
    assert list(valid_after.context["votes"]) == [vote]
    assert AdminAuditLog.objects.filter(
        action=AdminAuditLog.ACTION_RATING_RESTORED,
        object_id=vote.id,
    ).exists()


@pytest.mark.django_db
def test_complaint_queue_assign_resolve_reject_with_audit() -> None:
    game = _game("complaint_game")
    reporter = _user("complaint_reporter")
    moderator = _staff("complaint_moderator", StaffRole.MODERATOR)
    second = _staff("complaint_second", StaffRole.MODERATOR)
    editor = _staff("complaint_editor", StaffRole.EDITOR)
    first = _complaint(game, reporter)
    second_complaint = _complaint(game, reporter, subject="Спам в описании")
    client = _client(moderator)
    _elevate(client)

    queue = client.get(reverse("crm:complaints"))
    assert queue.status_code == 200
    queue_body = queue.content.decode()
    assert "Накрутка оценок" in queue_body
    assert "Спам в описании" in queue_body
    assert "Жалобы" in queue_body

    assigned = client.post(
        reverse("crm:complaint_assign", args=[first.id]),
        {"assignee_id": str(second.id)},
    )
    assert assigned.status_code == 302
    first.refresh_from_db()
    assert first.status == Complaint.STATUS_ASSIGNED
    assert first.assigned_to_id == second.id
    assigned_audit = AdminAuditLog.objects.get(action=AdminAuditLog.ACTION_COMPLAINT_ASSIGNED)
    assert assigned_audit.actor_id == moderator.id
    assert assigned_audit.object_type == "complaint"
    assert assigned_audit.object_id == first.id
    assert assigned_audit.before_data["status"] == Complaint.STATUS_NEW
    assert assigned_audit.after_data["status"] == Complaint.STATUS_ASSIGNED
    assert assigned_audit.after_data["assigned_to_id"] == str(second.id)

    invalid_assignee = client.post(
        reverse("crm:complaint_assign", args=[second_complaint.id]),
        {"assignee_id": str(editor.id)},
    )
    assert invalid_assignee.status_code == 302
    second_complaint.refresh_from_db()
    assert second_complaint.status == Complaint.STATUS_NEW
    assert AdminAuditLog.objects.filter(action=AdminAuditLog.ACTION_COMPLAINT_ASSIGNED).count() == 1

    resolved = client.post(
        reverse("crm:complaint_resolve", args=[first.id]),
        {"resolution": "Оценка скрыта, нарушение подтверждено"},
    )
    assert resolved.status_code == 302
    first.refresh_from_db()
    assert first.status == Complaint.STATUS_RESOLVED
    assert first.resolution == "Оценка скрыта, нарушение подтверждено"
    assert first.resolved_at is not None
    resolved_audit = AdminAuditLog.objects.get(action=AdminAuditLog.ACTION_COMPLAINT_RESOLVED)
    assert resolved_audit.actor_id == moderator.id
    assert resolved_audit.object_id == first.id
    assert resolved_audit.reason == "Оценка скрыта, нарушение подтверждено"

    rejected = client.post(
        reverse("crm:complaint_reject", args=[second_complaint.id]),
        {"resolution": "Нарушений не найдено"},
    )
    assert rejected.status_code == 302
    second_complaint.refresh_from_db()
    assert second_complaint.status == Complaint.STATUS_REJECTED
    assert second_complaint.resolution == "Нарушений не найдено"
    rejected_audit = AdminAuditLog.objects.get(action=AdminAuditLog.ACTION_COMPLAINT_REJECTED)
    assert rejected_audit.actor_id == moderator.id
    assert rejected_audit.object_id == second_complaint.id

    audit_count = AdminAuditLog.objects.count()
    repeat = client.post(
        reverse("crm:complaint_resolve", args=[first.id]),
        {"resolution": "Повторное решение"},
    )
    assert repeat.status_code == 302
    first.refresh_from_db()
    assert first.status == Complaint.STATUS_RESOLVED
    assert first.resolution == "Оценка скрыта, нарушение подтверждено"
    assert AdminAuditLog.objects.count() == audit_count

    no_resolution = client.post(
        reverse("crm:complaint_resolve", args=[_complaint(game, reporter).id]),
        {"resolution": "   "},
    )
    assert no_resolution.status_code == 302
    assert AdminAuditLog.objects.count() == audit_count


@pytest.mark.django_db
def test_complaint_decisions_require_role_and_step_up() -> None:
    game = _game("complaint_denied_game")
    reporter = _user("complaint_denied_reporter")
    complaint = _complaint(game, reporter)
    editor = _staff("complaint_denied_editor", StaffRole.EDITOR)
    editor_client = _client(editor)
    _elevate(editor_client)

    denied = editor_client.post(
        reverse("crm:complaint_resolve", args=[complaint.id]),
        {"resolution": "Нельзя"},
    )
    assert denied.status_code == 403
    complaint.refresh_from_db()
    assert complaint.status == Complaint.STATUS_NEW
    assert AdminAuditLog.objects.count() == 0

    moderator = _staff("complaint_denied_moderator", StaffRole.MODERATOR)
    client = _client(moderator)
    no_step_up = client.post(
        reverse("crm:complaint_resolve", args=[complaint.id]),
        {"resolution": "Без подтверждения"},
    )
    assert no_step_up.status_code == 302
    assert no_step_up.url.startswith(reverse("crm:step_up"))
    complaint.refresh_from_db()
    assert complaint.status == Complaint.STATUS_NEW
    assert AdminAuditLog.objects.count() == 0

    owner = _staff("complaint_owner", StaffRole.OWNER)
    owner_client = _client(owner)
    _elevate(owner_client)
    owner_resolved = owner_client.post(
        reverse("crm:complaint_resolve", args=[complaint.id]),
        {"resolution": "Владелец подтвердил"},
    )
    assert owner_resolved.status_code == 302
    complaint.refresh_from_db()
    assert complaint.status == Complaint.STATUS_RESOLVED
    assert complaint.resolution == "Владелец подтвердил"


@pytest.mark.django_db
def test_rating_decision_rejects_cross_site_post_without_csrf_token() -> None:
    game = _game("csrf_game")
    vote = _vote(game, _user("csrf_voter"), 1)
    recalculate(game)
    moderator = _staff("csrf_moderator", StaffRole.MODERATOR)
    client = Client(enforce_csrf_checks=True)
    client.force_login(moderator)
    session = client.session
    session["ba_2fa_verified"] = True
    session["crm_step_up_at"] = timezone.now().isoformat()
    session.save()

    response = client.post(
        reverse("crm:rating_hide", args=[vote.id]),
        {"reason": "Без CSRF"},
    )
    assert response.status_code == 403
    vote.refresh_from_db()
    assert vote.is_valid is True
    assert AdminAuditLog.objects.count() == 0


@pytest.mark.django_db
def test_complaint_close_requires_resolution_at_service_level() -> None:
    game = _game("service_resolution_game")
    complaint = _complaint(game, _user("resolution_reporter"))
    moderator = _staff("resolution_moderator", StaffRole.MODERATOR)

    empty = resolve_complaint(
        actor=moderator,
        complaint_id=complaint.id,
        resolution="   ",
    )
    assert empty.ok is False
    assert empty.reason == "resolution_required"
    complaint.refresh_from_db()
    assert complaint.status == Complaint.STATUS_NEW
    assert AdminAuditLog.objects.count() == 0

    rejected = reject_complaint(
        actor=moderator,
        complaint_id=complaint.id,
        resolution="Не подтверждено",
    )
    assert rejected.ok is True
    complaint.refresh_from_db()
    assert complaint.status == Complaint.STATUS_REJECTED
    assert GameRatingAggregate.objects.filter(game=game).exists() is False
