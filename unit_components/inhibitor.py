import logging
from typing import Any, Iterable, Optional, TYPE_CHECKING
import dataclasses

from geometry import Circle, do_circles_intersect, is_circle_contained

from constants import INHIBITOR_RADIUS_PER_HULL_POINT, INHIBITOR_ANTIMATTER_COST_PER_50_RADIUS
from .base import UnitComponent

if TYPE_CHECKING:
    from entities import Unit
    from galaxy import Galaxy
    from game import Game

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class InhibitorStateCheck:
    """Side-effect-free result for a requested inhibitor state change."""

    allowed: bool
    code: Optional[str] = None
    message: str = ""
    proposed_field: Optional[Circle] = None


class HyperspaceInhibitionFieldEmitter(UnitComponent):
    """A component that generates a hyperspace inhibition field, preventing jumps."""
    DISPLAY_NAME: str = "Inhibitor"
    SIDEBAR_ORDER: int = 4
    radius: float = 50.0
    is_active: bool = False

    def __init__(self, unit: 'Unit', radius: float = 50.0, hull_cost: float = 20.0):
        super().__init__(unit, hull_cost=hull_cost)
        self.radius = radius
        self.is_active = False

    @staticmethod
    def calc_hull_cost(radius: float) -> float:
        """Compute the hull cost of a Hyperspace Inhibitor component from inhibitor_radius."""
        if radius <= 0:
            return 0.0
        return float(radius / INHIBITOR_RADIUS_PER_HULL_POINT)

    def get_antimatter_cost_per_turn(self) -> float:
        """Calculates antimatter consumption per turn based on field radius."""
        return (float(self.radius) / 50.0) * INHIBITOR_ANTIMATTER_COST_PER_50_RADIUS

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        data.append({
            'type': 'inhibitor_button',
            'is_active': self.is_active,
            'height': 30
        })
        am_cost_text = f"AM Cost: {self.get_antimatter_cost_per_turn():.1f}/turn"
        data.append({'type': 'label', 'text': am_cost_text, 'object_id': '#sidebar_info_label', 'height': 20})
        return data

    def get_basic_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_basic_sidebar_data(game_state)
        if self.is_destroyed:
            return data
        status_str = "Active" if self.is_active else "Inactive"
        obj_id = '#sidebar_status_active_label' if self.is_active else '#sidebar_status_idle_label'
        cost_str = f" ({self.get_antimatter_cost_per_turn():.1f} AM/turn)" if self.is_active else ""
        data.append({
            'type': 'label',
            'text': f"• FTL Inhibition: {status_str}{cost_str} (Radius {int(self.radius)})",
            'object_id': obj_id,
            'height': 18,
            'indent_level': 1
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
        """Deactivates the inhibition field and cleans up registered spatial zone."""
        if self.is_active:
            galaxy_ref = getattr(self.unit, 'in_galaxy', None)
            if galaxy_ref and self.unit.in_system and self.unit.in_hex is not None:
                system_obj = galaxy_ref.systems.get(self.unit.in_system)
                if system_obj and self.unit.in_hex in system_obj.hexes:
                    current_hex = system_obj.hexes[self.unit.in_hex]
                    if self.unit.id in current_hex.dynamic_inhibition_zones:
                        del current_hex.dynamic_inhibition_zones[self.unit.id]
        self.is_active = False
        logger.debug(f"Unit {self.unit.name} inhibition field deactivated.")

    def update(self) -> None:
        """Consume antimatter while active. Auto-deactivate if empty or missing storage."""
        if not self.is_active or self.is_destroyed:
            return

        cost = self.get_antimatter_cost_per_turn()
        am_comp = getattr(self.unit, 'antimatter_component', None)
        if not am_comp:
            logger.debug(
                f"[{self.unit.name}] Inhibitor Field deactivated: no AntimatterStorage on unit."
            )
            self.turn_off()
            return

        consumed = am_comp.consume(cost)
        if not consumed:
            logger.debug(
                f"[{self.unit.name}] Inhibitor Field deactivated: insufficient antimatter "
                f"({am_comp.current_amount:.1f} < {cost:.1f})."
            )
            self.turn_off()

    def on_destroyed(self) -> None:
        if self.is_active:
            self.turn_off()

    def check_state_change(
        self,
        turn_on: bool,
        galaxy_ref: 'Galaxy',
        *,
        existing_zones: Optional[Iterable[Circle]] = None,
    ) -> InhibitorStateCheck:
        """Validate a requested state without changing authoritative game state."""
        if self.is_destroyed:
            return InhibitorStateCheck(
                False,
                "inhibitor_unavailable",
                "The inhibitor component is destroyed.",
            )

        current_hex = self._current_hex(galaxy_ref)
        if current_hex is None:
            return InhibitorStateCheck(
                False,
                "inhibitor_unavailable",
                "The unit does not have a valid sector location.",
            )

        if not turn_on:
            return InhibitorStateCheck(True)

        proposed_field = Circle(center=self.unit.position, radius=self.radius)
        if not is_circle_contained(proposed_field, current_hex.boundary_circle):
            return InhibitorStateCheck(
                False,
                "inhibitor_out_of_bounds",
                "The inhibitor field would cross the sector boundary.",
                proposed_field,
            )

        zones = (
            list(existing_zones)
            if existing_zones is not None
            else current_hex.get_all_inhibition_zones()
        )
        if any(do_circles_intersect(proposed_field, zone) for zone in zones):
            return InhibitorStateCheck(
                False,
                "inhibitor_overlap",
                "The inhibitor field would overlap an existing inhibition zone.",
                proposed_field,
            )

        return InhibitorStateCheck(True, proposed_field=proposed_field)

    def set_active(self, turn_on: bool, galaxy_ref: 'Galaxy') -> InhibitorStateCheck:
        """Apply an explicitly requested state after authoritative validation."""
        check = self.check_state_change(turn_on, galaxy_ref)
        if not check.allowed:
            logger.debug(
                "[%s] SET_INHIBITOR: FAILED (%s).",
                self.unit.name,
                check.message,
            )
            return check

        current_hex = self._current_hex(galaxy_ref)
        if current_hex is None:
            return InhibitorStateCheck(
                False,
                "inhibitor_unavailable",
                "The unit does not have a valid sector location.",
            )

        if turn_on:
            self.turn_on()
            current_hex.dynamic_inhibition_zones[self.unit.id] = check.proposed_field
        else:
            current_hex.dynamic_inhibition_zones.pop(self.unit.id, None)
            self.turn_off()
        return check

    def _current_hex(self, galaxy_ref: 'Galaxy') -> Any | None:
        if not galaxy_ref or not self.unit.in_system or self.unit.in_hex is None:
            return None
        system = getattr(galaxy_ref, "systems", {}).get(self.unit.in_system)
        if system is None:
            return None
        return getattr(system, "hexes", {}).get(self.unit.in_hex)

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
        return self.set_active(not self.is_active, galaxy_ref).allowed
