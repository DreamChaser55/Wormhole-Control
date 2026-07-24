import logging
from typing import Optional, TYPE_CHECKING
from geometry import Position, distance
from utils import HexCoord
from ..enums import AbilityType
from .base import AbilityDefinition, AbilityInstance

if TYPE_CHECKING:
    from galaxy import Galaxy
    from .component import AbilityComponent

logger = logging.getLogger(__name__)


class RepairCloudAbility(AbilityInstance):
    DEFINITION = AbilityDefinition(
        ability_type=AbilityType.REPAIR_CLOUD,
        name="Repair Cloud",
        description="Disperses repair nanites that restore 5 HP per turn to all friendly ships within 350 units for 4 turns.",
        cooldown=8,
        duration=4,
        range=350.0,
        requires_target_unit=False,
        requires_target_position=False,
        antimatter_cost=35,
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
        logger.debug(f"[{component.unit.name}] Repair Cloud activated. Healing friendlies within {self.DEFINITION.range} units for {self.DEFINITION.duration} turns.")
        return True

    def on_turn_update(self, component: 'AbilityComponent', galaxy: 'Galaxy') -> None:
        self._apply_repair_cloud(component, galaxy)

    def on_expire(self, component: 'AbilityComponent', galaxy: 'Galaxy') -> None:
        logger.debug(f"[{component.unit.name}] Repair Cloud expired.")

    def _apply_repair_cloud(self, component: 'AbilityComponent', galaxy: 'Galaxy') -> None:
        """Heals all friendly units within Repair Cloud range by 5 HP."""
        system = galaxy.systems.get(component.unit.in_system)
        if not system:
            return
        hex_obj = system.hexes.get(component.unit.in_hex)
        if not hex_obj:
            return
        heal_per_turn = 5
        for unit in hex_obj.units:
            if unit.owner != component.unit.owner:
                continue
            if distance(component.unit.position, unit.position) <= self.DEFINITION.range:
                unit.heal_hull(heal_per_turn)
                logger.debug(f"[Repair Cloud] Healed {unit.name} for {heal_per_turn} HP.")
