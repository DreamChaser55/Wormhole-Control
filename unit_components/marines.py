import logging
from typing import TYPE_CHECKING
from .base import UnitComponent

if TYPE_CHECKING:
    from entities import Unit

logger = logging.getLogger(__name__)


class MarinesComponent(UnitComponent):
    """
    Component representing onboard marine infantry.
    The number of marines determines component hull cost and probability of Capture Unit success.
    """
    DISPLAY_NAME: str = "Marines"

    def __init__(self, unit: 'Unit', marines_count: int = 10, hull_cost: float = 0.0):
        super().__init__(unit, hull_cost=hull_cost)
        self.marines_count: int = max(0, int(marines_count))

    def to_dict(self) -> dict:
        return {
            "marines_count": self.marines_count,
            "hull_cost": self.hull_cost,
        }
