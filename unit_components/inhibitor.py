import logging
from typing import TYPE_CHECKING
import dataclasses

from .base import UnitComponent

if TYPE_CHECKING:
    from entities import Unit
    from galaxy import Galaxy
    from game import Game

logger = logging.getLogger(__name__)

class HyperspaceInhibitionFieldEmitter(UnitComponent):
    """A component that generates a hyperspace inhibition field, preventing jumps."""
    DISPLAY_NAME: str = "Inhibitor"
    SIDEBAR_ORDER: int = 4
    radius: float = 50.0
    is_active: bool = False

    def __init__(self, unit: 'Unit', radius: float = 50.0, hull_cost: int = 20):
        super().__init__(unit, hull_cost=hull_cost)
        self.radius = radius
        self.is_active = False

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        data.append({
            'type': 'inhibitor_button',
            'is_active': self.is_active,
            'height': 30
        })
        return data

    def turn_on(self) -> None:
        """Activates the inhibition field. (Validation logic will be handled by the order)."""
        if self.is_destroyed:
            return
        # In the future, an order will perform validation before setting this.
        self.is_active = True
        logger.debug(f"Unit {self.unit.name} inhibition field activated.")

    def turn_off(self) -> None:
        """Deactivates the inhibition field."""
        self.is_active = False
        logger.debug(f"Unit {self.unit.name} inhibition field deactivated.")

    def on_destroyed(self) -> None:
        if self.is_active:
            galaxy_ref = getattr(self.unit, 'in_galaxy', None)
            if galaxy_ref and self.unit.in_system and self.unit.in_hex:
                current_hex = galaxy_ref.systems[self.unit.in_system].hexes.get(self.unit.in_hex)
                if current_hex and self.unit.id in current_hex.dynamic_inhibition_zones:
                    del current_hex.dynamic_inhibition_zones[self.unit.id]
            self.turn_off()

    def toggle(self, galaxy_ref: 'Galaxy') -> bool:
        """
        Directly toggles the hyperspace inhibition field on or off, performing
        all necessary spatial and game-logic validation before applying the state change.

        When turning ON, the method validates that:
        1. The proposed field (a circle based on the emitter's radius) is fully
           contained within the boundaries of the current sector (hex).
        2. The proposed field does not overlap with any existing inhibition zones
           in the current sector.
        
        If validation passes, it updates both the component's internal state and
        registers the dynamic inhibition zone within the current hex. When turning OFF,
        it cleans up the registered zone.

        Args:
            galaxy_ref ('Galaxy'): A reference to the main galaxy object, used to
                                   access the current star system and hex grid data.

        Returns:
            bool: True if the toggle operation was successful and applied. False if
                  the toggle failed due to validation errors (e.g., crossing a sector
                  boundary or overlapping with another field), or if the unit's
                  location data is invalid.
        """
        from geometry import Circle, is_circle_contained, do_circles_intersect

        if not galaxy_ref or not self.unit.in_system or self.unit.in_hex is None:
            return False

        if self.is_destroyed:
            return False

        current_hex = galaxy_ref.systems[self.unit.in_system].hexes[self.unit.in_hex]
        
        if self.is_active:
            # Deactivate the field and clean up spatial registration.
            if self.unit.id in current_hex.dynamic_inhibition_zones:
                del current_hex.dynamic_inhibition_zones[self.unit.id]
            self.turn_off()
            return True
        else:
            # Activate the field after checking sector boundaries and overlap constraints.
            proposed_field = Circle(center=self.unit.position, radius=self.radius)

            if not is_circle_contained(proposed_field, current_hex.boundary_circle):
                logger.debug(f"[{self.unit.name}] TOGGLE_INHIBITOR (Direct): FAILED (field would cross sector boundary).")
                return False

            for existing_zone in current_hex.get_all_inhibition_zones():
                if do_circles_intersect(proposed_field, existing_zone):
                    logger.debug(f"[{self.unit.name}] TOGGLE_INHIBITOR (Direct): FAILED (field would overlap with another).")
                    return False
            
            self.turn_on()
            current_hex.dynamic_inhibition_zones[self.unit.id] = proposed_field
            return True
