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
    {"key": "has_cloaking_device",       "label": "Cloaking Device",    "cost_key": "cloaking_hull_cost",         "default_cost": 10.0, "is_dynamic": False},
]

HULL_SIZE_NAMES = [hs.name for hs in HullSize]
TURRET_TYPES = [t.name for t in TurretType]
TURRET_VARIANTS = [v.name for v in TurretVariant]
ABILITY_NAMES = [a.value for a in AbilityType]
HYPERDRIVE_TYPES = ["BASIC", "ADVANCED"]
WING_TYPES = ["FIGHTER", "BOMBER"]

COMPONENT_DESCRIPTIONS = {
    "has_antimatter_harvester": "Antimatter Harvester<br><br>Generates antimatter resource automatically over time for hyperdrive jumps and abilities.",
    "has_constructor_component": "Constructor Component<br><br>Enables construction of orbital structures, starbases, and warp gates.",
    "has_colony_component": "Colony Component<br><br>Enables colonizing uncolonized habitable planets.",
    "has_civilian_habitat_component": "Civilian Habitat<br><br>Provides economic bonuses (+50 credits per turn) if stationed in a sector with a colonized celestial object.",
    "has_metal_refinery_component": "Metal Refinery<br><br>Processes raw ore into refined metal alloys.",
    "has_crystal_refinery_component": "Crystal Refinery<br><br>Refines raw crystal into energy matrix components.",
    "has_cloaking_device": "Cloaking Device<br><br>Hides the unit from enemy long-range (inter-sector) sensors when activated. Short-range in-sector sensors can still detect the unit. Consumes 5.0 antimatter per turn while active. Auto-deactivates if antimatter runs dry.",
    "has_inhibitor": "Inhibitor Field<br><br>Generates a hyperspace inhibition zone around the unit, preventing hyperdrive jumps into or out of the field. Consumes antimatter per turn while active scaled by field radius. Auto-deactivates if antimatter runs dry.",
}
