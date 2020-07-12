from typing import Any
from typing import Dict
from typing import Iterable
from typing import List
from typing import TypeVar

T = TypeVar("T")

JSON = Dict[str, str]
ListJSON = Dict[str, List[JSON]]
AnyJSON = Dict[str, Any]


def batch(lst: List[T], n: int = 1) -> Iterable[List[T]]:
    ln = len(lst)
    for ndx in range(0, ln, n):
        yield lst[ndx : min(ndx + n, ln)]


def get_footer(user_id: str, anonymous: bool, secret: bool) -> str:
    if secret:
        return "Poll creator and votes are hidden."
    if anonymous:
        return f"Anonymous poll created by <@{user_id}> with /votey"

    return f"Poll created by <@{user_id}> with /votey"
