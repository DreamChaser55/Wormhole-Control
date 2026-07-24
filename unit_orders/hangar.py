import logging
from typing import Dict, Optional, Any, TYPE_CHECKING

from geometry import distance, move_towards_position
from constants import HullSize
from .base import Order, OrderStatus, OrderType
from .movement import MoveOrder

if TYPE_CHECKING:
    from galaxy import Galaxy
    from entities import Unit

logger = logging.getLogger(__name__)


class DockOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.DOCK, parameters, parent_order)

    def get_state_data(self) -> Dict[str, Any]:
        state_data = super().get_state_data()
        target_carrier_id = self.parameters.get("target_carrier_id")
        target_name = None
        if target_carrier_id and self.unit and self.unit.game:
            target_carrier = self.unit.game.galaxy.get_unit_by_id(target_carrier_id)
            if target_carrier:
                target_name = target_carrier.name
        state_data["target_carrier_id"] = target_carrier_id
        state_data["target_name"] = target_name
        return state_data

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        target_carrier_id = self.parameters.get("target_carrier_id")
        target_carrier = self.unit.game.galaxy.get_unit_by_id(target_carrier_id)

        if not target_carrier:
            self.status = OrderStatus.FAILED
            logger.debug(f"DOCK order failed: Target carrier {target_carrier_id} not found.")
            return

        docking_component = None
        if self.unit.hull_size == HullSize.STRIKECRAFT_WING and target_carrier.strikecraft_bay_component:
            docking_component = target_carrier.strikecraft_bay_component
        elif target_carrier.hangar_component:
            docking_component = target_carrier.hangar_component

        if not docking_component:
            self.status = OrderStatus.FAILED
            logger.debug(f"DOCK order failed: Target carrier {target_carrier.name} has no compatible hangar/strikecraftbay for {self.unit.name}.")
            return

        if not docking_component.can_dock(self.unit):
            self.status = OrderStatus.FAILED
            logger.debug(f"DOCK order failed: Target carrier {target_carrier.name} has no space/slots for {self.unit.name}.")
            return

        docking_range = 100.0
        in_same_system_and_hex = (self.unit.in_system == target_carrier.in_system and self.unit.in_hex == target_carrier.in_hex)
        in_range = in_same_system_and_hex and (distance(self.unit.position, target_carrier.position) <= docking_range)

        if not in_range:
            if in_same_system_and_hex:
                dest_pos = move_towards_position(self.unit.position, target_carrier.position, docking_range - 5.0)
            else:
                dest_pos = target_carrier.position

            move_params = {
                "destination_system_name": target_carrier.in_system,
                "destination_hex_coord": target_carrier.in_hex,
                "destination_position": dest_pos
            }
            move_order = MoveOrder(self.unit, move_params, parent_order=self)
            self.add_sub_order(move_order)

            dock_sub_order = DockOrder(self.unit, self.parameters, parent_order=self)
            self.add_sub_order(dock_sub_order)
            return

        success = docking_component.dock(self.unit, galaxy_ref)
        if success:
            self.status = OrderStatus.COMPLETED
            logger.debug(f"Unit {self.unit.name} successfully docked to {target_carrier.name}.")
        else:
            self.status = OrderStatus.FAILED
            logger.debug(f"Docking of {self.unit.name} to {target_carrier.name} failed.")

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return
        if not self.sub_orders:
            self.status = OrderStatus.COMPLETED


class DeployUnitOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.DEPLOY_UNIT, parameters, parent_order)

    def get_state_data(self) -> Dict[str, Any]:
        state_data = super().get_state_data()
        docked_unit_id = self.parameters.get("docked_unit_id")
        docked_name = None
        if docked_unit_id and self.unit and self.unit.game:
            docked_units = []
            if self.unit.hangar_component:
                docked_units.extend(self.unit.hangar_component.docked_units)
            if self.unit.strikecraft_bay_component:
                docked_units.extend(self.unit.strikecraft_bay_component.docked_units)
            for du in docked_units:
                if du.id == docked_unit_id:
                    docked_name = du.name
                    break
        state_data["docked_unit_id"] = docked_unit_id
        state_data["docked_name"] = docked_name
        return state_data

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        if not self.unit.hangar_component and not self.unit.strikecraft_bay_component:
            self.status = OrderStatus.FAILED
            logger.debug(f"DEPLOY_UNIT order failed: Unit {self.unit.name} has no HangarComponent or StrikecraftBayComponent.")
            return

        docked_unit_id = self.parameters.get("docked_unit_id")
        docked_unit = None
        source_component = None
        
        if self.unit.hangar_component:
            for du in self.unit.hangar_component.docked_units:
                if du.id == docked_unit_id:
                    docked_unit = du
                    source_component = self.unit.hangar_component
                    break
        if not docked_unit and self.unit.strikecraft_bay_component:
            for du in self.unit.strikecraft_bay_component.docked_units:
                if du.id == docked_unit_id:
                    docked_unit = du
                    source_component = self.unit.strikecraft_bay_component
                    break

        if not docked_unit:
            self.status = OrderStatus.FAILED
            logger.debug(f"DEPLOY_UNIT order failed: Docked unit {docked_unit_id} not found in hangar or strikecraft bay.")
            return

        success = source_component.deploy(docked_unit, galaxy_ref)
        if success:
            self.status = OrderStatus.COMPLETED
            logger.debug(f"Unit {docked_unit.name} successfully deployed from {self.unit.name}.")
        else:
            self.status = OrderStatus.FAILED
            logger.debug(f"Deployment of {docked_unit.name} from {self.unit.name} failed.")

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return
        if not self.sub_orders:
            self.status = OrderStatus.COMPLETED


class DeployAllWingsOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.DEPLOY_ALL_WINGS, parameters, parent_order)

    def get_state_data(self) -> Dict[str, Any]:
        state_data = super().get_state_data()
        return state_data

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        if not self.unit.strikecraft_bay_component:
            self.status = OrderStatus.FAILED
            logger.debug(f"DEPLOY_ALL_WINGS order failed: Unit {self.unit.name} has no StrikecraftBayComponent.")
            return

        comp = self.unit.strikecraft_bay_component
        if not comp.docked_units:
            self.status = OrderStatus.COMPLETED
            logger.debug(f"DEPLOY_ALL_WINGS: No docked strikecraft wings to deploy on {self.unit.name}.")
            return

        docked_copy = list(comp.docked_units)
        success_count = 0
        for docked_unit in docked_copy:
            success = comp.deploy(docked_unit, galaxy_ref)
            if success:
                success_count += 1

        if success_count > 0:
            self.status = OrderStatus.COMPLETED
            logger.debug(f"Successfully deployed {success_count} fighter wings from {self.unit.name}.")
        else:
            self.status = OrderStatus.FAILED
            logger.debug(f"Failed to deploy any fighter wings from {self.unit.name}.")

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return
        if not self.sub_orders:
            self.status = OrderStatus.COMPLETED
