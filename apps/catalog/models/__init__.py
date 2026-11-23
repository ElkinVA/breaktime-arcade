from .asset import GameAsset
from .game import Game
from .genre import Genre, GenreTranslation
from .relations import GameGenre, GameTag
from .slug import GameSlugHistory
from .tag import Tag, TagTranslation
from .translation import GameTranslation
from .version import GameVersion

__all__ = [
    "Game",
    "GameAsset",
    "GameGenre",
    "GameSlugHistory",
    "GameTag",
    "GameTranslation",
    "GameVersion",
    "Genre",
    "GenreTranslation",
    "Tag",
    "TagTranslation",
]
