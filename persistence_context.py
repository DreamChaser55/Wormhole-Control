"""Constructor allocation isolation while preparing a campaign on the game thread."""
from contextlib import contextmanager
from contextvars import ContextVar

_allocations = ContextVar("campaign_load_allocations", default=None)


def allocate_id(owner, attribute):
    local = _allocations.get()
    if local is None:
        value = getattr(owner, attribute)
        setattr(owner, attribute, value + 1)
        return value
    key = (owner, attribute)
    value = local.get(key, 0)
    local[key] = value + 1
    return value


def observe_id(owner, attribute, value):
    if _allocations.get() is None:
        setattr(owner, attribute, max(getattr(owner, attribute), value + 1))


@contextmanager
def isolated_allocations():
    allocations = {}
    token = _allocations.set(allocations)
    try:
        yield allocations
    finally:
        _allocations.reset(token)
