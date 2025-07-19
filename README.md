# Wormhole Control

**Wormhole Control** is a 2D turn-based 4X space strategy game prototype written in Python using Pygame and pygame_gui. The game features a large-scale universe where players manage space ships across a galaxy of star systems connected by wormholes. Each star system contains a hexagonal grid of sectors.

## Features

### Core Gameplay
- **Turn-based Strategy**: Classic 4X gameplay (eXplore, eXpand, eXploit, eXterminate)
- **Multi-scale Universe**: Navigate between galaxy view, system view, and sector view
- **Wormhole Network**: Faster-than-light travel between star systems via wormhole connections
- **Resource Management**: Manage Credits, Metal, and Crystal resources
- **Player vs AI**: Support for multiple players (human and AI)

### Space Units & Components
- **Modular Ship Design**: Units built with customizable components
- **Hull Sizes**: Five hull classes (Tiny, Small, Medium, Large, Huge) with different capacities
- **Unit Components**:
  - **Engines**: Enable sublight movement within sectors
  - **Hyperdrives**: Basic (intra-system jumps) and Advanced (inter-system jumps via wormholes)
  - **Weapons**: Combat systems with various turret types
  - **Inhibitors**: Hyperspace inhibition field generators (prevents enemy jumps)
  - **Colony Component**: For planetary colonization
  - **Constructor Component**: For building stations and structures

### Celestial Objects
- **Stars**: Various types (G-Type, Red Dwarf, White Dwarf, Neutron Star, Pulsar, Black Hole, etc.)
- **Planets**: Nine planet types (Terran, Desert, Volcanic, Ice, Gas Giant, etc.)
- **Colonizable Bodies**: Planets, Moons (Crystal source), Asteroids (Metal source)
- **Space Phenomena**: Nebulae, Storms, Comets, Asteroid Fields, Debris Fields

### Advanced Systems
- **Complex Orders System**: Queue multiple commands for units
- **Population Growth**: Dynamic population mechanics for colonies
- **Pathfinding**: Intelligent navigation in the wormhole network
- **Turn Processing**: Comprehensive turn-based game state management
- **GUI System**: Rich user interface with context menus, sidebar, and dynamic content

## Installation & Requirements

### Dependencies
- **Python 3.7+**
- **pygame**: Core game engine
- **pygame_gui**: User interface framework

#### Install dependencies:
```bash
pip install pygame pygame_gui
```

## Game Controls & Interface

### View Navigation
- **Galaxy View**: Overview of all star systems and wormhole connections
- **System View**: Hexagonal grid showing all sectors within a star system
- **Sector View**: Detailed view of individual sector with celestial bodies and units

### Unit Management
- **Selection**: Click to select units and objects
- **Multiple Selection**: Drag selection box or Ctrl+click
- **Context Menus**: Right-click for available actions
- **Order Queue**: View and manage pending unit orders
- **Component Control**: Toggle inhibitor fields, manage weapons systems

### Turn System
- **End Turn**: Process all player actions and advance to next player
- **Resource Display**: Real-time tracking of Credits, Metal, Crystal
- **Player Indicator**: Visual display of current player and color

## Project Structure

```
Wormhole Control/
├── game.py              # Main game class and entry point
├── entities.py          # Game objects (Player, Units, Celestial Bodies)
├── galaxy.py            # Galaxy generation and star system management
├── gui.py               # User interface management
├── input_processor.py   # Input handling and event processing
├── turn_processor.py    # Turn-based game logic processing
├── unit_components.py   # Modular unit component system
├── unit_orders.py       # Unit command and order system
├── unit_templates.py    # Predefined unit configurations
├── constants.py         # Game constants and configuration
├── geometry.py          # Mathematical utilities (vectors, positions)
├── hexgrid_utils.py     # Hexagonal grid calculations
├── pathfinding.py       # Navigation and pathfinding algorithms
├── renderer.py          # Graphics rendering system
├── sector_utils.py      # Sector-specific utilities
├── utils.py             # General utility functions
├── theme.json           # UI theme configuration
└── rendering/           # Specialized rendering modules
    ├── drawing_utils.py     # Basic shape drawing utilities
    ├── galaxy_renderer.py   # Galaxy view rendering (systems and wormholes)
    ├── system_renderer.py   # System view rendering (hex grid and celestial bodies)
    └── sector_renderer.py   # Sector view rendering (detailed display of objects inside a sector)
```

## Game Mechanics

### Movement System
- **Sublight Travel**: Move within sectors using engines
- **Hex Jumps**: Jump between sectors using basic hyperdrive
- **Wormhole Travel**: Inter-system jumps through wormholes via advanced hyperdrive
- **Hyperspace Inhibition**: Prevent enemy jumps with inhibitor fields

### Resource Economy
- **Credits**: Primary currency for transactions
- **Metal**: Harvested from asteroids, used for construction
- **Crystal**: Harvested from moons, used for advanced technology

### Combat & Warfare
- **Hull Points**: Unit durability based on hull size
- **Weapon Systems**: Various turret types with different capabilities

## Development

### Debug Features
- Debug mode available via `DEBUG = True` in constants.py
- Performance profiling via `PROFILE = True`

## Getting Started

1. **Install Python 3.7+** and the required dependencies
2. **Run the game** with `python game.py`
3. **Click "New Game"** to start a new campaign
4. **Explore the interface** by navigating between galaxy, system, and sector views
5. **Select units** and give them orders using the context menu system
6. **Manage resources** and expand your empire across the galaxy

## License

All content and source code for this game are subject to the terms of the MIT License.