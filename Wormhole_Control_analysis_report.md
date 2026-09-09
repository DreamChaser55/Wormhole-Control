# Wormhole Control — remaining analysis work

- **Reviewed:** 2026-09-09
- **Sources:** [README](README.md), [Reference Manual](docs/REFERENCE.md), current implementation and regression tests.
- **Scope:** remaining architecture and maintenance recommendations from the project analysis, plus optional design opportunities.

## Current assessment

The remaining finding is **WC-016: maintainability risk concentrated in mechanic dispatchers**. Command interpretation, presentation, component construction and turn processing still distribute related rules across several modules. Changes to one mechanic can therefore require coordinated edits in human input, AI validation, order execution and rendering.

This report distinguishes the still-open mechanic-consolidation work from the completed import/ownership maintenance sprint and optional extensions. Roadmap points #2 and #3 have been implemented within their agreed incremental scope. The final local Windows Python 3.12.14 run passed **1,371 tests and 10 subtests with no warnings**. Native desktop scale checks and the CI platform matrix remain external validation, not claimed local results.

## WC-016 — mechanic dispatchers (still open)

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

## Completed maintenance sprint — roadmap #2 and #3

### Import and ownership boundaries

- Display discovery, fullscreen environment handling and Windows DPI setup now live in explicit application bootstrap. `DisplayConfig` supplies per-instance metrics to GUI, rendering, cameras and input. Constants expose fixed compatibility defaults; importing core modules cannot initialize or query a display.
- Canonical domain groups contain coordinates/object identity, communications, players/diplomacy, celestial bodies, minefields and units. `entities`, `unit_orders` and `unit_components` preserve explicit lazy compatibility exports and class identity. Repository consumers use defining modules; the existing order registry remains authoritative.
- `TurnProcessor` delegates notifications, communications refresh and AI timing to an application adapter. Standalone domain use has a null presentation port. `Game.turn_processor` is canonical, with `turn_manager` forwarding to it.
- Commander retains queue/stance ownership and consolidates foreground retirement. Order retains subtree transitions and once-only outcomes; concrete orders retain actuator cleanup and charge/refund ownership. Restore uses its dedicated non-replaying path. No additional lifecycle framework was introduced.

### Contracts and GUI polish

- Internal naming and the `local_order_id` alias distinguish process-local order identity from public UUIDs; wire/save fields remain unchanged. New coordinate contracts use `HexCoord` and `hex_coord`, retaining historical keywords. The pulsar drain constant now names antimatter, with an old-name alias.
- Order classes declare narrow target-field metadata for generic inspection, including object namespaces and private agent-host handling. This does not consolidate mechanic dispatch or eligibility and does not add a parallel mechanic catalog.
- Ownership APIs, synchronous events and intelligence execution document validation responsibility, immediate/delayed effects, failure behavior and cleanup. Predictable platform/conversion catches were narrowed; GUI/I/O/thread containment and command partial-commit recovery remain. The [exception review](docs/ARCHITECTURE_BOUNDARIES.md#exception-review) records retained boundaries.
- Rich-text font variants preload idempotently for application and standalone designer/retrofit managers. Retrofit turret summaries wrap to measured width. The previous targeted baseline was 89 passes with 20 warnings; the affected scenarios are now warning-free.

### Quality checks and validation limits

- Added static core dependency checks, fresh-process blocked-import/display tests, focused F/E9 lint and strict mypy checks on new boundary contracts. Existing generated-reference and behavior gates remain.
- Real widgets were tested at 1280×720, 1920×1080 and 2560×1440, including designer, both wizard stages, retrofit, HUD and dialogs. Representative rendered images were visually inspected. Missing/duplicate font-preload and undersized-label warnings are blocking failures in these scenarios.
- The local full suite passed 1,371 tests plus 10 subtests without warnings. Targeted lint, mypy, import-boundary checks and generated-reference consistency passed. Windows subprocess checks verify per-monitor DPI awareness. Linux Python 3.10/3.14 and Windows Python 3.14 remain configured in CI; this host's local runtime is Windows Python 3.12.14.
- Physical Windows desktop checks at 100%, 150% and 200% scaling remain a release validation task. Automated tests do not alter the user's desktop settings or claim to replace those checks.

## Remaining roadmap

1. **Consolidate mechanic interpretation — open, separate sprint.** Select one command/component family, extend its existing descriptors, and migrate human input, AI guidance/validation, construction and presentation consumers. Preserve public behavior while reducing duplicated decisions.
2. **Establish import and ownership boundaries — implemented.** Preserve the new bootstrap, domain dependency direction and existing transition owners as mechanic work proceeds.
3. **Improve contracts and polish — implemented within the focused scope.** Maintain the new checks and complete the external display-scale/platform validation described above.

Campaign-owned allocation, a generalized lifecycle framework, distinct position/displacement classes, property-based exploration, coverage thresholds and dependency locking were explicitly deferred. A standalone headless simulation API is also deferred. The feature opportunities below remain separate choices, not prerequisites for this sprint.

See [import, display and mutation boundaries](docs/ARCHITECTURE_BOUNDARIES.md) for the canonical module map, public compatibility contracts and review decisions.

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
