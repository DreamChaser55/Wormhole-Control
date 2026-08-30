from .base import OrderStatus, OrderType, Order
from .movement import ReachWaypointOrder, MoveOrder, calculate_required_antimatter
from .patrol import PatrolOrder
from .combat import AttackOrder, ProtectOrder
from .stance import StanceOrder
from .defend import DefendOrder
from .inhibitor import ToggleInhibitorOrder
from .colony import ColonizeOrder, LoadColonistsOrder
from .construction import ConstructOrder
from .repair import RepairOrder
from .antimatter import TransferAntimatterOrder, ContinuousResupplyOrder
from .mining import MineOrder, UnloadResourcesOrder, ContinuousMineOrder
from .hangar import DockOrder, DeployUnitOrder, DeployAllWingsOrder
from .abilities import UseAbilityOrder
from .minelayer import LayMinefieldOrder
from .refit import RefitOrder
from .trade import TradeOrder, ContinuousTradeOrder
from .intelligence import (
    InfiltrateUnitOrder,
    InfiltratePlanetOrder,
    RelocateAgentOrder,
    SabotageOrder,
    CISweepOrder,
    EliminateAgentOrder,
    ExtractAgentOrder,
)

# The single authoritative mapping used by persistence and coverage tests.
ORDER_CLASS_REGISTRY = {
    OrderType.REACH_WAYPOINT: ReachWaypointOrder,
    OrderType.MOVE: MoveOrder,
    OrderType.PATROL: PatrolOrder,
    OrderType.ATTACK: AttackOrder,
    OrderType.DEFEND: DefendOrder,
    OrderType.PROTECT: ProtectOrder,
    OrderType.TOGGLE_INHIBITOR: ToggleInhibitorOrder,
    OrderType.COLONIZE: ColonizeOrder,
    OrderType.LOAD_COLONISTS: LoadColonistsOrder,
    OrderType.CONSTRUCT: ConstructOrder,
    OrderType.REPAIR: RepairOrder,
    OrderType.MINE: MineOrder,
    OrderType.UNLOAD_RESOURCES: UnloadResourcesOrder,
    OrderType.DOCK: DockOrder,
    OrderType.DEPLOY_UNIT: DeployUnitOrder,
    OrderType.DEPLOY_ALL_WINGS: DeployAllWingsOrder,
    OrderType.USE_ABILITY: UseAbilityOrder,
    OrderType.CONTINUOUS_MINE: ContinuousMineOrder,
    OrderType.TRANSFER_ANTIMATTER: TransferAntimatterOrder,
    OrderType.CONTINUOUS_RESUPPLY: ContinuousResupplyOrder,
    OrderType.LAY_MINEFIELD: LayMinefieldOrder,
    OrderType.REFIT_UNIT: RefitOrder,
    OrderType.TRADE: TradeOrder,
    OrderType.CONTINUOUS_TRADE: ContinuousTradeOrder,
    OrderType.INFILTRATE_UNIT: InfiltrateUnitOrder,
    OrderType.INFILTRATE_PLANET: InfiltratePlanetOrder,
    OrderType.RELOCATE_AGENT: RelocateAgentOrder,
    OrderType.SABOTAGE: SabotageOrder,
    OrderType.CI_SWEEP: CISweepOrder,
    OrderType.ELIMINATE_AGENT: EliminateAgentOrder,
    OrderType.EXTRACT_AGENT: ExtractAgentOrder,
    OrderType.STANCE: StanceOrder,
}

__all__ = [
    "OrderStatus",
    "OrderType",
    "Order",
    "ReachWaypointOrder",
    "MoveOrder",
    "calculate_required_antimatter",
    "PatrolOrder",
    "AttackOrder",
    "ProtectOrder",
    "StanceOrder",
    "DefendOrder",
    "ToggleInhibitorOrder",
    "ColonizeOrder",
    "LoadColonistsOrder",
    "ConstructOrder",
    "RepairOrder",
    "RefitOrder",
    "TransferAntimatterOrder",
    "ContinuousResupplyOrder",
    "MineOrder",
    "UnloadResourcesOrder",
    "ContinuousMineOrder",
    "DockOrder",
    "DeployUnitOrder",
    "DeployAllWingsOrder",
    "UseAbilityOrder",
    "LayMinefieldOrder",
    "TradeOrder",
    "ContinuousTradeOrder",
    "InfiltrateUnitOrder",
    "InfiltratePlanetOrder",
    "RelocateAgentOrder",
    "SabotageOrder",
    "CISweepOrder",
    "EliminateAgentOrder",
    "ExtractAgentOrder",
    "ORDER_CLASS_REGISTRY",
]
