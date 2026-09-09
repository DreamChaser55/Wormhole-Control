"""Constructor allocation isolation while preparing a campaign on the game thread."""
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, cast

AllocationCounters = dict[tuple[type[Any], str], int]
_allocations: ContextVar[AllocationCounters | None] = ContextVar("campaign_load_allocations", default=None)


def allocate_id(owner: type[Any], attribute: str) -> int:
    """Consume one ID from the preparation scope or the process-local class counter.

    The owner is the canonical class, including when reached through a compatibility
    export. Isolated preparation never changes live counters; commit reconciles them.
    IDs are opaque and this helper does not perform campaign-wide allocation.
    """
    local = _allocations.get()
    if local is None:
        value = cast(int, getattr(owner, attribute))
        setattr(owner, attribute, value + 1)
        return value
    key = (owner, attribute)
    value = local.get(key, 0)
    local[key] = value + 1
    return value


def observe_id(owner: type[Any], attribute: str, value: int) -> None:
    if _allocations.get() is None:
        setattr(owner, attribute, max(getattr(owner, attribute), value + 1))


@contextmanager
def isolated_allocations() -> Iterator[AllocationCounters]:
    """Yield private counters and restore the prior scope even when preparation fails."""
    allocations: AllocationCounters = {}
    token = _allocations.set(allocations)
    try:
        yield allocations
    finally:
        _allocations.reset(token)
