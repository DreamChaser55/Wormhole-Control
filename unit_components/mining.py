import logging
from typing import Optional, TYPE_CHECKING
import dataclasses

from .base import UnitComponent
from geometry import distance

if TYPE_CHECKING:
    from entities import Unit, CelestialBody
    from galaxy import Galaxy
    from game import Game

logger = logging.getLogger(__name__)

class MiningComponent(UnitComponent):
    """A component that allows a unit to extract raw resources from celestial bodies."""
    DISPLAY_NAME: str = "Mining"
    SIDEBAR_ORDER: int = 7
    mining_rate: float = 10.0
    mining_range: float = 200.0
    raw_metal_cargo: float = 0.0
    raw_crystal_cargo: float = 0.0
    max_cargo: float = 100.0
    mining_target: Optional['CelestialBody'] = None

    def __init__(self, unit: 'Unit', mining_rate: float = 10.0, mining_range: float = 200.0, max_cargo: float = 100.0, hull_cost: int = 10):
        super().__init__(unit, hull_cost=hull_cost)
        self.mining_rate = mining_rate
        self.mining_range = mining_range
        self.raw_metal_cargo = 0.0
        self.raw_crystal_cargo = 0.0
        self.max_cargo = max_cargo
        self.mining_target = None

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        metal = int(self.raw_metal_cargo)
        crystal = int(self.raw_crystal_cargo)
        max_c = int(self.max_cargo)
        data.append({'type': 'label', 'text': f"Raw Cargo: {metal} Metal, {crystal} Crystal / {max_c}", 'object_id': '#sidebar_info_label', 'height': 20})
        if self.raw_metal_cargo > 0 or self.raw_crystal_cargo > 0:
            data.append({
                'type': 'button',
                'text': "Unload to Nearest Refinery",
                'object_id': '#sidebar_expand_button',
                'action_id': 'unload_resources_nearest',
                'target_data': self.unit.id,
                'height': 25
            })
        if self.mining_target:
            data.append({'type': 'label', 'text': f"Mining Target: {self.mining_target.name}", 'object_id': '#sidebar_info_label', 'height': 20})
        return data

    def set_target(self, target: 'CelestialBody') -> None:
        self.mining_target = target

    def clear_target(self) -> None:
        self.mining_target = None

    def get_cargo_fullness(self) -> float:
        """Returns the percentage of cargo that is full (0.0 to 1.0)."""
        total_cargo = self.raw_metal_cargo + self.raw_crystal_cargo
        if self.max_cargo <= 0:
            return 1.0
        return min(1.0, total_cargo / self.max_cargo)

    def update(self, galaxy: 'Galaxy') -> None:
        if self.is_destroyed:
            return

        if not self.mining_target:
            return

        # Need to be in same system and hex
        if self.unit.in_system != self.mining_target.in_system or self.unit.in_hex != self.mining_target.in_hex:
            return

        # Need to be within range
        if distance(self.unit.position, self.mining_target.position) > self.mining_range:
            return

        total_cargo = self.raw_metal_cargo + self.raw_crystal_cargo
        if total_cargo >= self.max_cargo:
            return

        available_space = self.max_cargo - total_cargo
        amount_to_mine = min(self.mining_rate, available_space)

        from entities import Asteroid, AsteroidField, Moon
        if isinstance(self.mining_target, (Asteroid, AsteroidField)):
            # Infinite yield: we extract mining_rate without depleting the asteroid
            self.raw_metal_cargo += amount_to_mine
            logger.debug(f"{self.unit.name} mined {amount_to_mine} raw metal from {self.mining_target.name}. Cargo: {self.raw_metal_cargo}/{self.max_cargo}")
        elif isinstance(self.mining_target, Moon):
            # Infinite yield: we extract mining_rate without depleting the moon
            self.raw_crystal_cargo += amount_to_mine
            logger.debug(f"{self.unit.name} mined {amount_to_mine} raw crystal from {self.mining_target.name}. Cargo: {self.raw_crystal_cargo}/{self.max_cargo}")

    def unload_to_refinery(self, unload_metal: bool = True, unload_crystal: bool = True) -> tuple[float, float]:
        """Empties cargo and returns a tuple of (metal_amount, crystal_amount) unloaded."""
        metal_amount = self.raw_metal_cargo if unload_metal else 0.0
        crystal_amount = self.raw_crystal_cargo if unload_crystal else 0.0
        if unload_metal:
            self.raw_metal_cargo = 0.0
        if unload_crystal:
            self.raw_crystal_cargo = 0.0
        return metal_amount, crystal_amount


class MetalRefineryComponent(UnitComponent):
    """A component that instantly converts raw metal into player metal upon delivery."""
    DISPLAY_NAME: str = "Metal Refinery"
    SIDEBAR_ORDER: int = 8
    unload_range: float = 300.0

    def __init__(self, unit: 'Unit', unload_range: float = 300.0, hull_cost: int = 20):
        super().__init__(unit, hull_cost=hull_cost)
        self.unload_range = unload_range

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        data.append({'type': 'label', 'text': "Metal Refinery Active", 'object_id': '#sidebar_info_label', 'height': 20})
        return data

    def accept_resources(self, amount: float) -> None:
        if self.is_destroyed:
            return
        if self.unit.owner:
            self.unit.owner.metal += amount
            logger.debug(f"{self.unit.name} refined {amount} raw metal instantly for {self.unit.owner.name}.")


class CrystalRefineryComponent(UnitComponent):
    """A component that instantly converts raw crystal into player crystal upon delivery."""
    DISPLAY_NAME: str = "Crystal Refinery"
    SIDEBAR_ORDER: int = 9
    unload_range: float = 300.0

    def __init__(self, unit: 'Unit', unload_range: float = 300.0, hull_cost: int = 20):
        super().__init__(unit, hull_cost=hull_cost)
        self.unload_range = unload_range

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        data.append({'type': 'label', 'text': "Crystal Refinery Active", 'object_id': '#sidebar_info_label', 'height': 20})
        return data

    def accept_resources(self, amount: float) -> None:
        if self.is_destroyed:
            return
        if self.unit.owner:
            self.unit.owner.crystal += amount
            logger.debug(f"{self.unit.name} refined {amount} raw crystal instantly for {self.unit.owner.name}.")
