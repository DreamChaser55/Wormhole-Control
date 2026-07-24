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


class IonBoltAbility(AbilityInstance):
    DEFINITION = AbilityDefinition(
        ability_type=AbilityType.ION_BOLT,
        name="Ion Bolt",
        description="Disables a target unit, preventing movement and attacks for 3 turns.",
        cooldown=7,
        duration=3,
        range=400.0,
        requires_target_unit=True,
        requires_target_position=False,
        antimatter_cost=25,
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
            logger.debug(f"[{component.unit.name}] Ion Bolt requires a target unit.")
            return False
        target_unit = galaxy.get_unit_by_id(target_unit_id)
        if not target_unit:
            logger.debug(f"[{component.unit.name}] Ion Bolt: target unit {target_unit_id} not found.")
            return False

        target_unit.is_disabled = True
        target_unit.disabled_by_unit_ids.add(component.unit.id)
        self.target_unit_id = target_unit_id
        logger.debug(f"[{component.unit.name}] Ion Bolt disabled {target_unit.name}.")
        return True

    def on_expire(self, component: 'AbilityComponent', galaxy: 'Galaxy') -> None:
        if self.target_unit_id is not None:
            target_unit = galaxy.get_unit_by_id(self.target_unit_id)
            if target_unit:
                target_unit.disabled_by_unit_ids.discard(component.unit.id)
                if not target_unit.disabled_by_unit_ids:
                    target_unit.is_disabled = False
                logger.debug(f"[{component.unit.name}] Ion Bolt expired on {target_unit.name}. Disabled: {target_unit.is_disabled}.")
        self.target_unit_id = None
