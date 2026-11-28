"""Интеграционные проверки публичной языковой оболочки BA-STAGE-1.1."""

from __future__ import annotations

import re
from typing import Any

import pytest
from django.template import Context, Template
from django.test import Client, RequestFactory

from apps.i18n.models import Language, TranslationEntry
from apps.i18n.templatetags.portal_urls import language_url
from apps.i18n.views import root_redirect

SUPPORTED_LANGUAGES = ("en", "de", "nl", "ru", "fr", "es")


def _content(response: Any) -> str:
    return str(response.content.decode())


def _language_menu(content: str) -> str:
    start = content.index('id="lang-menu"')
    return content[start : content.index("</div>", start)]


@pytest.mark.django_db
@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_portal_shell_is_available_in_all_six_languages(anon_client: Client, language: str) -> None:
    response = anon_client.get(f"/{language}/")

    assert response.status_code == 200
    assert f'<html lang="{language}"' in _content(response)


@pytest.mark.django_db
@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_content_language_matches_url_language(anon_client: Client, language: str) -> None:
    response = anon_client.get(f"/{language}/")

    assert response.status_code == 200
    assert response["Content-Language"] == language


@pytest.mark.django_db
def test_content_language_does_not_leak_between_requests(anon_client: Client) -> None:
    for language in SUPPORTED_LANGUAGES:
        response = anon_client.get(f"/{language}/")
        assert response.status_code == 200
        assert response["Content-Language"] == language

    response = anon_client.get("/healthz")

    assert response.status_code == 200
    assert response["Content-Language"] == "en"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("de", "/de/"),
        ("de-AT", "/de/"),
        ("de-AT,de;q=0.9,en;q=0.8", "/de/"),
        ("en-US,en;q=0.9", "/en/"),
        ("nl-BE,nl;q=0.9,fr;q=0.8", "/nl/"),
        ("ru-RU", "/ru/"),
        ("fr-CH, fr;q=0.9, de;q=0.8", "/fr/"),
        ("es;q=0.5, de;q=0.9", "/de/"),
        ("xx;q=1.0, de;q=0.1", "/de/"),
        ("it;q=1.0", "/en/"),
        ("de;q=0.1, *;q=0.9", "/en/"),
        ("fr;q=0.1, *;q=0.9", "/en/"),
        ("de;q=0.9, *;q=0.5", "/de/"),
        ("en-US;q=0.9", "/en/"),
        ("*;q=0.5, de;q=0.9", "/de/"),
        ("*;q=0, de;q=0.9", "/de/"),
        ("en;q=0, *;q=0.5", "/de/"),
        ("de;q=0, *;q=0.5", "/en/"),
        ("en;q=0, de;q=0.9", "/de/"),
        ("de;q=0, fr;q=0.9", "/fr/"),
        ("de;q=0.5, fr;q=0.5", "/de/"),
        ("fr;q=0.5, de;q=0.5", "/fr/"),
        ("de;q=0", "/en/"),
        ("xx", "/en/"),
        ("*", "/en/"),
        ("", "/en/"),
        (";;;", "/en/"),
        ("de;q=0.9, ;;, fr;q=0.8", "/de/"),
        (";;, fr;q=0.8", "/fr/"),
        ("de;q=0.9, fr;q=abc", "/de/"),
    ],
)
def test_root_redirect_selects_language_from_accept_language(
    anon_client: Client, header: str, expected: str
) -> None:
    response = anon_client.get("/", HTTP_ACCEPT_LANGUAGE=header)

    assert response.status_code == 302
    assert response["Location"] == expected
    assert "Accept-Language" in response["Vary"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "header",
    [
        "*;q=0",
        "en;q=0",
        "en-US;q=0",
        "en;q=0, de;q=0, nl;q=0, ru;q=0, fr;q=0, es;q=0",
        "en;q=0, de;q=0",
    ],
)
def test_root_redirect_returns_406_when_no_acceptable_language(
    anon_client: Client, header: str
) -> None:
    response = anon_client.get("/", HTTP_ACCEPT_LANGUAGE=header)

    assert response.status_code == 406
    assert "Location" not in response
    assert "Accept-Language" in response["Vary"]


@pytest.mark.django_db
def test_root_redirect_without_header_falls_back_to_english(anon_client: Client) -> None:
    response = anon_client.get("/")

    assert response.status_code == 302
    assert response["Location"] == "/en/"
    assert "Accept-Language" in response["Vary"]


@pytest.mark.django_db
def test_root_redirect_does_not_loop(anon_client: Client) -> None:
    response = anon_client.get("/", HTTP_ACCEPT_LANGUAGE="de")

    assert response.status_code == 302
    target = response["Location"]
    assert target == "/de/"
    assert anon_client.get(target).status_code == 200


@pytest.mark.django_db
def test_language_switcher_preserves_nested_path_and_query(anon_client: Client) -> None:
    response = anon_client.get("/de/games/?page=2&sort=new")

    assert response.status_code == 200
    assert 'href="/fr/games/?page=2&amp;sort=new"' in _content(response)


@pytest.mark.django_db
def test_language_switcher_works_on_language_root(anon_client: Client) -> None:
    response = anon_client.get("/de/")

    assert response.status_code == 200
    menu = _language_menu(_content(response))
    assert 'href="/fr/"' in menu
    assert 'href="/de/"' in menu


@pytest.mark.django_db
def test_language_switcher_builds_only_local_active_language_links(anon_client: Client) -> None:
    response = anon_client.get("/de/games/?page=2")
    menu = _language_menu(_content(response))
    links = re.findall(r'href="([^"]+)"', menu)

    assert links
    assert all(link.startswith("/") for link in links)
    assert all("//" not in link for link in links)
    assert all(link.split("/")[1] in SUPPORTED_LANGUAGES for link in links)


@pytest.mark.django_db
def test_unknown_language_prefix_is_404(anon_client: Client) -> None:
    response = anon_client.get("/xx/games/?page=2")

    assert response.status_code == 404
    assert b'id="lang-menu"' not in response.content


@pytest.mark.django_db
def test_known_language_404_keeps_localized_shell(anon_client: Client) -> None:
    response = anon_client.get("/en/games/does-not-exist/")

    content = _content(response)
    assert response.status_code == 404
    assert 'id="lang-menu"' in content
    assert "Page not found" in content
    assert "The page you requested does not exist or was moved." in content
    assert '<a href="/en/" class="btn btn-primary">' in content


@pytest.mark.django_db
def test_language_switcher_does_not_preserve_unknown_prefix() -> None:
    request = RequestFactory().get("/xx/games/?page=2")

    assert language_url({"request": request}, "fr") == ""


@pytest.mark.django_db
def test_language_switcher_rejects_external_language_code() -> None:
    request = RequestFactory().get("/de/games/?page=2")

    assert language_url({"request": request}, "https://evil.example") == ""


@pytest.mark.django_db
def test_language_switcher_rejects_protocol_relative_path() -> None:
    request = RequestFactory().get("//evil.example/x")

    assert language_url({"request": request}, "fr") == ""


@pytest.mark.django_db
def test_language_switcher_uses_page_specific_localized_path() -> None:
    request = RequestFactory().get("/de/genres/shared/?sort=old")

    assert (
        language_url(
            {
                "request": request,
                "language_paths": {"fr": "/fr/genres/autre/?sort=old"},
            },
            "fr",
        )
        == "/fr/genres/autre/?sort=old"
    )


@pytest.mark.django_db
def test_language_switcher_ignores_non_local_page_specific_path() -> None:
    request = RequestFactory().get("/de/genres/shared/?sort=old")

    assert (
        language_url(
            {
                "request": request,
                "language_paths": {"fr": "https://evil.example/fr/"},
            },
            "fr",
        )
        == "/fr/genres/shared/?sort=old"
    )
    assert (
        language_url(
            {
                "request": request,
                "language_paths": {"fr": "//evil.example/fr/"},
            },
            "fr",
        )
        == "/fr/genres/shared/?sort=old"
    )


@pytest.mark.django_db
def test_public_language_route_returns_503_when_en_is_inactive(anon_client: Client) -> None:
    try:
        Language.objects.filter(code="en").update(is_active=False)

        response = anon_client.get("/de/")

        assert response.status_code == 503
        assert "Accept-Language" in response["Vary"]
        assert anon_client.get("/healthz").status_code == 200
    finally:
        Language.objects.filter(code="en").update(is_active=True)


@pytest.mark.django_db
def test_root_redirect_returns_503_when_en_is_inactive() -> None:
    try:
        Language.objects.filter(code="en").update(is_active=False)

        response = root_redirect(RequestFactory().get("/"))

        assert response.status_code == 503
        assert "Accept-Language" in response["Vary"]
    finally:
        Language.objects.filter(code="en").update(is_active=True)


@pytest.mark.django_db
def test_english_fallback_is_rendered_for_untranslated_language(anon_client: Client) -> None:
    value = (
        TranslationEntry.objects.filter(language__code="en", namespace="home", key="hero_title")
        .values_list("value", flat=True)
        .first()
    )

    assert value
    response = anon_client.get("/de/")

    assert response.status_code == 200
    assert value in _content(response)


@pytest.mark.django_db
def test_missing_translation_key_is_not_rendered() -> None:
    request = RequestFactory().get("/de/")
    request.LANGUAGE_CODE = "de"
    rendered = Template('{% load ba_i18n %}{% ba_t "missing.key" %}').render(
        Context({"request": request})
    )

    assert rendered == ""


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path",
    [
        "/de/genres/",
        "/de/legal/terms/",
        "/de/legal/privacy/",
        "/de/legal/cookies/",
        "/de/account/",
    ],
)
def test_portal_does_not_link_to_unimplemented_sections(anon_client: Client, path: str) -> None:
    response = anon_client.get("/de/")

    assert response.status_code == 200
    assert f'href="{path}' not in _content(response)


@pytest.mark.django_db
def test_public_header_links_to_auth_pages(anon_client: Client) -> None:
    content = _content(anon_client.get("/de/"))

    assert 'href="/de/auth/login/"' in content
    assert 'href="/de/auth/register/"' in content
