from geometry import Vector, Position
from enum import Enum, auto

# Development constants
DEBUG = False
PROFILE = False

# Math constants
SQRT3 = 1.7320508075688772

# UI Constants
SCREEN_RES = Vector(1280, 720)

# System view parameters
SYSTEM_CENTER_IN_PX = Position(SCREEN_RES.x // 2, SCREEN_RES.y // 2) # Center of system view hex grid in pixels
HEX_SIZE = 25 # in pixels

# Sector view circle parameters
SECTOR_CIRCLE_CENTER_IN_PX = Position(SCREEN_RES.x // 2, SCREEN_RES.y // 2) # Center of sector view circle in pixels
SECTOR_CIRCLE_RADIUS_IN_PX = SCREEN_RES.y // 2 # Radius for sector view circle in pixels
SECTOR_CIRCLE_RADIUS_LOGICAL = 1000.0

# Game Mechanics Constants
DEFAULT_HYPERDRIVE_RECHARGE_DURATION: int = 3
DEFAULT_JUMP_RANGE: int = 5 # in hexes

# Object sizes in sector view (in pixels):
STATION_ICON_SIZE = 10
SHIP_ICON_SIZE = 10
PLANET_RADIUS = 45
WORMHOLE_RADIUS = 35
STAR_RADIUS = 60
NEBULA_RADIUS = 200
STORM_RADIUS = 200
SECTOR_OBJECT_CLICK_RADIUS_MULT = 1.5
DEFAULT_SUBLIGHT_SHIP_SPEED = 100.0

# UI Constants
INFO_BOX_WIDTH = 250
TOP_BAR_HEIGHT = 35
CONTEXT_MENU_WIDTH = 180
CONTEXT_MENU_ITEM_HEIGHT = 25

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
GALAXY_BG_COLOR = (5, 5, 10)
SYSTEM_BG_COLOR = (10, 10, 20)
SECTOR_BG_COLOR = (20, 20, 40)
SECTOR_BORDER_COLOR = (60, 60, 80)

# Hull Size Constants

class HullSize(Enum):
    TINY = auto()
    SMALL = auto()
    MEDIUM = auto()
    LARGE = auto()
    HUGE = auto()

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


HULL_CAPACITIES = {
    HullSize.TINY: 10,
    HullSize.SMALL: 25,
    HullSize.MEDIUM: 50,
    HullSize.LARGE: 100,
    HullSize.HUGE: 200,
}

HIT_POINTS = {
    HullSize.TINY: 20,
    HullSize.SMALL: 50,
    HullSize.MEDIUM: 100,
    HullSize.LARGE: 200,
    HullSize.HUGE: 400,
}

HULL_BASE_ICON_SCALES = {
    HullSize.TINY: 0.6,
    HullSize.SMALL: 0.8,
    HullSize.MEDIUM: 1.0, # Medium is the baseline
    HullSize.LARGE: 1.3,
    HullSize.HUGE: 1.7,
}

HULL_DOT_COUNTS = {
    HullSize.TINY: 1,
    HullSize.SMALL: 2,
    HullSize.MEDIUM: 3,
    HullSize.LARGE: 4,
    HullSize.HUGE: 5,
}

SECTOR_VIEW_BASE_ICON_SIZE = 8.0
ICON_DOT_RADIUS = 1.5
ICON_DOT_SPACING = 4.0
