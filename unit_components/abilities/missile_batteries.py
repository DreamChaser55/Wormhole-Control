import logging
import math
from typing import Optional, List, TYPE_CHECKING
from geometry import Position, distance
from constants import HullSize
from utils import HexCoord
from ..enums import AbilityType, TurretType
from ..weapons import Weapons, Turret
from .base import AbilityDefinition, AbilityInstance

if TYPE_CHECKING:
    from galaxy import Galaxy
    from .component import AbilityComponent

logger = logging.getLogger(__name__)


class MissileBatteriesAbility(AbilityInstance):
    DEFINITION = AbilityDefinition(
        ability_type=AbilityType.MISSILE_BATTERIES,
        name="Missile Batteries",
        description="Deploys 3 missile platforms that automatically attack enemies for 4 turns.",
        cooldown=10,
        duration=4,
        range=0.0,
        requires_target_unit=False,
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
        spawned = self._spawn_missile_platforms(component, galaxy, self.DEFINITION.duration)
        self.spawned_unit_ids = spawned
        logger.debug(f"[{component.unit.name}] Missile Batteries: spawned {len(spawned)} platforms.")
        return True

    def on_turn_update(self, component: 'AbilityComponent', galaxy: 'Galaxy') -> None:
        self._auto_target_platforms(component, galaxy)

    def on_expire(self, component: 'AbilityComponent', galaxy: 'Galaxy') -> None:
        system = galaxy.systems.get(component.unit.in_system)
        if system:
            for uid in self.spawned_unit_ids:
                platform = galaxy.get_unit_by_id(uid)
                if platform:
                    galaxy.remove_unit(platform)
                    logger.debug(f"[{component.unit.name}] Missile Platform {uid} despawned.")
        self.spawned_unit_ids = []

    def _spawn_missile_platforms(
        self,
        component: 'AbilityComponent',
        galaxy: 'Galaxy',
        lifetime: int,
        num_platforms: int = 3,
        deploy_radius: float = 60.0,
    ) -> List[int]:
        """Spawns temporary missile platform units around the caster and returns their IDs."""
        from entities import Unit
        spawned_ids = []
        for i in range(num_platforms):
            angle = (2 * math.pi / num_platforms) * i
            px = component.unit.position.x + deploy_radius * math.cos(angle)
            py = component.unit.position.y + deploy_radius * math.sin(angle)
            platform_pos = Position(px, py)

            platform = Unit(
                owner=component.unit.owner,
                position=platform_pos,
                in_hex=component.unit.in_hex,
                in_system=component.unit.in_system,
                name="Missile Platform",
                hull_size=HullSize.TINY,
                game=component.unit.game,
            )
            platform.lifetime = lifetime
            platform.is_temporary = True

            # Add a weapons component with a single missile turret
            weapons_comp = Weapons(platform, hull_cost=0)
            turret = Turret(
                turret_type=TurretType.MISSILE,
                damage=15.0,
                range=350.0,
                cooldown=2,
                parent_unit=platform,
            )
            weapons_comp.add_turret(turret)
            platform.add_component(weapons_comp)

            system = galaxy.systems.get(component.unit.in_system)
            if system:
                system.add_unit(platform)
                spawned_ids.append(platform.id)

        return spawned_ids

    def _auto_target_platforms(self, component: 'AbilityComponent', galaxy: 'Galaxy') -> None:
        """Assigns the nearest enemy as the weapon target for each active missile platform."""
        system = galaxy.systems.get(component.unit.in_system)
        if not system:
            return

        for uid in self.spawned_unit_ids:
            platform = galaxy.get_unit_by_id(uid)
            if not platform or not platform.weapons_component:
                continue
            hex_obj = system.hexes.get(platform.in_hex)
            if not hex_obj:
                continue

            closest_enemy = None
            min_dist = float('inf')
            max_range = max((t.range for t in platform.weapons_component.turrets), default=0)
            for candidate in hex_obj.units:
                if candidate.owner == platform.owner or candidate.current_hit_points <= 0:
                    continue
                d = distance(platform.position, candidate.position)
                if d <= max_range and d < min_dist:
                    min_dist = d
                    closest_enemy = candidate

            platform.weapons_component.set_target(closest_enemy)
