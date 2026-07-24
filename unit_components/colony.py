import logging
from typing import TYPE_CHECKING
import dataclasses

from .base import UnitComponent

if TYPE_CHECKING:
    from entities import Unit, Planet
    from game import Game

logger = logging.getLogger(__name__)

class ColonyComponent(UnitComponent):
    """A component that allows a unit to transport population and colonize planets."""
    DISPLAY_NAME: str = "Colony"
    SIDEBAR_ORDER: int = 6
    population_cargo: int = 0
    max_cargo: int = 100

    def __init__(self, unit: 'Unit', hull_cost: int = 10):
        super().__init__(unit, hull_cost=hull_cost)
        self.population_cargo = 0
        self.max_cargo = 100

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        data.append({'type': 'label', 'text': f"Population Cargo: {self.population_cargo} / {self.max_cargo}", 'object_id': '#sidebar_info_label', 'height': 20})
        return data

    def load_population(self, planet: 'Planet', amount: int) -> bool:
        if self.is_destroyed:
            logger.debug(f"Error: Cannot load population, {self.unit.name}'s ColonyComponent is destroyed.")
            return False
        if planet.owner != self.unit.owner:
            logger.debug(f"Error: Cannot load population from unowned planet {planet.name}.")
            return False
        if planet.population < amount:
            logger.debug(f"Error: Not enough population on {planet.name} to load {amount}.")
            return False
        if self.population_cargo + amount > self.max_cargo:
            logger.debug(f"Error: Not enough cargo space to load {amount} population.")
            return False
        
        planet.population -= amount
        self.population_cargo += amount
        logger.debug(f"Loaded {amount} population from {planet.name}. Current cargo: {self.population_cargo}")
        return True

    def unload_population(self, planet: 'Planet', amount: int) -> bool:
        if self.is_destroyed:
            logger.debug(f"Error: Cannot unload population, {self.unit.name}'s ColonyComponent is destroyed.")
            return False
        if self.population_cargo < amount:
            logger.debug(f"Error: Not enough population in cargo to unload {amount}.")
            return False

        if planet.owner is None:
            planet.owner = self.unit.owner
            logger.debug(f"Planet {planet.name} has been colonized by {self.unit.owner.name}.")

        if planet.owner != self.unit.owner:
            logger.debug(f"Error: Cannot unload population on planet owned by another player.")
            return False

        planet.population += amount
        self.population_cargo -= amount
        logger.debug(f"Unloaded {amount} population onto {planet.name}. Current cargo: {self.population_cargo}")
        return True
