import logging
from typing import TYPE_CHECKING, Optional, Union

from .base import UnitComponent
from .enums import CloakingType
from constants import (
    CLOAKING_BASIC_HULL_COST,
    CLOAKING_ADVANCED_HULL_COST,
    CLOAKING_BASIC_ANTIMATTER_COST_PER_TURN,
    CLOAKING_ADVANCED_ANTIMATTER_COST_PER_TURN,
    DEFAULT_ADVANCED_CLOAKING_RADIUS,
)
from geometry import distance, Position

if TYPE_CHECKING:
    from entities import Unit
    from game import Game

logger = logging.getLogger(__name__)


class CloakingDevice(UnitComponent):
    """Component that hides units from enemy long-range (inter-sector) sensors.

    Types:
    - BASIC: Renders the mounting unit invisible to enemy long-range sensors.
    - ADVANCED: Generates an area-of-effect stealth field hiding the unit and all
      friendly units within its area radius from enemy long-range sensors.

    Short-range in-sector sensors can still detect units within normal visual range.
    The device consumes antimatter each turn while active and auto-deactivates if empty.
    """

    DISPLAY_NAME: str = "Cloaking Device"
    SIDEBAR_ORDER: int = 5

    def __init__(
        self,
        unit: 'Unit',
        device_type: Union[CloakingType, str] = CloakingType.BASIC,
        area_radius: Optional[float] = None,
        hull_cost: Optional[float] = None,
    ):
        if isinstance(device_type, str):
            dtype = CloakingType.ADVANCED if device_type.upper() == "ADVANCED" else CloakingType.BASIC
        else:
            dtype = device_type

        if dtype == CloakingType.ADVANCED:
            radius = (
                DEFAULT_ADVANCED_CLOAKING_RADIUS
                if area_radius is None or area_radius <= 0
                else float(area_radius)
            )
        else:
            radius = 0.0

        if hull_cost is None:
            hull_cost = CloakingDevice.calc_hull_cost(dtype, area_radius=radius)

        super().__init__(unit, hull_cost=hull_cost)
        self.device_type: CloakingType = dtype
        self.area_radius: float = radius
        self.is_active: bool = False

    @staticmethod
    def calc_hull_cost(
        device_type: Union[CloakingType, str] = CloakingType.BASIC,
        area_radius: float = DEFAULT_ADVANCED_CLOAKING_RADIUS,
        **kwargs
    ) -> float:
        """Return the hull cost of a Cloaking Device component based on its type and area radius."""
        dtype_str = device_type.value if isinstance(device_type, CloakingType) else str(device_type)
        if dtype_str.upper() == "ADVANCED":
            if area_radius <= 0:
                return 0.0
            return float((area_radius / DEFAULT_ADVANCED_CLOAKING_RADIUS) * CLOAKING_ADVANCED_HULL_COST)
        return float(CLOAKING_BASIC_HULL_COST)

    def get_antimatter_cost_per_turn(self) -> float:
        """Return antimatter consumption per turn while active."""
        if self.device_type == CloakingType.ADVANCED:
            if self.area_radius <= 0:
                return 0.0
            return float((self.area_radius / DEFAULT_ADVANCED_CLOAKING_RADIUS) * CLOAKING_ADVANCED_ANTIMATTER_COST_PER_TURN)
        return float(CLOAKING_BASIC_ANTIMATTER_COST_PER_TURN)

    def is_point_cloaked(self, target_pos: Position) -> bool:
        """Check if a target position is within this device's active cloaking coverage."""
        if not self.is_active or self.is_destroyed:
            return False
        if self.device_type == CloakingType.ADVANCED:
            return distance(self.unit.position, target_pos) <= self.area_radius
        return self.unit.position == target_pos

    # ------------------------------------------------------------------
    # Activation helpers
    # ------------------------------------------------------------------

    def activate(self) -> None:
        """Activate the cloaking field. No-ops if destroyed."""
        if self.is_destroyed:
            return
        self.is_active = True
        logger.debug(f"[{self.unit.name}] Cloaking Device ({self.device_type.value}) activated.")

    def deactivate(self) -> None:
        """Deactivate the cloaking field."""
        self.is_active = False
        logger.debug(f"[{self.unit.name}] Cloaking Device ({self.device_type.value}) deactivated.")

    def toggle(self) -> bool:
        """Toggle the cloaking field on or off.

        Returns:
            bool: True if the toggle was applied successfully.
                  False if the toggle failed (e.g. component is destroyed).
        """
        if self.is_destroyed:
            logger.debug(f"[{self.unit.name}] Cloaking Device toggle failed: component is destroyed.")
            return False
        if self.is_active:
            self.deactivate()
        else:
            self.activate()
        return True

    # ------------------------------------------------------------------
    # Per-turn update
    # ------------------------------------------------------------------

    def update(self) -> None:
        """Consume antimatter while cloaked. Auto-deactivate if empty."""
        if not self.is_active or self.is_destroyed:
            return

        am_comp = self.unit.antimatter_component
        cost = self.get_antimatter_cost_per_turn()
        if not am_comp:
            logger.debug(
                f"[{self.unit.name}] Cloaking Device deactivated: no AntimatterStorage on unit."
            )
            self.deactivate()
            return

        consumed = am_comp.consume(cost)
        if not consumed:
            logger.debug(
                f"[{self.unit.name}] Cloaking Device deactivated: insufficient antimatter "
                f"({am_comp.current_amount:.1f} < {cost:.1f})."
            )
            self.deactivate()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_destroyed(self) -> None:
        """Deactivate cloak if the component is destroyed."""
        if self.is_active:
            self.deactivate()

    # ------------------------------------------------------------------
    # Sidebar UI
    # ------------------------------------------------------------------

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        type_text = f"Type: {self.device_type.display_name}"
        if self.device_type == CloakingType.ADVANCED:
            type_text += f" (Radius: {int(self.area_radius)})"
        data.append({'type': 'label', 'text': type_text, 'object_id': '#sidebar_info_label', 'height': 20})
        data.append({
            'type': 'cloaking_button',
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
        radius_str = f", Radius {int(self.area_radius)}" if self.device_type == CloakingType.ADVANCED else ""
        data.append({
            'type': 'label',
            'text': f"• Cloaking ({self.device_type.display_name}): {status_str} ({self.get_antimatter_cost_per_turn():.1f} AM/turn{radius_str})",
            'object_id': obj_id,
            'height': 18,
            'indent_level': 1
        })
        return data

