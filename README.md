# Wormhole Control

**Wormhole Control** is a 2D turn-based 4X space strategy game prototype written in Python using `pygame-ce` and `pygame_gui`. Players command star fleets, colonize celestial bodies, manage supply lines, and wage tactical warfare across a procedural galaxy of star systems linked by wormholes.

The game uses a deliberately simple, tactical display aesthetic inspired by naval Combat Information Center (CIC) bridge consoles. Clean vector icons, range rings, and sensor cones provide full situational awareness across all three strategic zoom levels.

---

## Status

**Wormhole Control is an active prototype.** The game supports single-machine hot-seat multiplayer for 2 to 6 players and agentic OpenAI-powered opponents. AI players receive only player-visible state, formulate a turn plan, issue validated engine commands, update persistent strategy memory, and end their turn.

---

## Getting Started

### Requirements
- **Python 3.9+** (Verified working on Python 3.14.3)
- **pygame-ce** (Verified working on 2.5.7)
- **pygame_gui** (Verified working on 0.6.14)
- **OpenAI Python SDK** (for AI players)

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
   - Configure player count (2–6), custom names, faction colors, and human/AI thinking level. The player-type button cycles through Human, AI: Medium, AI: High, and AI: Low.
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
| **Middle Mouse Drag** | Pan tactical camera |
| **Mouse Wheel** | Zoom camera in / out |
| **G** | Switch to **Galaxy View** |
| **S** | Switch to **System View** |
| **E** | **End Turn** (process actions and advance to next player) |
| **ESC** | Open In-Game Menu / Cancel targeting mode / Deselect |
| **Arrow Keys** | Pan tactical camera |

---

## The Three Views

Wormhole Control organizes space into three interconnected strategic perspectives:

- **Galaxy View (`G`)**: Strategic overview of the known galaxy showing all star systems, player territory, and wormhole conduits connecting distant systems.
- **System View (`S`)**: System-level hex map showing orbital sectors radiating outward from the central star, along with celestial bodies, jump routes, and sector-level fog of war.
- **Sector View**: Tactical in-sector view providing a granular look at celestial objects, orbital structures, individual starships, weapon range circles, minefields, and real-time movement trajectories.

The **Top HUD Bar** tracks Credits, Metal, Crystal, the current turn number, and active player indicator with faction-themed panel coloring. The **Collapsible Sidebar** provides detailed inspectors for selected objects, order queues, component statuses, and actionable command buttons.

---

## Core Gameplay

### Turns & Players
Matches operate on a hot-seat turn sequence. At the start of a player's turn, movement orders execute, resource income and upkeep resolve, populations grow, and combat engagements are calculated. When finished issuing commands, press **`E`** or click **End Turn** on the HUD to advance.

### Resource Economy
- **Credits**: General empire treasury generated from colonized populations and civilian habitats. Credits fund ship construction, space installations, and ongoing fleet upkeep.
- **Metal**: Industrial mineral extracted from metal asteroids by mining ships. Refined at Metal Refineries to construct ship hulls and orbital infrastructure.
- **Crystal**: Rare energy crystalline mineral harvested from comets. Refined at Crystal Refineries to build advanced sensors, weapons, and hyperdrives.
- **Antimatter**: High-energy fuel stored in per-unit storage tanks. Powers sublight engine burn, hyperdrive jumps, cloaking fields, and special abilities. Antimatter can be gathered by **Antimatter Harvester** ships stationed near stars and transferred between ships in fleet formations.

### Movement & FTL
- **Sublight Propulsion**: Standard thruster movement within a sector hex powered by engines and antimatter.
- **Hex Jumps**: Short-range hyperdrive jumps between adjacent sectors within the same star system (requires **Basic Hyperdrive**).
- **Wormhole Traversal**: Long-range inter-system travel through natural spacetime wormholes (requires **Advanced Hyperdrive**).
- **Tactical Microjumps**: Instant short-distance teleportation via special ability to bypass hazards or reposition in combat.
- **Hyperspace Inhibition**: Dedicated inhibitor ships project interdiction fields that prevent enemy vessels from entering or exiting hyperspace within their radius.

### Combat & Warfare
- **Hull Durability & Defenses**: Ships feature customizable Armor, Rechargeable Shields, and Point Defense (PD) systems to mitigate incoming damage.
- **Weapon Systems**: Mount Mass Driver (kinetic), Beam (instant laser), or Missile (guided payload) turrets across Standard, Anti-Strikecraft, and Long-Range variants.
- **Unit Stances**: Configure automated engagement behavior (Do Nothing, Attack in Weapon Range, Attack in Sector, Attack in Jump Range, or Attack in System).
- **Combat Experience (XP)**: Units gain experience from battle, ranking up to boost weapon damage, defensive ratings, sublight speed, and hyperdrive jump ranges.
- **Boarding Actions**: Deploy specialized Marine strike teams to breach and capture enemy vessels.
- **Minefields**: Minelayers can deploy Anti-Ship and Anti-Strikecraft minefields for tactical area denial.
- **Strikecraft Wings**: Carriers deploy Fighter wings (air superiority / point defense) and Bomber wings (heavy anti-ship strikes).

### Detection & Intel
- **Sensor Horizons**: Ships and stations project short-range visual circles and long-range inter-sector sensor detection.
- **Fog of War & Sector Intel**: Unexplored regions remain hidden; explored sectors remember last-seen turn intel until refreshed by active sensors.
- **Cloaking Devices**: Active cloaking fields hide ships from enemy inter-sector long-range sensors at the cost of continuous antimatter consumption. Basic cloaks shield individual ships, while Advanced cloaks project an area-of-effect stealth field hiding entire fleet formations.
- **Espionage & Counter-Intelligence**: Infiltrate enemy vessels and colonies with covert operatives to tap their sensor horizons and execute subsystem sabotage. Counter-Intelligence ships execute active sector sweeps via the component sidebar panel (100 credits, 25 AM, 3-turn cooldown) to detect and eliminate hostile spies.

### Expansion & Infrastructure
- **Colonization**: Dispatch colony ships to settle habitable planets, moons, and colonizable asteroids to grow population and tax revenues.
- **Automated Logistics**: Set mining and harvester ships to automated loops (**Continuous Mine** and **Continuous Resupply**) to keep refineries supplied and fleets fueled.
- **Orbital Construction**: Constructors assemble orbital defense platforms, shipyards, refineries, and stations.
- **Civilian Habitats**: Deploy habitat modules to colonized sectors to provide direct economic bonuses (+50 credits/turn), supported up to finite colony population limits (base 1, +1 per 25 population).
- **Orbital Defense**: Deploy tactical defense modules in colonized sectors to project an area-of-effect aura (+20% attack damage, +20% defense mitigation) for friendly ships in radius, supported up to colony population limits (base 1, +1 per 25 population) with additive stacking.

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

- **Save Game**: Open the in-game menu (`ESC`) and select **Save Game** to persist complete game state to JSON format under the `saves/` directory.
- **Load Game**: Resume previous campaigns from the **Load Game** menu on the main title screen or inside an active match.
- **AI Memory**: Canonical long-term memory is embedded in each save. A readable derived copy is generated at `saves/agent_memory/<campaign>/<agent>/memory.md`.

## Agentic AI

AI players use the OpenAI Responses API with strict Structured Outputs. Configure the API key through `OPENAI_API_KEY`, or place the raw key in the ignored `API_keys/OpenAI.key` file. Environment configuration takes precedence. Secrets are never written to saves, memory, reports, or telemetry.

All AI players use **GPT-5.6 Luna**. The New Game Wizard exposes the model's
reasoning effort directly:

- **Low** — fastest, lowest-reasoning configuration.
- **Medium** — default configuration.
- **High** — more reasoning for difficult strategic turns.

The three levels share the same 7,000-output-token limit, 120-second timeout,
and 40-command turn limit, so the selected level changes only Luna's reasoning
effort. Older saves migrate Fast, Balanced, and Strategic selections to Low,
Medium, and High respectively when loaded.

Planning runs outside the Pygame thread. The version-2 observation distinguishes
hardware-supported commands from currently legal actions, supplies bounded option
lists, and keeps remote systems compact until friendly forces approach them.
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
request bodies.

See [Agentic AI Architecture](docs/AGENTIC_AI.md) for the full design and evaluation workflow.

---

## Development & Testing

### Automated Test Suite
Wormhole Control includes a comprehensive automated test suite consisting of **545 tests across 55 test modules** covering economy, combat, movement, AI logic, order trees, and GUI handlers:

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
