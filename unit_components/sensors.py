from typing import TYPE_CHECKING
from .base import UnitComponent
from constants import DEFAULT_SENSOR_SHORT_RANGE

if TYPE_CHECKING:
    from entities import Unit
    from game import Game

class Sensors(UnitComponent):
    """Component providing short-range tactical sensing and optional long-range presence sensing."""
    DISPLAY_NAME: str = "Sensors"
    SIDEBAR_ORDER: int = 6

    def __init__(self, unit: 'Unit', short_range_radius: float = DEFAULT_SENSOR_SHORT_RANGE, long_range_hexes: int = 0, hull_cost: int = 0):
        super().__init__(unit, hull_cost)
        self.short_range_radius: float = short_range_radius
        self.long_range_hexes: int = long_range_hexes

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
