# Development

Developer setup, subsystem boundaries and data-validation APIs. For player-facing
rules, use the [Reference Manual](REFERENCE.md). AI contracts, the local socket
interface and save schemas are maintained in [Agentic AI](AGENTIC_AI.md),
[Codex Control](CODEX_CONTROL.md) and [Campaign persistence](SAVE_FORMAT.md).

## Setup and checks

Install Python 3.10+ and run from the repository root:

```bash
pip install -r requirements-dev.txt
python -m pytest
```

Tests run offline with fake AI providers and temporary storage; no API key is
needed. For fast import and launch checks:

```bash
python -m pytest -m smoke
python game.py --smoke-test
```

Quality checks used by CI:

```bash
python -m ruff check .
python scripts/check_import_boundaries.py
python -m mypy --platform linux
python -m mypy --platform win32
python scripts/generate_reference.py --check
```

[CI](../.github/workflows/ci.yml) also applies broader lint to domain boundaries.
It runs the full suite on Linux with Python 3.10 and 3.14 and Windows with Python
3.14. Check that workflow for the authoritative matrix and command arguments.

CI prints each test name and the 20 slowest durations and uploads JUnit results
as `test-diagnostics-<os>-py<version>` artifacts retained for seven days. Linux
also prints current/peak process RSS and available system memory, in KiB, at
each test-module boundary and session completion. The same lines are saved in
`resources.log`. Reports live under the runner's temporary directory. Uploads
run after test failures, but cannot be guaranteed if the runner itself shuts down.

To reproduce the diagnostic run on Linux:

```bash
CI=true WORMHOLE_CI_REPORT_DIR=/tmp/wormhole-ci-reports python -m pytest -v --durations=20 --junitxml=/tmp/wormhole-ci-reports/junit.xml
```

Memory reporting is opt-in through both environment variables and has no effect
on pytest's exit status. Missing kernel metrics are reported as unavailable.

### Local WSL tests

Keep the Linux interpreter, virtual environment, and caches on WSL's native
filesystem, even when the source checkout is on a Windows drive. For example,
from the repository root in WSL, using an installed Linux Python 3.10 or newer:

```bash
python3 -m venv ~/.cache/wormhole-control/venv
~/.cache/wormhole-control/venv/bin/python -m pip install -r requirements-dev.txt
PYTHONPYCACHEPREFIX="$HOME/.cache/wormhole-control/pycache" \
  ~/.cache/wormhole-control/venv/bin/python -m pytest --durations=20 \
  -o cache_dir="$HOME/.cache/wormhole-control/pytest"
```

Use a separate environment and cache directory for each Python version. Keep
pytest's temporary directories on Linux as well; its default `/tmp` location is
suitable. Run performance comparisons sequentially with matching dependency
versions, and distinguish the first run's bytecode compilation from warm runs.
A native-Linux source checkout can further reduce filesystem overhead.

Test isolation also restores pygame_gui's process-global translation search paths,
locale, and file format after every test, including failures. Each manager adds
a search path; without restoration, later GUI text lookups repeatedly scan the
same directory. The cost is particularly high for environments under `/mnt/c` or
`/mnt/d`.

## Current formats and protocols

These identifiers describe independent contracts; changing one does not imply
changing the others. The table is generated from their runtime constants.

<!-- BEGIN GENERATED: versions -->
| Contract | Current version / identifier | Source |
| --- | --- | --- |
| Campaign save | 4.17 | [CURRENT_SAVE_VERSION](../save_manager.py) |
| Observation | 21 | [OBSERVATION_SCHEMA_VERSION](../game_ai/observation.py) |
| Command contract | 17 | [CONTRACT_VERSION](../game_ai/command_spec.py) |
| Response schema | wormhole_control_turn_v14 | [TURN_PLAN_SCHEMA_NAME](../game_ai/schema.py) |
| Prompt cache | wormhole-control-turn-v21 | [PROMPT_CACHE_KEY](../game_ai/adapters/openai_responses.py) |
| Local socket protocol | 3 | [PROTOCOL_VERSION](../game_control_protocol.py) |
| Strikecraft Bay component | 5 | [StrikecraftBayComponent.SCHEMA_VERSION](../unit_components/strikecraft.py) |
| Strikecraft Wing component | 2 | [StrikecraftWingComponent.SCHEMA_VERSION](../unit_components/strikecraft.py) |
<!-- END GENERATED: versions -->

## Architecture

| Area | Responsibility and entry points |
|---|---|
| Application | `game.py` coordinates the loop; `application_bootstrap.py` initializes runtime resources |
| Domain | `domain/` owns coordinates, identity, players, units, celestials and other world objects |
| Equipment | `unit_components/` owns installed equipment and ability state; `tactical_balance.py` supplies tactical defaults |
| Orders | `order_system.py` adapts human events; `unit_orders/` implements movement, combat and jobs; `order_history.py` records outcomes |
| Turn resolution | `turn_processor.py` resolves game rules; `TurnPresentation` supplies optional presentation callbacks |
| World services | `galaxy.py`, `geometry.py`, `pathfinding.py`, `visibility.py`, `environmental_effects.py`, `celestial_descriptions.py` and `economy.py` |
| Presentation | `gui/`, `rendering/` and `input_processor/` manage widgets, drawing, cameras and input; `events.py` decouples notifications |
| Automated players | `game_ai/` owns observations, command validation and provider coordination; `game_control_protocol.py` serves the local bridge |
| Persistence | `campaign_persistence.py`, `campaign_graph.py`, `state_codec.py` prepare and restore campaigns |
| Design data | `data/` holds built-in and Testing templates, spawn rates and star names; `custom_unit_templates.py` manages the user library |

Core imports must not initialize Pygame, GUI or displays. Import entities, orders
and components from their defining modules. Canonical domain classes live in
`domain/`; clean-process tests enforce the import boundary.

Commander owns explicit queue promotion and stance arbitration. An Order owns
subtree status, cancellation and outcomes; concrete orders own actuator/job cleanup.
The [shared order contract](AGENTIC_AI.md#shared-order-contract) and
[commit guarantees](AGENTIC_AI.md#commit-guarantees-and-lifecycle-feedback) define
validation, projection, execution checks, refunds and partial failures.
Turret authorization requires an `IN_PROGRESS` Attack or Attack (long-range only) on the active root's front
child chain. Cached targets, queued attacks and suspended subtrees cannot authorize
fire. See [player order rules](REFERENCE.md#queues-and-stances).

`MoveOrder.for_unit_approach()` and `for_celestial_approach()` carry typed target
references and operational standoff distances. Routing uses feasible system paths
and verified obstacle-avoiding sector segments. Target-derived coordinates must
follow the [observation disclosure policy](AGENTIC_AI.md#information-boundary).

### Turn timing

| Clock or phase | Meaning |
|---|---|
| Owner-turn resolution | `process_player_turn(player)` resolves that player's End Turn actions. `process_turn(player)` delegates to it; neither advances the player index or global round. |
| Global round | `game.turn_number` increments only after the last player's resolution and global end-of-round effects. Population growth and quiet-round planetary recovery run in that global phase. |
| Countdown counters | Ordinary ability cooldown/duration counters decrement during owner unit updates; stored units still tick timers without applying external ongoing effects. These are remaining counts, not round deadlines. |
| Ready/expiry deadlines | Tactical `ready_round` / `expires_round` values are absolute round numbers. `start_owner_turn` derives remaining counters and expires eligible effects when that owner starts. Wing recovery and antimatter multiplication also compare independent unit deadlines against the round clock. |

`end_turn()` owns the complete transition: resolve the departing player, run any
global phase, advance the player/round, refresh the next owner's tactical deadlines,
freeze the briefing and invoke presentation/AI scheduling. Services with round
markers guard individual effects, not the whole turn: wing endurance increments
once per owner per round before movement, while later reconciliation can enforce
returns without incrementing it. Repeating the entire resolution is not safe.

Load reconciliation derives state from saved clocks without advancing play. Keep
feature-specific timing in the [reference](REFERENCE.md); do not describe every
counter or deadline simply as "turns."

## Display and runtime resources

`Game` accepts an immutable per-application `DisplayConfig`, for example
`Game(display_config=DisplayConfig(1920, 1080, False))`. Bootstrap discovers display
metrics when none are supplied. Input, rendering and cameras use this configuration;
UI collaborators receive an explicit `DisplayConfig`; incomplete adapters are rejected.
Set `WORMHOLE_FULLSCREEN=true` to force full-screen mode.

Resources resolve relative to the application module or PyInstaller bundle,
independently of the working directory. Each UI manager gets an in-memory scaled
theme, absolute bundled font paths and idempotent rich-text font preloading.
Galaxy, System and Sector views keep independent transient cameras. Galaxy transforms
zoom about the gameplay viewport center with pixel-based panning; default transform
arguments preserve the New Game preview. Galaxy picking and rendering share this
transform, and both drawing surfaces are clipped to the viewport. A successful
campaign commit resets the galaxy camera and active drag gesture; rejected setup or
load attempts leave them intact. No camera state is serialized.

## Campaign setup contracts

The wizard, control interface and direct Python setup share the
[new-campaign limits](REFERENCE.md#setup-limits). `GameSettings.validation_issues()`
returns field/code/message records without mutation; `validate()` returns error
strings. Invalid construction raises `SettingsValidationError`, a `ValueError`.
Numeric settings reject booleans and non-finite values; zero is accepted where
the minimum permits it. Omitted settings use defaults.

`preview_only=True` is a constructor-only map-validation mode. Starting a campaign
always revalidates full settings, generated topology, homeworld references and
starter fleets. Preparation copies previews and isolates ID allocation before
replacing the campaign, resetting AI or closing the wizard. Failure preserves
campaign, preview, counters and AI state. Save loading uses its own validation.

## Template validation

See [external validation](REFERENCE.md#external-design-validation) for CLI usage
and exit codes. `unit_template_validation.validate_library(raw, is_builtin=False)`
returns invalid library keys mapped to error lists. `parse_library(payload)`
detects duplicate JSON keys. `custom_unit_templates.template_from_dict(key, data)`
is the shared side-effect-free decoder; `CustomUnitTemplate.validate()` returns
a list of error strings.

A library is a JSON object mapping keys to template objects. A custom template's
display name is `name`, falling back to its key. Names must be nonempty, unique
ignoring case and surrounding whitespace, and must not match built-in or Testing
keys or display names. Built-in definitions additionally validate category, roles,
description and canonical stored component costs, HP, build price and duration.
Templates may set `default_unit_name`; otherwise initial unit names use `name`.
Template identity is stored separately from the mutable unit name.

Hull names accept case-insensitive enum names; component enum values use canonical
uppercase names. Abilities use exact `AbilityType.value` strings and cannot be
selected twice. Omitted optional parameters use the shared decoder's defaults. Only canonical
fields are accepted, including `has_sensors`, `has_strikecraft_bay`,
`strikecraft_bay_slots` and `has_counter_intelligence`. Unknown fields and historical
aliases are rejected.

Numeric inputs must be finite JSON numbers; integer parameters must be JSON
integers. Booleans and numeric strings are invalid numbers, and component toggles
must be actual booleans. Type and enum checks also cover disabled components'
stored settings. Engine speed, defenses, sensor ranges, repair/mining rates and
ranges, cargo, inhibitor radius and cloaking radius must be non-negative. Jump
range, hangar/bay slots, marines and agent counts must be at least one. Enabled
AM storage must meet its hull-specific minimum.
Turret damage/range and editable fixed component hull costs must be nonnegative;
turret cooldown must be a nonnegative integer. Turret numeric validation is shared
with component restoration. Zero values and fractional damage/range remain legal.
Derived cost hints are still recalculated rather than validated as fixed costs.

The Designer, validator and retrofit share equipment checks: hull capacity,
hull/component restrictions, advanced equipment, wing turret roles, no wing
Mining, zero long-range wing Sensors, ability prerequisites, the Trade/Engine
dependency and at least one enabled component. Validation reports violations
without clamping input. The GUI's shared equipment-input parser handles draft text
separately from strict JSON validation, derives integer types from the design records,
and uses the same parameter minimums. Invalid text is retained with field-keyed errors;
only valid values update the numeric preview. Every save route re-reads hidden and
disabled settings and validates a detached candidate before library publication.
Retrofit confirmation likewise rechecks the current draft before emitting an action.
Draft errors and widget styling are transient and are never persisted.

The representational minimums above are shared with campaign persistence;
no additional turret balance caps are imposed. Derived dynamic
hull costs, HP, price and build time are regenerated for custom designs. Stored
fixed costs still count toward enabled equipment's hull budget. Change performance
parameters to change dynamic costs. Library loading and editing share current validation; see
[design validation](SAVE_FORMAT.md#design-validation).

## Storage and lookup contracts

`CustomTemplateManager(data_file=...)` supports isolated libraries. Design saves,
renames and deletions atomically replace the disk library before updating the
manager or registry. Failures raise `TemplatePersistenceError`; loading exposes
`last_load_error` and logs failures. A failed load blocks writes until successful
reload. Failed operations preserve the previous disk and registered state.

`PRIVATE_TEMPLATES` contains human-only custom designs. Use
`get_all_templates_for_player(owner)` to select buildable designs; automated
players must neither see nor construct private templates. Tests and child
processes use temporary `WORMHOLE_USER_DATA_DIR` locations.

New `GameObject` IDs are positive integers, starting at 1 in a fresh process.
IDs are opaque and saved values are preserved, including 0. Use `None`, not
zero, for a missing object/target. Missing-hex lookups return empty lists; valid
lookups return live sector collections. Inter-system transfers return `False`
for unknown systems or invalid destination hexes without changing membership
or location. Socket binding and command failure contracts belong to the
[control guide](CODEX_CONTROL.md#transport-and-process-behavior) and
[AI failure guide](AGENTIC_AI.md#failure-behavior).

## Unit references in logs

Use `game_logging.format_unit_for_log(unit)` for every named unit in a log
message, including targets and list members. It returns `Name (id:42)` using
the current object fields, preserves ID `0`, and works after docking or removal
without a galaxy lookup. In incomplete diagnostic objects, missing names and
IDs become `Unit` and `unknown`. The helper imports no domain or GUI modules and
does not configure logging.

Format each reference at the logging call site, including references in locally
assembled log text; do not modify unit names, UI labels or persisted state.
For mixed object kinds, apply it only to units. Design names, other object names
and quoted communications/developer feedback retain their existing formatting.
Both file and console handlers receive the same formatted message.

## Test conventions

`pytest.ini` sets `pythonpath = .`, `testpaths = tests` and the `smoke` marker.
Shared scenarios live in `tests/support`; test modules do not import each other.
`tests/conftest.py` sets headless SDL before application imports, isolates user
storage/process state and owns Pygame/full-game lifecycle fixtures.

Discard queued test events with `tests.support.pygame_runtime.drain_events()`.
With pinned pygame-ce 2.5.7, `pygame.event.clear()` can retain Python event
payloads, including widgets and their entire UI managers. The GUI fixtures drain
events after application shutdown, release pygame_gui's default manager, and
collect resource cycles while keeping SDL initialized for the test session.
Use these fixtures for GUI tests and keep teardown in `finally` blocks so failing
tests also release their resources.

Use real entities for game rules and doubles for collaborators. Prefer observable
outcomes and distinct boundaries over literal tuning values or implementation call
counts. Save and command fixtures should verify independent restored/observed
state rather than mirror serializers. Run checks appropriate to the changed boundary.

## Documentation maintenance

Keep `REFERENCE.md` focused on current player-facing rules. Update the existing
topic in present tense; put historical explanations in commits and PRs. Give
each contract one home and link to it. The README is a short introduction, not
a destination for feature announcements or reference material removed elsewhere.
Alpha changes do not require backward compatibility. `SAVE_FORMAT.md` documents
the sole supported save format and rejection behavior. Prefer a short package map over a file-by-file repository inventory.

`scripts/generate_reference.py` owns six blocks in `REFERENCE.md`: components,
abilities, order count, planets, environments and the built-in unit catalogue.
It also owns the current-format table above, reading literal module/class
constants without importing the game or provider. Link to that table instead
of repeating current-version announcements in feature documentation.
Preserve each `BEGIN GENERATED` / `END GENERATED` marker pair exactly once.
Regenerate with `python scripts/generate_reference.py`; prose and the README
remain hand-maintained. Changing an enum requires reviewing the handwritten
descriptions as well as generated counts.

For reference edits, check Markdown links and run:

```bash
python scripts/generate_reference.py --check
python -m pytest tests/test_reference_generation.py
```

### Shared celestial rules

`celestial_descriptions.describe_body` produces immutable public body profiles
from balance constants and body attributes. Environmental execution, sidebar
rules, AI body descriptions and generated reference tables consume these profiles.
`environmental_effects` combines current deployed-unit modifiers and exposes
`sublight_speed`, `sensor_radius`, and `long_range_sensor_hexes`; presentation and
observations use those queries rather than applying terrain independently.

Movement returns a transient map of unit IDs to the post-drag speed used for
positive sublight displacement. The same owner-turn hazard phase consumes this
map, so arrival does not erase abrasion eligibility and old movement cannot leak
into a later turn. No movement receipts are persisted.
