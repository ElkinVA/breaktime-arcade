"""CRM game card: read-only per-game audit history (§2.16.2)."""

from __future__ import annotations

import re

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StaffRole, User
from apps.catalog.models import Game, Genre
from apps.crm.models import AdminAuditLog
from apps.crm.services.audit import record_audit
from apps.crm.services.game_audit import AUDIT_PAGE_SIZE

PASSWORD = "correct horse battery staple"


def _game(technical_id: str) -> Game:
    genre, _created = Genre.objects.get_or_create(code=f"audit_{technical_id}")
    return Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=f"slug-{technical_id}",
        primary_genre=genre,
        status=Game.STATUS_PUBLISHED,
        published_at=timezone.now(),
    )


def _staff_client() -> tuple[Client, User]:
    staff = User.objects.create_user(
        login="audit_staff",
        password=PASSWORD,
        is_staff=True,
        crm_role=StaffRole.OWNER,
    )
    User.objects.filter(pk=staff.pk).update(totp_confirmed_at=timezone.now())
    client = Client()
    client.force_login(staff)
    session = client.session
    session["ba_2fa_verified"] = True
    session.save()
    return client, staff


def _detail_url(game: Game) -> str:
    return reverse("crm:game_detail", args=[game.id])


def _row_values(content: str, name: str) -> list[str]:
    return re.findall(
        rf'data-testid="crm-audit-{name}"[^>]*>(.*?)</td>',
        content,
        re.S,
    )


@pytest.mark.django_db
def test_game_audit_is_scoped_ordered_and_renders_dates() -> None:
    game = _game("audit_game")
    other = _game("audit_other_game")
    client, staff = _staff_client()

    first = record_audit(
        actor=staff,
        action=AdminAuditLog.ACTION_GAME_PUBLISHED,
        object_type="game",
        object_id=game.id,
        after={"current_version_id": "v1"},
    )
    second = record_audit(
        actor=staff,
        action=AdminAuditLog.ACTION_GAME_ROLLED_BACK,
        object_type="game",
        object_id=game.id,
        after={"current_version_id": "v0"},
    )
    record_audit(
        actor=staff,
        action=AdminAuditLog.ACTION_GAME_PUBLISHED,
        object_type="game",
        object_id=other.id,
    )

    response = client.get(_detail_url(game))

    assert response.status_code == 200
    content = response.content.decode()
    assert 'data-testid="crm-game-audit"' in content
    assert content.count('data-testid="crm-audit-row"') == 2
    actions = _row_values(content, "action")
    assert actions == ["Откат версии", "Публикация версии"]
    assert _row_values(content, "actor") == [staff.login, staff.login]
    dates = _row_values(content, "occurred-at")
    assert dates
    assert all(dates)
    assert dates[0] == timezone.localtime(second.created_at).strftime("%Y-%m-%d %H:%M")
    assert dates[1] == timezone.localtime(first.created_at).strftime("%Y-%m-%d %H:%M")


@pytest.mark.django_db
def test_game_audit_empty_state_and_role_gate() -> None:
    game = _game("audit_empty_game")
    client, _staff = _staff_client()

    response = client.get(_detail_url(game))
    assert response.status_code == 200
    content = response.content.decode()
    assert 'data-testid="crm-game-audit"' in content
    assert 'data-testid="crm-audit-empty"' in content
    assert "История изменений этой игры пока пуста." in content

    anonymous = Client().get(_detail_url(game))
    assert anonymous.status_code == 302
    assert "/crm/login/" in anonymous["Location"] or "/en/auth/login/" in anonymous["Location"]


@pytest.mark.django_db
def test_game_audit_pagination_is_bounded_and_uses_audit_page() -> None:
    game = _game("audit_paged_game")
    client, staff = _staff_client()
    for index in range(AUDIT_PAGE_SIZE + 1):
        AdminAuditLog.objects.create(
            actor=staff,
            action=AdminAuditLog.ACTION_GAME_PUBLISHED,
            object_type="game",
            object_id=game.id,
            after_data={"index": index},
        )

    first = client.get(_detail_url(game))
    assert first.status_code == 200
    assert first.context["audit"].page_obj.paginator.count == AUDIT_PAGE_SIZE + 1
    assert first.context["audit"].page_obj.paginator.num_pages == 2
    assert len(_row_values(first.content.decode(), "action")) == AUDIT_PAGE_SIZE

    second = client.get(_detail_url(game), {"audit_page": 2})
    assert second.status_code == 200
    assert len(_row_values(second.content.decode(), "action")) == 1

    beyond = client.get(_detail_url(game), {"audit_page": 999})
    assert beyond.status_code == 200
    assert len(_row_values(beyond.content.decode(), "action")) == 1
