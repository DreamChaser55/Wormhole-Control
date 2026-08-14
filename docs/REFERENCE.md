# Wormhole Control — Reference Manual

This document contains in-depth reference data, data structures, catalogues, enums, and architecture notes for **Wormhole Control**.

---

## 1. Project Structure

```
Wormhole Control/
├── game.py                        # Central game loop facade and delegate controller
├── game_logging.py                # Custom application logging formatter and bootstrap
├── game_settings.py               # GameSettings dataclass, PlayerConfig, and campaign bootstrap parameters
├── game_setup.py                  # Initial world generation and starting fleet placement
├── game_camera.py                 # Sector view camera math, pan boundaries, and smooth zoom
├── economy.py                     # Player credit income and fleet upkeep calculations
├── entities.py                    # Core game objects (Player, Unit, CelestialBody, Minefield, etc.)
├── events.py                      # Central event bus and game event definitions
├── galaxy.py                      # Galaxy generation, star system topology, and sector hex grids
├── galaxy_utils.py                # Galaxy generation helper functions and placement math
├── order_system.py                # Order dispatch, route planning, and command validation engine
├── input_processor.py             # Mouse/keyboard event dispatch and selection logic
├── turn_processor.py              # Turn resolution engine (economy, movement, combat, orders, XP)
├── custom_unit_templates.py       # Custom ship design manager and dynamic hull cost calculations
├── unit_templates.py              # Baseline predefined unit template loader
├── save_manager.py                # Game state serialization, save, and load manager (JSON)
├── visibility.py                  # Sensor detection algorithms and dynamic fog of war tracking
├── constants.py                   # Global constants, enums, colors, and resolution config
├── geometry.py                    # Vector2D and Position mathematical utilities
├── hexgrid_utils.py               # Hexagonal grid math and axial coordinate utilities
├── pathfinding.py                 # A* pathfinding and navigation algorithms
├── renderer.py                    # Top-level graphics rendering orchestrator
├── sector_utils.py                # Sector coordinate conversion and rendering math
├── utils.py                       # General utility functions and HexCoord type aliases
├── theme.json                     # Base UI visual theme configuration
├── theme_scaled.json              # Dynamically generated resolution-scaled theme
├── pytest.ini                     # Pytest configuration (testpaths, pythonpath)
├── LICENSE                        # MIT License text
├── data/                          # Persistent JSON data files
│   ├── custom_unit_templates.json # Player-created custom ship designs
│   ├── spawn_rates.json           # Celestial object generation probability tables
│   ├── star_names.json            # Procedural star system name registry
│   └── unit_templates.json        # Predefined default unit designs
├── fonts/                         # Bundled TrueType font assets
│   ├── dejavu-sans/               # DejaVu Sans font family
│   └── noto-emoji/                # Noto Emoji font family
├── game_actions/                  # GUI action dispatch package
│   ├── __init__.py                # Package exports
│   ├── app_actions.py             # Menu, view navigation, and persistence actions
│   ├── selection_actions.py       # Object selections and sidebar tab handlers
│   └── unit_actions.py            # Unit orders, stances, abilities, and carrier wing actions
├── gui/                           # User interface management package
│   ├── __init__.py                # Package re-exports for GUI_Handler facade
│   ├── handler.py                 # GUI_Handler orchestrator, view transitions, and delegates
│   ├── theme_loader.py            # Scaled theme loading and font preloading
│   ├── layout_main_menu.py        # Main menu and About screen layout builders
│   ├── layout_ingame_menu.py      # Pause menu and load game dialog builders
│   ├── layout_new_game_wizard.py  # New Game setup wizard (players, galaxy, economy)
│   ├── layout_hud.py              # Top bar, resource labels, and turn indicator
│   ├── context_menu.py            # Right-click context menu construction and hit testing
│   ├── event_router.py            # GUI event routing and action payload generation
│   ├── dynamic_actions.py         # Dynamic sidebar button and dropdown action payloads
│   ├── text_layout.py             # Text wrapping and measurement utilities
│   ├── sidebar/                   # Sidebar UI sub-package
│   │   ├── __init__.py            # Package re-exports
│   │   ├── builder.py             # Sidebar data payload orchestrator
│   │   ├── order_formatting.py    # HTML order-text formatters for UI queues
│   │   ├── panels_unit.py         # Unit panel, tabs, and component dropdown builders
│   │   ├── panels_world.py        # System, Hex, Celestial Body, and Minefield panel builders
│   │   └── view.py                # Dynamic sidebar widget factory and accordion state
│   └── unit_editor_gui/           # Unit Designer GUI sub-package
│       ├── __init__.py            # Package re-exports for UnitEditorWindow
│       ├── window.py              # UnitEditorWindow orchestrator facade
│       ├── catalog.py             # Component catalogue, option lists, and descriptions
│       ├── component_state.py     # Component selection, toggling, and restriction logic
│       ├── cost_model.py          # Hull capacity calculations and capacity bar drawing
│       ├── event_handlers.py      # Pygame GUI event handling and dispatch logic
│       ├── layout.py              # UI layout orchestrator (columns 1, 2, 4)
│       ├── layout_details.py      # Column 3 dynamic component detail controls
│       ├── param_readers.py       # Parameter input parsing functions
│       ├── summary_view.py        # Design summary HTML box formatting
│       ├── template_io.py         # Template saving, loading, deletion, and widget sync
│       ├── turret_editor.py       # Turret list management and widget building
│       └── widget_factory.py      # UI widget construction helper functions
├── rendering/                     # Specialized rendering modules
│   ├── drawing_utils.py           # Basic shape and overlay drawing utilities
│   ├── galaxy_renderer.py         # Galaxy view rendering (systems and wormhole links)
│   ├── main_menu_renderer.py      # Main menu view rendering (titles and starfield)
│   ├── system_renderer.py         # System view rendering (hex grid and celestial bodies)
│   └── sector_renderer/           # Sector view rendering package
│       ├── __init__.py            # Package exports (SectorViewRenderer facade)
│       ├── sector_renderer.py     # Sector view orchestrator facade
│       ├── sector_grid_renderer.py # Tactical grid, boundaries, and spatial clipping
│       ├── sector_celestial_renderer.py # Stars, planets, moons, nebulae, and storms
│       ├── sector_entity_renderer.py # Units, hull icons, health bars, and minefields
│       └── sector_overlay_renderer.py # Selection boxes, range circles, and fog of war
├── saves/                         # Saved game files (*.json)
├── tests/                         # Automated test suite (55 test modules, 545 tests)
│   ├── __init__.py
│   └── test_*.py                  # Unit and integration test suites
├── unit_components/               # Modular unit component package
│   ├── __init__.py                # Package exports and registry
│   ├── base.py                    # UnitComponent base class
│   ├── antimatter.py              # AntimatterStorage and AntimatterHarvester components
│   ├── civilian_habitat.py        # CivilianHabitatComponent (economic sector bonus)
│   ├── cloaking.py                # CloakingDevice component (sensor stealth)
│   ├── colony.py                  # ColonyComponent (planetary colonization)
│   ├── commander.py               # Commander component (order queues and stances)
│   ├── constructor.py             # Constructor component (unit and station building)
│   ├── defenses.py                # Defenses component (armor, shields, point defense)
│   ├── enums.py                   # Component-related enums (Stance, Turret, Ability, etc.)
│   ├── hangar.py                  # HangarComponent (dockable ship carrier bays)
│   ├── inhibitor.py               # HyperspaceInhibitionFieldEmitter component
│   ├── marines.py                 # MarinesComponent (boarding and capture)
│   ├── minelayer.py               # MinelayerComponent (minefield deployment)
│   ├── mining.py                  # Mining, MetalRefinery, and CrystalRefinery components
│   ├── movement.py                # Engines and Hyperdrive movement components
│   ├── repair.py                  # RepairComponent (automated field repairs)
│   ├── sensors.py                 # Sensors component (short and long range detection)
│   ├── strikecraft.py             # StrikecraftWing and StrikecraftBay components
│   ├── weapons.py                 # Weapons and Turret combat components
│   └── abilities/                 # Special abilities subpackage
│       ├── __init__.py            # Package exports
│       ├── base.py                # AbilityDefinition and AbilityInstance base classes
│       ├── registry.py            # Ability registry and definition mapping
│       ├── component.py           # AbilityComponent unit integration
│       ├── adaptive_forcefield.py # Adaptive Forcefield ability
│       ├── capture_unit.py        # Capture Unit (boarding) ability
│       ├── cluster_warhead.py     # Cluster Warhead area damage ability
│       ├── designate_target.py    # Designate Target sensor tagging ability
│       ├── drain_antimatter.py    # Drain Antimatter ability
│       ├── ion_bolt.py            # Ion Bolt system-disable ability
│       ├── microjump.py           # Microjump tactical teleport ability
│       ├── missile_batteries.py   # Missile Batteries salvo ability
│       ├── repair_cloud.py        # Repair Cloud area healing ability
│       └── scan_for_minefields.py # Scan for Minefields area reveal ability
└── unit_orders/                   # Unit command and order execution subpackage
    ├── __init__.py                # Package exports
    ├── base.py                    # Order base class, OrderType, and OrderStatus enums
    ├── abilities.py               # UseAbilityOrder implementation
    ├── antimatter.py              # TransferAntimatter and ContinuousResupply orders
    ├── colony.py                  # Colonize and LoadColonists orders
    ├── combat.py                  # Attack, Defend, and Protect orders
    ├── construction.py            # ConstructOrder implementation
    ├── hangar.py                  # Dock, DeployUnit, and DeployAllWings orders
    ├── inhibitor.py               # ToggleInhibitorOrder implementation
    ├── minelayer.py               # LayMinefieldOrder implementation
    ├── mining.py                  # Mine, UnloadResources, and ContinuousMine orders
    ├── movement.py                # Move and ReachWaypoint orders
    ├── patrol.py                  # PatrolOrder implementation
    └── repair.py                  # RepairOrder implementation
```

---

## 2. Hull Sizes

Wormhole Control features 6 hull classes (`HullSize`). Each hull size sets the capacity budget for installed components, baseline durability, minimum antimatter capacity, and baseline construction costs.

| Hull Size | Enum Value | Hull Capacity | Base HP | Min Antimatter Capacity | Base Build Cost (Credits) | Base Build Time (Turns) | Upkeep Cost / Turn |
|---|---|---|---|---|---|---|---|
| `STRIKECRAFT_WING` | 1 | 5.0 | 40 | 40.0 | 50 | 1 | 0.01 × HP |
| `TINY` | 2 | 10.0 | 20 | 60.0 | 100 | 3 | 0.01 × HP |
| `SMALL` | 3 | 25.0 | 50 | 80.0 | 250 | 6 | 0.01 × HP |
| `MEDIUM` | 4 | 50.0 | 100 | 100.0 | 500 | 10 | 0.01 × HP |
| `LARGE` | 5 | 100.0 | 200 | 150.0 | 1000 | 15 | 0.01 × HP |
| `HUGE` | 6 | 200.0 | 400 | 200.0 | 2000 | 20 | 0.01 × HP |

*Note: Total unit build cost is `Base Build Cost + (Used Hull Capacity × 30 Credits)`. Total build time is `Base Build Time + (Used Hull Capacity / 10 Turns)`.*

---

## 3. Component Catalogue

The Unit Designer (`gui/unit_editor_gui/catalog.py: COMPONENT_ROWS`) provides **21 selectable component rows**. In addition, all active units are equipped with a `Commander` component (order management and stances).

| # | Component Key | Label | Cost Type | Default Cost | Hull Size Restrictions / Notes |
|---|---|---|---|---|---|
| 1 | `has_engine` | Engines | Dynamic | 5.0 | Available on all hull sizes. Dynamic cost scales with sublight speed and hull size. |
| 2 | `has_antimatter_storage` | Antimatter Storage | Dynamic | 5.0 | Available on all hull sizes. Dynamic cost scales with additional storage capacity. |
| 3 | `has_antimatter_harvester` | Antimatter Harvester | Fixed | 15.0 | Forbidden on `STRIKECRAFT_WING` and `TINY`. Harvests antimatter near stars. |
| 4 | `has_hyperdrive` | Hyperdrive | Dynamic | 5.0 | Forbidden on `STRIKECRAFT_WING`. Basic hyperdrive available on `TINY`+; Advanced hyperdrive requires `SMALL`+. |
| 5 | `has_weapon_bays` | Weapons | Dynamic | 10.0 | Available on all hull sizes. Dynamic cost scales with turret count, damage, range, and fire rate. |
| 6 | `has_defenses` | Defenses | Dynamic | 10.0 | Available on all hull sizes. Dynamic cost scales with Armor, Shields, and Point Defense ratings. |
| 7 | `has_constructor_component` | Constructor | Fixed | 15.0 | Forbidden on `STRIKECRAFT_WING` and `TINY`. Enables building space stations and units. |
| 8 | `has_repair_component` | Repair | Dynamic | 15.0 | Forbidden on `STRIKECRAFT_WING` and `TINY`. Dynamic cost scales with repair rate. |
| 9 | `has_colony_component` | Colony | Fixed | 10.0 | Forbidden on `STRIKECRAFT_WING` and `TINY`. Enables planetary colonization. |
| 10 | `has_civilian_habitat_component` | Civilian Habitat | Fixed | 15.0 | Forbidden on `STRIKECRAFT_WING` and `TINY`. Generates +50 credits/turn in colonized sectors. |
| 11 | `has_mining_component` | Mining | Dynamic | 10.0 | Available on all hull sizes. Dynamic cost scales with mining rate and cargo capacity. |
| 12 | `has_metal_refinery_component` | Metal Refinery | Fixed | 20.0 | Forbidden on `STRIKECRAFT_WING` and `TINY`. Refines mined ore into metal. |
| 13 | `has_crystal_refinery_component` | Crystal Refinery | Fixed | 20.0 | Forbidden on `STRIKECRAFT_WING` and `TINY`. Refines mined crystals into usable crystal stock. |
| 14 | `has_hangar` | Hangar | Dynamic | 20.0 | Restricted to `LARGE` and `HUGE` hulls only. Dynamic cost scales with hangar slot capacity. |
| 15 | `has_strikecraft_bay` | Strikecraft Bay | Dynamic | 15.0 | Requires `MEDIUM`, `LARGE`, or `HUGE` hull. Dynamic cost scales with strikecraft wing slots. |
| 16 | `has_inhibitor` | Inhibitor Field | Dynamic | 20.0 | Requires `MEDIUM`, `LARGE`, or `HUGE` hull. Dynamic cost scales with inhibition field radius. |
| 17 | `has_ability_component` | Abilities | Dynamic | 10.0 | Forbidden on `STRIKECRAFT_WING` and `TINY`. Dynamic cost scales with number of equipped abilities. |
| 18 | `has_sensors` | Sensors | Dynamic | 2.0 | Available on all hull sizes. Dynamic cost scales with short-range radius and long-range hex coverage. |
| 19 | `has_minelayer_component` | Minelayer | Fixed | 15.0 | Forbidden on `STRIKECRAFT_WING` and `TINY`. Deploys tactical minefields. |
| 20 | `has_marines_component` | Marines | Dynamic | 10.0 | Forbidden on `STRIKECRAFT_WING`. Dynamic cost scales with embarked marine count. |
| 21 | `has_cloaking_device` | Cloaking Device | Fixed | 10.0 | Forbidden on `STRIKECRAFT_WING`. Hides unit from long-range inter-sector sensors while active. |
| — | *Always Present* | Commander | — | — | Core component present on all ships; manages order queues and combat stances. |

---

## 4. Special Abilities

There are **10 special abilities** in the game, registered in `unit_components/abilities/registry.py`. Each ability requires a specific component installed on the unit design.

| Ability | Cooldown (Turns) | Duration (Turns) | Range (px) | AM Cost | Required Component | Target Type | Description |
|---|---|---|---|---|---|---|---|
| **Adaptive Forcefield** | 8 | 3 | 0 (self) | 20 | Defenses (`has_defenses`) | None (Self) | Temporarily raises defensive mitigation against incoming attacks. |
| **Cluster Warhead** | 5 | 0 | 500.0 | 30 | Weapons (`has_weapon_bays`) | Position | Detonates an area-of-effect cluster warhead at the designated coordinate. |
| **Designate Target** | 6 | 4 | 450.0 | 15 | Sensors (`has_sensors`) | Unit | Tags an enemy unit with sensor lock, increasing fleet attack accuracy against it. |
| **Ion Bolt** | 7 | 3 | 400.0 | 25 | Weapons (`has_weapon_bays`) | Unit | Fires an electromagnetic bolt that disables the target's sublight engines and weapons. |
| **Missile Batteries** | 10 | 4 | 0 (self) | 40 | Weapons (`has_weapon_bays`) | None (Self) | Deploys autonomous missile platforms that fire coordinated salvos at nearby hostiles. |
| **Repair Cloud** | 8 | 4 | 350.0 | 35 | Repair (`has_repair_component`) | None (Self) | Emits an expanding nanite cloud that continuously repairs adjacent friendly units. |
| **Capture Unit** | 10 | 0 | 100.0 | 40 | Marines (`has_marines_component`) | Unit | Launches an armed marine boarding party to commandeer and seize control of an enemy vessel. |
| **Drain Antimatter** | 6 | 0 | 300.0 | 0 | Antimatter Storage (`has_antimatter_storage`) | Unit | Siphons antimatter fuel directly from an enemy unit's storage tanks into your own. |
| **Microjump** | 5 | 0 | 600.0 | 25 | Hyperdrive (`has_hyperdrive`) | Position | Executes an instant tactical micro-hyperjump to any target location within range. |
| **Scan for Minefields** | 6 | 0 | 1500.0 | 35 | Sensors (`has_sensors`) | None (Self) | Emits a high-frequency sensor sweep that permanently reveals all enemy minefields within range. |

---

## 5. Order Types

The `OrderType` enum (`unit_orders/base.py`) defines **21 order types** that can be issued to units:

| Order Type | Description |
|---|---|
| `REACH_WAYPOINT` | Direct movement to a single waypoint (system, hex, position). Sub-order spawned by `MOVE`. |
| `MOVE` | High-level multi-leg movement across positions, hexes, or star systems via wormholes. |
| `PATROL` | Repeatedly patrols a looping sequence of waypoint coordinates. |
| `ATTACK` | Moves into weapon range and engages a designated enemy unit until destroyed. |
| `DEFEND` | Holds position at a target location or guards a friendly unit against incoming hostiles. |
| `PROTECT` | Escorts a friendly unit, matching its movement and intercepting hostile attackers. |
| `TOGGLE_INHIBITOR` | Activates or deactivates the ship's hyperspace inhibition field emitter. |
| `COLONIZE` | Disembarks colonists from a colony ship to establish a settlement on a habitable body. |
| `LOAD_COLONISTS` | Embarks population from a colonized celestial body onto a colony transport. |
| `CONSTRUCT` | Deploys a constructor to build a new space station, structure, or starship. |
| `REPAIR` | Moves to and restores hull integrity on a damaged friendly unit. |
| `MINE` | Extracts raw metal from an asteroid or raw crystal from a comet. |
| `UNLOAD_RESOURCES` | Transports mined raw ore or crystals to a compatible refinery station. |
| `DOCK` | Lands a dockable vessel into a carrier's hangar bay. |
| `DEPLOY_UNIT` | Launches a specific docked vessel from a carrier's hangar bay. |
| `DEPLOY_ALL_WINGS` | Scrambles all carrier strikecraft wings (fighters/bombers) into active combat. |
| `USE_ABILITY` | Activates an equipped special ability on self, a target position, or a target unit. |
| `CONTINUOUS_MINE` | Automated cycle: mines raw resources until cargo is full, unloads at nearest refinery, and repeats. |
| `TRANSFER_ANTIMATTER` | Transfers a quantity of stored antimatter fuel to a friendly recipient ship. |
| `CONTINUOUS_RESUPPLY` | Automated harvester loop: charges antimatter at a star, seeks low-fuel friendly units, refuels them, and repeats. |
| `LAY_MINEFIELD` | Deploys an anti-ship or anti-strikecraft minefield at the unit's current position. |

---

## 6. Universe Objects & Celestial Bodies

### 6.1 Central Stars (`StarType`)
Every star system contains a central star with a unique antimatter harvesting rate multiplier (`constants.py: STAR_HARVEST_MULTIPLIERS`):

| Star Type | Enum Member | Harvest Multiplier | Color (RGB) | Inhibition Radius |
|---|---|---|---|---|
| **Pulsar** | `PULSAR` | **2.5×** | (225, 110, 255) | 2700.0 |
| **Blue Giant** | `BLUE_GIANT` | **2.0×** | (173, 216, 255) | 2700.0 |
| **Neutron Star** | `NEUTRON_STAR` | **1.8×** | (200, 245, 255) | 2700.0 |
| **Yellow Giant** | `YELLOW_GIANT` | **1.5×** | (255, 195, 0) | 2700.0 |
| **Red Giant** | `RED_GIANT` | **1.3×** | (235, 50, 35) | 2700.0 |
| **G-Type (Sol-like)** | `G_TYPE` | **1.0×** (Baseline) | (255, 235, 120) | 2700.0 |
| **White Dwarf** | `WHITE_DWARF` | **0.8×** | (240, 248, 255) | 2700.0 |
| **Protostar** | `PROTOSTAR` | **0.7×** | (255, 140, 0) | 2700.0 |
| **Red Dwarf** | `RED_DWARF` | **0.5×** | (255, 127, 80) | 2700.0 |
| **Brown Dwarf** | `BROWN_DWARF` | **0.3×** | (160, 82, 45) | 2700.0 |
| **Black Hole** | `BLACK_HOLE` | **0.1×** | (75, 35, 100) | 2700.0 |

### 6.2 Planets & Colonizable Bodies
- **Planets (`PlanetType`)**: 9 planetary classes (`TERRAN`, `DESERT`, `VOLCANIC`, `ICE`, `BARREN`, `FERROUS`, `GREENHOUSE`, `OCEANIC`, `GAS_GIANT`). Colonizable planets support up to **100.0 population** with a baseline growth rate of **2.0% per turn**. Inhibition radius: 2400.0.
- **Moons (`Moon`)**: Colonizable satellites supporting up to **50.0 population** with a growth rate of **1.0% per turn**. Inhibition radius: 1800.0.
- **Colonizable Asteroids (`ColonizableAsteroid`)**: Habitable asteroid outposts supporting up to **20.0 population** with a growth rate of **0.5% per turn**. Inhibition radius: 1200.0.

### 6.3 Resource & Spatial Phenomena
- **Metal Asteroids (`MetalAsteroid`)**: Non-colonizable mineral bodies providing a sustainable source of raw **Metal** (yield: 10.0/turn). Inhibition radius: 1200.0.
- **Comets (`Comet`)**: Pristine icy bodies yielding raw **Crystal** (yield: 10.0/turn). Inhibition radius: 600.0.
- **Wormholes (`Wormhole`)**: Natural spacetime conduits linking star systems. Traversal requires an Advanced Hyperdrive. Inhibition radius: 1500.0.
- **Asteroid Fields (`AsteroidField`)**: Dense clusters of rocky fragments. Inhibition radius: 900.0.
- **Ice Fields (`IceField`)**: Dense fields of volatile ice particles. Inhibition radius: 600.0.
- **Debris Fields (`DebrisField`)**: Remnants of past orbital battles or derelict structures.
- **Nebulae (`Nebula`)**: Vast interstellar clouds with 4 distinct elemental subtypes (`HYDROGEN`, `NITROGEN`, `OXYGEN`, `DUST`).
- **Space Storms (`Storm`)**: Hazardous energetic disturbances with 3 environmental subtypes (`PLASMA`, `MAGNETIC`, `RADIATION`).

---

## 7. Enums Quick Reference

### Unit Stances (`UnitStance` — 5 total)
- `DO_NOTHING`: Hold fire and ignore hostile units unless directly ordered.
- `ATTACK_WEAPON_RANGE`: Engage hostile units that enter weapon range.
- `ATTACK_SAME_SECTOR`: Intercept and engage any hostile unit detected in the same sector hex.
- `ATTACK_INTRA_SYSTEM_JUMP_RANGE`: Jump to engage hostile units in adjacent sectors within basic hyperdrive range.
- `ATTACK_SAME_SYSTEM`: Jump to engage hostile units anywhere within the star system.

### Turret Types & Variants (`TurretType` × `TurretVariant` — 3 × 3)
- **Turret Types**:
  - `MASS_DRIVER`: Kinetic projectile weaponry with solid damage and velocity.
  - `BEAM`: Directed energy beam weaponry delivering instantaneous hit-scan damage.
  - `MISSILE`: Guided ordnance with extended range and explosive impact.
- **Turret Variants**:
  - `STANDARD`: Balanced profile with standard range, damage, and cooldown.
  - `ANTI_STRIKECRAFT`: High rate of fire and tracking speed, optimized against strikecraft.
  - `LONG_RANGE`: Extended engagement range with increased cycle cooldown.

### Minefield Types (`MinefieldType` — 2 total)
- `ANTI_SHIP`: Heavy proximity charges engineered to destroy capital ships and frigates.
- `ANTI_STRIKECRAFT`: High-density fragmentation charges designed to shred incoming strikecraft wings.

### Hyperdrive Types (`HyperdriveType` — 2 total)
- `BASIC`: Enables sublight travel and intra-system hex jumps between adjacent sector hexes.
- `ADVANCED`: Enables intra-system hex jumps and inter-system wormhole conduit travel.

### Strikecraft Wing Types (`WingType` — 2 total)
- `FIGHTER`: Fast dogfighter wings designed for air superiority and point-defense interception.
- `BOMBER`: Heavy torpedo craft designed to deliver devastating payload strikes against capital hulls.

---

## 8. Architecture & Subsystems

```
┌─────────────────────────────────────────────────────────────┐
│                         game.py                             │
│                  (Central Loop & Facade)                    │
└───────┬───────────────────┬─────────────────────┬───────────┘
        │                   │                     │
        ▼                   ▼                     ▼
┌──────────────┐    ┌───────────────┐    ┌────────────────────┐
│   events.py  │    │  gui/handler  │    │ renderer.py        │
│  (Event Bus) │    │  (UI Facade)  │    │ (Render Pipeline)  │
└───────┬──────┘    └───────┬───────┘    └────────┬───────────┘
        │                   │                     │
        ▼                   ▼                     ▼
┌──────────────┐    ┌───────────────┐    ┌────────────────────┐
│ order_system │    │ gui/sidebar   │    │ rendering/sector_  │
│ (Order Queue)│    │ gui/unit_edit │    │ renderer/ (Facade) │
└───────┬──────┘    └───────────────┘    └────────────────────┘
        │
        ▼
┌──────────────┐
│ turn_process │
│ (Resolution) │
└──────────────┘
```

- **Event Bus (`events.py`)**: Decouples input handling, order queuing, and UI notifications using a lightweight publish/subscribe pattern.
- **Order System (`order_system.py`)**: Manages hierarchical order lifecycles (parent orders and dynamically generated sub-orders), route pathfinding, jump safety checks, and continuous loops.
- **Visibility Service (`visibility.py`)**: Computes sector-by-sector and in-hex sensor horizons. Generates fog-of-war masks and persists last-known sector intel per player.
- **GUI & Renderer Packages (`gui/`, `rendering/`)**: Strict facade pattern isolating UI widget hierarchies and layout managers from pygame-ce rendering loops and mathematical spatial transformations.
- **Resolution Independence (`theme_loader.py`, `TEXT_SCALE`, `theme_scaled.json`)**: Dynamically computes theme scale ratios to ensure clean font and layout rendering across diverse desktop resolutions.
