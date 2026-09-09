# Wormhole Control — remaining analysis work

- **Reviewed:** 2026-09-09
- **Sources:** [README](README.md), [Reference Manual](docs/REFERENCE.md), current implementation and regression tests.
- **Scope:** remaining architecture and maintenance recommendations from the project analysis, plus optional design opportunities.

## Current assessment

The remaining finding is **WC-016: maintainability risk concentrated in dispatchers and import boundaries**. Command interpretation, presentation, component construction and turn processing still distribute related rules across several modules. Changes to one mechanic can therefore require coordinated edits in human input, AI validation, order execution and rendering.

This report describes remaining work rather than a fresh gameplay audit. The recommendations below distinguish the open architecture finding from maintenance follow-ups and optional extensions. No new test run or runtime warning measurement is claimed here.

## WC-016 — dispatchers and import boundaries

**Severity:** Maintainability. **Confidence:** Confirmed. **Status:** Open.

### Parallel rule interpretation and large dispatchers

The following implementation areas concentrate decisions that would benefit from shared descriptors and smaller handlers:

| Current location | Remaining concern |
|---|---|
| `input_processor/context_menu_builder.py`: `build_sector_context_menu_options` | Capability, relationship, target type, labels and submenu construction share one branching catalog. |
| `input_processor/context_actions.py`: `handle_context_menu_action` | String action dispatch mixes parsing, selection, UI prompts and order creation. |
| `game_ai/rules.py`: `command_guidance` | Handwritten guidance interprets rules separately from executable command validation. |
| `game_ai/commands.py`: `CommandGateway._order_factory` and `CommandGateway._validate_unit_command` | Command-to-order construction and issuance checks overlap human action paths and domain rules. |
| `gui/event_router.py`: `process_event` | Widget routing and application behavior are coupled in a large branch tree. |
| `rendering/system_renderer.py`: `SystemViewRenderer._draw_system_view_order_lines` | Presentation reconstructs the meaning of many order types. |
| `turn_processor.py`: `TurnProcessor._process_movement` | Movement, fuel use, inhibition, jumps, transfers and state cleanup are tightly sequenced in one method. |
| `unit_orders/abilities.py`: `UseAbilityOrder.execute` | Targeting, approach insertion, ownership, range and activation are coupled. |
| `unit_components/constructor.py`: `instantiate_unit_from_template` | Component configuration choices converge in a large construction function. |

Decompose by mechanic: let each command, order or component descriptor supply appropriate parsing, eligibility, construction, formatting and guidance hooks. Share domain rules while retaining the visibility restrictions and UI behavior specific to each caller. Extend existing registries instead of introducing another parallel catalog.

The intended outcome is fewer independent interpretations of a mechanic. Splitting long functions into arbitrary helpers alone would leave the maintenance risk in place.

### Core/UI coupling and implicit exports

`game.py` eagerly imports GUI and rendering modules. `entities.py` aggregates players, celestial bodies, units, diplomacy and component/order imports. Some consumers use those imported names as indirect APIs; for example, `game.py` imports `Order` through `entities.py` rather than its defining module, `unit_orders/base.py`.

Move consumers toward imports from defining modules. Make any intentionally supported compatibility exports explicit and migrate their consumers gradually. Separate stable domain groups and UI adapters incrementally, with a core import boundary that does not require a display or GUI initialization.

### Import-time platform initialization

`constants.py` changes Windows DPI awareness at module scope and calls `detect_screen_resolution` to initialize `SCREEN_RES`. That helper can initialize, query and quit the Pygame display. Importing domain constants can consequently manipulate process-global GUI state and make import order significant.

Move OS/display initialization into application bootstrap and provide the computed display configuration to UI code. Keep game-rule constants independent of display discovery.

## Additional maintenance recommendations

### Contracts, naming and domain ownership

Document non-trivial public state-changing functions with their purpose, inputs, return values, failure behavior, side effects and ownership rules. Prioritize domain mutations, event handlers, command entry points and intelligence orders. Explain surprising lifecycle, cadence, canonical-state and visibility constraints where callers need them; avoid comment-density targets and comments that merely restate control flow.

Retain these API consistency improvements:

- Distinguish external `order_id` values (`Order.public_id`) from process-local `Order.order_id` values in internal naming or explicit aliases, preserving published interfaces during migration.
- Align `game.turn_manager` with its `TurnProcessor` role, and standardize axial-coordinate vocabulary across `in_hex`, `hex_coord`, `sector` and `sector_coord`.
- Give generic target-handling code explicit metadata for object-specific target fields rather than guessing among field names. Standardize component naming through stable registry keys before considering broad class renames.
- Rename `PULSAR_SHIELD_DRAIN_PERCENT` to reflect its antimatter-drain use in `TurnProcessor._process_environmental_hazards`.
- Consider distinct position/displacement types where they prevent meaningful mistakes; `geometry.py` currently aliases `Position` to `Vector`.
- Use a consistent annotation style compatible with the documented Python 3.10 minimum.

Process-global object and order counters remain an isolation concern. Campaign-owned allocation and smaller domain groups could reduce cross-imports and make independent simulations easier to run.

A general model of legal order transitions remains an architectural extension. Focus on consolidating transition ownership across order types and explicit/standing work, rather than adding another lifecycle layer with overlapping responsibilities.

### Exception handling and GUI polish

Review broad exception handlers in internal state transitions. Retain appropriate containment at I/O, GUI and thread boundaries; narrow internal catches or propagate programming failures with safe diagnostics. This is a general review recommendation, not a claim of a newly confirmed runtime defect.

Investigate residual `pygame_gui` layout and font warnings using the affected designer, wizard and other GUI scenarios. Adjust sizing and font preloading where needed, and verify the affected views at supported display scales. Establish the current warning set before making claims about its size or severity.

### Quality automation and testing extensions

- Extend lint and type checking incrementally beyond the current undefined-name rules, concentrating on domain boundaries and public contracts.
- Consider meaningful core-logic coverage gates and stricter reproducible runtime dependency resolution; the OpenAI SDK currently uses a version range.
- Add property-based exploration for save round trips, ID allocation, galaxy settings and geometric routing. Preserve existing focused behavior tests rather than duplicating them.
- Treat deterministic replay and broader compatibility snapshots as optional extensions described below.

## Remaining roadmap

1. **Consolidate mechanic interpretation.** Select one command/component family, extend its existing descriptors, and migrate its human input, AI guidance/validation, construction and presentation consumers. Preserve public behavior while reducing duplicated decisions.
2. **Establish import and ownership boundaries.** Move display discovery to bootstrap, migrate implicit imports to defining modules, and separate stable domain groups. Consolidate general order-transition ownership where it simplifies existing behavior.
3. **Improve contracts and polish.** Address the naming, docstring, exception-review and GUI recommendations above. Introduce broader quality gates incrementally as their signal becomes useful.

Acceptance should be demonstrated through preserved gameplay and public contracts, fewer parallel rule definitions, and domain imports that do not initialize a display. Feature extensions below are separate choices, not prerequisites for this refactoring.

## Optional design opportunities

### 1. Deterministic campaign seeds and replay bundles

Inject a campaign RNG and persist its seed/state. Bundle settings, save version and a bounded command/event stream for reproducible maps, radiation targets, wormhole failures, capture rolls and gas-giant departures. Use the same mechanism for tournament maps and deterministic AI evaluations.

### 2. A shared declarative mechanics catalog

Extend the descriptor work in WC-016 across designer/retrofit rows, command schemas and guidance, sidebar explanations, save compatibility metadata and reference generation. Integrate the existing registries, component codecs and generated-reference blocks into shared consumers; the opportunity is cross-system consistency beyond the current generated tables.

### 3. Generalized sourced status effects

Extend the source-owned ability model in `timed_effects.py` to environmental, sensor, cooldown and speed modifiers where useful. Give contributions explicit source, kind, magnitude, duration and stacking semantics, and derive aggregates so UI and AI can explain why a value changes.

### 4. Event-driven turn phases

Introduce a turn context carrying the active player, movement/contact results and destruction events. Let phases consume explicit events or presence information while preserving the documented mine and environmental cadence. This could reduce global scanning and provide a useful audit/replay stream.

### 5. A headless simulation package

Build on the core/UI boundary to expose a simulation API accepting actions and producing snapshots without Pygame or GUI imports. Use it for large deterministic test runs and AI evaluation, with the interactive UI acting as another consumer.

### 6. Contract snapshots and compatibility gates

Broaden golden snapshots for observation and command schemas, public reason codes, stable registry keys and save schemas. Require an explicit compatibility or migration decision when a snapshot changes, supplementing existing behavioral and generated-reference checks.

### 7. Reusable canonical state fingerprints

Generalize the canonical comparisons in `tests/test_persistence_integrity.py` into a reusable, normalized campaign representation and hash. Include rule-relevant state and exclude presentation caches and recomputable indexes. Extend its use to replay verification, stale-command detection and desynchronization diagnostics.
