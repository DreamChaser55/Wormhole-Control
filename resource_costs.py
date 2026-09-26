"""Pure industrial prices and atomic empire-resource transactions.

Reservations are a separate validation budget, not an escrow account. Payments
always recheck the live treasury before changing any of its three balances.
"""
from dataclasses import dataclass
import math
from typing import Mapping

from constants import HULL_CAPACITIES

RESOURCE_NAMES = ('credits', 'metal', 'crystal')
HULL_METAL_FACTOR = 0.5
EQUIPMENT_METAL_FACTOR = 1.0
EQUIPMENT_CRYSTAL_FACTOR = 0.5
FORTIFICATION_METAL_PER_LEVEL = 25
FORTIFICATION_CRYSTAL_PER_LEVEL = 5
SALVAGE_FACTOR = 0.5


@dataclass(frozen=True)
class ResourceCost:
    credits: float = 0
    metal: float = 0
    crystal: float = 0

    def __post_init__(self):
        for value in self.to_dict().values():
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError('Resource amounts must be finite non-negative numbers.')

    def to_dict(self) -> dict[str, float]:
        return {name: getattr(self, name) for name in RESOURCE_NAMES}

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != set(RESOURCE_NAMES):
            raise ValueError('Expected credits, metal and crystal amounts.')
        return cls(**value)

    def __add__(self, other):
        if not isinstance(other, ResourceCost):
            return NotImplemented
        return ResourceCost(**{name: getattr(self, name) + getattr(other, name) for name in RESOURCE_NAMES})

    def scaled(self, factor: float):
        if type(factor) not in (int, float) or not math.isfinite(factor) or factor < 0:
            raise ValueError('Resource multiplier must be finite and non-negative.')
        return ResourceCost(**{name: getattr(self, name) * factor for name in RESOURCE_NAMES})

    def shortfall(self, treasury):
        balances = resource_balances(treasury)
        return ResourceCost(**{name: max(0, getattr(self, name) - balances[name]) for name in RESOURCE_NAMES})

    def affordable(self, treasury) -> bool:
        balances = resource_balances(treasury)
        return all(balances[name] >= getattr(self, name) for name in RESOURCE_NAMES)

    def pay(self, player) -> bool:
        if not self.affordable(player):
            return False
        for name, amount in self.to_dict().items():
            if amount:
                setattr(player, name, getattr(player, name) - amount)
        return True

    def refund(self, player) -> None:
        for name, amount in self.to_dict().items():
            if amount:
                setattr(player, name, getattr(player, name) + amount)

    def describe(self) -> str:
        return ', '.join(f'{amount:g} {name}' for name, amount in self.to_dict().items())


def resource_balances(treasury) -> dict[str, float]:
    """Read wallets and projected budgets (which may contain deficits)."""
    if isinstance(treasury, Mapping):
        return {name: treasury.get(name, 0) for name in RESOURCE_NAMES}
    return {name: getattr(treasury, name, 0) for name in RESOURCE_NAMES}


def construction_cost(hull_size, used_hull, credits) -> ResourceCost:
    _validate_hull_usage(used_hull)
    return ResourceCost(credits, math.ceil(HULL_CAPACITIES[hull_size] * HULL_METAL_FACTOR
                                          + used_hull * EQUIPMENT_METAL_FACTOR),
                        math.ceil(used_hull * EQUIPMENT_CRYSTAL_FACTOR))


def installation_cost(used_hull, credits=0) -> ResourceCost:
    _validate_hull_usage(used_hull)
    return ResourceCost(credits, math.ceil(used_hull * EQUIPMENT_METAL_FACTOR),
                        math.ceil(used_hull * EQUIPMENT_CRYSTAL_FACTOR))


def _validate_hull_usage(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('Hull usage must be finite and non-negative.')


def template_cost(template) -> ResourceCost:
    """Derive materials from canonical design data, never authored price hints."""
    from custom_unit_templates import template_from_dict
    raw = dict(template)
    if hasattr(raw.get('hull_size'), 'name'):
        raw['hull_size'] = raw['hull_size'].name
    design = template_from_dict(raw.get('name', 'Construction'), raw)
    return construction_cost(design.hull_size, design.total_hull_cost,
                             template.get('build_cost', design.build_cost))


def fortification_cost(level) -> ResourceCost:
    from planetary_balance import FORTIFICATION_COSTS
    return ResourceCost(FORTIFICATION_COSTS[level - 1], FORTIFICATION_METAL_PER_LEVEL * level,
                        FORTIFICATION_CRYSTAL_PER_LEVEL * level)
