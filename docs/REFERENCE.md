# Wormhole Control — Reference Manual

Current gameplay rules, ship equipment, and operating guidance. Start with the
[README](../README.md) for installation and a short introduction. Technical details
live in [Development](DEVELOPMENT.md), [Agentic AI](AGENTIC_AI.md),
[Codex Control](CODEX_CONTROL.md), and [Campaign persistence](SAVE_FORMAT.md).

## Contents

- [Campaign setup](#campaign-setup)
- [Controls and views](#controls-and-views)
- [Economy and logistics](#economy-and-logistics)
- [Ships and construction](#ships-and-construction)
- [Orders and combat](#orders-and-combat)
- [Abilities](#abilities)
- [Exploration and environments](#exploration-and-environments)
- [Intelligence and teams](#intelligence-and-teams)
- [Storage and troubleshooting](#storage-and-troubleshooting)

## Campaign setup

Click **New Game** to open the two-stage wizard:

1. **Galaxy Setup & Preview:** Configure the map, then click **Generate Map** to
   inspect systems and wormhole routes. Regenerate until satisfied and choose
   **Next: Players & Economy ➔**.
2. **Factions & Starting Conditions:** Choose a spawn profile, configure players,
   teams and resources, and assign home systems. The controller button cycles
   through Human, Codex, AI: Medium, AI: High, and AI: Low.
3. Choose **Random** or **Specified** homes. For specified homes, use the ◀/▶
   buttons or select a system in the preview.
4. Click **Start Game** to begin turn 1. **◀ Back to Map** preserves player choices.

See [automated player setup](../README.md#automated-players) for controller configuration.

### Spawn profiles

**Normal** gives each player a distinct home system, an owned homeworld, and four
starter units: a Shipyard, Constructor, Colonizer, and Antimatter Harvester.
There must be at least as many generated systems as players. Specified homes must
be unique, with enough unclaimed systems left for random assignments.

**Testing** supplies ships and stations across Tiny through Huge hulls, including
a carrier. Unassigned players share Sol, or the first available system; specified
homes may also be shared. Testing designs become buildable only after a Testing
campaign starts. Starting Normal, loading a save, or returning to the main menu
removes them from the construction catalogue while preserving custom designs.
Loading a Testing save keeps existing ships but uses the normal catalogue; see
[Testing campaign saves](SAVE_FORMAT.md#testing-campaign-catalogue) for unfinished builds.

Both profiles choose unowned colonizable planets without changing their types.
If none is available, setup creates a Terran world in an empty noncentral sector;
without such a sector, setup fails. Starting population is capped to the world's
capacity. A failed start leaves the current campaign and map preview intact.

### Setup limits

| Setting | Accepted values |
|---|---|
| Players / systems | 2–6 players; 5–30 systems |
| System radii | Integer minimum and maximum in 3–12; minimum ≤ maximum |
| Inter-system distances | Finite, positive minimum and maximum; minimum < maximum |
| Wormhole density | 0–100% in the wizard; 0–1 in the control interface |
| Starting resources / population | Finite non-negative resources; non-negative integer population |
| Player names | Trimmed, 1–80 characters, unique ignoring case, no control characters |
| Colors | Three integer RGB channels in 0–255; repeated colors are allowed |
| Teams | Positive integer IDs; at least two distinct teams |
| AI settings | Low, Medium or High reasoning; 1–5 repair retries |

Home assignments must refer to generated systems; blank/Random means unassigned.
These limits apply to new campaigns. Loading uses the separate
[save validation rules](SAVE_FORMAT.md#transactional-load).

## Controls and views

| Input | Action |
|---|---|
| Left click | Select a unit, solid body, or destination |
| Shift + left click | Add or remove a unit from the selection |
| Left drag | Box-select units |
| Right click | Open contextual actions or issue a direct command |
| Shift + order | Queue behind existing explicit orders |
| Middle drag / arrow keys | Pan the System or Sector camera |
| Mouse wheel | Zoom the System or Sector camera |
| G / S | Switch to Galaxy / System View |
| E | End Turn |
| Esc | Open the in-game menu, cancel targeting, or deselect |

**Galaxy View** shows known systems, wormhole links and home-system faction markers.
Shared homes have concentric markers. **System View** shows sector hexes, bodies,
routes and fog of war; newly opened systems fit the available map area.
**Sector View** shows individual units, weapon ranges, minefields and tactical movement.
System and Sector views have independent zoom and pan controls. Selected objects
have corner brackets using their owner's faction color.

Inspect non-solid bodies—fields, nebulae and storms—through their hex sidebar.
Clicking inside these regions remains available for movement and targeting.
Their boundary circles show the affected area.

## Economy and logistics

Press **E** or **End Turn** when finished issuing orders. The hot-seat sequence
resolves the active player's movement, mine contacts, income, upkeep, growth and
combat before advancing to the next player.

| Resource | Source and use |
|---|---|
| Credits | Colony taxes, active Civilian Habitats and trade; pay for construction, equipment, upkeep and operations |
| Metal | Mine Metal Asteroids and unload at a Metal Refinery; some colonies also produce it passively |
| Crystal | Mine Comets and unload at a Crystal Refinery; some colonies also produce it passively |
| Antimatter (AM) | Per-ship fuel for movement and equipment; harvest near stars or inside hydrogen nebulae, then transfer to other ships |

**Continuous Mine** fills cargo, unloads at a compatible refinery and repeats.
**Continuous Resupply** alternates harvesting at a star and refueling friendly or
allied ships. **Continuous Trade** travels between active Civilian Habitats in
different sectors; payout scales with distance. A Trade Module requires Engines.

Colony ships settle habitable planets, moons and colonizable asteroids, or load
population from friendly/allied colonies. See [planetary traits](#planetary-traits)
for growth and passive yields. Each populated colony supports `max(1, floor(population / 25))`
modules of each kind: one at 25 population, two at 50. Civilian Habitats use their
owner's colony capacity and provide 50 credits/turn each while active. Orbital
Defense shares capacity across allied colonies and installations, providing its
[equipment bonuses](#component-catalogue) to allies in range.

## Ships and construction

### Unit Designer

Click **Unit Editor** beside **Comms** in any strategic view. Choose a hull,
configure equipment and save a design to make it available for construction.
Custom designs use a separate [user-data library](#custom-design-storage) and are
available to human players only; automated players use public built-in designs.
The Designer and retrofit editor enforce the same complete equipment rules.

### Hull sizes

Hull capacity is the budget for installed equipment. Minimum AM applies when
Antimatter Storage is equipped; it does not require every design to carry a tank.

| Hull | Capacity | Base HP | Minimum AM storage | Base credits | Base build turns |
|---|---|---|---|---|---|
| `STRIKECRAFT_WING` | 7 | 30 | 40 | 50 | 1 |
| `TINY` | 10 | 20 | 60 | 100 | 3 |
| `SMALL` | 25 | 50 | 80 | 250 | 6 |
| `MEDIUM` | 50 | 100 | 100 | 500 | 10 |
| `LARGE` | 100 | 200 | 150 | 1000 | 15 |
| `HUGE` | 200 | 400 | 200 | 2000 | 20 |

- Build credits = base credits + `round(used hull × 30)`.
- Build turns = base turns + `round(used hull / capacity × base turns)`.
- Upkeep = `0.01 × used hull` credits/turn; strikecraft wings are exempt.

### Component catalogue

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
| 18 | `has_inhibitor` | Inhibitor Field | Dynamic | 6.67 |
| 19 | `has_ability_component` | Abilities | Dynamic | 10.0 |
| 20 | `has_sensors` | Sensors | Dynamic | 2.0 |
| 21 | `has_minelayer_component` | Minelayer | Fixed | 15.0 |
| 22 | `has_marines_component` | Marines | Dynamic | 10.0 |
| 23 | `has_cloaking_device` | Cloaking Device | Dynamic | 10.0 |
| 24 | `has_intelligence_component` | Intelligence | Dynamic | 10.0 |
<!-- END GENERATED: components -->

Unless an exception is listed below, utility components require **Small or larger**
hulls. Dynamic costs follow configured performance; fixed costs appear in the table.

- **Engines:** All hulls. Cost is `speed / 20 × hull multiplier`: Wing 0.2,
  Tiny 0.6, Small 0.8, Medium 1, Large 1.5, Huge 2. Wing engines therefore provide
  100 base speed per hull point. XP, sabotage and abilities modify that base speed.
- **Antimatter Storage:** All hulls. Capacity determines cost and must meet the
  hull-specific minimum above. **Antimatter Harvester** collects fuel from stars
  and hydrogen nebulae.
- **Hyperdrive:** Basic requires Tiny or larger and permits intra-system hex
  jumps. Advanced requires Small or larger and also traverses wormholes.
  Wings cannot equip either type.
- **Weapons / Defenses:** All hulls. Weapon cost depends on turret count, damage,
  range and cooldown; defense cost depends on Armor, Shields and Point Defense.
- **Constructor:** Builds Tiny through Huge ships and stations and refits
  friendly/allied units. Wings are produced only by Strikecraft Bays.
- **Repair:** Cost scales with repair rate; restores friendly/allied ships.
- **Colony:** Colonizes habitable bodies and loads population from allied colonies.
- **Civilian Habitat:** Generates income when supported by its owner's populated colony.
- **Orbital Defense:** A supported module provides +20% weapon damage and +20%
  defense mitigation within 500 units. Overlapping auras stack additively.
- **Trade Module:** Requires Engines; earns income between active habitats in
  different sectors.
- **Mining:** Tiny or larger; cost scales with mining rate and cargo capacity.
  **Metal Refinery / Crystal Refinery** process the corresponding mined cargo.
- **Hangar:** Large or Huge only; cost scales with slots. Carries Tiny vessels,
  not strikecraft wings.
- **Strikecraft Bay:** Medium or larger; cost scales with wing slots. Builds,
  carries and replenishes Fighter or Bomber Wings.
- **Inhibitor Field:** Medium or larger. Cost is `radius / 15` hull; active fuel
  consumption is `radius × 0.1` AM/turn. The field must fit inside the sector and
  cannot overlap any natural or artificial inhibition zone. Insufficient fuel
  deactivates it.
- **Abilities:** Cost scales with equipped abilities; prerequisites must also be installed.
- **Sensors:** All hulls. Cost scales with short-range radius and long-range hex
  coverage. Wings must have zero long-range coverage.
- **Minelayer:** Deploys anti-ship or anti-strikecraft minefields.
- **Marines:** Tiny or larger; cost scales with marine count and enables boarding.
- **Cloaking Device:** Basic requires Tiny or larger: 10 hull, 300 build credits,
  5 AM/turn to hide the ship from long-range sensors. Advanced requires Small or
  larger and extends that protection to allies within radius `R`: `R / (500/30)`
  hull, `hull × 30` build credits, and `R × 0.04` AM/turn.
- **Intelligence:** 10 hull for the first agent and 5 per additional agent.
  Counter-Intelligence adds 10 hull / 300 build credits and enables sweeps and elimination.

Destroyed Engines, or Engines with no positive effective speed, prevent sublight
movement until repaired. An operational Hyperdrive can still perform jumps.

### Built-in unit catalog

Constructors can build ordinary ships and stations from the catalogue below.
Select a Constructor, right-click a location, and choose **Construct...**. Search
by name, role or ability; filter by category, hull, unit kind or price. Details
show equipment, effective weapon ranges, fuel, abilities, costs and upkeep.

**Build** replaces current orders and closes the catalogue. **Queue after existing
orders** appends one build per selected builder and keeps it open. These buttons
work independently of Shift. Queued builds pay when they start; idle builders
start immediately. Multiple builders show their combined price.

Wings can be inspected here but are produced in Strikecraft Bays. Select Fighter
or Bomber production in the bay's panel while it is operational and not building;
selection is allowed while idle or replenishing. New carriers produce Fighters.
Choose Bombers for Attack Run. Fighters specialize in intercepting wings; Bombers
attack larger ships. Built-in wings need no antimatter tank and travel between
sectors aboard their carrier.

<!-- BEGIN GENERATED: unit-catalog -->
| Design | Category | Hull / kind | Hull used | Credits | Turns | Upkeep | Role and operation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Bomber Wing | Carriers | STRIKECRAFT_WING wing | 6.97/7 | 259 | 2 | 0.00 | Designed for bomber strike. Built and replenished in a strikecraft bay; requires a carrier for transport between sectors. |
| Fighter Wing | Carriers | STRIKECRAFT_WING wing | 7.00/7 | 260 | 2 | 0.00 | Designed for fighter screen. Built and replenished in a strikecraft bay; requires a carrier for transport between sectors. |
| Escort Carrier | Carriers | MEDIUM ship | 49.30/50 | 1979 | 20 | 0.49 | Designed for light carrier. Inter-system travel. Build fighter or bomber wings using the production selector. |
| Fleet Carrier | Carriers | HUGE ship | 166.60/200 | 6998 | 37 | 1.67 | Designed for carrier command. Inter-system travel. Build fighter or bomber wings using the production selector. |
| Missile Platform | Combat | TINY station | 10.00/10 | 400 | 6 | 0.10 | Designed for local missile defense. Stationary installation. |
| Patrol Cutter | Combat | TINY ship | 10.00/10 | 400 | 6 | 0.10 | Designed for local patrol. Local-sector operations; Tiny craft can travel aboard a hangar transport. |
| Interceptor | Combat | SMALL ship | 24.20/25 | 976 | 12 | 0.24 | Designed for strikecraft interception. Inter-system travel. |
| Patrol Escort | Combat | MEDIUM ship | 33.00/50 | 1490 | 17 | 0.33 | Economical armed escort for patrol and convoy protection. Inter-system travel. |
| Beam Frigate | Combat | MEDIUM ship | 45.50/50 | 1865 | 19 | 0.46 | Designed for beam combat. Inter-system travel. |
| Kinetic Frigate | Combat | MEDIUM ship | 45.50/50 | 1865 | 19 | 0.46 | Designed for kinetic combat. Inter-system travel. |
| Missile Frigate | Combat | MEDIUM ship | 45.50/50 | 1865 | 19 | 0.46 | Designed for missile combat. Inter-system travel. |
| Flak Battery | Combat | MEDIUM station | 49.10/50 | 1973 | 20 | 0.49 | Designed for stationary air defense. Stationary installation. |
| Flak Escort | Combat | MEDIUM ship | 49.80/50 | 1994 | 20 | 0.50 | Designed for fleet air defense. Inter-system travel. |
| Artillery Cruiser | Combat | LARGE ship | 90.24/100 | 3707 | 29 | 0.90 | Designed for ranged fire support. Inter-system travel. |
| Assault Cruiser | Combat | LARGE ship | 90.67/100 | 3720 | 29 | 0.91 | Designed for direct assault. Inter-system travel. |
| Orbital Bastion | Combat | LARGE station | 92.80/100 | 3784 | 29 | 0.93 | Designed for colony defense. Stationary installation. Requires a friendly or allied colony and an available colony support slot. |
| Battleship | Combat | HUGE ship | 183.93/200 | 7518 | 38 | 1.84 | Designed for fleet anchor. Inter-system travel. |
| Siege Dreadnought | Combat | HUGE ship | 199.93/200 | 7998 | 40 | 2.00 | Designed for siege bombardment. Inter-system travel. |
| Interdiction Fortress | Combat | HUGE station | 200.00/200 | 8000 | 40 | 2.00 | Designed for fortified jump denial. Stationary installation. Activate clear of existing natural or artificial inhibition fields; maintain fuel supply. |
| Mining Drone | Economy | TINY ship | 9.00/10 | 370 | 6 | 0.09 | Designed for transportable mining. Local-sector operations; Tiny craft can travel aboard a hangar transport. Mine metal asteroids or comets and unload at the matching refinery. |
| Small Mining Ship | Economy | SMALL ship | 23.20/25 | 946 | 12 | 0.23 | Designed for local mining. Intra-system travel only. Mine metal asteroids or comets and unload at the matching refinery. |
| Civilian Habitat | Economy | SMALL station | 24.00/25 | 970 | 12 | 0.24 | Designed for income and trade destination. Stationary installation. Requires a friendly or allied colony and an available colony support slot. |
| Crystal Refinery Station | Economy | MEDIUM station | 32.00/50 | 1460 | 16 | 0.32 | Designed for crystal refining. Stationary installation. |
| Metal Refinery Station | Economy | MEDIUM station | 32.00/50 | 1460 | 16 | 0.32 | Designed for metal refining. Stationary installation. |
| Trade Freighter | Economy | MEDIUM ship | 37.00/50 | 1610 | 17 | 0.37 | Designed for local trade. Intra-system travel only. Needs active habitats in different sectors. |
| Colonizer | Economy | MEDIUM ship | 38.00/50 | 1640 | 18 | 0.38 | Designed for colonization. Inter-system travel. |
| Expedition Miner | Economy | MEDIUM ship | 46.50/50 | 1895 | 19 | 0.47 | Designed for expedition mining. Inter-system travel. Mine metal asteroids or comets and unload at the matching refinery. |
| Blockade Runner | Economy | MEDIUM ship | 49.00/50 | 1970 | 20 | 0.49 | Designed for covert inter-system trade. Inter-system travel. Needs active habitats in different sectors. |
| Industrial Hub | Economy | LARGE station | 92.99/100 | 3790 | 29 | 0.93 | Designed for industrial support. Stationary installation. |
| Small Repair Ship | Logistics | SMALL ship | 24.19/25 | 976 | 12 | 0.24 | Designed for local repair. Intra-system travel only. |
| Shipyard | Logistics | SMALL station | 25.00/25 | 1000 | 12 | 0.25 | Designed for stationary construction. Stationary installation. |
| Constructor | Logistics | MEDIUM ship | 43.00/50 | 1790 | 19 | 0.43 | Designed for mobile construction and refitting. Inter-system travel. |
| Fuel Depot | Logistics | MEDIUM station | 43.00/50 | 1790 | 19 | 0.43 | Designed for stationary fuel collection. Stationary installation. Harvest near stars or inside hydrogen nebulae. |
| Antimatter Harvester | Logistics | MEDIUM ship | 45.00/50 | 1850 | 19 | 0.45 | Designed for fuel collection. Inter-system travel. Harvest near stars or inside hydrogen nebulae. |
| Small Repair Station | Logistics | MEDIUM station | 47.99/50 | 1940 | 20 | 0.48 | Designed for stationary repair. Stationary installation. |
| Utility Transport | Logistics | LARGE ship | 76.50/100 | 3295 | 26 | 0.77 | Designed for Tiny vessel transport. Inter-system travel. Hangar accepts Tiny vessels, not strikecraft wings. |
| Nebula Tender | Logistics | LARGE ship | 80.50/100 | 3415 | 27 | 0.81 | Designed for nebula and fuel support. Inter-system travel. Harvest near stars or inside hydrogen nebulae. |
| Fleet Tanker | Logistics | LARGE ship | 87.50/100 | 3625 | 28 | 0.88 | Designed for fleet resupply. Inter-system travel. Harvest near stars or inside hydrogen nebulae. |
| Fleet Repair Ship | Logistics | LARGE ship | 87.99/100 | 3640 | 28 | 0.88 | Designed for fleet repair. Inter-system travel. |
| Heavy Shipyard | Logistics | LARGE station | 88.79/100 | 3664 | 28 | 0.89 | Designed for construction and repair base. Stationary installation. Hangar accepts Tiny vessels, not strikecraft wings. Support facilities do not accelerate construction. |
| Scout | Reconnaissance | SMALL ship | 24.40/25 | 982 | 12 | 0.24 | Designed for exploration. Inter-system travel. |
| Sensor Station | Reconnaissance | MEDIUM station | 46.00/50 | 1880 | 19 | 0.46 | Designed for long-range reconnaissance. Stationary installation. |
| Covert Intelligence Ship | Special Operations | MEDIUM ship | 48.00/50 | 1940 | 20 | 0.48 | Externally identical to the Patrol Escort, with two hidden intelligence agents. Constructed under the cover name ‘Patrol Escort’. After construction, you may rename it to another generic warship name; avoid names that reveal its intelligence role. Inter-system travel. |
| Minelayer | Special Operations | MEDIUM ship | 49.50/50 | 1985 | 20 | 0.49 | Designed for mine deployment. Inter-system travel. |
| Intelligence Ship | Special Operations | LARGE ship | 75.00/100 | 3250 | 26 | 0.75 | Designed for espionage and counter-intelligence. Inter-system travel. |
| Boarding Cruiser | Special Operations | LARGE ship | 82.00/100 | 3460 | 27 | 0.82 | Designed for boarding and capture. Inter-system travel. |
| Minesweeper | Special Operations | LARGE ship | 87.80/100 | 3634 | 28 | 0.88 | Designed for mine detection and clearance. Inter-system travel. |
| Command Cruiser | Special Operations | LARGE ship | 88.00/100 | 3640 | 28 | 0.88 | Designed for target designation and protection. Inter-system travel. |
| Raider | Special Operations | LARGE ship | 93.50/100 | 3805 | 29 | 0.94 | Designed for covert raiding. Inter-system travel. |
| Stealth Tender | Special Operations | LARGE ship | 97.50/100 | 3925 | 30 | 0.97 | Designed for fleet concealment and decoys. Inter-system travel. |
| Interdictor | Special Operations | LARGE ship | 100.00/100 | 4000 | 30 | 1.00 | Designed for mobile jump denial. Inter-system travel. Activate clear of existing natural or artificial inhibition fields; maintain fuel supply. |
<!-- END GENERATED: unit-catalog -->

### Field refitting

A Constructor can install or remove equipment on friendly/allied units within
500 units, approaching automatically when necessary. Installation costs
`added hull × 30` credits and takes `max(1, round(added hull / 5))` turns. Removal
takes one turn and pays 50% salvage only after successful completion.

The complete resulting design must satisfy hull capacity, component restrictions,
ability and Trade prerequisites, turret rules and numeric validation, with at
least one meaningful component. Removing a prerequisite can invalidate a refit.
Docked craft must remain safe. Validation happens before charging and again at
completion; queued jobs validate when they start. The engine calculates prices
and durations. Long-range turret costs use Designer stats before variant scaling.

Failed or cancelled installations refund their charge once to the original payer.
Failed or cancelled removals pay no salvage. A pending job cannot cancel or refund
another active job. For loading existing equipment and unfinished work, see
[retrofit persistence](SAVE_FORMAT.md#retrofit-settlement-in-42).

## Orders and combat

### Queues and stances

Explicit orders and standing engagement policy are separate. An explicit order
suspends stance combat; Shift queues behind other explicit work. Changing stance
does not interrupt an order and takes effect when the explicit queue is empty.
**Stop Unit** cancels both layers, clears fire/navigation targets, and selects
**Do Nothing**. Automated controllers can also cancel individual orders or clear
only explicit work; see [order control](CODEX_CONTROL.md#command-discovery-and-order-control).

| Stance | Automatic engagement boundary |
|---|---|
| `DO_NOTHING` | Hold fire unless directly ordered |
| `ATTACK_WEAPON_RANGE` | Visible enemies in weapon range |
| `ATTACK_SAME_SECTOR` | Visible enemies in the same sector |
| `ATTACK_INTRA_SYSTEM_JUMP_RANGE` | Visible enemies within intra-system jump range |
| `ATTACK_SAME_SYSTEM` | Visible enemies anywhere in the system |

Stance pursuit stops when the enemy becomes hidden or leaves the selected boundary.
A direct Attack order is independent of that boundary. Turrets fire only for an
active Attack, including one performed by Stance, Patrol, Protect or Defend;
queued, suspended or cancelled attacks do not authorize fire.

**Add Patrol Waypoint** extends an active or queued patrol without interrupting
its current leg. Shift queues a separate patrol. Patrol returns to its captured
starting position after visiting the waypoints, then repeats. Continuous orders
can block queued work until cancelled or replaced.

### Order types

<!-- BEGIN GENERATED: order-count -->
The `OrderType` enum defines **37 order types**, including the persistent `STANCE` root.
<!-- END GENERATED: order-count -->

| Order type | Action |
|---|---|
| `REACH_WAYPOINT` | Internal movement leg created by Move. |
| `MOVE` | Travel to a position, sector or system through a planned route. |
| `PATROL` | Repeat a waypoint route and return to the patrol's start. |
| `ATTACK` | Approach weapon range and engage an enemy. |
| `STANCE` | Standing engagement policy, separate from explicit orders. |
| `DEFEND` | Guard a position or friendly/allied unit. |
| `PROTECT` | Escort a friendly/allied unit and intercept enemies. |
| `TOGGLE_INHIBITOR` | Activate or deactivate an inhibition field. |
| `COLONIZE` | Establish a colony on a habitable body. |
| `LOAD_COLONISTS` | Load population from a friendly/allied colony. |
| `CONSTRUCT` | Build an ordinary ship or station. |
| `REFIT_UNIT` | Install or remove equipment through a Constructor. |
| `REPAIR` | Approach and repair a friendly/allied ship. |
| `MINE` | Extract metal from an asteroid or crystal from a comet. |
| `UNLOAD_RESOURCES` | Deliver cargo to a compatible refinery. |
| `DOCK` | Enter a compatible hangar or strikecraft bay. |
| `DEPLOY_UNIT` | Launch a selected carried vessel. |
| `DEPLOY_ALL_WINGS` | Launch the carrier's wings. |
| `USE_ABILITY` | Activate an equipped ability. |
| `CONTINUOUS_MINE` | Repeat mining and refinery deliveries. |
| `TRANSFER_ANTIMATTER` | Refuel a friendly/allied ship. |
| `CONTINUOUS_RESUPPLY` | Alternate star harvesting and fleet refueling. |
| `LAY_MINEFIELD` | Deploy a minefield at the ship's position. |
| `TRADE` | Visit an active habitat in another sector for income. |
| `CONTINUOUS_TRADE` | Repeat trade journeys between active habitats. |
| `INFILTRATE_UNIT` | Place an agent aboard an enemy ship. |
| `INFILTRATE_PLANET` | Place an agent on an enemy colony. |
| `RELOCATE_AGENT` | Move an embedded agent to another enemy host. |
| `SABOTAGE` | Disrupt the agent's host subsystem or colony. |
| `CI_SWEEP` | Reveal enemy agents on allied assets in range. |
| `ELIMINATE_AGENT` | Remove a discovered enemy agent. |
| `EXTRACT_AGENT` | Recover an owned agent into an owned Intelligence ship. |
| `ENTER_GAS_GIANT` | Approach and submerge in a gas giant. |
| `LEAVE_GAS_GIANT` | Emerge when a safe departure position is available. |
| `ATTACK_RUN` | Bomber approach and salvo created by the carrier ability. |
| `EMERGENCY_RECOVERY` | Wing return created by the carrier ability. |
| `RECOVER_FUEL_CACHE` | Approach and collect fuel from a visible cache. |

### Movement and collision avoidance

Tactical distances use logical sector units; each sector has radius **5000**.
Sublight movement consumes fuel. Hyperdrives jump between sectors, with Advanced
drives also using wormholes between systems. Natural and artificial inhibition
fields block jump entry and exit; plan approach legs outside their boundaries.

Ships automatically route around solid bodies and fields that exclude their hull
size. Navigation keeps 50 units of clearance and stays inside the sector. A route
that cannot be completed fails with `path_unavailable`; it does not pass through
an obstacle. Destinations in the clearance band just outside a solid surface are rejected.

Approach orders stop at their operational range. Protect maintains 150 units from
the target; Attack, Dock, Repair, Refit, trade, transfers, intelligence and targeted
abilities use their respective ranges. Colonization and loading colonists stop
150 units beyond the body's surface, approaching automatically if necessary.
Microjump and carrier deployment also respect hull-blocking fields and storms.

### Weapons and damage

| Turret type | Role | Counter |
|---|---|---|
| Mass Driver | Kinetic projectiles | Armor |
| Beam | Instant directed-energy fire | Shields |
| Missile | Guided explosive ordnance | Point Defense |

**Standard** turrets balance range, damage and cooldown. **Anti-Strikecraft**
turrets specialize in wings with faster tracking and fire. **Long Range** turrets
trade slower firing for reach. Combat XP improves weapon damage, defenses,
sublight speed and jump range.

Non-positive damage has no effect. Cover, defenses and damage reduction can fully
absorb a positive hit, including rounding it to zero; there is no one-HP minimum.
Damage reduction is limited to 0–100% and cannot heal a ship. Shields are mitigation,
not a regenerating health pool. See [environmental effects](#environmental-fields)
for cover, cooling and splash modifiers.

### Minefields

**Anti-Ship** fields target ordinary ships; **Anti-Strikecraft** fields target wings.
After movement on each ship owner's turn, every living deployed ship is checked
at its final position, including stationary ships. Each overlapping enemy field
can detonate once against that ship in the phase, subject to remaining mines.
Allied ships are excluded; hidden and docked ships do not trigger mines.

Crossing a field without ending inside it does not trigger a mine. Additional
players do not multiply damage or mine consumption per owner turn. Scan for
Minefields reveals hazards; Mine-Clearing Sweep removes only its limited mine budget.

## Abilities

Equip abilities in the Designer or retrofit editor. The table gives activation
costs, prerequisites, range and timing; the descriptions below explain effects.
Human controls and both automated controllers use shared validation and orders.
See [Codex commands](CODEX_CONTROL.md#tactical-ability-commands) for payloads.

<!-- BEGIN GENERATED: abilities -->
There are **21 special abilities** registered in the game.

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
| **Attack Run** | 8 | 6 | 750 | 40 | Strikecraft Bay, Sensors | Unit |
| **Evasive Formation** | 6 | 3 | 750 | 20 | Strikecraft Bay, Sensors | Unit |
| **Emergency Recovery** | 8 | 6 | 750 | 30 | Strikecraft Bay | Unit |
| **Tracking Lock** | 6 | 3 | 600 | 20 | Sensors, Weapons | Unit |
| **Flak Barrage** | 8 | 3 | 0 | 35 | Weapons | Self |
| **Ghost Fleet** | 8 | 0 | 750 | 25 | Sensors | Position |
| **Tractor Tether** | 6 | 3 | 400 | 20 | Engines | Unit |
| **Mine-Clearing Sweep** | 4 | 0 | 1000 | 25 | Sensors, Minelayer | Position |
| **Guardian Link** | 7 | 3 | 450 | 25 | Defenses | Unit |
| **Fuel Cache** | 4 | 0 | 250 | 55 | Antimatter Storage | Position |
| **Nebula Catalyst** | 7 | 3 | 750 | 30 | Sensors, Antimatter Storage | Nebula + Position |
<!-- END GENERATED: abilities -->

### Combat and support abilities

- **Adaptive Forcefield:** Reduces incoming damage by 75% while active.
- **Cluster Warhead:** Detonates an area attack at a position, excluding allies.
- **Designate Target:** Adds 50% turret damage against the marked enemy;
  contributions from different sources stack additively.
- **Ion Bolt:** Disables the target's movement and attacks while active.
- **Missile Batteries:** Deploys three temporary missile platforms that attack enemies.
- **Repair Cloud:** Restores 5 hull HP per turn to each friendly/allied unit in range.
- **Capture Unit:** Uses Marines to board and take ownership of an enemy vessel.
- **Drain Antimatter:** Removes up to 30 AM from an enemy tank and transfers fuel
  into the caster's available storage.
- **Microjump:** Repositions within the same sector, subject to collision and field restrictions.
- **Scan for Minefields:** Permanently reveals enemy minefields in range.

### Deployment and link abilities

Position casts require a legal location within local range. Tractor/Guardian
unit targeting and fuel recovery approach automatically. Cooldowns and finite
durations advance at the caster owner's turn start. Required equipment must be
operational, and activation requires enough AM.

- **Ghost Fleet:** Deploys a persistent radar decoy. Short-range inspection identifies
  it. Each deploying ship can have one surviving emitter across the galaxy.
- **Tractor Tether:** Pulls a smaller allied or enemy ship with Engines, excluding
  wings, up to 200 units per owner turn and stops at 150-unit separation. Each
  pull costs 5 AM; the caster's speed is halved. The link breaks beyond 600 units
  and can be cancelled explicitly.
- **Mine-Clearing Sweep:** Removes up to three mines in total from revealed enemy
  fields along a 200-unit-wide sweep. Remaining mines stay hazardous.
- **Guardian Link:** Redirects 30% of incoming weapon damage, capped at 20 per hit,
  to the guardian. The redirected share is reduced by 25% before guardian defenses.
  It protects an ally, requires continued range, and can be cancelled explicitly.
  A target can have only one incoming link of each type; Guardian chains cannot form cycles.
- **Fuel Cache:** Spends 55 AM to deploy a persistent pod holding 50 AM. Recovery
  requires functional storage with free capacity and an explicit order within
  150 units; it needs no Ability component. Enemies can recover visible caches.
  Each deploying ship can have three surviving caches across the galaxy.
- **Nebula Catalyst:** Requires **Sensors and Antimatter Storage**; a Harvester is
  optional. Select a known nebula in the current sector and a position inside it
  within cast range. One 600-radius patch per ship enhances hydrogen fuel savings
  and nitrogen cooling for allies, and oxygen splash damage and dust sensor
  penalties for enemies. Baseline nebula effects continue outside those enhancements.

Ghost emitters and fuel caches have no expiry. Identifying a decoy or partially
recovering a cache does not free a deployment slot. Source destruction, capture
or refitting does not reset the cap attached to that deploying ship. Active links
end if their participants cease to meet deployment, equipment, allegiance or range
requirements. See [tactical persistence](SAVE_FORMAT.md#tactical-state-in-41) for saved state.

### Carrier and anti-strikecraft abilities

Carrier support affects only the caster's own deployed wings belonging to that
carrier. These five casts are local to the current sector and do not automatically
approach. The caster pays AM; cooldowns and durations advance at its owner's turn
start. Tracking Lock and Flak Barrage require an anti-strikecraft turret.

- **Attack Run:** Select a visible non-wing enemy. Each eligible deployed bomber
  belonging to the carrier and within cast range gets its own run, replacing
  explicit work but preserving stance. Bombers follow the moving target at +50%
  speed and release one double-damage salvo from ready turrets, no earlier than
  the caster owner's next turn. Runs require continued visibility and normal
  weapon range, cooldowns and clear firing paths. Stop, replacement orders and
  Emergency Recovery abort without refunds. Queued follow-ups resume afterward.
  Disabled or recovering bombers are ineligible; targeting lists affected wings
  and the work being replaced.
- **Evasive Formation:** One owned deployed wing takes 50% less weapon damage and
  deals 25% less weapon damage. This includes Attack Run salvos and incoming Flak;
  mines and environmental hazards bypass evasion.
- **Emergency Recovery:** One owned deployed wing returns at double speed with
  weapons suppressed. It replaces explicit work and follows the carrier using
  normal docking, routing and capacity rules. Docking removes the boost and
  prevents relaunch until the next owner-turn start. Stop or replacement orders
  abort recovery.
- **Tracking Lock:** The caster's anti-strikecraft turrets deal double damage to
  one visible enemy wing. The lock breaks on lost visibility, sector/range
  separation or changed allegiance. Other units receive no damage bonus.
- **Flak Barrage:** A moving 500-radius aura deals a 4-damage kinetic hit to each
  hostile player's deployed wings inside it after that player's movement phase.
  Stationary wings are affected; allied and docked wings are excluded. Overlapping
  barrages do not stack. Flak uses normal weapon mitigation, evasion, Guardian Link
  and damage XP.

Identical carrier effects do not stack. Effects and unfinished carrier orders end
if the source is destroyed, captured, disabled, hidden, docked or loses required
operational equipment. Carrier command range is checked at activation; Tracking
range and Flak coverage update continuously. The Testing carrier demonstrates
carrier support; the Testing Huge ship demonstrates Tracking Lock and Flak Barrage.

## Exploration and environments

### Visibility and concealment

Ships and stations provide short-range visual coverage and long-range sector
detection, shared across allies. Unexplored space is hidden; explored sectors keep
last-seen turn intel until sensors refresh it. Embedded agents also share their
host's sensor coverage with their owner and allies.

Basic cloaking hides one ship from long-range detection; Advanced cloaking also
covers allies in its area. Nebulae and asteroid fields conceal ships inside them
from long-range sensors, so opponents must close to visual range. Allied
minefields are always visible. Covert equipment and enemy inspection limits are
covered under [covert ships and unit names](#covert-ships-and-unit-names).

### Celestial bodies and dimensions

Collision radii describe solid surfaces; inhibition radii block jumps; effect
radii delimit environmental modifiers. All values below use logical sector units.
Non-solid bodies are permeable except where a field or storm excludes the hull.

| Body | Collision radius | Inhibition radius | Effect radius | Resource or role |
|---|---|---|---|---|
| Star | 750.015; Blue/Red Giants 900 | 3375; Blue/Red Giants 3750; black holes 4500 | See star hazards below | Antimatter harvesting |
| Planet | 562.5; gas giants 675 | 3000; Ferrous 3250; gas giants 3500 | — | Colony or atmospheric hiding |
| Moon | 125.01 | 2250 | — | Colony |
| Colonizable Asteroid | 75.015 | 1500 | — | Colony |
| Metal Asteroid | 75.015 | 1500 | — | Raw metal, base yield 10/turn |
| Comet | 75.015 | 1000 | — | Raw crystal, base yield 10/turn |
| Wormhole | 0 | 1875 | — | Advanced Hyperdrive route between systems |
| Asteroid Field | 0 | 0 | 3600 | Concealment and movement restrictions |
| Ice Field | 0 | 0 | 3600 | Cover and cooling |
| Debris Field | 0 | 0 | 2000 | Cover and abrasion hazard |
| Nebula | 0 | 0 | 3600 | Concealment and subtype effects |
| Storm | 0 | 0 | 3600 | Subtype hazards |

Moons generate in empty hexes exactly one hex from a planet in the same system,
including gas giants. No eligible hex or planet means no moon spawn.

### Stars

Every system has a central star. Its type multiplies the base antimatter harvest rate.

| Star type | Harvest multiplier |
|---|---|
| Pulsar | 2.5× |
| Blue Giant | 2.0× |
| Neutron Star | 1.8× |
| Yellow Giant | 1.5× |
| Red Giant | 1.3× |
| G-Type | 1.0× |
| White Dwarf | 0.8× |
| Protostar | 0.7× |
| Red Dwarf | 0.5× |
| Brown Dwarf | 0.3× |
| Black Hole | 0.1× |

Black holes inflict 15 damage/turn within their 750-radius event horizon. Pulsars
drain 5% of a ship's current AM each turn anywhere in their sector. Blue and Red
Giants use the enlarged collision and inhibition radii in the dimensions table.

### Planetary traits

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

Moons support 50 population with 1% growth per owner turn; colonizable asteroids
support 20 with 0.5% growth. Population is clamped to capacity before growth or
growth-sabotage checks. Colonized planets deposit passive metal/crystal directly
into the owner's treasury each turn. Gas giants cannot be colonized.

### Environmental fields

Field density controls access, speed and cover. An excluded hull routes around
the field, cannot microjump or deploy into it, and stops at its boundary with
`hazard_blocked` if movement would enter it. Wings can traverse all field densities
and are exempt from field speed penalties and debris abrasion.

| Density | Largest permitted hull | Asteroid/debris speed | Ice speed | Debris damage/turn above speed 50 |
|---|---|---|---|---|
| Low | Large | 85% | 90% | 1 HP |
| Medium | Medium | 75% | 80% | 2 HP |
| High | Small | 65% | 70% | 3 HP |

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

Asteroid fields provide long-range concealment. Ice and debris provide the cover
shown above. Fields cannot be mined: target Metal Asteroids or Comets instead.

Ice/nitrogen cooling reduces a turret's cooldown reset **when it fires**, after
variant scaling. Positive cooldowns have a minimum reset of one; zero-cooldown
designs remain zero. Coolant sources do not stack. Entering or leaving a region
does not recalculate an already running cooldown. All turret types and hulls
benefit; ability cooldowns are unaffected.

### Nebulae and storms

All nebulae conceal ships from long-range detection. Their subtype adds:

| Nebula | Effect inside the cloud |
|---|---|
| Hydrogen | Harvest at 0.4× base rate; sublight propulsion uses 50% less AM |
| Nitrogen | Turret cooling, using the same rule as ice fields |
| Oxygen | Increased splash damage taken, using the generated multiplier above |
| Dust | Short-range sensor radius reduced by 30% |

Oxygen affects Cluster Warhead splash, not ordinary missiles, mines, hazards or
component spillover. Apply it once after distance falloff and before mitigation,
truncating the product to an integer. Overlapping oxygen clouds do not stack.
[Nebula Catalyst](#deployment-and-link-abilities) selectively enhances these effects.

| Storm | Effect inside the storm |
|---|---|
| Plasma | 8 thermal hull damage/turn |
| Magnetic | 6 AM drain/turn and no long-range sensor projection; wings cannot enter or launch inside |
| Radiation | 4 damage/turn to a random functional component |

Environmental boundaries include points exactly on the radius. Hidden and docked
units receive no external environmental modifiers.

### Gas-giant atmospheric hiding

Ships with operational Engines, Tiny through Huge, can enter gas giants. Wings
and stationary stations cannot. Hidden ships disappear from enemy sensors and
maps, cannot interact with outside space or project fields, and cannot be attacked
from outside. Opposing hidden ships cannot detect or attack each other. Upkeep
and existing ability timers continue.

Entry and departure preserve stance and queued work. Hidden ships pause outside
orders and execute only a Leave at the front of the queue:

- **Enter → Leave → Move:** Movement resumes after departure.
- **Enter → Move → Leave:** Move blocks departure; cancel or replace the blocking work.

Queue editing remains available while hidden, and saving preserves the pause.
Departure finds a position 50 units beyond the planet surface, clear of obstacles,
excluded fields and deployed ships, inside the sector boundary. If no safe position
exists, Leave fails with `path_unavailable`; the ship stays hidden and keeps its
remaining queue. An accepted Leave order does not guarantee safe exit placement.

## Intelligence and teams

### Teams and cooperation

Teams are set during campaign setup and remain fixed throughout the match. Players
on the same team are allies; all other players are enemies.

| System | Allied behavior |
|---|---|
| Sensors and cloaking | Share sensor coverage, infiltrated-host vision and Advanced cloak protection |
| Combat and mines | Do not acquire allies as hostile targets; mines and Cluster Warhead exclude allies |
| Support | Repair, refit, refuel, protect and load colonists from allied assets |
| Orbital Defense / Repair Cloud | Share aura benefits and healing; colony support slots are shared |
| Espionage | Infiltration, relocation and sabotage target enemies; sweeps and elimination protect allies |

Right-click menus offer the operations appropriate to the target's relationship.
Hostile abilities such as Capture Unit, Drain Antimatter and Designate Target
reject allies.

### Agents and sabotage

Intelligence ships deploy agents onto enemy units or colonies within 500 units.
Orders in operational range execute immediately; otherwise the ship approaches.
Agents can relocate between enemy hosts or be extracted into an owned Intelligence
ship with free capacity. They share the host's sensor coverage with their owner
and allies; infiltrated colonies provide a 500-radius visual area.

| Sabotage | Effect on the host |
|---|---|
| Engines | Maximum sublight speed halved |
| Weapons | Turret damage halved |
| Defenses | Defense mitigation halved |
| Hyperdrive | Hex and wormhole jumps disabled |
| Sensors | Short-range sensors and long-range coverage disabled |
| Antimatter | 5 AM leaked per turn |
| Economy | Colony tax income halved; the infiltrating player receives 25% of base tax |
| Growth | Population growth halted |

Activate **CI Sweep** in a Counter-Intelligence ship's component panel to reveal
enemy agents on friendly/allied assets within 500 units. It costs 100 credits and
25 AM, with a three-turn cooldown. There is no passive discovery. A CI ship can
eliminate discovered agents within the same operational range.

Infiltrated targets show infiltration/sabotage badges and a sidebar status banner.
Friendly/allied targets with discovered spies show a warning badge. Enemy players
cannot inspect or precision-target Intelligence components.

### Covert ships and unit names

The **Covert Intelligence Ship** has the same visible equipment as the **Patrol
Escort**, plus two hidden agents. It is constructed under the name **Patrol Escort**;
its catalogue title remains distinct. Neither design has cloaking or CI. The
catalogue lists their prices, hull use and upkeep.

Select an owned unit and edit its sidebar name. Names are trimmed, contain 1–30
characters and no control characters; duplicates are allowed. Renaming costs
nothing, preserves orders and equipment, works while submerged or damaged, and
persists through saving. Choose a generic name if you want to conceal an intelligence
role. Automated controllers use [rename_unit](CODEX_CONTROL.md#unit-names-and-covert-ships).

Enemy inspections hide template identity, actual hull use, upkeep, all order layers,
and construction/refit activity. Hull class, capacity, HP and public equipment
remain inspectable; owners and allies retain their access. Equivalent public
equipment does not reveal which twin an opponent sees, though behavior or discovered
espionage can expose its role.

### Communications

Use **Comms** for conversations between players. Transmissions are logged immediately
to `saves/comms.md`; saving also exports the campaign's conversations to
`saves/comms/<campaign_id>/comms.md`. Logs include turn, UTC timestamp, participants,
teams and text.

## Storage and troubleshooting

### Saving and loading

Use **Esc → Save Game** to write a JSON campaign under `saves/`. **Load Game** is
available from the main menu and during a match. Loading validates a separate
candidate before replacing the live campaign; a rejected save leaves play intact.
See [Campaign persistence](SAVE_FORMAT.md) for supported formats, restoration and
migration warnings. AI memory storage is described in
[AI memory and persistence](AGENTIC_AI.md#memory-and-persistence).

### Custom-design storage

Custom designs are stored in `custom_unit_templates.json` under:

| Platform | Directory |
|---|---|
| Windows | `%LOCALAPPDATA%/WormholeControl`, falling back to `~/AppData/Local/WormholeControl` |
| macOS | `~/Library/Application Support/WormholeControl` |
| Linux | `$XDG_DATA_HOME/WormholeControl`, falling back to `~/.local/share/WormholeControl` |

Set `WORMHOLE_USER_DATA_DIR` to an **absolute directory** to override the location.
A missing library starts an empty collection without creating a file. Only this
configured library is loaded. To relocate an existing library, close the game and
copy it to the configured directory, preserving any designs already there.

Malformed libraries and storage failures are reported in the log. Repair the file
and restart to reload it. Failed saves, renames and deletions preserve the previous
disk library and registered designs; a failed load blocks writes until a successful
reload. Built-in and Testing template keys and names are reserved even when Testing
is inactive. For existing designs that fail current validation, see
[design compatibility](SAVE_FORMAT.md#design-compatibility).

### External design validation

Validate a library without launching the GUI or changing files:

```bash
python scripts/validate_unit_templates.py
python scripts/validate_unit_templates.py "path/to/custom_unit_templates.json"
python scripts/validate_unit_templates.py -c builtin
```

The default is the configured custom library (`-c custom`). `-c builtin` or
`--catalogue builtin` selects `data/unit_templates.json`; an explicit path overrides
the selected catalogue's default file. Output includes the resolved path, errors
grouped by template and field, and counts.

| Exit code | Meaning |
|---|---|
| 0 | Valid library; an empty object `{}` is allowed |
| 1 | Invalid definitions or library structure |
| 2 | File, JSON parsing or command-line error; a missing file is an error |

Validation uses the Designer's complete equipment rules, reports duplicate JSON
keys and never repairs or publishes designs. See [template validation details](DEVELOPMENT.md#template-validation)
for fields, types, derived values and the Python API.

### Logs and recovery

Each run writes `game.log` in the root folder. Check it for storage and runtime
failures. AI telemetry and developer-feedback files are documented under
[AI failure behavior](AGENTIC_AI.md#failure-behavior). For rejected commands,
uncertain transport outcomes or partial execution, follow
[Codex recovery distinctions](CODEX_CONTROL.md#recovery-distinctions).
