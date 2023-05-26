from dataclasses import dataclass
from typing import Any
from typing import Dict
from typing import Iterable
from typing import List
from typing import Optional
from typing import TypeVar
from urllib.parse import urlparse

T = TypeVar("T")

JSON = Dict[str, str]
ListJSON = Dict[str, List[JSON]]
AnyJSON = Dict[str, Any]


@dataclass
class OptionData:
    text: str
    emoji: Optional[str]


@dataclass
class Command:
    question: str
    options: List[OptionData]
    anonymous: bool
    secret: bool
    vote_emoji: Optional[str]
    vote_limit: Optional[int]


def batch(lst: List[T], n: int = 1) -> Iterable[List[T]]:
    ln = len(lst)
    for ndx in range(0, ln, n):
        yield lst[ndx : min(ndx + n, ln)]


def get_footer(
    user_id: Optional[str], anonymous: bool, secret: bool, vote_limit: Optional[int]
) -> str:
    limit_str = ""
    if vote_limit:
        limit_str = f". (Pick up to {vote_limit} option{'s' if vote_limit > 1 else ''})"
    if secret:
        return f"Poll creator and votes are hidden{limit_str}"
    if anonymous:
        return f"Anonymous poll created by <@{user_id}> with /votey{limit_str}"

    return f"Poll created by <@{user_id}> with /votey{limit_str}"


def rewrite_pg_url(database_url: str) -> str:
    url = urlparse(database_url)
    return url._replace(scheme="postgresql+psycopg2").geturl()
