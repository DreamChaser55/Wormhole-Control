# Wormhole Control

**Wormhole Control** is a 2D turn-based 4X space strategy game written in Python using `pygame-ce` and `pygame_gui`. Command fleets and colonies across a procedural galaxy of star systems linked by wormholes, with a tactical display inspired by naval Combat Information Center consoles. This active alpha prototype supports single-machine hot-seat matches for 2–6 human, Codex-controlled, or built-in OpenAI players.

## Getting Started

Install **Python 3.10+**, then run these commands from the repository root:

```bash
pip install -r requirements.txt
python game.py
```

The requirements install the graphics libraries and OpenAI Python SDK. Human-only matches need no API key; only built-in OpenAI players require one.

Click **New Game**, generate a map and inspect its preview, then select **Next: Players & Economy ➔**. Choose the **Normal** spawn profile, configure your players and starting conditions, and click **Start Game**. The [campaign setup reference](docs/REFERENCE.md#campaign-setup) covers map settings, teams, home systems, and the Testing sandbox profile.

## Playing the Game

Explore systems, establish colonies, build ships, and keep your fleets supplied while choosing where to engage opponents. Credits, metal, and crystal support your empire; ships use antimatter for movement and equipment. Sensors reveal nearby space, making reconnaissance useful for planning routes and identifying targets.

Left-click to select a unit, then right-click to open contextual actions or issue a direct command. Hold **Shift** when issuing an order to queue it behind existing work. Press **G** for Galaxy View, **S** for System View, and use Sector View for individual ships and tactical positioning. When finished, press **E** or click **End Turn** to resolve your actions and advance to the next player. See [controls and views](docs/REFERENCE.md#controls-and-views) for navigation, selection, and turn briefings.

## Automated Players

Automated players receive player-visible information and issue validated game commands.

- **Built-in OpenAI players:** Choose an AI controller in the New Game Wizard; an OpenAI API key is required. Follow [automated player setup](docs/REFERENCE.md#automated-player-setup) for configuration.
- **Codex-controlled players:** Codex can launch and play the visible game through its local control bridge. This controller needs no game API key; follow the [Codex Control guide](docs/CODEX_CONTROL.md#quick-start) for setup and the play loop.

## Development

See the [Development guide](docs/DEVELOPMENT.md) for developer setup, offline tests, quality checks, architecture, and documentation maintenance.

## Documentation

- [Reference Manual](docs/REFERENCE.md): Gameplay rules, equipment, ship catalogue, and storage.
- [Development guide](docs/DEVELOPMENT.md): Architecture, validation APIs, testing, and documentation maintenance.
- [Agentic AI Architecture](docs/AGENTIC_AI.md): Built-in AI configuration, information boundaries, and evaluation.
- [Codex Control guide](docs/CODEX_CONTROL.md): Local control setup, commands, and recovery.
- [Campaign persistence](docs/SAVE_FORMAT.md): Save schema and transactional loading.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
Bundled fonts retain their own licenses; see [font sources and notices](fonts/README.md).
