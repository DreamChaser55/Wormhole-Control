import logging
from typing import TYPE_CHECKING

from .base import UnitComponent
from constants import CLOAKING_ANTIMATTER_COST_PER_TURN, CLOAKING_HULL_COST

if TYPE_CHECKING:
    from entities import Unit
    from game import Game

logger = logging.getLogger(__name__)


class CloakingDevice(UnitComponent):
    """Component that hides a unit from enemy long-range (inter-sector) sensors.

    When activated, the cloaking field renders the unit invisible to enemy
    long-range sensor sweeps across hex boundaries. Short-range in-sector
    sensors can still detect the unit at normal range.

    The device consumes CLOAKING_ANTIMATTER_COST_PER_TURN antimatter each
    turn while active. If the unit's antimatter storage runs dry, the cloak
    is automatically deactivated.
    """

    DISPLAY_NAME: str = "Cloaking Device"
    SIDEBAR_ORDER: int = 5

    def __init__(self, unit: 'Unit', hull_cost: float = CLOAKING_HULL_COST):
        super().__init__(unit, hull_cost=hull_cost)
        self.is_active: bool = False

    @staticmethod
    def calc_hull_cost(hull_cost: float = CLOAKING_HULL_COST) -> float:
        """Return the hull cost of a Cloaking Device component."""
        return float(hull_cost)

    # ------------------------------------------------------------------
    # Activation helpers
    # ------------------------------------------------------------------

    def activate(self) -> None:
        """Activate the cloaking field. No-ops if destroyed."""
        if self.is_destroyed:
            return
        self.is_active = True
        logger.debug(f"[{self.unit.name}] Cloaking Device activated.")

    def deactivate(self) -> None:
        """Deactivate the cloaking field."""
        self.is_active = False
        logger.debug(f"[{self.unit.name}] Cloaking Device deactivated.")

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
        if not am_comp:
            logger.debug(
                f"[{self.unit.name}] Cloaking Device deactivated: no AntimatterStorage on unit."
            )
            self.deactivate()
            return

        consumed = am_comp.consume(CLOAKING_ANTIMATTER_COST_PER_TURN)
        if not consumed:
            logger.debug(
                f"[{self.unit.name}] Cloaking Device deactivated: insufficient antimatter "
                f"({am_comp.current_amount:.1f} < {CLOAKING_ANTIMATTER_COST_PER_TURN:.1f})."
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
        data.append({
            'type': 'cloaking_button',
            'is_active': self.is_active,
            'height': 30
        })
        am_cost_text = f"AM Cost: {CLOAKING_ANTIMATTER_COST_PER_TURN:.1f}/turn"
        data.append({'type': 'label', 'text': am_cost_text, 'object_id': '#sidebar_info_label', 'height': 20})
        return data

    def get_basic_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_basic_sidebar_data(game_state)
        if self.is_destroyed:
            return data
        status_str = "Active" if self.is_active else "Inactive"
        obj_id = '#sidebar_status_active_label' if self.is_active else '#sidebar_status_idle_label'
        data.append({
            'type': 'label',
            'text': f"• Cloaking: {status_str} ({CLOAKING_ANTIMATTER_COST_PER_TURN:.1f} AM/turn)",
            'object_id': obj_id,
            'height': 18,
            'indent_level': 1
        })
        return data
