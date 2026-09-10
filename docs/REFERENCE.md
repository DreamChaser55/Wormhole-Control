# Wormhole Control — Reference Manual

This document contains player guidance, in-depth reference data, data structures, catalogues, enums, architecture notes, and development instructions for **Wormhole Control**. For installation and a short introduction, see the [README](../README.md).

---

## Contents

- [Playing the Game](#playing-the-game)
- [1. Project Structure](#1-project-structure)
- [2. Hull Sizes](#2-hull-sizes)
- [3. Component Catalogue](#3-component-catalogue)
- [4. Special Abilities](#4-special-abilities)
- [5. Order Types](#5-order-types)
- [6. Universe Objects & Celestial Bodies](#6-universe-objects--celestial-bodies)
- [7. Enums Quick Reference](#7-enums-quick-reference)
- [8. Architecture & Subsystems](#8-architecture--subsystems)
- [9. Intelligence, Counter-Intelligence & Sabotage Systems](#9-intelligence-counter-intelligence--sabotage-systems)
- [10. Diplomacy & Team Systems](#10-diplomacy--team-systems)
- [11. Celestial Collision Avoidance](#11-celestial-collision-avoidance)
- [AI order control (observation 5, command contract 3)](#ai-order-control-observation-5-command-contract-3)
- [12. Celestial Bodies & Environmental Mechanics](#12-celestial-bodies--environmental-mechanics)
- [13. Damage & Minefield Resolution](#13-damage--minefield-resolution)
- [Runtime storage and API failure contracts](#runtime-storage-and-api-failure-contracts)
- [New-campaign validation](#new-campaign-validation)
- [Development and Testing](#development-and-testing)

## Playing the Game

### Campaign Setup

Click **New Game** on the main menu to open the two-stage New Game Wizard.

1. **Galaxy Setup & Preview:** Adjust the star system count (5–30), minimum/maximum system radius (3–12), wormhole connectivity density (0–100%), and minimum/maximum inter-system distances. Click **Generate Map** to re-roll the map and preview its topology, system positions, and wormhole conduits. Select **Next: Players & Economy ➔** to continue.
2. **Factions & Starting Conditions:** Choose the **Normal** campaign or **Testing** sandbox [spawn profile](#spawn-profiles-spawnprofile--2-total). Configure 2–6 players, names, faction colors, and controllers. The player-type button cycles through Human, Codex, AI: Medium, AI: High, and AI: Low. Set starting credits, metal, crystal, and homeworld population.
3. **Home Systems:** Choose **Random** assignment or **Specified** homes. For specified homes, cycle systems using the ◀/▶ buttons or click systems in the Map Preview. The spawn-profile rules govern distinct and shared homes.
4. Click **Start Game** to generate the campaign and begin turn 1. **◀ Back to Map** returns to Stage 1 while preserving player choices.

See [new-campaign validation](#new-campaign-validation) for complete settings restrictions and [automated player setup](../README.md#automated-players) for controller configuration.

### Controls

| Input | Action |
|---|---|
| **Left Click** | Select unit, solid celestial body, or destination target (non-solid bodies are selected via hex sidebar) |
| **Shift + Left Click** | Add / remove unit from multi-unit selection |
| **Left Drag** | Draw selection box to select multiple units |
| **Right Click** | Open contextual action menu or issue direct unit command |
| **Shift + Order** | Queue new order behind current/existing orders (all order types) |
| **Middle Mouse Drag** | Pan the System or Sector View camera |
| **Mouse Wheel** | Zoom the System or Sector View camera in / out |
| **G** | Switch to **Galaxy View** |
| **S** | Switch to **System View** |
| **E** | **End Turn** (process actions and advance to next player) |
| **ESC** | Open In-Game Menu / Cancel targeting mode / Deselect |
| **Arrow Keys** | Pan the System or Sector View camera |

### The Three Views

Wormhole Control organizes space into three interconnected strategic perspectives:

- **Galaxy View (`G`)**: Strategic overview of the known galaxy showing all star systems, player home system color markers (including concentric circles for systems shared by multiple players), and wormhole conduits connecting distant systems.
- **System View (`S`)**: System-level hexgrid map showing orbital sectors radiating outward from the central star, along with celestial bodies, wormhole routes, and sector-level fog of war. Systems are automatically fitted to the unobstructed map area and support mouse-wheel zoom plus middle-drag or arrow-key panning.
- **Sector View**: Tactical view providing a granular look at celestial objects, orbital structures, individual starships, weapon range circles, minefields, and real-time movement trajectories in a specific sector.

Selected objects in System and Sector views are marked with four L-shaped corner brackets. System View brackets enclose the displayed icon or environmental effect with a small fixed screen-space gap and follow camera zoom and panning. Object selection highlights use the selected object's owner's faction color blended 20% toward white, including units, colonies, and Sector View minefields, while icons retain their original colors. Unowned objects and white faction colors retain white highlights. Each selected object uses its own owner's color, and ownership changes update the highlight immediately. The blue drag-selection rectangle and hex highlights retain their existing colors.

### Turns and Resource Economy

Matches operate on a hot-seat turn sequence. When finished issuing commands, press **`E`** or click **End Turn** on the HUD. This resolves that player's movement, mine contacts, resource income, upkeep, population growth and combat before advancing.

- **Credits**: General empire treasury generated from colonized populations and civilian habitats. Credits fund ship construction, space installations, and ongoing fleet upkeep.
- **Metal**: Extracted from metal asteroids by mining ships. Refined at Metal Refineries to construct ship hulls and orbital infrastructure.
- **Crystal**: Rare crystalline mineral harvested from comets. Refined at Crystal Refineries to build advanced sensors, weapons, and hyperdrives.
- **Antimatter**: High-energy fuel stored in per-unit storage tanks. Powers sublight engine burn, hyperdrive jumps, cloaking fields, and special abilities. Antimatter can be gathered by **Antimatter Harvester** ships stationed near stars and transferred to other ships.

### Movement and Fleet Operations

Sublight engines consume antimatter to move within a sector. Basic hyperdrives enable adjacent-sector hex jumps within a system; advanced hyperdrives also allow inter-system wormhole travel. The Microjump ability repositions a ship within its sector, subject to [collision and field restrictions](#11-celestial-collision-avoidance). Inhibitor ships prevent enemy hyperspace entry and exit within their fields; massive celestial bodies also inhibit nearby jumps.

Mining and harvesting ships can maintain supply loops with **Continuous Mine** and **Continuous Resupply**; harvesters collect antimatter from stars and hydrogen nebulae. Constructors build orbital platforms, shipyards, refineries, and stations. See [order types](#5-order-types) for logistics workflows and [components](#3-component-catalogue) for construction, habitat, and orbital-defense requirements.

### Combat, Detection, and Expansion

Armor counters mass drivers, Shields counter beams, and Point Defense counters missiles. Units gain combat experience (XP), ranking up to improve weapon damage, defensive ratings, sublight speed, and hyperdrive jump ranges. See [turret types and variants](#turret-types--variants-turrettype--turretvariant--3--3), [standing engagement policies](#unit-stances-unitstance--5-total), and [damage and minefield resolution](#13-damage--minefield-resolution) for detailed combat rules. Boarding uses Marines and the [Capture Unit ability](#4-special-abilities); carrier fighters and bombers are covered under [strikecraft wing types](#strikecraft-wing-types-wingtype--2-total).

Ships and stations provide short-range visual circles and long-range inter-sector detection. Unexplored space stays hidden; explored sectors retain last-seen turn intel until active sensors refresh it. See [visibility and allied sensor sharing](#102-sensor-sharing-visibility--stealth), [cloaking components](#3-component-catalogue), and [intelligence operations](#9-intelligence-counter-intelligence--sabotage-systems) for concealment and covert reconnaissance.

Colony ships settle habitable planets, moons, and colonizable asteroids. Consult [planetary traits](#121-planetary-classification--traits) for population growth and passive resource yields, and [environmental mechanics](#12-celestial-bodies--environmental-mechanics) for tactical cover, hazards, and gas-giant hiding.

### Unit Designer

Click **Unit Editor** beside **Comms** in the bottom panel to open the **Unit Designer** and create starship templates. The button is available in Galaxy, System, and Sector views without opening the in-game menu. Choose a [hull size](#2-hull-sizes), tune engines, hyperdrives, turrets, and defenses with dynamic hull costs, and install fixed utility modules such as refineries, colony pods, and hangars. The [component catalogue](#3-component-catalogue) and [special abilities table](#4-special-abilities) describe available equipment and restrictions.

Saved designs immediately become available for construction in active shipyards. Designs live in a separate user-data library; see [custom-design storage and migration](#custom-design-storage-and-migration) for paths, recovery, and upgrades.

### Saving and Loading

Open the in-game menu (**Esc**) and select **Save Game** to write a JSON campaign under `saves/`. Select **Load Game** on the main title screen or in-game menu to resume a campaign. See [save integrity](#107-save-format-40-integrity) and [Campaign persistence](SAVE_FORMAT.md) for preserved state, validation guarantees, and legacy migration warnings.

Built-in AI players keep canonical long-term memory in the campaign save; a readable derived copy is generated at `saves/agent_memory/<campaign>/<agent>/memory.md`. See [AI memory and persistence](AGENTIC_AI.md#memory-and-persistence) for its lifecycle, and [communications persistence](#106-inter-player-communications--markdown-persistence) for real-time and campaign-specific transmission logs.

## 1. Project Structure

```text
Wormhole-Control/
├── LICENSE
├── README.md
├── campaign_graph.py
├── campaign_persistence.py
├── application_bootstrap.py
├── component_visibility.py
├── constants.py
├── display_config.py
├── custom_unit_templates.py
├── economy.py
├── entities.py
├── environmental_effects.py
├── events.py
├── galaxy.py
├── galaxy_utils.py
├── game.py
├── game_camera.py
├── game_control.py
├── game_control_protocol.py
├── game_logging.py
├── game_settings.py
├── game_setup.py
├── geometry.py
├── hexgrid_utils.py
├── order_history.py
├── order_system.py
├── pathfinding.py
├── persistence_context.py
├── player_controller.py
├── pyproject.toml
├── pytest.ini
├── renderer.py
├── requirements-dev.txt
├── requirements.txt
├── save_manager.py
├── save_migrations.py
├── sector_utils.py
├── state_codec.py
├── theme.json
├── timed_effects.py
├── turn_processor.py
├── turn_presentation.py
├── unit_templates.py
├── utils.py
├── visibility.py
├── .github/
│   └── workflows/
│       └── ci.yml
├── data/
│   ├── spawn_rates.json
│   ├── star_names.json
│   └── unit_templates.json
├── docs/
│   ├── AGENTIC_AI.md
│   ├── CODEX_CONTROL.md
│   ├── REFERENCE.md
│   └── SAVE_FORMAT.md
├── domain/  # Canonical classes; entities.py is an explicit lazy compatibility facade
│   ├── coordinates.py
│   ├── identity.py
│   ├── communications.py
│   ├── players.py
│   ├── celestials.py
│   ├── minefields.py
│   └── units.py
├── fonts/  # Bundled font families
├── game_actions/
│   ├── __init__.py
│   ├── app_actions.py
│   ├── selection_actions.py
│   ├── turn_presentation.py
│   └── unit_actions.py
├── game_ai/
│   ├── __init__.py
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── fake.py
│   │   └── openai_responses.py
│   ├── command_spec.py
│   ├── commands.py
│   ├── config.py
│   ├── contracts.py
│   ├── coordinator.py
│   ├── evaluation.py
│   ├── intelligence.py
│   ├── memory.py
│   ├── observation.py
│   ├── order_view.py
│   ├── prompts.py
│   ├── rules.py
│   ├── runtime.py
│   └── schema.py
├── gui/
│   ├── __init__.py
│   ├── communications_window.py
│   ├── context_menu.py
│   ├── dynamic_actions.py
│   ├── event_router.py
│   ├── handler.py
│   ├── layout_hud.py
│   ├── layout_ingame_menu.py
│   ├── layout_main_menu.py
│   ├── layout_new_game_wizard.py
│   ├── retrofit_gui/
│   │   ├── __init__.py
│   │   ├── catalog.py
│   │   ├── layout.py
│   │   ├── param_readers.py
│   │   └── wizard.py
│   ├── sidebar/
│   │   ├── __init__.py
│   │   ├── builder.py
│   │   ├── order_formatting.py
│   │   ├── panels_unit.py
│   │   ├── panels_world.py
│   │   └── view.py
│   ├── text_layout.py
│   ├── theme_loader.py
│   └── unit_editor_gui/
│       ├── __init__.py
│       ├── catalog.py
│       ├── component_state.py
│       ├── cost_model.py
│       ├── event_handlers.py
│       ├── layout.py
│       ├── layout_details.py
│       ├── param_readers.py
│       ├── save_dialog.py
│       ├── summary_view.py
│       ├── template_io.py
│       ├── turret_editor.py
│       ├── widget_factory.py
│       └── window.py
├── input_processor/
│   ├── __init__.py
│   ├── context_actions.py
│   ├── context_menu_builder.py
│   ├── hover_tracker.py
│   ├── keyboard_handler.py
│   ├── mouse_handler.py
│   └── processor.py
├── rendering/
│   ├── drawing_utils.py
│   ├── galaxy_renderer.py
│   ├── main_menu_renderer.py
│   ├── sector_renderer/
│   │   ├── __init__.py
│   │   ├── sector_celestial_renderer.py
│   │   ├── sector_entity_renderer.py
│   │   ├── sector_grid_renderer.py
│   │   ├── sector_overlay_renderer.py
│   │   └── sector_renderer.py
│   └── system_renderer.py
├── scripts/
│   ├── check_import_boundaries.py
│   └── generate_reference.py
├── unit_components/
│   ├── __init__.py
│   ├── abilities/
│   │   ├── __init__.py
│   │   ├── adaptive_forcefield.py
│   │   ├── base.py
│   │   ├── capture_unit.py
│   │   ├── cluster_warhead.py
│   │   ├── component.py
│   │   ├── designate_target.py
│   │   ├── drain_antimatter.py
│   │   ├── ion_bolt.py
│   │   ├── microjump.py
│   │   ├── missile_batteries.py
│   │   ├── registry.py
│   │   ├── repair_cloud.py
│   │   └── scan_for_minefields.py
│   ├── antimatter.py
│   ├── base.py
│   ├── civilian_habitat.py
│   ├── cloaking.py
│   ├── colony.py
│   ├── commander.py
│   ├── constructor.py
│   ├── defenses.py
│   ├── enums.py
│   ├── hangar.py
│   ├── inhibitor.py
│   ├── intelligence.py
│   ├── marines.py
│   ├── minelayer.py
│   ├── mining.py
│   ├── movement.py
│   ├── orbital_defense.py
│   ├── persistence.py
│   ├── repair.py
│   ├── sensors.py
│   ├── strikecraft.py
│   ├── trade.py
│   └── weapons.py
├── unit_orders/
│   ├── __init__.py
│   ├── abilities.py
│   ├── antimatter.py
│   ├── base.py
│   ├── colony.py
│   ├── combat.py
│   ├── construction.py
│   ├── defend.py
│   ├── gas_giant.py
│   ├── hangar.py
│   ├── inhibitor.py
│   ├── intelligence.py
│   ├── minelayer.py
│   ├── mining.py
│   ├── movement.py
│   ├── patrol.py
│   ├── refit.py
│   ├── repair.py
│   ├── stance.py
│   ├── registry.py
│   └── trade.py
├── tests/  # Offline behavior suites, shared support scenarios, and lifecycle fixtures
└── saves/  # Runtime campaigns and logs
```

---

## 2. Hull Sizes

Wormhole Control features 6 hull classes (`HullSize`). Each hull size sets the capacity budget for installed components, baseline durability, minimum antimatter capacity, and baseline construction costs.

| Hull Size | Enum Value | Hull Capacity | Base HP | Min Antimatter Capacity | Base Build Cost (Credits) | Base Build Time (Turns) | Upkeep Cost / Turn |
|---|---|---|---|---|---|---|---|
| `STRIKECRAFT_WING` | 1 | 5.0 | 40 | 40.0 | 50 | 1 | 0 (Exempt) |
| `TINY` | 2 | 10.0 | 20 | 60.0 | 100 | 3 | 0.01 × Used Hull Points |
| `SMALL` | 3 | 25.0 | 50 | 80.0 | 250 | 6 | 0.01 × Used Hull Points |
| `MEDIUM` | 4 | 50.0 | 100 | 100.0 | 500 | 10 | 0.01 × Used Hull Points |
| `LARGE` | 5 | 100.0 | 200 | 150.0 | 1000 | 15 | 0.01 × Used Hull Points |
| `HUGE` | 6 | 200.0 | 400 | 200.0 | 2000 | 20 | 0.01 × Used Hull Points |

*Note: Total unit build cost is `Base Build Cost + (Used Hull Capacity × 30 Credits)`. Total build time is `Base Build Time + (Used Hull Capacity / 10 Turns)`. Ongoing unit upkeep cost is `0.01 Credits × Used Hull Points` per turn (Strikecraft Wings are exempt). Strikecraft Wings are immune to negative field effects (sublight speed drag in Asteroid, Ice, and Debris Fields, and debris abrasion damage), but are strictly banned from entering or launching within Magnetic Storms.*

---

## 3. Component Catalogue

<!-- BEGIN GENERATED: components -->
The Unit Designer provides **24 selectable component rows**. Commander is always present.

| # | Component Key | Label | Cost Type | Default Cost |
| --- | --- | --- | --- | --- |
| 1 | `has_engine` | Engines | Dynamic | 5.0 |
| 2 | `has_antimatter_storage` | Antimatter Storage | Dynamic | 5.0 |
| 3 | `has_antimatter_harvester` | Antimatter Harvester | Fixed | 15.0 |
| 4 | `has_hyperdrive` | Hyperdrive | Dynamic | 5.0 |
| 5 | `has_weapon_bays` | Weapons | Dynamic | 10.0 |
| 6 | `has_defenses` | Defenses | Dynamic | 10.0 |
| 7 | `has_constructor_component` | Constructor | Fixed | 15.0 |
| 8 | `has_repair_component` | Repair | Dynamic | 15.0 |
| 9 | `has_colony_component` | Colony | Fixed | 10.0 |
| 10 | `has_civilian_habitat_component` | Civilian Habitat | Fixed | 15.0 |
| 11 | `has_orbital_defense_component` | Orbital Defense | Fixed | 20.0 |
| 12 | `has_trade_component` | Trade Module | Fixed | 10.0 |
| 13 | `has_mining_component` | Mining | Dynamic | 10.0 |
| 14 | `has_metal_refinery_component` | Metal Refinery | Fixed | 20.0 |
| 15 | `has_crystal_refinery_component` | Crystal Refinery | Fixed | 20.0 |
| 16 | `has_hangar` | Hangar | Dynamic | 20.0 |
| 17 | `has_strikecraft_bay` | Strikecraft Bay | Dynamic | 15.0 |
| 18 | `has_inhibitor` | Inhibitor Field | Dynamic | 20.0 |
| 19 | `has_ability_component` | Abilities | Dynamic | 10.0 |
| 20 | `has_sensors` | Sensors | Dynamic | 2.0 |
| 21 | `has_minelayer_component` | Minelayer | Fixed | 15.0 |
| 22 | `has_marines_component` | Marines | Dynamic | 10.0 |
| 23 | `has_cloaking_device` | Cloaking Device | Dynamic | 10.0 |
| 24 | `has_intelligence_component` | Intelligence | Dynamic | 10.0 |
<!-- END GENERATED: components -->

Hull restrictions and component behavior:

- **Engines**: Available on all hull sizes. Dynamic cost scales with sublight speed and hull size.
- **Antimatter Storage**: Available on all hull sizes. Dynamic cost scales with additional storage capacity.
- **Antimatter Harvester**: Forbidden on `STRIKECRAFT_WING` and `TINY`. Harvests antimatter near stars.
- **Hyperdrive**: Forbidden on `STRIKECRAFT_WING`. Basic hyperdrive available on `TINY`+; Advanced hyperdrive requires `SMALL`+.
- **Weapons**: Available on all hull sizes. Dynamic cost scales with turret count, damage, range, and fire rate.
- **Defenses**: Available on all hull sizes. Dynamic cost scales with Armor, Shields, and Point Defense ratings.
- **Constructor**: Forbidden on `STRIKECRAFT_WING` and `TINY`. Enables building space stations and starships (`TINY` through `HUGE`; strikecraft wings are excluded and constructed solely by units with a strikecraft bay), as well as field refitting (adding or removing components) on friendly and allied vessels.
- **Repair**: Forbidden on `STRIKECRAFT_WING` and `TINY`. Dynamic cost scales with repair rate. Repairs friendly and allied ships.
- **Colony**: Forbidden on `STRIKECRAFT_WING` and `TINY`. Enables planetary colonization and loading colonists from friendly/allied worlds.
- **Civilian Habitat**: Forbidden on `STRIKECRAFT_WING` and `TINY`. Generates +50 credits/turn in colonized sectors up to the colony's supported habitat limit (base 1, +1 per 25 population).
- **Orbital Defense**: Forbidden on `STRIKECRAFT_WING` and `TINY`. Projects an area-of-effect aura (500 radius) providing +20% weapon damage and +20% defense mitigation to friendly and allied ships in range in friendly/allied colonized sectors up to the colony's supported orbital defense limit (base 1, +1 per 25 population). Overlapping auras stack additively.
- **Trade Module**: Forbidden on `STRIKECRAFT_WING` and `TINY`. **Requires Engines (`has_engine`)**. Enables trade ships to earn credits by traveling between active Civilian Habitat modules in different sectors, with payout scaling with distance between sectors.
- **Mining**: Available on all hull sizes. Dynamic cost scales with mining rate and cargo capacity.
- **Metal Refinery**: Forbidden on `STRIKECRAFT_WING` and `TINY`. Refines mined ore into metal.
- **Crystal Refinery**: Forbidden on `STRIKECRAFT_WING` and `TINY`. Refines mined crystals into usable crystal stock.
- **Hangar**: Restricted to `LARGE` and `HUGE` hulls only. Dynamic cost scales with hangar slot capacity.
- **Strikecraft Bay**: Requires `MEDIUM`, `LARGE`, or `HUGE` hull. Dynamic cost scales with strikecraft wing slots. Solely responsible for the construction and replenishment of strikecraft wings.
- **Inhibitor Field**: Requires `MEDIUM`, `LARGE`, or `HUGE` hull. Dynamic cost scales with inhibition field radius.
- **Abilities**: Forbidden on `STRIKECRAFT_WING` and `TINY`. Dynamic cost scales with number of equipped abilities.
- **Sensors**: Available on all hull sizes. Dynamic cost scales with short-range radius and long-range hex coverage. Coverage is shared across all allied players.
- **Minelayer**: Forbidden on `STRIKECRAFT_WING` and `TINY`. Deploys tactical minefields that ignore friendly and allied vessels.
- **Marines**: Forbidden on `STRIKECRAFT_WING`. Dynamic cost scales with embarked marine count.
- **Cloaking Device**: Forbidden on `STRIKECRAFT_WING`; `ADVANCED` requires at least `SMALL` hull. **Basic** (10 Hull, 5 AM/turn, 300 credits) hides single unit from long-range sensors; **Advanced** projects an area-of-effect stealth field hiding friendly and allied units within its radius, with hull cost ($R/16.6667$), credit build cost contribution ($\text{Hull} \times 30$), and antimatter drain ($R \times 0.04\text{ AM/turn}$) scaling dynamically with area radius $R$ (baseline 30 Hull, 900 credits, 20 AM/turn at 500 radius).
- **Intelligence**: Forbidden on `STRIKECRAFT_WING` and `TINY`. Dynamic cost scales with agent capacity (5.0 hull per agent, default 2 agents). Optional Counter-Intelligence suite (+10.0 hull, +300 credits) enables active sector counter-espionage sweeps (activated via the component sidebar panel; cost: 100 credits, 25 AM, 3-turn cooldown) to protect friendly and allied assets and eliminate discovered enemy agents.

An Engines component is operational only while it has hit points remaining and
provides a positive effective speed. Destroyed Engines immediately halt and
invalidate sub-light movement until repaired above 0 HP. This does not disable
hex or wormhole jumps performed by an otherwise operational Hyperdrive.

---

## 4. Special Abilities

Tactical positions and ranges use logical sector units (sector radius 5000); renderers convert them to pixels.

<!-- BEGIN GENERATED: abilities -->
There are **10 special abilities** registered in the game.

| Ability | Cooldown (Turns) | Duration (Turns) | Range (logical units) | AM Cost | Required Component | Target Type |
| --- | --- | --- | --- | --- | --- | --- |
| **Adaptive Forcefield** | 8 | 3 | 0.0 | 20 | Defenses | Self |
| **Cluster Warhead** | 5 | 0 | 500.0 | 30 | Weapons | Position |
| **Designate Target** | 6 | 4 | 450.0 | 15 | Sensors | Unit |
| **Ion Bolt** | 7 | 3 | 400.0 | 25 | Weapons | Unit |
| **Missile Batteries** | 10 | 4 | 0.0 | 40 | Weapons | Self |
| **Repair Cloud** | 8 | 4 | 350.0 | 35 | Repair | Self |
| **Capture Unit** | 10 | 0 | 100.0 | 40 | Marines | Unit |
| **Drain Antimatter** | 6 | 0 | 300.0 | 0 | Antimatter Storage | Unit |
| **Microjump** | 5 | 0 | 0.0 | 25 | Hyperdrive | Position |
| **Scan for Minefields** | 6 | 0 | 1500.0 | 35 | Sensors | Self |
<!-- END GENERATED: abilities -->

- **Adaptive Forcefield**: Temporarily raises defensive mitigation against incoming attacks.
- **Cluster Warhead**: Detonates an area-of-effect cluster warhead at the designated coordinate.
- **Designate Target**: Applies +50% turret damage amplification to the marked enemy; contributions from different sources stack additively.
- **Ion Bolt**: Fires an electromagnetic bolt that disables the target's sublight engines and weapons.
- **Missile Batteries**: Deploys autonomous missile platforms that fire coordinated salvos at nearby hostiles.
- **Repair Cloud**: Emits an expanding nanite cloud that continuously repairs adjacent friendly units.
- **Capture Unit**: Launches an armed marine boarding party to commandeer and seize control of an enemy vessel.
- **Drain Antimatter**: Siphons antimatter fuel directly from an enemy unit's storage tanks into your own.
- **Microjump**: Executes an instant tactical micro-hyperjump to any target location in the same sector.
- **Scan for Minefields**: Emits a high-frequency sensor sweep that permanently reveals all enemy minefields within range.

---

## 5. Order Types

<!-- BEGIN GENERATED: order-count -->
The `OrderType` enum defines **34 order types**, including the persistent `STANCE` root.
<!-- END GENERATED: order-count -->

| Order Type | Description |
|---|---|
| `REACH_WAYPOINT` | Direct movement to a single waypoint (system, hex, position). Sub-order spawned by `MOVE`. |
| `MOVE` | High-level multi-leg movement across positions, hexes, or star systems via wormholes. |
| `PATROL` | Repeatedly patrols a looping sequence of waypoint coordinates. |
| `ATTACK` | Moves into weapon range and engages a designated enemy unit until destroyed. |
| `STANCE` | Persistent standing engagement policy. Owns at most one transient `ATTACK` child and is not placed in the explicit queue. |
| `DEFEND` | Holds position at a target location or guards a friendly/allied unit against incoming hostiles. |
| `PROTECT` | Escorts a friendly or allied unit, matching its movement and intercepting hostile attackers. |
| `TOGGLE_INHIBITOR` | Activates or deactivates the ship's hyperspace inhibition field emitter. |
| `COLONIZE` | Disembarks colonists from a colony ship to establish a settlement on a habitable body. |
| `LOAD_COLONISTS` | Embarks population from a friendly or allied colonized celestial body onto a colony transport. |
| `CONSTRUCT` | Deploys a constructor to build a new space station, structure, or starship (excluding strikecraft wings). |
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
| `INFILTRATE_UNIT` | Deploys a covert agent onto an enemy vessel within operational range (500 logical units). |
| `INFILTRATE_PLANET` | Deploys a covert agent onto an enemy colonized celestial body within operational range. |
| `RELOCATE_AGENT` | Moves an embedded agent from their current host to another enemy unit or colony in operational range. |
| `SABOTAGE` | Commands an embedded agent to sabotage host unit subsystems or colonial infrastructure. |
| `CI_SWEEP` | Counter-Intelligence ship performs an active sector sweep (activated via component sidebar panel; cost: 100 credits, 25 AM, 3-turn cooldown) to detect enemy spies on friendly and allied assets within operational range (500 logical units). |
| `ELIMINATE_AGENT` | Counter-Intelligence ship neutralizes and removes a discovered enemy agent from a friendly or allied unit or colony. |
| `EXTRACT_AGENT` | Recovers an owned embedded agent into a selected owned Intelligence unit with free capacity. |
| `ENTER_GAS_GIANT` | Commands an eligible ship with operational engines to submerge into a gas giant atmosphere, vanishing from map display and sensor detection. |
| `LEAVE_GAS_GIANT` | Commands a submerged ship to emerge from a gas giant atmosphere on a random vector outside the collision boundary. |

---

## 6. Universe Objects & Celestial Bodies

All world entities derived from `GameObject` use positive integer IDs for newly
constructed objects, beginning at `1` in a fresh process. IDs are opaque and
saved games preserve their original values; legacy saves may therefore still
contain ID `0`. Code uses `None`, rather than zero, to represent a missing
object or target ID.

### 6.1 Central Stars (`StarType`)
Every star system contains a central star with a unique antimatter harvesting rate multiplier (`constants.py: STAR_HARVEST_MULTIPLIERS`). Central stars are solid celestial obstacles with a physical **Collision Radius** of **750.015 logical units** (`STAR_RADIUS`):

| Star Type | Enum Member | Harvest Multiplier | Color (RGB) | Inhibition Radius | Collision Radius |
|---|---|---|---|---|---|
| **Pulsar** | `PULSAR` | **2.5×** | (225, 110, 255) | 3375.0 | 750.015 |
| **Blue Giant** | `BLUE_GIANT` | **2.0×** | (173, 216, 255) | 3750.0 | 900.0 |
| **Neutron Star** | `NEUTRON_STAR` | **1.8×** | (200, 245, 255) | 3375.0 | 750.015 |
| **Yellow Giant** | `YELLOW_GIANT` | **1.5×** | (255, 195, 0) | 3375.0 | 750.015 |
| **Red Giant** | `RED_GIANT` | **1.3×** | (235, 50, 35) | 3750.0 | 900.0 |
| **G-Type (Sol-like)** | `G_TYPE` | **1.0×** (Baseline) | (255, 235, 120) | 3375.0 | 750.015 |
| **White Dwarf** | `WHITE_DWARF` | **0.8×** | (240, 248, 255) | 3375.0 | 750.015 |
| **Protostar** | `PROTOSTAR` | **0.7×** | (255, 140, 0) | 3375.0 | 750.015 |
| **Red Dwarf** | `RED_DWARF` | **0.5×** | (255, 127, 80) | 3375.0 | 750.015 |
| **Brown Dwarf** | `BROWN_DWARF` | **0.3×** | (160, 82, 45) | 3375.0 | 750.015 |
| **Black Hole** | `BLACK_HOLE` | **0.1×** | (75, 35, 100) | 4500.0 | 750.015 |

### 6.2 Planets & Colonizable Bodies
- **Planets (`PlanetType`)**: Nine planetary classes have distinct population caps, growth rates and yields; see the canonical [planetary traits table](#121-planetary-classification--traits). Gas giants are non-colonizable and support [atmospheric hiding](#125-gas-giant-atmospheric-hiding). Inhibition radius: 3000.0 logical units (Ferrous: 3250.0, Gas Giant: 3500.0). Collision radius: `PLANET_RADIUS` (562.50), or 675.0 for gas giants.
- **Moons (`Moon`)**: Colonizable satellites. Newly generated moons occupy empty hexes exactly one hex from a planet in the same system, including gas giants. Moon spawns are skipped when no eligible hex remains or the system has no planets. Existing saves retain their moon positions. Inhibition radius: 2250.0 logical units. Collision radius: `MOON_RADIUS` (125.01).
- **Colonizable Asteroids (`ColonizableAsteroid`)**: Habitable asteroid outposts. Inhibition radius: 1500.0 logical units. Collision radius: `ASTEROID_RADIUS` (75.015). Population limits for both satellites and outposts appear with the planetary traits below.

### 6.3 Resource & Spatial Phenomena
- **Metal Asteroids (`MetalAsteroid`)**: Non-colonizable mineral bodies providing a sustainable source of raw **Metal** (yield: 10.0/turn). Inhibition radius: 1500.0 logical units. **Collision Radius**: **75.015 logical units** (`ASTEROID_RADIUS`).
- **Comets (`Comet`)**: Pristine icy bodies yielding raw **Crystal** (yield: 10.0/turn). Inhibition radius: 1000.0 logical units. **Collision Radius**: **75.015 logical units** (`COMET_RADIUS`).
- **Wormholes (`Wormhole`)**: Natural spacetime conduits linking star systems. Traversal requires an Advanced Hyperdrive. Visual radius: 291.66 logical units. Inhibition radius: 1875.0 logical units. **Collision Radius**: **0.0 logical units** (permeable).
- **Asteroid Fields (`AsteroidField`)**: Dense clusters of rocky fragments. Effects radius: 3600.0 logical units. Sublight speed drag: 25% (strikecraft wings exempt). Hyperspace inhibition: none (0.0 logical units). **Collision Radius**: **0.0 logical units** (permeable for passable hulls).
- **Ice Fields (`IceField`)**: Dense fields of volatile ice particles. Effects radius: 3600.0 logical units. Sublight speed drag: 20% (strikecraft wings exempt). Hyperspace inhibition: none (0.0 logical units). **Collision Radius**: **0.0 logical units** (permeable for passable hulls).
- **Debris Fields (`DebrisField`)**: Remnants of past orbital battles or derelict structures. Effects radius: 2000.0 logical units. Sublight speed drag: 25% and high-speed abrasion hazard (speed > 50 inflicts 2 HP damage/turn; strikecraft wings exempt from both). Hyperspace inhibition: none (0.0 logical units). **Collision Radius**: **0.0 logical units** (permeable for passable hulls).
- **Nebulae (`Nebula`)**: Vast interstellar clouds with 4 distinct elemental subtypes (`HYDROGEN`, `NITROGEN`, `OXYGEN`, `DUST`). Visual radius: 3600.0 logical units. **Collision Radius**: **0.0 logical units** (permeable). Naturally conceals starships positioned within its cloud boundaries from enemy long-range (inter-sector) sensors.
- **Space Storms (`Storm`)**: Hazardous energetic disturbances with 3 environmental subtypes (`PLASMA`, `MAGNETIC`, `RADIATION`). Visual radius: 3600.0 logical units. **Collision Radius**: **0.0 logical units** (permeable for standard starships; Magnetic Storms act as impassable collision obstacles for strikecraft wings, and launching wings within them is banned).

### 6.4 Celestial Body Dimensions & Obstacle Classification Summary

| Entity Class | Solid Obstacle? | Collision Radius (logical units) | Inhibition Radius (logical units) | Effect Radius (logical units) | Harvest / Resource Yield | Colonizable |
|---|---|---|---|---|---|---|
| `Star` | **Yes** | 750.015 (`STAR_RADIUS`, Giants: 900.0) | 3375.0 (Black Hole: 4500.0, Giants: 3750.0) | — | 0.1× – 2.5× Antimatter | No |
| `Planet` | **Yes** | 562.50 (`PLANET_RADIUS`, Gas Giant: 675.0) | 3000.0 (Ferrous: 3250.0, Gas Giant: 3500.0) | — | — | Varies; see §12.1 |
| `Moon` | **Yes** | 125.01 (`MOON_RADIUS`) | 2250.0 | — | — | Yes; see §12.1 |
| `ColonizableAsteroid` | **Yes** | 75.015 (`ASTEROID_RADIUS`) | 1500.0 | — | — | Yes; see §12.1 |
| `MetalAsteroid` | **Yes** | 75.015 (`ASTEROID_RADIUS`) | 1500.0 | — | 10.0 Metal / Turn | No |
| `Comet` | **Yes** | 75.015 (`COMET_RADIUS`) | 1000.0 | — | 10.0 Crystal / Turn | No |
| `Wormhole` | No | 0.00 (Permeable) | 1875.0 | — | Inter-System Travel | No |
| `AsteroidField` | No | 0.00 (Permeable) | 0.0 | 3600.0 (`ASTEROID_FIELD_RADIUS`) | — | No |
| `IceField` | No | 0.00 (Permeable) | 0.0 | 3600.0 (`ICE_FIELD_RADIUS`) | — | No |
| `DebrisField` | No | 0.00 (Permeable) | 0.0 | 2000.0 (`DEBRIS_FIELD_RADIUS`) | — | No |
| `Nebula` | No | 0.00 (Permeable) | 0.0 | 3600.0 (`NEBULA_RADIUS`) | 0.4× AM (Hydrogen) | No (Long-Range Stealth) |
| `Storm` | No | 0.00 (Permeable) | 0.0 | 3600.0 (`STORM_RADIUS`) | — | No |

---

## 7. Enums Quick Reference

### Unit Stances (`UnitStance` — 5 total)
- `DO_NOTHING`: Hold fire and ignore hostile units unless directly ordered.
- `ATTACK_WEAPON_RANGE`: Engage hostile units that enter weapon range.
- `ATTACK_SAME_SECTOR`: Intercept and engage any hostile unit detected in the same sector hex.
- `ATTACK_INTRA_SYSTEM_JUMP_RANGE`: Jump to engage hostile units in adjacent sectors within basic hyperdrive range.
- `ATTACK_SAME_SYSTEM`: Jump to engage hostile units anywhere within the star system.

Each Commander keeps two independent layers. `current_order` and `orders_queue`
contain only explicit player/AI work. A persistent `StanceOrder` is the standing
policy and may own the transient hierarchy `STANCE → ATTACK → MOVE →
REACH_WAYPOINT`. Any explicit order suspends that engagement and starts
immediately when there is no other explicit current order; Shift only queues an
explicit order behind other explicit orders. Changing stance never interrupts
foreground work, and the new policy takes effect once the explicit queue is
empty. **Stop Unit** and the public `cancel_orders` command cancel both layers,
clear fire/navigation targets, and select `DO_NOTHING`.

All turret fire requires an `IN_PROGRESS` Attack order on the active root's
front-child chain. Direct Attack orders remain authoritative while executing
their approach movement. Stance, Patrol, Protect, and Defend authorize fire only
through their active front Attack child. A cached turret target, a queued Attack,
or a suspended/cancelled subtree never authorizes fire. Stance targets must remain
visible enemies inside the selected vigilance boundary; leaving it recursively
cancels the pursuit before movement is resolved. Direct Attack orders are not
restricted by the selected stance boundary.

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

### Spawn Profiles (`SpawnProfile` — 2 total)
- `NORMAL`: Standard 4X gameplay setup. Each player begins in their own distinct star system with an owned homeworld planet (starting population capped to that planet's capacity) and 4 core starter units spawned in orbit around the homeworld:
  1. Starting Constructor Station (`SHIPYARD_MK1`)
  2. Constructor Ship (`CONSTRUCTOR_MK1`)
  3. Colonizer Ship (`COLONIZER_MK1`)
  4. Antimatter Harvester Ship (`ANTIMATTER_HARVESTER`)
- `TESTING`: Sandbox setup. Unassigned players share `Sol` (or the first available system); specified homes may also share systems. Each player receives testing ships and stations across all sizes (`TINY`..`HUGE`) and a carrier.

Both profiles select only unowned, colonizable planets and retain their planetary type. If none is available, setup creates a Terran fallback in an empty noncentral sector; without a valid sector, setup fails. Starting population must be non-negative and is capped to the selected world's capacity.

Normal requires at least as many requested and actual systems as players, unique specified home systems, and enough unclaimed systems for all random assignments. Unknown assignments and generation shortfalls produce actionable errors. Map-only previews validate generation independently of player starts. Immediately before starting, the same rules are rechecked by the wizard, control interface and direct setup. Preparation copies previews, isolates ID allocation, and validates homeworld references and starter fleets before replacing the live campaign, resetting AI or closing the wizard. A preparation failure preserves the campaign, preview, counters and AI state. These new-game restrictions do not prevent loading older shared-start saves.

---

## 8. Architecture & Subsystems

Domain types now live in `domain` groups, with explicit lazy compatibility exports
through `entities`, `unit_orders` and `unit_components`. Core imports require no
Pygame/GUI/display initialization. `Game` discovers or accepts an immutable
`DisplayConfig` during construction and provides it to presentation and input code;
display values in `constants.py` are fixed compatibility defaults. Runtime turn
presentation uses an optional `TurnPresentation` adapter. See [Development and
Testing](#development-and-testing) for import-boundary checks and quality gates.

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
- **Inter-system Routing (`pathfinding.py`)**: Unweighted Dijkstra selects shortest feasible system routes; intra-system jump waypoints use cube-coordinate interpolation on the hex grid.
- **Order System (`order_system.py`)**: Adapts human events into order issuance. Commander owns explicit queue promotion and stance arbitration; Order owns subtree status/cancellation and outcome recording; concrete orders own movement, continuous loops and actuator/job cleanup.
- **Field Refitting System (`unit_orders/refit.py`, `unit_components/constructor.py`)**: Enables units with a `Constructor` to dynamically install components onto, or strip components from, friendly and allied units within build range (500 logical units). Component addition costs `Used Hull × 30` credits and requires `max(1, round(Hull / 5))` turns. Component removal takes 1 turn and grants an immediate 50% salvage credit refund. Orders automatically enforce hull size restrictions, headroom limits, and docked carrier craft safety checks, prepending `MoveOrder` approach sub-orders if out of range.
- **Visibility & Sensor Sharing (`visibility.py`)**: Computes sector-by-sector and in-hex sensor horizons. Generates fog-of-war masks, unifies short-range and long-range sensor coverage across all allied players, shares stealth area cloaking protection, conceals units inside nebulae from long-range sensors, and persists last-known sector intel per player.
- **Diplomacy & Team System (`entities.py`, `game_settings.py`, `game_setup.py`, `save_manager.py`)**: Manages static multi-team configurations established during game setup. Evaluates relations (`is_allied_with`, `is_enemy_of`) to govern sensor sharing, tactical combat engagement, logistics sharing, area buffs, friendly fire prevention, and covert espionage targeting.
- **Sub-light Navigation & Celestial Collision Avoidance (`geometry.py`, `unit_orders/movement.py`)**: Verified tangent-polygon routes avoid expanded solid bodies and hull-blocking fields within the sector boundary; see [collision avoidance](#11-celestial-collision-avoidance).
- **GUI & Renderer Packages (`gui/`, `rendering/`)**: Strict facade pattern isolating UI widget hierarchies and layout managers from pygame-ce rendering loops and mathematical spatial transformations. System and sector views maintain independent transient cameras with cursor-anchored smooth zoom, middle-drag and arrow-key panning; newly opened systems auto-fit inside the HUD-free gameplay rectangle. The galaxy renderer highlights player home systems dynamically using each player's faction color, rendering concentric circles for systems containing multiple player homeworlds.
- **Two-Stage Campaign Setup & Home Star System Assignment (`gui/layout_new_game_wizard.py`, `game_settings.py`, `game_setup.py`)**: Stage 1 generates and previews the map; Stage 2 configures factions, economy and home assignments. Specified homes must be distinct for Normal and may be shared for Testing. An isolated campaign is validated before commit; see [spawn profiles](#spawn-profiles-spawnprofile--2-total).
- **Resolution Independence (`display_config.py`, `gui/theme_loader.py`)**: Uses per-application metrics for rendering, camera transforms and input. Each UI manager receives a fresh theme scaled to its resolution, absolute bundled font paths and idempotent rich-text font preloading. No generated theme file is written. Retrofit turret summaries wrap to measured text width.

### Configuration and Data Files

- `data/` contains bundled unit templates, spawn rates, and star names. Custom designs use the [user-data library](#custom-design-storage-and-migration).
- `constants.py` provides game tuning constants, colors, and fixed compatibility display defaults; importing it does not discover or initialize a display.
- `display_config.py` defines immutable per-application resolution and UI metrics. `Game(display_config=DisplayConfig(1920, 1080, False))` accepts explicit dimensions; otherwise bootstrap discovers the display.
- `WORMHOLE_FULLSCREEN=true` forces full-screen display mode.

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
- **Deployment Range**: Standard operational range is **500.0 logical units**.
- **Real-Time Execution**: When issuing an intelligence command within operational range in the same sector, the order executes immediately in the current frame without requiring the turn to end. If outside range, an approach `MoveOrder` is automatically generated and executed.
- **Relocation & Extraction**: Agents can transition directly between enemy hosts in range via `RelocateAgentOrder` or be recovered back into an Intelligence vessel via `ExtractAgentOrder`.

### 9.3 Sensor Sharing & Fog of War
- **Covert Sensor Reconnaissance**: Embedded agents grant their owner full access to the host unit or colony's sensor horizon.
- **Visibility & Rendering**:
  - `VisibilityService` incorporates short-range and long-range sensor coverage of all infiltrated targets.
  - Sector view Fog-of-War cutouts immediately reveal the area around infiltrated enemy units and celestial bodies (500-logical-unit radius for colonies).
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
- **Active CI Sweeps (`CISweepOrder`)**: A vessel equipped with a Counter-Intelligence suite performs an area-of-effect sector sweep within operational range (500 logical units) activated via the Intelligence component panel in the sidebar. The sweep reveals all enemy agents embedded on friendly and allied ships or colonies in range, setting `agent.is_discovered = True`. Sweeps cost **100 credits** from the treasury, **25 AM** from the ship's tanks, and trigger a **3-turn cooldown** on the vessel. Passive turn-tick detection is not present—enemy agents remain hidden unless actively swept.
- **Elimination (`EliminateAgentOrder`)**: Counter-Intelligence ships within the 500-logical-unit operational range can neutralize and remove any discovered enemy agent from friendly and allied assets.
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
  - Short-range sensor horizons (logical sector units) and long-range radar hex coverage are fully shared across all allied players.
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

### 10.6 Inter-Player Communications & Markdown Persistence
- **Transmission Threads (`Conversation`)**: Diplomatic messages between pairs of players are tracked in chronological order within `Conversation` entities (`Message` dataclass).
- **Real-Time Markdown Logging**: Every transmission sent via the Comms menu or AI agents (`send_message`) is appended in real-time to `saves/comms.md` with turn number, ISO 8601 UTC timestamp, sender/recipient names, IDs, team affiliations, and message text.
- **Campaign Save Sidecars**: When saving campaigns (`save_game_to_file`), complete campaign transmission logs are atomically exported to `saves/comms/<campaign_id>/comms.md`.

### 10.7 Save Format 4.0 Integrity

Components own versioned state codecs, including common hull cost and subsystem
HP, complete turret layouts/cooldowns, ability definitions and runtime timers,
and construction/refit progress. Current-format units restore their exact
installed inventory independently of template files.

Commander saves its stance under `configuration` and explicit `current_order`
and `orders_queue` under `runtime`. Public order UUIDs, descendants, resource
charges/refunds, and bounded outcome history persist. Active orders rebind
actuators without replaying startup side effects; transient stance engagements
are reacquired through normal play.

Loading migrates and validates an isolated campaign, resolves references, and
rebuilds visibility, spatial inhibition zones, carrier/agent links, and galaxy
indexes before commit. Allocator reconciliation includes minefields and all
nested stored units. Failure leaves the running campaign and AI untouched.
Timed effects have source-owned, idempotent cleanup on expiry, destruction,
component removal/replacement, and load.

Explicit 3.0/3.1/3.2 migrations preserve recoverable state and warn about omitted
legacy fields. Unknown versions and unrecoverable dynamic equipment are rejected.
See [Campaign persistence](SAVE_FORMAT.md) for the schema, migration policy,
transaction boundaries, reconciliation rules, and regression tests.

---

## 11. Celestial Collision Avoidance

### 11.1 Overview & Purpose
In Wormhole Control, ships moving at sub-light speeds navigate tactical sector space (a 5000-logical-unit radius circle per hex). To preserve spatial immersion and tactical realism, units never fly straight through physical solid bodies (such as stars, planets, moons, asteroids, or comets).

The collision avoidance system automatically detects obstructed sub-light trajectories in real-time, calculates verified circumscribed tangent-polygon bypass routes, and injects intermediate waypoint sub-orders into unit order queues without requiring manual player micro-management.

### 11.2 Celestial Body Collision Radii & Classification
Every celestial entity defines a `collision_radius: float` attribute (`entities.py`):

1. **Solid Celestial Obstacles (`collision_radius > 0.0`)**:
   - **Central Star (`Star`)**: `STAR_RADIUS = 750.015` logical units (Giants: `GIANT_STAR_RADIUS = 900.0`)
   - **Planets (`Planet`)**: `PLANET_RADIUS = 562.50` logical units (Gas Giant: `675.0`)
   - **Moons (`Moon`)**: `MOON_RADIUS = 125.01` logical units
   - **Asteroids (`ColonizableAsteroid`, `MetalAsteroid`)**: `ASTEROID_RADIUS = 75.015` logical units
   - **Comets (`Comet`)**: `COMET_RADIUS = 75.015` logical units

2. **Permeable Spatial Phenomena (`collision_radius = 0.0`)**:
   - **Nebulae, Space Storms, Wormholes, Asteroid Fields, Ice Fields, Debris Fields**: Normally permeable. Fields that prohibit the moving hull size and Magnetic Storms for strikecraft are included as collision obstacles; see §12.3–12.4.

3. **Safety Margin**:
   - When checking for collisions and computing avoidance waypoints, the navigation engine adds the shared `NAVIGATION_CLEARANCE` (50.0 logical units) around the obstacle's physical radius:
   $$R_{\text{expanded}} = r_{\text{body}} + \text{margin}$$

Every returned segment is checked against every expanded obstacle and the sector boundary. Tangency is valid within numerical tolerance. The router tries both bypass directions and has bounded search limits; an exhausted or invalid search fails movement with `path_unavailable` instead of reporting an unobstructed route.

Only original endpoints inside physical bodies retain the landing/departure exception for their endpoint segment. A start inside the clearance band must first escape outward; a destination inside that band is rejected. Intermediate waypoints do not receive landing exceptions.

### 11.3 Target-Unit Standoff Arrival
Orders that must approach another unit create target-aware movement through
`MoveOrder.for_unit_approach(...)`. The move stores `target_unit_id` and
`standoff_distance` (defaulting to `DEFAULT_STANDOFF_DISTANCE = 150.0` logical units for escort/protect orders), resolves the final tactical coordinate when route planning
begins, and persists that coordinate as `destination_position`.

- **Same sector (sub-light)**: The destination is the point on the target's
  standoff circle that lies on the mover-target line and is closest to the
  moving unit.
- **Different sector, inhibited target**: The destination lies on the line from
  the inhibition-field center through the target, on the outward side of the
  target's standoff circle. The jump lands just outside the field and the ship
  covers only the remaining distance by sub-light movement.
- **Different sector, uninhibited target**: The destination is a random point
  on the standoff circle that remains inside the sector and outside every
  inhibition field. The resolved random point is retained for the lifetime of
  that `MoveOrder`.

Inhibition fields cannot overlap, so a target or candidate position can be
contained by at most one field. Protect orders maintain the standard 150.0 logical unit standoff perimeter. Attack, Dock, Repair, Refit, resource
transfer, trade, intelligence, and unit-targeted ability orders preserve their
existing operational ranges by supplying those ranges as the standoff distance.

### 11.4 Celestial Body Standoff Arrival (Colonization & Colonist Transfers)
Orders targeting solid celestial bodies (`ColonizeOrder` and `LoadColonistsOrder`) create target-aware approach movement through `MoveOrder.for_celestial_approach(...)`. The move stores `target_celestial_id` and `standoff_distance` (`DEFAULT_STANDOFF_DISTANCE = 150.0` logical units), calculating the arrival coordinate on the standoff perimeter:

$$R_{\text{standoff}} = r_{\text{body}} + \text{DEFAULT\_STANDOFF\_DISTANCE}$$

where $r_{\text{body}}$ is the body's physical collision radius (e.g. `PLANET_RADIUS = 562.5`, `MOON_RADIUS = 125.01`, `ASTEROID_RADIUS = 75.015`).

- **Operational Distance Requirement**: The game demands that the colonizer vessel be within $r_{\text{body}} + \text{DEFAULT\_STANDOFF\_DISTANCE}$ before unloading or embarking population. If outside this range, approach movement sub-orders are automatically planned and executed first.
- **Same sector (sub-light)**: The standoff destination is the point on the body's standoff circle along the mover-target ray closest to the ship.
- **Different sector (intra-system jump)**: The standoff destination is chosen on the side of the celestial body facing the origin sector hex, along the inter-hex displacement vector.
- **Different system (inter-system jump)**: The standoff destination is chosen on the side facing the entry wormhole in the destination system.
- **Collision Safety**: Because the plotted arrival point lies strictly outside the solid body's collision circle, vessels fly directly to the standoff perimeter without penetrating the planet surface or triggering collisions.


## AI order control (observation 5, command contract 3)

Both GPT-5.6 Luna and the Codex socket controller use the same command registry,
observation builder, visibility policy and preflight/commit gateway. Socket protocol 2
rejects older clients; [CODEX_CONTROL.md](CODEX_CONTROL.md) contains examples and recovery rules.

Friendly observations separate standing policy/engagement from explicit current and queued
orders. Explicit Move suppresses stance combat; changing stance preserves explicit work.
`cancel_order` cancels one UUID-identified current/queued root. `clear_explicit_orders`
clears explicit work while preserving stance, whereas `cancel_orders` remains full Stop.
Internal/stance roots cannot be edited individually. Pending construction/refit cancellation
releases only the owning order's job/charge, once; it cannot refund another active job.

AI `patrol` accepts a complete single destination or 1–16 waypoints. It visits the route,
returns to its captured start and repeats. `append_patrol_waypoints` extends a named current
or queued patrol without interrupting its active leg. Ordinary `queue=true` creates a
separate patrol. For human players, the "Add Patrol Waypoint" context menu option
extends an active or queued patrol route, whereas `Shift` consistently queues a new order
(including a new separate patrol) behind existing work. Continuous roots report queue
blocking as guidance rather than forbidding intentional queued work.

Tactical observations include actual turret range/cooldown/target classes, base/effective
sensor and hyperdrive ranges, jump status/functionality, support ranges, defend radius and
cloak status/upkeep. Supported hardware is distinguished from current issuance legality.
Friendly/allied turret observations retain `cooldown` (base) and `cooldown_remaining`, and add `effective_cooldown` (reset if fired here). Already-exposed celestial bodies include numeric `environmental_effects` where applicable. These additive fields retain observation schema 5, command contract 3 and socket protocol 2. Enemy Intelligence components are hidden in observations and subsystem menus; hidden and
nonexistent target guesses receive indistinguishable public errors. Hidden target-derived
movement geometry is redacted; explicit player coordinates remain order intent. No raw
persistence or sidebar state is serialized into AI observations.

The top-level `intelligence` observation exposes owned agents with source unit, public host,
and current sabotage, plus discovered enemy agents hosted by friendly or allied assets. It
never reveals an owned agent's discovery status, an enemy agent's source/sabotage, allied
agent identities, or undiscovered-agent counts. `player_commands` supplies bounded sabotage
and relocation choices. Owned Intelligence/CI unit capability details supply capacity,
range, infiltration/extraction targets, sweep readiness/cost/cooldown, and eliminable agent
IDs. Luna and Codex can issue `infiltrate_unit`, `infiltrate_planet`, `sabotage`,
`relocate_agent`, `extract_agent`, `ci_sweep`, and `eliminate_agent` through the same gateway.

Preflight is atomic. Commit exceptions can leave partial effects: results identify completed,
failed (uncertain), and unattempted operations, with accurate command indices. There is no
rollback or automatic retry. Codex must obtain a fresh observation; Luna offers manual recovery
and never applies a rejected memory patch. Command issuance is distinct from completion.

Save 4.0 retains the public UUID persistence introduced in 3.2 (including serialized descendants and docked units) plus each
player's last 128 lifecycle events, further limited to 32,000 serialized characters. Events
record completed/failed/cancelled roots exactly once with bounded reason codes and monotonic
IDs. Legacy saves receive new UUIDs and empty journals. Stance engagements remain transient.
Expanded observation suborders are limited to 32 nodes per unit/depth 6; all explicit root IDs
remain available. Waypoint previews are limited to 16; omitted counts are explicit.

---

## 12. Celestial Bodies & Environmental Mechanics

### 12.1 Planetary Classification & Traits

Every planet generated in the galaxy possesses distinctive biological and geological traits defined in `PLANET_TRAITS`:

<!-- BEGIN GENERATED: planets -->
| Planet Type | Colonizable | Max Population | Growth Rate | Passive Metal | Passive Crystal | Antimatter Multiplier |
| --- | --- | --- | --- | --- | --- | --- |
| **Terran** | Yes | 100.0 | 2% / turn | 0.0 | 0.0 | 0.0x |
| **Oceanic** | Yes | 120.0 | 2.5% / turn | 0.0 | 0.0 | 0.0x |
| **Desert** | Yes | 75.0 | 1.5% / turn | 0.0 | 0.0 | 0.0x |
| **Ice** | Yes | 60.0 | 1% / turn | 0.0 | 2.0 | 0.0x |
| **Barren** | Yes | 40.0 | 0.8% / turn | 0.0 | 0.0 | 0.0x |
| **Volcanic** | Yes | 50.0 | 0.8% / turn | 5.0 | 0.0 | 0.0x |
| **Ferrous** | Yes | 70.0 | 1.2% / turn | 8.0 | 0.0 | 0.0x |
| **Greenhouse** | Yes | 35.0 | 0.5% / turn | 0.0 | 3.0 | 0.0x |
| **Gas Giant** | No | 0.0 | 0% / turn | 0.0 | 0.0 | 0.0x |
<!-- END GENERATED: planets -->

- **Terran**: Balanced biosphere with standard habitability.
- **Oceanic**: High carrying capacity and rapid population expansion.
- **Desert**: Arid wasteland with restricted water reservoirs.
- **Ice**: Glaciated crust yielding passive crystal extraction.
- **Barren**: Airless rock requiring pressurized dome complexes.
- **Volcanic**: Geothermal magma chambers rich in raw minerals.
- **Ferrous**: Massive heavy-metal mantle generating industrial iron.
- **Greenhouse**: Superheated dense atmosphere yielding synthetic crystal.
- **Gas Giant**: Atmospheric hiding cover; 3500 inhibition.

- **Moons & Colonizable Asteroids**: Both support colonization. Moons have a population cap of 50.0 and growth of 1.0% per owner turn; colonizable asteroids have a cap of 20.0 and growth of 0.5% per owner turn.
- **Population bounds**: Starting planets use the smaller of requested population and their cap. Existing over-cap planetary populations are clamped before growth or growth-sabotage checks, so sabotage cannot preserve an overflow.
- **Passive Resource Yields**: Colonized planets generate their passive metal or crystal directly into the owner's treasury at the end of each turn, providing strategic economic value beyond direct taxation.

### 12.2 Extreme Star Remnants

Stars anchor the gravitational and hyperspace topology of star systems:
- **Black Hole**: Extreme gravitational anomaly. Features an event horizon of 750 logical units radius that inflicts 15 damage per turn to all vessels within it. Projects an expansive hyperspace inhibition field of 4500 radius. Minimum fuel harvesting multiplier (0.1x).
- **Pulsar**: High-energy neutron star with intense rotational sweeps. Drains 5% of a ship's current antimatter reserves per turn when within the sector. Yields a massive fuel harvesting multiplier (2.5x).
- **Giant Stars (Blue Giant, Red Giant)**: Massive stellar radius (900.0 physical collision radius) with extended hyperspace inhibition fields (3750 radius).

### 12.3 Environmental Fields & Tactical Cover

<!-- BEGIN GENERATED: environment -->
| Density | Ice beam cover | Debris kinetic/missile cover |
| --- | --- | --- |
| Low | 5% | 5% |
| Medium | 10% | 10% |
| High | 15% | 15% |

| Environment | Combat modifier |
| --- | --- |
| Ice field | -1 turn to cooldown reset when firing |
| Nitrogen nebula | -1 turn to cooldown reset when firing |
| Oxygen nebula | 1.15x splash damage taken |
<!-- END GENERATED: environment -->
 
- **Selection & Interaction**: Non-solid celestial bodies (Asteroid Fields, Ice Fields, Debris Fields, Nebulae, and Storms) are atmospheric and environmental regions with `is_solid = False`. They cannot be selected by clicking inside their area in the sector view canvas, preventing accidental click interception and preserving open tactical movement/patrol clicks. They are inspected and selected exclusively via the sidebar panel of their containing hex. In Sector View, all non-solid bodies are visually rendered with an exact-radius turquoise circle (`TURQUOISE = (64, 224, 208)`) marking their physical boundary and area of effect for the player. AI agents observe `is_solid = False` and the exact `effect_radius` for these bodies in system observations.
- **Hull Size Access Gating**:
  - `FieldDensity.LOW`: Max allowable hull is `HullSize.LARGE` (blocks `HUGE` ships and stations).
  - `FieldDensity.MEDIUM`: Max allowable hull is `HullSize.MEDIUM` (blocks `LARGE` and `HUGE`).
  - `FieldDensity.HIGH`: Max allowable hull is `HullSize.SMALL` (blocks `MEDIUM`, `LARGE`, and `HUGE`).
  - `STRIKECRAFT_WING` wings can enter and traverse fields of any density level.
  - Impassable fields act as physical collision obstacles for waypoint routing, halt movement at the boundary with `"hazard_blocked"`, and block microjumps and carrier deployments.

- **Asteroid Field**:
  - **Tactical Radar Stealth**: Conceals all ships inside the field from enemy long-range sensor presence detection.
  - **Navigation Resistance**: Sublight speed drag scaled by density (LOW: 0.85x, MEDIUM: 0.75x, HIGH: 0.65x).
  - **Mining Target**: Non-mineable for raw metal (raw metal extraction is strictly exclusive to concentrated `MetalAsteroid` bodies).
  - **Inhibition**: No hyperspace inhibition (0.0 radius).
- **Ice Field**:
  - **Tactical Cover**: Dense cryogenic ice particles scatter coherent energy, providing beam defense mitigation (see the generated density table above).
  - **Cooling Aid**: Ice and nitrogen coolant reduce the reset cooldown when a turret fires, using the values above. Apply cooling after turret-variant scaling, with a minimum positive reset of one turn; existing zero-cooldown designs remain zero. Overlapping coolant sources do not stack. The normal owner-turn tick is unchanged, and entering or leaving a field never recalculates a running cooldown. All turret types and hull classes benefit; ability cooldowns are unaffected.
  - **Navigation**: Sublight speed drag scaled by density (LOW: 0.90x, MEDIUM: 0.80x, HIGH: 0.70x; strikecraft wings exempt). No hyperspace inhibition (0.0 radius). Non-mineable for crystal.
- **Debris Field**:
  - **Tactical Cover**: Dense wreckage fragments intercept ballistic projectiles, providing kinetic and missile defense mitigation (see the generated density table above).
  - **Navigation Hazard**: Moving at high sublight velocities (`speed > 50.0`) through the debris causes abrasive hull damage scaled by density (LOW: 1 HP, MEDIUM: 2 HP, HIGH: 3 HP per turn; strikecraft wings exempt).
  - **Navigation Drag**: Sublight speed drag scaled by density (LOW: 0.85x, MEDIUM: 0.75x, HIGH: 0.65x; strikecraft wings exempt). Non-mineable. No hyperspace inhibition (0.0 radius).

### 12.4 Nebulae & Space Storm Hazards

- **Nebulae** (`radius = 3600.0` logical units):
  - **All Nebulae**: Defeat long-range sensor detection, concealing ships from enemy presence radars.
  - **Hydrogen Nebula**: High molecular fuel density allows Antimatter Harvesters to scoop fuel at 0.4x base harvest rate; ships traveling inside burn 50% less antimatter during sublight propulsion (`HYDROGEN_NEBULA_AM_BURN_MOD = 0.5`).
  - **Nitrogen Nebula**: Uses the same non-stacking on-fire turret cooling rule as ice fields (see §12.3).
  - **Oxygen Nebula**: Amplifies splash damage against a victim inside its radius (see the generated multiplier in §12.3). Cluster Warhead is currently the splash source; ordinary missiles, minefields, hazards and component spillover are unaffected. Apply once after falloff and before existing mitigation, truncating the decimal product to an integer. Overlapping oxygen clouds do not stack. Shields retain mitigation strength and have no regenerating health pool.
  - **Dust Nebula**: Dense particulate scatter reduces short-range visual sensor radius by 30% (`DUST_NEBULA_SENSOR_MOD = 0.70`).
- **Space Storms** (`radius = 3600.0` logical units):
  - **Plasma Storm**: Inflicts 8 thermal damage per turn to unit hit points.
  - **Magnetic Storm**: Drains 6 antimatter per turn from onboard reserves; violent electromagnetic flux completely scrambles long-range radar projection from within the storm. Strikecraft wings are strictly banned from entering or launching within Magnetic Storms.
  - **Radiation Storm**: Energetic cosmic radiation inflicts 4 damage per turn to a random functional unit component, degrading subsystem integrity.


Environmental queries use the current sector and include points exactly on the body radius. Hidden and docked units receive no external modifiers. Base turret cooldowns and remaining cooldowns retain their existing save 4.0 fields; location-derived modifiers are recomputed.

### 12.5 Gas-Giant Atmospheric Hiding

Ships with operational sublight engines (`TINY` through `HUGE`) can enter gas giants. Strikecraft wings and stationary stations cannot. Hidden ships disappear from enemy sensors and tactical maps, cannot interact with outside space or project fields, and cannot be attacked from outside. Opposing hidden ships cannot detect or attack one another. Upkeep and existing ability timers continue.

Entry and departure complete their explicit roots exactly once. Both preserve stance policy and queued orders. Hidden ships pause outside-space work and execute only a front-of-queue Leave. Strict FIFO applies: **Enter → Leave → Move** resumes movement after departure; **Enter → Move → Leave** stays blocked until the player cancels or replaces the blocking work. Queue-edit commands remain available while hidden; saving and loading preserves the pause.

Departure searches the ring at the planet's collision radius plus `NAVIGATION_CLEARANCE`, currently 725 logical units for gas giants. It tries 64 random bearings, then a deterministic one-degree sweep. Each candidate must lie inside the sector's 20-unit inset, clear expanded solid bodies and hull-blocking fields, and remain at least `NAVIGATION_CLEARANCE` (50 units) from every deployed living ship center. Successful placement commits immediately so later departures cannot reuse occupied positions. If no candidate passes, Leave fails with `path_unavailable`; the ship remains hidden and its remaining queue is preserved.

## 13. Damage & Minefield Resolution

### 13.1 Full Damage Absorption

Non-positive incoming hull damage is a no-op. Environmental cover, defenses and damage reduction retain their existing mitigation order and integer rounding. Effective damage reduction is bounded to `[0, 1]`; it cannot increase damage or heal a ship. Positive hits can be fully absorbed, including fractional reductions that round down to zero. There is no one-HP minimum after mitigation.

### 13.2 Minefield Cadence

After movement on each ship owner's turn, every living, deployed ship is checked at its final position, including stationary ships. Each overlapping enemy field can detonate against that ship once in this phase, subject to remaining mines. Owner and allied ships are excluded; anti-ship and anti-strikecraft subtype targeting, damage, depletion and destruction rules still apply. Hidden and docked ships do not trigger fields.

This is a position check: crossing a field without ending inside it does not trigger a mine. Damage and mine consumption per owner turn do not increase when more players join the campaign.


## Runtime storage and API failure contracts

### Custom-design storage and migration

Custom designs are stored as `custom_unit_templates.json` in:

- Windows: `%LOCALAPPDATA%/WormholeControl` (fallback: `~/AppData/Local/WormholeControl`).
- macOS: `~/Library/Application Support/WormholeControl`.
- Linux: `$XDG_DATA_HOME/WormholeControl` (fallback: `~/.local/share/WormholeControl`).

Set `WORMHOLE_USER_DATA_DIR` to an **absolute directory path** to use another location. Tests automatically use temporary user storage, including child processes.

Fresh installations start with an empty custom-design library. On first use, when no user library exists and a legacy `data/custom_unit_templates.json` file is present, the game validates the complete library before copying it. It leaves the original bytes intact. An existing user library, including an empty one, always takes precedence. Migration preserves historical designs even if later balance changes put them over today's hull budget; editing and saving still uses current design validation.

Malformed libraries and storage failures are reported in the log. Repair a malformed library and restart the game to reload it; the persistence failure contract below describes how failed operations preserve existing state.

**Upgrade sequence:** The legacy library has been removed from version control. An existing user-data library is retained. Users upgrading from a version that stored designs in the checkout should back up that file before updating, then copy it into their user-data directory while the game is closed. Migration support remains available if a legacy file is supplied; it never overwrites an existing user library.

`CustomTemplateManager(data_file=..., legacy_file=...)` supports isolated libraries; an explicit data path disables automatic legacy discovery.

### Persistence and API failure behavior

Design saves, renames, and deletions persist through atomic replacement before updating the manager or `UNIT_TEMPLATES`. Successful return values and validation-error lists are unchanged. Storage failures raise `TemplatePersistenceError`, which the editor displays without reporting success. Loading reports failures through `last_load_error` and logging, retaining existing state and blocking subsequent writes until a successful reload. Failed saves, renames, and deletions preserve the previous disk library and registered designs.

Missing-hex lookups return empty lists; valid lookups return the live sector collections. Inter-system transfers return `False` for unknown systems or invalid destination hexes without changing unit location or membership. `ControlService(host=...)` accepts only `127.0.0.1` and raises `ValueError` for other values before creating a socket.

Unexpected command preparation/commit failures retain their existing public error contracts, atomic preflight, and partial-commit recovery rules. Internal diagnostics include stage, command index/type, exception class, and traceback frame locations only; exception messages, payloads, source lines, observations, memory, and locals are omitted. Resource paths resolve from the application module or PyInstaller bundle, never the working directory. UI themes are scaled in memory; `theme_scaled.json` is no longer generated. Campaign saves and logs keep their existing locations.

### Debug log

Each game run produces a `game.log` text file in the root folder containing the debug log. AI telemetry and developer-feedback files are described under [AI failure behavior](AGENTIC_AI.md#failure-behavior).


## New-campaign validation

The wizard, direct Python setup and control protocol share side-effect-free settings validation. Campaigns require 2–6 players and 5–30 systems; both radius bounds are integers in 3–12 with minimum no greater than maximum. Distances are finite and positive with minimum strictly smaller than maximum; wormhole density is in [0, 1]. Resources are finite and non-negative, and starting population is a non-negative integer. Zero is accepted without replacing it with defaults. Booleans are not numeric settings.

Player names are trimmed, 1–80 characters, unique ignoring case and contain no control characters. Colors are three integer RGB channels in [0, 255]; repeated colors are allowed. Teams use positive integer IDs and at least two teams are required. Controllers, reasoning effort (low/medium/high), repair retries (1–5), spawn profiles and assignment modes must be recognized. Omitted values keep their defaults; invalid values produce explicit errors. Home names must be strings or None, with blank/Random treated as unassigned.

`GameSettings.validation_issues()` returns field/code/message records without mutation; `validate()` retains its list-of-strings interface. Invalid construction raises `SettingsValidationError`, a `ValueError` subclass. `preview_only=True` is a constructor-only map validation mode for previews, not a campaign validation bypass. Preparation always revalidates full settings before isolation and checks the generated topology again before commit. The control adapter retains its envelope and public error codes, including the exactly-one-Codex-player requirement. Save loading does not enforce new-campaign restrictions.

## Development and Testing

### Smoke Tests

For fast verification of clean imports, module boundaries, headless game launch, and test collection:

```bash
# Run the fast import & launch smoke test suite
python -m pytest -m smoke

# Or execute a headless launch smoke test directly
python game.py --smoke-test
```

### Automated Test Suite

The offline pytest suite covers gameplay rules, saves and migrations, AI command and information boundaries, and GUI interactions. Tests use temporary storage and fake AI providers; no API key is needed.

```bash
pip install -r requirements-dev.txt
python -m pytest
```

CI checks undefined names with Ruff, adds broader lint and type checks at domain boundaries, verifies generated reference blocks, and runs the full suite once on Linux Python 3.10 and 3.14 plus Windows Python 3.14. Clean-process import tests enforce the core/UI boundary. To run launch smoke tests locally, use `python -m pytest -m smoke`. Other local checks:

```bash
python -m ruff check .
python scripts/check_import_boundaries.py
python -m mypy
python scripts/generate_reference.py --check
```

Refresh generated tables with `python scripts/generate_reference.py`. Numeric tables come from runtime constants and registries; explanatory prose remains hand-maintained. The README is hand-maintained and is not a generation target. See [new-campaign validation](#new-campaign-validation) for strict setup rules.

Configuration is specified in `pytest.ini` (`pythonpath = .`, `testpaths = tests`, `markers = smoke`).

Shared scenarios live in `tests/support`; test modules do not import one another.
`tests/conftest.py` configures headless SDL before application imports, isolates
user storage and process state, and owns Pygame/full-game lifecycle fixtures.
Use real entities when testing game rules, and doubles only for collaborators.
Prefer observable outcomes and distinct boundaries over literal tuning values or
implementation call counts. See [Architecture & Subsystems](#8-architecture--subsystems) for the domain and presentation responsibilities those boundaries protect.
