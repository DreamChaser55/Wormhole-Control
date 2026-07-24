import logging
from typing import Optional, TYPE_CHECKING
import dataclasses

from .base import UnitComponent
from geometry import distance

if TYPE_CHECKING:
    from entities import Unit
    from galaxy import Galaxy
    from game import Game

logger = logging.getLogger(__name__)

class RepairComponent(UnitComponent):
    """A component that allows a unit to repair damaged friendly units."""
    DISPLAY_NAME: str = "Repair"
    SIDEBAR_ORDER: int = 10
    repair_rate: float = 10.0
    repair_range: float = 200.0
    credit_cost_per_hp: float = 1.0
    target: Optional['Unit'] = None

    def __init__(self, unit: 'Unit', repair_rate: float = 10.0, repair_range: float = 200.0, credit_cost_per_hp: float = 1.0, hull_cost: int = 15):
        super().__init__(unit, hull_cost=hull_cost)
        self.repair_rate = repair_rate
        self.repair_range = repair_range
        self.credit_cost_per_hp = credit_cost_per_hp
        self.target = None

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        data.append({'type': 'label', 'text': f"Repair Rate: {self.repair_rate} HP/turn", 'object_id': '#sidebar_info_label', 'height': 20})
        data.append({'type': 'label', 'text': f"Repair Range: {self.repair_range}", 'object_id': '#sidebar_info_label', 'height': 20})
        target_name = self.target.name if self.target else "None"
        data.append({'type': 'label', 'text': f"Repair Target: {target_name}", 'object_id': '#sidebar_info_label', 'height': 20})
        return data

    def set_target(self, target_unit: 'Unit') -> None:
        self.target = target_unit

    def clear_target(self) -> None:
        self.target = None

    def update(self, galaxy: 'Galaxy') -> None:
        if self.is_destroyed:
            return

        if not self.target:
            return

        target_valid = (
            self.target.current_hit_points > 0 and
            self.target.owner == self.unit.owner and
            self.unit.in_system == self.target.in_system and
            self.unit.in_hex == self.target.in_hex and
            distance(self.unit.position, self.target.position) <= self.repair_range
        )

        if not target_valid:
            return

        needs_hull_repair = self.target.current_hit_points < self.target.max_hit_points
        damaged_components = [c for c in self.target.components.values() if c.current_hit_points < c.max_hit_points]

        if not needs_hull_repair and not damaged_components:
            return

        player = self.unit.owner
        if player.credits <= 0:
            logger.debug(f"Repair by {self.unit.name} on {self.target.name} halted due to insufficient credits.")
            return

        max_hp_to_repair = min(self.repair_rate, player.credits / self.credit_cost_per_hp)
        if max_hp_to_repair < 1.0:
            return

        repair_budget = int(max_hp_to_repair)
        hp_repaired = 0

        if needs_hull_repair:
            healed = self.target.heal_hull(repair_budget)
            hp_repaired += healed
            repair_budget -= healed

        if repair_budget > 0 and damaged_components:
            healed = self.target.heal_components(repair_budget)
            hp_repaired += healed
            repair_budget -= healed

        if hp_repaired > 0:
            cost = int(hp_repaired * self.credit_cost_per_hp)
            player.credits = max(0, player.credits - cost)
            logger.debug(f"Unit {self.unit.name} repaired {self.target.name} for {hp_repaired} HP, costing {cost} credits.")
