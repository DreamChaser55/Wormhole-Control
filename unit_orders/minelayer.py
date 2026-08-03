import logging
from typing import Dict, Any, TYPE_CHECKING
from .base import Order, OrderStatus, OrderType
from unit_components import MinelayerComponent, MinefieldType

if TYPE_CHECKING:
    from entities import Unit
    from galaxy import Galaxy

logger = logging.getLogger(__name__)

class LayMinefieldOrder(Order):
    """An order instructing a unit with a MinelayerComponent to deploy a minefield."""
    def __init__(self, unit: 'Unit', minefield_type: Any = MinefieldType.ANTI_SHIP, parameters: Dict[str, Any] = None, parent_order: Order = None):
        params = dict(parameters) if parameters else {}
        if 'minefield_type' not in params:
            mtype_val = minefield_type.value if isinstance(minefield_type, MinefieldType) else minefield_type
            params['minefield_type'] = mtype_val
        super().__init__(unit, OrderType.LAY_MINEFIELD, params, parent_order)

    @property
    def minefield_type(self) -> MinefieldType:
        mtype_str = self.parameters.get('minefield_type', MinefieldType.ANTI_SHIP.value)
        try:
            return MinefieldType(mtype_str)
        except ValueError:
            return MinefieldType.ANTI_SHIP

    def execute(self, galaxy_ref: 'Galaxy' = None, galaxy: 'Galaxy' = None) -> OrderStatus:
        target_galaxy = galaxy_ref if galaxy_ref is not None else galaxy
        if self.status in (OrderStatus.COMPLETED, OrderStatus.FAILED, OrderStatus.CANCELLED):
            return self.status

        self.status = OrderStatus.IN_PROGRESS

        minelayer = self.unit.get_component(MinelayerComponent)
        if not minelayer or minelayer.is_destroyed:
            logger.debug(f"{self.unit.name} cannot lay minefield: Minelayer component missing or destroyed.")
            self.status = OrderStatus.FAILED
            return self.status

        system_name = self.unit.in_system
        hex_coord = self.unit.in_hex
        position = self.unit.position

        minefield = minelayer.deploy_mine(target_galaxy, system_name, hex_coord, position, minefield_type=self.minefield_type)

        if minefield:
            logger.debug(f"{self.unit.name} successfully executed LayMinefieldOrder.")
            self.status = OrderStatus.COMPLETED
        else:
            logger.debug(f"{self.unit.name} failed to deploy minefield.")
            self.status = OrderStatus.FAILED

        return self.status
