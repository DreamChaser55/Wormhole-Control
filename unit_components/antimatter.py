import logging
from typing import Optional, TYPE_CHECKING
import dataclasses

from .base import UnitComponent
from geometry import distance
from constants import (
    DEFAULT_ANTIMATTER_CAPACITY, DEFAULT_ANTIMATTER_REGEN,
    DEFAULT_ANTIMATTER_HARVEST_RATE, ANTIMATTER_HARVEST_RANGE,
    ANTIMATTER_HARVESTER_HULL_COST, ANTIMATTER_CAPACITY_PER_HULL_POINT
)

if TYPE_CHECKING:
    from entities import Unit, CelestialBody
    from galaxy import Galaxy
    from game import Game

logger = logging.getLogger(__name__)

@dataclasses.dataclass
class AntimatterStorage(UnitComponent):
    """Component storing and managing antimatter energy levels for a unit."""
    DISPLAY_NAME: str = "Antimatter Storage"
    SIDEBAR_ORDER: int = 1
    max_capacity: float = DEFAULT_ANTIMATTER_CAPACITY
    current_amount: float = DEFAULT_ANTIMATTER_CAPACITY
    regen_rate: float = DEFAULT_ANTIMATTER_REGEN

    def __init__(self, unit: 'Unit', max_capacity: float = DEFAULT_ANTIMATTER_CAPACITY, regen_rate: float = DEFAULT_ANTIMATTER_REGEN, hull_cost: float = 0.0):
        if hull_cost == 0.0:
            hull_cost = AntimatterStorage.calc_hull_cost(max_capacity)
        super().__init__(unit, hull_cost=hull_cost)
        self.max_capacity = max_capacity
        self.regen_rate = regen_rate
        self.current_amount = max_capacity

    @staticmethod
    def calc_hull_cost(capacity: float) -> float:
        """Compute the hull cost of an Antimatter Storage component from its capacity."""
        if capacity <= 0:
            return 0.0
        return capacity / ANTIMATTER_CAPACITY_PER_HULL_POINT

    def consume(self, amount: float) -> bool:
        """Deducts antimatter. Returns True on success, False if insufficient."""
        if self.is_destroyed:
            return False
        if self.current_amount >= amount:
            self.current_amount -= amount
            logger.debug(f"[{self.unit.name}] Consumed {amount} antimatter. Remaining: {self.current_amount:.1f}/{self.max_capacity:.1f}")
            return True
        return False

    def regenerate(self) -> None:
        """Regenerates antimatter up to max_capacity.

        Note: this is no longer called automatically every turn for all units.
        Passive regeneration has been replaced by the AntimatterHarvester
        component (which refills its own unit's storage while near a star)
        and by transferring antimatter from another unit's storage. This
        method is kept for components/abilities that may still want to grant
        a flat regeneration tick (and for backward-compatible tests).
        """
        if self.is_destroyed:
            return
        if self.current_amount < self.max_capacity:
            old = self.current_amount
            self.current_amount = min(self.max_capacity, self.current_amount + self.regen_rate)
            logger.debug(f"[{self.unit.name}] Regenerated {self.current_amount - old:.1f} antimatter. Current: {self.current_amount:.1f}/{self.max_capacity:.1f}")

    def add(self, amount: float) -> float:
        """Adds antimatter up to max_capacity. Returns the actual amount added.

        Used by AntimatterHarvester (harvesting near a star) and by
        TransferAntimatterOrder (receiving antimatter from another unit).
        """
        if self.is_destroyed or amount <= 0:
            return 0.0
        available_space = max(0.0, self.max_capacity - self.current_amount)
        added = min(amount, available_space)
        if added > 0:
            self.current_amount += added
        return added

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        status = f"{self.current_amount:.1f}/{self.max_capacity:.1f}"
        data.append({'type': 'label', 'text': f"Antimatter: {status}", 'object_id': '#sidebar_info_label', 'height': 20})
        return data

    def get_basic_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_basic_sidebar_data(game_state)
        if self.is_destroyed:
            return data
        data.append({
            'type': 'label',
            'text': f"• Antimatter: {self.current_amount:.1f}/{self.max_capacity:.1f}",
            'object_id': '#sidebar_value_label',
            'height': 18,
            'indent_level': 1
        })
        return data


class AntimatterHarvester(UnitComponent):
    """Component that lets a unit generate new antimatter for its own storage.

    Only units equipped with this component can replenish antimatter, and
    only while positioned near a star (same system+hex as a Star, within
    harvest_range of it). Units without a harvester must be topped up by
    another unit transferring antimatter from its own storage instead
    (see TransferAntimatterOrder).
    """
    DISPLAY_NAME: str = "Antimatter Harvester"
    SIDEBAR_ORDER: int = 1

    def __init__(self, unit: 'Unit', harvest_rate: float = DEFAULT_ANTIMATTER_HARVEST_RATE, hull_cost: float = ANTIMATTER_HARVESTER_HULL_COST):
        super().__init__(unit, hull_cost=hull_cost)
        self.harvest_rate = harvest_rate
        self.harvest_range: float = ANTIMATTER_HARVEST_RANGE
        self.is_harvesting: bool = False  # Updated each turn: True if currently near a star and harvesting

    def find_nearby_star(self, galaxy: 'Galaxy') -> Optional['CelestialBody']:
        """Returns a Star in the unit's current system+hex within harvest_range, if any."""
        if not galaxy or not self.unit.in_system or self.unit.in_hex is None:
            return None
        system = galaxy.systems.get(self.unit.in_system)
        if not system:
            return None
        hex_obj = system.hexes.get(self.unit.in_hex)
        if not hex_obj:
            return None
        from entities import Star
        for body in hex_obj.celestial_bodies:
            if isinstance(body, Star) and distance(self.unit.position, body.position) <= self.harvest_range:
                return body
        return None

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        galaxy = game_state.galaxy if game_state else None
        nearby_star = self.find_nearby_star(galaxy)
        data.append({'type': 'label', 'text': f"Base Harvest Rate: {self.harvest_rate:.1f}/turn", 'object_id': '#sidebar_info_label', 'height': 20})
        if self.is_harvesting and nearby_star:
            multiplier = getattr(nearby_star, 'harvest_multiplier', 1.0)
            effective_rate = self.harvest_rate * multiplier
            data.append({'type': 'label', 'text': f"Effective Rate: {effective_rate:.1f}/turn ({multiplier:.1f}x star mult)", 'object_id': '#sidebar_info_label', 'height': 20})
            status_text = f"Harvesting (near {nearby_star.name})"
        else:
            status_text = "Idle (no star in range)"
        data.append({'type': 'label', 'text': f"Harvest Range: {self.harvest_range:.0f}", 'object_id': '#sidebar_info_label', 'height': 20})
        data.append({'type': 'label', 'text': f"Status: {status_text}", 'object_id': '#sidebar_info_label', 'height': 20})
        return data

    def get_basic_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_basic_sidebar_data(game_state)
        if self.is_destroyed:
            return data
        galaxy = game_state.galaxy if game_state else None
        nearby_star = self.find_nearby_star(galaxy)
        if self.is_harvesting and nearby_star:
            multiplier = getattr(nearby_star, 'harvest_multiplier', 1.0)
            effective_rate = self.harvest_rate * multiplier
            rate_text = f"{effective_rate:.1f}/t eff. [{self.harvest_rate:.1f} base]"
            status_text = "Harvesting"
            obj_id = '#sidebar_status_active_label'
        else:
            rate_text = f"{self.harvest_rate:.1f}/t base"
            status_text = "Idle"
            obj_id = '#sidebar_status_idle_label'
        data.append({
            'type': 'label',
            'text': f"• AM Harvest: {status_text} ({rate_text})",
            'object_id': obj_id,
            'height': 18,
            'indent_level': 1
        })
        return data


    def update(self, galaxy: 'Galaxy') -> None:
        """Refills the unit's own AntimatterStorage while near a star. Called each turn."""
        if self.is_destroyed:
            self.is_harvesting = False
            return

        am_comp = self.unit.antimatter_component
        if not am_comp:
            self.is_harvesting = False
            return

        nearby_star = self.find_nearby_star(galaxy)
        if nearby_star is None:
            self.is_harvesting = False
            return

        self.is_harvesting = True
        multiplier = getattr(nearby_star, 'harvest_multiplier', 1.0)
        effective_rate = self.harvest_rate * multiplier
        added = am_comp.add(effective_rate)
        if added > 0:
            logger.debug(f"[{self.unit.name}] Harvested {added:.1f} antimatter (base {self.harvest_rate:.1f} x {multiplier:.1f}x) near {nearby_star.name}. Current: {am_comp.current_amount:.1f}/{am_comp.max_capacity:.1f}")
