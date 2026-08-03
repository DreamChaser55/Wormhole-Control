import logging
from typing import Optional, Tuple, TYPE_CHECKING
import dataclasses

from .base import UnitComponent
from .enums import MinefieldType
from constants import MINEFIELD_CREDIT_COST, MINEFIELD_ANTIMATTER_COST, MINELAYER_HULL_COST, MAX_MINEFIELDS_PER_HEX

if TYPE_CHECKING:
    from entities import Unit, Minefield
    from galaxy import Galaxy
    from game import Game
    from utils import HexCoord
    from geometry import Position

logger = logging.getLogger(__name__)

class MinelayerComponent(UnitComponent):
    """A component that allows a unit to deploy minefields into system hexes."""
    DISPLAY_NAME: str = "Minelayer"
    SIDEBAR_ORDER: int = 14

    def __init__(self, unit: 'Unit', credit_cost: float = MINEFIELD_CREDIT_COST, antimatter_cost: float = MINEFIELD_ANTIMATTER_COST, hull_cost: float = MINELAYER_HULL_COST):
        super().__init__(unit, hull_cost=hull_cost)
        self.credit_cost = credit_cost
        self.antimatter_cost = antimatter_cost

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        data.append({
            'type': 'label',
            'text': f"Cost: {int(self.credit_cost)} Credits, {int(self.antimatter_cost)} AM",
            'object_id': '#sidebar_info_label',
            'height': 20
        })
        data.append({
            'type': 'button',
            'text': "Lay Anti-Ship Minefield",
            'object_id': '#sidebar_expand_button',
            'action_id': 'lay_minefield_anti_ship',
            'target_data': self.unit.id,
            'height': 25
        })
        data.append({
            'type': 'button',
            'text': "Lay Anti-Strikecraft Minefield",
            'object_id': '#sidebar_expand_button',
            'action_id': 'lay_minefield_anti_strikecraft',
            'target_data': self.unit.id,
            'height': 25
        })
        return data

    def get_basic_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_basic_sidebar_data(game_state)
        if self.is_destroyed:
            return data
        data.append({
            'type': 'label',
            'text': f"• Minelayer: Active ({int(self.credit_cost)} cr / {int(self.antimatter_cost)} AM)",
            'object_id': '#sidebar_status_active_label',
            'height': 18,
            'indent_level': 1
        })
        return data

    def can_lay_mine(self, galaxy: 'Galaxy', system_name: str, hex_coord: 'HexCoord') -> Tuple[bool, str]:
        if self.is_destroyed:
            return False, "Minelayer component is destroyed."

        if not self.unit.owner:
            return False, "Unit has no owner."

        if self.unit.owner.credits < self.credit_cost:
            return False, f"Insufficient credits ({self.unit.owner.credits:.0f}/{self.credit_cost:.0f})."

        am_comp = self.unit.antimatter_component
        if not am_comp or am_comp.current_amount < self.antimatter_cost:
            current_am = am_comp.current_amount if am_comp else 0.0
            return False, f"Insufficient antimatter ({current_am:.1f}/{self.antimatter_cost:.1f})."

        system = galaxy.systems.get(system_name)
        if not system:
            return False, f"System '{system_name}' not found."

        hex_obj = system.hexes.get(hex_coord)
        if not hex_obj:
            return False, f"Hex {hex_coord} not found."

        if len(hex_obj.minefields) >= MAX_MINEFIELDS_PER_HEX:
            return False, f"Sector minefield limit reached ({len(hex_obj.minefields)}/{MAX_MINEFIELDS_PER_HEX})."

        return True, "Ready to lay minefield."

    def deploy_mine(self, galaxy: 'Galaxy', system_name: str, hex_coord: 'HexCoord', position: 'Position', minefield_type: typing.Union[MinefieldType, str] = MinefieldType.ANTI_SHIP) -> Optional['Minefield']:
        can_lay, reason = self.can_lay_mine(galaxy, system_name, hex_coord)
        if not can_lay:
            logger.debug(f"Cannot lay minefield: {reason}")
            return None

        from entities import Minefield  # avoid circular import
        system = galaxy.systems[system_name]
        hex_obj = system.hexes[hex_coord]

        # Deduct resources
        self.unit.owner.credits -= self.credit_cost
        if self.unit.antimatter_component:
            self.unit.antimatter_component.consume(self.antimatter_cost)

        # Create minefield
        minefield = Minefield(
            owner=self.unit.owner,
            position=position,
            in_hex=hex_coord,
            in_system=system_name,
            minefield_type=minefield_type
        )
        hex_obj.add_minefield(minefield)
        logger.debug(f"{self.unit.name} deployed {minefield.name} in {system_name}:{hex_coord} at pos {position}")
        return minefield
