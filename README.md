# Wormhole Control

**Wormhole Control** is a 2D turn-based 4X space strategy game prototype written in Python using `pygame-ce` ('pygame - Community Edition') and `pygame_gui`. The game features a large-scale universe where players manage space ships across a galaxy of star systems connected by wormholes. Each star system contains a hexagonal grid of sectors.

## Features

### Core Gameplay
- **Turn-based Strategy**: Classic 4X gameplay (eXplore, eXpand, eXploit, eXterminate)
- **Multi-scale Universe**: Navigate between galaxy view, system view, and sector view
- **Wormhole Network**: Faster-than-light travel between star systems via wormhole connections
- **Resource Economy**: Manage Credits, Metal, Crystal, and Antimatter fuel
- **Player vs AI**: Support for multiple players (human and AI) with turn processing

### Space Units & Components
- **Modular Ship Design**: Units built with customizable components and dynamic parameter scaling
- **Hull Sizes**: Six hull classes (`STRIKECRAFT_WING`, `TINY`, `SMALL`, `MEDIUM`, `LARGE`, `HUGE`) with different capacities and base stats
- **Unit Components (15 total)**:
  - **Engines**: Enable sublight movement within sectors
  - **Hyperdrives**: Basic (intra-system jumps) and Advanced (inter-system jumps via wormholes)
  - **Weapons**: Combat systems with customizable weapon types and damage parameters
  - **Defenses**: Defensive shields and armor for damage mitigation
  - **Inhibitors**: Hyperspace inhibition field generators (prevents enemy jumps within radius)
  - **Colony Component**: For planetary colonization
  - **Constructor Component**: For building space stations and structures
  - **Refinery Components**: Metal and Crystal processing modules
  - **Mining Component**: Automated mining of resources from celestial bodies
  - **Antimatter Harvester**: Harvests antimatter fuel from stars
  - **Hangar Component**: Stores and transports dockable ships
  - **Strikecraft Bay**: Deploys strikecraft wings (fighters, bombers)
  - **Marines Component**: Boarding actions and unit capture mechanics
  - **Minelayer Component**: Deploys defensive minefields in sector hexes
  - **Repair Component**: Automated hull repair and maintenance field generator
  - **Sensors Component**: Short-range and long-range sensor detection for visibility

### Special Abilities (7 total)
- **Adaptive Forcefield**: Temporarily boosts defensive damage mitigation
- **Capture Unit**: Boarding action by Marines to commandeer enemy vessels
- **Cluster Warhead**: High-impact area explosion across targeted hexes
- **Designate Target**: Marks target unit to increase fleet attack accuracy
- **Ion Bolt**: Disables targeted enemy systems and sub-FTL engines
- **Missile Batteries**: Launches long-range tactical missile salvos
- **Repair Cloud**: Emits a nanite cloud that repairs adjacent friendly units

### Celestial Objects
- **Stars**: Various types (G-Type, Red Dwarf, White Dwarf, Neutron Star, Pulsar, Black Hole, etc.) with star-harvesting multipliers
- **Planets**: Nine planet types (Terran, Desert, Volcanic, Ice, Barren, Ferrous, Greenhouse, Oceanic, Gas Giant)
- **Colonizable Bodies**: Planets, Moons, Asteroids (Metal source)
- **Space Phenomena**: Nebulae, Storms (Plasma, Magnetic, Radiation), Comets (Crystal source), Asteroid Fields, Debris Fields

### Advanced Subsystems
- **Unit Designer**: Custom unit design GUI with dynamic hull cost calculation, component scaling, and template serialization
- **Save & Load System**: Full game state persistence to JSON with save management
- **Fog of War & Visibility**: Dynamic sensor-based visibility mapping across sector hexes and galaxy views
- **Experience System**: Units gain XP through combat and actions, boosting stats up to rank caps
- **Complex Orders System**: Queue sublight move, hex jump, wormhole jump, harvest, transfer, repair, minefield, and ability orders

## Installation & Requirements

### Dependencies
- **Python 3.8+**
- **pygame-ce**: Core game engine
- **pygame_gui**: User interface framework

#### Install dependencies:
```bash
pip install pygame-ce pygame_gui
```

## Game Controls & Interface

### View Navigation
- **Galaxy View**: Overview of all star systems and wormhole connections
- **System View**: Hexagonal grid showing all sectors within a star system
- **Sector View**: Detailed view of individual sector with celestial bodies and units

### Unit Management
- **Selection**: Click to select units and objects
- **Multiple Selection**: Drag selection box or Ctrl+click
- **Context Menus**: Right-click for available actions and special abilities
- **Order Queue**: View and manage pending unit orders
- **Unit Editor**: Access the Unit Designer to create and save custom ship templates

### Turn System
- **End Turn**: Process all player actions and advance to next player
- **Resource Display**: Real-time tracking of Credits, Metal, Crystal, Antimatter
- **Player Indicator**: Visual display of current player and team color

## Project Structure

```
Wormhole Control/
├── game.py                   # Central game loop facade and delegate controller
├── game_logging.py           # Custom application logging formatter and logger bootstrap
├── game_camera.py            # Sector view camera math and smooth zoom/pan controller
├── economy.py                # Credit income and fleet upkeep calculation functions
├── game_setup.py             # Game state bootstrap and starting fleet setup
├── game_actions/             # GUI action dispatch package
│   ├── app_actions.py        # Menu, navigation, persistence, and application handlers
│   ├── unit_actions.py       # Unit orders, stances, abilities, and carrier wing handlers
│   └── selection_actions.py  # Object selections and sidebar tab switch handlers
├── sidebar/                  # Sidebar payload generation package
│   ├── builder.py            # Sidebar data payload orchestrator
│   ├── order_formatting.py   # HTML order-text formatters for UI order queues
│   ├── panels_world.py       # System, Hex, Celestial Body, and Minefield panel builders
│   └── panels_unit.py        # Unit panel, tabs, and component dropdown builders
├── entities.py               # Game objects (Player, Units, Celestial Bodies, Stations)
├── galaxy.py                 # Galaxy generation and star system topology
├── gui.py                    # User interface management (Top bar, Sidebar, Menus)
├── input_processor.py        # Input handling and mouse/keyboard event processing
├── turn_processor.py         # Turn-based game logic and resolution engine
├── unit_editor_gui.py        # Custom Unit Designer GUI window
├── custom_unit_templates.py  # Runtime custom ship template manager and dynamic cost scaling
├── save_manager.py           # Game state serialization, save, and load manager
├── visibility.py             # Fog of War and sensor range visibility algorithms
├── events.py                 # Central event bus and game event definitions
├── unit_components/          # Modular unit component package
│   ├── base.py               # UnitComponent base class
│   ├── engines.py            # Engine and sublight components
│   ├── hyperdrive.py         # Hyperdrive components
│   ├── weapons.py            # Weapon components and turret definitions
│   ├── defenses.py           # Defense and shield components
│   ├── sensors.py            # Sensor range components
│   ├── hangar.py             # Ship hangar and strikecraft bay components
│   ├── abilities/            # Unit special abilities subpackage
│   └── ...                   # Additional components (Mining, Antimatter, Repair, Marines, Minelayer)
├── unit_orders/             # Unit command and order execution subpackage
├── unit_templates.py         # Baseline predefined unit configurations
├── constants.py              # Game constants, enums, colors, and resolution configuration
├── geometry.py               # Vector2D and Position mathematical utilities
├── hexgrid_utils.py          # Hexagonal grid math and coordinate utilities
├── pathfinding.py            # Navigation and pathfinding algorithms
├── renderer.py               # Graphics rendering controller
├── sector_utils.py           # Sector-specific rendering and coordinate utilities
├── utils.py                  # General utility functions
├── theme.json                # UI visual theme configuration
└── rendering/                # Specialized rendering modules
    ├── drawing_utils.py      # Basic shape and overlay drawing utilities
    ├── galaxy_renderer.py    # Galaxy view rendering (systems and wormholes)
    ├── main_menu_renderer.py # Main menu view rendering (titles, buttons, and about screen)
    ├── sector_renderer/      # Sector view rendering package
    │   ├── __init__.py                # Package exports (SectorViewRenderer facade & sub-renderers)
    │   ├── sector_renderer.py         # Sector view orchestrator facade delegating to sub-renderers
    │   ├── sector_grid_renderer.py    # Tactical grid, sector boundary, and spatial clipping math
    │   ├── sector_celestial_renderer.py # Stars, planets, moons, nebulae, storms, and particle fields
    │   ├── sector_entity_renderer.py   # Units, hull icons, health bars, minefields, and inhibition fields
    │   └── sector_overlay_renderer.py  # Selection brackets/box, range circles, order lines, and fog of war
    └── system_renderer.py    # System view rendering (hex grid and celestial bodies)
```

## Game Mechanics

### Movement System
- **Sublight Travel**: Move within sectors using engines
- **Hex Jumps**: Jump between sectors using basic hyperdrive
- **Wormhole Travel**: Inter-system jumps through wormholes via advanced hyperdrive
- **Hyperspace Inhibition**: Prevent enemy jumps with inhibitor fields

### Resource Economy
- **Credits**: Primary currency for transactions and upkeep
- **Metal**: Harvested from asteroids, used for construction
- **Crystal**: Harvested from comets, used for advanced technology
- **Antimatter**: Powers sub-light engines, hyperdrive jumps, and special abilities.
  Only units with the **Antimatter Harvester** component can generate new antimatter,
  and only while stationed near a star. All other units must be resupplied by
  transferring antimatter from another unit's storage.

### Combat & Warfare
- **Hull Points**: Unit durability based on hull size and component choices
- **Weapon Systems**: Dynamic range, fire rate, and damage scaling
- **Boarding Actions**: Commandeer enemy vessels using Marines
- **Minefields**: Tactical sector hex area denial

## Getting Started

1. **Install Python 3.8+** and the required dependencies
2. **Run the game** with `python game.py`
3. **Click "New Game"** to start a new campaign
4. **Explore the interface** by navigating between galaxy, system, and sector views
5. **Select units** and give them orders using the context menu system
6. **Design custom units** in the Unit Designer window
7. **Manage resources** and expand your empire across the galaxy

## License

All content and source code for this game are subject to the terms of the MIT License.