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
| Campaign save | 4.21 | [CURRENT_SAVE_VERSION](../save_manager.py) |
| Observation | 28 | [OBSERVATION_SCHEMA_VERSION](../game_ai/observation.py) |
| Command contract | 23 | [CONTRACT_VERSION](../game_ai/command_spec.py) |
| Response schema | wormhole_control_turn_v15 | [TURN_PLAN_SCHEMA_NAME](../game_ai/schema.py) |
| Prompt cache | wormhole-control-turn-v28 | [PROMPT_CACHE_KEY](../game_ai/adapters/openai_responses.py) |
| Local socket protocol | 4 | [PROTOCOL_VERSION](../game_control_protocol.py) |
| Constructor component | 5 | [Constructor.SCHEMA_VERSION](../unit_components/constructor.py) |
| Commander component | 2 | [Commander.SCHEMA_VERSION](../unit_components/commander.py) |
| Strikecraft Bay component | 5 | [StrikecraftBayComponent.SCHEMA_VERSION](../unit_components/strikecraft.py) |
| Strikecraft Wing component | 2 | [StrikecraftWingComponent.SCHEMA_VERSION](../unit_components/strikecraft.py) |
<!-- END GENERATED: versions -->

## Playtest repair plan — 2026-09-30

The [playtest report](../PLAYTEST_REPORT_2026-09-30.md) identified eight confirmed
issues. The implemented plan preserves fog of war, batch preflight atomicity,
order ownership and existing gameplay balance.

| Issue | Plan and implementation | Regression coverage |
| --- | --- | --- |
| Windows TLS trust | Combine bundled/system roots; honor CA overrides; classify failures without payloads. | Trust loading, invalid bundle, typed error chains, SDK client verification. |
| Failed AI turn looks busy | Publish bounded lifecycle/attention, wake waiters, add current-failure retry/skip tokens. | Pending/immediate waits, stale turns/tokens, partial-commit retry rejection, idempotent recovery. |
| Friendly legacy target | Share relation/range/capability rules through discovery, gateway and execution. | Friendly/allied rejection before replacement/payment; legitimate allied Ion Bolt; private enemy fuel. |
| Impossible attack routes | Reuse approach estimation and movement-capability checks, including deployables. | Stations/wings/local craft excluded; legal stationary fire and mobile approaches retained. |
| Generic execution outcomes | Propagate allowlisted movement/ability/carrier/placement causes to root history/briefings. | Relation, carrier departure, placement retention, one root outcome. |
| Zero error latency | Measure monotonic submission-to-failure elapsed time. | Delayed transport failure with safe telemetry. |
| Stale local skill/examples | Link runtime-generated versions; check authored control examples and skill guidance. | Stale examples/skill fail read-only documentation checks. |
| Ordinary cancellation on forced return | Set `wing_endurance_expired` before cancelling interrupted roots. | Current and queued interruption causes; existing voluntary cancellation behavior. |

Additional implemented interface work: stable planning catalogs and constructor
price exceptions, section/cache-use metrics, per-command field-presence guidance,
merged durable lessons and objective/order guidance, conditional journey progress,
owned known Fleet Jump origin blockers, seeded setup/export, and explicit contained
save/load/menu actions. See the [AI contract](AGENTIC_AI.md) and
[control guide](CODEX_CONTROL.md) for public fields and recovery guarantees.

`python scripts/benchmark_observations.py` uses seed 20260930 with two radius-3
systems and separate Normal/Testing setups. Compare original request characters
with content-input characters and inspect stable-prefix size; provider token/cache
figures are recorded separately. These fixtures do not establish large-map speed,
billed cost or a model-strength ranking.

Measured initial planning-content characters (including the new shared-context
instructions, excluding unchanged system instructions):

| Profile | Original request | Compact content | Stable catalogs | Reduction |
| --- | ---: | ---: | ---: | ---: |
| Normal | 178,144 | 165,035 | 108,156 | 7.4% |
| Testing | 234,350 | 221,371 | 112,776 | 5.5% |

Automatic quiet-turn continuation and delta observations remain optional experiments.
The cache/compaction measurements should come first; an automatic continuation
needs a defined interruption contract for discoveries, combat, losses, failures and
resource shortages. Opening-pace/balance changes and tactical model comparisons
require separate fixed Normal/Testing gameplay evidence. No balance retuning or
live paid provider benchmark is part of these repairs.

Validation completed: 4,836 tests and 10 subtests passed, with 8 tests skipped.
Ruff, import boundaries, generated-reference drift, Linux/Windows mypy checks and
the headless application smoke test passed. The existing key configuration was
retained; validation made no live provider calls.

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

### Industrial resource accounting

`resource_costs.py` owns immutable `ResourceCost` bundles, uniform material formulas,
atomic affordability/payment/refund operations, and treasury reads. Quotes use
canonical hull usage; material prices are derived rather than editable template
inputs. Existing credit prices and production durations remain independent.

Construction, refits, wing production and fortifications charge through the shared
helpers. Orders retain original payer and paid amounts in all three resources;
removal/dismantling pay fractional salvage only on completion. Human group
construction and automated commands share the projected reservation budget.
Reservations do not escrow stockpiles. Extend the shared helpers when adding
industrial spending instead of implementing separate credit/material mutations.

Tests should cover each independently insufficient resource, rejection before order
replacement, approaching and queued reservations, paid-work restoration, and
exactly-once original-payer settlement. AI-facing budget and disclosure fields are
specified in the [commit guarantees](AGENTIC_AI.md#commit-guarantees-and-lifecycle-feedback).

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
Enabled Sensors additionally require a base short-range radius of at least 200.0
logical units on every hull, including wings. The Designer, library/CLI validation
and field refits share this minimum; disabled Sensors retain the nonnegative floor.
Effective range penalties and saved installed equipment are unaffected.
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

Campaign persistence keeps its representational minimums and preserves installed
sensor radii below the design minimum; no additional turret balance caps are imposed.
Derived dynamic hull costs, HP, price and build time are regenerated for custom designs. Stored
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

`StarSystem.spawn_celestial_bodies` in `galaxy.py` places the central star, draws
independent radius-based planet and secondary-body budgets, places planets by
radial ring, then secondary bodies and deferred moons, and finally refreshes
static inhibition zones. Unplaceable moons become weighted nonmoon bodies to
preserve the secondary budget. Galaxy generation adds wormhole pairs afterward.

The generation constants in `galaxy.py` own the count ranges and the planet-type
weights for the inner, middle and outer thirds. Integer distance comparisons
include exact third-boundaries in the nearer zone. `data/spawn_rates.json` owns
only relative secondary-body weights; its values need not sum to one. Stellar
types, field density and nebula/storm subtype draws retain their own distributions.
All draws use the existing seeded Python random stream. New generation can change
seeded layouts; loading restores saved bodies without running generation or
enforcing the new population budgets. Player-facing rules live in
[system generation](REFERENCE.md#system-generation).

`celestial_descriptions.describe_body` produces immutable public body profiles
from balance constants and body attributes. Environmental execution, sidebar
rules, AI body descriptions and generated reference tables consume these profiles.
`environmental_effects` combines current deployed-unit modifiers and exposes
`sublight_speed`, `sensor_radius`, and `long_range_sensor_hexes`; presentation and
observations use those queries rather than applying terrain independently.

`planetary_intel.py` owns colony ownership disclosure, separate from physical
body disclosure. `VisibilitySnapshot.sensed_colony_ids` derives short-range
surface contacts and long-range sector coverage from the shared sensor pipeline.
Human presentation, AI options and command preflight/commit use shared disclosed
ownership eligibility: current or last-known ownership authorizes colony approaches.
Colonization also permits unknown ownership on a physically colonizable body, but
rejects disclosed occupied targets. `current_ownership` remains the strict gate for
effects and current statistics; colonization must confirm an unowned body on contact.
Active and queued orders retain their targets after contact loss, wait at action
range, and revalidate when coverage returns. Progress derives `waiting_for_contact`
without adding saved fields. Empty child queues cannot complete a waiting action.
Batch projection treats an in-range action without contact as pending, never settled;
population checks and reservations read live population only with current knowledge.
Player `planetary_intel` records only observed owner IDs and round numbers. Normal
visibility/discovery, executing order checks and committed ownership changes refresh
authorized records; pure queries and loading preserve history.

Movement returns a transient map of unit IDs to the post-drag speed used for
positive sublight displacement. The same owner-turn hazard phase consumes this
map, so arrival does not erase abrasion eligibility and old movement cannot leak
into a later turn. No movement receipts are persisted.

## Titan services

`titan_balance.py` owns Core/power tuning; ordinary hull tables define Titan
capacity, HP, propulsion and rendering. `titan_acquisition.py` derives ownership
and pending acquisitions from `campaign_graph`, explicit roots and constructor
jobs. The batch ledger substitutes projected roots for live roots, so cancellation
and replacement release capacity without predicting boarding success. Accepted
construction persists `construction_hull_size` and rechecks it before payment
and completion. Completion settles its root as ownership replaces the reservation.

`titan_abilities.process` runs once per owner round before movement/hazards.
Queued issuance reserves fuel; only this phase executes powers. Unit-level
`titan_cooldowns` and `last_titan_action_round` survive component replacement.
Active ability instances hold expiry, source ownership, scan coordinates and
Lance charge/origin/public-order identity. Decommissioning prerequisites cancels
active effects before removal. Pure visibility and effective-stat queries do not
advance or reconcile state. Visibility coverage uses the existing short-range
pipeline; weapon protection uses `combat_hit`, and wing bonuses multiply through
existing speed and outgoing/incoming damage helpers.

The [Titan acceptance tests](../tests/test_titans.py) cover deferred activation,
atomic placement, both drive types, construction/capture reservations, visibility,
stacking, interruptions, persistence and controller/UI integration. See
[Titan gameplay rules](TITANS.md) for the complete feature contract.
