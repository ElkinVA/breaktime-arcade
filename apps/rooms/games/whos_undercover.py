"""Who's Undercover? server-side setup and role assignment (Live Room)."""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SUPPORTED_LANGUAGES = {"en", "ru"}
MIN_PLAYERS = 4
MAX_PLAYERS = 12
MAX_UNDERCOVER = 3
MAX_NAME_LENGTH = 24


class GameSetupError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _language(language: str | None) -> str:
    return language if language in SUPPORTED_LANGUAGES else "en"


def load_decks(language: str | None) -> list[dict[str, Any]]:
    code = _language(language)
    path = DATA_DIR / f"whos_undercover_{code}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    decks = payload.get("words")
    if not isinstance(decks, list) or not decks:
        raise GameSetupError("E_PACK")
    return decks


def validate_setup(
    *,
    player_count: int,
    undercover_count: int,
    mr_white: bool,
    category_id: str | None,
    language: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not MIN_PLAYERS <= player_count <= MAX_PLAYERS:
        raise GameSetupError("E_PLAYERS")
    if not 1 <= undercover_count <= MAX_UNDERCOVER:
        raise GameSetupError("E_UNDERCOVER")
    infiltrators = undercover_count + (1 if mr_white else 0)
    if player_count - infiltrators <= infiltrators:
        raise GameSetupError("E_BALANCE")
    decks = load_decks(language)
    deck = next((item for item in decks if item.get("id") == category_id), None)
    if deck is None:
        deck = secrets.choice(decks)
    pairs = deck.get("pairs")
    if not isinstance(pairs, list) or not pairs:
        raise GameSetupError("E_PACK")
    return (
        {
            "undercover_count": undercover_count,
            "mr_white": mr_white,
            "category_id": deck["id"],
            "category_name": deck.get("name", deck["id"]),
            "language": _language(language),
        },
        {"deck": deck, "pair": secrets.choice(pairs)},
    )


def assign_roles(
    members: list[dict[str, Any]],
    *,
    undercover_count: int,
    mr_white: bool,
    category_id: str | None,
    language: str | None,
) -> dict[str, Any]:
    setup, selected = validate_setup(
        player_count=len(members),
        undercover_count=undercover_count,
        mr_white=mr_white,
        category_id=category_id,
        language=language,
    )
    civilian_word, undercover_word = selected["pair"][0], selected["pair"][1]
    roles = ["undercover"] * undercover_count
    if mr_white:
        roles.append("mr_white")
    roles.extend(["civilian"] * (len(members) - len(roles)))
    secrets.SystemRandom().shuffle(roles)
    order = secrets.SystemRandom().sample(range(len(members)), len(members))
    players = []
    reveal_order = []
    for index, role in enumerate(roles):
        member = members[index]
        word = (
            civilian_word
            if role == "civilian"
            else undercover_word
            if role == "undercover"
            else None
        )
        players.append(
            {
                "id": str(member["id"]),
                "name": member["name"],
                "role": role,
                "word": word,
                "alive": True,
                "revealed": False,
                "eliminated_round": None,
                "revealed_role": None,
            }
        )
    for index in order:
        reveal_order.append(players[index]["id"])
    return {
        "game_id": "whos_undercover",
        "phase": "reveal",
        "round": 1,
        "setup": setup,
        "players": players,
        "reveal_order": reveal_order,
        "revealed_count": 0,
        "civilian_word": civilian_word,
        "undercover_word": undercover_word,
        "votes": {},
        "last_vote": None,
        "winner": None,
        "reason": None,
        "mr_white_guess": None,
        "history": [],
    }


__all__ = [
    "GameSetupError",
    "MAX_NAME_LENGTH",
    "MAX_PLAYERS",
    "assign_roles",
    "load_decks",
    "validate_setup",
]
