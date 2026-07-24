import math
import random
from typing import Optional, TYPE_CHECKING
import dataclasses

from .base import UnitComponent
from .enums import TurretType
from constants import XP_DEFENSE_BONUS

if TYPE_CHECKING:
    from entities import Unit
    from game import Game

@dataclasses.dataclass
class Defenses(UnitComponent):
    """
    Provides protection against incoming attacks.
    - Armor reduces mass driver damage.
    - Shields reduce beam damage.
    - Point defense cannons reduce missile damage.
    """
    DISPLAY_NAME: str = "Defenses"
    SIDEBAR_ORDER: int = 4
    armor: int = 0
    shields: int = 0
    point_defense: int = 0

    def __init__(self, unit: 'Unit', armor: int = 0, shields: int = 0, point_defense: int = 0, hull_cost: int = 0):
        super().__init__(unit, hull_cost=hull_cost)
        self.armor = armor
        self.shields = shields
        self.point_defense = point_defense

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        xp = self.unit.experience_points
        if xp > 0:
            mult = self.unit.xp_multiplier(XP_DEFENSE_BONUS)
            bonus_pct = int((mult - 1.0) * 100)
            def fmt(val: int) -> str:
                return f"{val} (+{bonus_pct}% XP)"
        else:
            def fmt(val: int) -> str:
                return str(val)
        data.append({'type': 'label', 'text': f"Armor: {fmt(self.armor)}", 'object_id': '#sidebar_info_label', 'height': 20})
        data.append({'type': 'label', 'text': f"Shields: {fmt(self.shields)}", 'object_id': '#sidebar_info_label', 'height': 20})
        data.append({'type': 'label', 'text': f"Point Defense: {fmt(self.point_defense)}", 'object_id': '#sidebar_info_label', 'height': 20})
        return data

    def calculate_mitigation(self, incoming_damage: int, damage_type: Optional[TurretType]) -> int:
        if self.is_destroyed or damage_type is None:
            return 0

        mitigation = 0
        if damage_type == TurretType.MASS_DRIVER:
            mitigation += random.randint(0, self.armor)
            mitigation += random.randint(0, int(math.sqrt(self.shields)))
            mitigation += random.randint(0, int(math.sqrt(self.point_defense)))
        elif damage_type == TurretType.BEAM:
            mitigation += random.randint(0, self.shields)
            mitigation += random.randint(0, int(math.sqrt(self.armor)))
            mitigation += random.randint(0, int(math.sqrt(self.point_defense)))
        elif damage_type == TurretType.MISSILE:
            mitigation += random.randint(0, self.point_defense)
            mitigation += random.randint(0, int(math.sqrt(self.armor)))
            mitigation += random.randint(0, int(math.sqrt(self.shields)))

        # Apply XP defense bonus: veteran units are more effective at blocking damage
        mitigation = int(mitigation * self.unit.xp_multiplier(XP_DEFENSE_BONUS))

        return min(incoming_damage, mitigation)
