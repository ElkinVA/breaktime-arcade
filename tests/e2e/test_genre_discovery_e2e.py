"""Full browser journey through the public genre discovery path.

The fixture creates its own disposable genre, game, version and static runtime
through ``manage.py shell`` in the live dev stack. It never depends on a random
existing catalog row. Teardown removes its runtime and mutable rows; the Game
row is archived because PostgreSQL permanently forbids physical deletes.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright

BASE_URL = os.environ.get("BA_E2E_BASE_URL", "https://portal.test:8443").rstrip("/")
ROOT = Path(__file__).resolve().parents[2]
SEED_MARKER = "GENRE_DISCOVERY_E2E_SEED="

pytestmark = pytest.mark.e2e

if os.environ.get("BA_E2E") != "1":
    pytest.skip(
        "BA_E2E не включён; задайте BA_E2E=1 и BA_E2E_BASE_URL",
        allow_module_level=True,
    )


def _compose_shell(script: str) -> subprocess.CompletedProcess[str]:
    docker = shutil.which("docker")
    assert docker is not None, "docker is required for the genre discovery E2E fixture"
    completed = subprocess.run(  # noqa: S603 - fixed local dev stack fixture
        [
            docker,
            "compose",
            "-f",
            "compose.yml",
            "-f",
            "compose.dev-lite.yml",
            "exec",
            "-T",
            "web",
            "python",
            "manage.py",
            "shell",
            "-c",
            script,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"Genre discovery E2E shell failed ({completed.returncode}):\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed


def _seed_discovery_fixture() -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    technical_id = f"e2ediscovery{suffix}"
    host_label = f"e2e-discovery-{suffix}"
    game_slug = f"e2e-discovery-game-{suffix}"
    genre_code = f"e2ediscovery{suffix}"
    genre_slug_en = f"e2e-discovery-en-{suffix}"
    genre_slug_ru = f"e2e-otkrytie-{suffix}"
    genre_name_en = f"E2E Discovery {suffix}"
    genre_name_ru = f"E2E Открытие {suffix}"
    game_name_en = f"E2E Discovery Game {suffix}"
    game_name_ru = f"E2E Игра {suffix}"
    game_slug_ru = f"e2e-igra-{suffix}"
    runtime_marker = f"Runtime {suffix} loaded"
    runtime_files = {
        "index.html": (
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            "<title>E2E runtime</title></head><body>"
            f'<p id="runtime-proof" data-testid="runtime-proof">{runtime_marker}</p>'
            '<script src="js/proof.js"></script></body></html>'
        ).encode(),
        "js/proof.js": b"document.documentElement.dataset.runtimeScript = 'executed';\n",
    }

    seed_lines = [
        "import hashlib",
        "import json",
        "from pathlib import Path",
        "from django.conf import settings",
        "from django.utils import timezone",
        "from apps.catalog.models import (",
        "    Game, GameTranslation, GameVersion, Genre, GenreTranslation",
        ")",
        "from apps.i18n.models import Language",
        "from apps.pipeline.services.artifacts import ensure_root, runtime_hash_for, runtime_path",
        f"technical_id = {technical_id!r}",
        f"host_label = {host_label!r}",
        f"game_slug = {game_slug!r}",
        f"genre_code = {genre_code!r}",
        f"genre_slug_en = {genre_slug_en!r}",
        f"genre_slug_ru = {genre_slug_ru!r}",
        f"genre_name_en = {genre_name_en!r}",
        f"genre_name_ru = {genre_name_ru!r}",
        f"game_name_en = {game_name_en!r}",
        f"game_name_ru = {game_name_ru!r}",
        f"game_slug_ru = {game_slug_ru!r}",
        f"runtime_marker = {runtime_marker!r}",
        f"runtime_files = {runtime_files!r}",
        "fallback_genre = Genre.objects.exclude(code=genre_code).order_by('code').first()",
        "if fallback_genre is None:",
        "    raise RuntimeError('a non-fixture genre is required for teardown')",
        "genre = Genre.objects.create(code=genre_code, sort_order=0)",
        "for language_code, name, slug in (",
        "    ('en', genre_name_en, genre_slug_en),",
        "    ('ru', genre_name_ru, genre_slug_ru),",
        "):",
        "    language = Language.objects.get(code=language_code)",
        "    GenreTranslation.objects.create(",
        "        genre=genre, language=language, name=name, slug=slug",
        "    )",
        "game = Game.objects.create(",
        "    technical_id=technical_id,",
        "    host_label=host_label,",
        "    slug=game_slug,",
        "    primary_genre=genre,",
        "    status=Game.STATUS_PUBLISHED,",
        "    published_at=timezone.now(),",
        "    default_language='en',",
        "    estimated_play_minutes=3,",
        ")",
        "en = Language.objects.get(code='en')",
        "ru = Language.objects.get(code='ru')",
        "GameTranslation.objects.create(",
        "    game=game,",
        "    language=en,",
        "    name=game_name_en,",
        "    slug=game_slug,",
        "    short_description='Disposable discovery fixture.',",
        "    description='Deterministic genre discovery browser fixture.',",
        ")",
        "GameTranslation.objects.create(",
        "    game=game,",
        "    language=ru,",
        "    name=game_name_ru,",
        "    slug=game_slug_ru,",
        "    short_description='Одноразовая фикстура discovery.',",
        "    description='Детерминированная браузерная фикстура жанров.',",
        ")",
        "runtime_hashes = {",
        "    name: hashlib.sha256(payload).hexdigest()",
        "    for name, payload in runtime_files.items()",
        "}",
        "runtime_hash = runtime_hash_for(runtime_hashes)",
        "runtime_dir = runtime_path(",
        "    ensure_root(Path(settings.ZIP_PUBLIC_RUNTIME_ROOT)),",
        "    runtime_hash,",
        "    host_label,",
        ")",
        "for relative, payload in runtime_files.items():",
        "    path = runtime_dir / relative",
        "    path.parent.mkdir(parents=True, exist_ok=True)",
        "    path.write_bytes(payload)",
        "package_hash = hashlib.sha256(b'e2e discovery package').hexdigest()",
        "version = GameVersion.objects.create(",
        "    game=game,",
        "    semver='1.0.0',",
        "    package_hash=package_hash,",
        "    runtime_hash=runtime_hash,",
        "    sdk_version='1.1.0',",
        "    size_bytes=len(b'e2e discovery package'),",
        "    manifest={'id': technical_id, 'name': 'E2E discovery fixture'},",
        "    supported_languages=['en', 'ru'],",
        "    import_report={'status': 'created', 'fixture': 'genre-discovery-e2e'},",
        "    e2e_report={'passed': True, 'fixture': 'genre-discovery-e2e'},",
        ")",
        "game.current_version = version",
        "game.save(update_fields=['current_version'])",
        "print(",
        f"    {SEED_MARKER!r} + json.dumps({{",
        "        'genre_id': str(genre.pk),",
        "        'game_id': str(game.pk),",
        "        'version_id': str(version.pk),",
        "        'game_slug': game.slug,",
        "        'genre_slug_en': genre_slug_en,",
        "        'genre_slug_ru': genre_slug_ru,",
        "        'genre_name_en': genre_name_en,",
        "        'genre_name_ru': genre_name_ru,",
        "        'game_name_en': game_name_en,",
        "        'game_name_ru': game_name_ru,",
        "        'game_origin': host_label + '.games.test',",
        "        'runtime_hash': runtime_hash,",
        "        'runtime_marker': runtime_marker,",
        "        'runtime_path': str(runtime_dir),",
        "    })",
        ")",
    ]
    completed = _compose_shell("\n".join(seed_lines))
    for line in completed.stdout.splitlines():
        if line.startswith(SEED_MARKER):
            payload = json.loads(line[len(SEED_MARKER) :])
            return {str(key): str(value) for key, value in payload.items()}
    raise AssertionError(
        f"Genre discovery E2E fixture did not return identifiers: "
        f"{completed.stdout}\n{completed.stderr}"
    )


def _cleanup_discovery_fixture(seed: dict[str, str]) -> None:
    cleanup_lines = [
        "import shutil",
        "from pathlib import Path",
        "from apps.catalog.models import (",
        "    Game,",
        "    GameGenre,",
        "    GameTranslation,",
        "    GameVersion,",
        "    Genre,",
        "    GenreTranslation,",
        ")",
        "from apps.gameplay.models import GameSession",
        f"game_id = {seed['game_id']!r}",
        f"version_id = {seed['version_id']!r}",
        f"genre_id = {seed['genre_id']!r}",
        f"runtime_path = Path({seed['runtime_path']!r})",
        "if runtime_path.is_dir():",
        "    shutil.rmtree(runtime_path, ignore_errors=True)",
        "host_runtime_dir = runtime_path.parent",
        "if host_runtime_dir.is_dir() and not any(host_runtime_dir.iterdir()):",
        "    host_runtime_dir.rmdir()",
        "GameSession.objects.filter(game_id=game_id).delete()",
        "GameTranslation.objects.filter(game_id=game_id).delete()",
        "GameGenre.objects.filter(game_id=game_id).delete()",
        "game = Game.objects.filter(pk=game_id).first()",
        "fallback_genre = Genre.objects.exclude(pk=genre_id).order_by('code').first()",
        "if game is not None:",
        "    game.current_version = None",
        "    if fallback_genre is not None:",
        "        game.primary_genre = fallback_genre",
        "    game.save(update_fields=['current_version', 'primary_genre'])",
        "GameVersion.objects.filter(pk=version_id).delete()",
        "game = Game.objects.filter(pk=game_id).first()",
        "if game is not None:",
        "    game.status = Game.STATUS_ARCHIVED",
        "    game.save(update_fields=['status'])",
        "GenreTranslation.objects.filter(genre_id=genre_id).delete()",
        "Genre.objects.filter(pk=genre_id).delete()",
        "print('GENRE_DISCOVERY_E2E_CLEANUP=ok')",
    ]
    completed = _compose_shell("\n".join(cleanup_lines))
    if "GENRE_DISCOVERY_E2E_CLEANUP=ok" not in completed.stdout:
        raise AssertionError(f"Genre discovery E2E cleanup did not confirm: {completed.stdout}")


@pytest.fixture(scope="module")
def discovery_seed() -> dict[str, str]:
    seed = _seed_discovery_fixture()
    try:
        yield seed
    finally:
        _cleanup_discovery_fixture(seed)


@pytest.fixture(scope="module")
def browser(discovery_seed: dict[str, str]) -> Browser:
    portal_host = urlsplit(BASE_URL).hostname or "portal.test"
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(
            headless=True,
            args=[
                "--host-resolver-rules="
                f"MAP {discovery_seed['game_origin']} 127.0.0.1, MAP {portal_host} 127.0.0.1"
            ],
        )
        yield instance
        instance.close()


@pytest.fixture
def page(browser: Browser) -> Page:
    context = browser.new_context(
        ignore_https_errors=True,
        viewport={"width": 360, "height": 640},
    )
    instance = context.new_page()
    yield instance
    context.close()


@pytest.mark.parametrize("language", ["en", "ru"])
def test_home_genre_game_detail_and_runtime_journey(
    page: Page,
    discovery_seed: dict[str, str],
    language: str,
) -> None:
    genre_name = discovery_seed[f"genre_name_{language}"]
    genre_slug = discovery_seed[f"genre_slug_{language}"]
    game_name = discovery_seed[f"game_name_{language}"]

    response = page.goto(f"{BASE_URL}/{language}/", wait_until="domcontentloaded")
    assert response is not None
    assert response.status == 200
    block = page.locator('[data-testid="home-genres"]')
    expect(block).to_be_visible()
    link = block.locator('[data-testid="home-genre-link"]').filter(has_text=genre_name)
    expect(link).to_be_visible()
    assert link.get_attribute("href") == f"/{language}/genres/{genre_slug}/"
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")

    link.click()
    page.wait_for_url(
        f"**/{language}/genres/{genre_slug}/",
        wait_until="domcontentloaded",
    )
    expect(page.locator("h1")).to_have_text(genre_name)
    expect(page.locator("#genre-sort")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")

    card = page.get_by_role("link", name=game_name, exact=True)
    expect(card).to_be_visible()
    card.click()
    page.wait_for_url(
        f"**/{language}/games/{discovery_seed['game_slug']}/",
        wait_until="domcontentloaded",
    )
    expect(page.locator("h1")).to_have_text(game_name)

    play = page.get_by_role("link", name="Play", exact=True)
    expect(play).to_be_visible()
    play.click()
    page.wait_for_url(
        f"**/{language}/games/{discovery_seed['game_slug']}/play/",
        wait_until="domcontentloaded",
    )

    frame_element = page.locator("#game-frame")
    expect(frame_element).to_be_visible()
    portal_port = urlsplit(BASE_URL).port
    port_suffix = "" if portal_port in (None, 443) else f":{portal_port}"
    runtime_prefix = (
        f"https://{discovery_seed['game_origin']}{port_suffix}/v/"
        f"{discovery_seed['runtime_hash']}/index.html#p="
    )
    expect(frame_element).to_have_attribute("data-src", re.compile(re.escape(runtime_prefix)))
    runtime = page.frame_locator("#game-frame")
    expect(runtime.locator("#runtime-proof")).to_be_visible(timeout=30000)
    expect(runtime.locator("#runtime-proof")).to_have_text(discovery_seed["runtime_marker"])
    expect(runtime.locator("html")).to_have_attribute("data-runtime-script", "executed")
    expect(page.locator("#player-status")).to_be_hidden()

    runtime_src = frame_element.get_attribute("src")
    assert runtime_src is not None
    assert runtime_src.startswith(runtime_prefix)
    assert re.search(r"[?&]s=[0-9a-f-]{36}(?:&|$)", runtime_src)
