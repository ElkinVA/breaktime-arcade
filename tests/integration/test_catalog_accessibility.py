"""Accessibility and 360 px structure for the catalog controls (§2.7).

Covers the catalog search/filter/sort controls and the rating widget:
keyboard focus styling, programmatic labels and the single-column mobile
layout contract.  Real browser viewport checks live in ``tests/e2e``.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Game, Genre
from apps.gameplay.models import UserGamePlaytime

INTERACTIVE_TAGS = {"input", "select", "textarea"}
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class ControlCollector(HTMLParser):
    """Collect controls, ``label[for]`` targets and selected element attributes."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.controls: list[tuple[str, dict[str, str], bool]] = []
        self.elements: list[tuple[str, dict[str, str]]] = []
        self.label_targets: set[str] = set()
        self._label_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name: value or "" for name, value in attrs}
        self.elements.append((tag, attributes))
        if tag == "label":
            target = attributes.get("for")
            if target:
                self.label_targets.add(target)
            self._label_depth += 1
        if tag in INTERACTIVE_TAGS:
            self.controls.append((tag, attributes, self._label_depth > 0))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag == "label" and self._label_depth:
            self._label_depth -= 1


def _collect(body: str) -> ControlCollector:
    collector = ControlCollector()
    collector.feed(body)
    return collector


def _game() -> Game:
    genre = Genre.objects.create(code="a11y_puzzle")
    return Game.objects.create(
        technical_id="a11y_game",
        host_label="a11y-game.games.test",
        slug="a11y-game",
        primary_genre=genre,
        status=Game.STATUS_PUBLISHED,
        published_at=timezone.now(),
    )


def _assert_labelled(collector: ControlCollector) -> None:
    visible = [
        (tag, attrs, wrapped)
        for tag, attrs, wrapped in collector.controls
        if attrs.get("type", "").lower() != "hidden"
    ]
    assert visible, "no interactive controls rendered"
    for tag, attrs, wrapped in visible:
        control_id = attrs.get("id", "")
        assert control_id, f"{tag} {attrs.get('name')} has no id"
        has_label = (
            wrapped
            or control_id in collector.label_targets
            or bool(attrs.get("aria-label"))
            or bool(attrs.get("aria-labelledby"))
        )
        assert has_label, f"{tag} {attrs.get('name')} has no accessible label"


def _element(collector: ControlCollector, tag: str, attr: str, value: str) -> dict[str, str]:
    for name, attributes in collector.elements:
        if name == tag and attributes.get(attr) == value:
            return attributes
    raise AssertionError(f"<{tag} {attr}={value!r}> is missing")


@pytest.mark.django_db
def test_catalog_controls_have_labels_and_mobile_single_column_layout() -> None:
    _game()

    response = Client().get("/en/games/")
    body = response.content.decode()
    collector = _collect(body)

    _assert_labelled(collector)

    form = _element(collector, "form", "role", "search")
    assert form.get("aria-labelledby") == "catalog-heading"
    assert "grid-cols-1" in form.get("class", "")
    assert _element(collector, "h1", "id", "catalog-heading")

    results = _element(collector, "div", "id", "game-results")
    assert results.get("aria-live") == "polite"
    assert results.get("aria-labelledby") == "catalog-heading"

    search = _element(collector, "input", "id", "catalog-search")
    assert search.get("name") == "q"
    assert search.get("type") == "search"
    assert "w-full" in search.get("class", "")

    for control in ("catalog-genre", "catalog-duration", "catalog-sort"):
        attrs = _element(collector, "select", "id", control)
        assert "w-full" in attrs.get("class", "")


@pytest.mark.django_db
def test_rating_widget_has_group_label_and_live_status() -> None:
    game = _game()
    user = User.objects.create_user(login="a11y_voter", password="correct horse battery staple")
    UserGamePlaytime.objects.create(user=user, game=game, verified_seconds=120)
    client = Client()
    client.force_login(user)

    response = client.get("/en/games/a11y-game/")
    body = response.content.decode()
    collector = _collect(body)

    _assert_labelled(collector)

    legend = _element(collector, "legend", "id", "rating-vote-legend")
    assert legend.get("id") == "rating-vote-legend"
    radiogroup = _element(collector, "div", "role", "radiogroup")
    assert radiogroup.get("aria-labelledby") == "rating-vote-legend"

    status = _element(collector, "p", "role", "status")
    assert status.get("aria-live") == "polite"
    assert status.get("aria-atomic") == "true"

    radios = [
        attrs
        for tag, attrs, _wrapped in collector.controls
        if tag == "input" and attrs.get("name") == "value"
    ]
    assert len(radios) == 5
    for attrs in radios:
        assert attrs.get("aria-label")

    # The radio itself is visually hidden; the star label must show focus.
    rating_labels = [
        attrs
        for tag, attrs in collector.elements
        if tag == "label" and attrs.get("for", "").startswith("rating-vote-radio-")
    ]
    assert len(rating_labels) == 5
    assert all("focus-within:outline" in attrs.get("class", "") for attrs in rating_labels)


def test_stylesheet_defines_visible_keyboard_focus() -> None:
    css = Path(settings.BASE_DIR, "static", "src", "css", "app.css").read_text(encoding="utf-8")

    assert ":focus-visible" in css
    assert "outline" in css
    assert "var(--ba-accent)" in css
