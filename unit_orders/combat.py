from tactical_abilities import combat_target
from unit_orders.base import OrderTargetField
import logging
from game_logging import format_unit_for_log
from typing import Dict, Optional, Any, TYPE_CHECKING

from geometry import distance
from constants import DEFAULT_STANDOFF_DISTANCE
from unit_components.weapons import targeting_range
from .base import Order, OrderStatus, OrderType
from .movement import MoveOrder

if TYPE_CHECKING:
    from galaxy import Galaxy
    from domain.units import Unit

logger = logging.getLogger(__name__)


def resolve_component_type(comp_spec: Any) -> Optional[type]:
    """Resolve a component class from a class object, class name, or normalized alias string."""
    if comp_spec is None:
        return None
    if isinstance(comp_spec, type):
        return comp_spec

    from unit_components.persistence import component_registry
    registry = component_registry()
    if not isinstance(comp_spec, str):
        return None

    direct = registry.get(comp_spec)
    if direct is not None and isinstance(direct, type):
        return direct

    normalized = comp_spec.lower().replace(" ", "").replace("_", "")
    alias_map = {
        "engines": registry.get("Engines"),
        "engine": registry.get("Engines"),
        "hyperdrive": registry.get("Hyperdrive"),
        "weapons": registry.get("Weapons"),
        "weapon": registry.get("Weapons"),
        "defenses": registry.get("Defenses"),
        "defense": registry.get("Defenses"),
        "inhibitor": registry.get("HyperspaceInhibitionFieldEmitter"),
        "hyperspaceinhibitionfieldemitter": registry.get("HyperspaceInhibitionFieldEmitter"),
        "cloaking": registry.get("CloakingDevice"),
        "cloakingdevice": registry.get("CloakingDevice"),
        "sensors": registry.get("Sensors"),
        "sensor": registry.get("Sensors"),
        "constructor": registry.get("Constructor"),
        "repair": registry.get("RepairComponent"),
        "repaircomponent": registry.get("RepairComponent"),
        "colony": registry.get("ColonyComponent"),
        "colonycomponent": registry.get("ColonyComponent"),
        "mining": registry.get("MiningComponent"),
        "miningcomponent": registry.get("MiningComponent"),
        "metalrefinery": registry.get("MetalRefineryComponent"),
        "metalrefinerycomponent": registry.get("MetalRefineryComponent"),
        "crystalrefinery": registry.get("CrystalRefineryComponent"),
        "crystalrefinerycomponent": registry.get("CrystalRefineryComponent"),
        "hangar": registry.get("HangarComponent"),
        "hangarcomponent": registry.get("HangarComponent"),
        "strikecraftbay": registry.get("StrikecraftBayComponent"),
        "strikecraftbaycomponent": registry.get("StrikecraftBayComponent"),
        "trade": registry.get("TradeComponent"),
        "tradecomponent": registry.get("TradeComponent"),
        "civilianhabitat": registry.get("CivilianHabitatComponent"),
        "civilianhabitatcomponent": registry.get("CivilianHabitatComponent"),
        "orbitaldefense": registry.get("OrbitalDefenseComponent"),
        "orbitaldefensecomponent": registry.get("OrbitalDefenseComponent"),
        "antimatter": registry.get("AntimatterStorage"),
        "antimatterstorage": registry.get("AntimatterStorage"),
        "harvester": registry.get("AntimatterHarvester"),
        "antimatterharvester": registry.get("AntimatterHarvester"),
        "minelayer": registry.get("MinelayerComponent"),
        "minelayercomponent": registry.get("MinelayerComponent"),
        "marines": registry.get("MarinesComponent"),
        "marinescomponent": registry.get("MarinesComponent"),
        "intelligence": registry.get("IntelligenceComponent"),
        "intelligencecomponent": registry.get("IntelligenceComponent"),
        "abilities": registry.get("AbilityComponent"),
        "ability": registry.get("AbilityComponent"),
        "abilitycomponent": registry.get("AbilityComponent"),
    }
    return alias_map.get(normalized)


class AttackOrder(Order):
    target_fields = (OrderTargetField('target_unit_id', 'unit', public=True),)
    attack_type = OrderType.ATTACK
    long_range_only = False

    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, self.attack_type, parameters, parent_order)

    def target_not_visible(self, galaxy_ref: 'Galaxy', visibility_snapshot=None) -> bool:
        """Read current owner coverage without recording intel or advancing orders."""
        if galaxy_ref is None:
            return False
        galaxy_ref = getattr(getattr(self.unit, "game", None), "galaxy", None) or galaxy_ref
        if galaxy_ref is None or self.unit.owner is None:
            return False
        target_id = self.parameters.get("target_unit_id")
        if target_id is None:
            return False
        target = combat_target(galaxy_ref, target_id)
        if target is None:
            # Docked ships leave the galaxy lookup, but are still lost
            # contacts rather than destroyed targets.
            from campaign_graph import find_unit
            target = find_unit(galaxy_ref, target_id)
        from domain.players import are_enemies
        if target is None or target.current_hit_points <= 0 or not are_enemies(self.unit.owner, target.owner):
            return False  # Retain the existing missing/dead/friendly lifecycle.
        from visibility import VisibilityService, is_unit_visible
        if visibility_snapshot is None:
            visibility_snapshot = VisibilityService.compute(galaxy_ref, self.unit.owner, record_intel=False)
        return not is_unit_visible(visibility_snapshot, target)

    def cancel_if_target_not_visible(self, galaxy_ref: 'Galaxy', visibility_snapshot=None) -> bool:
        """Cancel this engagement only; callers settle roots/parents at safe boundaries."""
        if self.status not in {OrderStatus.PENDING, OrderStatus.IN_PROGRESS}:
            return False
        if not self.target_not_visible(galaxy_ref, visibility_snapshot):
            return False
        self.failure_reason = "target_not_visible"
        self.cancel()
        self.sub_orders.clear()
        logger.debug(
            "Attack cancelled: attacker=%s target=%s order=%s reason=target_not_visible",
            self.unit.id, self.parameters.get("target_unit_id"), self.public_id,
        )
        return True

    def approach_range(self, target_unit: 'Unit') -> Optional[float]:
        """Shortest effective range of the turrets that determine this approach."""
        weapons = self.unit.weapons_component
        if not weapons:
            return None
        turrets = weapons.eligible_turrets_for(target_unit, long_range_only=self.long_range_only)
        if not isinstance(turrets, (list, tuple)):
            # Keep lightweight weapon collaborators usable by order tests.
            from unit_components.enums import TurretVariant
            turrets = [t for t in getattr(weapons, 'turrets', [])
                       if not self.long_range_only or t.variant == TurretVariant.LONG_RANGE]
        component_type = resolve_component_type(self.parameters.get("target_component_type"))
        return min((targeting_range(turret.range, component_type) for turret in turrets), default=None)

    def get_state_data(self) -> Dict[str, Any]:
        state_data = super().get_state_data()
        target_unit_id = self.parameters.get("target_unit_id")
        target_name = None
        lookup_attempted = False
        lookup_success = False
        if target_unit_id is not None and self.unit and self.unit.game:
            lookup_attempted = True
            target_unit = combat_target(self.unit.game.galaxy, target_unit_id)
            if target_unit:
                target_name = target_unit.name
                lookup_success = True
        state_data["target_unit_id"] = target_unit_id
        state_data["target_name"] = target_name
        state_data["target_component_type"] = self.parameters.get("target_component_type")
        state_data["lookup_attempted"] = lookup_attempted
        state_data["lookup_success"] = lookup_success
        return state_data

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        if self.status != OrderStatus.PENDING:
            return
        super().execute(galaxy_ref)

        if self.cancel_if_target_not_visible(galaxy_ref):
            return

        target_unit_id = self.parameters["target_unit_id"]
        galaxy = getattr(getattr(self.unit, "game", None), "galaxy", None) or galaxy_ref
        target_unit = combat_target(galaxy, target_unit_id) if galaxy else None

        target_component_type = resolve_component_type(self.parameters.get("target_component_type"))

        from domain.players import are_enemies
        weapons = self.unit.weapons_component
        if not target_unit or not are_enemies(self.unit.owner, target_unit.owner):
            self.fail("target_unavailable")
            if weapons:
                # A rejected attack must not leave a lock inherited from a
                # previous foreground/standing engagement.
                weapons.clear_target()
            return

        if not weapons:
            self.fail("capability_unavailable")
            return
        min_turret_range = self.approach_range(target_unit)
        if min_turret_range is None:
            self.fail("capability_unavailable")
            weapons.clear_target()
            return
        weapons.set_target(target_unit, target_component_type)

        if self.unit.in_system != target_unit.in_system or self.unit.in_hex != target_unit.in_hex:
            in_the_same_system_and_hex = False
        else:
            in_the_same_system_and_hex = True

        in_range = distance(self.unit.position, target_unit.position) < min_turret_range

        if not in_the_same_system_and_hex or not in_range:
            move_order = MoveOrder.for_unit_approach(
                self.unit,
                target_unit,
                max(1.0, min_turret_range - 5.0),
                parent_order=self,
            )
            self.add_sub_order(move_order)

    def update(self, galaxy_ref: 'Galaxy') -> None:
        from domain.units import Unit

        if self.status != OrderStatus.IN_PROGRESS:
            return
        if self.cancel_if_target_not_visible(galaxy_ref):
            return

        target_unit_id = self.parameters.get("target_unit_id")
        galaxy = getattr(getattr(self.unit, "game", None), "galaxy", None) or galaxy_ref
        target_unit = combat_target(galaxy, target_unit_id) if target_unit_id is not None and galaxy else None

        from domain.players import are_enemies
        if (
            not target_unit
            or target_unit.current_hit_points <= 0
            or not are_enemies(self.unit.owner, target_unit.owner)
        ):
            for child in list(self.sub_orders):
                child.cancel()
            self.sub_orders.clear()
            self.status = OrderStatus.COMPLETED
            if self._owns_weapon_engagement() and self.unit.weapons_component:
                self.unit.weapons_component.clear_target()
            return

        weapons = self.unit.weapons_component
        min_turret_range = self.approach_range(target_unit)
        if min_turret_range is None:
            for child in list(self.sub_orders):
                child.cancel()
            self.sub_orders.clear()
            self.fail("capability_unavailable")
            if self._owns_weapon_engagement() and weapons:
                weapons.clear_target()
            return

        standoff_distance = max(1.0, min_turret_range - 5.0)

        in_the_same_system_and_hex = (self.unit.in_system == target_unit.in_system and self.unit.in_hex == target_unit.in_hex)
        
        in_range = in_the_same_system_and_hex and distance(self.unit.position, target_unit.position) < min_turret_range

        # Check if we have an active movement sub-order
        has_movement_order = False
        if self.sub_orders:
            current_sub = self.sub_orders[0]
            if current_sub.order_type == OrderType.MOVE:
                has_movement_order = True
                dest_system = current_sub.parameters.get("destination_system_name")
                dest_hex = current_sub.parameters.get("destination_hex_coord")
                dest_pos = current_sub.parameters.get("destination_position")

                # If we are now in the same system and hex, and already within range, we should cancel the movement sub-order.
                if in_the_same_system_and_hex and in_range:
                    target_label = format_unit_for_log(target_unit) if isinstance(target_unit, Unit) else target_unit.name
                    logger.debug(f"[{format_unit_for_log(self.unit)}] Target {target_label} is in weapon range. Cancelling movement.")
                    current_sub.cancel()
                    self.sub_orders.popleft()
                    has_movement_order = False
                else:
                    # Otherwise, check if target has moved away from our movement destination parameters
                    target_moved = False
                    if dest_system != target_unit.in_system or dest_hex != target_unit.in_hex:
                        target_moved = True
                    elif dest_pos:
                        approach_resolved = current_sub.parameters.get("approach_position_resolved", True)
                        if approach_resolved:
                            current_offset = distance(dest_pos, target_unit.position)
                            if abs(current_offset - standoff_distance) > 15.0:
                                target_moved = True

                    if target_moved:
                        target_label = format_unit_for_log(target_unit) if isinstance(target_unit, Unit) else target_unit.name
                        logger.debug(f"[{format_unit_for_log(self.unit)}] Target {target_label} moved. Recalculating path.")
                        current_sub.cancel()
                        self.sub_orders.popleft()
                        has_movement_order = False

        # If we don't have a movement order, check if we need to move
        if not has_movement_order:
            if not in_the_same_system_and_hex or not in_range:
                move_order = MoveOrder.for_unit_approach(
                    self.unit,
                    target_unit,
                    standoff_distance,
                    parent_order=self,
                )
                self.add_sub_order(move_order)

        super().update(galaxy_ref)

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return
        target_unit_id = self.parameters["target_unit_id"]
        galaxy_ref = (
            getattr(getattr(self.unit, "game", None), "galaxy", None)
            or getattr(self.unit, "in_galaxy", None)
        )
        target_unit = combat_target(galaxy_ref, target_unit_id) if galaxy_ref else None
        target_component_type_str = self.parameters.get("target_component_type")

        from domain.players import are_enemies
        if (
            not target_unit
            or target_unit.current_hit_points <= 0
            or not are_enemies(self.unit.owner, target_unit.owner)
        ):
            self.status = OrderStatus.COMPLETED
            if self._owns_weapon_engagement() and self.unit.weapons_component:
                self.unit.weapons_component.clear_target()
            return
            
        if target_component_type_str:
            target_component_type = resolve_component_type(target_component_type_str)
            if target_component_type:
                target_component = target_unit.get_component(target_component_type)
                if not target_component or target_component.is_destroyed:
                    self.status = OrderStatus.COMPLETED
                    if self._owns_weapon_engagement() and self.unit.weapons_component:
                        self.unit.weapons_component.clear_target()

    def _owns_weapon_engagement(self) -> bool:
        commander = getattr(self.unit, "commander_component", None)
        method = getattr(commander, "is_order_on_active_front_chain", None) if commander else None
        if callable(method):
            result = method(self)
            if isinstance(result, bool):
                return result
        active_attack = getattr(commander, "get_active_attack_order", None) if commander else None
        return bool(callable(active_attack) and active_attack() is self)

    def cancel(self) -> None:
        owns_engagement = self._owns_weapon_engagement()
        super().cancel()
        if owns_engagement and self.unit.weapons_component:
            self.unit.weapons_component.clear_target()

    def resume(self, galaxy_ref: 'Galaxy') -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return
        if self.target_not_visible(galaxy_ref):
            # Hydration must not advance lifecycle/history or resume pursuit.
            if self._owns_weapon_engagement() and self.unit.weapons_component:
                self.unit.weapons_component.clear_target()
            return
        target_id = self.parameters.get("target_unit_id")
        from tactical_abilities import combat_target
        target = combat_target(galaxy_ref, target_id) if target_id is not None else None
        weapons = self.unit.weapons_component
        from domain.players import are_enemies
        if target and weapons and are_enemies(self.unit.owner, target.owner) and self.approach_range(target) is not None:
            weapons.set_target(target, resolve_component_type(self.parameters.get("target_component_type")))
        elif weapons:
            # Rebinding must not advance order lifecycle or write history on load.
            weapons.clear_target()
        super().resume(galaxy_ref)


class AttackLongRangeOrder(AttackOrder):
    """Use long-range turrets for approach distance; all eligible turrets may fire."""
    attack_type = OrderType.ATTACK_LONG_RANGE
    long_range_only = True


def discard_lost_attack_engagement(parent: Order, galaxy_ref: 'Galaxy') -> bool:
    """Let a continuing mission consume contact loss without cancelling itself."""
    if not parent.sub_orders or not isinstance(parent.sub_orders[0], AttackOrder):
        return False
    attack = parent.sub_orders[0]
    attack.cancel_if_target_not_visible(galaxy_ref)
    if attack.status == OrderStatus.CANCELLED and attack.failure_reason == "target_not_visible":
        parent.sub_orders.popleft()
        return True
    return False


class ProtectOrder(Order):
    target_fields = (OrderTargetField('target_unit_id', 'unit', public=True),)

    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.PROTECT, parameters, parent_order)

    def get_state_data(self) -> Dict[str, Any]:
        state_data = super().get_state_data()
        target_unit_id = self.parameters.get("target_unit_id")
        target_name = None
        lookup_attempted = False
        lookup_success = False
        if target_unit_id is not None and self.unit and self.unit.game:
            lookup_attempted = True
            target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id)
            if target_unit:
                target_name = target_unit.name
                lookup_success = True
        state_data["target_unit_id"] = target_unit_id
        state_data["target_name"] = target_name
        state_data["lookup_attempted"] = lookup_attempted
        state_data["lookup_success"] = lookup_success
        return state_data

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)
        target_unit_id = self.parameters.get("target_unit_id")
        galaxy = getattr(getattr(self.unit, "game", None), "galaxy", None) or galaxy_ref
        target_unit = galaxy.get_unit_by_id(target_unit_id) if target_unit_id is not None and galaxy else None

        if not target_unit:
            self.fail("target_unavailable")
            logger.debug(f"PROTECT order failed: Target unit {target_unit_id} not found.")
            return

        from domain.players import are_allies
        if not are_allies(self.unit.owner, target_unit.owner):
            self.fail("target_unavailable")
            logger.debug(f"PROTECT order failed: Target unit {format_unit_for_log(target_unit)} is not allied.")
            return

    def _find_nearby_enemy(self, galaxy_ref: 'Galaxy', target_unit: 'Unit') -> Optional['Unit']:
        weapons = self.unit.weapons_component
        if not weapons or weapons.is_destroyed or not weapons.turrets:
            return None

        # The protector must be in the same system and hex as the protected unit to search for enemies
        if self.unit.in_system != target_unit.in_system or self.unit.in_hex != target_unit.in_hex:
            return None

        system = galaxy_ref.systems.get(self.unit.in_system)
        if not system:
            return None

        hex_obj = system.hexes.get(self.unit.in_hex)
        if not hex_obj:
            return None

        closest_enemy = None
        min_dist = float('inf')

        # Any enemy that gets closer than 1000.0 to the protected ship is a valid target.
        detection_range = 1000.0

        visibility_snapshot = None
        if self.unit.owner and galaxy_ref:
            from visibility import VisibilityService
            turn_num = getattr(getattr(self.unit, 'game', None), 'turn_number', None)
            if turn_num is None:
                turn_num = getattr(galaxy_ref, 'turn_number', 1)
                if hasattr(galaxy_ref, 'game') and hasattr(galaxy_ref.game, 'turn_number'):
                    turn_num = getattr(galaxy_ref.game, 'turn_number', 1)
            visibility_snapshot = VisibilityService.compute(galaxy_ref, self.unit.owner, turn_number=turn_num)

        from domain.players import are_enemies
        from visibility import is_unit_visible
        for candidate in hex_obj.units:
            if are_enemies(self.unit.owner, candidate.owner) and candidate.current_hit_points > 0:
                if visibility_snapshot is not None and not is_unit_visible(visibility_snapshot, candidate):
                    continue

                if not weapons.eligible_turrets_for(candidate):
                    continue

                dist_to_protector = distance(self.unit.position, candidate.position)
                dist_to_protected = distance(target_unit.position, candidate.position)

                if dist_to_protected < detection_range:
                    if dist_to_protector < min_dist:
                        min_dist = dist_to_protector
                        closest_enemy = candidate

        return closest_enemy

    def update(self, galaxy_ref: 'Galaxy') -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            super().update(galaxy_ref)
            return

        target_unit_id = self.parameters.get("target_unit_id")
        galaxy = getattr(getattr(self.unit, "game", None), "galaxy", None) or galaxy_ref
        target_unit = galaxy.get_unit_by_id(target_unit_id) if target_unit_id is not None and galaxy else None

        from domain.players import are_allies
        if (
            not target_unit
            or target_unit.current_hit_points <= 0
            or not are_allies(self.unit.owner, target_unit.owner)
        ):
            # The protected unit may disappear or change diplomacy while an
            # approach/attack child still owns an actuator.  Unwind the whole
            # subtree before completing so no stale pursuit can continue.
            for child in list(self.sub_orders):
                child.cancel()
            self.sub_orders.clear()
            self.status = OrderStatus.COMPLETED
            if self.unit.weapons_component:
                self.unit.weapons_component.clear_target()
            return

        discard_lost_attack_engagement(self, galaxy_ref)

        # Check if we are currently executing an AttackOrder
        has_attack_order = False
        if self.sub_orders:
            current_sub = self.sub_orders[0]
            if current_sub.order_type == OrderType.ATTACK:
                has_attack_order = True
                enemy_id = current_sub.parameters.get("target_unit_id")
                enemy_unit = galaxy.get_unit_by_id(enemy_id) if enemy_id is not None and galaxy else None
                from domain.players import are_enemies

                is_in_range = False
                if (enemy_unit and 
                        enemy_unit.current_hit_points > 0 and 
                        are_enemies(self.unit.owner, enemy_unit.owner) and
                        enemy_unit.in_system == self.unit.in_system and 
                        enemy_unit.in_hex == self.unit.in_hex and
                        target_unit.in_system == self.unit.in_system and
                        target_unit.in_hex == self.unit.in_hex):
                    dist_to_protected = distance(target_unit.position, enemy_unit.position)
                    if dist_to_protected < 1000.0:
                        is_in_range = True

                if not is_in_range:
                    logger.debug(f"[{format_unit_for_log(self.unit)}] Protect attack target lost, dead, or out of threat range. Resuming protection.")
                    current_sub.cancel()
                    self.sub_orders.popleft()
                    has_attack_order = False

        if not has_attack_order:
            # Look for nearby enemies to engage
            nearby_enemy = self._find_nearby_enemy(galaxy_ref, target_unit)
            if nearby_enemy:
                logger.debug(f"[{format_unit_for_log(self.unit)}] Enemy detected near protected target: {format_unit_for_log(nearby_enemy)}. Engaging!")
                # Cancel current movement/follow sub-orders
                for sub in list(self.sub_orders):
                    sub.cancel()
                self.sub_orders.clear()

                # Spawn attack order
                attack_params = {"target_unit_id": nearby_enemy.id}
                self.add_sub_order(AttackOrder(self.unit, attack_params, parent_order=self))
            else:
                # If no enemies, handle follow movement
                has_movement_order = False
                if self.sub_orders:
                    current_sub = self.sub_orders[0]
                    if current_sub.order_type in [OrderType.MOVE, OrderType.REACH_WAYPOINT]:
                        has_movement_order = True
                        dest_system = current_sub.parameters.get("destination_system_name")
                        dest_hex = current_sub.parameters.get("destination_hex_coord")
                        dest_pos = current_sub.parameters.get("destination_position")

                        # If protected unit changed system/hex, or moved significantly from movement destination:
                        planned_standoff = float(current_sub.parameters.get("standoff_distance", DEFAULT_STANDOFF_DISTANCE))
                        approach_resolved = current_sub.parameters.get("approach_position_resolved", True)
                        if (dest_system != target_unit.in_system or
                                dest_hex != target_unit.in_hex or
                                (dest_pos and approach_resolved and
                                 abs(distance(dest_pos, target_unit.position) - planned_standoff) > 15.0)):
                            logger.debug(f"[{format_unit_for_log(self.unit)}] Protected unit {format_unit_for_log(target_unit)} moved. Recalculating path.")
                            current_sub.cancel()
                            self.sub_orders.popleft()
                            has_movement_order = False

                if has_movement_order:
                    # Cancel movement order if we are already close enough
                    if self.unit.in_system == target_unit.in_system and self.unit.in_hex == target_unit.in_hex:
                        dist_to_target = distance(self.unit.position, target_unit.position)
                        if dist_to_target <= DEFAULT_STANDOFF_DISTANCE:
                            logger.debug(f"[{format_unit_for_log(self.unit)}] Close enough to protected unit {format_unit_for_log(target_unit)}. Stopping movement.")
                            if self.sub_orders:
                                self.sub_orders[0].cancel()
                                self.sub_orders.popleft()
                            has_movement_order = False

                if not has_movement_order:
                    in_same_system_and_hex = (self.unit.in_system == target_unit.in_system and self.unit.in_hex == target_unit.in_hex)
                    dist_to_target = distance(self.unit.position, target_unit.position) if in_same_system_and_hex else float('inf')

                    if not in_same_system_and_hex or dist_to_target > DEFAULT_STANDOFF_DISTANCE:
                        self.add_sub_order(MoveOrder.for_unit_approach(
                            self.unit,
                            target_unit,
                            DEFAULT_STANDOFF_DISTANCE,
                            parent_order=self,
                        ))

        super().update(galaxy_ref)

    def check_completion_conditions(self) -> None:
        pass
