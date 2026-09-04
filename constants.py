import pygame
import os
import ctypes

# Disable Windows OS window scaling to ensure 1:1 pixel perfect resolution
if os.name == 'nt':
    try:
        # Windows 8.1 and later
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            # Windows Vista and later
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
from typing import Dict, Optional, Tuple, Any

from geometry import Vector, Position
from enum import Enum, auto

# Development constants
DEBUG = False
PROFILE = False

# Math constants
SQRT3 = 1.7320508075688772

# Fullscreen mode config (supports environment override)
FULLSCREEN = os.environ.get("WORMHOLE_FULLSCREEN", "True").lower() == "true"

# Function to determine screen resolution safely
def detect_screen_resolution(fullscreen: bool = FULLSCREEN) -> Vector:
    """Determine screen resolution safely, falling back to DEFAULT_RES on error or in headless environments."""
    if fullscreen:
        try:
            had_to_init = False
            if not pygame.display.get_init():
                pygame.display.init()
                had_to_init = True
            
            info = pygame.display.Info()
            res = DEFAULT_RES
            if info.current_w > 0 and info.current_h > 0:
                res = Vector(info.current_w, info.current_h)
                
            if had_to_init:
                pygame.display.quit()
            return res
        except Exception:
            return DEFAULT_RES
    return DEFAULT_RES

# Determine resolution at game start
DEFAULT_RES = Vector(2560, 1440)
SCREEN_RES = detect_screen_resolution(FULLSCREEN)

# UI Constants
TEXT_SCALE = (SCREEN_RES.y / 720.0) ** 1.15

# Logical Galaxy Constants
LOGICAL_GALAXY_SIZE = Vector(2560.0, 1440.0)

# System view parameters
SYSTEM_CENTER_IN_PX = Position(SCREEN_RES.x // 2, SCREEN_RES.y // 2) # Center of system view hex grid in pixels
HEX_SIZE = int(25 * (SCREEN_RES.y / 720.0)) # in pixels
SYSTEM_ZOOM_MIN = 0.8
SYSTEM_ZOOM_MAX = 15.0

# Sector view circle parameters
SECTOR_CIRCLE_CENTER_IN_PX = Position(SCREEN_RES.x // 2, SCREEN_RES.y // 2) # Center of sector view circle in pixels
SECTOR_CIRCLE_RADIUS_IN_PX = SCREEN_RES.y // 2 # Radius for sector view circle in pixels
SECTOR_CIRCLE_RADIUS_LOGICAL = 5000.0
SECTOR_ZOOM_MIN = 0.8
SECTOR_ZOOM_MAX = 15.0

# Capped internal resolution (diameter, in px) used to composite a storm's
# rotating particles before a single scale-to-screen blit. Bounding this
# independent of screen size/zoom keeps per-frame compositing cost constant
# even at very high zoom levels.
STORM_COMPOSE_MAX_DIAMETER = 384

# Game Mechanics Constants
DEFAULT_HYPERDRIVE_RECHARGE_DURATION: int = 3
DEFAULT_JUMP_RANGE: int = 5 # in hexes
DEFAULT_STANDOFF_DISTANCE: float = 150.0  # Logical distance maintained when following or escorting a target unit
UPKEEP_COST_PER_HULL_POINT: float = 0.01  # Credits per used hull point per turn
TAX_RATE: float = 0.1  # 10% tax rate
POPULATION_PER_HABITAT: float = 25.0  # Population required per supported civilian habitat module
BASE_HABITAT_CAPACITY: int = 1  # Base habitat modules supported by any colonized celestial body with population > 0

# Orbital Defense Constants
POPULATION_PER_ORBITAL_DEFENSE: float = 25.0  # Population required per supported orbital defense module
BASE_ORBITAL_DEFENSE_CAPACITY: int = 1  # Base orbital defense modules supported by any colonized celestial body with population > 0
DEFAULT_ORBITAL_DEFENSE_RADIUS: float = 500.0  # Tactical effective radius in logical sector units
DEFAULT_ORBITAL_DEFENSE_ATTACK_BONUS: float = 0.20  # +20% weapon attack damage bonus
DEFAULT_ORBITAL_DEFENSE_DEFENSE_BONUS: float = 0.20  # +20% damage mitigation bonus
ORBITAL_DEFENSE_HULL_COST: float = 20.0  # Base hull cost for orbital defense component
ORBITAL_DEFENSE_RING_COLOR: tuple[int, int, int] = (100, 220, 100)  # Visual range ring color in sector view


# Trade Mechanics Constants
TRADE_BASE_HULL_COST: float = 10.0
TRADE_BASE_INCOME: float = 25.0
TRADE_INCOME_PER_DISTANCE_UNIT: float = 15.0
TRADE_INTERSYSTEM_HOP_DISTANCE: float = 10.0
TRADE_ARRIVAL_RANGE: float = 200.0

# Antimatter Mechanics Constants
DEFAULT_ANTIMATTER_CAPACITY: float = 100.0
MIN_ANTIMATTER_CAPACITY: float = 100.0
DEFAULT_ANTIMATTER_REGEN: float = 10.0
ANTIMATTER_CAPACITY_PER_HULL_POINT: float = 20.0
ENGINE_ANTIMATTER_COST_PER_TURN: float = 1.0
BASELINE_ENGINE_SPEED: float = 100.0
HYPERDRIVE_SYSTEM_JUMP_COST: float = 25.0
HYPERDRIVE_HEX_JUMP_COST: float = 10.0

# Dynamic Component Tuning Constants
HANGAR_HULL_COST_PER_SLOT: float = 10.0
STRIKECRAFT_BAY_HULL_COST_PER_SLOT: float = 7.5
REPAIR_RATE_PER_HULL_POINT: float = 0.667
REPAIR_CREDIT_COST_PER_HP: float = 1.0
MINING_RATE_PER_HULL_POINT: float = 2.0
MINING_CARGO_PER_HULL_POINT: float = 20.0
INHIBITOR_RADIUS_PER_HULL_POINT: float = 5.0
INHIBITOR_ANTIMATTER_COST_PER_50_RADIUS: float = 5.0

# Minefield Constants
MINEFIELD_CREDIT_COST: float = 300.0
MINEFIELD_ANTIMATTER_COST: float = 20.0
MAX_MINEFIELDS_PER_HEX: int = 4
MINEFIELD_DEFAULT_DAMAGE: float = 40.0
MINEFIELD_DEFAULT_MINES: int = 5
MINEFIELD_DETONATION_RADIUS: float = 300.0
MINELAYER_HULL_COST: float = 15.0

# Intelligence & Counter-Intelligence Constants
CI_SWEEP_CREDIT_COST: float = 100.0
CI_SWEEP_ANTIMATTER_COST: float = 25.0
CI_SWEEP_COOLDOWN_TURNS: int = 3
CI_SWEEP_RANGE: float = 500.0

# Antimatter Harvester component: only units with this component can generate
# new antimatter, and only while positioned near a star.
DEFAULT_ANTIMATTER_HARVEST_RATE: float = 10.0
ANTIMATTER_HARVEST_RANGE: float = 3000.0
ANTIMATTER_HARVESTER_HULL_COST: float = 15.0
ANTIMATTER_HARVESTER_RETURN_THRESHOLD: float = 60.0

# Antimatter Transfer: units without a harvester must receive antimatter by
# transferring it from another unit's existing storage.
ANTIMATTER_TRANSFER_RATE: float = 25.0
ANTIMATTER_TRANSFER_RANGE: float = 200.0

# Sensors / Fog of War Constants
DEFAULT_SENSOR_SHORT_RANGE: float = 2000.0     # logical units (sector radius = 5000)
SENSOR_RANGE_PER_HULL_POINT: float = 1000.0    # hull points per unit of short-range radius
SENSOR_LONG_RANGE_HULL_COST_PER_HEX: float = 5.0   # hull points per long-range ring
DEFAULT_SENSOR_LONG_RANGE_HEXES: int = 1       # default ring count for a long-range upgrade

# Cloaking Device Constants
CLOAKING_BASIC_HULL_COST: float = 10.0            # Hull cost for Basic (single-unit) cloak
CLOAKING_ADVANCED_HULL_COST: float = 30.0         # Baseline hull cost for Advanced (area) cloak at default radius
CLOAKING_BASIC_ANTIMATTER_COST_PER_TURN: float = 5.0  # Antimatter per turn for Basic cloak
CLOAKING_ADVANCED_ANTIMATTER_COST_PER_TURN: float = 20.0  # Baseline antimatter per turn for Advanced cloak at default radius
DEFAULT_ADVANCED_CLOAKING_RADIUS: float = 500.0   # Logical radius for Advanced area cloaking
CLOAKING_ADVANCED_RADIUS_PER_HULL_POINT: float = DEFAULT_ADVANCED_CLOAKING_RADIUS / CLOAKING_ADVANCED_HULL_COST  # ~16.6667 radius units per hull point
CLOAKING_ADVANCED_ANTIMATTER_COST_PER_RADIUS: float = CLOAKING_ADVANCED_ANTIMATTER_COST_PER_TURN / DEFAULT_ADVANCED_CLOAKING_RADIUS  # 0.04 AM per turn per radius unit

# Fog visuals
FOG_PRESENCE_COLOR = (200, 60, 60)             # generic enemy-presence marker color
FOG_TINT_COLOR = (0, 0, 0, 60)                 # optional faint shading for non-detailed hexes (system view)
FOG_OF_WAR_COLOR = (40, 40, 50, 55)            # semi-transparent grey fog for out-of-sensor-range areas (sector view)

# Experience point (XP) constants
MAX_UNIT_XP: int = 1000               # Maximum XP a unit can accumulate
XP_WEAPON_DAMAGE_BONUS: float = 0.25  # +25% weapon damage at max XP
XP_DEFENSE_BONUS: float = 0.25        # +25% defense mitigation at max XP
XP_SPEED_BONUS: float = 0.15          # +15% sub-FTL speed at max XP
XP_JUMP_RANGE_BONUS: float = 0.20     # +20% hyperdrive jump range at max XP

# Object sizes in sector view (in logical world coordinates):
STATION_ICON_SIZE = 27.78
SHIP_ICON_SIZE = 27.78
PLANET_RADIUS = 562.5
WORMHOLE_RADIUS = 291.66
STAR_RADIUS = 750.015
NEBULA_RADIUS = 3600.0
STORM_RADIUS = 3600.0
MOON_RADIUS = 125.01
ASTEROID_RADIUS = 75.015
COMET_RADIUS = 75.015
CELESTIAL_FIELD_RADIUS = 300.0
ASTEROID_FIELD_RADIUS = 3600.0
ICE_FIELD_RADIUS = 3600.0
DEBRIS_FIELD_RADIUS = 2000.0
SECTOR_OBJECT_CLICK_RADIUS_MULT = 1.5
DEFAULT_SUBLIGHT_SHIP_SPEED = 100.0

# UI Constants
INFO_BOX_WIDTH = int(SCREEN_RES.x * (250 / 1280.0))
TOP_BAR_HEIGHT = int(SCREEN_RES.y * (35 / 720.0))
CONTEXT_MENU_WIDTH = int(SCREEN_RES.x * (180 / 1280.0))
CONTEXT_MENU_ITEM_HEIGHT = int(SCREEN_RES.y * (25 / 720.0))
SECTOR_GRID_SPACING = 1000.0 # Logical distance between tactical grid lines

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (128, 128, 128) # Used to highlight the hex containing the selected object
DARK_GRAY = (50, 50, 50) # Hex grid color
RED = (255, 0, 0)
DARK_RED = (100, 20, 20) # Hex fill color for enemy presence detected in system view
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
YELLOW = (255, 255, 0) # Star
ORANGE = (255, 165, 0)
CYAN = (0, 255, 255) # Planet
PURPLE = (128, 0, 128) # Wormhole
TURQUOISE = (64, 224, 208) # Non-solid celestial body effect radius
NON_SOLID_CELESTIAL_RADIUS_COLOR = TURQUOISE
HOVER_HIGHLIGHT_COLOR = (200, 200, 0, 150) # Semi-transparent yellow highlight for hovered object
SELECTION_HIGHLIGHT_COLOR = (255, 255, 255) # White highlight for selected object
MOVE_ORDER_LINE_COLOR = (0, 255, 0, 150) # Semi-transparent green line for sublight move orders
HEX_JUMP_ORDER_LINE_COLOR = (0, 255, 255, 150) # Semi-transparent cyan line for hex jump orders
HYPERDRIVE_RANGE_CIRCLE_COLOR = (0, 255, 255, 180) # Semi-transparent cyan for hyperdrive range circle
HYPERDRIVE_RANGE_HEX_FILL_COLOR = (0, 255, 255, 25) # Semi-transparent cyan fill for hexes within hyperdrive range
SENSOR_RANGE_HEX_FILL_COLOR = (0, 200, 255, 25) # Semi-transparent cyan/sky-blue fill for hexes within sensor range
WORMHOLE_JUMP_ORDER_COLOR = (255, 80, 255, 150) # Semi-transparent light magenta line for wormhole jump orders
WORMHOLE_LINE_COLOR = (180, 0, 255) # Bluish magenta for wormhole lines in galaxy view
GALAXY_BG_COLOR = (2, 2, 4)
SYSTEM_BG_COLOR = (4, 4, 8)
SECTOR_BG_COLOR = (6, 6, 12)
SECTOR_BORDER_COLOR = (60, 60, 80)
SECTOR_GRID_COLOR = (30, 35, 45) # Faint grey grid color for sector view

# Enum Definitions
class HullSize(Enum):
    STRIKECRAFT_WING = auto()
    TINY = auto()
    SMALL = auto()
    MEDIUM = auto()
    LARGE = auto()
    HUGE = auto()

ADVANCED_CLOAKING_MIN_HULL: HullSize = HullSize.SMALL # Minimum hull size capable of mounting Advanced Cloak

class FieldDensity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

FIELD_DENSITY_MAX_HULL: Dict[FieldDensity, HullSize] = {
    FieldDensity.LOW: HullSize.LARGE,
    FieldDensity.MEDIUM: HullSize.MEDIUM,
    FieldDensity.HIGH: HullSize.SMALL,
}

FIELD_DENSITY_PARTICLES: Dict[FieldDensity, int] = {
    FieldDensity.LOW: 200,
    FieldDensity.MEDIUM: 350,
    FieldDensity.HIGH: 550,
}

ASTEROID_FIELD_PARTICLES: Dict[FieldDensity, int] = {
    FieldDensity.LOW: 200,
    FieldDensity.MEDIUM: 350,
    FieldDensity.HIGH: 550,
}

ICE_FIELD_PARTICLES: Dict[FieldDensity, int] = {
    FieldDensity.LOW: 150,
    FieldDensity.MEDIUM: 260,
    FieldDensity.HIGH: 400,
}

DEBRIS_FIELD_PARTICLES: Dict[FieldDensity, int] = {
    FieldDensity.LOW: 100,
    FieldDensity.MEDIUM: 180,
    FieldDensity.HIGH: 300,
}

class StarType(Enum):
    # Main sequence stars
    G_TYPE = auto()  # Sun-like
    RED_DWARF = auto()
    # Stellar remnants
    WHITE_DWARF = auto()
    NEUTRON_STAR = auto()
    PULSAR = auto()
    BLACK_HOLE = auto()
    # Giant stars
    RED_GIANT = auto()
    YELLOW_GIANT = auto()
    BLUE_GIANT = auto()
    # Pre-stellar objects
    PROTOSTAR = auto()
    BROWN_DWARF = auto()

STAR_HARVEST_MULTIPLIERS: Dict[StarType, float] = {
    StarType.PULSAR: 2.5,
    StarType.BLUE_GIANT: 2.0,
    StarType.NEUTRON_STAR: 1.8,
    StarType.YELLOW_GIANT: 1.5,
    StarType.RED_GIANT: 1.3,
    StarType.G_TYPE: 1.0,
    StarType.WHITE_DWARF: 0.8,
    StarType.PROTOSTAR: 0.7,
    StarType.RED_DWARF: 0.5,
    StarType.BROWN_DWARF: 0.3,
    StarType.BLACK_HOLE: 0.1,
}

STAR_COLORS: Dict[StarType, Tuple[int, int, int]] = {
    StarType.G_TYPE: (255, 235, 120),
    StarType.RED_DWARF: (255, 127, 80),
    StarType.WHITE_DWARF: (240, 248, 255),
    StarType.NEUTRON_STAR: (200, 245, 255),
    StarType.PULSAR: (225, 110, 255),
    StarType.BLACK_HOLE: (75, 35, 100),
    StarType.RED_GIANT: (235, 50, 35),
    StarType.YELLOW_GIANT: (255, 195, 0),
    StarType.BLUE_GIANT: (173, 216, 255),
    StarType.PROTOSTAR: (255, 140, 0),
    StarType.BROWN_DWARF: (160, 82, 45),
}

class PlanetType(Enum):
    TERRAN = auto()
    DESERT = auto()
    VOLCANIC = auto()
    ICE = auto()
    BARREN = auto()
    FERROUS = auto()
    GREENHOUSE = auto()
    OCEANIC = auto()
    GAS_GIANT = auto()

class NebulaType(Enum):
    HYDROGEN = auto()
    NITROGEN = auto()
    OXYGEN = auto()
    DUST = auto()

class StormType(Enum):
    PLASMA = auto()
    MAGNETIC = auto()
    RADIATION = auto()

NEBULA_COLORS = {
    NebulaType.HYDROGEN: (255, 105, 180, 30),
    NebulaType.NITROGEN: (138, 43, 226, 30),
    NebulaType.OXYGEN: (0, 191, 255, 30),
    NebulaType.DUST: (160, 82, 45, 30),
}

STORM_COLORS = {
    StormType.PLASMA: (255, 69, 0, 40),      # Fiery OrangeRed
    StormType.MAGNETIC: (75, 0, 130, 40),    # Electric Indigo
    StormType.RADIATION: (173, 255, 47, 40), # Sickly GreenYellow
}

STORM_LIGHTNING_COLOR = (255, 255, 224, 150) # Light Yellow for lightning

# Planetary Traits & Habitability Configuration
PLANET_TRAITS: Dict[PlanetType, Dict[str, Any]] = {
    PlanetType.TERRAN: {
        "is_colonizable": True,
        "max_population": 100.0,
        "growth_rate": 0.02,
        "passive_metal": 0.0,
        "passive_crystal": 0.0,
        "am_harvest_multiplier": 0.0,
        "inhibition_radius": 3000.0,
        "collision_radius": PLANET_RADIUS,
        "description": "Temperate biosphere with optimal habitability.",
    },
    PlanetType.OCEANIC: {
        "is_colonizable": True,
        "max_population": 120.0,
        "growth_rate": 0.025,
        "passive_metal": 0.0,
        "passive_crystal": 0.0,
        "am_harvest_multiplier": 0.0,
        "inhibition_radius": 3000.0,
        "collision_radius": PLANET_RADIUS,
        "description": "Lush water world supporting expansive population.",
    },
    PlanetType.DESERT: {
        "is_colonizable": True,
        "max_population": 75.0,
        "growth_rate": 0.015,
        "passive_metal": 0.0,
        "passive_crystal": 0.0,
        "am_harvest_multiplier": 0.0,
        "inhibition_radius": 3000.0,
        "collision_radius": PLANET_RADIUS,
        "description": "Arid dunes and scarce water reservoirs.",
    },
    PlanetType.ICE: {
        "is_colonizable": True,
        "max_population": 60.0,
        "growth_rate": 0.010,
        "passive_metal": 0.0,
        "passive_crystal": 2.0,
        "am_harvest_multiplier": 0.0,
        "inhibition_radius": 3000.0,
        "collision_radius": PLANET_RADIUS,
        "description": "Glaciated surface yielding passive crystal deposits.",
    },
    PlanetType.BARREN: {
        "is_colonizable": True,
        "max_population": 40.0,
        "growth_rate": 0.008,
        "passive_metal": 0.0,
        "passive_crystal": 0.0,
        "am_harvest_multiplier": 0.0,
        "inhibition_radius": 3000.0,
        "collision_radius": PLANET_RADIUS,
        "description": "Airless rocky crust requiring sealed dome habitats.",
    },
    PlanetType.VOLCANIC: {
        "is_colonizable": True,
        "max_population": 50.0,
        "growth_rate": 0.008,
        "passive_metal": 5.0,
        "passive_crystal": 0.0,
        "am_harvest_multiplier": 0.0,
        "inhibition_radius": 3000.0,
        "collision_radius": PLANET_RADIUS,
        "description": "Hostile geothermal vents rich in raw mineral deposits.",
    },
    PlanetType.FERROUS: {
        "is_colonizable": True,
        "max_population": 70.0,
        "growth_rate": 0.012,
        "passive_metal": 8.0,
        "passive_crystal": 0.0,
        "am_harvest_multiplier": 0.0,
        "inhibition_radius": 3250.0,
        "collision_radius": PLANET_RADIUS,
        "description": "Heavy metal crust yielding rich passive metal revenue.",
    },
    PlanetType.GREENHOUSE: {
        "is_colonizable": True,
        "max_population": 35.0,
        "growth_rate": 0.005,
        "passive_metal": 0.0,
        "passive_crystal": 3.0,
        "am_harvest_multiplier": 0.0,
        "inhibition_radius": 3000.0,
        "collision_radius": PLANET_RADIUS,
        "description": "Caustic high-pressure atmosphere yielding exotic crystal.",
    },
    PlanetType.GAS_GIANT: {
        "is_colonizable": False,
        "max_population": 0.0,
        "growth_rate": 0.0,
        "passive_metal": 0.0,
        "passive_crystal": 0.0,
        "am_harvest_multiplier": 0.5,
        "inhibition_radius": 3500.0,
        "collision_radius": 675.0,
        "description": "Massive volatile gas mantle. Non-colonizable; antimatter harvesting hub.",
    },
}

# Environmental Hazards & Special Effects Constants
STORM_PLASMA_DAMAGE_PER_TURN = 8.0
STORM_MAGNETIC_AM_DRAIN_PER_TURN = 6.0
STORM_RADIATION_COMPONENT_DAMAGE_PER_TURN = 4.0
STORM_RADIATION_ACCURACY_PENALTY = 0.20

BLACK_HOLE_INHIBITION_RADIUS = 4500.0
BLACK_HOLE_EVENT_HORIZON_RADIUS = 750.0
BLACK_HOLE_EVENT_HORIZON_DAMAGE = 15.0
PULSAR_SHIELD_DRAIN_PERCENT = 0.05
GIANT_STAR_RADIUS = 900.0
GIANT_STAR_INHIBITION_RADIUS = 3750.0

ASTEROID_FIELD_SPEED_MOD = 0.75
ICE_FIELD_SPEED_MOD = 0.80
ICE_FIELD_BEAM_DEFENSE_BONUS = 0.10
ICE_FIELD_COOLDOWN_REDUCTION = 1

DEBRIS_FIELD_SPEED_MOD = 0.75
DEBRIS_FIELD_DEFENSE_BONUS = 0.10
DEBRIS_FIELD_HAZARD_SPEED_THRESHOLD = 50.0
DEBRIS_FIELD_HAZARD_DAMAGE = 2.0

ASTEROID_FIELD_DENSITY_SPEED_MOD: Dict[FieldDensity, float] = {
    FieldDensity.LOW: 0.85,
    FieldDensity.MEDIUM: 0.75,
    FieldDensity.HIGH: 0.65,
}

ICE_FIELD_DENSITY_SPEED_MOD: Dict[FieldDensity, float] = {
    FieldDensity.LOW: 0.90,
    FieldDensity.MEDIUM: 0.80,
    FieldDensity.HIGH: 0.70,
}

ICE_FIELD_DENSITY_BEAM_DEFENSE_BONUS: Dict[FieldDensity, float] = {
    FieldDensity.LOW: 0.05,
    FieldDensity.MEDIUM: 0.10,
    FieldDensity.HIGH: 0.15,
}

DEBRIS_FIELD_DENSITY_SPEED_MOD: Dict[FieldDensity, float] = {
    FieldDensity.LOW: 0.85,
    FieldDensity.MEDIUM: 0.75,
    FieldDensity.HIGH: 0.65,
}

DEBRIS_FIELD_DENSITY_DEFENSE_BONUS: Dict[FieldDensity, float] = {
    FieldDensity.LOW: 0.05,
    FieldDensity.MEDIUM: 0.10,
    FieldDensity.HIGH: 0.15,
}

DEBRIS_FIELD_DENSITY_HAZARD_DAMAGE: Dict[FieldDensity, float] = {
    FieldDensity.LOW: 1.0,
    FieldDensity.MEDIUM: 2.0,
    FieldDensity.HIGH: 3.0,
}


HYDROGEN_NEBULA_HARVEST_MULTIPLIER = 0.4
HYDROGEN_NEBULA_AM_BURN_MOD = 0.5
DUST_NEBULA_SENSOR_MOD = 0.70
NITROGEN_NEBULA_COOLDOWN_REDUCTION = 1
OXYGEN_NEBULA_SHIELD_REGEN_BONUS = 0.25
OXYGEN_NEBULA_SPLASH_DAMAGE_MOD = 1.15


HULL_CAPACITIES: Dict[HullSize, float] = {
    HullSize.STRIKECRAFT_WING: 5.0,
    HullSize.TINY: 10.0,
    HullSize.SMALL: 25.0,
    HullSize.MEDIUM: 50.0,
    HullSize.LARGE: 100.0,
    HullSize.HUGE: 200.0,
}

HYPERDRIVE_ANTIMATTER_HULL_SIZE_MULTIPLIERS: Dict[HullSize, float] = {
    HullSize.STRIKECRAFT_WING: 0.4,
    HullSize.TINY: 0.6,
    HullSize.SMALL: 0.8,
    HullSize.MEDIUM: 1.0,
    HullSize.LARGE: 1.5,
    HullSize.HUGE: 2.0,
}

ENGINE_ANTIMATTER_HULL_SIZE_MULTIPLIERS: Dict[HullSize, float] = {
    HullSize.STRIKECRAFT_WING: 0.4,
    HullSize.TINY: 0.6,
    HullSize.SMALL: 0.8,
    HullSize.MEDIUM: 1.0,
    HullSize.LARGE: 1.5,
    HullSize.HUGE: 2.0,
}

HIT_POINTS = {
    HullSize.STRIKECRAFT_WING: 40,
    HullSize.TINY: 20,
    HullSize.SMALL: 50,
    HullSize.MEDIUM: 100,
    HullSize.LARGE: 200,
    HullSize.HUGE: 400,
}

HULL_BASE_ICON_SCALES = {
    HullSize.STRIKECRAFT_WING: 1.2,
    HullSize.TINY: 0.6,
    HullSize.SMALL: 0.8,
    HullSize.MEDIUM: 1.0, # Medium is the baseline
    HullSize.LARGE: 1.3,
    HullSize.HUGE: 1.7,
}

HULL_DOT_COUNTS = {
    HullSize.STRIKECRAFT_WING: 0,
    HullSize.TINY: 1,
    HullSize.SMALL: 2,
    HullSize.MEDIUM: 3,
    HullSize.LARGE: 4,
    HullSize.HUGE: 5,
}

SECTOR_VIEW_BASE_ICON_SIZE = 22.22
ICON_DOT_RADIUS = 4.17
ICON_DOT_SPACING = 11.11

MIN_ANTIMATTER_CAPACITY_BY_HULL: Dict[HullSize, float] = {
    HullSize.STRIKECRAFT_WING: 40.0,
    HullSize.TINY: 60.0,
    HullSize.SMALL: 80.0,
    HullSize.MEDIUM: 100.0,
    HullSize.LARGE: 150.0,
    HullSize.HUGE: 200.0,
}

def get_min_antimatter_capacity(hull_size: Optional[HullSize] = None) -> float:
    """Return the minimum antimatter storage capacity for a given hull size.

    If hull_size is None, returns the baseline MIN_ANTIMATTER_CAPACITY (100.0).
    """
    if hull_size is None:
        return MIN_ANTIMATTER_CAPACITY
    return MIN_ANTIMATTER_CAPACITY_BY_HULL.get(hull_size, MIN_ANTIMATTER_CAPACITY)

