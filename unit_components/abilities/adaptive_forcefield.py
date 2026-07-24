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


class AdaptiveForcefieldAbility(AbilityInstance):
    DEFINITION = AbilityDefinition(
        ability_type=AbilityType.ADAPTIVE_FORCEFIELD,
        name="Adaptive Forcefield",
        description="Reduces incoming damage by 75% for 3 turns.",
        cooldown=8,
        duration=3,
        range=0.0,
        requires_target_unit=False,
        requires_target_position=False,
        antimatter_cost=20,
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
        component.unit.damage_reduction = 0.75
        logger.debug(f"[{component.unit.name}] Adaptive Forcefield activated. Damage reduction: 75%.")
        return True

    def on_expire(self, component: 'AbilityComponent', galaxy: 'Galaxy') -> None:
        component.unit.damage_reduction = max(0.0, component.unit.damage_reduction - 0.75)
        logger.debug(f"[{component.unit.name}] Adaptive Forcefield expired. Damage reduction removed.")
