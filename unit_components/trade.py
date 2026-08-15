import logging
from typing import TYPE_CHECKING, List, Dict, Optional, Tuple, Any

from .base import UnitComponent
from constants import (
    TRADE_BASE_HULL_COST, TRADE_BASE_INCOME, TRADE_INCOME_PER_DISTANCE_UNIT,
    TRADE_INTERSYSTEM_HOP_DISTANCE
)
from geometry import hex_distance
from utils import HexCoord

if TYPE_CHECKING:
    from entities import Unit
    from galaxy import Galaxy
    from game import Game

logger = logging.getLogger(__name__)


class TradeComponent(UnitComponent):
    """A component that allows a ship to operate as a trade vessel, earning credits
    by traveling between active civilian habitats located in different sectors.
    Income scales with distance between sectors.
    """
    DISPLAY_NAME: str = "Trade Module"
    SIDEBAR_ORDER: int = 11

    def __init__(
        self,
        unit: 'Unit',
        hull_cost: float = TRADE_BASE_HULL_COST,
        trade_revenue_multiplier: float = 1.0
    ):
        super().__init__(unit, hull_cost=hull_cost)
        self.trade_revenue_multiplier: float = float(trade_revenue_multiplier)
        self.last_traded_sector: Optional[Tuple[str, Tuple[int, int]]] = None
        self.last_traded_unit_id: Optional[int] = None
        self.last_trade_income: float = 0.0
        self.total_trade_income: float = 0.0
        self.trades_completed: int = 0

    @staticmethod
    def calc_hull_cost(trade_revenue_multiplier: float = 1.0) -> float:
        """Calculates hull cost based on trade module revenue multiplier."""
        return float(TRADE_BASE_HULL_COST * max(1.0, trade_revenue_multiplier))

    def calculate_distance_between_sectors(
        self,
        origin_sector: Tuple[str, Tuple[int, int]],
        dest_sector: Tuple[str, Tuple[int, int]],
        galaxy: Optional['Galaxy'] = None
    ) -> float:
        """Calculates effective distance between two sectors (intra-system hex distance
        or inter-system jump hops + hex distance).
        """
        origin_sys, origin_hex_raw = origin_sector
        dest_sys, dest_hex_raw = dest_sector

        origin_hex = HexCoord(origin_hex_raw[0], origin_hex_raw[1])
        dest_hex = HexCoord(dest_hex_raw[0], dest_hex_raw[1])

        if origin_sys == dest_sys:
            return float(hex_distance(origin_hex, dest_hex))

        g = galaxy or (getattr(self.unit, 'in_galaxy', None) if self.unit else None)
        if not g and self.unit and getattr(self.unit, 'game', None):
            g = getattr(self.unit.game, 'galaxy', None)

        hops = 1
        if g and hasattr(g, 'system_graph'):
            from pathfinding import find_intersystem_path
            hull_size = getattr(self.unit, 'hull_size', None)
            path = find_intersystem_path(g.system_graph, origin_sys, dest_sys, hull_size)
            if path and len(path) > 1:
                hops = len(path) - 1

        return float(hops * TRADE_INTERSYSTEM_HOP_DISTANCE + hex_distance(origin_hex, dest_hex))

    def calculate_trade_income(
        self,
        origin_sector: Tuple[str, Tuple[int, int]],
        dest_sector: Tuple[str, Tuple[int, int]],
        galaxy: Optional['Galaxy'] = None
    ) -> float:
        """Calculates credit payout for completing a trade leg between origin and destination sectors."""
        if origin_sector == dest_sector:
            return 0.0

        dist = self.calculate_distance_between_sectors(origin_sector, dest_sector, galaxy)
        if dist <= 0:
            return 0.0

        income = (TRADE_BASE_INCOME + dist * TRADE_INCOME_PER_DISTANCE_UNIT) * self.trade_revenue_multiplier
        return float(round(income, 2))

    def execute_trade(
        self,
        habitat_unit: 'Unit',
        galaxy: Optional['Galaxy'] = None
    ) -> Tuple[bool, float, str]:
        """Executes a trade transaction at an active civilian habitat unit."""
        if self.is_destroyed:
            return False, 0.0, "Trade Module is destroyed."

        if not habitat_unit:
            return False, 0.0, "Invalid civilian habitat target."

        hab_comp = getattr(habitat_unit, 'civilian_habitat_component', None)
        if not hab_comp or hab_comp.is_destroyed:
            return False, 0.0, f"Target {habitat_unit.name} has no functioning Civilian Habitat component."

        g = galaxy or (getattr(self.unit, 'in_galaxy', None) if self.unit else None)
        if not g and self.unit and getattr(self.unit, 'game', None):
            g = getattr(self.unit.game, 'galaxy', None)

        if not hab_comp.is_active(g):
            return False, 0.0, f"Civilian Habitat on {habitat_unit.name} is currently inactive (exceeds colony capacity or not stationed at colonized world)."

        dest_sector = (habitat_unit.in_system, (habitat_unit.in_hex[0], habitat_unit.in_hex[1]))

        if self.last_traded_sector is None:
            self.last_traded_sector = dest_sector
            self.last_traded_unit_id = habitat_unit.id
            return True, 0.0, f"Trade route established at {habitat_unit.name} ({dest_sector[0]} {dest_sector[1]}). Next destination in another sector will earn credits."

        if self.last_traded_sector == dest_sector:
            return False, 0.0, f"Already traded in sector ({dest_sector[0]} {dest_sector[1]}). Must travel to an active Civilian Habitat in a different sector."

        income = self.calculate_trade_income(self.last_traded_sector, dest_sector, g)
        if income > 0:
            if self.unit and self.unit.owner:
                self.unit.owner.credits += income
            self.total_trade_income += income
            self.trades_completed += 1
            self.last_trade_income = income

            origin_str = f"{self.last_traded_sector[0]} {self.last_traded_sector[1]}"
            dest_str = f"{dest_sector[0]} {dest_sector[1]}"
            self.last_traded_sector = dest_sector
            self.last_traded_unit_id = habitat_unit.id
            logger.info(f"Unit {self.unit.name} completed trade route {origin_str} -> {dest_str}, earning {income:.2f} credits.")
            return True, income, f"Trade completed! Route from {origin_str} to {dest_str} earned +{int(income)} Credits."

        return False, 0.0, "Trade yielded 0 distance."

    def get_sidebar_data(self, game_state: 'Game') -> List[Dict]:
        data = super().get_sidebar_data(game_state)
        if self.is_destroyed:
            return data

        if self.last_traded_sector:
            port_text = f"Last Port: {self.last_traded_sector[0]} {self.last_traded_sector[1]}"
        else:
            port_text = "Last Port: None (Awaiting initial habitat)"

        data.append({
            'type': 'label',
            'text': port_text,
            'object_id': '#sidebar_info_label',
            'height': 20
        })

        data.append({
            'type': 'label',
            'text': f"Last Payout: +{int(self.last_trade_income)} credits  |  Total Revenue: {int(self.total_trade_income)}c ({self.trades_completed} trades)",
            'object_id': '#sidebar_info_label',
            'height': 20
        })
        return data

    def get_basic_sidebar_data(self, game_state: 'Game') -> List[Dict]:
        data = super().get_basic_sidebar_data(game_state)
        if self.is_destroyed:
            return data

        if self.trades_completed > 0:
            text = f"• Trade Module: Active (+{int(self.total_trade_income)}c earned, {self.trades_completed} trades)"
            obj_id = '#sidebar_value_label'
        else:
            text = "• Trade Module: Ready"
            obj_id = '#sidebar_info_label'

        data.append({
            'type': 'label',
            'text': text,
            'object_id': obj_id,
            'height': 18,
            'indent_level': 1
        })
        return data
