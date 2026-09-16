"""
catalog.py

Component definitions, catalogue constants, option lists, and component descriptions
for the Unit Designer GUI.
"""

import typing
from constants import HullSize
from unit_components.enums import (
    AbilityType, CloakingType, HyperdriveType, TurretType, TurretVariant, WingType,
)

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
    {"key": "has_inhibitor",             "label": "Inhibitor Field",    "cost_key": "inhibitor_hull_cost",        "default_cost": 6.666666666666667, "is_dynamic": True},
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
HYPERDRIVE_TYPES = [t.name for t in HyperdriveType]
CLOAKING_TYPES = [t.name for t in CloakingType]
WING_TYPES = [t.name for t in WingType]


def ability_button_text(
    aname: str, selected: bool = False, missing_components: typing.Sequence[str] = ()
) -> str:
    """Label missing equipment and always show Nebula Catalyst's prerequisites."""
    from unit_components.abilities import ABILITY_DEFINITIONS

    definition = ABILITY_DEFINITIONS[AbilityType(aname)]
    text = f"[{'x' if selected else ' '}] {definition.name}"
    displayed_components = (definition.required_components
        if definition.ability_type == AbilityType.NEBULA_CATALYST else missing_components)
    if displayed_components:
        labels = {row["key"]: row["label"] for row in COMPONENT_ROWS}
        requirements = ", ".join(labels.get(key, key) for key in displayed_components)
        text += f" (Req: {requirements})"
    if aname in ('tracking_lock', 'flak_barrage') and 'anti-strikecraft turret' not in missing_components:
        text += ' (Requires an anti-strikecraft turret)'
    return text


COMPONENT_DESCRIPTIONS = {
    "has_engine": "Sublight propulsion for movement within a sector. Destroyed Engines or non-positive effective speed prevent sublight movement; an operational Hyperdrive can still jump.",
    "has_antimatter_storage": "Stores antimatter (AM) fuel for movement, jumps and equipment. Storage alone does not generate fuel; replenish it by harvesting or transfer.",
    "has_antimatter_harvester": "Collects antimatter from stars and hydrogen nebulae using harvesting orders. Yield depends on the source; harvesting is not automatic fuel generation anywhere in space.",
    "has_hyperdrive": "Basic Hyperdrive jumps between sectors within a star system. Advanced Hyperdrive also traverses wormholes between systems. Natural and artificial inhibition fields block jump entry and exit.",
    "has_weapon_bays": "Mounts Mass Driver, Beam and Missile turrets. Choose Standard, Anti-Strikecraft or Long Range variants. Turrets fire during authorized combat orders, subject to range, cooldown and line of fire.",
    "has_defenses": "Mitigates incoming attacks with Armor, Shields and Point Defense. Armor counters kinetic fire, Shields counter beams, and Point Defense counters missiles. Shields are mitigation, not a regenerating health pool.",
    "has_constructor_component": "Builds Tiny through Huge ships and stations and refits friendly or allied units. Strikecraft wings are produced by Strikecraft Bays. Construction spends credits and takes turns.",
    "has_repair_component": "Restores damaged friendly or allied ships using repair orders. The ship approaches repair range automatically; repair work costs credits.",
    "has_colony_component": "Carries colonists to settle habitable planets, moons and colonizable asteroids. Load population from friendly or allied colonies before colonizing. Gas giants cannot be colonized.",
    "has_civilian_habitat_component": "Provides 50 credits per turn while supported by its owner's populated colony in the same sector. Active habitats are destinations for trade routes.",
    "has_orbital_defense_component": "A supported installation boosts weapon damage and defense mitigation for friendly and allied ships in range. Colony support slots are shared across allies. Overlapping auras stack additively.",
    "has_trade_component": "The Trade Module requires Engines and earns credits by travelling between active Civilian Habitats in different sectors. Longer routes yield more income. Continuous Trade repeats the route.",
    "has_mining_component": "Extracts metal from Metal Asteroids and crystal from Comets into cargo storage. Unload at the matching refinery. Continuous Mine repeats harvesting and delivery.",
    "has_metal_refinery_component": "Processes mined metal cargo delivered by mining ships into usable metal resources. It does not mine asteroids itself.",
    "has_crystal_refinery_component": "Processes mined crystal cargo delivered by mining ships into usable crystal resources. It does not mine comets itself.",
    "has_hangar": "Carries Tiny vessels for transport and later deployment. Hangars do not accept strikecraft wings; those use a Strikecraft Bay.",
    "has_strikecraft_bay": "Builds, carries and replenishes Fighter or Bomber Wings. Fighters intercept wings; Bombers attack larger ships. Wings travel between sectors aboard their carrier.",
    "has_inhibitor": "Projects a field preventing hyperdrive jumps into or out of its area. The field must fit inside the sector and cannot overlap another natural or artificial inhibition zone. Running out of fuel deactivates it.",
    "has_ability_component": "Equips combat, support and toggleable environmental resistance abilities. Each ability requires its listed equipment. Casts require enough antimatter and a ready cooldown; resistance toggles consume antimatter each owner turn while enabled.",
    "has_sensors": "Provides short-range visual coverage and long-range sector detection, shared with allies. Short-range inspection reveals detail; long-range detection can be defeated by cloaking or terrain concealment.",
    "has_minelayer_component": "Deploys Anti-Ship or Anti-Strikecraft minefields. Enemy ships ending their owner's movement phase inside a matching field can trigger mines; allied, hidden and docked ships are excluded.",
    "has_marines_component": "Carries boarding teams for capturing enemy vessels through the Capture Unit ability. Equipping Marines alone does not equip that ability.",
    "has_cloaking_device": "Activated cloaking hides ships from enemy long-range sensors. Basic protects the ship itself; Advanced also protects allies within its configured radius. Short-range sensors still detect cloaked ships.",
    "has_intelligence_component": "Deploys agents onto enemy ships and colonies for sensor intelligence and sabotage. Agents can relocate between enemy hosts or be extracted. Counter-Intelligence is an optional upgrade for detecting and eliminating enemy agents.",
    "has_counter_intelligence": "Enables active CI Sweeps to reveal enemy agents on friendly or allied assets, and elimination of discovered agents. There is no passive discovery.",
}
