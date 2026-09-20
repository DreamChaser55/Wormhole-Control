# Wormhole Control

**Wormhole Control** is a 2D turn-based 4X space strategy game written in Python using `pygame-ce` and `pygame_gui`. Command fleets, colonize celestial bodies, manage supply lines, and fight across a procedural galaxy of star systems linked by wormholes. The tactical display takes inspiration from naval Combat Information Center consoles, using vector icons, range rings, and sensor cones across three strategic views.

**This is an active prototype.** Matches support single-machine hot-seat play for 2–6 human, Codex-controlled, or built-in OpenAI players. Automated players receive player-visible information and issue validated game commands.

## Getting Started

Install **Python 3.10+**, then run these commands from the repository root:

```bash
pip install -r requirements.txt
python game.py
```

The requirements install the graphics libraries and OpenAI Python SDK. An API key is needed only when using built-in OpenAI players; you can start a human-only match without one.

To begin a campaign:

1. Click **New Game**. In the first wizard stage, generate a map and inspect its preview.
2. Select **Next: Players & Economy ➔**, choose the **Normal** spawn profile for a standard campaign, and configure your players and starting conditions. **Testing** provides a sandbox fleet for experimenting with units.
3. Click **Start Game** to begin turn 1. Use **◀ Back to Map** if you want to revise the galaxy before starting.

The [campaign setup reference](docs/REFERENCE.md#campaign-setup) explains map settings, player controllers, and home-system assignment.

## Playing the Game

Explore star systems, establish colonies, build ships, and keep your fleets supplied while deciding where to engage opponents. Credits, metal, and crystal support your empire; ships carry antimatter for movement and equipment. Sensors reveal nearby space, so reconnaissance helps you choose routes and targets.

Use **Galaxy View** (`G`) to see systems and wormhole connections, **System View** (`S`) to inspect a system's sectors, and **Sector View** for individual ships, celestial objects, and tactical positioning. All three views have independent zoom and pan controls. In Galaxy View, middle-click a system to enter it; middle-drag to pan; click **Reset View** or press `R` to restore the fitted overview.

Storage-equipped ships and stations can **Transfer Antimatter** or **Take Antimatter** from friendly units. Both **Continuous Resupply** (harvesters) and **Continuous Antimatter Transport** offer Automatic or Manual destinations. Automatic routes supply nearby eligible owned units across the galaxy; Manual routes supply one chosen owned/allied depot. Transports load at a chosen source and reserve return fuel. Dedicated transporter, storage station, and Small cache station designs are available in the Logistics catalogue. Harvesters collect fuel from stars and hydrogen nebulae; **Multiply Antimatter** doubles nearby friendly tanks with a 30-round cooldown and a shared recipient recovery period.

Recruit troops into dedicated transports, bombard enemy fortifications with Siege Batteries, and invade colonies through [planetary warfare](docs/REFERENCE.md#planetary-warfare). Colony sidebars provide immediate fortification upgrades; invasion dialogs show the odds and troop losses before you commit.

Retire owned ships and stations with a Constructor using **Dismantle…**, or dismantle a docked wing from its owning bay. Work takes half the current design build time per included hull and returns 50% of its build cost, reduced by hull damage. Docked craft are included; cargo is lost. See [dismantling](docs/REFERENCE.md#unit-dismantling) for interruptions and bay production controls.

Select a unit and use its contextual actions to issue orders. Hold **Shift** when issuing an order to queue it behind existing work. When finished, press **E** or click **End Turn** to resolve your player's actions and advance to the next player.

| Input | Action |
|---|---|
| Left click | Select a unit, solid body, or destination |
| Shift + left click / left drag | Adjust a multi-unit selection / box-select units |
| Right click | Open contextual actions or issue a direct command |
| Shift + order | Queue an order behind existing work |
| Middle drag / arrow keys | Pan the Galaxy, System or Sector camera |
| Mouse wheel | Zoom the Galaxy, System or Sector camera toward the cursor |
| G / S | Switch to Galaxy / System View |
| R | Reset Galaxy camera to fitted overview (Galaxy View) |
| E | End Turn |
| Esc | Open the in-game menu, cancel targeting, or deselect |

At the start of your turn, an event briefing reports combat, losses, completed
construction, problems, discoveries and new messages since your previous **End
Turn**, including its resolution. **Settings → Turn summary mode**, available
from the main and in-game menus, offers **Always show turn summary**,
**Automatic** (the default: significant events only), and **Do not show turn
summary**. The choice is remembered across restarts for all campaigns and human
players. Use **Esc → Turn
Summary** to reopen it, or **Open Comms** to read new messages. Automated players
receive the same player-visible briefing in their observations.

Inspect non-solid bodies, such as nebulae and storms, through their hex sidebar. For rules and detailed interaction guidance, see [controls and views](docs/REFERENCE.md#controls-and-views).

Click **Unit Editor** beside **Comms** in the bottom panel to open the **Unit Designer** and create ship templates for construction. The button is available in Galaxy, System, and Sector views. Open **Save Game** from the in-game menu to save a campaign; **Load Game** is available from the main menu and during a match. Custom designs use a separate [user-data library](docs/REFERENCE.md#custom-design-storage).

Select a Constructor and choose **Construct...** from its location context menu to
search the [built-in unit catalogue](docs/REFERENCE.md#built-in-unit-catalog).
Automated players can [override weapon and defense types](docs/REFERENCE.md#automated-construction-customization)
for individual builds to counter observed opponents, preserving template costs and equipment budgets.
Carriers select Fighter, Bomber, Interceptor or Long Range Bomber Wings through their
strikecraft bay production picker. Human and automated players can independently
override wing turret types (Mass Driver, Beam or Missile) and defense types (Armor,
Shields or Point Defense) for future builds. The picker previews the equipment;
**Template Default** restores that part of the selected design's presets. Equipment
supports [combat, deployment and carrier abilities](docs/REFERENCE.md#abilities),
including [toggleable environmental resistances](docs/REFERENCE.md#environmental-resistance-abilities)
that reduce matching hazards by 75% while consuming antimatter each owner turn,
while intelligence ships can infiltrate enemies and operate under
[covert names](docs/REFERENCE.md#covert-ships-and-unit-names).

Check templates against current Unit Designer rules without launching the game:

```bash
python scripts/validate_unit_templates.py
python scripts/validate_unit_templates.py "path/to/custom_unit_templates.json"
python scripts/validate_unit_templates.py -c builtin
```

The first command checks the configured user-data library, while `-c builtin`
(or `--catalogue builtin`) checks `data/unit_templates.json`. Validation reports
errors without changing files; see [external design validation](docs/REFERENCE.md#external-design-validation)
for field rules and exit codes.

## Automated Players

**Built-in OpenAI players:** Choose an AI controller in the New Game Wizard. Set `OPENAI_API_KEY`, or place the raw key in the ignored `API_keys/OpenAI.key` file; the environment variable takes precedence. Choose **Low** reasoning for faster turns, **Medium** for the default, or **High** for more strategic reasoning. The in-game **AI Settings** menu controls repair retries. See [Agentic AI Architecture](docs/AGENTIC_AI.md) for model configuration, memory, limits, and failure recovery.

**Codex-controlled players:** Codex can launch the visible game, create a campaign, observe its player's state, issue orders, and end turns through the local control bridge. No API key is required for this controller. Follow the [Codex Control guide](docs/CODEX_CONTROL.md) for setup and the play loop.

## Development

Install the development dependencies and run the offline test suite:

```bash
pip install -r requirements-dev.txt
python -m pytest
```

For fast import and launch smoke checks:

```bash
python -m pytest -m smoke
```

Tests use temporary storage and fake AI providers, so no API key is needed. See [Development](docs/DEVELOPMENT.md) for quality checks, CI coverage, test conventions, and reference-table generation.

The game is officially unreleased and in active Alpha version development, thus backward compatibility is a non-issue. Always prefer contributing simpler code over implementing any backward compatibility features.

## Documentation

- [Reference Manual](docs/REFERENCE.md): Gameplay rules, equipment, ship catalogue, and storage guidance.
- [Development guide](docs/DEVELOPMENT.md): Architecture, validation APIs, testing, and documentation maintenance.
- [Agentic AI Architecture](docs/AGENTIC_AI.md): Built-in AI configuration, information boundaries, and evaluation.
- [Codex Control guide](docs/CODEX_CONTROL.md): Local control setup, commands, and recovery.
- [Campaign persistence](docs/SAVE_FORMAT.md): Current save schema and transactional loading.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
