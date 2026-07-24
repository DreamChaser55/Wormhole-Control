import logging
from typing import Dict, Optional, Any, TYPE_CHECKING

from utils import HexCoord
from geometry import Position, distance
from constants import HullSize
from .base import Order, OrderStatus, OrderType
from .movement import MoveOrder
from .combat import AttackOrder

if TYPE_CHECKING:
    from galaxy import Galaxy
    from entities import Unit

logger = logging.getLogger(__name__)


class PatrolOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.PATROL, parameters, parent_order)
        self.start_system_name = None
        self.start_hex_coord = None
        self.start_position = None
        self.patrol_phase = "TO_TARGET" # "TO_TARGET" or "TO_START"
        self.current_waypoint_index = 0

        if "waypoints" not in self.parameters and "destination_position" in self.parameters:
            self.parameters["waypoints"] = [{
                "system_name": self.parameters["destination_system_name"],
                "hex_coord": self.parameters["destination_hex_coord"],
                "position": self.parameters["destination_position"]
            }]

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)
        self.start_system_name = self.unit.in_system
        self.start_hex_coord = self.unit.in_hex
        self.start_position = Position(self.unit.position.x, self.unit.position.y)
        self.current_waypoint_index = 0
        self._spawn_move_to_current_waypoint()

    def _spawn_move_to_current_waypoint(self) -> None:
        wps = self.parameters.get("waypoints", [])
        if not wps:
            self.status = OrderStatus.FAILED
            return

        num_wps = len(wps)
        idx = self.current_waypoint_index
        if idx < num_wps:
            self.patrol_phase = "TO_TARGET"
            wp = wps[idx]
            move_params = {
                "destination_system_name": wp["system_name"],
                "destination_hex_coord": wp["hex_coord"],
                "destination_position": wp["position"]
            }
        else:
            self.patrol_phase = "TO_START"
            move_params = {
                "destination_system_name": self.start_system_name,
                "destination_hex_coord": self.start_hex_coord,
                "destination_position": self.start_position
            }
        self.add_sub_order(MoveOrder(self.unit, move_params, parent_order=self))

    def add_waypoint(self, system_name: str, hex_coord: HexCoord, position: Position) -> None:
        if "waypoints" not in self.parameters:
            self.parameters["waypoints"] = []
            if "destination_position" in self.parameters:
                self.parameters["waypoints"].append({
                    "system_name": self.parameters["destination_system_name"],
                    "hex_coord": self.parameters["destination_hex_coord"],
                    "position": self.parameters["destination_position"]
                })

        old_len = len(self.parameters["waypoints"])
        self.parameters["waypoints"].append({
            "system_name": system_name,
            "hex_coord": hex_coord,
            "position": position
        })

        if self.status == OrderStatus.IN_PROGRESS:
            if getattr(self, "current_waypoint_index", 0) == old_len:
                self.current_waypoint_index = old_len + 1

    def get_state_data(self) -> Dict[str, Any]:
        state_data = super().get_state_data()
        state_data["current_waypoint_index"] = getattr(self, "current_waypoint_index", 0)
        if "waypoints" in self.parameters:
            state_data["parameters"]["waypoints"] = self.parameters["waypoints"]
        return state_data

    def _find_nearby_enemy(self, galaxy_ref: 'Galaxy') -> Optional['Unit']:
        weapons = self.unit.weapons_component
        if not weapons or weapons.is_destroyed or not weapons.turrets:
            return None

        from unit_components import TurretVariant

        system = galaxy_ref.systems.get(self.unit.in_system)
        if not system:
            return None

        hex_obj = system.hexes.get(self.unit.in_hex)
        if not hex_obj:
            return None

        closest_enemy = None
        min_dist = float('inf')

        for unit in hex_obj.units:
            if unit.owner != self.unit.owner and unit.current_hit_points > 0:
                # Fighter/Bomber targeting rules
                if self.unit.hull_size == HullSize.STRIKECRAFT_WING:
                    wing_comp = self.unit.strikecraft_wing_component
                    if wing_comp:
                        from unit_components import WingType
                        if wing_comp.wing_type == WingType.FIGHTER:
                            if unit.hull_size != HullSize.STRIKECRAFT_WING:
                                continue
                        elif wing_comp.wing_type == WingType.BOMBER:
                            if unit.hull_size == HullSize.STRIKECRAFT_WING:
                                continue

                # Find maximum range of turrets that can target this unit
                can_target = False
                max_range_for_unit = 0.0
                for t in weapons.turrets:
                    if unit.hull_size == HullSize.STRIKECRAFT_WING and t.variant != TurretVariant.ANTI_STRIKECRAFT:
                        continue
                    can_target = True
                    if t.range > max_range_for_unit:
                        max_range_for_unit = t.range

                if not can_target:
                    continue

                dist = distance(self.unit.position, unit.position)
                if dist <= max_range_for_unit and dist < min_dist:
                    min_dist = dist
                    closest_enemy = unit

        return closest_enemy

    def update(self, galaxy_ref: 'Galaxy') -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            super().update(galaxy_ref)
            return

        # Check if we are currently executing an AttackOrder
        has_attack_order = False
        if self.sub_orders:
            current_sub = self.sub_orders[0]
            if current_sub.order_type == OrderType.ATTACK:
                has_attack_order = True
                target_id = current_sub.parameters.get("target_unit_id")
                target_unit = self.unit.game.galaxy.get_unit_by_id(target_id) if target_id else None
                if (not target_unit or 
                    target_unit.current_hit_points <= 0 or 
                    target_unit.in_system != self.unit.in_system or 
                    target_unit.in_hex != self.unit.in_hex):
                    # Target is dead, missing, or fled the sector. Cancel the attack order.
                    logger.debug(f"[{self.unit.name}] Patrol target lost, dead, or fled. Resuming patrol.")
                    current_sub.cancel()
                    self.sub_orders.popleft()
                    if self.unit.weapons_component:
                        self.unit.weapons_component.clear_target()
                    # Re-route to current waypoint destination
                    self._spawn_move_to_current_waypoint()
                    has_attack_order = False

        if not has_attack_order:
            # Look for nearby enemies to engage
            nearby_enemy = self._find_nearby_enemy(galaxy_ref)
            if nearby_enemy:
                logger.debug(f"[{self.unit.name}] Enemy detected: {nearby_enemy.name}. Engaging!")
                # Cancel current movement sub-orders
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

        super().update(galaxy_ref)

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return

        # If we reach here and sub-orders are empty, it means the current movement leg has finished.
        # Transition to the next phase of the patrol loop.
        wps = self.parameters.get("waypoints", [])
        num_wps = len(wps)
        self.current_waypoint_index = (self.current_waypoint_index + 1) % (num_wps + 1)
        self._spawn_move_to_current_waypoint()

        idx = self.current_waypoint_index
        if idx < num_wps:
            logger.debug(f"[{self.unit.name}] Patrol leg completed. Heading to waypoint {idx}: {wps[idx]['position']}")
        else:
            logger.debug(f"[{self.unit.name}] Patrol leg completed. Returning to start: {self.start_position}")
