from typing import Any
from typing import Callable
from typing import Dict
from typing import Iterable
from typing import List
from typing import TypeVar

T = TypeVar('T')

JSON = Dict[str, str]
ListJSON = Dict[str, List[JSON]]
AnyJSON = Dict[str, Any]

def batch(lst: List[T], n: int = 1) -> Iterable[List[T]]:
    ln = len(lst)
    for ndx in range(0, ln, n):
        yield lst[ndx:min(ndx + n, ln)]