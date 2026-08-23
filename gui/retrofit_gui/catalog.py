"""
catalog.py

Component definitions, catalogue metadata, option constants, and default configs
for the Retrofit Customization Options Wizard.
"""

from typing import List, Dict, Any
from constants import (
    HullSize, DEFAULT_ANTIMATTER_CAPACITY, DEFAULT_SENSOR_SHORT_RANGE,
    DEFAULT_JUMP_RANGE, ANTIMATTER_HARVESTER_HULL_COST, MINELAYER_HULL_COST,
    ORBITAL_DEFENSE_HULL_COST
)
from unit_components import (
    Engines, Hyperdrive, Weapons, Defenses, AntimatterHarvester, AntimatterStorage,
    Sensors, RepairComponent, MiningComponent, MetalRefineryComponent,
    CrystalRefineryComponent, HangarComponent, StrikecraftBayComponent,
    ColonyComponent, CivilianHabitatComponent, OrbitalDefenseComponent,
    TradeComponent, HyperspaceInhibitionFieldEmitter, MinelayerComponent,
    MarinesComponent, CloakingDevice, AbilityComponent, Constructor,
    TurretType, TurretVariant, AbilityType
)

# List of mountable component definitions for Retrofit Wizard
# comp_key: canonical internal key matching Constructor / refit mapping
# display_name: player-facing label
# comp_cls: UnitComponent class
# is_dynamic: whether the component has dynamic configurable parameters
RETROFIT_COMPONENTS: List[Dict[str, Any]] = [
    {
        "comp_key": "Engines",
        "display_name": "Engines",
        "comp_cls": Engines,
        "is_dynamic": True,
        "description": "Sublight propulsion thrusters enabling movement within tactical sectors. Speed determines movement rate and antimatter efficiency.",
    },
    {
        "comp_key": "Hyperdrive",
        "display_name": "Hyperdrive",
        "comp_cls": Hyperdrive,
        "is_dynamic": True,
        "description": "FTL drive for inter-sector travel. Basic hyperdrive enables hex jumps within star systems; Advanced hyperdrive enables traversal through wormholes.",
    },
    {
        "comp_key": "Weapons",
        "display_name": "Weapons Bay",
        "comp_cls": Weapons,
        "is_dynamic": True,
        "description": "Mounts weapon turrets (Mass Driver, Beam, Missile) across Standard, Anti-Strikecraft, and Long-Range variants to engage hostile targets.",
    },
    {
        "comp_key": "Defenses",
        "display_name": "Defenses",
        "comp_cls": Defenses,
        "is_dynamic": True,
        "description": "Defensive mitigation systems consisting of Armor plating, Rechargeable Shields, and Point Defense (PD) arrays.",
    },
    {
        "comp_key": "AntimatterStorage",
        "display_name": "Antimatter Storage",
        "comp_cls": AntimatterStorage,
        "is_dynamic": True,
        "description": "Dedicated high-energy containment tanks storing antimatter fuel for sublight thrusters, hyperdrive jumps, cloaks, and special abilities.",
    },
    {
        "comp_key": "Sensors",
        "display_name": "Sensor Suite",
        "comp_cls": Sensors,
        "is_dynamic": True,
        "description": "Tactical scanning arrays providing short-range tactical line of sight and long-range inter-sector strategic detection.",
    },
    {
        "comp_key": "StrikecraftBayComponent",
        "display_name": "Strikecraft Bay",
        "comp_cls": StrikecraftBayComponent,
        "is_dynamic": True,
        "description": "Specialized flight decks supporting Fighter or Bomber strikecraft wings for tactical space superiority and strike missions.",
    },
    {
        "comp_key": "HangarComponent",
        "display_name": "Hangar Bay",
        "comp_cls": HangarComponent,
        "is_dynamic": True,
        "description": "Internal docking bays capable of carrying smaller starships and support craft.",
    },
    {
        "comp_key": "RepairComponent",
        "display_name": "Repair Module",
        "comp_cls": RepairComponent,
        "is_dynamic": True,
        "description": "Engineering repair beams capable of repairing damaged friendly hulls in the field.",
    },
    {
        "comp_key": "MiningComponent",
        "display_name": "Mining Module",
        "comp_cls": MiningComponent,
        "is_dynamic": True,
        "description": "Industrial resource extraction beams allowing vessels to harvest metal from asteroids and crystal from comets.",
    },
    {
        "comp_key": "HyperspaceInhibitionFieldEmitter",
        "display_name": "Hyperspace Inhibitor",
        "comp_cls": HyperspaceInhibitionFieldEmitter,
        "is_dynamic": True,
        "description": "Projects a hyperspace interdiction field that blocks all hyperdrive jumps into or out of its operational radius.",
    },
    {
        "comp_key": "MarinesComponent",
        "display_name": "Marines Barracks",
        "comp_cls": MarinesComponent,
        "is_dynamic": True,
        "description": "Quarters specialized Marine assault boarding teams capable of boarding and capturing hostile vessels.",
    },
    {
        "comp_key": "AbilityComponent",
        "display_name": "Special Abilities",
        "comp_cls": AbilityComponent,
        "is_dynamic": True,
        "description": "Equips active tactical combat and support abilities (Adaptive Forcefields, Microjumps, EMP Ion Bolts, Repair Clouds, etc.).",
    },
    {
        "comp_key": "CloakingDevice",
        "display_name": "Cloaking Device",
        "comp_cls": CloakingDevice,
        "is_dynamic": True,
        "description": "Active stealth camouflage field hiding vessels from enemy long-range inter-sector sensors. Basic provides personal stealth; Advanced projects area stealth.",
    },
    {
        "comp_key": "AntimatterHarvester",
        "display_name": "AM Harvester",
        "comp_cls": AntimatterHarvester,
        "is_dynamic": False,
        "description": "Automated scoop array that gathers antimatter particles when stationed in solar sectors near stars.",
    },
    {
        "comp_key": "MetalRefineryComponent",
        "display_name": "Metal Refinery",
        "comp_cls": MetalRefineryComponent,
        "is_dynamic": False,
        "description": "Refines raw ore into usable industrial metal alloys.",
    },
    {
        "comp_key": "CrystalRefineryComponent",
        "display_name": "Crystal Refinery",
        "comp_cls": CrystalRefineryComponent,
        "is_dynamic": False,
        "description": "Processes harvested raw crystal into refined energy crystals.",
    },
    {
        "comp_key": "ColonyComponent",
        "display_name": "Colony Module",
        "comp_cls": ColonyComponent,
        "is_dynamic": False,
        "description": "Carries colonial infrastructure to establish colonies on habitable worlds.",
    },
    {
        "comp_key": "CivilianHabitatComponent",
        "display_name": "Civilian Habitat",
        "comp_cls": CivilianHabitatComponent,
        "is_dynamic": False,
        "description": "Provides direct economic tax bonuses (+50 credits/turn) when stationed at colonized celestial bodies.",
    },
    {
        "comp_key": "OrbitalDefenseComponent",
        "display_name": "Orbital Defense",
        "comp_cls": OrbitalDefenseComponent,
        "is_dynamic": False,
        "description": "Projects a tactical aura (+20% damage, +20% defense mitigation) for friendly ships in colonized sectors.",
    },
    {
        "comp_key": "TradeComponent",
        "display_name": "Trade Module",
        "comp_cls": TradeComponent,
        "is_dynamic": False,
        "description": "Enables civilian trade runs between active Civilian Habitats across star systems to generate trade profits. (Requires Engine).",
    },
    {
        "comp_key": "MinelayerComponent",
        "display_name": "Minelayer",
        "comp_cls": MinelayerComponent,
        "is_dynamic": False,
        "description": "Deploys tactical anti-ship or anti-strikecraft minefields for area denial.",
    },
    {
        "comp_key": "Constructor",
        "display_name": "Constructor Module",
        "comp_cls": Constructor,
        "is_dynamic": False,
        "description": "Enables construction of orbital installations, starbases, and field refitting of friendly starships.",
    },
]

TURRET_TYPES = [t.name for t in TurretType]
TURRET_VARIANTS = [v.name for v in TurretVariant]
ABILITY_NAMES = [a.value for a in AbilityType]
HYPERDRIVE_TYPES = ["BASIC", "ADVANCED"]
CLOAKING_TYPES = ["BASIC", "ADVANCED"]
WING_TYPES = ["FIGHTER", "BOMBER"]
