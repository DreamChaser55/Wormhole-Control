"""Movement payment exceptions shared by resolution and travel previews."""
from constants import HullSize


def fuel_free_sublight(unit):
    return unit.hull_size == HullSize.STRIKECRAFT_WING and unit.antimatter_component is None

