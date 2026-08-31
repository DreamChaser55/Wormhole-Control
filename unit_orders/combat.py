import logging
from typing import Dict, Optional, Any, TYPE_CHECKING

from geometry import distance
from constants import HullSize, DEFAULT_STANDOFF_DISTANCE
from .base import Order, OrderStatus, OrderType
from .movement import MoveOrder

if TYPE_CHECKING:
    from galaxy import Galaxy
    from entities import Unit

logger = logging.getLogger(__name__)


def resolve_component_type(comp_spec: Any) -> Optional[type]:
    """Resolve a component class from a class object, class name, or normalized alias string."""
    if comp_spec is None:
        return None
    if isinstance(comp_spec, type):
        return comp_spec

    import unit_components
    if not isinstance(comp_spec, str):
        return None

    direct = getattr(unit_components, comp_spec, None)
    if direct is not None and isinstance(direct, type):
        return direct

    normalized = comp_spec.lower().replace(" ", "").replace("_", "")
    alias_map = {
        "engines": getattr(unit_components, "Engines", None),
        "engine": getattr(unit_components, "Engines", None),
        "hyperdrive": getattr(unit_components, "Hyperdrive", None),
        "weapons": getattr(unit_components, "Weapons", None),
        "weapon": getattr(unit_components, "Weapons", None),
        "defenses": getattr(unit_components, "Defenses", None),
        "defense": getattr(unit_components, "Defenses", None),
        "inhibitor": getattr(unit_components, "HyperspaceInhibitionFieldEmitter", None),
        "hyperspaceinhibitionfieldemitter": getattr(unit_components, "HyperspaceInhibitionFieldEmitter", None),
        "cloaking": getattr(unit_components, "CloakingDevice", None),
        "cloakingdevice": getattr(unit_components, "CloakingDevice", None),
        "sensors": getattr(unit_components, "Sensors", None),
        "sensor": getattr(unit_components, "Sensors", None),
        "constructor": getattr(unit_components, "Constructor", None),
        "repair": getattr(unit_components, "RepairComponent", None),
        "repaircomponent": getattr(unit_components, "RepairComponent", None),
        "colony": getattr(unit_components, "ColonyComponent", None),
        "colonycomponent": getattr(unit_components, "ColonyComponent", None),
        "mining": getattr(unit_components, "MiningComponent", None),
        "miningcomponent": getattr(unit_components, "MiningComponent", None),
        "metalrefinery": getattr(unit_components, "MetalRefineryComponent", None),
        "metalrefinerycomponent": getattr(unit_components, "MetalRefineryComponent", None),
        "crystalrefinery": getattr(unit_components, "CrystalRefineryComponent", None),
        "crystalrefinerycomponent": getattr(unit_components, "CrystalRefineryComponent", None),
        "hangar": getattr(unit_components, "HangarComponent", None),
        "hangarcomponent": getattr(unit_components, "HangarComponent", None),
        "strikecraftbay": getattr(unit_components, "StrikecraftBayComponent", None),
        "strikecraftbaycomponent": getattr(unit_components, "StrikecraftBayComponent", None),
        "trade": getattr(unit_components, "TradeComponent", None),
        "tradecomponent": getattr(unit_components, "TradeComponent", None),
        "civilianhabitat": getattr(unit_components, "CivilianHabitatComponent", None),
        "civilianhabitatcomponent": getattr(unit_components, "CivilianHabitatComponent", None),
        "orbitaldefense": getattr(unit_components, "OrbitalDefenseComponent", None),
        "orbitaldefensecomponent": getattr(unit_components, "OrbitalDefenseComponent", None),
        "antimatter": getattr(unit_components, "AntimatterStorage", None),
        "antimatterstorage": getattr(unit_components, "AntimatterStorage", None),
        "harvester": getattr(unit_components, "AntimatterHarvester", None),
        "antimatterharvester": getattr(unit_components, "AntimatterHarvester", None),
        "minelayer": getattr(unit_components, "MinelayerComponent", None),
        "minelayercomponent": getattr(unit_components, "MinelayerComponent", None),
        "marines": getattr(unit_components, "MarinesComponent", None),
        "marinescomponent": getattr(unit_components, "MarinesComponent", None),
        "intelligence": getattr(unit_components, "IntelligenceComponent", None),
        "intelligencecomponent": getattr(unit_components, "IntelligenceComponent", None),
        "abilities": getattr(unit_components, "AbilityComponent", None),
        "ability": getattr(unit_components, "AbilityComponent", None),
        "abilitycomponent": getattr(unit_components, "AbilityComponent", None),
    }
    return alias_map.get(normalized)


class AttackOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.ATTACK, parameters, parent_order)

    def get_state_data(self) -> Dict[str, Any]:
        state_data = super().get_state_data()
        target_unit_id = self.parameters.get("target_unit_id")
        target_name = None
        lookup_attempted = False
        lookup_success = False
        if target_unit_id and self.unit and self.unit.game:
            lookup_attempted = True
            target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id)
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
        super().execute(galaxy_ref)

        target_unit_id = self.parameters["target_unit_id"]
        galaxy = getattr(getattr(self.unit, "game", None), "galaxy", None) or galaxy_ref
        target_unit = galaxy.get_unit_by_id(target_unit_id) if galaxy else None

        target_component_type = resolve_component_type(self.parameters.get("target_component_type"))

        from entities import are_enemies
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
        eligible_turrets = weapons.eligible_turrets_for(target_unit)
        if not isinstance(eligible_turrets, (list, tuple)):
            eligible_turrets = list(getattr(weapons, "turrets", []))
        if not eligible_turrets:
            self.fail("capability_unavailable")
            weapons.clear_target()
            return
        weapons.set_target(target_unit, target_component_type)

        if self.unit.in_system != target_unit.in_system or self.unit.in_hex != target_unit.in_hex:
            in_the_same_system_and_hex = False
        else:
            in_the_same_system_and_hex = True

        in_range = False
        for turret in eligible_turrets:
            if distance(self.unit.position, target_unit.position) < turret.range:
                in_range = True
                break
            
        min_turret_range = min(turret.range for turret in eligible_turrets)

        if not in_the_same_system_and_hex or not in_range:
            move_order = MoveOrder.for_unit_approach(
                self.unit,
                target_unit,
                max(1.0, min_turret_range - 5.0),
                parent_order=self,
            )
            self.add_sub_order(move_order)

    def update(self, galaxy_ref: 'Galaxy') -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            super().update(galaxy_ref)
            return

        target_unit_id = self.parameters.get("target_unit_id")
        galaxy = getattr(getattr(self.unit, "game", None), "galaxy", None) or galaxy_ref
        target_unit = galaxy.get_unit_by_id(target_unit_id) if target_unit_id and galaxy else None

        from entities import are_enemies
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
        eligible_turrets = weapons.eligible_turrets_for(target_unit) if weapons else []
        if weapons and not isinstance(eligible_turrets, (list, tuple)):
            eligible_turrets = list(getattr(weapons, "turrets", []))
        if not weapons or not eligible_turrets:
            for child in list(self.sub_orders):
                child.cancel()
            self.sub_orders.clear()
            self.status = OrderStatus.FAILED
            if self._owns_weapon_engagement() and weapons:
                weapons.clear_target()
            return

        min_turret_range = min(turret.range for turret in eligible_turrets)

        in_the_same_system_and_hex = (self.unit.in_system == target_unit.in_system and self.unit.in_hex == target_unit.in_hex)
        
        in_range = False
        if in_the_same_system_and_hex:
            for turret in eligible_turrets:
                if distance(self.unit.position, target_unit.position) < turret.range:
                    in_range = True
                    break

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
                    logger.debug(f"[{self.unit.name}] Target {target_unit.name} is in weapon range. Cancelling movement.")
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
                            if abs(current_offset - (min_turret_range - 5.0)) > 15.0:
                                target_moved = True

                    if target_moved:
                        logger.debug(f"[{self.unit.name}] Target {target_unit.name} moved. Recalculating path.")
                        current_sub.cancel()
                        self.sub_orders.popleft()
                        has_movement_order = False

        # If we don't have a movement order, check if we need to move
        if not has_movement_order:
            if not in_the_same_system_and_hex or not in_range:
                move_order = MoveOrder.for_unit_approach(
                    self.unit,
                    target_unit,
                    max(1.0, min_turret_range - 5.0),
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
        target_unit = galaxy_ref.get_unit_by_id(target_unit_id) if galaxy_ref else None
        target_component_type_str = self.parameters.get("target_component_type")

        from entities import are_enemies
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
        target_id = self.parameters.get("target_unit_id")
        target = galaxy_ref.get_unit_by_id(target_id) if target_id else None
        weapons = self.unit.weapons_component
        from entities import are_enemies
        if target and weapons and are_enemies(self.unit.owner, target.owner) and weapons.eligible_turrets_for(target):
            weapons.set_target(target, resolve_component_type(self.parameters.get("target_component_type")))
        elif weapons:
            self.status = OrderStatus.FAILED
            weapons.clear_target()
        super().resume(galaxy_ref)


class ProtectOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.PROTECT, parameters, parent_order)

    def get_state_data(self) -> Dict[str, Any]:
        state_data = super().get_state_data()
        target_unit_id = self.parameters.get("target_unit_id")
        target_name = None
        lookup_attempted = False
        lookup_success = False
        if target_unit_id and self.unit and self.unit.game:
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
        target_unit = galaxy.get_unit_by_id(target_unit_id) if target_unit_id and galaxy else None

        if not target_unit:
            self.fail("target_unavailable")
            logger.debug(f"PROTECT order failed: Target unit {target_unit_id} not found.")
            return

        from entities import are_allies
        if not are_allies(self.unit.owner, target_unit.owner):
            self.fail("target_unavailable")
            logger.debug(f"PROTECT order failed: Target unit {target_unit.name} is not allied.")
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

        from entities import are_enemies
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
        target_unit = galaxy.get_unit_by_id(target_unit_id) if target_unit_id and galaxy else None

        from entities import are_allies
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

        # Check if we are currently executing an AttackOrder
        has_attack_order = False
        if self.sub_orders:
            current_sub = self.sub_orders[0]
            if current_sub.order_type == OrderType.ATTACK:
                has_attack_order = True
                enemy_id = current_sub.parameters.get("target_unit_id")
                enemy_unit = galaxy.get_unit_by_id(enemy_id) if enemy_id and galaxy else None
                from entities import are_enemies

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
                    logger.debug(f"[{self.unit.name}] Protect attack target lost, dead, or out of threat range. Resuming protection.")
                    current_sub.cancel()
                    self.sub_orders.popleft()
                    has_attack_order = False

        if not has_attack_order:
            # Look for nearby enemies to engage
            nearby_enemy = self._find_nearby_enemy(galaxy_ref, target_unit)
            if nearby_enemy:
                logger.debug(f"[{self.unit.name}] Enemy detected near protected target: {nearby_enemy.name}. Engaging!")
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
                            logger.debug(f"[{self.unit.name}] Protected unit {target_unit.name} moved. Recalculating path.")
                            current_sub.cancel()
                            self.sub_orders.popleft()
                            has_movement_order = False

                if has_movement_order:
                    # Cancel movement order if we are already close enough
                    if self.unit.in_system == target_unit.in_system and self.unit.in_hex == target_unit.in_hex:
                        dist_to_target = distance(self.unit.position, target_unit.position)
                        if dist_to_target <= DEFAULT_STANDOFF_DISTANCE:
                            logger.debug(f"[{self.unit.name}] Close enough to protected unit {target_unit.name}. Stopping movement.")
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
