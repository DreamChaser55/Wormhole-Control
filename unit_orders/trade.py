import logging
import typing
from typing import Dict, Optional, Any, List, Tuple, TYPE_CHECKING

from constants import TRADE_ARRIVAL_RANGE
from geometry import distance
from .base import Order, OrderStatus, OrderType
from .movement import MoveOrder

if TYPE_CHECKING:
    from galaxy import Galaxy
    from entities import Unit

logger = logging.getLogger(__name__)


class TradeOrder(Order):
    """Order instructing a ship with a TradeComponent to travel to an active
    Civilian Habitat unit and execute a trade transaction.
    """
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.TRADE, parameters, parent_order)

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        target_unit_id = self.parameters.get("target_unit_id")
        if not target_unit_id:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] TRADE order failed: no target_unit_id.")
            return

        target_unit = galaxy_ref.get_unit_by_id(target_unit_id)
        if not target_unit:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] TRADE order failed: target unit {target_unit_id} not found.")
            return

        trade_comp = getattr(self.unit, 'trade_component', None)
        if not trade_comp or trade_comp.is_destroyed:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] TRADE order failed: unit has no functioning TradeComponent.")
            return

        hab_comp = getattr(target_unit, 'civilian_habitat_component', None)
        if not hab_comp or hab_comp.is_destroyed:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] TRADE order failed: target {target_unit.name} has no functioning CivilianHabitatComponent.")
            return

        if not hab_comp.is_active(galaxy_ref):
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] TRADE order failed: target {target_unit.name} civilian habitat is inactive.")
            return

        at_location = (self.unit.in_system == target_unit.in_system and self.unit.in_hex == target_unit.in_hex)
        in_range = at_location and (distance(self.unit.position, target_unit.position) <= TRADE_ARRIVAL_RANGE)

        if not in_range:
            if not self.has_active_sub_orders():
                move_order = MoveOrder.for_unit_approach(
                    self.unit,
                    target_unit,
                    max(10.0, TRADE_ARRIVAL_RANGE - 10.0),
                    parent_order=self,
                )
                self.add_sub_order(move_order)

                trade_sub_order = TradeOrder(self.unit, self.parameters, parent_order=self)
                self.add_sub_order(trade_sub_order)
            return

        success, income, msg = trade_comp.execute_trade(target_unit, galaxy_ref)
        if success:
            self.status = OrderStatus.COMPLETED
            logger.debug(f"[{self.unit.name}] TRADE order completed: {msg}")
        else:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] TRADE order failed: {msg}")

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return

        if not self.sub_orders:
            galaxy_ref = self.unit.game.galaxy if getattr(self.unit, 'game', None) else None
            if not galaxy_ref:
                self.status = OrderStatus.FAILED
                return

            target_unit_id = self.parameters.get("target_unit_id")
            target_unit = galaxy_ref.get_unit_by_id(target_unit_id)
            if not target_unit:
                self.status = OrderStatus.FAILED
                return

            trade_comp = getattr(self.unit, 'trade_component', None)
            if not trade_comp or trade_comp.is_destroyed:
                self.status = OrderStatus.FAILED
                return

            success, income, msg = trade_comp.execute_trade(target_unit, galaxy_ref)
            if success:
                self.status = OrderStatus.COMPLETED
                logger.debug(f"[{self.unit.name}] TRADE order completed on arrival: {msg}")
            else:
                self.status = OrderStatus.FAILED
                logger.debug(f"[{self.unit.name}] TRADE order failed on arrival: {msg}")


class ContinuousTradeOrder(Order):
    """Automated order where a trade ship continuously travels between active
    Civilian Habitat components located in different sectors to maximize trade income.
    """
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.CONTINUOUS_TRADE, parameters, parent_order)

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        trade_comp = getattr(self.unit, 'trade_component', None)
        if not trade_comp or trade_comp.is_destroyed:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] CONTINUOUS_TRADE order failed: unit has no TradeComponent.")
            return

        self._plan_next_trade_leg(galaxy_ref)

    def _get_active_habitats(self, galaxy_ref: 'Galaxy') -> List['Unit']:
        """Finds all friendly units with active Civilian Habitat components."""
        active_habitats: List['Unit'] = []
        for system in galaxy_ref.systems.values():
            for hex_obj in system.hexes.values():
                for u in hex_obj.units:
                    if u.owner == self.unit.owner:
                        hab_comp = getattr(u, 'civilian_habitat_component', None)
                        if hab_comp and not hab_comp.is_destroyed and hab_comp.is_active(galaxy_ref):
                            active_habitats.append(u)
        return active_habitats

    def _plan_next_trade_leg(self, galaxy_ref: 'Galaxy') -> None:
        trade_comp = getattr(self.unit, 'trade_component', None)
        if not trade_comp or trade_comp.is_destroyed:
            self.status = OrderStatus.FAILED
            return

        all_active = self._get_active_habitats(galaxy_ref)
        if not all_active:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] CONTINUOUS_TRADE failed: No active Civilian Habitats found in galaxy.")
            return

        current_sector = (self.unit.in_system, tuple(self.unit.in_hex))
        last_sector = trade_comp.last_traded_sector

        # If we haven't traded yet, and we are currently at an active habitat in this sector,
        # prime our start location at this habitat.
        if last_sector is None:
            here_habitats = [h for h in all_active if (h.in_system, tuple(h.in_hex)) == current_sector]
            if here_habitats:
                trade_comp.execute_trade(here_habitats[0], galaxy_ref)
                last_sector = trade_comp.last_traded_sector

        # Candidates must be in a DIFFERENT sector from the last traded sector
        if last_sector is not None:
            valid_targets = [h for h in all_active if (h.in_system, tuple(h.in_hex)) != last_sector]
        else:
            # If still None, pick any active habitat
            valid_targets = all_active

        if not valid_targets:
            logger.debug(f"[{self.unit.name}] CONTINUOUS_TRADE: All active habitats are in the current/last traded sector. Waiting for habitat in another sector.")
            return

        # Select the target that yields the highest trade payout (longest distance)
        best_target = None
        max_income = -1.0
        ref_sector = last_sector or current_sector

        for hab in valid_targets:
            hab_sector = (hab.in_system, tuple(hab.in_hex))
            income = trade_comp.calculate_trade_income(ref_sector, hab_sector, galaxy_ref)
            if income > max_income:
                max_income = income
                best_target = hab

        if best_target:
            logger.debug(f"[{self.unit.name}] CONTINUOUS_TRADE: Selected habitat {best_target.name} (id:{best_target.id}) in {best_target.in_system} {best_target.in_hex} for estimated payout {max_income:.0f}c.")
            trade_params = {"target_unit_id": best_target.id}
            self.add_sub_order(TradeOrder(self.unit, trade_params, parent_order=self))
        else:
            self.status = OrderStatus.FAILED

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return

        if not self.sub_orders:
            galaxy_ref = self.unit.game.galaxy if getattr(self.unit, 'game', None) else None
            if not galaxy_ref:
                self.status = OrderStatus.FAILED
                return

            self._plan_next_trade_leg(galaxy_ref)
