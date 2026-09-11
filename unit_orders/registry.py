"""Authoritative persistence order-class registry."""
from .abilities import UseAbilityOrder
from .strikecraft import AttackRunOrder, EmergencyRecoveryOrder
from .recover_fuel import RecoverFuelCacheOrder
from .antimatter import ContinuousResupplyOrder, TransferAntimatterOrder
from .base import Order, OrderStatus, OrderType
from .colony import ColonizeOrder, LoadColonistsOrder
from .combat import AttackOrder, ProtectOrder
from .construction import ConstructOrder
from .defend import DefendOrder
from .gas_giant import EnterGasGiantOrder, LeaveGasGiantOrder
from .hangar import DeployAllWingsOrder, DeployUnitOrder, DockOrder
from .inhibitor import ToggleInhibitorOrder
from .intelligence import (
    CISweepOrder,
    EliminateAgentOrder,
    ExtractAgentOrder,
    InfiltratePlanetOrder,
    InfiltrateUnitOrder,
    RelocateAgentOrder,
    SabotageOrder,
)
from .minelayer import LayMinefieldOrder
from .mining import ContinuousMineOrder, MineOrder, UnloadResourcesOrder
from .movement import MoveOrder, ReachWaypointOrder, calculate_required_antimatter
from .patrol import PatrolOrder
from .refit import RefitOrder
from .repair import RepairOrder
from .stance import StanceOrder
from .trade import ContinuousTradeOrder, TradeOrder

# The single authoritative mapping used by persistence and coverage tests.
ORDER_CLASS_REGISTRY = {
    OrderType.ATTACK_RUN: AttackRunOrder,
    OrderType.EMERGENCY_RECOVERY: EmergencyRecoveryOrder,
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
    OrderType.ENTER_GAS_GIANT: EnterGasGiantOrder,
    OrderType.LEAVE_GAS_GIANT: LeaveGasGiantOrder,
    OrderType.STANCE: StanceOrder,
    OrderType.RECOVER_FUEL_CACHE: RecoverFuelCacheOrder,
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
    "AttackRunOrder",
    "EmergencyRecoveryOrder",
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
    "RecoverFuelCacheOrder",
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
    "EnterGasGiantOrder",
    "LeaveGasGiantOrder",
    "ORDER_CLASS_REGISTRY",
]
