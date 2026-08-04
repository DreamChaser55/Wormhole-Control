import logging
import random
from typing import Optional, TYPE_CHECKING
from geometry import Position
from utils import HexCoord
from ..enums import AbilityType, UnitStance
from ..defenses import Defenses
from ..marines import MarinesComponent
from .base import AbilityDefinition, AbilityInstance

if TYPE_CHECKING:
    from galaxy import Galaxy
    from .component import AbilityComponent

logger = logging.getLogger(__name__)


class CaptureUnitAbility(AbilityInstance):
    DEFINITION = AbilityDefinition(
        ability_type=AbilityType.CAPTURE_UNIT,
        name="Capture Unit",
        description="Captures an enemy unit within very short range (100 units). Target unit must be disabled and defenseless. Requires Marines component; capture probability scales with marine count.",
        cooldown=10,
        duration=0,
        range=100.0,
        requires_target_unit=True,
        requires_target_position=False,
        antimatter_cost=40,
        required_components=["has_marines_component"],
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

        marines_comp = component.unit.get_component(MarinesComponent)
        marines_count = marines_comp.marines_count if marines_comp else 0
        if marines_count <= 0:
            logger.debug(f"[{component.unit.name}] Capture Unit failed: no active marines available on board.")
            return False

        target_capacity = getattr(target_unit, "hull_capacity", 50.0)
        req_marines = max(1.0, target_capacity / 5.0)
        success_prob = min(1.0, marines_count / req_marines)

        roll = random.random()
        if roll >= success_prob:
            logger.debug(
                f"[{component.unit.name}] Capture Unit failed roll ({roll:.2f} >= {success_prob:.2f}) "
                f"with {marines_count} marines against {target_unit.name}."
            )
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

        logger.debug(
            f"[{component.unit.name}] Captured unit {target_unit.name} (id:{target_unit.id}) from player "
            f"{old_owner.id if old_owner else 'None'} to player {component.unit.owner.id} "
            f"with {marines_count} marines (success prob: {success_prob:.0%})."
        )
        return True
