import logging
import typing
from typing import Dict, Optional, Any, TYPE_CHECKING, Deque
from enum import Enum, auto
from collections import deque

from constants import HullSize

if TYPE_CHECKING:
    from galaxy import Galaxy, Wormhole
    from entities import Unit

logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    """Enum representing the possible states of an Order."""
    PENDING = auto()      # Order has been created but not started
    IN_PROGRESS = auto()  # Order is currently being executed
    COMPLETED = auto()    # Order has been successfully completed
    FAILED = auto()       # Order has failed and cannot be completed
    CANCELLED = auto()    # Order was cancelled before completion


class OrderType(Enum):
    """Enum representing the different types of orders."""
    REACH_WAYPOINT = auto() # Move to a waypoint (system, hex, position). No dynamic planning or sub-order spawning. Simple movement to a single location. Spawned as sub-order(s) of MOVE.
    MOVE = auto()           # High-level move to a location (system, hex, position). Will plan a potentially multi-leg route to the destination and spawn one or more sub-orders of REACH_WAYPOINT.
    PATROL = auto()         # Patrol between positions
    ATTACK = auto()         # Attack a target
    DEFEND = auto()         # Defend a position or unit
    PROTECT = auto()        # Protect a friendly unit, follow it and attack nearby enemies
    TOGGLE_INHIBITOR = auto() # Turn the hyperspace inhibitor on or off
    COLONIZE = auto()       # Unload population to colonize a planet
    LOAD_COLONISTS = auto() # Load population from a planet
    CONSTRUCT = auto()      # Construct a new unit/station
    REPAIR = auto()         # Repair a damaged friendly unit
    MINE = auto()           # Mine raw resources from a celestial body
    UNLOAD_RESOURCES = auto() # Unload raw resources to a refinery
    DOCK = auto()
    DEPLOY_UNIT = auto()
    DEPLOY_ALL_WINGS = auto()
    USE_ABILITY = auto()  # Use a special ability (with optional target unit or position)
    CONTINUOUS_MINE = auto() # Cycles between mining and unloading at closest refinery
    TRANSFER_ANTIMATTER = auto() # Transfer antimatter from this unit's storage to a friendly target unit


class Order:
    """Represents an order given to a unit by the player.
    
    Orders can contain sub-orders that must be completed before the main order
    is considered complete. This creates a recursive order structure.
    """
    order_counter = 0

    def __init__(self, unit: 'Unit', order_type: OrderType, parameters: Dict[str, Any] = None, parent_order: Optional['Order'] = None):
        self.unit = unit
        self.order_id = Order.order_counter
        Order.order_counter += 1
        self.order_type = order_type
        self.parameters = parameters or {}
        self.status = OrderStatus.PENDING
        self.sub_orders: Deque['Order'] = deque()
        self.parent_order = parent_order

    def get_state_data(self) -> Dict[str, Any]:
        """Returns raw structured state data for this order."""
        return {
            "order_type": self.order_type.name,
            "status": self.status.name,
            "parameters": self.parameters,
        }

    def add_sub_order(self, sub_order: 'Order') -> None:
        """Add a sub-order to this order's queue."""
        sub_order.parent_order = self
        sub_order.unit = self.unit
        self.sub_orders.append(sub_order)
        logger.debug(f"  Added sub-order {sub_order.order_type.name} (id:{sub_order.order_id}) to order {self.order_type.name} (id:{self.order_id}) for unit {self.unit.name} (id:{self.unit.id}).")
        
    def remove_sub_order(self, order_id: typing.Union[str, int]) -> bool:
        """Remove a sub-order from the queue by its ID.
        
        Returns True if the order was found and removed, False otherwise.
        """
        for i, order in enumerate(self.sub_orders):
            if order.order_id == order_id:
                self.sub_orders.remove(order)
                return True
        return False

    def is_completed(self) -> bool:
        """Check if this order and all its sub-orders are completed."""
        if self.status != OrderStatus.COMPLETED:
            return False
            
        for sub_order in self.sub_orders:
            if not sub_order.is_completed():
                return False
                
        return True

    def has_active_sub_orders(self) -> bool:
        """Check if any sub-orders are still in progress or pending."""
        for sub_order in self.sub_orders:
            if sub_order.status in [OrderStatus.IN_PROGRESS, OrderStatus.PENDING] or sub_order.has_active_sub_orders():
                return True
        return False

    def update(self, galaxy_ref: 'Galaxy') -> None:
        """Update the order status based on sub-orders status and own completion."""
        # Process the front sub-order in the queue sequentially. We block and wait
        # until the current sub-order is fully resolved (completed, failed, or cancelled).
        while self.sub_orders:
            current_sub_order = self.sub_orders[0]

            if current_sub_order.status == OrderStatus.PENDING:
                current_sub_order.execute(galaxy_ref=galaxy_ref)

            if current_sub_order.status == OrderStatus.IN_PROGRESS:
                current_sub_order.update(galaxy_ref=galaxy_ref)

            if current_sub_order.status == OrderStatus.FAILED:
                self.status = OrderStatus.FAILED
                for sub in list(self.sub_orders):
                    sub.cancel()
                self.sub_orders.clear()
                return

            elif current_sub_order.status == OrderStatus.CANCELLED:
                self.status = OrderStatus.CANCELLED
                for sub in list(self.sub_orders):
                    sub.cancel()
                self.sub_orders.clear()
                return

            elif current_sub_order.status == OrderStatus.COMPLETED:
                self.sub_orders.popleft()
            else:
                return

        # Once all sub-orders are cleared, verify if the parent order itself is complete.
        if self.status == OrderStatus.IN_PROGRESS:
            self.check_completion_conditions()

    def cancel(self) -> None:
        """Cancel this order and all its sub-orders."""
        self.status = OrderStatus.CANCELLED
        for sub_order in self.sub_orders:
            sub_order.cancel()
    
    def check_completion_conditions(self) -> None:
        """Check order-specific completion conditions and update status."""
        pass
        
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(type={self.order_type.name}, status={self.status.name}, id={str(self.order_id)[:8]})"

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        """Execute this order."""
        if self.status != OrderStatus.PENDING:
            return
        self.status = OrderStatus.IN_PROGRESS
        logger.debug(f"[{self.unit.name} (id:{self.unit.id})] {self.__class__.__name__}.execute: {self.order_type.name} (id:{self.order_id}): Executing order.")

    def find_wormhole_to_system(self, current_system_name: str, target_system_name: str, galaxy_ref: 'Galaxy', ship_size: Optional[HullSize] = None) -> Optional['Wormhole']:
        if not galaxy_ref: return None
        for wh_id, wormhole_obj in galaxy_ref.wormholes.items():
            if wormhole_obj.in_system == current_system_name and \
               wormhole_obj.exit_system_name == target_system_name:
                if ship_size and ship_size.value > wormhole_obj.diameter.value:
                    continue
                return wormhole_obj
        return None
