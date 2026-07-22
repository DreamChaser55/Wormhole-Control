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

from geometry import Vector, Position
from enum import Enum, auto

# Development constants
DEBUG = False
PROFILE = False

# Math constants
SQRT3 = 1.7320508075688772

# Fullscreen mode config (supports environment override)
FULLSCREEN = os.environ.get("WORMHOLE_FULLSCREEN", "True").lower() == "true"

# Determine resolution at game start
DEFAULT_RES = Vector(2560, 1440)
SCREEN_RES = DEFAULT_RES

if FULLSCREEN:
    try:
        had_to_init = False
        if not pygame.display.get_init():
            pygame.display.init()
            had_to_init = True
        
        info = pygame.display.Info()
        if info.current_w > 0 and info.current_h > 0:
            SCREEN_RES = Vector(info.current_w, info.current_h)
            
        if had_to_init:
            pygame.display.quit()
    except Exception:
        # Fallback in headless or test environments
        SCREEN_RES = DEFAULT_RES
else:
    SCREEN_RES = DEFAULT_RES

# UI Constants
TEXT_SCALE = (SCREEN_RES.y / 720.0) ** 1.15

# Logical Galaxy Constants
LOGICAL_GALAXY_SIZE = Vector(2560.0, 1440.0)

# System view parameters
SYSTEM_CENTER_IN_PX = Position(SCREEN_RES.x // 2, SCREEN_RES.y // 2) # Center of system view hex grid in pixels
HEX_SIZE = int(25 * (SCREEN_RES.y / 720.0)) # in pixels

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
UPKEEP_COST_PER_HULL_POINT: float = 0.01  # Credits per used hull point per turn
TAX_RATE: float = 0.1  # 10% tax rate

# Antimatter Mechanics Constants
DEFAULT_ANTIMATTER_CAPACITY: float = 100.0
DEFAULT_ANTIMATTER_REGEN: float = 10.0
ANTIMATTER_CAPACITY_PER_HULL_POINT: float = 20.0
ENGINE_ANTIMATTER_COST_PER_TURN: float = 5.0
HYPERDRIVE_SYSTEM_JUMP_COST: float = 50.0
HYPERDRIVE_HEX_JUMP_COST: float = 20.0

# Antimatter Harvester component: only units with this component can generate
# new antimatter, and only while positioned near a star.
DEFAULT_ANTIMATTER_HARVEST_RATE: float = 10.0
DEFAULT_ANTIMATTER_HARVEST_RANGE: float = 800.0
ANTIMATTER_HARVESTER_HULL_COST: int = 15

# Antimatter Transfer: units without a harvester must receive antimatter by
# transferring it from another unit's existing storage.
ANTIMATTER_TRANSFER_RATE: float = 25.0
ANTIMATTER_TRANSFER_RANGE: float = 200.0



# Experience point (XP) constants
MAX_UNIT_XP: int = 1000               # Maximum XP a unit can accumulate
XP_WEAPON_DAMAGE_BONUS: float = 0.25  # +25% weapon damage at max XP
XP_DEFENSE_BONUS: float = 0.25        # +25% defense mitigation at max XP
XP_SPEED_BONUS: float = 0.15          # +15% sub-FTL speed at max XP
XP_JUMP_RANGE_BONUS: float = 0.20     # +20% hyperdrive jump range at max XP


# Object sizes in sector view (in logical world coordinates):
STATION_ICON_SIZE = 27.78
SHIP_ICON_SIZE = 27.78
PLANET_RADIUS = 375.0
WORMHOLE_RADIUS = 291.66
STAR_RADIUS = 500.01
NEBULA_RADIUS = 1666.68
STORM_RADIUS = 1666.68
MOON_RADIUS = 83.34
ASTEROID_RADIUS = 50.01
COMET_RADIUS = 50.01
CELESTIAL_FIELD_RADIUS = 300.0
SECTOR_OBJECT_CLICK_RADIUS_MULT = 1.5
DEFAULT_SUBLIGHT_SHIP_SPEED = 100.0

# UI Constants
INFO_BOX_WIDTH = int(SCREEN_RES.x * (250 / 1280.0))
TOP_BAR_HEIGHT = int(SCREEN_RES.y * (35 / 720.0))
CONTEXT_MENU_WIDTH = int(SCREEN_RES.x * (180 / 1280.0))
CONTEXT_MENU_ITEM_HEIGHT = int(SCREEN_RES.y * (25 / 720.0))

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (128, 128, 128) # Used to highlight the hex containing the selected object
DARK_GRAY = (50, 50, 50) # Hex grid color
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
YELLOW = (255, 255, 0) # Star
ORANGE = (255, 165, 0)
CYAN = (0, 255, 255) # Planet
PURPLE = (128, 0, 128) # Wormhole
HOVER_HIGHLIGHT_COLOR = (200, 200, 0, 150) # Semi-transparent yellow highlight for hovered object
SELECTION_HIGHLIGHT_COLOR = (255, 255, 255) # White highlight for selected object
MOVE_ORDER_LINE_COLOR = (0, 255, 0, 150) # Semi-transparent green line for sublight move orders
HEX_JUMP_ORDER_LINE_COLOR = (0, 255, 255, 150) # Semi-transparent cyan line for hex jump orders
WORMHOLE_JUMP_ORDER_COLOR = (255, 80, 255, 150) # Semi-transparent light magenta line for wormhole jump orders
WORMHOLE_LINE_COLOR = (180, 0, 255) # Bluish magenta for wormhole lines in galaxy view
GALAXY_BG_COLOR = (2, 2, 4)
SYSTEM_BG_COLOR = (4, 4, 8)
SECTOR_BG_COLOR = (6, 6, 12)
SECTOR_BORDER_COLOR = (60, 60, 80)

# Check if enums are already defined to prevent breaking identity during reload
import sys
_existing = sys.modules.get('constants')

if _existing and hasattr(_existing, 'HullSize'):
    HullSize = _existing.HullSize
else:
    class HullSize(Enum):
        STRIKECRAFT_WING = auto()
        TINY = auto()
        SMALL = auto()
        MEDIUM = auto()
        LARGE = auto()
        HUGE = auto()

if _existing and hasattr(_existing, 'StarType'):
    StarType = _existing.StarType
else:
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

if _existing and hasattr(_existing, 'PlanetType'):
    PlanetType = _existing.PlanetType
else:
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

if _existing and hasattr(_existing, 'NebulaType'):
    NebulaType = _existing.NebulaType
else:
    class NebulaType(Enum):
        HYDROGEN = auto()
        NITROGEN = auto()
        OXYGEN = auto()
        DUST = auto()

if _existing and hasattr(_existing, 'StormType'):
    StormType = _existing.StormType
else:
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


HULL_CAPACITIES = {
    HullSize.STRIKECRAFT_WING: 5,
    HullSize.TINY: 10,
    HullSize.SMALL: 25,
    HullSize.MEDIUM: 50,
    HullSize.LARGE: 100,
    HullSize.HUGE: 200,
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
