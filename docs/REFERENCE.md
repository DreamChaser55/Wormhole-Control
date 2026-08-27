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
├── input_processor/               # Mouse/keyboard event dispatch and selection package
│   ├── __init__.py                # Package facade and public re-exports
│   ├── processor.py               # InputProcessor main orchestrator class
│   ├── hover_tracker.py           # Spatial entity hover detection (galaxy, system, sector)
│   ├── mouse_handler.py           # Mouse click dispatch, box selection, ability targeting
│   ├── keyboard_handler.py        # Keyboard camera panning and global hotkeys
│   ├── context_menu_builder.py    # Dynamic right-click context menu and submenu generators
│   └── context_actions.py         # Context menu action event dispatchers
├── order_system.py                # Order dispatch, route planning, and command validation engine
├── turn_processor.py              # Turn resolution engine (economy, movement, combat, orders, XP)
├── custom_unit_templates.py       # Custom ship design manager and dynamic hull cost calculations
├── unit_templates.py              # Baseline predefined unit template loader
├── save_manager.py                # Game state serialization, save, and load manager (JSON)
├── visibility.py                  # Sensor detection algorithms and dynamic fog of war tracking
├── constants.py                   # Global constants, enums, colors, and resolution config
├── geometry.py                    # Vector, Position, Circle geometry, intersection math, and avoidance pathfinding
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
├── tests/                         # Automated test suite
│   ├── __init__.py
│   └── test_*.py                  # Unit and integration test suites
├── unit_components/               # Modular unit component package
│   ├── __init__.py                # Package exports and registry
│   ├── base.py                    # UnitComponent base class
│   ├── antimatter.py              # AntimatterStorage and AntimatterHarvester components
│   ├── civilian_habitat.py        # CivilianHabitatComponent (economic sector bonus)
│   ├── orbital_defense.py         # OrbitalDefenseComponent (AoE tactical attack & defense aura)
│   ├── cloaking.py                # CloakingDevice component (sensor stealth)
│   ├── colony.py                  # ColonyComponent (planetary colonization)
│   ├── commander.py               # Commander component (order queues and stances)
│   ├── constructor.py             # Constructor component (unit and station building)
│   ├── defenses.py                # Defenses component (armor, shields, point defense)
│   ├── enums.py                   # Component-related enums (Stance, Turret, Ability, etc.)
│   ├── hangar.py                  # HangarComponent (dockable ship carrier bays)
│   ├── inhibitor.py               # HyperspaceInhibitionFieldEmitter component
│   ├── intelligence.py            # IntelligenceComponent and Agent (espionage and counter-intelligence)
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
    ├── combat.py                  # Attack and Protect orders
    ├── construction.py            # ConstructOrder implementation
    ├── defend.py                  # DefendOrder implementation (positional and perimeter defense)
    ├── hangar.py                  # Dock, DeployUnit, and DeployAllWings orders
    ├── inhibitor.py               # ToggleInhibitorOrder implementation
    ├── intelligence.py            # InfiltrateUnit, InfiltratePlanet, RelocateAgent, Sabotage, CISweep, EliminateAgent, ExtractAgent orders
    ├── minelayer.py               # LayMinefieldOrder implementation
    ├── mining.py                  # Mine, UnloadResources, and ContinuousMine orders
    ├── movement.py                # Move and ReachWaypoint orders
    ├── patrol.py                  # PatrolOrder implementation
    ├── refit.py                   # RefitOrder implementation (field component addition/removal)
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

The Unit Designer (`gui/unit_editor_gui/catalog.py: COMPONENT_ROWS`) provides **22 selectable component rows**. In addition, all active units are equipped with a `Commander` component (order management and stances).

| # | Component Key | Label | Cost Type | Default Cost | Hull Size Restrictions / Notes |
|---|---|---|---|---|---|
| 1 | `has_engine` | Engines | Dynamic | 5.0 | Available on all hull sizes. Dynamic cost scales with sublight speed and hull size. |
| 2 | `has_antimatter_storage` | Antimatter Storage | Dynamic | 5.0 | Available on all hull sizes. Dynamic cost scales with additional storage capacity. |
| 3 | `has_antimatter_harvester` | Antimatter Harvester | Fixed | 15.0 | Forbidden on `STRIKECRAFT_WING` and `TINY`. Harvests antimatter near stars. |
| 4 | `has_hyperdrive` | Hyperdrive | Dynamic | 5.0 | Forbidden on `STRIKECRAFT_WING`. Basic hyperdrive available on `TINY`+; Advanced hyperdrive requires `SMALL`+. |
| 5 | `has_weapon_bays` | Weapons | Dynamic | 10.0 | Available on all hull sizes. Dynamic cost scales with turret count, damage, range, and fire rate. |
| 6 | `has_defenses` | Defenses | Dynamic | 10.0 | Available on all hull sizes. Dynamic cost scales with Armor, Shields, and Point Defense ratings. |
| 7 | `has_constructor_component` | Constructor | Fixed | 15.0 | Forbidden on `STRIKECRAFT_WING` and `TINY`. Enables building space stations and units, as well as field refitting (adding or removing components) on friendly and allied vessels. |
| 8 | `has_repair_component` | Repair | Dynamic | 15.0 | Forbidden on `STRIKECRAFT_WING` and `TINY`. Dynamic cost scales with repair rate. Repairs friendly and allied ships. |
| 9 | `has_colony_component` | Colony | Fixed | 10.0 | Forbidden on `STRIKECRAFT_WING` and `TINY`. Enables planetary colonization and loading colonists from friendly/allied worlds. |
| 10 | `has_civilian_habitat_component` | Civilian Habitat | Fixed | 15.0 | Forbidden on `STRIKECRAFT_WING` and `TINY`. Generates +50 credits/turn in colonized sectors up to the colony's supported habitat limit (base 1, +1 per 25 population). |
| 11 | `has_orbital_defense_component` | Orbital Defense | Fixed | 20.0 | Forbidden on `STRIKECRAFT_WING` and `TINY`. Projects an area-of-effect aura (500 radius) providing +20% weapon damage and +20% defense mitigation to friendly and allied ships in range in friendly/allied colonized sectors up to the colony's supported orbital defense limit (base 1, +1 per 25 population). Overlapping auras stack additively. |
| 12 | `has_trade_component` | Trade Module | Fixed | 10.0 | Forbidden on `STRIKECRAFT_WING` and `TINY`. **Requires Engines (`has_engine`)**. Enables trade ships to earn credits by traveling between active Civilian Habitat modules in different sectors, with payout scaling with distance between sectors. |
| 13 | `has_mining_component` | Mining | Dynamic | 10.0 | Available on all hull sizes. Dynamic cost scales with mining rate and cargo capacity. |
| 14 | `has_metal_refinery_component` | Metal Refinery | Fixed | 20.0 | Forbidden on `STRIKECRAFT_WING` and `TINY`. Refines mined ore into metal. |
| 15 | `has_crystal_refinery_component` | Crystal Refinery | Fixed | 20.0 | Forbidden on `STRIKECRAFT_WING` and `TINY`. Refines mined crystals into usable crystal stock. |
| 16 | `has_hangar` | Hangar | Dynamic | 20.0 | Restricted to `LARGE` and `HUGE` hulls only. Dynamic cost scales with hangar slot capacity. |
| 17 | `has_strikecraft_bay` | Strikecraft Bay | Dynamic | 15.0 | Requires `MEDIUM`, `LARGE`, or `HUGE` hull. Dynamic cost scales with strikecraft wing slots. |
| 18 | `has_inhibitor` | Inhibitor Field | Dynamic | 20.0 | Requires `MEDIUM`, `LARGE`, or `HUGE` hull. Dynamic cost scales with inhibition field radius. |
| 19 | `has_ability_component` | Abilities | Dynamic | 10.0 | Forbidden on `STRIKECRAFT_WING` and `TINY`. Dynamic cost scales with number of equipped abilities. |
| 20 | `has_sensors` | Sensors | Dynamic | 2.0 | Available on all hull sizes. Dynamic cost scales with short-range radius and long-range hex coverage. Coverage is shared across all allied players. |
| 21 | `has_minelayer_component` | Minelayer | Fixed | 15.0 | Forbidden on `STRIKECRAFT_WING` and `TINY`. Deploys tactical minefields that ignore friendly and allied vessels. |
| 22 | `has_marines_component` | Marines | Dynamic | 10.0 | Forbidden on `STRIKECRAFT_WING`. Dynamic cost scales with embarked marine count. |
| 23 | `has_cloaking_device` | Cloaking Device | Dynamic | 10.0 / 30.0 | Forbidden on `STRIKECRAFT_WING`; `ADVANCED` requires at least `SMALL` hull. **Basic** (10 Hull, 5 AM/turn, 300 credits) hides single unit from long-range sensors; **Advanced** projects an area-of-effect stealth field hiding friendly and allied units within its radius, with hull cost ($R/16.6667$), credit build cost contribution ($\text{Hull} \times 30$), and antimatter drain ($R \times 0.04\text{ AM/turn}$) scaling dynamically with area radius $R$ (baseline 30 Hull, 900 credits, 20 AM/turn at 500 radius). |
| 24 | `has_intelligence_component` | Intelligence | Dynamic | 10.0 | Forbidden on `STRIKECRAFT_WING` and `TINY`. Dynamic cost scales with agent capacity (5.0 hull per agent, default 2 agents). Optional Counter-Intelligence suite (+10.0 hull, +300 credits) enables active sector counter-espionage sweeps (activated via the component sidebar panel; cost: 100 credits, 25 AM, 3-turn cooldown) to protect friendly and allied assets and eliminate discovered enemy agents. |
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
| **Microjump** | 5 | 0 | 0 (sector) | 25 | Hyperdrive (`has_hyperdrive`) | Position | Executes an instant tactical micro-hyperjump to any target location in the same sector. |
| **Scan for Minefields** | 6 | 0 | 1500.0 | 35 | Sensors (`has_sensors`) | None (Self) | Emits a high-frequency sensor sweep that permanently reveals all enemy minefields within range. |

---

## 5. Order Types

The `OrderType` enum (`unit_orders/base.py`) defines **29 order types** that can be issued to units:

| Order Type | Description |
|---|---|
| `REACH_WAYPOINT` | Direct movement to a single waypoint (system, hex, position). Sub-order spawned by `MOVE`. |
| `MOVE` | High-level multi-leg movement across positions, hexes, or star systems via wormholes. |
| `PATROL` | Repeatedly patrols a looping sequence of waypoint coordinates. |
| `ATTACK` | Moves into weapon range and engages a designated enemy unit until destroyed. |
| `DEFEND` | Holds position at a target location or guards a friendly/allied unit against incoming hostiles. |
| `PROTECT` | Escorts a friendly or allied unit, matching its movement and intercepting hostile attackers. |
| `TOGGLE_INHIBITOR` | Activates or deactivates the ship's hyperspace inhibition field emitter. |
| `COLONIZE` | Disembarks colonists from a colony ship to establish a settlement on a habitable body. |
| `LOAD_COLONISTS` | Embarks population from a friendly or allied colonized celestial body onto a colony transport. |
| `CONSTRUCT` | Deploys a constructor to build a new space station, structure, or starship. |
| `REFIT_UNIT` | Deploys a constructor to install new components or decommission existing components on a friendly or allied vessel in the field. |
| `REPAIR` | Moves to and restores hull integrity on a damaged friendly or allied unit. |
| `MINE` | Extracts raw metal from an asteroid or raw crystal from a comet. |
| `UNLOAD_RESOURCES` | Transports mined raw ore or crystals to a compatible refinery station. |
| `DOCK` | Lands a dockable vessel into a carrier's hangar bay. |
| `DEPLOY_UNIT` | Launches a specific docked vessel from a carrier's hangar bay. |
| `DEPLOY_ALL_WINGS` | Scrambles all carrier strikecraft wings (fighters/bombers) into active combat. |
| `USE_ABILITY` | Activates an equipped special ability on self, a target position, or a target unit. |
| `CONTINUOUS_MINE` | Automated cycle: mines raw resources until cargo is full, unloads at nearest refinery, and repeats. |
| `TRANSFER_ANTIMATTER` | Transfers a quantity of stored antimatter fuel to a friendly or allied recipient ship. |
| `CONTINUOUS_RESUPPLY` | Automated harvester loop: charges antimatter at a star, seeks low-fuel friendly or allied units, refuels them, and repeats. |
| `LAY_MINEFIELD` | Deploys an anti-ship or anti-strikecraft minefield at the unit's current position. |
| `TRADE` | Travels to a designated active Civilian Habitat in another sector and conducts trade, earning credits based on distance. |
| `CONTINUOUS_TRADE` | Automated merchant cycle: travels between active Civilian Habitat modules in different sectors to maximize trade revenue continuously. |
| `INFILTRATE_UNIT` | Deploys a covert agent onto an enemy vessel within operational range (500 px). |
| `INFILTRATE_PLANET` | Deploys a covert agent onto an enemy colonized celestial body within operational range. |
| `RELOCATE_AGENT` | Moves an embedded agent from their current host to another enemy unit or colony in operational range. |
| `SABOTAGE` | Commands an embedded agent to sabotage host unit subsystems or colonial infrastructure. |
| `CI_SWEEP` | Counter-Intelligence ship performs an active sector sweep (activated via component sidebar panel; cost: 100 credits, 25 AM, 3-turn cooldown) to detect enemy spies on friendly and allied assets within operational range (500 px). |
| `ELIMINATE_AGENT` | Counter-Intelligence ship neutralizes and removes a discovered enemy agent from a friendly or allied unit or colony. |
| `EXTRACT_AGENT` | Recovers an embedded agent back into the parent Intelligence unit. |

---

## 6. Universe Objects & Celestial Bodies

### 6.1 Central Stars (`StarType`)
Every star system contains a central star with a unique antimatter harvesting rate multiplier (`constants.py: STAR_HARVEST_MULTIPLIERS`). Central stars are solid celestial obstacles with a physical **Collision Radius** of **500.01 px** (`STAR_RADIUS`):

| Star Type | Enum Member | Harvest Multiplier | Color (RGB) | Inhibition Radius | Collision Radius |
|---|---|---|---|---|---|
| **Pulsar** | `PULSAR` | **2.5×** | (225, 110, 255) | 2700.0 | 500.01 |
| **Blue Giant** | `BLUE_GIANT` | **2.0×** | (173, 216, 255) | 2700.0 | 500.01 |
| **Neutron Star** | `NEUTRON_STAR` | **1.8×** | (200, 245, 255) | 2700.0 | 500.01 |
| **Yellow Giant** | `YELLOW_GIANT` | **1.5×** | (255, 195, 0) | 2700.0 | 500.01 |
| **Red Giant** | `RED_GIANT` | **1.3×** | (235, 50, 35) | 2700.0 | 500.01 |
| **G-Type (Sol-like)** | `G_TYPE` | **1.0×** (Baseline) | (255, 235, 120) | 2700.0 | 500.01 |
| **White Dwarf** | `WHITE_DWARF` | **0.8×** | (240, 248, 255) | 2700.0 | 500.01 |
| **Protostar** | `PROTOSTAR` | **0.7×** | (255, 140, 0) | 2700.0 | 500.01 |
| **Red Dwarf** | `RED_DWARF` | **0.5×** | (255, 127, 80) | 2700.0 | 500.01 |
| **Brown Dwarf** | `BROWN_DWARF` | **0.3×** | (160, 82, 45) | 2700.0 | 500.01 |
| **Black Hole** | `BLACK_HOLE` | **0.1×** | (75, 35, 100) | 2700.0 | 500.01 |

### 6.2 Planets & Colonizable Bodies
- **Planets (`PlanetType`)**: 9 planetary classes (`TERRAN`, `DESERT`, `VOLCANIC`, `ICE`, `BARREN`, `FERROUS`, `GREENHOUSE`, `OCEANIC`, `GAS_GIANT`). Colonizable planets support up to **100.0 population** with a baseline growth rate of **2.0% per turn**. Inhibition radius: 2400.0. **Collision Radius**: **375.0 px** (`PLANET_RADIUS`).
- **Moons (`Moon`)**: Colonizable satellites supporting up to **50.0 population** with a growth rate of **1.0% per turn**. Inhibition radius: 1800.0. **Collision Radius**: **83.34 px** (`MOON_RADIUS`).
- **Colonizable Asteroids (`ColonizableAsteroid`)**: Habitable asteroid outposts supporting up to **20.0 population** with a growth rate of **0.5% per turn**. Inhibition radius: 1200.0. **Collision Radius**: **50.01 px** (`ASTEROID_RADIUS`).

### 6.3 Resource & Spatial Phenomena
- **Metal Asteroids (`MetalAsteroid`)**: Non-colonizable mineral bodies providing a sustainable source of raw **Metal** (yield: 10.0/turn). Inhibition radius: 1200.0. **Collision Radius**: **50.01 px** (`ASTEROID_RADIUS`).
- **Comets (`Comet`)**: Pristine icy bodies yielding raw **Crystal** (yield: 10.0/turn). Inhibition radius: 600.0. **Collision Radius**: **50.01 px** (`COMET_RADIUS`).
- **Wormholes (`Wormhole`)**: Natural spacetime conduits linking star systems. Traversal requires an Advanced Hyperdrive. Visual radius: 291.66. Inhibition radius: 1500.0. **Collision Radius**: **0.0 px** (permeable).
- **Asteroid Fields (`AsteroidField`)**: Dense clusters of rocky fragments. Inhibition radius: 900.0. **Collision Radius**: **0.0 px** (permeable).
- **Ice Fields (`IceField`)**: Dense fields of volatile ice particles. Inhibition radius: 600.0. **Collision Radius**: **0.0 px** (permeable).
- **Debris Fields (`DebrisField`)**: Remnants of past orbital battles or derelict structures. **Collision Radius**: **0.0 px** (permeable).
- **Nebulae (`Nebula`)**: Vast interstellar clouds with 4 distinct elemental subtypes (`HYDROGEN`, `NITROGEN`, `OXYGEN`, `DUST`). Visual radius: 1666.68. **Collision Radius**: **0.0 px** (permeable). Naturally conceals starships positioned within its cloud boundaries from enemy long-range (inter-sector) sensors.
- **Space Storms (`Storm`)**: Hazardous energetic disturbances with 3 environmental subtypes (`PLASMA`, `MAGNETIC`, `RADIATION`). Visual radius: 1666.68. **Collision Radius**: **0.0 px** (permeable).

### 6.4 Celestial Body Dimensions & Obstacle Classification Summary

| Entity Class | Solid Obstacle? | Collision Radius (`px`) | Inhibition Radius (`px`) | Harvest / Resource Yield | Colonizable |
|---|---|---|---|---|---|
| `Star` | **Yes** | 500.01 (`STAR_RADIUS`) | 2700.0 | 0.1× – 2.5× Antimatter | No |
| `Planet` | **Yes** | 375.00 (`PLANET_RADIUS`) | 2400.0 | — | Yes (Max 100 pop) |
| `Moon` | **Yes** | 83.34 (`MOON_RADIUS`) | 1800.0 | — | Yes (Max 50 pop) |
| `ColonizableAsteroid` | **Yes** | 50.01 (`ASTEROID_RADIUS`) | 1200.0 | — | Yes (Max 20 pop) |
| `MetalAsteroid` | **Yes** | 50.01 (`ASTEROID_RADIUS`) | 1200.0 | 10.0 Metal / Turn | No |
| `Comet` | **Yes** | 50.01 (`COMET_RADIUS`) | 600.0 | 10.0 Crystal / Turn | No |
| `Wormhole` | No | 0.00 (Permeable) | 1500.0 | Inter-System Travel | No |
| `AsteroidField` | No | 0.00 (Permeable) | 900.0 | — | No |
| `IceField` | No | 0.00 (Permeable) | 600.0 | — | No |
| `DebrisField` | No | 0.00 (Permeable) | 0.0 | — | No |
| `Nebula` | No | 0.00 (Permeable) | 0.0 | — | No (Long-Range Stealth) |
| `Storm` | No | 0.00 (Permeable) | 0.0 | — | No |

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

### Sabotage Types (`SabotageType` — 8 total)
- `ENGINES`: Reduces host vessel maximum sublight speed by 50%.
- `WEAPONS`: Decreases turret weapon damage output by 50%.
- `DEFENSES`: Lowers armor mitigation and shield strength by 50%.
- `HYPERDRIVE`: Disables intra-system sector jumping and wormhole jumping.
- `SENSORS`: Blindfolds target short-range sensors and disables long-range radar hex sharing.
- `ANTIMATTER`: Causes 5.0 antimatter fuel leak per turn from storage tanks.
- `ECONOMY`: Halves credit tax revenue generated by the host colony.
- `GROWTH`: Halts population growth on the host colony.

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
- **Field Refitting System (`unit_orders/refit.py`, `unit_components/constructor.py`)**: Enables units with a `Constructor` to dynamically install components onto, or strip components from, friendly and allied units within build range (500 px). Component addition costs `Used Hull × 30` credits and requires `max(1, round(Hull / 5))` turns. Component removal takes 1 turn and grants an immediate 50% salvage credit refund. Orders automatically enforce hull size restrictions, headroom limits, and docked carrier craft safety checks, prepending `MoveOrder` approach sub-orders if out of range.
- **Visibility & Sensor Sharing (`visibility.py`)**: Computes sector-by-sector and in-hex sensor horizons. Generates fog-of-war masks, unifies short-range and long-range sensor coverage across all allied players, shares stealth area cloaking protection, conceals units inside nebulae from long-range sensors, and persists last-known sector intel per player.
- **Diplomacy & Team System (`entities.py`, `game_settings.py`, `game_setup.py`, `save_manager.py`)**: Manages static multi-team configurations established during game setup. Evaluates relations (`is_allied_with`, `is_enemy_of`) to govern sensor sharing, tactical combat engagement, logistics sharing, area buffs, friendly fire prevention, and covert espionage targeting.
- **Sub-light Navigation & Celestial Collision Avoidance (`geometry.py`, `unit_orders/movement.py`)**: Real-time geometric pathfinding preventing sub-light vessels from clipping into solid celestial bodies (stars, planets, moons, asteroids, comets). Uses parametric line-circle intersection analysis, dual-tangent escape waypoint generation, and recursive obstacle resolution to steer ships safely around physical bodies with a $+50.0\text{ px}$ clearance margin, while permitting unhindered landings and departures.
- **GUI & Renderer Packages (`gui/`, `rendering/`)**: Strict facade pattern isolating UI widget hierarchies and layout managers from pygame-ce rendering loops and mathematical spatial transformations.
- **Resolution Independence (`theme_loader.py`, `TEXT_SCALE`, `theme_scaled.json`)**: Dynamically computes theme scale ratios to ensure clean font and layout rendering across diverse desktop resolutions.

---

## 9. Intelligence, Counter-Intelligence & Sabotage Systems

### 9.1 Overview & Components
The Intelligence system introduces covert operations, espionage, sensor reconnaissance, subsystem sabotage, and counter-intelligence sweeps into the strategic and tactical gameplay.

- **`IntelligenceComponent` (`unit_components/intelligence.py`)**:
  - Available on `SMALL`, `MEDIUM`, `LARGE`, and `HUGE` hulls (Forbidden on `STRIKECRAFT_WING` and `TINY`).
  - **Agent Capacity**: Configurable in the Unit Designer / Retrofit Wizard ($5.0\text{ Hull/agent}$, default 2 agents).
  - **Counter-Intelligence Suite**: Optional toggle ($+10.0\text{ Hull}$, $+300\text{ credits}$) that enables active sector sweeps to uncover enemy agents and eliminate them.
- **`Agent` Dataclass (`unit_components/intelligence.py`)**:
  - Embedded field operative with fields: `id`, `owner`, `source_unit_id`, `target_type` (`"UNIT"` or `"CELESTIAL_BODY"`), `target_id`, `is_discovered`, `active_sabotage`, and `turns_active`.

### 9.2 Agent Deployment & Operational Lifecycle
- **Deployment Range**: Standard operational range is **500.0 px**.
- **Real-Time Execution**: When issuing an intelligence command within operational range in the same sector, the order executes immediately in the current frame without requiring the turn to end. If outside range, an approach `MoveOrder` is automatically generated and executed.
- **Relocation & Extraction**: Agents can transition directly between enemy hosts in range via `RelocateAgentOrder` or be recovered back into an Intelligence vessel via `ExtractAgentOrder`.

### 9.3 Sensor Sharing & Fog of War
- **Covert Sensor Reconnaissance**: Embedded agents grant their owner full access to the host unit or colony's sensor horizon.
- **Visibility & Rendering**:
  - `VisibilityService` incorporates short-range and long-range sensor coverage of all infiltrated targets.
  - Sector view Fog-of-War cutouts immediately reveal the area around infiltrated enemy units and celestial bodies (500 px radius for colonies).
  - Range circles (weapons, sensors) and system-view long-range highlights are fully rendered for selected infiltrated enemy units.

### 9.4 Subsystem & Colonial Sabotage
Agents can execute 8 distinct sabotage operations against their host:
1. **Engines (`ENGINES`)**: Multiplies maximum sublight speed by 0.5×.
2. **Weapons (`WEAPONS`)**: Multiplies turret damage output by 0.5×.
3. **Defenses (`DEFENSES`)**: Multiplies armor rating and shield absorption by 0.5×.
4. **Hyperdrive (`HYPERDRIVE`)**: Disables intra-system sector hex jumps and wormhole jumps.
5. **Sensors (`SENSORS`)**: Multiplies short-range sensor radius by 0.0× and disables long-range radar hex sharing.
6. **Antimatter (`ANTIMATTER`)**: Drains 5.0 antimatter fuel per turn from target tanks.
7. **Economy (`ECONOMY`)**: Siphons/destroys 50% of the host colony's credit tax revenue.
8. **Growth (`GROWTH`)**: Halts population growth on the host colony.

### 9.5 Counter-Intelligence, Discovery & Stealth
- **Active CI Sweeps (`CISweepOrder`)**: A vessel equipped with a Counter-Intelligence suite performs an area-of-effect sector sweep within operational range (500 px) activated via the Intelligence component panel in the sidebar. The sweep reveals all enemy agents embedded on friendly and allied ships or colonies in range, setting `agent.is_discovered = True`. Sweeps cost **100 credits** from the treasury, **25 AM** from the ship's tanks, and trigger a **3-turn cooldown** on the vessel. Passive turn-tick detection is not present—enemy agents remain hidden unless actively swept.
- **Elimination (`EliminateAgentOrder`)**: Counter-Intelligence ships within 500 px operational range can neutralize and remove any discovered enemy agent from friendly and allied assets.
- **Covert Component Concealment**: The `IntelligenceComponent` is completely hidden from enemy players. When an enemy player inspects a hostile vessel, the component is completely omitted from the sidebar (both the *Basic Info* component overview and the *Components* dropdown inspector) and is hidden from the attack context menu. Friendly and allied players retain full visibility and inspector access.
- **Visual & UI Indicators**:
  - Infiltrated ships and planets display `[INFILTRATED]` (cyan) or `[SABOTAGED: <TYPE>]` (orange) badges in sector view and cyan spy indicators in system view.
  - Friendly and allied entities hosting detected enemy spies display `[DISCOVERED SPY]` (red) warning badges.
  - Sidebar panels display a prominent `👁 COVERT AGENT EMBEDDED [SABOTAGE: ...]` status banner when inspecting infiltrated targets.

---

## 10. Diplomacy & Team Systems

### 10.1 Overview & Team Architecture
Wormhole Control supports multi-player and multi-team diplomatic alignment. Diplomatic relations are configured during game setup in the **New Game Wizard** and remain **static in-game** throughout the match.

- **Team Groups (`team_id: int`)**: Players are assigned to numeric teams ($1 \dots N$).
  - **Allies**: Players sharing the same `team_id` are considered allies (`player.is_allied_with(other)` is `True`).
  - **Enemies**: Players assigned to different `team_id` values are enemies (`player.is_enemy_of(other)` is `True`).
- **Validation**: When configuring games with 2 or more players, at least two distinct teams are required to ensure valid competitive or cooperative matchups.
- **Persistence**: Team assignments are serialized and deserialized with the game state in `save_manager.py` (`team_id`).

### 10.2 Sensor Sharing, Visibility & Stealth
- **Allied Sensor Fusion (`visibility.py`)**:
  - Short-range sensor horizons (pixels) and long-range radar hex coverage are fully shared across all allied players.
  - Infiltrated enemy units or celestial bodies also provide shared sensor vision to the infiltrating player and all of their allies.
  - Long-range sector reconnaissance automatically records sector intel for all allied players.
- **Fog of War**: Sector-view Fog of War cutouts dynamically reveal regions covered by friendly or allied sensor suites.
- **Advanced Area Cloaking**: Units equipped with an active Advanced Cloaking Device (`CloakingType.ADVANCED`) extend long-range sensor stealth to all friendly and allied vessels located within their projection radius.
- **Environmental Nebula Concealment**: Starships stationed inside a nebula cloud are naturally concealed from enemy long-range (inter-sector) sensors, requiring enemy vessels to close into short-range visual sensor distance to achieve detailed target identification.
- **Minefield Awareness**: Minefields deployed by allied players are always visible and do not trigger on friendly or allied ships.

### 10.3 Combat, Targeting & Area Effects
- **Target Discrimination**:
  - Combat orders (`AttackOrder`, `ProtectOrder`, `PatrolOrder`) exclusively acquire enemy targets and will never engage friendly or allied ships.
  - Automated turret fire and weapon systems reject allied targets.
- **Orbital Defense Coordination (`unit_components/orbital_defense.py`)**:
  - Orbital defense ships activate their defensive aura in sectors containing friendly or allied colonies with population $> 0$.
  - Defense capacity limits and active aura slots are shared and coordinated with allied orbital defense vessels in the sector.
  - The $+20\%$ weapon damage and $+20\%$ defense mitigation aura applies to all allied ships in range.
- **Area Healing & Splash Avoidance**:
  - **Repair Cloud (`repair_cloud.py`)**: Heals all friendly and allied vessels within range.
  - **Cluster Warhead (`cluster_warhead.py`)**: AoE detonation excludes friendly and allied ships from splash damage.

### 10.4 Intelligence & Covert Rules
- **Hostile Espionage Operations**: Infiltration (`InfiltrateUnitOrder`, `InfiltratePlanetOrder`), agent relocation (`RelocateAgentOrder`), and subsystem sabotage strictly target enemy units and enemy colonies.
- **Covert Component Concealment**: Hostile players inspecting opposing units cannot detect installed `IntelligenceComponent` suites in the sidebar (Basic Info overview and Components tab inspector) or target them in attack context menus.
- **Economic Siphoning**: Credit tax siphoning from the Economy sabotage operation applies exclusively to enemy colonies.
- **Shared Counter-Intelligence**:
  - Active `CISweepOrder` scans both friendly and allied ships/colonies in range to expose hidden enemy agents.
  - Discovered enemy spies on allied ships or colonies can be neutralized via `EliminateAgentOrder`.

### 10.5 Support & Logistics Cooperation
- **Refitting & Repairs**: Constructor ships (`RefitOrder`) can add or remove components on allied vessels, and repair ships (`RepairOrder`) can restore hull integrity on damaged allied units.
- **Antimatter Transfers**: Harvesters and tankers (`TransferAntimatterOrder`, `ContinuousResupplyOrder`) can transfer fuel to allied vessels.
- **Colonist Transfers**: Colony transports (`LoadColonistsOrder`) can embark population from allied colonies.
- **Hostile Abilities**: Targeted hostile abilities (`CaptureUnit`, `DrainAntimatter`, `DesignateTarget`) automatically disallow targeting allied ships.
- **Context Menus**: Right-click context menus dynamically adapt based on diplomacy, displaying cooperative options (Protect, Repair, Refit, Refuel, CI Sweep) for allies, and hostile options (Attack, Infiltrate, Sabotage) for enemies.

---

## 11. Celestial Collision Avoidance

### 11.1 Overview & Purpose
In Wormhole Control, ships moving at sub-light speeds navigate tactical sector space ($5000\text{ px}$ radius circle per hex). To preserve spatial immersion and tactical realism, units never fly straight through physical solid bodies (such as stars, planets, moons, asteroids, or comets). 

The collision avoidance system automatically detects obstructed sub-light trajectories in real-time, calculates optimal curved bypass trajectories using geometric tangent math, and injects intermediate waypoint sub-orders into unit order queues without requiring manual player micro-management.

### 11.2 Celestial Body Collision Radii & Classification
Every celestial entity defines a `collision_radius: float` attribute (`entities.py`):

1. **Solid Celestial Obstacles (`collision_radius > 0.0`)**:
   - **Central Star (`Star`)**: `STAR_RADIUS = 500.01 px`
   - **Planets (`Planet`)**: `PLANET_RADIUS = 375.00 px`
   - **Moons (`Moon`)**: `MOON_RADIUS = 83.34 px`
   - **Asteroids (`ColonizableAsteroid`, `MetalAsteroid`)**: `ASTEROID_RADIUS = 50.01 px`
   - **Comets (`Comet`)**: `COMET_RADIUS = 50.01 px`

2. **Permeable Spatial Phenomena (`collision_radius = 0.0`)**:
   - **Nebulae, Space Storms, Wormholes, Asteroid Fields, Ice Fields, Debris Fields**: Non-solid entities that do not obstruct sub-light flight. Ships pass straight through them.

3. **Safety Margin**:
   - When checking for collisions and computing avoidance waypoints, the navigation engine adds a safety margin buffer $\text{margin} = 50.0\text{ px}$ around the obstacle's physical radius:
   $$R_{\text{expanded}} = r_{\text{body}} + \text{margin}$$
