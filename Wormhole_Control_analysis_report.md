# Wormhole Control — analysis and code review

Review date: **2026-09-22**  
Base revision: **`5c6fe34f2d1902f9cf2a8a5e50ec35a880edaefd`**

Code metrics and original audit results refer to the base revision above.
Outstanding recommendations were updated on **2026-09-24** after removing addressed findings.

## Assessment

The project has useful foundations: explicit order ownership, separate campaign preparation and commit, allowlisted persistence, player-scoped observations, shared command definitions, bounded histories, and substantial offline tests. These are worth preserving. Several large modules repeat related rules, and documentation still duplicates contracts across feature sections.

The best next step is focused extraction of large responsibilities and consolidation of repeated documentation. A new entity framework, generic transaction engine, wholesale UI rewrite, or repository-wide typing conversion would add risk without addressing these problems directly.

**Latest recorded verification: the full offline suite passed on all three CI OS/Python combinations, executed locally.** See the latest recorded verification below for runtime versions and counts. The latest runs reported no warnings. Original audit results are retained in the testing section.

### Scope and method

- Read `README.md`, `docs/REFERENCE.md`, and `docs/AGENTIC_AI.md`, and cross-checked `DEVELOPMENT.md`, `SAVE_FORMAT.md`, and `CODEX_CONTROL.md` against implementation.
- Inventoried all tracked Python files with the AST: **228 production/tooling files, 55,721 lines; 175 test/support files, 48,791 lines** at the base revision. Empty package files and scripts are included; dependencies, ignored caches, and generated runtime data are excluded.
- Reviewed important application, domain, order, component, persistence, AI/control, UI, rendering, configuration, and testing files. Followed risky paths across modules. The file review records the principal conclusions; the AST inventory is broader than the detailed manual review.
- Ran the full offline suite, configured quality checks, additional lint, local Markdown link/heading checks, and isolated behavioral probes. Live provider calls, real API credentials, and the user's saved campaigns were not used.
- This is a source review and targeted behavioral audit, not a proof that every possible campaign, UI interaction, or malformed input is correct. Runtime coverage percentages were not measured. The original audit did not execute the CI operating-system/Python matrix; the latest recorded runtime verification is listed separately below.

The remaining cleanup and documentation rewrites below are recommendations, not completed changes.

## Important file review

The following records individual important files and the main conclusions from their review. Related small implementations are summarized together where a separate row would repeat the same recommendation.

### Application, domain, and navigation

| File | Review conclusion |
|---|---|
| [game.py](D:/Programming/Github_repos/Wormhole-Control/game.py) | Correctly distinguishes successful load commit from later presentation failure. At 842 lines it still combines application lifecycle, selection, AI scheduling, conversations, and persistence entry points. Extract one cohesive responsibility at a time; do not replace it with a service container. |
| [game_setup.py](D:/Programming/Github_repos/Wormhole-Control/game_setup.py) | Candidate construction, explicit template input, and post-setup reconciliation are useful. Document preview ownership and failure behavior at the preparation entry point. Keep startup defaults separate from saved-state validation. |
| [game_settings.py](D:/Programming/Github_repos/Wormhole-Control/game_settings.py) | Setup and save restoration share player value checks, including rejecting booleans as integers. Preserve these checks and keep setup defaults separate from strict saved-state restoration. |
| [application_bootstrap.py](D:/Programming/Github_repos/Wormhole-Control/application_bootstrap.py) | Display discovery has clear ownership and cleanup. Preserve explicit startup discovery instead of restoring import-time SDL behavior. |
| [display_config.py](D:/Programming/Github_repos/Wormhole-Control/display_config.py) | Explicit display metrics and typed boundaries are a good separation. Prefer passing this object over adding more display globals. |
| [app_preferences.py](D:/Programming/Github_repos/Wormhole-Control/app_preferences.py) | Atomic replacement and UI-visible failure propagation are appropriate for a small preferences file. No need for a configuration framework. |
| [game_camera.py](D:/Programming/Github_repos/Wormhole-Control/game_camera.py) | Shared zoom mechanics are sensible. Modal/input-blocking knowledge is lengthy; let each dialog participate in one small common “blocks gameplay input” query as new dialogs are added. |
| [game_logging.py](D:/Programming/Github_repos/Wormhole-Control/game_logging.py) | Filtering provider payload logs is valuable. Review handler ownership if logging is configured repeatedly: removed handlers are not explicitly closed. This is a cleanup concern, not a demonstrated application leak. |
| [constants.py](D:/Programming/Github_repos/Wormhole-Control/constants.py) | Keep stable shared rules here; newer tactical/planetary balance modules already provide useful topic separation. Avoid scattering renamed duplicates across catalogs and GUI helpers. |
| [domain/identity.py](D:/Programming/Github_repos/Wormhole-Control/domain/identity.py) | Allocation isolation is a useful invariant. Keep tests for zero IDs, high restored IDs, and rejected-load allocator preservation. |
| [domain/coordinates.py](D:/Programming/Github_repos/Wormhole-Control/domain/coordinates.py) | A small typed coordinate boundary is preferable to another geometry hierarchy. Gradually reduce tuple/attribute compatibility branching where callers have a known type. |
| [domain/players.py](D:/Programming/Github_repos/Wormhole-Control/domain/players.py) | Central ownership/team helpers already exist. Preserve strict input validation before constructor defaulting during hydration. |
| [domain/units.py](D:/Programming/Github_repos/Wormhole-Control/domain/units.py) | Component replacement/destruction cleanup has useful intent documentation. The class remains broad; preserve cleanup ordering and distinguish installed, operational, and deployed state in callers. |
| [domain/celestials.py](D:/Programming/Github_repos/Wormhole-Control/domain/celestials.py) | Gas-giant release uses bounded candidates, common safety checks, and commit-after-placement. |
| [domain/construction_job.py](D:/Programming/Github_repos/Wormhole-Control/domain/construction_job.py) | This is a presentation/selection view of a live job, not another persisted entity. Name/document that distinction and avoid expanding it into authoritative construction state. |
| [domain/communications.py](D:/Programming/Github_repos/Wormhole-Control/domain/communications.py) | Keep conversation persistence distinct from filesystem export. Preserve player identity/path validation before export. |
| [domain/deployables.py](D:/Programming/Github_repos/Wormhole-Control/domain/deployables.py), [domain/minefields.py](D:/Programming/Github_repos/Wormhole-Control/domain/minefields.py) | Distinct tactical entities are justified. Keep their ownership, visibility, and removal semantics explicit rather than treating every object as a ship through duck typing. |
| [galaxy.py](D:/Programming/Github_repos/Wormhole-Control/galaxy.py) | Generation, topology, lookups, and relocation share a large file. Separate generation from live graph operations if touched next. Preserve reciprocal wormhole and containment invariants. |
| [geometry.py](D:/Programming/Github_repos/Wormhole-Control/geometry.py) | Pure geometric helpers are a good test boundary. Some comments narrate elementary arithmetic; retain tolerance, fallback, tangency, and safety explanations. |
| [pathfinding.py](D:/Programming/Github_repos/Wormhole-Control/pathfinding.py) | The intersystem graph has unit-weight edges, so BFS can replace Dijkstra's heap/distances with fewer moving parts. Preserve deterministic tie behavior and hull-diameter filtering. This is a simplicity opportunity, not a demonstrated performance bottleneck. |
| [location_validation.py](D:/Programming/Github_repos/Wormhole-Control/location_validation.py) | Useful shared destination validation. |
| [visibility.py](D:/Programming/Github_repos/Wormhole-Control/visibility.py) | Explicit snapshots and `record_intel=False` support pure observation/loading. Document that distinction on `compute()`. |
| [campaign_graph.py](D:/Programming/Github_repos/Wormhole-Control/campaign_graph.py) | Cycle/duplicate-containment detection and explicit stored-unit traversal are worth keeping. Use this traversal when “all owned units” truly includes stored craft; use deployment checks otherwise. |

### Resolution, orders, components, and designs

| File | Review conclusion |
|---|---|
| [turn_processor.py](D:/Programming/Github_repos/Wormhole-Control/turn_processor.py) | Phase sequencing is important and currently difficult to read beside the 396-line movement method. Future extraction of sublight, hex jump, and wormhole jump resolution must preserve successful-debit checks and rejected-relocation refunds. Describe owner-turn versus global-round timing at the orchestration point. |
| [economy.py](D:/Programming/Github_repos/Wormhole-Control/economy.py) | Preserve the shared pure income calculation used by previews and settlement, along with the explicitly documented upkeep exclusions. |
| [events.py](D:/Programming/Github_repos/Wormhole-Control/events.py) | Typed UI events are useful. Avoid adding an additional parallel command representation for every new feature when an existing gateway operation already fits. |
| [order_system.py](D:/Programming/Github_repos/Wormhole-Control/order_system.py) | Human-event translation and validation overlap with gateway/order logic. Reuse domain predicates and command preparation where practical; keep UI event translation thin. |
| [unit_orders/base.py](D:/Programming/Github_repos/Wormhole-Control/unit_orders/base.py) | Explicit roots, suborders, outcomes, and cancellation ownership justify this abstraction. Document which transitions execute children synchronously and which wait for a turn. |
| [unit_components/commander.py](D:/Programming/Github_repos/Wormhole-Control/unit_components/commander.py) | Actuator ownership and separate standing/explicit work are valuable safeguards. Keep the detailed intent comments around cancellation and stale targets. Sidebar formatting could eventually leave this stateful component. |
| [unit_orders/movement.py](D:/Programming/Github_repos/Wormhole-Control/unit_orders/movement.py) | Route planning, target approach, waypoint execution, and collision rules need smaller named units. Its class/method docs should explain when auto-approach replans and what failed planning leaves behind. |
| [unit_orders/abilities.py](D:/Programming/Github_repos/Wormhole-Control/unit_orders/abilities.py) | Large branching dispatcher with UI warnings inside domain execution. Extract target/range validation without inventing a new ability engine. |
| [unit_orders/construction.py](D:/Programming/Github_repos/Wormhole-Control/unit_orders/construction.py), [unit_orders/refit.py](D:/Programming/Github_repos/Wormhole-Control/unit_orders/refit.py) | Rechecking at execution and recording the actual payer are important. Keep cancellation/refund tests; avoid trusting UI price/duration hints. Refit's direct GUI warning callback is residual domain/presentation coupling. |
| [unit_orders/combat.py](D:/Programming/Github_repos/Wormhole-Control/unit_orders/combat.py), [unit_orders/stance.py](D:/Programming/Github_repos/Wormhole-Control/unit_orders/stance.py) | Explicit attack and standing engagement are distinct behaviors and should remain distinct. Consolidate shared target/range predicates, not the entire order lifecycle. |
| [unit_orders/fuel_transport.py](D:/Programming/Github_repos/Wormhole-Control/unit_orders/fuel_transport.py), [unit_orders/antimatter.py](D:/Programming/Github_repos/Wormhole-Control/unit_orders/antimatter.py) | Long-lived transport phases are justified by waiting, sourcing, and delivery. Document phase transitions and reserve semantics rather than repeating branches in comments. |
| [unit_orders/intelligence.py](D:/Programming/Github_repos/Wormhole-Control/unit_orders/intelligence.py) | Relocation, extraction, sabotage, discovery, and ownership are a substantial subsystem. Prefer shared target predicates and a clearly documented public failure vocabulary. |
| [unit_components/constructor.py](D:/Programming/Github_repos/Wormhole-Control/unit_components/constructor.py) | At 1,216 lines, combines assembly, eligibility, job state, settlement, and presentation. Extract pure assembly from the stateful constructor; preserve explicit template injection used in preparation. |
| [unit_components/antimatter.py](D:/Programming/Github_repos/Wormhole-Control/unit_components/antimatter.py) | `consume()` signals failure correctly for destroyed storage, and movement requires a successful debit. Preserve that safeguard and make the positive finite amount contract explicit at this reusable boundary. |
| [unit_components/movement.py](D:/Programming/Github_repos/Wormhole-Control/unit_components/movement.py) | Ownership tokens on targets are useful. Per-instance `RECHARGE_DURATION` looks like a module constant; rename only with deliberate persistence handling. |
| [unit_components/weapons.py](D:/Programming/Github_repos/Wormhole-Control/unit_components/weapons.py) | Persisting effective turret values avoids double-applying variants. |
| [unit_components/hangar.py](D:/Programming/Github_repos/Wormhole-Control/unit_components/hangar.py) | The SMALL-slot accounting branch predates the current TINY-only docking rule; verify saved-state expectations before removing it. |
| [unit_components/strikecraft.py](D:/Programming/Github_repos/Wormhole-Control/unit_components/strikecraft.py) | Stable slots, production selection, containment, launch, and replenishment are related but crowded. Keep slot identity and paid work explicit and improve method contracts. |
| [unit_components/abilities/base.py](D:/Programming/Github_repos/Wormhole-Control/unit_components/abilities/base.py) | Separating static definitions from runtime instances is useful. Preserve explicit schema checks and restoration without activation side effects. |
| [unit_components/abilities/component.py](D:/Programming/Github_repos/Wormhole-Control/unit_components/abilities/component.py) | Preserve the separate ordinary, tactical, and toggle lifecycle contracts when reorganizing. |
| [unit_components/abilities/registry.py](D:/Programming/Github_repos/Wormhole-Control/unit_components/abilities/registry.py) | Existing definitions should remain the source of ability metadata. Do not add another manual requirements mapping. |
| [unit_templates.py](D:/Programming/Github_repos/Wormhole-Control/unit_templates.py) | Built-in, Testing, and private categories are deliberately distinct. Preserve that privacy boundary and explicit Testing publication. Module import still reads the bundled catalog; this is different from unwanted user-data loading. |
| [custom_unit_templates.py](D:/Programming/Github_repos/Wormhole-Control/custom_unit_templates.py) | Dataclasses, costs, validation adapters, conversion, and storage make this a 1,149-line mixed module. Separate the storage manager from design representation/costs. |
| [unit_template_validation.py](D:/Programming/Github_repos/Wormhole-Control/unit_template_validation.py) | Strong type/shape checks, duplicate-key handling, and whole-library rejection are useful. |
| [refit_validation.py](D:/Programming/Github_repos/Wormhole-Control/refit_validation.py) | Recalculating cost hints and validating the complete resulting equipment are good. Keep this pure. |
| [construction_customization.py](D:/Programming/Github_repos/Wormhole-Control/construction_customization.py), [unit_catalog.py](D:/Programming/Github_repos/Wormhole-Control/unit_catalog.py) | Shared customization/catalog output reduces UI/AI drift. Continue generating public descriptions from authoritative design data. |

### Feature services and persistence

| File | Review conclusion |
|---|---|
| [antimatter_logistics.py](D:/Programming/Github_repos/Wormhole-Control/antimatter_logistics.py) | Debit-before-credit exchange is a useful model for payment correctness. Journey estimates should clearly state conservative assumptions and remain mutation-free. Compare estimates against actual travel in representative terrain. |
| [antimatter_multiplication.py](D:/Programming/Github_repos/Wormhole-Control/antimatter_multiplication.py) | The preview/commit split is appropriately small. Add fuller contracts for net generation, independent deadlines, and same-batch affordability. |
| [environmental_effects.py](D:/Programming/Github_repos/Wormhole-Control/environmental_effects.py), [celestial_descriptions.py](D:/Programming/Github_repos/Wormhole-Control/celestial_descriptions.py) | Shared terrain facts feeding gameplay, panels, AI, and generated docs are a strong pattern to keep. |
| [environmental_resistance.py](D:/Programming/Github_repos/Wormhole-Control/environmental_resistance.py) | Small pure queries plus explicit upkeep settlement are clear. Document `availability` overrides and owner-turn timing; avoid generic imported names without module qualification. |
| [planetary_warfare.py](D:/Programming/Github_repos/Wormhole-Control/planetary_warfare.py) | Shared blockers/previews and a persisted invasion RNG are useful. The many optional projection arguments on `blocker()` deserve a precise contract or a small input record when touched. |
| [wormhole_stabilization.py](D:/Programming/Github_repos/Wormhole-Control/wormhole_stabilization.py) | Payment timing and support shared across both ends are meaningful domain rules. Keep the distinction between pure effective stability and owner-turn support processing explicit. |
| [dismantling.py](D:/Programming/Github_repos/Wormhole-Control/dismantling.py) | Containment, paid bay work, settlement, and offline state justify focused helpers. `ContextVar` projection overrides need documented scope; do not expand them into a general ambient game-state mechanism. |
| [strikecraft_service.py](D:/Programming/Github_repos/Wormhole-Control/strikecraft_service.py) | Read-only state and once-per-owner-round advancement are correctly separated. Names such as `required` and `process` obscure their purpose when imported directly. |
| [tactical_abilities.py](D:/Programming/Github_repos/Wormhole-Control/tactical_abilities.py), [strikecraft_abilities.py](D:/Programming/Github_repos/Wormhole-Control/strikecraft_abilities.py) | Keep availability/preview separate from activation. Reduce duplicated guards across these and ordinary abilities, especially storage/functionality checks. |
| [timed_effects.py](D:/Programming/Github_repos/Wormhole-Control/timed_effects.py) | Source-owned contributions are a compact solution to overlapping effects. Document key identity and idempotent removal; avoid replacing this with a generic effect framework. |
| [order_history.py](D:/Programming/Github_repos/Wormhole-Control/order_history.py) | Bounded, saved outcomes and the explicit public reason allowlist are useful. Preserve exactly-once recording and disclosure limits. |
| [turn_briefing.py](D:/Programming/Github_repos/Wormhole-Control/turn_briefing.py) | Frozen reports and recipient-scoped recording are good. Document begin/finish collection windows and omitted-count accounting at the important entry points. |
| [save_manager.py](D:/Programming/Github_repos/Wormhole-Control/save_manager.py) | File I/O, JSON serialization, object hydration, and sidecar exports share 875 lines. Preserve strict identity serialization and shared sidecar containment when separating I/O responsibilities; keep file replacement behavior explicit. |
| [campaign_persistence.py](D:/Programming/Github_repos/Wormhole-Control/campaign_persistence.py) | Prepare/reconcile/commit is worth preserving. Large validators can be split by document section while retaining one strict entry point. Presence checks alone do not establish usable state. |
| [persistence_context.py](D:/Programming/Github_repos/Wormhole-Control/persistence_context.py) | A small scoped allocation mechanism solves a real transactional problem. Keep restoration in `finally`; document main-thread preparation expectations. |
| [state_codec.py](D:/Programming/Github_repos/Wormhole-Control/state_codec.py) | Explicit tags and enum allowlisting are preferable to arbitrary object deserialization. There is overlapping value encoding in `save_manager`; consolidate common primitives at a deliberate format change, not via compatibility layers. |
| [unit_components/persistence.py](D:/Programming/Github_repos/Wormhole-Control/unit_components/persistence.py), [tactical_persistence.py](D:/Programming/Github_repos/Wormhole-Control/tactical_persistence.py) | Keep allowlists, explicit field ownership, and post-reference validation. Avoid reflective serialization of every attribute. |

### AI, local control, UI, and rendering

| File | Review conclusion |
|---|---|
| [game_ai/commands.py](D:/Programming/Github_repos/Wormhole-Control/game_ai/commands.py) | Highest-priority complexity hotspot: 2,069 lines at the base revision, large preflight ledger and dispatch functions. Separate projection, command preparation, and commit orchestration while retaining clear failure-stage receipts. |
| [game_ai/command_spec.py](D:/Programming/Github_repos/Wormhole-Control/game_ai/command_spec.py) | Already the right place for shared command shape/capability metadata. Keep generated version/field documentation connected to it. |
| [game_ai/contracts.py](D:/Programming/Github_repos/Wormhole-Control/game_ai/contracts.py), [game_ai/schema.py](D:/Programming/Github_repos/Wormhole-Control/game_ai/schema.py) | Preserve strict structured-output fields and the distinction between transport schema and semantic game legality. Keep schema generation connected to command specifications. |
| [game_ai/observation.py](D:/Programming/Github_repos/Wormhole-Control/game_ai/observation.py) | Explicit disclosure and bounded option lists are valuable. Document which IDs/targets are safe for a viewer. Test private-state changes for absence of public differences. |
| [game_ai/order_view.py](D:/Programming/Github_repos/Wormhole-Control/game_ai/order_view.py), [game_ai/intelligence.py](D:/Programming/Github_repos/Wormhole-Control/game_ai/intelligence.py) | Redaction is a contract, not incidental formatting. Add function-level docs explaining unavailable targets, owner/allied access, and omission behavior. |
| [game_ai/rules.py](D:/Programming/Github_repos/Wormhole-Control/game_ai/rules.py) | `command_guidance()` is 421 lines. Split its output assembly by capability/domain and reuse existing validators; avoid another parallel set of legality rules. |
| [game_ai/coordinator.py](D:/Programming/Github_repos/Wormhole-Control/game_ai/coordinator.py) | Main-thread mutation, stale-result checks, and bounded semantic repair are useful. |
| [game_ai/adapters/openai_responses.py](D:/Programming/Github_repos/Wormhole-Control/game_ai/adapters/openai_responses.py) | Provider details are correctly isolated. No live model availability or provider behavior was tested in this review. |
| [game_ai/runtime.py](D:/Programming/Github_repos/Wormhole-Control/game_ai/runtime.py), [game_ai/config.py](D:/Programming/Github_repos/Wormhole-Control/game_ai/config.py) | Central runtime limits and credential-loading isolation are useful. Keep permissive user configuration normalization out of strict campaign restoration. |
| [game_ai/memory.py](D:/Programming/Github_repos/Wormhole-Control/game_ai/memory.py) | Bounded sections and atomic sidecar replacement are appropriate. Preserve shared identity and resolved-path containment checks. |
| [game_ai/evaluation.py](D:/Programming/Github_repos/Wormhole-Control/game_ai/evaluation.py) | Provider-independent cases and gateway acceptance scoring are useful. Keep offline contract tests separate from model quality/cost evaluations. |
| [game_control_protocol.py](D:/Programming/Github_repos/Wormhole-Control/game_control_protocol.py) | Loopback-only binding, size limits, turn tokens, response caching, and main-thread pumping form a sensible local boundary. Document cache lifetime and uncertain outcomes; do not describe preflight atomicity as rollback of every possible commit failure. |
| [game_control.py](D:/Programming/Github_repos/Wormhole-Control/game_control.py) | Small CLI is appropriate. Keep transport recovery tied to request IDs and observation refresh rather than blind command retries. |
| [gui/handler.py](D:/Programming/Github_repos/Wormhole-Control/gui/handler.py) | Acts as a UI facade but carries broad mutable state. Prefer focused dialogs/helpers and explicit lifecycle cleanup over adding more pass-through wrappers. |
| [gui/layout_new_game_wizard.py](D:/Programming/Github_repos/Wormhole-Control/gui/layout_new_game_wizard.py) | At 1,740 lines, combines layout, preview manipulation, player configuration, and validation feedback. Split by wizard page/preview responsibility, keeping draft settings ownership obvious. |
| [gui/event_router.py](D:/Programming/Github_repos/Wormhole-Control/gui/event_router.py) | `process_event()` is 300 lines. A few named per-dialog/feature handlers are simpler than continuing the branch chain or inventing a universal event framework. |
| [input_processor/context_actions.py](D:/Programming/Github_repos/Wormhole-Control/input_processor/context_actions.py) | `handle_context_menu_action()` is 454 lines. Extract handlers by actual action family; data-driven routing is suitable for simple direct dispatch only. |
| [input_processor/context_menu_builder.py](D:/Programming/Github_repos/Wormhole-Control/input_processor/context_menu_builder.py) | Repeats capability decisions. Use shared domain predicates so menu legality does not drift from execution. |
| [gui/sidebar/view.py](D:/Programming/Github_repos/Wormhole-Control/gui/sidebar/view.py) | Stable selection identity and measuring from the viewport origin address real UI concerns. |
| [gui/sidebar/panels_unit.py](D:/Programming/Github_repos/Wormhole-Control/gui/sidebar/panels_unit.py), [gui/sidebar/panels_world.py](D:/Programming/Github_repos/Wormhole-Control/gui/sidebar/panels_world.py) | Keep user-visible rows distinct from internal identity metadata. Preserve public equipment/privacy comparisons when changing layouts. |
| [gui/sidebar/order_formatting.py](D:/Programming/Github_repos/Wormhole-Control/gui/sidebar/order_formatting.py) | Large order-type formatter duplicates some traversal/knowledge used by renderers and AI views. Reuse neutral order traversal where possible, while retaining viewer-specific redaction. |
| [gui/unit_editor_gui/param_readers.py](D:/Programming/Github_repos/Wormhole-Control/gui/unit_editor_gui/param_readers.py) | Input handling silently substitutes/defaults or preserves old values in several places. Consistent inline feedback would improve clarity. |
| [gui/theme_loader.py](D:/Programming/Github_repos/Wormhole-Control/gui/theme_loader.py), [gui/text_layout.py](D:/Programming/Github_repos/Wormhole-Control/gui/text_layout.py) | Scaled in-memory themes and measured wrapping are useful. |
| [rendering/system_renderer.py](D:/Programming/Github_repos/Wormhole-Control/rendering/system_renderer.py) | Large draw and order-line methods need separation between waypoint collection and drawing. Reuse traversal with sector rendering where semantics match. |
| [rendering/sector_renderer/sector_renderer.py](D:/Programming/Github_repos/Wormhole-Control/rendering/sector_renderer/sector_renderer.py) | Bounded effect surfaces and limits on large rendering allocations are justified, not gratuitous complexity. Preserve lifecycle/cache tests. |
| [rendering/sector_renderer/sector_overlay_renderer.py](D:/Programming/Github_repos/Wormhole-Control/rendering/sector_renderer/sector_overlay_renderer.py) | Large overlay/order traversal is the next renderer extraction target. Avoid coupling presentation geometry back into command validation. |
| [rendering/galaxy_renderer.py](D:/Programming/Github_repos/Wormhole-Control/rendering/galaxy_renderer.py), [rendering/drawing_utils.py](D:/Programming/Github_repos/Wormhole-Control/rendering/drawing_utils.py) | Keep view-specific drawing separate from geometry and selection rules. Profile before adding more caches or spatial indexes. |

## Refactoring and cruft cleanup

### Changes with a clear payoff

1. **Split `game_ai/commands.py` by responsibility.** Keep `CommandGateway` as the facade. Move projection state and replay into a focused module; separate preparation by a few gameplay domains. Use small records for cohesive projected state if they replace parallel dictionaries. Preserve ordering, payer identity, replacement/queue semantics, and partial-commit receipts.
2. **Extract movement resolution and assembly.** Pull sublight/hex/wormhole resolution from `TurnProcessor`, and pure template assembly from `Constructor`. Keep orchestration and state transitions visible in their current owners.
3. **Reduce repeated presentation knowledge.** Share order traversal. Do not force player-redacted AI output and rich GUI formatting into one universal serializer.
4. **Separate storage mechanics from design rules.** Custom-library file operations and registration belong together; cost formulas and design dataclasses can remain in a separate focused module. Retain atomic writes and failure preservation.

### Complexity signals

Particularly large functions at the reviewed revision include `handle_context_menu_action` (454 lines), `command_guidance` (421), `_order_factory` (401), `_process_movement` (396), `_draw_system_view_order_lines` (357), `assemble_unit_from_template` (311), and `process_event` (300). These counts include comments and blanks; use them to select review targets, not as arbitrary maximums.

## Comments and docstrings

The production AST inventory contains 2,274 functions/methods, of which 1,377 lack docstrings; 417 of those span at least 15 lines. This is a prioritization heuristic, not a claim that every property, closure, test helper, or trivial wrapper needs a long comment.

The user's standard is appropriate for **important functions**: an opening docstring should explain purpose, high-level flow, meaningful arguments, and return values. For mutators, also state side effects, timing, and failure behavior.

| Priority function | What its docstring should establish |
|---|---|
| `CommandGateway._order_factory` | Validated inputs, deferred construction versus immediate execution, returned factory/label, and rejection behavior. |
| `CommandGateway._prepare` / `_validate_unit_command` | Projection overrides, viewer/ownership checks, returned operations, and preflight versus execution guarantees. |
| `TurnProcessor._process_movement` | Current-player scope, actuator ownership, fuel payment, relocation ordering, and the returned sublight movement record consumed by hazards. |
| `MoveOrder.plan_route` | Input location assumptions, approach resolution, created child orders, no-safe-path behavior, and whether failure leaves prepared children. |
| `UseAbilityOrder.execute` | Range checks, automatic approach cases, activation/payment, and completion/failure transitions. |
| `VisibilityService.compute` | Exact visibility versus presence, allied/infiltrated coverage, `record_intel` side effects, and the snapshot return type. |
| `game_ai.order_view.order_layers` | Viewer-specific redaction and behavior for missing/unobservable targets. |
| `prepare_campaign` / `reconcile` | Validation stages, isolated allocations, reference restoration, returned prepared state, and prohibited live-state effects. |
| `strikecraft_service.process` | Difference between reconciliation and advancement, once-per-owner-round timing, expiry, and return scheduling. |

For a mutating procedure, “Returns: None; updates …” is enough. Do not add redundant parameter blocks to a one-line property just to improve a percentage.

**Keep** explanations of actuator ownership, refund payer identity, deliberate conservative fuel estimates, cleanup ordering, restoration without activation, graphical allocation limits, and SDL event-payload cleanup. Those comments capture non-obvious intent.

**Trim or correct** step-by-step arithmetic narration in geometry/pathfinding, comments such as “remove from system” immediately above a removal call, repeated log-like phase headings, and stale statements.

## Naming and organization

Rename internal symbols when touching the relevant area; a repository-wide rename would create noise. Persisted names, enum values, command fields, and public method names may require coordinated changes.

| Current name | Suggested direction | Why |
|---|---|---|
| `GUI_Handler` | `GuiHandler` | Conventional class naming. |
| `strikecraft_service.required` | `requires_carrier_service` | Clear when imported outside the module. |
| `strikecraft_service.process` | `process_owner_endurance` | Identifies the subject and timing. |
| `strikecraft_service.state_view` | `service_state` | States which state is being projected. |
| `dismantling.offline` | `is_dismantling_offline`, or keep module-qualified | “Offline” alone is easily confused with destroyed/disabled equipment. |
| `planetary_warfare.blocker` | `planetary_action_blocker`, or keep module-qualified | Carries the relevant action domain. |
| `_BatchProjection._credits` | `available_credits` / `remaining_credits` | Distinguishes projected spendable money from the live balance. |
| `game_ai/observation.py`'s `player_intelligence_options` | `player_command_options` | It now also contains planetary defense options. |
| `AntimatterHarvester.find_nearby_star` | Use `find_nearby_harvest_source` consistently | The helper also returns hydrogen nebulae. |
| `Hyperdrive.RECHARGE_DURATION` | `recharge_duration` | It is per-instance configuration, not an immutable module constant; coordinate save schema changes. |
| `ConstructionJob` | Clarify as `ConstructionSiteView` if renamed | It is a live derived selection marker, not the authoritative persisted job. |
| `TurnProcessor.process_turn` / `process_player_turn` | Distinguish `resolve_player_actions` from `end_turn` | The former does not necessarily advance the active player/round. |

Prefer `owner_round`, `turn_number`, `cooldown_remaining`, and `ready_round` according to their actual clock. Avoid calling all counters “turns” in docstrings when one advances per owner and another per global round.

## Documentation accuracy and cleanup plan

The existing six-document split is broadly appropriate. Remaining problems are repeated contracts and feature-by-feature appendices that restate rules. The generated reference check does not validate all handwritten prose. Use the [generated version table](docs/DEVELOPMENT.md#current-formats-and-protocols) for current format and protocol identifiers.

### Give each topic one owner

| Document | Keep | Remove, shorten, or replace with links |
|---|---|---|
| `README.md` | Introduction, install/run, first-game path, links. | Keep it short; do not move detailed reference material into it. |
| `REFERENCE.md` | Current player-facing rules, controls, equipment, generated catalog/terrain tables, storage troubleshooting. | Removed features, historical version notes, repeated protocol internals. |
| `DEVELOPMENT.md` | Setup/checks, short architecture map, development invariants, fixtures, documentation maintenance. | Repeated test command lists elsewhere can link here. A permanent file-by-file inventory would become stale; this report is a dated review. |
| `AGENTIC_AI.md` | Observation/disclosure contract, shared command semantics, provider turn flow, memory, repair/failure behavior, evaluation. | Detailed gameplay rules already owned by `REFERENCE.md`; repeated feature histories. |
| `CODEX_CONTROL.md` | Local bridge setup, CLI/envelopes, turn tokens, request IDs, waits, retry/recovery workflow, a few practical command examples. | Repeated shared command/rule descriptions; link to their owner in `AGENTIC_AI.md` or `REFERENCE.md`. |
| `SAVE_FORMAT.md` | Sole current format, strict rejection, schema/state ownership, prepare/commit, references/timers, persistence-specific invariants. | Repeated full gameplay rules. |

Suggested sequence:

1. Consolidate common command lifecycle rules: queue/replacement, preflight purity, execution recheck, partial commit, cancellation, and observable outcomes. Link feature sections to that contract.
2. Keep feature documentation focused on its actual deltas: targets, timing, costs, visibility, and interruption conditions.
3. Retain the generated reference blocks and central version table. Extend generation only for stable registry facts; human explanations should remain authored prose.
4. Run link checks, generated-reference checks, and the relevant contract tests after each documentation change.

## Testing infrastructure and results

### Latest recorded verification

The **2026-09-24 verification** passed the full offline CI runtime matrix locally. Focused regressions cover public failure history and briefings, save/load retention, private-reason sanitization, income preview/settlement parity and purity, generated version documentation, and the dismantling preview with default and themed managers. No live API requests were made.

| Local runtime | Full offline suite |
|---|---|
| Ubuntu under WSL, Python 3.10.21 (CI matrix version) | 3,893 passed, 5 skipped, 10 subtests passed; 239.00 seconds. |
| Ubuntu under WSL, Python 3.14.7 (CI matrix version) | 3,893 passed, 5 skipped, 10 subtests passed; 200.68 seconds. |
| Windows, Python 3.14.7 (CI matrix version) | 3,890 passed, 8 skipped, 10 subtests passed; 224.89 seconds. |

The Linux runs used the mounted Windows workspace and native Linux caches. Elapsed times include concurrent local validation and are not standalone benchmarks.

Configured Ruff checks and repository-wide `F,E9` lint pass, as do import boundaries, both mypy platform configurations, generated-reference consistency, and whitespace checks. All 104 local documentation links and anchors pass. The final privacy-assertion adjustment also passed focused checks on all three runtimes.

The Windows skips are symbolic-link tests requiring unavailable privileges; Windows junction tests pass. Linux skips the four Windows junction cases and one existing Windows-only check. No warnings were reported. Save and external wire formats are unchanged.

### Original audit checks

Environment: **Windows, Python 3.12.14**, project `.venv`; pygame-ce **2.5.7**, pygame_gui **0.6.14**, pytest **9.1.1**, Ruff **0.12.12**, mypy **1.15.0**. The installed OpenAI SDK is **2.54.0**, but no live provider request was made.

| Check | Result |
|---|---|
| Final full `python -m pytest -q --durations=20 -o cache_dir=.codex_test_cache/audit/pytest --junitxml=.codex_test_cache/audit/final-junit.xml` | **3,426 passed, 10 subtests passed, 1 warning; 208.50 s.** |
| `python -m ruff check .` | Passed. |
| CI's scoped `ruff --select F,E9` check | Passed. |
| `python scripts/check_import_boundaries.py` | Passed. |
| `python -m mypy --platform linux` | Passed for the seven configured files. |
| `python -m mypy --platform win32` | Passed for the seven configured files. |
| `python scripts/generate_reference.py --check` | Passed. |
| Additional repository-wide `ruff --select F,E9` | 272 diagnostics at the base revision; retained as historical evidence. The latest broader lint result is recorded above. |
| Local Markdown path/heading check | No unresolved local links detected. External URLs were not fetched. |
| `git diff --check` | Passed for the changes. |

CI executes Ubuntu Python 3.10/3.14 and Windows Python 3.14. The original audit did not run those jobs. The latest recorded verification above distinguishes actual local runtime tests from the two static mypy platform configurations; local Ubuntu runs use WSL rather than GitHub-hosted runners.

### Keep these parts of the infrastructure

- `tests/conftest.py` isolates user storage, restores counters/registries/random state, and owns game/GUI/service teardown.
- Headless SDL setup precedes application imports, allowing offline behavior checks without visible windows.
- The session Pygame fixture plus explicit event draining, default-manager release, and garbage collection addresses real resource ownership issues.
- Subprocess/import-boundary tests protect fresh-process behavior that in-process mocks cannot reliably establish.
- Save/load identity, zero-ID, reference, cancellation/refund, privacy, idempotency, rendering allocation, and failure-cleanup regressions cover durable risks. Their age alone is not a reason to remove them.
- Generated-reference verification and the current OS/Python CI matrix provide useful complementary checks.

### Bloat and blind spots to address

1. **Repeated setup:** Share simple campaign/entity builders where setup remains duplicated. Avoid fixtures that construct a full UI or large galaxy for a calculation needing two units.
2. **Narrow typing scope:** Strict mypy covers seven selected boundary files with silent import following, not the entire game. Add types first to preparation results, projection records, and persistence validators where they clarify contracts.
3. **Cross-boundary coverage:** Continue testing where individually tested layers can disagree instead of adding more implementation-call-count assertions.
4. **UI test cost:** Several large-display tests take approximately 2–4 seconds each. Keep representative resolution/scale transitions and privacy cases; consolidate redundant screenshots/setup only after checking they do not protect different regressions. A roughly 3.5-minute complete local run does not justify deleting meaningful tests just to reduce count.

## Proposed action plan

Proposed on **2026-09-24**, following a check of the relevant implementation at **`7a5bd48`**. These actions remain planned, not completed. The order balances impact, effort, and regression risk: three quick improvements followed by three focused refactors. Command handling is the highest-priority maintenance refactor; the earlier items provide smaller, independently reviewable improvements.

### 1. Consolidate contracts and improve selected docstrings

**Effort: small.** Make the existing [shared order contract](docs/AGENTIC_AI.md#shared-order-contract) and [commit guarantees](docs/AGENTIC_AI.md#commit-guarantees-and-lifecycle-feedback) the authoritative explanation of preflight, execution rechecks, cancellation, refunds, and partial commits. Replace repeated explanations in feature sections with links. Keep gameplay rules in `REFERENCE.md` and version facts in the generated table in `DEVELOPMENT.md`.

Document missing or weak contracts around projection, visibility, campaign preparation, and owner-turn timing. Distinguish owner turns, global rounds, cooldown counters, and ready-round deadlines. Several priority functions already have useful docstrings, so review gaps individually and retain explanations of non-obvious behavior.

**Complete when:** local links and generated-reference checks pass, each shared rule has one clear documentation home, and the selected function contracts explain side effects and failure behavior.

### 2. Close replaced logging resources correctly

**Effort: small.** [Logging setup](game_logging.py) removes existing handlers without explicitly closing them. Establish handler ownership and close replaced application handlers, preserving provider-payload filtering and safe handling of externally installed handlers. This addresses a cleanup concern; the review does not establish an application leak.

**Complete when:** repeated initialization releases old file handles, avoids duplicate output, and retains the existing logging privacy checks. Use temporary log files for verification.

### 3. Finish Unit Designer input feedback

**Effort: medium; direct user benefit.** [Parameter readers](gui/unit_editor_gui/param_readers.py) still swallow parsing errors and silently clamp or retain values. Extend the existing validation approach to those fields: retain invalid draft text, identify the affected field, explain accepted values, and prevent saving a stale configuration. Show the amount by which a design exceeds hull capacity. Reuse shared equipment rules and preserve legal zero and fractional values.

**Complete when:** invalid text, non-finite values, invalid integer inputs, and capacity violations produce actionable feedback; correcting a field clears its error; rejected saves/refits preserve designs and credits. Extend existing Designer and retrofit regressions where coverage is missing.

### 4. Split command projection from preparation and commit

**Effort: large; highest maintenance priority.** Refactor [CommandGateway](game_ai/commands.py) in separate changes. First extract projection and its supporting records; then extract preparation by gameplay domain. Keep the gateway responsible for batch sequencing, commit, and receipts. Add types at the extracted boundaries where they clarify state ownership. Preserve the public facade and command/result contracts.

**Complete when:** existing regressions preserve mutation-free rejection, command ordering, queued prerequisites, shared capacity reservations, original-payer refunds, hidden-target privacy, and accurate partial-commit results. Check interactions such as load-then-colonize, cancellation versus active paid jobs, allied docking capacity, and immediate versus deferred fuel gains. Add tests only for uncovered interactions; do not introduce rollback semantics or automatic retries for commit failures.

### 5. Extract detached unit assembly

**Effort: medium.** Move [template assembly](unit_components/constructor.py) into a focused module. The detached assembly function already exists, making this a relatively clear extraction. Keep deployment, construction progress, payment, cancellation, and settlement with their current owners. Preserve explicit template injection during campaign preparation and existing allocation isolation.

**Complete when:** campaign setup, ordinary construction, carrier production, and customization produce equivalent equipment and placement, with unchanged allocator isolation and settlement behavior. Preserve built-in, Testing, and human-only private-template boundaries.

### 6. Extract movement resolution

**Effort: medium to large.** Separate sublight, hex-jump, and wormhole-jump resolution from [TurnProcessor](turn_processor.py). Keep turn-phase sequencing visible in the processor and preserve the transient movement record consumed by environmental hazards. Make the extraction independently reviewable from changes to route planning.

**Complete when:** tests preserve debit-before-movement, refunds after rejected relocation, actuator ownership, tankless-wing exceptions, collision/inhibition rules, and recharge/damage timing. Verify that only positive committed sublight displacement contributes to that owner-turn's movement hazard record.

### Follow-up work

- **Separate custom-template storage:** Extract file operations and registration from design representation and cost calculations. Preserve atomic writes, whole-library validation, failure preservation, and private-template access rules.
- **Extract wizard pages:** Separate map preview and player/economy page responsibilities, retaining one clear owner for draft settings. Preserve Back navigation, home assignments, and failed-start state.
- **Share neutral order traversal:** Reuse traversal where sidebar and renderer semantics match, while keeping GUI formatting and viewer-specific AI redaction distinct.
- **Treat the BFS change as optional:** The current intersystem heap orders equal-distance candidates by system name; a straightforward BFS can change chosen routes. Establish route-equivalence tests, including equal-hop alternatives and hull-diameter restrictions, before replacing it.
- **Keep deterministic scenario probes small:** Use seeded save/command fixtures for construction, logistics, capture, docking, and overlapping effects where existing coverage leaves a boundary untested. Prefer a handful of cross-boundary invariants over a new fuzzing framework.
- **Measure before caching:** Profile observation building, command guidance, and repeated graph lookups in a large campaign. Cache only stable catalogue data or measured hotspots with explicit invalidation rules.

### Implementation and verification

Record a baseline once before implementation. Keep the six actions in separate reviewable changes, with projection extraction preceding the command-preparation split. Constructor assembly and movement extraction can each proceed independently of that split. Keep behavior changes separate from mechanical extractions and preserve save and command formats throughout this scope.

Run focused checks after each change, extending existing tests only for uncovered guarantees. Require the full offline suite and existing Linux/Windows CI checks for major refactors: Ruff, import boundaries, both configured mypy platforms, and generated-reference consistency. Documentation changes need local link/anchor checks and the applicable reference checks; meaningful gameplay and privacy tests should remain intact.

No implementation changes or new runtime verification are implied by this plan. The recorded test results above remain historical evidence until implementation checks are run.

## Local evidence

The most useful local diagnostic artifacts are:

- Latest full-suite JUnit results: [Windows Python 3.14](D:/Programming/Github_repos/Wormhole-Control/.codex_test_cache/maintenance/windows314-junit.xml), [Linux Python 3.10](D:/Programming/Github_repos/Wormhole-Control/.codex_test_cache/maintenance/linux310-junit.xml), and [Linux Python 3.14](D:/Programming/Github_repos/Wormhole-Control/.codex_test_cache/maintenance/linux314-junit.xml).
- Previous 2026-09-23 full-suite JUnit results: [Windows Python 3.14](D:/Programming/Github_repos/Wormhole-Control/.codex_test_cache/f689/windows314-junit.xml), [Linux Python 3.10](D:/Programming/Github_repos/Wormhole-Control/.codex_test_cache/f689/linux310-final-junit.xml), and [Linux Python 3.14](D:/Programming/Github_repos/Wormhole-Control/.codex_test_cache/f689/linux314-final-junit.xml).
- Additional Python 3.12 full-suite JUnit results: [Windows](D:/Programming/Github_repos/Wormhole-Control/.codex_test_cache/f457/full-junit.xml) and [Linux](D:/Programming/Github_repos/Wormhole-Control/.codex_test_cache/f457/linux-junit.xml).
- [Original audit full-suite output](D:/Programming/Github_repos/Wormhole-Control/.codex_test_cache/audit/final-pytest.log) and [JUnit results](D:/Programming/Github_repos/Wormhole-Control/.codex_test_cache/audit/final-junit.xml).
- [Persistence, path, and observation probes](D:/Programming/Github_repos/Wormhole-Control/.codex_test_cache/audit/reproductions.json).
- [AST inventory](D:/Programming/Github_repos/Wormhole-Control/.codex_test_cache/audit/inventory.json), [expanded lint output](D:/Programming/Github_repos/Wormhole-Control/.codex_test_cache/audit/expanded-lint.json), and [review statistics/link check](D:/Programming/Github_repos/Wormhole-Control/.codex_test_cache/audit/stats.json).

These files are ignored working artifacts, not proposed permanent test infrastructure. The report summarizes the relevant conclusions without requiring these files.
