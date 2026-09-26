import logging
from game_logging import format_unit_for_log
from typing import Optional, TYPE_CHECKING
from geometry import Position
from domain.coordinates import HexCoord
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
            logger.debug(f"[{format_unit_for_log(component.unit)}] Drain Antimatter requires a target unit.")
            return False

        target_unit = galaxy.get_unit_by_id(target_unit_id)
        if not target_unit:
            logger.debug(f"[{format_unit_for_log(component.unit)}] Drain Antimatter: target unit {target_unit_id} not found.")
            return False

        from domain.players import are_allies
        if are_allies(target_unit.owner, component.unit.owner):
            logger.debug(f"[{format_unit_for_log(component.unit)}] Drain Antimatter: target unit {format_unit_for_log(target_unit)} is friendly/allied.")
            return False

        source_am = component.unit.antimatter_component
        if not source_am or source_am.is_destroyed:
            logger.debug(f"[{format_unit_for_log(component.unit)}] Drain Antimatter failed: source unit has no active antimatter storage.")
            return False

        target_am = target_unit.antimatter_component
        if not target_am or target_am.is_destroyed or target_am.current_amount <= 0:
            logger.debug(f"[{format_unit_for_log(component.unit)}] Drain Antimatter failed: target {format_unit_for_log(target_unit)} has no antimatter to drain.")
            return False

        drain_cap = 30.0
        drain_amount = min(drain_cap, target_am.current_amount)

        if drain_amount <= 0:
            return False

        target_am.current_amount -= drain_amount
        from turn_briefing import unit_event
        unit_event(target_unit, "combat", "Antimatter drained (AM)", actor=component.unit, amount=drain_amount)
        added = source_am.add(drain_amount)

        logger.debug(
            f"[{format_unit_for_log(component.unit)}] Drained {drain_amount:.1f} antimatter from {format_unit_for_log(target_unit)} "
            f"(target left with {target_am.current_amount:.1f}, source added {added:.1f})."
        )
        return True
