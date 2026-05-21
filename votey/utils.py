from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

type JSON = dict[str, str]
type AnyJSON = dict[str, Any]


@dataclass
class OptionData:
    text: str
    emoji: str | None


@dataclass
class Command:
    question: str
    options: list[OptionData]
    anonymous: bool
    secret: bool
    vote_emoji: str | None
    vote_limit: int | None


def pluralize(n: int, word: str) -> str:
    """Return `word` with an `s` suffix unless `n == 1`."""
    return word if n == 1 else f"{word}s"


def get_footer(
    user_id: str | None, anonymous: bool, secret: bool, vote_limit: int | None
) -> str:
    limit_str = (
        f". (Pick up to {vote_limit} {pluralize(vote_limit, 'option')})"
        if vote_limit
        else ""
    )
    if secret:
        return f"Poll creator and votes are hidden{limit_str}"
    if anonymous:
        return f"Anonymous poll created by <@{user_id}> with /votey{limit_str}"
    return f"Poll created by <@{user_id}> with /votey{limit_str}"


def normalize_database_url(database_url: str) -> str:
    """Return a SQLAlchemy-compatible database URL for the given backend."""
    url = urlparse(database_url)
    scheme = url.scheme.lower().split("+", maxsplit=1)[0]
    if scheme in ("postgres", "postgresql"):
        return url._replace(scheme="postgresql+psycopg2").geturl()
    return database_url
