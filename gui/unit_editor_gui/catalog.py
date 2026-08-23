"""
catalog.py

Component definitions, catalogue constants, option lists, and component descriptions
for the Unit Designer GUI.
"""

import typing
from constants import HullSize
from unit_components import AbilityType, TurretType, TurretVariant

# ---------------------------------------------------------------------------
# Component catalogue — defines order and labels.
# Dynamic components (Engines, Hyperdrive, Weapons, Defenses) have
# is_dynamic=True; their hull cost is computed at runtime.
# Fixed components carry a default_cost that is editable.
# ---------------------------------------------------------------------------

COMPONENT_ROWS: typing.List[typing.Dict] = [
    {"key": "has_engine",                "label": "Engines",            "cost_key": "engine_hull_cost",           "default_cost": 5.0,  "is_dynamic": True},
    {"key": "has_antimatter_storage",    "label": "Antimatter Storage", "cost_key": "antimatter_hull_cost",       "default_cost": 5.0,  "is_dynamic": True},
    {"key": "has_antimatter_harvester",  "label": "Antimatter Harvester", "cost_key": "antimatter_harvester_hull_cost", "default_cost": 15.0, "is_dynamic": False},
    {"key": "has_hyperdrive",            "label": "Hyperdrive",         "cost_key": "hyperdrive_hull_cost",       "default_cost": 5.0,  "is_dynamic": True},
    {"key": "has_weapon_bays",           "label": "Weapons",            "cost_key": "weapon_bays_hull_cost",      "default_cost": 10.0, "is_dynamic": True},
    {"key": "has_defenses",              "label": "Defenses",           "cost_key": "defenses_hull_cost",         "default_cost": 10.0, "is_dynamic": True},
    {"key": "has_constructor_component", "label": "Constructor",        "cost_key": "constructor_hull_cost",      "default_cost": 15.0, "is_dynamic": False},
    {"key": "has_repair_component",      "label": "Repair",             "cost_key": "repair_hull_cost",           "default_cost": 15.0, "is_dynamic": True},
    {"key": "has_colony_component",      "label": "Colony",             "cost_key": "colony_hull_cost",           "default_cost": 10.0, "is_dynamic": False},
    {"key": "has_civilian_habitat_component", "label": "Civilian Habitat", "cost_key": "civilian_habitat_hull_cost", "default_cost": 15.0, "is_dynamic": False},
    {"key": "has_orbital_defense_component", "label": "Orbital Defense", "cost_key": "orbital_defense_hull_cost", "default_cost": 20.0, "is_dynamic": False},
    {"key": "has_trade_component",            "label": "Trade Module",     "cost_key": "trade_hull_cost",            "default_cost": 10.0, "is_dynamic": False},
    {"key": "has_mining_component",      "label": "Mining",             "cost_key": "mining_hull_cost",           "default_cost": 10.0, "is_dynamic": True},
    {"key": "has_metal_refinery_component", "label": "Metal Refinery",  "cost_key": "metal_refinery_hull_cost",   "default_cost": 20.0, "is_dynamic": False},
    {"key": "has_crystal_refinery_component", "label": "Crystal Refinery", "cost_key": "crystal_refinery_hull_cost", "default_cost": 20.0, "is_dynamic": False},
    {"key": "has_hangar",                "label": "Hangar",             "cost_key": "hangar_hull_cost",           "default_cost": 20.0, "is_dynamic": True},
    {"key": "has_strikecraft_bay",       "label": "Strikecraft Bay",    "cost_key": "strikecraft_bay_hull_cost",  "default_cost": 15.0, "is_dynamic": True},
    {"key": "has_inhibitor",             "label": "Inhibitor Field",    "cost_key": "inhibitor_hull_cost",        "default_cost": 20.0, "is_dynamic": True},
    {"key": "has_ability_component",     "label": "Abilities",          "cost_key": "ability_hull_cost",          "default_cost": 10.0, "is_dynamic": True},
    {"key": "has_sensors",               "label": "Sensors",            "cost_key": "sensors_hull_cost",          "default_cost": 2.0,  "is_dynamic": True},
    {"key": "has_minelayer_component",   "label": "Minelayer",          "cost_key": "minelayer_hull_cost",        "default_cost": 15.0, "is_dynamic": False},
    {"key": "has_marines_component",     "label": "Marines",            "cost_key": "marines_hull_cost",          "default_cost": 10.0, "is_dynamic": True},
    {"key": "has_cloaking_device",       "label": "Cloaking Device",    "cost_key": "cloaking_device_hull_cost",  "default_cost": 10.0, "is_dynamic": True},
    {"key": "has_intelligence_component", "label": "Intelligence",       "cost_key": "intelligence_hull_cost",     "default_cost": 10.0, "is_dynamic": True},
]

HULL_SIZE_NAMES = [hs.name for hs in HullSize]
TURRET_TYPES = [t.name for t in TurretType]
TURRET_VARIANTS = [v.name for v in TurretVariant]
ABILITY_NAMES = [a.value for a in AbilityType]
HYPERDRIVE_TYPES = ["BASIC", "ADVANCED"]
CLOAKING_TYPES = ["BASIC", "ADVANCED"]
WING_TYPES = ["FIGHTER", "BOMBER"]

COMPONENT_DESCRIPTIONS = {
    "has_antimatter_harvester": "Antimatter Harvester<br><br>Generates antimatter resource automatically over time for hyperdrive jumps and abilities.",
    "has_constructor_component": "Constructor Component<br><br>Enables construction of orbital structures, starbases, and warp gates.",
    "has_colony_component": "Colony Component<br><br>Enables colonizing uncolonized habitable planets.",
    "has_civilian_habitat_component": "Civilian Habitat<br><br>Provides economic bonuses (+50 credits per turn) if stationed in a sector with a colonized celestial object.",
    "has_orbital_defense_component": "Orbital Defense<br><br>Projects an area-of-effect aura (500 radius) providing +20% attack damage and +20% defense mitigation to friendly ships in range.<br><br>• Only functions in sectors with a friendly colonized celestial body.<br>• Max supported modules scales with colony population (base 1, +1 per 25 population).<br>• Multiple overlapping Orbital Defense auras stack additively.",
    "has_trade_component": "Trade Module<br><br>Enables trade ships to earn credits by traveling between active Civilian Habitat modules located in different sectors. Greater distance between sectors yields higher trade income.<br><br><b>Requirement:</b> Requires an Engine component.",
    "has_metal_refinery_component": "Metal Refinery<br><br>Processes raw ore into refined metal alloys.",
    "has_crystal_refinery_component": "Crystal Refinery<br><br>Refines raw crystal into energy matrix components.",
    "has_cloaking_device": "Cloaking Device<br><br>Hides units from enemy long-range (inter-sector) sensors when activated.<br><br>• <b>Basic</b> (10 Hull, 5 AM/turn): Single-ship personal stealth.<br>• <b>Advanced</b> (30 Hull, 20 AM/turn): Area stealth field hiding friendly units within 500 radius.<br><br>Short-range sensors still detect units normally.",
    "has_inhibitor": "Inhibitor Field<br><br>Generates a hyperspace inhibition zone around the unit, preventing hyperdrive jumps into or out of the field. Consumes antimatter per turn while active scaled by field radius. Auto-deactivates if antimatter runs dry.",
    "has_intelligence_component": "Intelligence & Sabotage<br><br>Enables deploying invisible agents onto enemy units and colonized worlds in range (500 units).<br><br>• <b>Sensor Intel:</b> Reveals sensor vision of infiltrated units/colonies.<br>• <b>Sabotage:</b> Sabotages unit systems (Engines, Weapons, Defenses, Hyperdrive, Sensors, Antimatter) or planetary economic output/growth.<br>• <b>Counter-Intelligence:</b> Discovers and eliminates enemy agents lurking on friendly units and colonies within range.",
}

