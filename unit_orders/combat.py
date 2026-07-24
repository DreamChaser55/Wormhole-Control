import logging
from typing import Dict, Optional, Any, TYPE_CHECKING

from geometry import Position, distance, move_towards_position
from constants import HullSize
from .base import Order, OrderStatus, OrderType
from .movement import MoveOrder

if TYPE_CHECKING:
    from galaxy import Galaxy
    from entities import Unit

logger = logging.getLogger(__name__)


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
        state_data["lookup_attempted"] = lookup_attempted
        state_data["lookup_success"] = lookup_success
        return state_data

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        target_unit_id = self.parameters["target_unit_id"]
        target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id)

        target_component_type_str = self.parameters.get("target_component_type")
        target_component_type = None
        if target_component_type_str:
            import unit_components
            target_component_type = getattr(unit_components, target_component_type_str, None)

        if not target_unit:
            self.status = OrderStatus.FAILED
            return
        
        if self.unit.weapons_component:
            self.unit.weapons_component.set_target(target_unit, target_component_type)

            if self.unit.in_system != target_unit.in_system or self.unit.in_hex != target_unit.in_hex:
                in_the_same_system_and_hex = False
            else:
                in_the_same_system_and_hex = True

            in_range = False
            for turret in self.unit.weapons_component.turrets:
                if distance(self.unit.position, target_unit.position) < turret.range:
                    in_range = True
                    break
            
            min_turret_range = min(turret.range for turret in self.unit.weapons_component.turrets)

            if not in_the_same_system_and_hex or not in_range:
                dest_pos = move_towards_position(self.unit.position, target_unit.position, min_turret_range - 5.0)

                move_params = {
                    "destination_system_name": target_unit.in_system,
                    "destination_hex_coord": target_unit.in_hex,
                    "destination_position": dest_pos
                }
                move_order = MoveOrder(self.unit, move_params, parent_order=self)
                self.add_sub_order(move_order)

    def update(self, galaxy_ref: 'Galaxy') -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            super().update(galaxy_ref)
            return

        target_unit_id = self.parameters.get("target_unit_id")
        target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id) if target_unit_id else None

        if not target_unit or target_unit.current_hit_points <= 0:
            super().update(galaxy_ref)
            return

        weapons = self.unit.weapons_component
        if not weapons or not weapons.turrets:
            super().update(galaxy_ref)
            return

        min_turret_range = min(turret.range for turret in weapons.turrets)

        in_the_same_system_and_hex = (self.unit.in_system == target_unit.in_system and self.unit.in_hex == target_unit.in_hex)
        
        in_range = False
        if in_the_same_system_and_hex:
            for turret in weapons.turrets:
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
                    if self.unit.engines_component:
                        self.unit.engines_component.move_target = None
                    if self.unit.hyperdrive_component:
                        self.unit.hyperdrive_component.hex_jump_target = None
                        self.unit.hyperdrive_component.wormhole_jump_target = None
                    has_movement_order = False
                else:
                    # Otherwise, check if target has moved away from our movement destination parameters
                    target_moved = False
                    if dest_system != target_unit.in_system or dest_hex != target_unit.in_hex:
                        target_moved = True
                    elif dest_pos:
                        current_offset = distance(dest_pos, target_unit.position)
                        if abs(current_offset - (min_turret_range - 5.0)) > 15.0:
                            target_moved = True

                    if target_moved:
                        logger.debug(f"[{self.unit.name}] Target {target_unit.name} moved. Recalculating path.")
                        current_sub.cancel()
                        self.sub_orders.popleft()
                        if self.unit.engines_component:
                            self.unit.engines_component.move_target = None
                        if self.unit.hyperdrive_component:
                            self.unit.hyperdrive_component.hex_jump_target = None
                            self.unit.hyperdrive_component.wormhole_jump_target = None
                        has_movement_order = False

        # If we don't have a movement order, check if we need to move
        if not has_movement_order:
            if not in_the_same_system_and_hex or not in_range:
                dest_pos = move_towards_position(self.unit.position, target_unit.position, min_turret_range - 5.0)
                move_params = {
                    "destination_system_name": target_unit.in_system,
                    "destination_hex_coord": target_unit.in_hex,
                    "destination_position": dest_pos
                }
                move_order = MoveOrder(self.unit, move_params, parent_order=self)
                self.add_sub_order(move_order)

        super().update(galaxy_ref)

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return
        target_unit_id = self.parameters["target_unit_id"]
        target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id)
        target_component_type_str = self.parameters.get("target_component_type")

        if not target_unit or target_unit.current_hit_points <= 0:
            self.status = OrderStatus.COMPLETED
            if self.unit.weapons_component:
                self.unit.weapons_component.clear_target()
            return
            
        if target_component_type_str:
            import unit_components
            target_component_type = getattr(unit_components, target_component_type_str, None)
            if target_component_type:
                target_component = target_unit.get_component(target_component_type)
                if not target_component or target_component.is_destroyed:
                    self.status = OrderStatus.COMPLETED
                    if self.unit.weapons_component:
                        self.unit.weapons_component.clear_target()


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
        target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id) if target_unit_id else None

        if not target_unit:
            self.status = OrderStatus.FAILED
            logger.debug(f"PROTECT order failed: Target unit {target_unit_id} not found.")
            return

        if target_unit.owner != self.unit.owner:
            self.status = OrderStatus.FAILED
            logger.debug(f"PROTECT order failed: Target unit {target_unit.name} is not friendly.")
            return

    def _find_nearby_enemy(self, galaxy_ref: 'Galaxy', target_unit: 'Unit') -> Optional['Unit']:
        weapons = self.unit.weapons_component
        if not weapons or weapons.is_destroyed or not weapons.turrets:
            return None

        from unit_components import TurretVariant, WingType

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

        for candidate in hex_obj.units:
            if candidate.owner != self.unit.owner and candidate.current_hit_points > 0:
                # Fighter/Bomber targeting rules
                if self.unit.hull_size == HullSize.STRIKECRAFT_WING:
                    wing_comp = self.unit.strikecraft_wing_component
                    if wing_comp:
                        if wing_comp.wing_type == WingType.FIGHTER:
                            if candidate.hull_size != HullSize.STRIKECRAFT_WING:
                                continue
                        elif wing_comp.wing_type == WingType.BOMBER:
                            if candidate.hull_size == HullSize.STRIKECRAFT_WING:
                                continue

                can_target = False
                for t in weapons.turrets:
                    if candidate.hull_size == HullSize.STRIKECRAFT_WING and t.variant != TurretVariant.ANTI_STRIKECRAFT:
                        continue
                    can_target = True
                    break

                if not can_target:
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
        target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id) if target_unit_id else None

        if not target_unit or target_unit.current_hit_points <= 0:
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
                enemy_unit = self.unit.game.galaxy.get_unit_by_id(enemy_id) if enemy_id else None

                is_in_range = False
                if (enemy_unit and 
                        enemy_unit.current_hit_points > 0 and 
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
                    if self.unit.weapons_component:
                        self.unit.weapons_component.clear_target()
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
                if self.unit.engines_component:
                    self.unit.engines_component.move_target = None
                if self.unit.hyperdrive_component:
                    self.unit.hyperdrive_component.hex_jump_target = None
                    self.unit.hyperdrive_component.wormhole_jump_target = None

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
                        if (dest_system != target_unit.in_system or
                                dest_hex != target_unit.in_hex or
                                (dest_pos and distance(dest_pos, target_unit.position) > 15.0)):
                            logger.debug(f"[{self.unit.name}] Protected unit {target_unit.name} moved. Recalculating path.")
                            current_sub.cancel()
                            self.sub_orders.popleft()
                            has_movement_order = False

                if has_movement_order:
                    # Cancel movement order if we are already close enough
                    if self.unit.in_system == target_unit.in_system and self.unit.in_hex == target_unit.in_hex:
                        dist_to_target = distance(self.unit.position, target_unit.position)
                        if dist_to_target <= 30.0:
                            logger.debug(f"[{self.unit.name}] Close enough to protected unit {target_unit.name}. Stopping movement.")
                            if self.sub_orders:
                                self.sub_orders[0].cancel()
                                self.sub_orders.popleft()
                            if self.unit.engines_component:
                                self.unit.engines_component.move_target = None
                            has_movement_order = False

                if not has_movement_order:
                    in_same_system_and_hex = (self.unit.in_system == target_unit.in_system and self.unit.in_hex == target_unit.in_hex)
                    dist_to_target = distance(self.unit.position, target_unit.position) if in_same_system_and_hex else float('inf')

                    if not in_same_system_and_hex or dist_to_target > 30.0:
                        move_params = {
                            "destination_system_name": target_unit.in_system,
                            "destination_hex_coord": target_unit.in_hex,
                            "destination_position": Position(target_unit.position.x, target_unit.position.y)
                        }
                        self.add_sub_order(MoveOrder(self.unit, move_params, parent_order=self))

        super().update(galaxy_ref)

    def check_completion_conditions(self) -> None:
        pass
