from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

type JSON = dict[str, str]
type AnyJSON = dict[str, Any]

MAX_OPTIONS = 10


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


class CommandError(StrEnum):
    NO_OPTIONS = "no_options"
    TOO_MANY_OPTIONS = "too_many_options"
    LIMIT_NOT_INT = "limit_not_int"
    LIMIT_TOO_LOW = "limit_too_low"
    LIMIT_EXCEEDS_OPTIONS = "limit_exceeds_options"


def is_slackmoji(string: str) -> bool:
    return len(string) >= 2 and string.startswith(":") and string.endswith(":")


def build_command(
    *,
    question: str,
    options: list[OptionData],
    anonymous: bool,
    secret: bool,
    vote_emoji_raw: str | None,
    vote_limit_raw: str | None,
) -> tuple[Command, None] | tuple[None, CommandError]:
    """Validate already-parsed poll inputs and assemble a `Command`.

    Both the slash-command parser and the modal `view_submission` handler
    converge here after pulling raw values out of their respective payload
    shapes. Errors are returned as a `CommandError` enum so each caller can
    map them to its own UX (ephemeral DM copy vs. block-id-keyed errors).
    """
    if not options:
        return None, CommandError.NO_OPTIONS
    if len(options) > MAX_OPTIONS:
        return None, CommandError.TOO_MANY_OPTIONS

    vote_limit: int | None = None
    if vote_limit_raw:
        try:
            vote_limit = int(vote_limit_raw)
        except ValueError:
            return None, CommandError.LIMIT_NOT_INT
        if vote_limit < 1:
            return None, CommandError.LIMIT_TOO_LOW
        if vote_limit > len(options):
            return None, CommandError.LIMIT_EXCEEDS_OPTIONS

    vote_emoji = (
        vote_emoji_raw if vote_emoji_raw and is_slackmoji(vote_emoji_raw) else None
    )

    return (
        Command(
            question=question,
            options=options,
            anonymous=secret or anonymous,
            secret=secret,
            vote_emoji=vote_emoji,
            vote_limit=vote_limit,
        ),
        None,
    )


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
