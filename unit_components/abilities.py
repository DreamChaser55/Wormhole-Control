import logging
import typing
from typing import Optional, TYPE_CHECKING
import dataclasses
import math

from .base import UnitComponent
from .enums import AbilityType, UnitStance, TurretType
from .defenses import Defenses
from .weapons import Weapons, Turret
from utils import HexCoord
from geometry import Position, distance
from constants import HullSize

if TYPE_CHECKING:
    from entities import Unit
    from galaxy import Galaxy
    from game import Game

logger = logging.getLogger(__name__)

@dataclasses.dataclass
class AbilityDefinition:
    """Static definition of an ability's properties (shared across all units)."""
    ability_type: AbilityType
    name: str
    description: str
    cooldown: int            # Turns before the ability can be used again
    duration: int            # Turns the effect persists (0 = instant / one-shot)
    range: float             # Max targeting distance in logical units (0 = self only)
    requires_target_unit: bool       # True if the ability needs a unit to be selected
    requires_target_position: bool   # True if the ability needs a position click
    antimatter_cost: int = 0         # Cost in antimatter to activate this ability


# Registry of all ability definitions. Tuned values live here.
ABILITY_DEFINITIONS: typing.Dict[AbilityType, AbilityDefinition] = {
    AbilityType.ADAPTIVE_FORCEFIELD: AbilityDefinition(
        ability_type=AbilityType.ADAPTIVE_FORCEFIELD,
        name="Adaptive Forcefield",
        description="Reduces incoming damage by 75% for 3 turns.",
        cooldown=8,
        duration=3,
        range=0.0,
        requires_target_unit=False,
        requires_target_position=False,
        antimatter_cost=20,
    ),
    AbilityType.CLUSTER_WARHEAD: AbilityDefinition(
        ability_type=AbilityType.CLUSTER_WARHEAD,
        name="Cluster Warhead",
        description="Fires a missile that deals heavy splash damage at a target position.",
        cooldown=5,
        duration=0,
        range=500.0,
        requires_target_unit=False,
        requires_target_position=True,
        antimatter_cost=30,
    ),
    AbilityType.DESIGNATE_TARGET: AbilityDefinition(
        ability_type=AbilityType.DESIGNATE_TARGET,
        name="Designate Target",
        description="Marks an enemy unit. Friendly units deal +50% damage against it for 4 turns.",
        cooldown=6,
        duration=4,
        range=450.0,
        requires_target_unit=True,
        requires_target_position=False,
        antimatter_cost=15,
    ),
    AbilityType.ION_BOLT: AbilityDefinition(
        ability_type=AbilityType.ION_BOLT,
        name="Ion Bolt",
        description="Disables a target unit, preventing movement and attacks for 3 turns.",
        cooldown=7,
        duration=3,
        range=400.0,
        requires_target_unit=True,
        requires_target_position=False,
        antimatter_cost=25,
    ),
    AbilityType.MISSILE_BATTERIES: AbilityDefinition(
        ability_type=AbilityType.MISSILE_BATTERIES,
        name="Missile Batteries",
        description="Deploys 3 missile platforms that automatically attack enemies for 4 turns.",
        cooldown=10,
        duration=4,
        range=0.0,
        requires_target_unit=False,
        requires_target_position=False,
        antimatter_cost=40,
    ),
    AbilityType.REPAIR_CLOUD: AbilityDefinition(
        ability_type=AbilityType.REPAIR_CLOUD,
        name="Repair Cloud",
        description="Disperses repair nanites that restore 5 HP per turn to all friendly ships within 350 units for 4 turns.",
        cooldown=8,
        duration=4,
        range=350.0,
        requires_target_unit=False,
        requires_target_position=False,
        antimatter_cost=35,
    ),
    AbilityType.CAPTURE_UNIT: AbilityDefinition(
        ability_type=AbilityType.CAPTURE_UNIT,
        name="Capture Unit",
        description="Captures an enemy unit within very short range (100 units). Target unit must be disabled and defenseless (weapons and defenses destroyed or missing).",
        cooldown=10,
        duration=0,
        range=100.0,
        requires_target_unit=True,
        requires_target_position=False,
        antimatter_cost=40,
    ),
}


class AbilityInstance:
    """Runtime state for a single ability on a unit."""
    definition: AbilityDefinition
    cooldown_remaining: int = 0
    is_active: bool = False
    duration_remaining: int = 0
    target_unit_id: typing.Optional[int] = None
    target_position: typing.Optional[Position] = None
    # For Missile Batteries: track spawned platform unit IDs
    spawned_unit_ids: typing.List[int] = dataclasses.field(default_factory=list)

    def __init__(
        self,
        definition: AbilityDefinition,
        cooldown_remaining: int = 0,
        is_active: bool = False,
        duration_remaining: int = 0,
        target_unit_id: typing.Optional[int] = None,
        target_position: typing.Optional[Position] = None,
        spawned_unit_ids: typing.Optional[typing.List[int]] = None,
    ):
        self.definition = definition
        self.cooldown_remaining = cooldown_remaining
        self.is_active = is_active
        self.duration_remaining = duration_remaining
        self.target_unit_id = target_unit_id
        self.target_position = target_position
        self.spawned_unit_ids = spawned_unit_ids if spawned_unit_ids is not None else []

    @property
    def is_ready(self) -> bool:
        """True if the ability is off cooldown and not currently active."""
        return self.cooldown_remaining <= 0 and not self.is_active


class AbilityComponent(UnitComponent):
    """
    Manages the set of special abilities available to a unit.

    Each ability has its own cooldown and active-duration tracking. This component
    is responsible for ticking cooldowns, applying ongoing effects each turn
    (e.g. Repair Cloud healing, Designate Target marking), and cleaning up expired
    effects. If this component is destroyed the unit cannot use any abilities.
    """
    DISPLAY_NAME: str = "Abilities"
    SIDEBAR_ORDER: int = 14
    abilities: typing.Dict[AbilityType, AbilityInstance] = dataclasses.field(default_factory=dict)

    def __init__(self, unit: 'Unit', ability_types: typing.List[AbilityType], hull_cost: int = 10):
        super().__init__(unit, hull_cost=hull_cost)
        self.abilities: typing.Dict[AbilityType, AbilityInstance] = {}
        for atype in ability_types:
            defn = ABILITY_DEFINITIONS.get(atype)
            if defn:
                self.abilities[atype] = AbilityInstance(definition=defn)
            else:
                logger.warning(f"[AbilityComponent] Unknown ability type: {atype}")

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        status = "DESTROYED" if self.is_destroyed else f"HP: {self.current_hit_points}/{self.max_hit_points}"
        data = [{
            'type': 'label',
            'text': f"Ability System [{status}]",
            'object_id': '#sidebar_section_header_label',
            'height': 28,
        }]

        # Show Ion Bolt / Designate Target targeting-mode indicator
        if game_state.pending_ability:
            pending_name = game_state.pending_ability[0].replace('_', ' ').title()
            data.append({
                'type': 'label',
                'text': f"\u25b6 Select target for: {pending_name}",
                'object_id': '#sidebar_hit_points_light_damage_label',
                'height': 22,
            })

        for ability_type, instance in self.abilities.items():
            defn = instance.definition
            if instance.is_active:
                cd_str = f"Active ({instance.duration_remaining} turns)"
                btn_obj_id = '#sidebar_section_header_label'
            elif instance.cooldown_remaining > 0:
                cd_str = f"Cooldown: {instance.cooldown_remaining} turns"
                btn_obj_id = '#sidebar_info_label'
            else:
                cd_str = "Ready"
                btn_obj_id = '#sidebar_expand_button'

            # Check if there is enough antimatter
            am_comp = self.unit.antimatter_component
            has_enough_am = True
            if am_comp and am_comp.current_amount < defn.antimatter_cost:
                has_enough_am = False

            btn_text = f"{defn.name} ({defn.antimatter_cost} AM) [{cd_str}]"
            data.append({
                'type': 'button',
                'text': btn_text,
                'object_id': btn_obj_id,
                'action_id': 'use_ability',
                'target_data': {
                    'ability_type_str': ability_type.value,
                    'requires_target_unit': defn.requires_target_unit,
                    'requires_target_position': defn.requires_target_position,
                },
                'height': 28,
                'enabled': instance.is_ready and not self.is_destroyed and has_enough_am,
            })
            data.append({
                'type': 'label',
                'text': f"  {defn.description}",
                'object_id': '#sidebar_info_label',
                'height': 18,
            })
        return data

    def can_use(self, ability_type: AbilityType) -> bool:
        """Returns True if the ability exists, the component is intact, it is off cooldown, and has enough antimatter."""
        if self.is_destroyed:
            return False
        instance = self.abilities.get(ability_type)
        if not instance:
            return False
        if not instance.is_ready:
            return False
        am_comp = self.unit.antimatter_component
        if am_comp and am_comp.current_amount < instance.definition.antimatter_cost:
            return False
        return True

    def activate(
        self,
        ability_type: AbilityType,
        galaxy: 'Galaxy',
        target_unit_id: typing.Optional[int] = None,
        target_position: typing.Optional[Position] = None,
        target_system_name: typing.Optional[str] = None,
        target_hex_coord: typing.Optional[HexCoord] = None,
    ) -> bool:
        """
        Activates the specified ability.

        Performs validation, applies immediate effects, and sets the active
        state. Returns True on success, False on failure.
        """
        if not self.can_use(ability_type):
            logger.debug(f"[{self.unit.name}] Cannot use {ability_type.name}: not ready, component destroyed, or low antimatter.")
            return False

        instance = self.abilities[ability_type]
        defn = instance.definition

        # --- Immediate activation effects ---
        if ability_type == AbilityType.ADAPTIVE_FORCEFIELD:
            self.unit.damage_reduction = 0.75
            logger.debug(f"[{self.unit.name}] Adaptive Forcefield activated. Damage reduction: 75%.")

        elif ability_type == AbilityType.CLUSTER_WARHEAD:
            if target_position is None:
                logger.debug(f"[{self.unit.name}] Cluster Warhead requires a target position.")
                return False
            self._apply_cluster_warhead(
                galaxy,
                target_position,
                target_system_name=target_system_name,
                target_hex_coord=target_hex_coord
            )

        elif ability_type == AbilityType.DESIGNATE_TARGET:
            if target_unit_id is None:
                logger.debug(f"[{self.unit.name}] Designate Target requires a target unit.")
                return False
            target_unit = galaxy.get_unit_by_id(target_unit_id)
            if not target_unit:
                logger.debug(f"[{self.unit.name}] Designate Target: target unit {target_unit_id} not found.")
                return False
            target_unit.damage_amplification += 0.5
            instance.target_unit_id = target_unit_id
            logger.debug(f"[{self.unit.name}] Designate Target applied to {target_unit.name}. Amplification now: {target_unit.damage_amplification:.2f}.")

        elif ability_type == AbilityType.ION_BOLT:
            if target_unit_id is None:
                logger.debug(f"[{self.unit.name}] Ion Bolt requires a target unit.")
                return False
            target_unit = galaxy.get_unit_by_id(target_unit_id)
            if not target_unit:
                logger.debug(f"[{self.unit.name}] Ion Bolt: target unit {target_unit_id} not found.")
                return False
            target_unit.is_disabled = True
            target_unit.disabled_by_unit_ids.add(self.unit.id)
            instance.target_unit_id = target_unit_id
            logger.debug(f"[{self.unit.name}] Ion Bolt disabled {target_unit.name}.")

        elif ability_type == AbilityType.MISSILE_BATTERIES:
            spawned = self._spawn_missile_platforms(galaxy, defn.duration)
            instance.spawned_unit_ids = spawned
            logger.debug(f"[{self.unit.name}] Missile Batteries: spawned {len(spawned)} platforms.")

        elif ability_type == AbilityType.REPAIR_CLOUD:
            # Healing applied each turn in update(); nothing immediate needed.
            logger.debug(f"[{self.unit.name}] Repair Cloud activated. Healing friendlies within {defn.range} units for {defn.duration} turns.")

        elif ability_type == AbilityType.CAPTURE_UNIT:
            if target_unit_id is None:
                logger.debug(f"[{self.unit.name}] Capture Unit requires a target unit.")
                return False
            target_unit = galaxy.get_unit_by_id(target_unit_id)
            if not target_unit:
                logger.debug(f"[{self.unit.name}] Capture Unit: target unit {target_unit_id} not found.")
                return False

            if target_unit.owner == self.unit.owner:
                logger.debug(f"[{self.unit.name}] Capture Unit: target unit {target_unit.name} is already friendly.")
                return False

            if target_unit.engines_component is not None:
                engines_disabled = target_unit.engines_component.is_destroyed or target_unit.is_disabled
                if not engines_disabled:
                    logger.debug(f"[{self.unit.name}] Capture Unit failed: target {target_unit.name} engines are not disabled.")
                    return False

            if target_unit.weapons_component and not target_unit.weapons_component.is_destroyed:
                logger.debug(f"[{self.unit.name}] Capture Unit failed: target {target_unit.name} weapons are active.")
                return False

            defenses = target_unit.get_component(Defenses)
            if defenses and not defenses.is_destroyed:
                logger.debug(f"[{self.unit.name}] Capture Unit failed: target {target_unit.name} defenses are active.")
                return False

            # Transfer ownership
            old_owner = target_unit.owner
            target_unit.owner = self.unit.owner

            # Reset targets and stance of the captured unit to prevent unwanted behaviors
            if target_unit.commander_component:
                target_unit.commander_component.clear_orders()
                target_unit.commander_component.stance = UnitStance.DO_NOTHING

            if target_unit.weapons_component:
                target_unit.weapons_component.clear_target()

            logger.debug(f"[{self.unit.name}] Captured unit {target_unit.name} (id:{target_unit.id}) from player {old_owner.id if old_owner else 'None'} to player {self.unit.owner.id}.")

        # --- Consume antimatter ---
        am_comp = self.unit.antimatter_component
        if am_comp:
            consumed = am_comp.consume(defn.antimatter_cost)
            if not consumed:
                logger.debug(f"[{self.unit.name}] Consume failed during activation (insufficient antimatter).")
                return False

        # --- Mark as active and set cooldown ---
        instance.is_active = (defn.duration > 0)
        instance.duration_remaining = defn.duration
        instance.target_position = target_position
        instance.cooldown_remaining = defn.cooldown
        return True

    def _apply_cluster_warhead(
        self,
        galaxy: 'Galaxy',
        target_position: Position,
        target_system_name: typing.Optional[str] = None,
        target_hex_coord: typing.Optional[HexCoord] = None,
        splash_radius: float = 200.0,
        base_damage: int = 80,
    ) -> None:
        """Deals splash damage to all units at the target position within splash_radius."""
        sys_name = target_system_name if target_system_name is not None else self.unit.in_system
        hex_coord = target_hex_coord if target_hex_coord is not None else self.unit.in_hex

        system = galaxy.systems.get(sys_name)
        if not system:
            return
        hex_obj = system.hexes.get(hex_coord)
        if not hex_obj:
            return
        for target_unit in list(hex_obj.units):
            if target_unit is self.unit:
                continue
            dist = distance(target_unit.position, target_position)
            if dist <= splash_radius:
                # Damage falls off linearly with distance
                falloff = max(0.0, 1.0 - (dist / splash_radius))
                damage = max(1, int(base_damage * falloff))
                target_unit.take_damage(damage)
                logger.debug(f"[Cluster Warhead] Hit {target_unit.name} for {damage} damage (dist={dist:.1f}).")

    def _spawn_missile_platforms(
        self,
        galaxy: 'Galaxy',
        lifetime: int,
        num_platforms: int = 3,
        deploy_radius: float = 60.0,
    ) -> typing.List[int]:
        """Spawns temporary missile platform units around the caster and returns their IDs."""
        from entities import Unit
        spawned_ids = []
        for i in range(num_platforms):
            angle = (2 * math.pi / num_platforms) * i
            px = self.unit.position.x + deploy_radius * math.cos(angle)
            py = self.unit.position.y + deploy_radius * math.sin(angle)
            platform_pos = Position(px, py)

            platform = Unit(
                owner=self.unit.owner,
                position=platform_pos,
                in_hex=self.unit.in_hex,
                in_system=self.unit.in_system,
                name=f"Missile Platform",
                hull_size=HullSize.TINY,
                game=self.unit.game,
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

            system = galaxy.systems.get(self.unit.in_system)
            if system:
                system.add_unit(platform)
                spawned_ids.append(platform.id)

        return spawned_ids

    def _expire_ability(self, ability_type: AbilityType, galaxy: 'Galaxy') -> None:
        """Cleans up lingering effects when an ability's duration expires."""
        instance = self.abilities[ability_type]

        if ability_type == AbilityType.ADAPTIVE_FORCEFIELD:
            self.unit.damage_reduction = max(0.0, self.unit.damage_reduction - 0.75)
            logger.debug(f"[{self.unit.name}] Adaptive Forcefield expired. Damage reduction removed.")

        elif ability_type == AbilityType.DESIGNATE_TARGET:
            if instance.target_unit_id is not None:
                target_unit = galaxy.get_unit_by_id(instance.target_unit_id)
                if target_unit:
                    target_unit.damage_amplification = max(0.0, target_unit.damage_amplification - 0.5)
                    logger.debug(f"[{self.unit.name}] Designate Target expired on {target_unit.name}. Amplification now: {target_unit.damage_amplification:.2f}.")
            instance.target_unit_id = None

        elif ability_type == AbilityType.ION_BOLT:
            if instance.target_unit_id is not None:
                target_unit = galaxy.get_unit_by_id(instance.target_unit_id)
                if target_unit:
                    target_unit.disabled_by_unit_ids.discard(self.unit.id)
                    if not target_unit.disabled_by_unit_ids:
                        target_unit.is_disabled = False
                    logger.debug(f"[{self.unit.name}] Ion Bolt expired on {target_unit.name}. Disabled: {target_unit.is_disabled}.")
            instance.target_unit_id = None

        elif ability_type == AbilityType.MISSILE_BATTERIES:
            # Platforms have their own lifetime; despawn any still alive
            system = galaxy.systems.get(self.unit.in_system)
            if system:
                for uid in instance.spawned_unit_ids:
                    platform = galaxy.get_unit_by_id(uid)
                    if platform:
                        galaxy.remove_unit(platform)
                        logger.debug(f"[{self.unit.name}] Missile Platform {uid} despawned.")
            instance.spawned_unit_ids = []

        elif ability_type == AbilityType.REPAIR_CLOUD:
            logger.debug(f"[{self.unit.name}] Repair Cloud expired.")

        instance.is_active = False
        instance.duration_remaining = 0
        instance.target_position = None

    def _apply_repair_cloud(self, galaxy: 'Galaxy') -> None:
        """Heals all friendly units within Repair Cloud range by 5 HP."""
        defn = ABILITY_DEFINITIONS[AbilityType.REPAIR_CLOUD]
        system = galaxy.systems.get(self.unit.in_system)
        if not system:
            return
        hex_obj = system.hexes.get(self.unit.in_hex)
        if not hex_obj:
            return
        heal_per_turn = 5
        for unit in hex_obj.units:
            if unit.owner != self.unit.owner:
                continue
            if distance(self.unit.position, unit.position) <= defn.range:
                unit.heal_hull(heal_per_turn)
                logger.debug(f"[Repair Cloud] Healed {unit.name} for {heal_per_turn} HP.")

    def _auto_target_platforms(self, galaxy: 'Galaxy') -> None:
        """Assigns the nearest enemy as the weapon target for each active missile platform."""
        instance = self.abilities.get(AbilityType.MISSILE_BATTERIES)
        if not instance:
            return
        system = galaxy.systems.get(self.unit.in_system)
        if not system:
            return

        for uid in instance.spawned_unit_ids:
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

    def update(self, galaxy: 'Galaxy') -> None:
        """
        Called once per turn. Ticks cooldowns, applies ongoing ability effects,
        and expires abilities whose duration has elapsed.
        """
        if self.is_destroyed:
            return

        for ability_type, instance in self.abilities.items():
            # --- Tick cooldown ---
            if instance.cooldown_remaining > 0:
                instance.cooldown_remaining -= 1

            # --- Apply ongoing effects for active abilities ---
            if instance.is_active:
                if ability_type == AbilityType.REPAIR_CLOUD:
                    self._apply_repair_cloud(galaxy)

                elif ability_type == AbilityType.MISSILE_BATTERIES:
                    self._auto_target_platforms(galaxy)

                # --- Tick duration ---
                if instance.duration_remaining > 0:
                    instance.duration_remaining -= 1

                # --- Check expiry ---
                if instance.duration_remaining <= 0:
                    self._expire_ability(ability_type, galaxy)
