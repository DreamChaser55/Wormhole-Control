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


class ClusterWarheadAbility(AbilityInstance):
    DEFINITION = AbilityDefinition(
        ability_type=AbilityType.CLUSTER_WARHEAD,
        name="Cluster Warhead",
        description="Fires a missile that deals heavy splash damage at a target position.",
        cooldown=5,
        duration=0,
        range=500.0,
        requires_target_unit=False,
        requires_target_position=True,
        antimatter_cost=30,
    )

    SPLASH_RADIUS: float = 200.0
    BASE_DAMAGE: int = 80

    def on_activate(
        self,
        component: 'AbilityComponent',
        galaxy: 'Galaxy',
        target_unit_id: Optional[int] = None,
        target_position: Optional[Position] = None,
        target_system_name: Optional[str] = None,
        target_hex_coord: Optional[HexCoord] = None,
    ) -> bool:
        if target_position is None:
            logger.debug(f"[{component.unit.name}] Cluster Warhead requires a target position.")
            return False

        self._apply_splash_damage(
            component,
            galaxy,
            target_position,
            target_system_name=target_system_name,
            target_hex_coord=target_hex_coord,
        )
        return True

    def _apply_splash_damage(
        self,
        component: 'AbilityComponent',
        galaxy: 'Galaxy',
        target_position: Position,
        target_system_name: Optional[str] = None,
        target_hex_coord: Optional[HexCoord] = None,
    ) -> None:
        """Deals splash damage to all units at the target position within SPLASH_RADIUS."""
        sys_name = target_system_name if target_system_name is not None else component.unit.in_system
        hex_coord = target_hex_coord if target_hex_coord is not None else component.unit.in_hex

        system = galaxy.systems.get(sys_name)
        if not system:
            return
        hex_obj = system.hexes.get(hex_coord)
        if not hex_obj:
            return
        for target_unit in list(hex_obj.units):
            if target_unit is component.unit:
                continue
            dist = distance(target_unit.position, target_position)
            if dist <= self.SPLASH_RADIUS:
                # Damage falls off linearly with distance
                falloff = max(0.0, 1.0 - (dist / self.SPLASH_RADIUS))
                damage = max(1, int(self.BASE_DAMAGE * falloff))
                target_unit.take_damage(damage)
                logger.debug(f"[Cluster Warhead] Hit {target_unit.name} for {damage} damage (dist={dist:.1f}).")
