import logging
from typing import TYPE_CHECKING
from .base import UnitComponent

if TYPE_CHECKING:
    from entities import Unit

logger = logging.getLogger(__name__)

MARINES_HULL_COST_PER_MARINE: float = 1.0


class MarinesComponent(UnitComponent):
    """
    Component representing onboard marine infantry.
    The number of marines determines component hull cost and probability of Capture Unit success.
    """
    DISPLAY_NAME: str = "Marines"

    def __init__(self, unit: 'Unit', marines_count: int = 10, hull_cost: float = 0.0):
        super().__init__(unit, hull_cost=hull_cost)
        self.marines_count: int = max(0, int(marines_count))

    @staticmethod
    def calc_hull_cost(marines_count: int) -> float:
        """Compute the hull cost of a Marines component from marines_count."""
        if marines_count <= 0:
            return 0.0
        return float(marines_count * MARINES_HULL_COST_PER_MARINE)

    def to_dict(self) -> dict:
        return {
            "marines_count": self.marines_count,
            "hull_cost": self.hull_cost,
        }
