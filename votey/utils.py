from typing import Any
from typing import Iterable

def batch(iterable, n=1) -> Iterable[Any]:
    l = len(iterable)
    for ndx in range(0, l, n):
        yield iterable[ndx:min(ndx + n, l)]
