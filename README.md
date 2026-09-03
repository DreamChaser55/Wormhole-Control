# Wormhole Control

**Wormhole Control** is a 2D turn-based 4X space strategy game prototype written in Python using `pygame-ce` and `pygame_gui`. Players command star fleets, colonize celestial bodies, manage supply lines, and wage tactical warfare across a procedural galaxy of star systems linked by wormholes.

The game uses a deliberately simple, tactical display aesthetic inspired by naval Combat Information Center (CIC) bridge consoles. Clean vector icons, range rings, and sensor cones provide full situational awareness across all three strategic zoom levels.

---

## Status

**Wormhole Control is an active prototype.** The game supports single-machine hot-seat multiplayer for 2 to 6 human, Codex-controlled, or agentic OpenAI-powered players. Automated players receive only player-visible state and issue validated engine commands.

---

## Getting Started

### Requirements
- **Python 3.9+** (Verified working on Python 3.14.3)
- **pygame-ce** (Verified working on 2.5.7)
- **pygame_gui** (Verified working on 0.6.14)
- **OpenAI Python SDK** (only for built-in OpenAI players)

### Installation & Launch

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Launch the game:**
   ```bash
   python game.py
   ```

3. **Start a campaign:**
   - Click **New Game** to open the **New Game Wizard**.
   - Select the **Spawn Profile**: **Normal** (authentic 4X starting state with each player starting in their own star system with a constructor station, constructor ship, colonizer ship, and antimatter harvester) or **Testing** (sandbox profile with all players in Sol equipped with testing ships and stations of all sizes).
   - Configure player count (2–6), custom names, faction colors, and controller type. The player-type button cycles through Human, Codex, AI: Medium, AI: High, and AI: Low.
   - Adjust galaxy generation parameters (system count, radius, wormhole connectivity) and starting economies.
   - Click **Start Game** to generate the galaxy and begin turn 1.

---

## Controls

| Input | Action |
|---|---|
| **Left Click** | Select unit, celestial body, or destination target |
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

---

## The Three Views

Wormhole Control organizes space into three interconnected strategic perspectives:

- **Galaxy View (`G`)**: Strategic overview of the known galaxy showing all star systems, and wormhole conduits connecting distant systems.
- **System View (`S`)**: System-level hexgrid map showing orbital sectors radiating outward from the central star, along with celestial bodies, wormhole routes, and sector-level fog of war. Systems are automatically fitted to the unobstructed map area and support mouse-wheel zoom plus middle-drag or arrow-key panning.
- **Sector View**: Tactical view providing a granular look at celestial objects, orbital structures, individual starships, weapon range circles, minefields, and real-time movement trajectories in a specific sector.

---

## Core Gameplay

### Turns & Players
Matches operate on a hot-seat turn sequence. At the start of a player's turn, movement orders execute, resource income and upkeep resolve, populations grow, and combat engagements are calculated. When finished issuing commands, press **`E`** or click **End Turn** on the HUD to advance.

### Resource Economy
- **Credits**: General empire treasury generated from colonized populations and civilian habitats. Credits fund ship construction, space installations, and ongoing fleet upkeep.
- **Metal**: Extracted from metal asteroids by mining ships. Refined at Metal Refineries to construct ship hulls and orbital infrastructure.
- **Crystal**: Rare crystalline mineral harvested from comets. Refined at Crystal Refineries to build advanced sensors, weapons, and hyperdrives.
- **Antimatter**: High-energy fuel stored in per-unit storage tanks. Powers sublight engine burn, hyperdrive jumps, cloaking fields, and special abilities. Antimatter can be gathered by **Antimatter Harvester** ships stationed near stars and transferred to other ships.

### Movement & FTL
- **Sublight Propulsion**: Standard thruster movement within a sector hex powered by engines and antimatter.
- **Hex Jumps**: Short-range hyperdrive jumps between adjacent sectors within the same star system (requires **Basic Hyperdrive**).
- **Wormhole Traversal**: Long-range inter-system travel through natural spacetime wormholes (requires **Advanced Hyperdrive**).
- **Tactical Microjumps**: Instant short-distance teleportation via special ability to bypass hazards or reposition in combat.
- **Hyperspace Inhibition**: Dedicated inhibitor ships project interdiction fields that prevent enemy vessels from entering or exiting hyperspace within their radius. Gravitational fields from massive celestial bodies also prevent hyperspace jumps in their vicitity.

### Combat & Warfare
- **Weapon Systems**: Mount Mass Driver (kinetic), Beam (laser), or Missile (guided payload) turrets across Standard, Anti-Strikecraft, and Long-Range variants.
- **Hull Durability & Defenses**: Ships feature customizable Armor (counters mass drivers), Shields (counters beams), and Point Defense (counters missiles) systems to mitigate incoming damage.
- **Unit Stances**: Configure a persistent standing engagement policy (Do Nothing, Attack in Weapon Range, Attack in Sector, Attack in Jump Range, or Attack in System). Explicit orders temporarily suspend stance pursuits and always take priority; the stance resumes when explicit work finishes. **Stop Unit** cancels everything and selects Do Nothing.
- **Combat Experience (XP)**: Units gain experience from battle, ranking up to boost weapon damage, defensive ratings, sublight speed, and hyperdrive jump ranges.
- **Boarding Actions**: Deploy specialized Marine strike teams to breach and capture enemy vessels.
- **Minefields**: Minelayers can deploy Anti-Ship and Anti-Strikecraft minefields for tactical area denial.
- **Strikecraft Wings**: Carriers deploy Fighter wings (air superiority) and Bomber wings (heavy anti-ship strikes). Strikecraft wings are nimble enough to ignore negative movement speed penalties from fields and debris field abrasion, but are banned from entering or launching within violent Magnetic Storms.

### Detection & Intel
- **Sensor Horizons**: Ships and stations project short-range visual circles and long-range inter-sector sensor detection.
- **Fog of War & Sector Intel**: Unexplored regions remain hidden; explored sectors remember last-seen turn intel until refreshed by active sensors.
- **Cloaking Devices**: Active cloaking fields hide ships from enemy inter-sector long-range sensors at the cost of continuous antimatter consumption. Basic cloaks shield individual ships, while Advanced cloaks project an area-of-effect stealth field hiding entire fleet formations.
- **Nebula & Asteroid Field Concealment**: Starships stationed inside a nebula cloud or an asteroid field are naturally concealed from enemy long-range (inter-sector) radar presence, requiring enemy ships to move within short-range visual range to achieve detailed detection.
- **Espionage & Counter-Intelligence**: Infiltrate enemy vessels and colonies with covert operatives to tap their sensor horizons and execute subsystem sabotage. Counter-Intelligence ships can execute active sector sweeps to detect and eliminate hostile spies.

### Expansion & Infrastructure
- **Colonization**: Dispatch colony ships to settle habitable planets, moons, and colonizable asteroids. Different planetary classes feature distinct growth rates and passive resource extraction (e.g. Volcanic and Ferrous worlds generate passive metal; Ice and Greenhouse worlds yield passive crystal). Massive Gas Giants cannot be colonized.
- **Automated Logistics & Harvesting**: Set mining and harvester ships to automated loops (**Continuous Mine** and **Continuous Resupply**) to keep refineries supplied and fleets fueled. Antimatter Harvesters can gather fuel from Stars, Gas Giants, and Hydrogen Nebulae.
- **Orbital Construction**: Constructors assemble orbital defense platforms, shipyards, refineries, and stations.
- **Civilian Habitats**: Deploy habitat modules to colonized sectors to provide direct economic bonuses, supported up to finite colony population limits.
- **Orbital Defense**: Deploy tactical defense modules in colonized sectors to project an area-of-effect attack/defense buff aura for friendly ships in radius, supported up to colony population limits with additive stacking.

### Celestial Environments & Tactical Cover
- **Celestial Field Density**:
  - Asteroid Fields, Ice Fields, and Debris Fields feature varying **Density** levels:
    - **Low Density**: Passable by hulls up to `LARGE` (blocks `HUGE` ships and stations).
    - **Medium Density**: Passable by hulls up to `MEDIUM` (blocks `LARGE` and `HUGE`).
    - **High Density**: Passable only by `SMALL`, `TINY`, and `STRIKECRAFT_WING` units (blocks `MEDIUM`, `LARGE`, and `HUGE`).
    - Strikecraft Wings can traverse fields of any density level.
  - Impassable fields act as physical obstacles for pathfinding and collision avoidance, blocking movement orders, microjumps, and carrier launches.
- **Tactical Cover & Field Effects**:
  - **Ice Fields**: Cryogenic ice particles scatter incoming energy beams, granting defense mitigation against beam attacks (+8% Low, +12% Medium, +16% High), weapon cooling, and sublight speed drag.
  - **Debris Fields**: Dense wreckage fragments intercept ballistic munitions, granting defense mitigation against kinetic and missile attacks (+8% Low, +12% Medium, +16% High), sublight drag, and high-speed navigation abrasion damage scaled by field density.
  - **Asteroid Fields**: Dense asteroid fields scatter long-range radar sensors and project hyperspace inhibition (900 radius), with sublight drag scaled by density.
- **Environmental Hazards**:
  - **Black Holes**: Extreme gravitational tidal distortion inflicts 15 hull damage per turn within 750 radius of the singularity.
  - **Pulsars**: Sweeping magnetic radiation pulses drain 5% of a ship's current antimatter reserves per turn.
  - **Debris Field Abrasion**: Moving at high sublight velocities (speed > 50) through debris clouds inflicts damage per turn scaled by density (1 Low, 2 Medium, 3 High; strikecraft wings are exempt).
  - **Space Storms**: Plasma storms inflict 8 thermal damage per turn; Magnetic storms drain 6 antimatter per turn and jam long-range radar sensors (strikecraft wings are banned from entering or launching in magnetic storms); Radiation storms inflict 4 component damage per turn and degrade weapon accuracy.

---

## Ship Design

Access the **Unit Designer** from the main menu or the in-game menu to build and customize starship templates:

- **Hull Sizing**: Choose from 6 hull classes (`STRIKECRAFT_WING`, `TINY`, `SMALL`, `MEDIUM`, `LARGE`, `HUGE`), each offering distinct capacity budgets, baseline hit points, and construction costs.
- **Dynamic & Fixed Components**: Tune sublight engines, hyperdrives, turrets, and defense ratings with dynamically scaling hull costs, or install fixed utility modules like refineries, colony pods, and hangars.
- **Special Abilities**: Equip up to 9 specialized abilities, including *Adaptive Forcefields*, *Cluster Warheads*, *Designate Target*, *Ion Bolts*, *Missile Batteries*, *Repair Clouds*, *Capture Unit*, *Drain Antimatter*, and *Microjumps*.
- **Persistence**: Saved designs are stored in `data/custom_unit_templates.json` and immediately become available for construction in active shipyards.

> For complete component hull costs, stat scaling formulas, and ability tables, consult the [Reference Manual](docs/REFERENCE.md).

---

## Saving & Loading

- **Save Game**: Open the in-game menu (`ESC`) and select **Save Game** to persist complete game state to JSON format under the `saves/` directory. Save format 3.2 preserves stances, explicit current/queued orders, public order UUIDs, and bounded per-player outcome history; older saves still load.
- **Load Game**: Resume previous campaigns from the **Load Game** menu on the main title screen or inside an active match.
- **AI Memory**: Built-in OpenAI players keep canonical long-term memory in each save. A readable derived copy is generated at `saves/agent_memory/<campaign>/<agent>/memory.md`.
- **Comms Log**: In-game player communications are logged in real-time to `saves/comms.md`. Campaign-specific transmission logs are also generated at `saves/comms/<campaign>/comms.md` during saves.

## Agentic AI

AI players use the OpenAI Responses API with strict Structured Outputs. Configure the API key through `OPENAI_API_KEY`, or place the raw key in the ignored `API_keys/OpenAI.key` file. Environment configuration takes precedence. Secrets are never written to saves, memory, reports, or telemetry.

All AI players use **GPT-5.6 Luna**. The New Game Wizard exposes the model's
reasoning effort directly:

- **Low** — fastest, lowest-reasoning configuration.
- **Medium** — default configuration.
- **High** — more reasoning for difficult strategic turns.

The three levels share the same 7,000-output-token limit, 120-second timeout,
and 40-command turn limit, so the selected level changes only Luna's reasoning
effort.

Planning runs outside the Pygame thread. The version-3 observation distinguishes
hardware-supported commands from currently legal actions, supplies bounded option
lists, reports inhibitor state and activation eligibility, and keeps remote
systems compact until friendly forces approach them.
Returned command batches are preflighted atomically before the game is mutated;
ordered dependencies such as loading colonists and then queueing colonization are
validated together.

Open **AI Settings** from the in-game pause menu to configure 1–5 repair retries
separately for each AI player (2 by default). A retry is an additional model
request after the initial output and receives the immediately preceding rejected
plan plus its exact validation errors. Changes take effect on that AI's next turn
and persist with normal game saves. The selected reasoning effort is retained for
repairs. After the configured retries are exhausted, failures leave the End Turn
button available for manual recovery.
Each planning attempt writes bounded operational telemetry (model, reasoning,
usage, latency, command summaries, validation errors, and retry outcome) without
persisting prompts, observations, memory, analysis, raw model output, or SDK
request bodies. AI agents can also message the game developer (`message_developer`)
to report gameplay bugs, rule confusions, or balance suggestions directly to
`saves/ai_feedback.md`.

Both AI interfaces use observation schema **5** and command contract **3**. Friendly
units expose separate standing, current, and queued orders, tactical ranges, and
persistent completion/failure/cancellation history. The command catalog is included
in observations. AI patrols accept explicit routes; `cancel_order` cancels one
explicit root, and `clear_explicit_orders` preserves stance. `cancel_orders` remains
full Stop. Intelligence ships can infiltrate visible hostile ships and colonies,
extract owned agents, run CI sweeps, and eliminate discovered enemy agents. Embedded
agents can be sabotaged or relocated through player-level commands that do not alter
ship orders. Unexpected commit exceptions stop the batch without rollback: completed
operations are reported, the failing operation may have partial effects, and Codex
must observe again before issuing commands or ending its turn.

See [Agentic AI Architecture](docs/AGENTIC_AI.md) for the full design and evaluation workflow.

## Codex-Controlled Player

Codex can launch the visible game, create a campaign containing exactly one Codex player, observe fog-of-war-safe state, submit incremental command batches with atomic preflight, and end turns through the loopback-only JSON bridge:

```powershell
python .\game_control.py '{"action":"status"}'
```

No API key is required because the bridge makes no OpenAI API calls. See the [Codex Control Protocol v2 guide](docs/CODEX_CONTROL.md) for setup schemas, the play loop, PowerShell/stdin examples, port configuration, errors, retries, and sandbox guidance.

---

## Development & Testing

### Automated Test Suite
Wormhole Control includes a comprehensive automated test suite consisting of an extensive offline regression suite covering economy, combat, movement, AI logic, order trees, and GUI handlers:

```bash
pip install -r requirements-dev.txt
python -m pytest
```

Configuration is specified in `pytest.ini` (`pythonpath = .`, `testpaths = tests`).

### Debug log

Each run of the game produces a `game.log` text file in the root folder, containing the debug log.

### Configuration & Data Files
- `data/`: Contains JSON files for unit templates, custom designs, spawn rates, and star name generators.
- `constants.py`: Central repository for game tuning constants, colors, and resolution definitions.
- **Environment Flags**:
  - `WORMHOLE_FULLSCREEN=1`: Forces full-screen display mode.

> For the full repository file tree and architecture breakdown, see the [Reference Manual](docs/REFERENCE.md).

---

## License

This project is licensed under the terms of the MIT License. See the [LICENSE](LICENSE) file for details.
