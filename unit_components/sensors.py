from typing import TYPE_CHECKING
from .base import UnitComponent
from constants import (
    DEFAULT_SENSOR_SHORT_RANGE,
    SENSOR_RANGE_PER_HULL_POINT,
    SENSOR_LONG_RANGE_HULL_COST_PER_HEX
)

if TYPE_CHECKING:
    from entities import Unit
    from game import Game

class Sensors(UnitComponent):
    """Component providing short-range tactical sensing and optional long-range presence sensing."""
    DISPLAY_NAME: str = "Sensors"
    SIDEBAR_ORDER: int = 6

    def __init__(self, unit: 'Unit', short_range_radius: float = DEFAULT_SENSOR_SHORT_RANGE, long_range_hexes: int = 0, hull_cost: float = 0.0):
        super().__init__(unit, hull_cost)
        self.short_range_radius: float = short_range_radius
        self.long_range_hexes: int = long_range_hexes

    @staticmethod
    def calc_hull_cost(short_range_radius: float, long_range_hexes: int) -> float:
        """Compute the hull cost of a Sensors component upgrade."""
        base = (short_range_radius / SENSOR_RANGE_PER_HULL_POINT) if short_range_radius > 0 else 0.0
        return base + max(0, long_range_hexes) * SENSOR_LONG_RANGE_HULL_COST_PER_HEX

    @property
    def has_short_range(self) -> bool:
        return self.short_range_radius > 0

    @property
    def has_long_range(self) -> bool:
        return self.long_range_hexes > 0

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        sr_text = f"Short Range: {int(self.short_range_radius)}" if self.has_short_range else "Short Range: None"
        lr_text = f"Long Range: {self.long_range_hexes} hex(es)" if self.has_long_range else "Long Range: None"
        data.append({'type': 'label', 'text': sr_text, 'object_id': '#sidebar_info_label', 'height': 20})
        data.append({'type': 'label', 'text': lr_text, 'object_id': '#sidebar_info_label', 'height': 20})
        return data

    def get_basic_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_basic_sidebar_data(game_state)
        if self.is_destroyed:
            return data
        sr = int(self.short_range_radius) if self.has_short_range else 0
        lr = self.long_range_hexes if self.has_long_range else 0
        data.append({
            'type': 'label',
            'text': f"• Sensor Range: Short {sr} | Long {lr} hexes",
            'object_id': '#sidebar_value_label',
            'height': 18,
            'indent_level': 1
        })
        return data

