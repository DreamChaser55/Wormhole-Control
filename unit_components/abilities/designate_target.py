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


class DesignateTargetAbility(AbilityInstance):
    DEFINITION = AbilityDefinition(
        ability_type=AbilityType.DESIGNATE_TARGET,
        name="Designate Target",
        description="Marks an enemy unit. Friendly units deal +50% damage against it for 4 turns.",
        cooldown=6,
        duration=4,
        range=450.0,
        requires_target_unit=True,
        requires_target_position=False,
        antimatter_cost=15,
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
            logger.debug(f"[{component.unit.name}] Designate Target requires a target unit.")
            return False
        target_unit = galaxy.get_unit_by_id(target_unit_id)
        if not target_unit:
            logger.debug(f"[{component.unit.name}] Designate Target: target unit {target_unit_id} not found.")
            return False

        target_unit.damage_amplification += 0.5
        self.target_unit_id = target_unit_id
        logger.debug(f"[{component.unit.name}] Designate Target applied to {target_unit.name}. Amplification now: {target_unit.damage_amplification:.2f}.")
        return True

    def on_expire(self, component: 'AbilityComponent', galaxy: 'Galaxy') -> None:
        if self.target_unit_id is not None:
            target_unit = galaxy.get_unit_by_id(self.target_unit_id)
            if target_unit:
                target_unit.damage_amplification = max(0.0, target_unit.damage_amplification - 0.5)
                logger.debug(f"[{component.unit.name}] Designate Target expired on {target_unit.name}. Amplification now: {target_unit.damage_amplification:.2f}.")
        self.target_unit_id = None
