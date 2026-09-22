# Wormhole Control — analysis and code review

Review date: **2026-09-22**  
Base revision: **`5c6fe34f2d1902f9cf2a8a5e50ec35a880edaefd`**

Resolved findings have been removed; remaining findings retain their original IDs. Code metrics and original audit results refer to the base revision above.

## Assessment

The project has useful foundations: explicit order ownership, separate campaign preparation and commit, allowlisted persistence, player-scoped observations, shared command definitions, bounded histories, and substantial offline tests. These are worth preserving. The remaining correctness problems concern saved player and path validation, launch placement, movement payment, command discovery, and AI request lifecycle. Several large modules also repeat related rules.

The best next step is a sequence of small correctness fixes followed by focused extraction and documentation cleanup. A new entity framework, generic transaction engine, wholesale UI rewrite, or repository-wide typing conversion would add risk without addressing the demonstrated problems directly.

**Latest verification: 3,529 tests passed, plus 10 subtests, in 211.01 seconds.** One font-preload warning remains. The findings below remain open; original audit results are retained in the testing section.

### Scope and method

- Read `README.md`, `docs/REFERENCE.md`, and `docs/AGENTIC_AI.md`, and cross-checked `DEVELOPMENT.md`, `SAVE_FORMAT.md`, and `CODEX_CONTROL.md` against implementation.
- Inventoried all tracked Python files with the AST: **228 production/tooling files, 55,721 lines; 175 test/support files, 48,791 lines** at the base revision. Empty package files and scripts are included; dependencies, ignored caches, and generated runtime data are excluded.
- Reviewed important application, domain, order, component, persistence, AI/control, UI, rendering, configuration, and testing files. Followed risky paths across modules and reproduced the findings identified as reproduced below. The file review records the principal conclusions; the AST inventory is broader than the detailed manual review.
- Ran the full offline suite, configured quality checks, additional lint, local Markdown link/heading checks, and isolated behavioral probes. Live provider calls, real API credentials, and the user's saved campaigns were not used.
- This is a source review and targeted behavioral audit, not a proof that every possible campaign, UI interaction, or malformed input is correct. Runtime coverage percentages were not measured, and the CI operating-system/Python matrix was not executed locally.

The remaining fixes, general cleanup, and documentation rewrites below are recommendations, not completed changes.

## Prioritized findings

The remaining findings are P2: reproducible correctness or lifecycle issues worth fixing next. These priorities are project triage judgments, not formal security ratings.

| ID | Priority | Finding | Evidence |
|---|---|---|---|
| F4 | P2 | Save identifiers can escape sidecar directories. | Accepted path-bearing ID and escaped write reproduced inside a temporary directory. |
| F5 | P2 | Malformed saved player fields survive preparation and break later use. | Invalid team accepted; observation then raises `TypeError`. |
| F6 | P2 | Carrier launch can place craft outside the sector. | A normal deployment completed at radius 5,040 in a radius-5,000 sector. |
| F7 | P2 | Movement ignores failed antimatter consumption. | Destroyed storage allowed movement without a fuel debit. |
| F8 | P2 | A legal player command is omitted from the supported-command list. | `upgrade_planetary_defenses` present in legal/options, absent from supported. |
| F9 | P2 | Resetting AI planning leaves new work queued behind the old request. | Reproduced with a blocking fake provider; no network involved. |

### F4 — Saved IDs are used as unchecked filesystem path segments

Sources: [campaign_persistence.py:74](D:/Programming/Github_repos/Wormhole-Control/campaign_persistence.py:74), [game_ai/memory.py:123](D:/Programming/Github_repos/Wormhole-Control/game_ai/memory.py:123), [save_manager.py:778](D:/Programming/Github_repos/Wormhole-Control/save_manager.py:778).

`campaign_id` is checked only for a nonempty string; `agent_id` is not constrained to a safe path segment. Memory and communication exporters concatenate these values into paths and create directories/write files.

**Reproduction:** `prepare_campaign()` accepted `campaign_id="../../escape"` and a path-bearing `agent_id`. A subsequent memory export resolved outside its configured saves directory. The probe was contained entirely within a disposable temporary directory.

The concrete risk is unintended creation/overwriting of sidecar files such as `memory.md` or `comms.md` when importing a crafted save and later exporting/saving. This finding does not demonstrate code execution or automatic writes merely from reading JSON.

**Fix:** Validate IDs as safe single path segments and verify resolved output containment before writing. Reject absolute paths, separators, traversal, and relevant Windows path forms. If production IDs are required to be exactly the generated format, document and enforce that contract; fixtures currently also use readable IDs such as `integrity`. Do not silently regenerate persisted identities to recover from invalid values.

### F5 — Saved player state bypasses the stricter new-game invariants

Sources: [campaign_persistence.py:83](D:/Programming/Github_repos/Wormhole-Control/campaign_persistence.py:83), [save_manager.py:384](D:/Programming/Github_repos/Wormhole-Control/save_manager.py:384), [domain/players.py:41](D:/Programming/Github_repos/Wormhole-Control/domain/players.py:41), [game_ai/observation.py:165](D:/Programming/Github_repos/Wormhole-Control/game_ai/observation.py:165).

The document validator requires player fields to exist but does not validate several of their types/values. Hydration passes them through a constructor that supplies defaults and normalizes configuration.

**Reproductions:**

- `team_id={"bad": true}` is accepted; building the next observation raises `TypeError` at `int(player.team_id)`.
- `persistent_id=null` is accepted and becomes a newly generated ID.
- `ai_repair_retries=false` is accepted and becomes the default retry count.

The first case permits unusable state past the preparation boundary. The others contradict strict current-format restoration and can conceal corruption or change identity.

**Fix:** Validate saved names, team IDs, persistent/agent IDs, controller/configuration fields, and relevant identity uniqueness before constructors run. Reuse small value validators from setup where the contracts actually match, while keeping new-game defaulting separate from strict saved-state restoration. Rejected loads must leave the live campaign and allocators unchanged.

### F6 — Launch placement skips sector bounds for real campaigns

Sources: [HangarComponent.deploy:122](D:/Programming/Github_repos/Wormhole-Control/unit_components/hangar.py:122), [StrikecraftBayComponent.deploy:485](D:/Programming/Github_repos/Wormhole-Control/unit_components/strikecraft.py:485), [tests/test_hangar.py:208](D:/Programming/Github_repos/Wormhole-Control/tests/test_hangar.py:208).

Both launch implementations apply their radius test only when `self.unit.in_system is None`. Deployed carriers in real campaigns have a system name, so this test is skipped. The normal hangar also accepts the first random candidate without checking collision geometry. The order's hazard checks concern the carrier location, not every candidate launch location.

**Reproduction:** A real carrier at `(4990, 0)` docks a TINY ship. Force angle zero and offset 50. `DeployUnitOrder` completes, inserts the craft into the sector, and places it at `(5040, 0)` although the sector radius is 5,000. The strikecraft bay contains the same faulty bounds condition; that parallel path was confirmed by inspection rather than a second launch probe.

The existing offset test uses `in_system=None` with a comment equating that to “sector view,” and places the carrier at 990. Neither reflects the live location model or the current boundary, so it misses the bug.

**Fix:** Validate every candidate against the actual sector boundary and relevant obstacles/hazards. Use bounded attempts and return failure without changing containment when no candidate is safe. Share a small placement predicate where behavior is common; retain wing-specific magnetic-storm rules. Replace the misleading fixture with a real carrier near the current boundary and add blocked-placement coverage.

### F7 — Movement proceeds after a failed fuel debit

Sources: [turn_processor.py:248](D:/Programming/Github_repos/Wormhole-Control/turn_processor.py:248), [system-jump debit:413](D:/Programming/Github_repos/Wormhole-Control/turn_processor.py:413), [hex-jump debit:542](D:/Programming/Github_repos/Wormhole-Control/turn_processor.py:542).

Movement checks the tank's quantity, then ignores the boolean returned by `consume()` and proceeds when consumption refuses payment. Both jump branches repeat the pattern.

**Reproduction:** A real ship with a valid MoveOrder, speed 100, and a tank holding 100 AM moves 100 units. With a healthy tank it finishes at 98 AM; with destroyed storage it still moves 100 units and retains 100 AM. The jump cases were identified by inspection, not separately executed.

**Fix:** Require the appropriate functional fuel source and successful debit before committing displacement. Preserve any deliberate fuel-exempt craft rules explicitly. Add sublight and jump tests for destroyed storage and verify that a failed relocation does not consume fuel either.

### F8 — Player-level command discovery contradicts itself

Source: [game_ai/observation.py:144](D:/Programming/Github_repos/Wormhole-Control/game_ai/observation.py:144) and [supported list:222](D:/Programming/Github_repos/Wormhole-Control/game_ai/observation.py:222).

The code adds `upgrade_planetary_defenses` to player-level options and, when available, `legal`, but omits it from the hardcoded `supported` array. A populated owned Terran colony reproduces `legal - supported == {"upgrade_planetary_defenses"}`.

**Fix:** Derive the player-level supported list from the existing command specifications, or minimally include the missing command and add an invariant test that every legal command is supported. Do not create another command registry.

### F9 — AI reset does not release the only planning worker

Sources: [game_ai/coordinator.py:46](D:/Programming/Github_repos/Wormhole-Control/game_ai/coordinator.py:46), [reset/shutdown:111](D:/Programming/Github_repos/Wormhole-Control/game_ai/coordinator.py:111), [provider configuration:32](D:/Programming/Github_repos/Wormhole-Control/game_ai/adapters/openai_responses.py:32).

`Future.cancel()` cannot stop an already-running provider call. Reset discards the handle, but the single-worker executor remains occupied. New campaign planning is submitted to the same executor and waits behind the obsolete request. The configured request timeout is 120 seconds with two SDK retries, so the delay can be substantial; it is not necessarily capped at one timeout interval.

**Reproduction:** A fake provider blocks its first request. After `reset()` and submission of a replacement, the old future remains running, the new future is queued, and coordinator state says `thinking`. Only releasing the old request starts the new one. Stale results are not shown to mutate the new campaign; the demonstrated issue is delayed replacement work.

`shutdown(wait=False)` also does not terminate an active thread or guarantee immediate Python process exit.

**Fix:** Define a bounded request cancellation/retirement policy and explicit provider shutdown ownership. Prefer cancellable I/O or a deliberately bounded lifecycle over accumulating replacement executors/threads. Test reset and shutdown with an actually running fake provider, not only an unstarted/cancellable Future.

## Important file review

The following records individual important files and the main conclusions from their review. Related small implementations are summarized together where a separate row would repeat the same recommendation.

### Application, domain, and navigation

| File | Review conclusion |
|---|---|
| [game.py](D:/Programming/Github_repos/Wormhole-Control/game.py) | Correctly distinguishes successful load commit from later presentation failure. At 842 lines it still combines application lifecycle, selection, AI scheduling, conversations, and persistence entry points. Extract one cohesive responsibility at a time; do not replace it with a service container. |
| [game_setup.py](D:/Programming/Github_repos/Wormhole-Control/game_setup.py) | Candidate construction, explicit template input, and post-setup reconciliation are useful. Document preview ownership and failure behavior at the preparation entry point. Keep startup defaults separate from saved-state validation. |
| [game_settings.py](D:/Programming/Github_repos/Wormhole-Control/game_settings.py) | Stronger input checks than saved players, including rejecting booleans as integers. Reuse the relevant checks for F5 without importing wizard logic into persistence. |
| [application_bootstrap.py](D:/Programming/Github_repos/Wormhole-Control/application_bootstrap.py) | Display discovery has clear ownership and cleanup. Preserve explicit startup discovery instead of restoring import-time SDL behavior. |
| [display_config.py](D:/Programming/Github_repos/Wormhole-Control/display_config.py) | Explicit display metrics and typed boundaries are a good separation. Prefer passing this object over adding more display globals. |
| [app_preferences.py](D:/Programming/Github_repos/Wormhole-Control/app_preferences.py) | Atomic replacement and UI-visible failure propagation are appropriate for a small preferences file. No need for a configuration framework. |
| [game_camera.py](D:/Programming/Github_repos/Wormhole-Control/game_camera.py) | Shared zoom mechanics are sensible. Modal/input-blocking knowledge is lengthy; let each dialog participate in one small common “blocks gameplay input” query as new dialogs are added. |
| [game_logging.py](D:/Programming/Github_repos/Wormhole-Control/game_logging.py) | Filtering provider payload logs is valuable. Review handler ownership if logging is configured repeatedly: removed handlers are not explicitly closed. This is a cleanup concern, not a demonstrated application leak. |
| [constants.py](D:/Programming/Github_repos/Wormhole-Control/constants.py) | Keep stable shared rules here; newer tactical/planetary balance modules already provide useful topic separation. Avoid scattering renamed duplicates across catalogs and GUI helpers. |
| [domain/identity.py](D:/Programming/Github_repos/Wormhole-Control/domain/identity.py) | Allocation isolation is a useful invariant. Keep tests for zero IDs, high restored IDs, and rejected-load allocator preservation. |
| [domain/coordinates.py](D:/Programming/Github_repos/Wormhole-Control/domain/coordinates.py) | A small typed coordinate boundary is preferable to another geometry hierarchy. Gradually reduce tuple/attribute compatibility branching where callers have a known type. |
| [domain/players.py](D:/Programming/Github_repos/Wormhole-Control/domain/players.py) | Central ownership/team helpers already exist. Use them instead of copied `_are_allies` implementations. Constructor defaulting is inappropriate for strict hydration unless inputs are validated first. |
| [domain/units.py](D:/Programming/Github_repos/Wormhole-Control/domain/units.py) | Component replacement/destruction cleanup has useful intent documentation. The class remains broad; preserve cleanup ordering and distinguish installed, operational, and deployed state in callers. |
| [domain/celestials.py](D:/Programming/Github_repos/Wormhole-Control/domain/celestials.py) | Gas-giant release already uses bounded candidates, common safety checks, and commit-after-placement. This provides a simpler model for correcting carrier deployment. Sabotage implementation disagrees with the manual. |
| [domain/construction_job.py](D:/Programming/Github_repos/Wormhole-Control/domain/construction_job.py) | This is a presentation/selection view of a live job, not another persisted entity. Name/document that distinction and avoid expanding it into authoritative construction state. |
| [domain/communications.py](D:/Programming/Github_repos/Wormhole-Control/domain/communications.py) | Keep conversation persistence distinct from filesystem export. Player identity/path validation belongs before export. |
| [domain/deployables.py](D:/Programming/Github_repos/Wormhole-Control/domain/deployables.py), [domain/minefields.py](D:/Programming/Github_repos/Wormhole-Control/domain/minefields.py) | Distinct tactical entities are justified. Keep their ownership, visibility, and removal semantics explicit rather than treating every object as a ship through duck typing. |
| [galaxy.py](D:/Programming/Github_repos/Wormhole-Control/galaxy.py) | Generation, topology, lookups, and relocation share a large file. Separate generation from live graph operations if touched next. Preserve reciprocal wormhole and containment invariants. |
| [geometry.py](D:/Programming/Github_repos/Wormhole-Control/geometry.py) | Pure geometric helpers are a good test boundary. Some comments narrate elementary arithmetic; retain tolerance, fallback, tangency, and safety explanations. |
| [pathfinding.py](D:/Programming/Github_repos/Wormhole-Control/pathfinding.py) | The intersystem graph has unit-weight edges, so BFS can replace Dijkstra's heap/distances with fewer moving parts. Preserve deterministic tie behavior and hull-diameter filtering. This is a simplicity opportunity, not a demonstrated performance bottleneck. |
| [location_validation.py](D:/Programming/Github_repos/Wormhole-Control/location_validation.py) | Useful shared destination validation. Extend consistent placement validation to launch candidates rather than duplicating only part of it. |
| [visibility.py](D:/Programming/Github_repos/Wormhole-Control/visibility.py) | Explicit snapshots and `record_intel=False` support pure observation/loading. Document that distinction on `compute()` and replace copied relationship helpers with the canonical ones. |
| [campaign_graph.py](D:/Programming/Github_repos/Wormhole-Control/campaign_graph.py) | Cycle/duplicate-containment detection and explicit stored-unit traversal are worth keeping. Use this traversal when “all owned units” truly includes stored craft; use deployment checks otherwise. |

### Resolution, orders, components, and designs

| File | Review conclusion |
|---|---|
| [turn_processor.py](D:/Programming/Github_repos/Wormhole-Control/turn_processor.py) | Phase sequencing is important and currently difficult to read beside the 396-line movement method. Extract sublight, hex jump, and wormhole jump resolution; fix F7 first. Describe owner-turn versus global-round timing at the orchestration point. |
| [economy.py](D:/Programming/Github_repos/Wormhole-Control/economy.py) | Income estimation repeats resolution rules from `_process_resource_generation`, including slightly different sabotage relationship checks. Return a shared pure income breakdown and let resolution apply it. Preserve the explicitly documented upkeep exclusions. |
| [events.py](D:/Programming/Github_repos/Wormhole-Control/events.py) | Typed UI events are useful. Avoid adding an additional parallel command representation for every new feature when an existing gateway operation already fits. |
| [order_system.py](D:/Programming/Github_repos/Wormhole-Control/order_system.py) | Human-event translation and validation overlap with gateway/order logic. Reuse domain predicates and command preparation where practical; keep UI event translation thin. |
| [unit_orders/base.py](D:/Programming/Github_repos/Wormhole-Control/unit_orders/base.py) | Explicit roots, suborders, outcomes, and cancellation ownership justify this abstraction. Document which transitions execute children synchronously and which wait for a turn. |
| [unit_components/commander.py](D:/Programming/Github_repos/Wormhole-Control/unit_components/commander.py) | Actuator ownership and separate standing/explicit work are valuable safeguards. Keep the detailed intent comments around cancellation and stale targets. Sidebar formatting could eventually leave this stateful component. |
| [unit_orders/movement.py](D:/Programming/Github_repos/Wormhole-Control/unit_orders/movement.py) | Route planning, target approach, waypoint execution, and collision rules need smaller named units. Its class/method docs should explain when auto-approach replans and what failed planning leaves behind. |
| [unit_orders/abilities.py](D:/Programming/Github_repos/Wormhole-Control/unit_orders/abilities.py) | Large branching dispatcher, UI warnings inside domain execution, and an inaccurate class docstring about position-target auto-movement. Extract target/range validation without inventing a new ability engine. |
| [unit_orders/construction.py](D:/Programming/Github_repos/Wormhole-Control/unit_orders/construction.py), [unit_orders/refit.py](D:/Programming/Github_repos/Wormhole-Control/unit_orders/refit.py) | Rechecking at execution and recording the actual payer are important. Keep cancellation/refund tests; avoid trusting UI price/duration hints. Refit's direct GUI warning callback is residual domain/presentation coupling. |
| [unit_orders/combat.py](D:/Programming/Github_repos/Wormhole-Control/unit_orders/combat.py), [unit_orders/stance.py](D:/Programming/Github_repos/Wormhole-Control/unit_orders/stance.py) | Explicit attack and standing engagement are distinct behaviors and should remain distinct. Consolidate shared target/range predicates, not the entire order lifecycle. |
| [unit_orders/hangar.py](D:/Programming/Github_repos/Wormhole-Control/unit_orders/hangar.py) | Launch orders check carrier hazards, but placement must also validate the selected craft position. See F6. |
| [unit_orders/fuel_transport.py](D:/Programming/Github_repos/Wormhole-Control/unit_orders/fuel_transport.py), [unit_orders/antimatter.py](D:/Programming/Github_repos/Wormhole-Control/unit_orders/antimatter.py) | Long-lived transport phases are justified by waiting, sourcing, and delivery. Document phase transitions and reserve semantics rather than repeating branches in comments. |
| [unit_orders/intelligence.py](D:/Programming/Github_repos/Wormhole-Control/unit_orders/intelligence.py) | Relocation, extraction, sabotage, discovery, and ownership are a substantial subsystem. Prefer shared target predicates and a clearly documented public failure vocabulary. |
| [unit_components/constructor.py](D:/Programming/Github_repos/Wormhole-Control/unit_components/constructor.py) | At 1,216 lines, combines assembly, eligibility, job state, settlement, and presentation. Extract pure assembly from the stateful constructor; preserve explicit template injection used in preparation. |
| [unit_components/antimatter.py](D:/Programming/Github_repos/Wormhole-Control/unit_components/antimatter.py) | `consume()` signals failure correctly for destroyed storage, but callers do not consistently honor it. Make the positive finite amount contract explicit at this reusable boundary. |
| [unit_components/movement.py](D:/Programming/Github_repos/Wormhole-Control/unit_components/movement.py) | Ownership tokens on targets are useful. Per-instance `RECHARGE_DURATION` looks like a module constant; rename only with deliberate persistence handling. |
| [unit_components/weapons.py](D:/Programming/Github_repos/Wormhole-Control/unit_components/weapons.py) | Persisting effective turret values avoids double-applying variants. |
| [unit_components/hangar.py](D:/Programming/Github_repos/Wormhole-Control/unit_components/hangar.py) | F6 and a misleading `in_system is None` branch. The SMALL-slot accounting branch also predates the current TINY-only docking rule; verify saved-state expectations before removing it. |
| [unit_components/strikecraft.py](D:/Programming/Github_repos/Wormhole-Control/unit_components/strikecraft.py) | Stable slots, production selection, containment, launch, and replenishment are related but crowded. Keep slot identity and paid work explicit; reuse safe placement and improve method contracts. |
| [unit_components/abilities/base.py](D:/Programming/Github_repos/Wormhole-Control/unit_components/abilities/base.py) | Separating static definitions from runtime instances is useful. Preserve explicit schema checks and restoration without activation side effects. |
| [unit_components/abilities/component.py](D:/Programming/Github_repos/Wormhole-Control/unit_components/abilities/component.py) | Preserve the separate ordinary, tactical, and toggle lifecycle contracts when reorganizing. |
| [unit_components/abilities/registry.py](D:/Programming/Github_repos/Wormhole-Control/unit_components/abilities/registry.py) | Existing definitions should remain the source of ability metadata. Do not add another manual requirements mapping. |
| [unit_templates.py](D:/Programming/Github_repos/Wormhole-Control/unit_templates.py) | Built-in, Testing, and private categories are deliberately distinct. Preserve that privacy boundary and explicit Testing publication. Module import still reads the bundled catalog; this is different from unwanted user-data loading. |
| [custom_unit_templates.py](D:/Programming/Github_repos/Wormhole-Control/custom_unit_templates.py) | Dataclasses, costs, validation adapters, conversion, and storage make this a 1,149-line mixed module. Separate the storage manager from design representation/costs, remove the fake mapping adapter, and correct its opening description. |
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
| [order_history.py](D:/Programming/Github_repos/Wormhole-Control/order_history.py) | Bounded, saved outcomes are useful. `hazard_blocked` is emitted by orders but absent from `PUBLIC_REASONS`, so history normalizes it to `execution_failed`; unify the intentional public vocabulary. |
| [turn_briefing.py](D:/Programming/Github_repos/Wormhole-Control/turn_briefing.py) | Frozen reports and recipient-scoped recording are good. Document begin/finish collection windows and omitted-count accounting at the important entry points. |
| [save_manager.py](D:/Programming/Github_repos/Wormhole-Control/save_manager.py) | File I/O, JSON serialization, object hydration, and sidecar exports share 875 lines. Separate sidecars first, fix F4/F5, and keep file replacement behavior explicit. |
| [campaign_persistence.py](D:/Programming/Github_repos/Wormhole-Control/campaign_persistence.py) | Prepare/reconcile/commit is worth preserving. Large validators can be split by document section while retaining one strict entry point. Presence checks alone do not establish usable state. |
| [persistence_context.py](D:/Programming/Github_repos/Wormhole-Control/persistence_context.py) | A small scoped allocation mechanism solves a real transactional problem. Keep restoration in `finally`; document main-thread preparation expectations. |
| [state_codec.py](D:/Programming/Github_repos/Wormhole-Control/state_codec.py) | Explicit tags and enum allowlisting are preferable to arbitrary object deserialization. There is overlapping value encoding in `save_manager`; consolidate common primitives at a deliberate format change, not via compatibility layers. |
| [unit_components/persistence.py](D:/Programming/Github_repos/Wormhole-Control/unit_components/persistence.py), [tactical_persistence.py](D:/Programming/Github_repos/Wormhole-Control/tactical_persistence.py) | Keep allowlists, explicit field ownership, and post-reference validation. Avoid reflective serialization of every attribute. |

### AI, local control, UI, and rendering

| File | Review conclusion |
|---|---|
| [game_ai/commands.py](D:/Programming/Github_repos/Wormhole-Control/game_ai/commands.py) | Highest-priority complexity hotspot: 2,069 lines at the base revision, large preflight ledger and dispatch functions. Separate projection, command preparation, and commit orchestration while retaining clear failure-stage receipts. |
| [game_ai/command_spec.py](D:/Programming/Github_repos/Wormhole-Control/game_ai/command_spec.py) | Already the right place for shared command shape/capability metadata. Use it for player command discovery and generated version/field documentation. |
| [game_ai/contracts.py](D:/Programming/Github_repos/Wormhole-Control/game_ai/contracts.py), [game_ai/schema.py](D:/Programming/Github_repos/Wormhole-Control/game_ai/schema.py) | Preserve strict structured-output fields and the distinction between transport schema and semantic game legality. Keep schema generation connected to command specifications. |
| [game_ai/observation.py](D:/Programming/Github_repos/Wormhole-Control/game_ai/observation.py) | Explicit disclosure and bounded option lists are valuable. Fix F8 and document which IDs/targets are safe for a viewer. Test private-state changes for absence of public differences. |
| [game_ai/order_view.py](D:/Programming/Github_repos/Wormhole-Control/game_ai/order_view.py), [game_ai/intelligence.py](D:/Programming/Github_repos/Wormhole-Control/game_ai/intelligence.py) | Redaction is a contract, not incidental formatting. Add function-level docs explaining unavailable targets, owner/allied access, and omission behavior. |
| [game_ai/rules.py](D:/Programming/Github_repos/Wormhole-Control/game_ai/rules.py) | `command_guidance()` is 421 lines. Split its output assembly by capability/domain and reuse existing validators; avoid another parallel set of legality rules. |
| [game_ai/coordinator.py](D:/Programming/Github_repos/Wormhole-Control/game_ai/coordinator.py) | Main-thread mutation, stale-result checks, and bounded semantic repair are useful. Worker cancellation/lifecycle remains incomplete; see F9. |
| [game_ai/adapters/openai_responses.py](D:/Programming/Github_repos/Wormhole-Control/game_ai/adapters/openai_responses.py) | Provider details are correctly isolated. Document/own client closure, request cancellation, timeout, and transport retries together. No live model availability or provider behavior was tested in this review. |
| [game_ai/runtime.py](D:/Programming/Github_repos/Wormhole-Control/game_ai/runtime.py), [game_ai/config.py](D:/Programming/Github_repos/Wormhole-Control/game_ai/config.py) | Central runtime limits and credential-loading isolation are useful. Keep permissive user configuration normalization out of strict campaign restoration. |
| [game_ai/memory.py](D:/Programming/Github_repos/Wormhole-Control/game_ai/memory.py) | Bounded sections and atomic sidecar replacement are appropriate. Fix path containment. The 8,000-character bound applies to receipts, not all memory sections combined; make wording precise. |
| [game_ai/evaluation.py](D:/Programming/Github_repos/Wormhole-Control/game_ai/evaluation.py) | Provider-independent cases and gateway acceptance scoring are useful. Keep offline contract tests separate from model quality/cost evaluations. |
| [game_control_protocol.py](D:/Programming/Github_repos/Wormhole-Control/game_control_protocol.py) | Loopback-only binding, size limits, turn tokens, response caching, and main-thread pumping form a sensible local boundary. Document cache lifetime and uncertain outcomes; do not describe preflight atomicity as rollback of every possible commit failure. |
| [game_control.py](D:/Programming/Github_repos/Wormhole-Control/game_control.py) | Small CLI is appropriate. Keep transport recovery tied to request IDs and observation refresh rather than blind command retries. |
| [gui/handler.py](D:/Programming/Github_repos/Wormhole-Control/gui/handler.py) | Acts as a UI facade but carries broad mutable state. Prefer focused dialogs/helpers and explicit lifecycle cleanup over adding more pass-through wrappers. |
| [gui/layout_new_game_wizard.py](D:/Programming/Github_repos/Wormhole-Control/gui/layout_new_game_wizard.py) | At 1,740 lines, combines layout, preview manipulation, player configuration, and validation feedback. Split by wizard page/preview responsibility, keeping draft settings ownership obvious. |
| [gui/event_router.py](D:/Programming/Github_repos/Wormhole-Control/gui/event_router.py) | `process_event()` is 300 lines. A few named per-dialog/feature handlers are simpler than continuing the branch chain or inventing a universal event framework. |
| [input_processor/context_actions.py](D:/Programming/Github_repos/Wormhole-Control/input_processor/context_actions.py) | `handle_context_menu_action()` is 454 lines. Extract handlers by actual action family; data-driven routing is suitable for simple direct dispatch only. |
| [input_processor/context_menu_builder.py](D:/Programming/Github_repos/Wormhole-Control/input_processor/context_menu_builder.py) | Repeats relationship helpers and capability decisions. Use canonical relationship/domain predicates so menu legality does not drift from execution. |
| [gui/sidebar/view.py](D:/Programming/Github_repos/Wormhole-Control/gui/sidebar/view.py) | Stable selection identity and measuring from the viewport origin address real UI concerns. |
| [gui/sidebar/panels_unit.py](D:/Programming/Github_repos/Wormhole-Control/gui/sidebar/panels_unit.py), [gui/sidebar/panels_world.py](D:/Programming/Github_repos/Wormhole-Control/gui/sidebar/panels_world.py) | Keep user-visible rows distinct from internal identity metadata. Preserve public equipment/privacy comparisons when changing layouts. |
| [gui/sidebar/order_formatting.py](D:/Programming/Github_repos/Wormhole-Control/gui/sidebar/order_formatting.py) | Large order-type formatter duplicates some traversal/knowledge used by renderers and AI views. Reuse neutral order traversal where possible, while retaining viewer-specific redaction. |
| [gui/unit_editor_gui/widget_factory.py](D:/Programming/Github_repos/Wormhole-Control/gui/unit_editor_gui/widget_factory.py), [gui/retrofit_gui/layout.py](D:/Programming/Github_repos/Wormhole-Control/gui/retrofit_gui/layout.py) | Four widget helpers have identical bodies across these modules. Extract those small helpers, rather than building a generic form engine. |
| [gui/unit_editor_gui/param_readers.py](D:/Programming/Github_repos/Wormhole-Control/gui/unit_editor_gui/param_readers.py) | Input handling silently substitutes/defaults or preserves old values in several places. Consistent inline feedback would improve clarity. |
| [gui/theme_loader.py](D:/Programming/Github_repos/Wormhole-Control/gui/theme_loader.py), [gui/text_layout.py](D:/Programming/Github_repos/Wormhole-Control/gui/text_layout.py) | Scaled in-memory themes and measured wrapping are useful. Resolve the remaining rich-text fallback font warning at the actual manager/style used by the dismantling preview. |
| [rendering/system_renderer.py](D:/Programming/Github_repos/Wormhole-Control/rendering/system_renderer.py) | Large draw and order-line methods need separation between waypoint collection and drawing. Reuse traversal with sector rendering where semantics match. |
| [rendering/sector_renderer/sector_renderer.py](D:/Programming/Github_repos/Wormhole-Control/rendering/sector_renderer/sector_renderer.py) | Bounded effect surfaces and limits on large rendering allocations are justified, not gratuitous complexity. Preserve lifecycle/cache tests. |
| [rendering/sector_renderer/sector_overlay_renderer.py](D:/Programming/Github_repos/Wormhole-Control/rendering/sector_renderer/sector_overlay_renderer.py) | Large overlay/order traversal is the next renderer extraction target. Avoid coupling presentation geometry back into command validation. |
| [rendering/galaxy_renderer.py](D:/Programming/Github_repos/Wormhole-Control/rendering/galaxy_renderer.py), [rendering/drawing_utils.py](D:/Programming/Github_repos/Wormhole-Control/rendering/drawing_utils.py) | Keep view-specific drawing separate from geometry and selection rules. Profile before adding more caches or spatial indexes. |

## Refactoring and cruft cleanup

### Changes with a clear payoff

1. **Share narrow invariants first.** Movement fuel/payment checks, player identity validation, and candidate placement remain inconsistent. Fix these in small helpers close to their domain, with one authoritative result used by UI, AI, and execution where applicable.
2. **Split `game_ai/commands.py` by responsibility.** Keep `CommandGateway` as the facade. Move projection state and replay into a focused module; separate preparation by a few gameplay domains. Use small records for cohesive projected state if they replace parallel dictionaries. Preserve ordering, payer identity, replacement/queue semantics, and partial-commit receipts.
3. **Extract movement resolution and assembly.** Pull sublight/hex/wormhole resolution from `TurnProcessor`, and pure template assembly from `Constructor`. Keep orchestration and state transitions visible in their current owners.
4. **Reduce repeated presentation knowledge.** Share order traversal and tiny widget helpers. Do not force player-redacted AI output and rich GUI formatting into one universal serializer.
5. **Separate pure calculations from settlement.** A shared income breakdown can drive the HUD and resource generation. Extend the existing preview/commit pattern where calculations are repeated.
6. **Separate storage mechanics from design rules.** Custom-library file operations and registration belong together; cost formulas and design dataclasses can remain in a separate focused module. Retain atomic writes and failure preservation.

### Concrete low-risk cleanup candidates

- Replace copied relationship helpers in `visibility.py` and `input_processor/context_menu_builder.py` with `domain.players.are_allies/are_enemies`; their compatibility handling is already present centrally.
- Replace `_AbilityRequirementsMap(dict)` with calls to the existing `get_ability_required_components()`. Consumers use `.get()`; the subclass is otherwise an empty dictionary with surprising mapping semantics.
- Remove the redundant `ADVANCED_CLOAKING_MIN_HULL` definition in `custom_unit_templates.py:105`; the later import at line 184 overwrites it.
- Remove the duplicated `game.display_config = DisplayConfig()` in `tests/support/campaigns.py`.
- Consolidate the repeated collision-test setup and identical editor/retrofit widget builders. Avoid abstract base test classes for a single duplicated fixture.
- Prune unused imports, unnecessary f-string prefixes, and truly unused locals in small batches. Review import side effects and local assignments before automatic deletion.
- Simplify the generic `.gitignore` template's irrelevant Django/Celery/Sage/Jupyter sections if desired. This is minor housekeeping, not a significant source of runtime complexity.
- `theme.json` references six of the fourteen bundled font files. The other eight are asset-removal candidates after checking packaging, runtime selection, and font-license requirements. Do not delete fonts solely because an import search finds no name.

### Quantified lint and complexity signals

The configured whole-repository Ruff check selects only `F821`, `F822`, and `F823`. It passes. A broader **diagnostic** run with `--select F,E9` reports:

| Diagnostic | Production/tooling | Tests |
|---|---:|---:|
| Unused imports (`F401`) | 159 | 31 |
| Unused locals (`F841`) | 2 | 60 |
| Redefinitions (`F811`) | 1 | 6 |
| f-strings without placeholders (`F541`) | 12 | 1 |
| **Total** | **174** | **98** |

These are **272 cleanup signals, not 272 bugs**. The test redefinitions reported here are import/shadowing cases, not evidence of overwritten test functions. Extend lint to cleaned modules incrementally; do not enable a large new rule set and then suppress its output wholesale.

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

**Trim or correct** step-by-step arithmetic narration in geometry/pathfinding, comments such as “remove from system” immediately above a removal call, repeated log-like phase headings, and stale statements. Specific inaccuracies include:

- `custom_unit_templates.py` claims custom designs are inserted into `UNIT_TEMPLATES` and mentions `create_unit_from_template`; current private registration is separate and the constructor entry point is `instantiate_unit_from_template`.
- The same module says only Engines, Weapons, Defenses, and Hyperdrive use dynamic costs, despite additional dynamic components.
- `UseAbilityOrder` claims position-target abilities perform no auto-movement, but the implementation creates approach orders for applicable position-target effects.
- The hangar test equates a missing system name with the camera's sector view; location and view mode are independent.

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

The existing six-document split is broadly appropriate. The problems are repeated contracts, feature-by-feature appendices that restate rules, and old version claims outside generated blocks. No broken local Markdown file/heading links were found by the audit checker. The generated reference check passes, but it does not validate all handwritten prose.

### Specific inaccuracies

| Location | Current problem | Required correction |
|---|---|---|
| [CODEX_CONTROL.md:247](D:/Programming/Github_repos/Wormhole-Control/docs/CODEX_CONTROL.md:247) | Says command contract 15. | Current command contract is 17. |
| [CODEX_CONTROL.md:360](D:/Programming/Github_repos/Wormhole-Control/docs/CODEX_CONTROL.md:360), [CODEX_CONTROL.md:520](D:/Programming/Github_repos/Wormhole-Control/docs/CODEX_CONTROL.md:520) | Says observation 12 / command 10. | Current observation is 21 / command 17; socket protocol remains 3. |
| [CODEX_CONTROL.md:504](D:/Programming/Github_repos/Wormhole-Control/docs/CODEX_CONTROL.md:504) | Calls the current turn-summary observation schema 15. | Use the current schema or link to one version table. |
| [SAVE_FORMAT.md:326](D:/Programming/Github_repos/Wormhole-Control/docs/SAVE_FORMAT.md:326) | Dismantling section says Bay component schema 4. | Current Strikecraft Bay schema is 5; another section already documents it correctly. |
| [REFERENCE.md:1031](D:/Programming/Github_repos/Wormhole-Control/docs/REFERENCE.md:1031) | Mentions partially recovering a cache and retaining its deployment slot. | Remove the obsolete fuel-cache statement; that deployable/order no longer exists. |
| [REFERENCE.md:1298](D:/Programming/Github_repos/Wormhole-Control/docs/REFERENCE.md:1298) | Sensors sabotage disables both ranges. | Code halves short-range radius and disables long-range coverage. |
| [REFERENCE.md:1299](D:/Programming/Github_repos/Wormhole-Control/docs/REFERENCE.md:1299) | Antimatter sabotage leaks 5 AM per turn. | `Unit.apply_sabotage` immediately attempts to drain half the current fuel; no corresponding 5-AM-per-turn drain exists in the reviewed update path. Resolve intended rule versus implementation explicitly. |
| [REFERENCE.md:1160](D:/Programming/Github_repos/Wormhole-Control/docs/REFERENCE.md:1160) and launch descriptions | General placement/safety descriptions are stronger than carrier candidate validation. | Fix F6, then document consistent actual placement guarantees. |
| [AGENTIC_AI.md:113](D:/Programming/Github_repos/Wormhole-Control/docs/AGENTIC_AI.md:113) | Memory-limit wording can read as a total memory limit. | State that the 8,000-character cap is for recent receipts; other bounded sections add to it. |

The current implementation's version set is: **save 4.17; observation 21; command contract 17; response schema v14; prompt cache v21; socket protocol 3; Strikecraft Bay schema 5; Strikecraft Wing schema 2.** These are different contracts and should not be collapsed into one version number.

### Give each topic one owner

| Document | Keep | Remove, shorten, or replace with links |
|---|---|---|
| `README.md` | Introduction, install/run, first-game path, links. | Keep it short; do not move detailed reference material into it. |
| `REFERENCE.md` | Current player-facing rules, controls, equipment, generated catalog/terrain tables, storage troubleshooting. | Removed features, historical version notes, repeated protocol internals. |
| `DEVELOPMENT.md` | Setup/checks, short architecture map, development invariants, fixtures, documentation maintenance. | Repeated test command lists elsewhere can link here. A permanent file-by-file inventory would become stale; this report is a dated review. |
| `AGENTIC_AI.md` | Observation/disclosure contract, shared command semantics, provider turn flow, memory, repair/failure behavior, evaluation. | Detailed gameplay rules already owned by `REFERENCE.md`; repeated feature histories and current-version announcements. |
| `CODEX_CONTROL.md` | Local bridge setup, CLI/envelopes, turn tokens, request IDs, waits, retry/recovery workflow, a few practical command examples. | Repeated shared command/rule descriptions; link to their owner in `AGENTIC_AI.md` or `REFERENCE.md`. |
| `SAVE_FORMAT.md` | Sole current format, strict rejection, schema/state ownership, prepare/commit, references/timers, persistence-specific invariants. | Historical 4.x change narration and repeated full gameplay rules. |

Suggested sequence:

1. Correct the factual mismatches above before moving content.
2. Put current versions in one small generated or centrally checked table and link to it. Keep historical information in Git history unless it explains a current invariant.
3. Consolidate common command lifecycle rules: queue/replacement, preflight purity, execution recheck, partial commit, cancellation, and observable outcomes. Link feature sections to that contract.
4. Keep feature documentation focused on its actual deltas: targets, timing, costs, visibility, and interruption conditions.
5. Retain the existing six generated reference blocks. Extend generation only for stable registry facts such as versions or public reason codes; human explanations should remain authored prose.
6. Run link checks, generated-reference checks, and the relevant contract tests after each documentation change.

## Testing infrastructure and results

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
| Additional repository-wide `ruff --select F,E9` | 272 diagnostics, classified above; this broader check is not the configured gate. |
| Local Markdown path/heading check | No unresolved local links detected. External URLs were not fetched. |
| `git diff --check` | Passed for the changes. |

The remaining warning is `noto_sans_bold_aa_14` not preloaded in `test_dismantling.py::test_preview_dialog_routes_to_shared_gateway`. It is non-fatal and should be fixed locally rather than globally suppressed.

CI additionally executes Ubuntu Python 3.10/3.14 and Windows Python 3.14. Passing mypy with two `--platform` values is static analysis, not evidence that those runtime matrix jobs passed during this review.

### Keep these parts of the infrastructure

- `tests/conftest.py` isolates user storage, restores counters/registries/random state, and owns game/GUI/service teardown.
- Headless SDL setup precedes application imports, allowing offline behavior checks without visible windows.
- The session Pygame fixture plus explicit event draining, default-manager release, and garbage collection addresses real resource ownership issues.
- Subprocess/import-boundary tests protect fresh-process behavior that in-process mocks cannot reliably establish.
- Save/load identity, zero-ID, reference, cancellation/refund, privacy, idempotency, rendering allocation, and failure-cleanup regressions cover durable risks. Their age alone is not a reason to remove them.
- Generated-reference verification and the current OS/Python CI matrix provide useful complementary checks.

### Bloat and blind spots to address

1. **Misleading doubles:** The hangar boundary test passes an impossible live location and an old scale assumption. Use a small real campaign for membership/geometry rules; reserve mocks for external collaborators.
2. **Repeated setup:** Share duplicated collision setup and simple campaign/entity builders. Avoid fixtures that construct a full UI or large galaxy for a calculation needing two units.
3. **Unused test setup:** Sixty unused local diagnostics merit review. A created entity may intentionally affect the world even if its variable is unused; do not delete the call automatically.
4. **Weak lint scope:** The green default Ruff run says little about unused code. Expand cleaned module coverage gradually.
5. **Narrow typing scope:** Strict mypy covers seven selected boundary files with silent import following, not the entire game. Add types first to preparation results, projection records, and persistence validators where they clarify contracts.
6. **Missing cross-boundary tests:** Most reproduced bugs occur where two individually tested layers disagree. Add the focused scenarios below instead of more implementation-call-count assertions.
7. **UI test cost:** Several large-display tests take approximately 2–4 seconds each. Keep representative resolution/scale transitions and privacy cases; consolidate redundant screenshots/setup only after checking they do not protect different regressions. A roughly 3.5-minute complete local run does not justify deleting meaningful tests just to reduce count.

### Recommended regression additions

| Boundary | Meaningful assertion |
|---|---|
| Movement → fuel payment | Destroyed storage prevents paid motion; successful motion pays exactly once; failed relocation does not debit. |
| Save preparation → identity and filesystem | Invalid player values reject without commit; sidecars cannot escape their roots on Windows or POSIX path inputs. |
| Carrier launch → sector membership | Candidate is in bounds and safe; failed placement retains docked membership and position. |
| Observation → command specification | Legal commands are a subset of supported commands; supported player commands match the registry. |
| AI reset → active worker | New work has defined bounded behavior while an old request runs; shutdown releases owned resources. |
| Order failure → public history | Intended actionable reasons such as `hazard_blocked` survive journaling without exposing private details. |

## Suggested implementation order and improvement ideas

### First: correctness with small diffs

1. Fix strict player/ID validation and sidecar containment together (F4/F5).
2. Fix carrier placement and movement payment (F6/F7).
3. Fix command discovery (F8), then resolve the AI request lifecycle policy (F9).
4. Correct inaccurate docs and public reason-code drift alongside the affected behavior.

### Next: reduce maintenance cost

- Extract command projection, movement resolution, constructor assembly, and wizard pages in separate reviewable changes. Preserve public behavior while moving code.
- Apply the small duplication/import cleanup, then widen lint for cleaned modules.
- Add intent-focused docstrings to the important functions listed above; remove neighboring narration that becomes redundant.
- Consolidate documentation according to topic ownership and keep version facts generated/checked.

### Useful improvements to consider after correctness

- **A concise diagnostics summary:** Surface actionable order failure reasons and AI request state, including whether replacement work is queued behind an old request. Existing logs/receipts already provide the basis.
- **Better Designer feedback:** Extend field-level error feedback to the remaining parameter readers that silently default or retain old values. Show why a configuration cannot fit its hull.
- **Deterministic scenario probes:** Keep small, seeded save/command fixtures for representative construction, logistics, capture, docking, and overlapping effects. Favor a handful of cross-boundary invariants over a large new fuzzing framework initially.
- **Measure observation and guidance cost:** Before caching, profile a large campaign's observation building, command guidance, and repeated graph lookups. Cache only stable catalog data or proven hotspots with explicit invalidation rules.
- **Unified income explanation:** A shared income breakdown can improve both correctness and the player-facing economy display without a new subsystem.
- **Clear clocks:** Document owner turns, global rounds, cooldowns, and ready-round deadlines consistently in code and UI help. Many interruption and persistence errors become easier to review once the clock is explicit.

The desired outcome is fewer independent implementations of the same rule, clearer ownership of mutable state, and tests that exercise real boundary behavior. The existing modular domain services and preparation/commit model can support that work without a broad rewrite.

## Local evidence

The most useful local diagnostic artifacts are:

- [Latest full-suite JUnit results](D:/Programming/Github_repos/Wormhole-Control/.codex_test_cache/p1/full-junit.xml).
- [Original audit full-suite output](D:/Programming/Github_repos/Wormhole-Control/.codex_test_cache/audit/final-pytest.log) and [JUnit results](D:/Programming/Github_repos/Wormhole-Control/.codex_test_cache/audit/final-junit.xml).
- [Persistence, path, and observation probes](D:/Programming/Github_repos/Wormhole-Control/.codex_test_cache/audit/reproductions.json).
- [Placement and movement results](D:/Programming/Github_repos/Wormhole-Control/.codex_test_cache/audit/gameplay-probes.json), with [probe source](D:/Programming/Github_repos/Wormhole-Control/.codex_test_cache/audit/gameplay_probes.py).
- [Coordinator reset results](D:/Programming/Github_repos/Wormhole-Control/.codex_test_cache/audit/coordinator-probe.json), with [probe source](D:/Programming/Github_repos/Wormhole-Control/.codex_test_cache/audit/coordinator_probe.py).
- [AST inventory](D:/Programming/Github_repos/Wormhole-Control/.codex_test_cache/audit/inventory.json), [expanded lint output](D:/Programming/Github_repos/Wormhole-Control/.codex_test_cache/audit/expanded-lint.json), and [review statistics/link check](D:/Programming/Github_repos/Wormhole-Control/.codex_test_cache/audit/stats.json).

These files are ignored working artifacts, not proposed permanent test infrastructure. The report includes the important reproduction conditions so its conclusions remain understandable without them.
