"""Explicit, lazy order exports; the persistence registry lives in registry."""
from importlib import import_module

_EXPORTS = {'OrderStatus': ('unit_orders.base', 'OrderStatus'),
 'OrderType': ('unit_orders.base', 'OrderType'),
 'Order': ('unit_orders.base', 'Order'),
 'ReachWaypointOrder': ('unit_orders.movement', 'ReachWaypointOrder'),
 'MoveOrder': ('unit_orders.movement', 'MoveOrder'),
 'calculate_required_antimatter': ('unit_orders.movement', 'calculate_required_antimatter'),
 'PatrolOrder': ('unit_orders.patrol', 'PatrolOrder'),
 'AttackOrder': ('unit_orders.combat', 'AttackOrder'),
 'ProtectOrder': ('unit_orders.combat', 'ProtectOrder'),
 'StanceOrder': ('unit_orders.stance', 'StanceOrder'),
 'DefendOrder': ('unit_orders.defend', 'DefendOrder'),
 'ToggleInhibitorOrder': ('unit_orders.inhibitor', 'ToggleInhibitorOrder'),
 'ColonizeOrder': ('unit_orders.colony', 'ColonizeOrder'),
 'LoadColonistsOrder': ('unit_orders.colony', 'LoadColonistsOrder'),
 'ConstructOrder': ('unit_orders.construction', 'ConstructOrder'),
 'RepairOrder': ('unit_orders.repair', 'RepairOrder'),
 'TransferAntimatterOrder': ('unit_orders.antimatter', 'TransferAntimatterOrder'),
 'ContinuousResupplyOrder': ('unit_orders.antimatter', 'ContinuousResupplyOrder'),
 'MineOrder': ('unit_orders.mining', 'MineOrder'),
 'UnloadResourcesOrder': ('unit_orders.mining', 'UnloadResourcesOrder'),
 'ContinuousMineOrder': ('unit_orders.mining', 'ContinuousMineOrder'),
 'DockOrder': ('unit_orders.hangar', 'DockOrder'),
 'DeployUnitOrder': ('unit_orders.hangar', 'DeployUnitOrder'),
 'DeployAllWingsOrder': ('unit_orders.hangar', 'DeployAllWingsOrder'),
 'UseAbilityOrder': ('unit_orders.abilities', 'UseAbilityOrder'),
 'LayMinefieldOrder': ('unit_orders.minelayer', 'LayMinefieldOrder'),
 'RefitOrder': ('unit_orders.refit', 'RefitOrder'),
 'TradeOrder': ('unit_orders.trade', 'TradeOrder'),
 'ContinuousTradeOrder': ('unit_orders.trade', 'ContinuousTradeOrder'),
 'InfiltrateUnitOrder': ('unit_orders.intelligence', 'InfiltrateUnitOrder'),
 'InfiltratePlanetOrder': ('unit_orders.intelligence', 'InfiltratePlanetOrder'),
 'RelocateAgentOrder': ('unit_orders.intelligence', 'RelocateAgentOrder'),
 'SabotageOrder': ('unit_orders.intelligence', 'SabotageOrder'),
 'CISweepOrder': ('unit_orders.intelligence', 'CISweepOrder'),
 'EliminateAgentOrder': ('unit_orders.intelligence', 'EliminateAgentOrder'),
 'ExtractAgentOrder': ('unit_orders.intelligence', 'ExtractAgentOrder'),
 'EnterGasGiantOrder': ('unit_orders.gas_giant', 'EnterGasGiantOrder'),
 'LeaveGasGiantOrder': ('unit_orders.gas_giant', 'LeaveGasGiantOrder'),
 'ORDER_CLASS_REGISTRY': ('unit_orders.registry', 'ORDER_CLASS_REGISTRY')}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module, attribute = _EXPORTS[name]
    value = import_module(module)
    if attribute is not None:
        value = getattr(value, attribute)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
