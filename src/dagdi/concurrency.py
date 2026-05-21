"""Concurrency helpers for parallel target execution."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List, Optional, Sequence, TypeVar, cast

T = TypeVar("T")
U = TypeVar("U")


def parallel_map_ordered(
    items: Sequence[T],
    func: Callable[[T], U],
    max_workers: Optional[int] = None,
    on_complete: Optional[Callable[[int, int], None]] = None,
) -> List[U]:
    """Run work in parallel while preserving input order in the output.

    Args:
        on_complete: Optional callback(completed_count, total_count) invoked
                     on the main thread after each item finishes.
    """
    if not items:
        return []

    total = len(items)
    worker_count = max_workers or min(32, total)

    if worker_count <= 1:
        result_list: List[U] = []
        for i, item in enumerate(items):
            result_list.append(func(item))
            if on_complete:
                on_complete(i + 1, total)
        return result_list

    results: List[Optional[U]] = [None] * total
    completed = 0
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_index = {
            executor.submit(func, item): index for index, item in enumerate(items)
        }
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            results[index] = future.result()
            completed += 1
            if on_complete:
                on_complete(completed, total)

    return [cast(U, result) for result in results]
