import logging
from typing import Optional, TYPE_CHECKING
from geometry import Position
from utils import HexCoord
from ..enums import AbilityType
from .base import AbilityDefinition, AbilityInstance

if TYPE_CHECKING:
    from galaxy import Galaxy
    from .component import AbilityComponent

logger = logging.getLogger(__name__)


class DrainAntimatterAbility(AbilityInstance):
    DEFINITION = AbilityDefinition(
        ability_type=AbilityType.DRAIN_ANTIMATTER,
        name="Drain Antimatter",
        description="Drains up to 30.0 antimatter from an enemy unit within range (300 units) and transfers it to this unit.",
        cooldown=6,
        duration=0,
        range=300.0,
        requires_target_unit=True,
        requires_target_position=False,
        antimatter_cost=0,
        required_components=["has_antimatter_storage"],
    )

    def on_activate(
        self,
        component: 'AbilityComponent',
        galaxy: 'Galaxy',
        target_unit_id: Optional[int] = None,
        target_position: Optional[Position] = None,
        target_system_name: Optional[str] = None,
        target_hex_coord: Optional[HexCoord] = None,
    ) -> bool:
        if target_unit_id is None:
            logger.debug(f"[{component.unit.name}] Drain Antimatter requires a target unit.")
            return False

        target_unit = galaxy.get_unit_by_id(target_unit_id)
        if not target_unit:
            logger.debug(f"[{component.unit.name}] Drain Antimatter: target unit {target_unit_id} not found.")
            return False

        from entities import are_allies
        if are_allies(target_unit.owner, component.unit.owner):
            logger.debug(f"[{component.unit.name}] Drain Antimatter: target unit {target_unit.name} is friendly/allied.")
            return False

        source_am = component.unit.antimatter_component
        if not source_am or source_am.is_destroyed:
            logger.debug(f"[{component.unit.name}] Drain Antimatter failed: source unit has no active antimatter storage.")
            return False

        target_am = target_unit.antimatter_component
        if not target_am or target_am.is_destroyed or target_am.current_amount <= 0:
            logger.debug(f"[{component.unit.name}] Drain Antimatter failed: target {target_unit.name} has no antimatter to drain.")
            return False

        drain_cap = 30.0
        drain_amount = min(drain_cap, target_am.current_amount)

        if drain_amount <= 0:
            return False

        target_am.current_amount -= drain_amount
        added = source_am.add(drain_amount)

        logger.debug(
            f"[{component.unit.name}] Drained {drain_amount:.1f} antimatter from {target_unit.name} "
            f"(target left with {target_am.current_amount:.1f}, source added {added:.1f})."
        )
        return True
