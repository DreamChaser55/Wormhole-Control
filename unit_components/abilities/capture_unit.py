import logging
from typing import Optional, TYPE_CHECKING
from geometry import Position
from utils import HexCoord
from ..enums import AbilityType, UnitStance
from ..defenses import Defenses
from .base import AbilityDefinition, AbilityInstance

if TYPE_CHECKING:
    from galaxy import Galaxy
    from .component import AbilityComponent

logger = logging.getLogger(__name__)


class CaptureUnitAbility(AbilityInstance):
    DEFINITION = AbilityDefinition(
        ability_type=AbilityType.CAPTURE_UNIT,
        name="Capture Unit",
        description="Captures an enemy unit within very short range (100 units). Target unit must be disabled and defenseless (weapons and defenses destroyed or missing).",
        cooldown=10,
        duration=0,
        range=100.0,
        requires_target_unit=True,
        requires_target_position=False,
        antimatter_cost=40,
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
            logger.debug(f"[{component.unit.name}] Capture Unit requires a target unit.")
            return False
        target_unit = galaxy.get_unit_by_id(target_unit_id)
        if not target_unit:
            logger.debug(f"[{component.unit.name}] Capture Unit: target unit {target_unit_id} not found.")
            return False

        if target_unit.owner == component.unit.owner:
            logger.debug(f"[{component.unit.name}] Capture Unit: target unit {target_unit.name} is already friendly.")
            return False

        if target_unit.engines_component is not None:
            engines_disabled = target_unit.engines_component.is_destroyed or target_unit.is_disabled
            if not engines_disabled:
                logger.debug(f"[{component.unit.name}] Capture Unit failed: target {target_unit.name} engines are not disabled.")
                return False

        if target_unit.weapons_component and not target_unit.weapons_component.is_destroyed:
            logger.debug(f"[{component.unit.name}] Capture Unit failed: target {target_unit.name} weapons are active.")
            return False

        defenses = target_unit.get_component(Defenses)
        if defenses and not defenses.is_destroyed:
            logger.debug(f"[{component.unit.name}] Capture Unit failed: target {target_unit.name} defenses are active.")
            return False

        # Transfer ownership
        old_owner = target_unit.owner
        target_unit.owner = component.unit.owner

        # Reset targets and stance of the captured unit to prevent unwanted behaviors
        if target_unit.commander_component:
            target_unit.commander_component.clear_orders()
            target_unit.commander_component.stance = UnitStance.DO_NOTHING

        if target_unit.weapons_component:
            target_unit.weapons_component.clear_target()

        logger.debug(f"[{component.unit.name}] Captured unit {target_unit.name} (id:{target_unit.id}) from player {old_owner.id if old_owner else 'None'} to player {component.unit.owner.id}.")
        return True
