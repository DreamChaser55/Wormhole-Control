import math
import random
from typing import Optional, TYPE_CHECKING
import dataclasses

from .base import UnitComponent
from .enums import TurretType
from constants import XP_DEFENSE_BONUS

if TYPE_CHECKING:
    from domain.units import Unit
    from game import Game

DEFENSE_PER_HULL_POINT: float = 3.0

@dataclasses.dataclass
class Defenses(UnitComponent):
    """
    Provides protection against incoming attacks.
    - Armor reduces mass driver damage.
    - Shields reduce beam damage.
    - Point defense cannons reduce missile damage.
    """
    STATE_CONFIG = ('armor', 'shields', 'point_defense')
    STATE_RUNTIME = ()
    STATE_REFS = ()
    STATE_REAL_FIELDS = ("armor", "shields", "point_defense")
    DISPLAY_NAME: str = "Defenses"
    SIDEBAR_ORDER: int = 4
    armor: float = 0.0
    shields: float = 0.0
    point_defense: float = 0.0

    def __init__(self, unit: 'Unit', armor: float = 0.0, shields: float = 0.0, point_defense: float = 0.0, hull_cost: float = 0.0):
        super().__init__(unit, hull_cost=hull_cost)
        self.armor = float(armor)
        self.shields = float(shields)
        self.point_defense = float(point_defense)

    def on_destroyed(self) -> None:
        from tactical_abilities import cancel
        cancel(self.unit, "guardian_link")

    @staticmethod
    def calc_hull_cost(armor: float, shields: float, point_defense: float) -> float:
        """Compute the hull cost of a Defenses component from its stats."""
        total = armor + shields + point_defense
        if total <= 0:
            return 0.0
        return total / DEFENSE_PER_HULL_POINT

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        xp = self.unit.experience_points
        galaxy_ref = getattr(game_state, 'galaxy', None) if game_state else None
        _, od_def_bonus = self.unit.get_orbital_defense_buffs(galaxy_ref) if hasattr(self.unit, 'get_orbital_defense_buffs') else (0.0, 0.0)
        
        bonus_tags = []
        if xp > 0:
            mult = self.unit.xp_multiplier(XP_DEFENSE_BONUS)
            bonus_tags.append(f"+{int((mult - 1.0) * 100)}% XP")
        if od_def_bonus > 0:
            bonus_tags.append(f"+{int(od_def_bonus * 100)}% OD")
        
        if bonus_tags:
            tag_str = f" ({', '.join(bonus_tags)})"
            def fmt(val: float) -> str:
                return f"{val:g}{tag_str}"
        else:
            def fmt(val: float) -> str:
                return f"{val:g}"
        data.append({'type': 'label', 'text': f"Armor: {fmt(self.armor)}", 'object_id': '#sidebar_info_label', 'height': 20})
        data.append({'type': 'label', 'text': f"Shields: {fmt(self.shields)}", 'object_id': '#sidebar_info_label', 'height': 20})
        data.append({'type': 'label', 'text': f"Point Defense: {fmt(self.point_defense)}", 'object_id': '#sidebar_info_label', 'height': 20})
        return data

    def get_basic_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_basic_sidebar_data(game_state)
        if self.is_destroyed:
            return data
        data.append({
            'type': 'label',
            'text': f"• Armor {self.armor:g} | Shields {self.shields:g} | PD {self.point_defense:g}",
            'object_id': '#sidebar_value_label',
            'height': 18,
            'indent_level': 1
        })
        return data


    def calculate_mitigation(self, incoming_damage: int, damage_type: Optional[TurretType]) -> int:
        if self.is_destroyed or damage_type is None:
            return 0

        def _roll(val: float) -> float:
            if val <= 0.0:
                return 0.0
            return random.uniform(0.0, val)

        mitigation = 0.0
        if damage_type == TurretType.MASS_DRIVER:
            mitigation += _roll(self.armor)
            mitigation += _roll(math.sqrt(max(0.0, self.shields)))
            mitigation += _roll(math.sqrt(max(0.0, self.point_defense)))
        elif damage_type == TurretType.BEAM:
            mitigation += _roll(self.shields)
            mitigation += _roll(math.sqrt(max(0.0, self.armor)))
            mitigation += _roll(math.sqrt(max(0.0, self.point_defense)))
        elif damage_type == TurretType.MISSILE:
            mitigation += _roll(self.point_defense)
            mitigation += _roll(math.sqrt(max(0.0, self.armor)))
            mitigation += _roll(math.sqrt(max(0.0, self.shields)))

        # Apply XP defense bonus: veteran units are more effective at blocking damage
        mitigation = mitigation * self.unit.xp_multiplier(XP_DEFENSE_BONUS)

        # Apply Orbital Defense defense bonus: units in active friendly orbital defense fields mitigate more damage
        if hasattr(self.unit, 'get_orbital_defense_buffs'):
            _, od_def_bonus = self.unit.get_orbital_defense_buffs()
            if od_def_bonus > 0.0:
                mitigation = mitigation * (1.0 + od_def_bonus)

        return min(incoming_damage, int(round(mitigation)))
