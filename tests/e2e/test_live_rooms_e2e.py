"""Two-browser Live Room E2E for Who's Undercover? Live.

Requires the dev stack with ``whos_undercover_live`` imported/published by
``make undercover-live-seed``. Each player uses an independent browser context
and therefore an independent portal identity/session.
"""

from __future__ import annotations

import contextlib
import os
import re

import pytest
from playwright.sync_api import Browser, BrowserContext, FrameLocator, Page, expect, sync_playwright

BASE_URL = os.environ.get("BA_E2E_BASE_URL", "https://portal.test:8443").rstrip("/")
GAME_URL = f"{BASE_URL}/en/games/whos-undercover-live/play/"
GAME_ORIGIN = "whos-undercover-live.games.test"

pytestmark = pytest.mark.e2e

if os.environ.get("BA_E2E") != "1":
    pytest.skip(
        "BA_E2E не включён; задайте BA_E2E=1 и BA_E2E_BASE_URL",
        allow_module_level=True,
    )


@pytest.fixture(scope="module")
def browser() -> Browser:
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(
            headless=True,
            args=[f"--host-resolver-rules=MAP {GAME_ORIGIN} 127.0.0.1, MAP portal.test 127.0.0.1"],
        )
        yield instance
        instance.close()


def _context(browser: Browser) -> BrowserContext:
    return browser.new_context(
        ignore_https_errors=True,
        viewport={"width": 1100, "height": 900},
    )


def _open_player(browser: Browser) -> tuple[BrowserContext, Page, FrameLocator]:
    context = _context(browser)
    page = context.new_page()
    page.goto(GAME_URL, wait_until="domcontentloaded")
    frame = page.frame_locator("#game-frame")
    expect(frame.locator("#entry-screen")).to_be_visible(timeout=20000)
    return context, page, frame


def _wait_for_frame(frame: FrameLocator, selector: str, timeout: int = 20000) -> None:
    expect(frame.locator(selector)).to_be_visible(timeout=timeout)


def _wait_for_each(
    pages: list[Page], frames: list[FrameLocator], selector: str, timeout: int = 20000
) -> None:
    # Bring each tab to the foreground before waiting: a background tab is
    # allowed to pause polling, and its next visibilitychange refresh updates it.
    for page, frame in zip(pages, frames, strict=True):
        page.bring_to_front()
        _wait_for_frame(frame, selector, timeout)


def _click_ready_until_start_enabled(
    frames: list[FrameLocator], host: FrameLocator, wait_page: Page
) -> None:
    for _ in range(6):
        if host.locator("#lobby-start").is_enabled():
            return
        for frame in frames[1:]:
            button = frame.locator("#lobby-ready")
            if button.is_visible() and button.is_enabled() and button.inner_text() == "I'm ready":
                button.click()
        wait_page.wait_for_timeout(900)
    expect(host.locator("#lobby-start")).to_be_enabled(timeout=15000)


def _setup_players(
    browser: Browser,
    names: list[str],
    *,
    undercover_count: int = 1,
    mr_white: bool = False,
) -> tuple[list[BrowserContext], list[Page], list[FrameLocator], list[str], list[str], list[str]]:
    contexts: list[BrowserContext] = []
    pages: list[Page] = []
    frames: list[FrameLocator] = []
    for _ in names:
        context, page, frame = _open_player(browser)
        contexts.append(context)
        pages.append(page)
        frames.append(frame)

    host = frames[0]
    host.locator("#create-name").fill(names[0])
    host.locator("#create-max").select_option(str(len(names)))
    host.locator("#create-undercover").select_option(str(undercover_count))
    if mr_white:
        host.locator("#create-mrwhite").check(force=True)
    host.locator("#create-room").click()
    _wait_for_frame(host, "#lobby-screen")
    code = host.locator("#lobby-code").inner_text()

    for index, frame in enumerate(frames[1:], start=1):
        frame.locator("#join-code").fill(code)
        frame.locator("#join-name").fill(names[index])
        frame.locator("#join-room").click()
        _wait_for_frame(frame, "#lobby-screen")

    _click_ready_until_start_enabled(frames, host, pages[0])
    host.locator("#lobby-start").click()
    _wait_for_each(pages, frames, "#reveal-screen")

    roles: list[str] = []
    words: list[str] = []
    for frame in frames:
        roles.append(frame.locator("#reveal-role").inner_text())
        words.append(frame.locator("#reveal-word").inner_text())
        # Only the viewer's own role/word is rendered here.
        assert roles[-1] in {"Civilian", "Undercover", "Mr. White"}
    for index, frame in enumerate(frames):
        visible = frame.locator("#reveal-screen").inner_text()
        for other, word in enumerate(words):
            if other == index or roles[other] == roles[index] or word in {"", "—"}:
                continue
            pattern = rf"(?<!\w){re.escape(word)}(?!\w)"
            assert re.search(pattern, visible, re.IGNORECASE) is None, (
                f"player {index} can see another player's word"
            )
    return contexts, pages, frames, names, roles, words


def _setup_four_players(
    browser: Browser,
) -> tuple[list[BrowserContext], list[Page], list[FrameLocator], list[str], list[str], list[str]]:
    return _setup_players(browser, ["Host", "G1", "G2", "G3"])


def _ack_reveal_and_wait_for_clues(
    pages: list[Page], frames: list[FrameLocator], wait_page: Page
) -> None:
    for page, frame in zip(pages, frames, strict=True):
        page.bring_to_front()
        button = frame.locator("#reveal-ack")
        if button.is_visible() and button.is_enabled():
            button.click()
        wait_page.wait_for_timeout(450)
    # The server may reject a stale ack while other players are acking;
    # retry the UI action until the public phase moves on.
    for _ in range(8):
        if all(frame.locator("#clues-screen").is_visible() for frame in frames):
            break
        for page, frame in zip(pages, frames, strict=True):
            page.bring_to_front()
            button = frame.locator("#reveal-ack")
            if button.is_visible() and button.is_enabled():
                with contextlib.suppress(Exception):
                    button.click()
        wait_page.wait_for_timeout(500)
    _wait_for_each(pages, frames, "#clues-screen")


def _advance_clues_to_vote(
    pages: list[Page], host: FrameLocator, frames: list[FrameLocator], wait_page: Page
) -> None:
    for _ in range(8):
        if all(frame.locator("#vote-screen").is_visible() for frame in frames):
            break
        pages[0].bring_to_front()
        button = host.locator("#clues-next")
        if button.is_visible() and button.is_enabled():
            button.click()
        wait_page.wait_for_timeout(700)
    _wait_for_each(pages, frames, "#vote-screen")


def _cast_votes(
    pages: list[Page],
    frames: list[FrameLocator],
    wait_page: Page,
    targets: list[str],
) -> None:
    for page, target, frame in zip(pages, targets, frames, strict=True):
        page.bring_to_front()
        for _ in range(12):
            if not frame.locator("#vote-screen").is_visible():
                break
            if frame.locator("#vote-self").is_visible():
                break
            button = frame.locator("#vote-targets button", has_text=target)
            if button.is_visible() and button.is_enabled():
                button.click()
            wait_page.wait_for_timeout(800)


def test_four_players_reveal_privately_and_civilians_win(browser: Browser) -> None:
    contexts: list[BrowserContext] = []
    pages: list[Page] = []
    try:
        contexts, pages, frames, names, roles, words = _setup_four_players(browser)
        undercover = roles.index("Undercover")
        assert words[undercover] != words[(undercover + 1) % len(words)]

        # Reconnect one guest through the same portal context. SDK storage
        # restores the room id and the server re-delivers the same private role.
        pages[1].close()
        reconnected = contexts[1].new_page()
        reconnected.goto(GAME_URL, wait_until="domcontentloaded")
        reconnect_frame = reconnected.frame_locator("#game-frame")
        reconnected.bring_to_front()
        _wait_for_frame(reconnect_frame, "#reveal-screen")
        assert reconnect_frame.locator("#reveal-role").inner_text() == roles[1]
        frames[1] = reconnect_frame
        pages[1] = reconnected

        _ack_reveal_and_wait_for_clues(pages, frames, pages[0])
        _advance_clues_to_vote(pages, frames[0], frames, pages[0])

        targets = [
            names[(index + 1) % len(names)] if index == undercover else names[undercover]
            for index in range(len(names))
        ]
        _cast_votes(pages, frames, pages[0], targets)

        _wait_for_each(pages, frames, "#over-screen")
        expect(frames[0].locator("#over-title")).to_have_text("Civilians win")
        expect(frames[0].locator("#over-players")).to_contain_text("Undercover")
        expect(frames[0].locator("#over-civilian")).not_to_have_text("—")

        # Replay keeps the same table and deals a fresh round.
        for _ in range(4):
            pages[0].bring_to_front()
            if frames[0].locator("#reveal-screen").is_visible():
                break
            if frames[0].locator("#over-restart").is_visible():
                frames[0].locator("#over-restart").click()
            pages[0].wait_for_timeout(700)
        _wait_for_each(pages, frames, "#reveal-screen")
        for frame in frames:
            assert frame.locator("#reveal-role").inner_text() in {
                "Civilian",
                "Undercover",
                "Mr. White",
            }
    finally:
        for context in contexts:
            context.close()


def test_tied_vote_starts_the_next_round(browser: Browser) -> None:
    contexts: list[BrowserContext] = []
    pages: list[Page] = []
    try:
        contexts, pages, frames, _, _, _ = _setup_four_players(browser)
        _ack_reveal_and_wait_for_clues(pages, frames, pages[0])
        _advance_clues_to_vote(pages, frames[0], frames, pages[0])

        # Host and G2 vote for G1; G1 and G3 vote for G2: a true 2:2 tie.
        _cast_votes(pages, frames, pages[0], ["G1", "G2", "G1", "G2"])
        _wait_for_each(pages, frames, "#result-screen")
        expect(frames[0].locator("#result-title")).to_have_text("Tie — nobody leaves this round.")

        for _ in range(4):
            pages[0].bring_to_front()
            if frames[0].locator("#clues-screen").is_visible():
                break
            if frames[0].locator("#result-next").is_visible():
                frames[0].locator("#result-next").click()
            pages[0].wait_for_timeout(700)
        _wait_for_each(pages, frames, "#clues-screen")
        expect(frames[0].locator("#clues-round")).to_have_text("Round 2")
    finally:
        for context in contexts:
            context.close()


def test_caught_mr_white_can_steal_the_game(browser: Browser) -> None:
    contexts: list[BrowserContext] = []
    pages: list[Page] = []
    try:
        contexts, pages, frames, names, roles, words = _setup_players(
            browser,
            ["Host", "G1", "G2", "G3", "MW"],
            mr_white=True,
        )
        mr_index = roles.index("Mr. White")
        civilian_word = next(
            word for role, word in zip(roles, words, strict=True) if role == "Civilian"
        )
        _ack_reveal_and_wait_for_clues(pages, frames, pages[0])
        _advance_clues_to_vote(pages, frames[0], frames, pages[0])

        # Everyone except Mr. White votes for Mr. White; Mr. White cannot vote
        # for himself, so the table still reaches a majority.
        fallback = names[0] if mr_index != 0 else names[1]
        targets = [
            fallback if index == mr_index else names[mr_index] for index in range(len(names))
        ]
        _cast_votes(pages, frames, pages[0], targets)

        _wait_for_each(pages, frames, "#mrwhite-screen")
        mrwhite = frames[mr_index]
        expect(mrwhite.locator("#mrwhite-form")).to_be_visible()
        pages[mr_index].bring_to_front()
        pages[0].wait_for_timeout(1200)
        mrwhite.locator("#mrwhite-guess").fill(civilian_word)

        for _ in range(8):
            if frames[0].locator("#over-screen").is_visible():
                break
            if not mrwhite.locator("#mrwhite-form").is_visible():
                break
            # Re-fill each attempt so the test is also stable against an older
            # published runtime that cleared the input on every poll.
            mrwhite.locator("#mrwhite-guess").fill(civilian_word)
            button = mrwhite.locator("#mrwhite-submit")
            if button.is_visible() and button.is_enabled():
                button.click()
            pages[0].wait_for_timeout(700)
        _wait_for_each(pages, frames, "#over-screen")
        expect(frames[0].locator("#over-title")).to_have_text("Mr. White wins")
        expect(frames[0].locator("#over-reason")).to_have_text("Mr. White guessed the word.")
        expect(frames[0].locator("#over-civilian")).to_have_text(civilian_word)
    finally:
        for context in contexts:
            context.close()
