"""Explicit, lazy compatibility exports. Import implementations from their defining modules."""
from importlib import import_module

_EXPORTS = {'random': ('random', None),
 'HyperdriveType': ('unit_components.enums', 'HyperdriveType'),
 'CloakingType': ('unit_components.enums', 'CloakingType'),
 'JumpStatus': ('unit_components.enums', 'JumpStatus'),
 'UnitStance': ('unit_components.enums', 'UnitStance'),
 'TurretType': ('unit_components.enums', 'TurretType'),
 'TurretVariant': ('unit_components.enums', 'TurretVariant'),
 'WingType': ('unit_components.enums', 'WingType'),
 'AbilityType': ('unit_components.enums', 'AbilityType'),
 'MinefieldType': ('unit_components.enums', 'MinefieldType'),
 'SabotageType': ('unit_components.enums', 'SabotageType'),
 'UnitComponent': ('unit_components.base', 'UnitComponent'),
 'AntimatterStorage': ('unit_components.antimatter', 'AntimatterStorage'),
 'AntimatterHarvester': ('unit_components.antimatter', 'AntimatterHarvester'),
 'Engines': ('unit_components.movement', 'Engines'),
 'Hyperdrive': ('unit_components.movement', 'Hyperdrive'),
 'Turret': ('unit_components.weapons', 'Turret'),
 'Weapons': ('unit_components.weapons', 'Weapons'),
 'Defenses': ('unit_components.defenses', 'Defenses'),
 'HyperspaceInhibitionFieldEmitter': ('unit_components.inhibitor',
                                      'HyperspaceInhibitionFieldEmitter'),
 'MinelayerComponent': ('unit_components.minelayer', 'MinelayerComponent'),
 'Commander': ('unit_components.commander', 'Commander'),
 'RepairComponent': ('unit_components.repair', 'RepairComponent'),
 'ColonyComponent': ('unit_components.colony', 'ColonyComponent'),
 'MiningComponent': ('unit_components.mining', 'MiningComponent'),
 'MetalRefineryComponent': ('unit_components.mining', 'MetalRefineryComponent'),
 'CrystalRefineryComponent': ('unit_components.mining', 'CrystalRefineryComponent'),
 'HangarComponent': ('unit_components.hangar', 'HangarComponent'),
 'StrikecraftWingComponent': ('unit_components.strikecraft', 'StrikecraftWingComponent'),
 'StrikecraftBayComponent': ('unit_components.strikecraft', 'StrikecraftBayComponent'),
 'AbilityDefinition': ('unit_components.abilities', 'AbilityDefinition'),
 'ABILITY_DEFINITIONS': ('unit_components.abilities', 'ABILITY_DEFINITIONS'),
 'AbilityInstance': ('unit_components.abilities', 'AbilityInstance'),
 'AbilityComponent': ('unit_components.abilities', 'AbilityComponent'),
 'BuildableUnit': ('unit_components.constructor', 'BuildableUnit'),
 'Constructor': ('unit_components.constructor', 'Constructor'),
 'UNIT_TEMPLATES': ('unit_components.constructor', 'UNIT_TEMPLATES'),
 'instantiate_unit_from_template': ('unit_components.constructor',
                                    'instantiate_unit_from_template'),
 'instantiate_component_for_unit': ('unit_components.constructor',
                                    'instantiate_component_for_unit'),
 'get_component_class_by_name': ('unit_components.constructor', 'get_component_class_by_name'),
 'COMPONENT_NAME_MAP': ('unit_components.constructor', 'COMPONENT_NAME_MAP'),
 'Sensors': ('unit_components.sensors', 'Sensors'),
 'CloakingDevice': ('unit_components.cloaking', 'CloakingDevice'),
 'MarinesComponent': ('unit_components.marines', 'MarinesComponent'),
 'CivilianHabitatComponent': ('unit_components.civilian_habitat', 'CivilianHabitatComponent'),
 'OrbitalDefenseComponent': ('unit_components.orbital_defense', 'OrbitalDefenseComponent'),
 'TradeComponent': ('unit_components.trade', 'TradeComponent'),
 'IntelligenceComponent': ('unit_components.intelligence', 'IntelligenceComponent'),
 'Agent': ('unit_components.intelligence', 'Agent')}
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
