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

## Architecture

| Area | Responsibility and entry points |
|---|---|
| Application | `game.py` coordinates the loop; `application_bootstrap.py` initializes runtime resources |
| Domain | `domain/` owns coordinates, identity, players, units, celestials and other world objects |
| Equipment | `unit_components/` owns installed equipment and ability state; `tactical_balance.py` supplies tactical defaults |
| Orders | `order_system.py` adapts human events; `unit_orders/` implements movement, combat and jobs; `order_history.py` records outcomes |
| Turn resolution | `turn_processor.py` resolves game rules; `TurnPresentation` supplies optional presentation callbacks |
| World services | `galaxy.py`, `geometry.py`, `pathfinding.py`, `visibility.py`, `environmental_effects.py` and `economy.py` |
| Presentation | `gui/`, `rendering/` and `input_processor/` manage widgets, drawing, cameras and input; `events.py` decouples notifications |
| Automated players | `game_ai/` owns observations, command validation and provider coordination; `game_control_protocol.py` serves the local bridge |
| Persistence | `campaign_persistence.py`, `campaign_graph.py`, `state_codec.py` and `save_migrations.py` prepare and restore campaigns |
| Design data | `data/` holds built-in and Testing templates, spawn rates and star names; `custom_unit_templates.py` manages the user library |

Core imports must not initialize Pygame, GUI or displays. `entities`,
`unit_orders` and `unit_components` expose explicit lazy exports. Canonical domain
classes live in `domain/`; clean-process tests enforce the import boundary.

Commander owns explicit queue promotion and stance arbitration. An Order owns
subtree status, cancellation and outcomes; concrete orders own actuator/job cleanup.
Turret authorization requires an `IN_PROGRESS` Attack on the active root's front
child chain. Cached targets, queued attacks and suspended subtrees cannot authorize
fire. See [player order rules](REFERENCE.md#queues-and-stances).

`MoveOrder.for_unit_approach()` and `for_celestial_approach()` carry typed target
references and operational standoff distances. Routing uses feasible system paths
and verified obstacle-avoiding sector segments. Target-derived coordinates must
follow the [observation disclosure policy](AGENTIC_AI.md#information-boundary).

## Display and runtime resources

`Game` accepts an immutable per-application `DisplayConfig`, for example
`Game(display_config=DisplayConfig(1920, 1080, False))`. Bootstrap discovers display
metrics when none are supplied. Input, rendering and cameras use this configuration;
display values in `constants.py` are fixed defaults and do not discover a display.
Set `WORMHOLE_FULLSCREEN=true` to force full-screen mode.

Resources resolve relative to the application module or PyInstaller bundle,
independently of the working directory. Each UI manager gets an in-memory scaled
theme, absolute bundled font paths and idempotent rich-text font preloading.
System and Sector views keep independent transient cameras.

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
selected twice. Omitted parameters and the aliases `has_scanner`, `has_fighter_bay`,
`fighter_bay_slots` and `counter_intelligence` use the shared decoder's defaults
and mappings. Unknown extra fields are ignored.

Numeric inputs must be finite JSON numbers; integer parameters must be JSON
integers. Booleans and numeric strings are invalid numbers, and component toggles
must be actual booleans. Type and enum checks also cover disabled components'
stored settings. Engine speed, defenses, sensor ranges, repair/mining rates and
ranges, cargo, inhibitor radius and cloaking radius must be non-negative. Jump
range, hangar/bay slots, marines and agent counts must be at least one. Enabled
AM storage must meet its hull-specific minimum.

The Designer, validator and retrofit share equipment checks: hull capacity,
hull/component restrictions, advanced equipment, wing turret roles, no wing
Mining, zero long-range wing Sensors, ability prerequisites, the Trade/Engine
dependency and at least one enabled component. Validation reports violations
without applying the Designer's input clamps.

Turret damage/range must be finite numbers and cooldown an integer; validation
adds no balance bounds beyond those enforced by the Designer. Derived dynamic
hull costs, HP, price and build time are regenerated for custom designs. Stored
fixed costs still count toward enabled equipment's hull budget. Change performance
parameters to change dynamic costs. Permissive loading and strict validation are
distinct; see [design compatibility](SAVE_FORMAT.md#design-compatibility).

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

## Test conventions

`pytest.ini` sets `pythonpath = .`, `testpaths = tests` and the `smoke` marker.
Shared scenarios live in `tests/support`; test modules do not import each other.
`tests/conftest.py` sets headless SDL before application imports, isolates user
storage/process state and owns Pygame/full-game lifecycle fixtures.

Use real entities for game rules and doubles for collaborators. Prefer observable
outcomes and distinct boundaries over literal tuning values or implementation call
counts. Save and command fixtures should verify independent restored/observed
state rather than mirror serializers. Run checks appropriate to the changed boundary.

## Documentation maintenance

Keep `REFERENCE.md` focused on current player-facing rules. Update the existing
topic in present tense; put historical explanations in commits and PRs. Give
each contract one home and link to it. The README is a short introduction, not
a destination for feature announcements or reference material removed elsewhere.
Compatibility guidance belongs in `SAVE_FORMAT.md` while it describes supported
behavior. Prefer a short package map over a file-by-file repository inventory.

`scripts/generate_reference.py` owns six blocks in `REFERENCE.md`: components,
abilities, order count, planets, environments and the built-in unit catalogue.
Preserve each `BEGIN GENERATED` / `END GENERATED` marker pair exactly once.
Regenerate with `python scripts/generate_reference.py`; prose and the README
remain hand-maintained. Changing an enum requires reviewing the handwritten
descriptions as well as generated counts.

For reference edits, check Markdown links and run:

```bash
python scripts/generate_reference.py --check
python -m pytest tests/test_reference_generation.py
```
