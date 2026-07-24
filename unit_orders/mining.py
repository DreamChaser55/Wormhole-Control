import logging
import typing
from typing import Dict, Optional, Any, TYPE_CHECKING

from geometry import distance, hex_distance, move_towards_position
from pathfinding import find_intersystem_path
from .base import Order, OrderStatus, OrderType
from .movement import MoveOrder

if TYPE_CHECKING:
    from galaxy import Galaxy
    from entities import Unit

logger = logging.getLogger(__name__)


class MineOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.MINE, parameters, parent_order)

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        target_id = self.parameters.get("target_id")
        if not target_id:
            self.status = OrderStatus.FAILED
            logger.debug(f"MINE order failed: no target_id.")
            return

        target = galaxy_ref.get_celestial_body_by_id(target_id)
        if not target:
            self.status = OrderStatus.FAILED
            logger.debug(f"MINE order failed: Celestial body with ID {target_id} not found.")
            return

        if not getattr(self.unit, 'mining_component', None):
            self.status = OrderStatus.FAILED
            logger.debug(f"MINE order failed: Unit {self.unit.name} has no MiningComponent.")
            return

        at_location = (self.unit.in_system == target.in_system and self.unit.in_hex == target.in_hex)
        in_range = at_location and (distance(self.unit.position, target.position) <= self.unit.mining_component.mining_range)

        if not in_range:
            if not self.has_active_sub_orders():
                if at_location:
                    dest_pos = move_towards_position(self.unit.position, target.position, self.unit.mining_component.mining_range - 5.0)
                else:
                    dest_pos = target.position

                move_params = {
                    "destination_system_name": target.in_system,
                    "destination_hex_coord": target.in_hex,
                    "destination_position": dest_pos
                }
                move_order = MoveOrder(self.unit, move_params, parent_order=self)
                self.add_sub_order(move_order)

                mine_sub_order = MineOrder(self.unit, self.parameters, parent_order=self)
                self.add_sub_order(mine_sub_order)
            return

        self.unit.mining_component.set_target(target)
        logger.debug(f"MINE order: {self.unit.name} started mining {target.name}.")

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return
        if self.unit.mining_component:
            if self.unit.mining_component.get_cargo_fullness() >= 1.0:
                self.status = OrderStatus.COMPLETED
                self.unit.mining_component.clear_target()
                logger.debug(f"MINE order completed: Cargo full for {self.unit.name}.")


class UnloadResourcesOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.UNLOAD_RESOURCES, parameters, parent_order)

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        target_unit_id = self.parameters.get("target_unit_id")
        target_unit = galaxy_ref.get_unit_by_id(target_unit_id)

        if not target_unit:
            self.status = OrderStatus.FAILED
            logger.debug(f"UNLOAD_RESOURCES order failed: Target unit {target_unit_id} not found.")
            return

        if not getattr(self.unit, 'mining_component', None):
            self.status = OrderStatus.FAILED
            logger.debug(f"UNLOAD_RESOURCES order failed: Unit {self.unit.name} has no MiningComponent.")
            return

        is_metal_refinery = bool(getattr(target_unit, 'metal_refinery_component', None))
        is_crystal_refinery = bool(getattr(target_unit, 'crystal_refinery_component', None))

        if not (is_metal_refinery or is_crystal_refinery):
            self.status = OrderStatus.FAILED
            logger.debug(f"UNLOAD_RESOURCES order failed: Target {target_unit.name} has no refinery components.")
            return

        # Determine unload range from either component
        unload_range = 300.0
        if is_metal_refinery:
            unload_range = target_unit.metal_refinery_component.unload_range
        elif is_crystal_refinery:
            unload_range = target_unit.crystal_refinery_component.unload_range

        at_location = (self.unit.in_system == target_unit.in_system and self.unit.in_hex == target_unit.in_hex)
        in_range = at_location and (distance(self.unit.position, target_unit.position) <= unload_range)

        if not in_range:
            if not self.has_active_sub_orders():
                if at_location:
                    dest_pos = move_towards_position(self.unit.position, target_unit.position, unload_range - 5.0)
                else:
                    dest_pos = target_unit.position

                move_params = {
                    "destination_system_name": target_unit.in_system,
                    "destination_hex_coord": target_unit.in_hex,
                    "destination_position": dest_pos
                }
                move_order = MoveOrder(self.unit, move_params, parent_order=self)
                self.add_sub_order(move_order)

                unload_sub_order = UnloadResourcesOrder(self.unit, self.parameters, parent_order=self)
                self.add_sub_order(unload_sub_order)
            return

        # We are in range, execute unload
        metal_amount, crystal_amount = self.unit.mining_component.unload_to_refinery(
            unload_metal=is_metal_refinery,
            unload_crystal=is_crystal_refinery
        )

        if is_metal_refinery and metal_amount > 0:
            target_unit.metal_refinery_component.accept_resources(metal_amount)

        if is_crystal_refinery and crystal_amount > 0:
            target_unit.crystal_refinery_component.accept_resources(crystal_amount)

        self.status = OrderStatus.COMPLETED
        logger.debug(f"UNLOAD_RESOURCES order completed: {self.unit.name} unloaded resources to {target_unit.name}.")

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return
        # Execution is immediate once in range, so handled above.
        if not self.sub_orders:
            self.status = OrderStatus.COMPLETED


class ContinuousMineOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.CONTINUOUS_MINE, parameters, parent_order)

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        target_id = self.parameters.get("target_id")
        if not target_id:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] CONTINUOUS_MINE order failed: no target_id.")
            return

        target = galaxy_ref.get_celestial_body_by_id(target_id)
        if not target:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] CONTINUOUS_MINE order failed: Celestial body with ID {target_id} not found.")
            return

        if not getattr(self.unit, 'mining_component', None):
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] CONTINUOUS_MINE order failed: Unit has no MiningComponent.")
            return

        mining_comp = self.unit.mining_component
        if mining_comp.get_cargo_fullness() >= 1.0:
            refinery = self._find_closest_refinery(galaxy_ref)
            if not refinery:
                self.status = OrderStatus.FAILED
                logger.debug(f"[{self.unit.name}] CONTINUOUS_MINE order failed: Cargo full but no refinery found.")
                return
            self._spawn_unload_order(refinery.id)
        else:
            self._spawn_mine_order(target_id)

    def _spawn_mine_order(self, target_id: str) -> None:
        mine_params = {"target_id": target_id}
        self.add_sub_order(MineOrder(self.unit, mine_params, parent_order=self))

    def _spawn_unload_order(self, refinery_id: typing.Union[str, int]) -> None:
        unload_params = {"target_unit_id": refinery_id}
        self.add_sub_order(UnloadResourcesOrder(self.unit, unload_params, parent_order=self))

    def _find_closest_refinery(self, galaxy_ref: 'Galaxy') -> Optional['Unit']:
        mining_comp = self.unit.mining_component
        if not mining_comp:
            return None

        has_metal = mining_comp.raw_metal_cargo > 0
        has_crystal = mining_comp.raw_crystal_cargo > 0

        target = galaxy_ref.get_celestial_body_by_id(self.parameters.get("target_id"))
        from entities import Asteroid, AsteroidField, Moon
        if not has_metal and not has_crystal and target:
            if isinstance(target, (Asteroid, AsteroidField)):
                has_metal = True
            elif isinstance(target, Moon):
                has_crystal = True

        friendly_refineries = []
        for system in galaxy_ref.systems.values():
            for hex_obj in system.hexes.values():
                for u in hex_obj.units:
                    if u.owner == self.unit.owner:
                        is_metal_ref = getattr(u, 'metal_refinery_component', None) is not None
                        is_crystal_ref = getattr(u, 'crystal_refinery_component', None) is not None
                        if (has_metal and is_metal_ref) or (has_crystal and is_crystal_ref):
                            friendly_refineries.append(u)

        if not friendly_refineries:
            return None

        def get_dist_to_refinery(refinery):
            if self.unit.in_system == refinery.in_system:
                if self.unit.in_hex == refinery.in_hex:
                    return distance(self.unit.position, refinery.position)
                else:
                    return hex_distance(self.unit.in_hex, refinery.in_hex) * 10000.0
            else:
                path = find_intersystem_path(galaxy_ref.system_graph, self.unit.in_system, refinery.in_system, self.unit.hull_size)
                if path is None:
                    return float('inf')
                return (len(path) - 1) * 1000000.0 + hex_distance(self.unit.in_hex, refinery.in_hex) * 10000.0

        nearest_refinery = None
        min_dist = float('inf')
        for r in friendly_refineries:
            dist = get_dist_to_refinery(r)
            if dist < min_dist:
                min_dist = dist
                nearest_refinery = r

        return nearest_refinery

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return

        if not self.sub_orders:
            galaxy_ref = self.unit.game.galaxy
            target_id = self.parameters.get("target_id")
            
            mining_comp = self.unit.mining_component
            if not mining_comp:
                self.status = OrderStatus.FAILED
                return

            if mining_comp.get_cargo_fullness() >= 1.0:
                refinery = self._find_closest_refinery(galaxy_ref)
                if not refinery:
                    self.status = OrderStatus.FAILED
                    logger.debug(f"[{self.unit.name}] ContinuousMineOrder failed: cargo full, no refinery found.")
                    return
                self._spawn_unload_order(refinery.id)
                logger.debug(f"[{self.unit.name}] ContinuousMineOrder: cargo full. Heading to refinery {refinery.name} (id:{refinery.id}).")
            else:
                self._spawn_mine_order(target_id)
                logger.debug(f"[{self.unit.name}] ContinuousMineOrder: cargo has space. Heading back to mine target {target_id}.")
