# Wormhole Control project analysis

- **Audit date:** 2026-09-05
- **Revision reviewed:** `b2c324f` (`main`)
- **Primary documents:** `README.md`, `docs/REFERENCE.md`, and `docs/AGENTIC_AI.md`
- **Scope:** production code, data/configuration, tests, persistence, the command/control boundary, GUI/rendering structure, documentation accuracy, comments/docstrings, naming, and repository hygiene.

## Executive assessment

Wormhole Control is an ambitious and unusually broad prototype. It has a real domain model, a compositional unit system, hierarchical orders, three levels of spatial simulation, fog of war, persistence, a large GUI, and two constrained machine-control paths. The agentic-AI boundary is the strongest architectural area: observations are visibility-filtered, commands are schema-constrained, game mutation returns to the main thread, stale model responses are rejected, and preflight is separated from commit. The 1,116-test suite is also substantial for a project of this size.

The reviewed revision is nevertheless **not launchable in a normal environment**. A missing `typing` import in `rendering/galaxy_renderer.py` raises `NameError` while importing `game`, and normal pytest collection stops with 30 errors. After applying an in-memory import workaround, 1,115 tests passed in the sandbox; the remaining loopback-socket test passed when rerun outside the sandbox. This suggests a healthy underlying test baseline, but it also shows that the suite lacks a minimal clean-process import/launch gate.

Beyond that blocker, the largest product risk is persistence. Saves preserve much of the visible game state but omit generic component health, weapon cooldowns/configuration, ability instances and timers, and several dynamically installed component parameters. Restoring an active inhibitor does not recreate its actual inhibition zone. Loading is non-transactional, ignores the declared save version, and can leave the current game partially replaced after a corrupt payload. In a long-running strategy game, these are release-level integrity problems.

Several gameplay defects are also confirmed: radiation storms currently do no component damage; a fully mitigated zero-damage hit becomes one damage while Adaptive Forcefield is active; entering or leaving a gas giant records a cancelled order even though the order completes; homeworld selection can choose a non-colonizable gas giant and can start colonies above their population cap; and legacy object ID `0`, explicitly documented as valid, is rejected by many truthiness checks. Minefields are processed for every unit at the end of every player's turn, making stationary mine damage scale with player count unless that behavior is intentional.

Overall recommendation: treat the project as a strong prototype with a credible architecture, but block a tagged release until the import failure, save/load fidelity, radiation hazard, homeworld setup, order-journal, and timed-effect lifecycle issues are fixed and covered by regression tests.

## Audit method and evidence

The audit used the following methods:

- Read all three requested documents in full. `docs/CODEX_CONTROL.md` was also checked where it overlaps the agentic/control implementation.
- Inspected all 162 production Python modules, with focused tracing through bootstrap, settings/setup, entities/galaxy, geometry/pathfinding, turn processing, orders, components, abilities, save/load, visibility, AI commands/observations, control protocol, input handling, GUI, and rendering.
- Enumerated module and function sizes and performed an AST-based scan for module documentation, public-callable docstrings, large/branch-heavy functions, broad exception handlers, mutable defaults, duplicate definitions, and likely unresolved names.
- Ran a clean import, normal pytest collection, a full suite with a non-mutating `typing` workaround, an isolated socket rerun outside the sandbox, and forced bytecode compilation.
- Ran targeted behavior probes for component save round-tripping, ability state, Adaptive Forcefield damage, radiation storms, gas-giant order journaling, and collision-clearance routing.
- Compared documented values and feature claims against constants, enums, registries, and executable mechanics.

This was not a live balance playtest or a performance profile of a long campaign. No live OpenAI API request was made. GUI behavior was assessed from code and test output rather than a complete interactive session because the normal application import is currently blocked.

## Verification baseline

| Check | Result | Interpretation |
|---|---:|---|
| `python -c "import game"` | Failed | `NameError: name 'typing' is not defined` at `rendering/galaxy_renderer.py:226` |
| Normal `pytest -q` | Collection aborted | 30 collection errors caused by the same import failure; no meaningful normal-suite result |
| Full suite with `typing` injected into `builtins` | 1,115 passed, 1 failed, 168 warnings, 10 subtests passed | The only failure was a loopback connection timeout in the restricted sandbox |
| Isolated loopback test outside the sandbox | Passed | Confirms the remaining failure was environmental rather than a project defect |
| Forced `compileall` | Passed | Useful syntax check, but it cannot catch a runtime annotation-name failure |

The likely post-import-fix baseline is therefore **1,116 passing tests**, but that result should be confirmed by running the suite normally after the source fix. The 168 warnings are mostly `pygame_gui` undersized-label warnings in the unit designer/new-game wizard, plus missing preloaded font variants. They are not test failures, but they are useful evidence of layout debt.

## Prioritized finding register

| ID | Severity | Confidence | Finding |
|---|---|---|---|
| WC-001 | Blocker | Confirmed | The game and test suite cannot import because `rendering/galaxy_renderer.py` uses `typing.*` without importing `typing`. |
| WC-002 | High | Confirmed | Save/load is lossy for component damage, abilities, weapon cooldown/configuration, and several dynamic component parameters. |
| WC-003 | High | Confirmed | Loading is non-transactional, does not dispatch on save version, and can leave a partially mutated game after failure. |
| WC-004 | High | Confirmed | Radiation storms never select a component and therefore deal no component damage; their documented accuracy penalty is also absent. |
| WC-005 | High | Confirmed | New-game homeworld assignment can colonize gas giants, exceed population caps, and reuse a starting system despite the Normal-profile guarantee. |
| WC-006 | High | Confirmed | Gas-giant entry/exit clears the order that is currently executing, journaling it as cancelled before it reports completion. |
| WC-007 | High | Confirmed | Timed ability effects can become permanent after save/load or destruction of the source component/unit. |
| WC-008 | High | Confirmed | Adaptive Forcefield changes a zero-damage hit into one point of hull damage. |
| WC-009 | High | Confirmed | Many order and rendering paths reject legacy object ID `0`, despite the documented and schema-level contract allowing it. |
| WC-010 | Medium/High | Strong inference | Minefield contact checks run globally once per player turn, so damage and mine consumption scale with player count. |
| WC-011 | Medium | Confirmed | Several documented environmental mechanics are constants/UI text only and never affect gameplay. |
| WC-012 | Medium | Confirmed | Collision avoidance tests the physical obstacle rather than the requested expanded safety margin. |
| WC-013 | Medium | Confirmed | Settings validation and galaxy generation permit invalid or impossible configurations and can silently produce fewer systems than requested. |
| WC-014 | Medium | Confirmed | The global object counter is rebuilt without considering minefield IDs, allowing ID reuse after loading some saves. |
| WC-015 | Low/Medium | Confirmed | Several public APIs fail less gracefully than their shape implies, and internal command exceptions lose diagnostic stack traces. |
| WC-016 | Maintainability | Confirmed | A small number of very large dispatch/state-machine functions and accidental re-export boundaries concentrate change risk. |
| WC-017 | Documentation | Confirmed | README and reference values, counts, feature descriptions, and project tree have material drift from the implementation. |
| WC-018 | Repository hygiene | Confirmed | Mutable user templates and a generated, resolution-specific theme are committed as source artifacts. |

## Detailed findings

### WC-001 — import and launch blocker

`rendering/galaxy_renderer.py:3` imports only `TYPE_CHECKING` from `typing`, while module-level function annotations use `typing.Any`, `typing.Optional`, `typing.Dict`, `typing.List`, and `typing.Tuple` at `:226-230` and `:341-346`. The file has neither `import typing` nor postponed annotations. Importing `game` traverses `game -> gui -> layout_new_game_wizard -> rendering.galaxy_renderer` and evaluates those annotations immediately.

Impact:

- `python game.py` cannot reach the game loop.
- Any test importing the GUI/game/rendering chain fails during collection.
- A renderer-only change has a repository-wide blast radius because imports eagerly connect the core, GUI, and rendering layers.

Recommended repair: add the intended import or convert the annotations to directly imported names, then add a clean-process smoke test such as `python -c "import game; import renderer"` to CI. Postponed annotations are also reasonable, but consistency across the project matters more than the particular style.

### WC-002 — save/load does not preserve the game that was saved

`save_manager.serialize_components` (`save_manager.py:278-366`) is a large external type switch. It serializes selected fields for selected component classes, but it does not serialize the base `UnitComponent.current_hit_points` or `max_hit_points` for any component. A damaged engine, sensor, defense, commander, or other subsystem returns at full component health after load.

The same switch has no state branch for `Weapons` or `AbilityComponent`:

- Turret `current_cooldown` is lost. A just-fired weapon can become immediately ready after load.
- A dynamically refitted `Weapons` component is serialized as an empty object, so its turret layout cannot be reconstructed from the save.
- Ability type membership, `is_active`, `cooldown_remaining`, `duration_remaining`, `target_unit_id`, `target_position`, and spawned-unit IDs are lost.
- A dynamically refitted `AbilityComponent` is recreated from an empty `ability_types` list by `instantiate_component_for_unit` (`unit_components/constructor.py:996-1004`).
- Hull-level status flags such as `damage_reduction`, `damage_amplification`, `is_disabled`, and `disabled_by_unit_ids` *are* restored (`save_manager.py:887-895`). Their originating ability instance and expiry timer are not, so a temporary debuff/buff can become permanent.

Other component classes are either omitted or only partially represented. Examples include Marines, Minelayer, Antimatter Harvester, Civilian Habitat, and refinery configuration. Base-template components often appear to survive because `deserialize_unit` rebuilds the named template first, but dynamically added/refitted components fall back to constructor defaults. This makes persistence behavior depend on a unit's construction history rather than only its current state.

A direct round-trip probe produced:

```text
before component HP: 1
after component HP: 10
serialized ability payload: {}
restored ability state: absent
restored unit damage_reduction: 0.75
```

The active-inhibitor path has a separate spatial inconsistency. `is_active` is saved and restored (`save_manager.py:301`, `:950-951`), but deserialization only rebuilds static celestial zones (`:1098-1099`). It never repopulates `Hex.dynamic_inhibition_zones`. The loaded ship advertises an active field and continues to consume antimatter, but the field does not block jumps until some later action recreates it.

Recommended design:

1. Put persistence ownership on each component: `to_state()` plus `restore_state()` or a versioned component-state codec.
2. Always persist the common envelope (`type`, `schema_version`, `hull_cost`, `current_hit_points`, `max_hit_points`) and let each subtype add its own state.
3. Persist ability definitions and runtime state independently; resolve target IDs only after the complete object graph exists.
4. Rebuild all derived indexes/zones/targets in an explicit post-load reconciliation pass.
5. Add a table-driven round-trip test for every registered component and every ability, including a dynamically refitted component.

### WC-003 — load is non-transactional and the version field is decorative

`deserialize_game_state` starts mutating the live `Game` at `save_manager.py:1134`: turn, view, selection, conversations, players, galaxy, counters, visibility, GUI, and AI scheduling are replaced in stages. Its catch-all at `:1223-1225` returns `False` without restoring the previous state. `Game.load_game` also resets the AI coordinator before attempting the load (`game.py:445-479`). A malformed save can therefore fail visibly while leaving a partly replaced campaign and a stopped AI turn.

The writer emits `"version": "3.2"` (`save_manager.py:465`), but the reader never reads that field. Compatibility currently relies on scattered defaults and comments. Two of those defaults are stale: `NebulaType[... "EMISSION"]` and `StormType[... "ION"]` at `save_manager.py:569` and `:572` reference names that do not exist in the current enums. A legacy or hand-edited body missing those keys fails instead of receiving a valid default.

Recommended repair:

- Parse and validate into an isolated state graph first.
- Run schema migration by declared version.
- Resolve references and recompute derived state.
- Validate invariants.
- Swap the completed graph into `Game` only after all prior steps succeed.
- Reset/schedule the AI and refresh the GUI only after commit.

For a strategy game, a load failure should be all-or-nothing.

### WC-004 — radiation storms are inert, and “accuracy” does not exist

The radiation branch in `turn_processor.py:573-579` does this:

```python
comps = [c for c in getattr(unit, 'components', []) if not c.is_destroyed]
```

`Unit.components` is a dictionary (`entities.py:940`). Iterating it yields component **classes**, not instances. `c.is_destroyed` therefore refers to the class-level property object, which is truthy, and the comprehension selects nothing. A direct probe put a ship with three healthy components inside a radiation storm; every component retained its original HP.

Even after changing iteration to `.values()`, the current `comps[0]` behavior would always damage insertion-order-first rather than the “random functional component” promised by `docs/REFERENCE.md:749`.

`STORM_RADIATION_ACCURACY_PENALTY` is defined at `constants.py:472` but is never consumed. Turret fire in `unit_components/weapons.py:47-95` is deterministic and has no hit/accuracy model. This is not just a missing modifier; the documented mechanic has no underlying system to modify.

Recommended repair: iterate `unit.components.values()`, select with an injectable campaign RNG, and decide whether to add a real hit-chance model or remove “accuracy penalty” from constants/docs. Add a radiation-specific turn-processor regression test; the current celestial hazard test covers only plasma and magnetic storms.

### WC-005 — new-game setup can create invalid starting states

`game_setup.start_new_game` selects any unowned `Planet` (`game_setup.py:135-138`, repeated at `:175-178`). It does not filter `planet.is_colonizable` or exclude `PlanetType.GAS_GIANT`, even though gas giants are explicitly non-colonizable (`constants.py:455-464`, README line 116). It then assigns ownership and population unconditionally.

The default starting population is 50. Some valid planet types have lower caps: Barren has 40 and Greenhouse has 35 (`constants.py:411-419`, `:444-453`). `Planet.update_population` only clamps while `population < max_population` (`entities.py:617-623`), so an over-cap homeworld remains over cap indefinitely.

Normal spawn also says each player receives a distinct system (`game_setup.py:115-117`), while the UI allows six players and only five systems. `_select_starting_systems` returns all available systems when there are too few (`:19-23`), and assignment then wraps with modulo (`:132`). This silently violates the profile guarantee. The README even describes concentric home markers for deliberately shared systems, so the product needs an explicit rule rather than an accidental fallback.

Finally, setup mutates `game.settings`, resets AI, assigns a new campaign ID, and switches the GUI before galaxy construction is known to succeed (`:61-82`). A generation failure therefore leaves a partial UI/session transition.

Recommended repair:

- Select only unowned, colonizable planets.
- Clamp or validate starting population per chosen world, or create a guaranteed Terran homeworld.
- Make `num_systems >= num_players` a Normal-profile invariant, or explicitly expose/describe shared starts.
- Stage the new campaign off to the side and commit only after galaxy, players, homeworlds, and starter units validate.

### WC-006 — gas-giant orders report mutually inconsistent outcomes

`Planet.hide_unit` calls `unit.commander_component.clear_explicit_orders()` at `entities.py:547-548`. That method cancels the current explicit root and records its outcome. `EnterGasGiantOrder.execute` is itself the current explicit root; after `hide_unit` returns, it assigns `OrderStatus.COMPLETED` (`unit_orders/gas_giant.py:88`). The same sequence exists in `Planet.release_unit` (`entities.py:611-612`) and `LeaveGasGiantOrder` (`unit_orders/gas_giant.py:140`).

A Commander-level probe of both operations ended with the in-memory order status `COMPLETED`, but the public order history contained `outcome="cancelled"` and `reason="cancelled"`. This violates the exact-once terminal-outcome contract stated in `docs/AGENTIC_AI.md:261-262` and can mislead both AI recovery and human diagnostics.

The release position also has weaker guarantees than the docs claim. It tries 64 random vectors and rejects celestial collisions/sector overflow, but the fallback at `entities.py:597-599` bypasses those checks. It does not check other ships, so “multiple departing ships emerge on distinct vectors” is probabilistic rather than guaranteed.

Recommended repair: the order lifecycle, not the domain entity, should decide which explicit work is cancelled. Add a narrow method for clearing unrelated movement/targets, or exclude the executing root from cancellation. Choose and reserve an exit position through one validated helper, with deterministic fallback and unit deconfliction.

### WC-007 — active ability effects lack destruction and persistence cleanup

`AbilityComponent.update` simply returns if the component is destroyed (`unit_components/abilities/component.py:203-209`). `AbilityComponent` does not override `UnitComponent.on_destroyed`, and `Unit.destroy` does not call each component's destruction hook (`entities.py:1311-1336`). Consequently:

- Adaptive Forcefield can leave `unit.damage_reduction` behind.
- Designate Target can leave `target.damage_amplification` behind.
- Ion Bolt can leave a target ID in `disabled_by_unit_ids`, keeping the target disabled.
- Any spawned/ongoing ability resources whose cleanup is tied to expiry can survive their source.

Save/load makes the same condition possible without destruction because it persists the target/unit flags but not the active ability and its timer.

Recommended design: introduce an idempotent effect-removal path used by normal expiry, component destruction, unit destruction, capture/ownership changes where relevant, and load reconciliation. Represent stacked effects by source IDs/tokens rather than only aggregate floats, so cleanup can remove exactly one source. Test every timed ability against expiry, source-component destruction, source-unit destruction, save/load mid-effect, and target destruction.

### WC-008 — Adaptive Forcefield can increase damage

`Unit.take_damage` first permits environmental cover and defenses to reduce damage to zero, then applies:

```python
amount = max(1, int(amount * (1.0 - self.damage_reduction)))
```

at `entities.py:1242-1243`. With any positive `damage_reduction`, even an input of zero becomes one. A direct probe changed a 100-HP unit to 99 after `take_damage(0)` while the forcefield was active.

Recommended repair: return early for non-positive post-mitigation damage, or clamp to `max(0, ...)`. If every successful attack is intentionally meant to inflict a minimum of one, apply that rule once, before or after all mitigation consistently, and document it. The current behavior depends on whether a forcefield happens to be active.

### WC-009 — valid legacy ID zero is handled as “missing”

`docs/REFERENCE.md:293-297` explicitly states that legacy saves may preserve object ID `0` and that `None`, not zero, means missing. The AI command schema also accepts non-negative IDs. Numerous runtime paths still use truthiness:

- `unit_orders/mining.py:25,159`
- `unit_orders/colony.py:31,105`
- `unit_orders/gas_giant.py:31,54`
- `unit_orders/trade.py:28`
- `unit_orders/combat.py:94,167,305,326,342,415,441`
- `unit_orders/antimatter.py:35,121,151`
- `unit_orders/hangar.py:26,101`
- `unit_orders/repair.py:25`
- `unit_orders/refit.py:63`
- `unit_orders/patrol.py:172`
- `unit_orders/defend.py:187`
- system/sector order-line rendering and sidebar formatting.

The result is a preflight/runtime/display mismatch: a command can satisfy the public contract but be rejected, ignored, or rendered without its target later.

Recommended repair: use `is None`/`is not None` consistently for identifiers. Add one migrated-save fixture containing ID zero and run it through every target-bearing command serializer, validator, executor, and formatter. Consider reserving zero and migrating it once if ongoing compatibility is not worth the pervasive special case—but then change the published contract and migration logic together.

### WC-010 — minefields tick globally per player turn

`TurnProcessor.process_player_turn` calls `_process_minefield_detonations()` after movement (`turn_processor.py:89-100`). That helper accepts no current player and scans every unit in every system (`:697-734`). In a three-player game, a stationary unit inside an enemy field can therefore trigger a mine three times per round, even when the other two players' turns did not move it. Mine depletion and damage rate scale with player count.

The comment says “Minefield detonations from movement,” which suggests the intended scope is the just-moved active-player units. Existing tests invoke the private global helper once and do not test round cadence.

This is marked Medium/High rather than unconditionally High because the desired game rule is not explicitly documented. The current behavior should either be changed to active-player/moved-unit contact resolution, or documented and tested as an every-player-turn area hazard.

### WC-011 — several environmental mechanics are promises, not mechanics

Repository-wide use tracing found these values defined but not consumed by gameplay:

- `ICE_FIELD_COOLDOWN_REDUCTION` (`constants.py:484`) is copied to `IceField.cooldown_reduction` (`entities.py:731`) but weapons never read it.
- `NITROGEN_NEBULA_COOLDOWN_REDUCTION` (`constants.py:531`) is never used.
- `OXYGEN_NEBULA_SHIELD_REGEN_BONUS` (`:532`) is never used; the current `Defenses.shields` value is mitigation strength, not a regenerating shield pool.
- `OXYGEN_NEBULA_SPLASH_DAMAGE_MOD` (`:533`) is never used by Cluster Warhead or combat.
- `STORM_RADIATION_ACCURACY_PENALTY` (`:472`) is never used, and there is no accuracy roll to modify.

The README and Reference describe those behaviors as implemented. This creates both balance surprises and AI misinformation because strategic rules are sourced from prose as well as observations.

There is also a numeric mismatch. README lines 132-133 and Reference lines 730/734 promise Low/Medium/High cover of +8%/+12%/+16%, while `constants.py:503-506` and `:515-518` implement +5%/+10%/+15%.

Recommended repair: choose the intended rule for each mechanic, implement it with tests, and generate UI/help/reference values from the same declarative registry. Do not retain constants merely as placeholders while prose presents them as live features.

### WC-012 — collision clearance margin is not enforced

`compute_avoidance_waypoints` creates expanded circles using `radius + margin` (`geometry.py:214`) and its helper docstring says it returns the first expanded obstacle hit. The actual intersection and quadratic entry calculations use `orig`, the unexpanded obstacle, at `:227-238`.

A segment crossing 149 units above a radius-100 obstacle with a 50-unit requested margin returned no waypoints. It misses the physical body by 49 units, but violates the stated 50-unit clearance.

Recommended repair: use the expanded circle for intersection and entry calculations while retaining the original circle only for the deliberate “endpoint inside body” landing/departure exception. Add tangent, near-tangent, endpoint-inside, multiple-obstacle, and sector-boundary property tests.

### WC-013 — validation and generation do not share one enforceable contract

`GameSettings.validate` (`game_settings.py:139-166`) checks only radius ordering, distance ordering, two-team minimum, and named pregenerated systems. It does not enforce the README's 2–6 players and 5–30 systems, positive radii/distances, density in `[0,1]`, non-negative resources/population, valid team IDs/colors/controllers, unique/usable names, or Normal-profile topology requirements. `__post_init__` invokes this partial validation once, but settings remain mutable afterward. The control protocol and GUI implement additional, duplicated validation rules.

`normalize_spawn_profile` silently maps an unknown string to Normal (`game_settings.py:35-45`), hiding malformed input rather than rejecting it.

Galaxy placement gives each requested system only 100 random attempts (`galaxy.py:468-529`). Failure is logged at debug level and generation continues with fewer systems. With impossible but currently accepted bounds, a “15 system” setup can contain only one system. A zero-system value reaches `system_names[0]` and fails. That shortfall then feeds directly into homeworld reuse.

Recommended repair:

- Make one side-effect-free validator authoritative for GUI, control, and direct construction.
- Return structured validation errors, not silent normalization.
- Either construct topology with an algorithm that guarantees the requested count for valid settings or fail the whole generation with an actionable error.
- Inject a `random.Random(seed)` so a map can be reproduced from a save, bug report, or tournament configuration.

### WC-014 — minefield IDs can collide after load

Minefields inherit `GameObject` (`entities.py:846`) and their IDs are serialized/restored (`save_manager.py:1035-1055`). The post-load maximum-ID scan covers celestial bodies and deployed/hidden/docked unit trees (`save_manager.py:1181-1197`) but not `hex_obj.minefields`. It also ignores the serialized `game_state.object_counter` even though the writer records it (`:455`, `:473`). A minefield whose ID is greater than every body/unit ID can therefore be followed by a newly created object with the same ID.

Recommended repair: include every `GameObject` collection in a single graph iterator, then set the allocator to `max(serialized_counter, observed_max + 1)`. Longer term, inject ID allocators into a campaign instead of using process-global counters; this improves save isolation and tests as well as correctness.

### WC-015 — small API and diagnostic reliability problems

- `StarSystem.get_units_in_hex` and `get_celestial_bodies_in_hex` use `self.hexes.get(coord, []).units` / `.celestial_bodies` (`galaxy.py:289-295`). An invalid coordinate therefore raises `AttributeError` on a list rather than returning an empty list.
- `Galaxy.move_unit_between_systems` indexes both system names before checking them (`galaxy.py:674-681`), so the advertised `False` path for an unknown system is unreachable; `KeyError` is raised first.
- `ControlService.__init__` accepts a `host` argument but always assigns `DEFAULT_HOST` (`game_control_protocol.py:133-137`). Hardcoding loopback is a sound safety choice; the API should remove the misleading argument or validate that only loopback values are accepted.
- `game_ai.commands` converts unexpected prepare/commit exceptions into safe public errors at `game_ai/commands.py:578-594`, which is good for information control, but it does not log the exception internally. Unexpected engine defects become nearly impossible to diagnose. Use `logger.exception` with non-sensitive context while preserving the generic client response.
- Broad `except Exception` appears 33 times. Many are appropriate at I/O, GUI, serialization, plugin/API, or thread boundaries; internal state transitions should narrow catches or re-raise after logging so programming errors do not masquerade as ordinary user failures.

## Architecture review by subsystem

| Area | Assessment | Highest-value change |
|---|---|---|
| Bootstrap/config (`game.py`, `constants.py`, `utils.py`) | `Game` is a practical façade and application entry point, but importing it eagerly pulls in GUI/rendering. `constants.py` performs Windows DPI and display probing at import time. `resource_path` falls back to the process working directory. | Move OS/display initialization into bootstrap; resolve development resources from `__file__`; establish a headless core import boundary. |
| Settings/setup (`game_settings.py`, `game_setup.py`) | Dataclasses make configuration understandable, but validation is partial/duplicated and setup mutates the live session early. | Central validated campaign factory returning either a complete state or structured errors. |
| Domain model (`entities.py`, `galaxy.py`) | The model is expressive, but `entities.py` is a 1,408-line aggregate containing players, bodies, units, diplomacy, damage, and environmental behavior. Global counters and cross-imports complicate isolation. | Split stable domain groups and introduce campaign-owned repositories/ID allocation without a big-bang rewrite. |
| Components (`unit_components/`) | Composition is a good fit for customizable units, and registries/factories already exist. Lifecycle and persistence are not part of the component protocol. | Add explicit `update`, `on_destroyed`, `to_state`, `restore_state`, and validation contracts to the base/registry. |
| Orders (`unit_orders/`, `order_system.py`, `order_history.py`) | Hierarchical orders, explicit roots, suborders, persistence hooks, and bounded public history are strong ideas. Lifecycle transitions are distributed and can contradict one another. | Centralize legal transitions and exactly-once terminal journaling in an order lifecycle/state machine. |
| Turn processing (`turn_processor.py`) | Stage ordering is visible and timed, but one 390-line movement method coordinates too many rules; global mine and environmental scans obscure cadence. | Make each phase accept/return an explicit turn context (active player, moved units, emitted events). |
| Geometry/pathfinding (`geometry.py`, `pathfinding.py`, `hexgrid_utils.py`) | Algorithms are separated from much of the UI and have focused tests. Naming/docs overstate A*, and clearance uses the wrong circle. | Correct margin logic, clarify algorithm names, and add seeded/property-based edge-case testing. |
| Visibility/intelligence (`visibility.py`, `component_visibility.py`) | Allied sensor sharing, hidden-component redaction, remembered intel, cloaking, nebulae, and gas hiding are thoughtfully modeled. No obvious enemy-state leak was found in the reviewed observation paths. | Keep visibility as the only authority and add snapshot/golden tests whenever a new field enters an observation or sidebar. |
| Combat/abilities | Modular ability classes are easy to extend, but temporary effects are represented as aggregate flags/floats and lack robust ownership cleanup. Several mechanics described as accuracy/cooling/regeneration have no engine abstraction. | Introduce sourced status effects and a combat-modifier pipeline before adding more abilities/hazards. |
| Persistence (`save_manager.py`) | JSON, atomic file replacement, nested unit traversal, order runtime hooks, and best-effort sidecars are solid starting points. The centralized type switch is already drifting from the component registry. | Versioned, object-owned codecs plus staged graph validation and post-load reconciliation. |
| Agentic AI (`game_ai/`) | Strongest subsystem: strict schema, visibility-safe observations, public error normalization, bounded memory/history, stale-response protection, and main-thread mutation. | Split `commands.py`, deduplicate validation with human actions/orders, and add internal exception diagnostics. |
| Codex control (`game_control.py`, `game_control_protocol.py`) | Loopback-only transport, idempotency cache, turn tokens, observation freshness, bounded request sizes, and queued main-thread dispatch are good defensive choices. | Clarify the host API and keep protocol validation generated from the same settings/command contracts. |
| GUI/input/rendering | The package split is much better than a monolithic Pygame loop, but large dispatchers and layout files still encode long `if/elif` catalogs. The renderer import can currently break the entire program. | Registry-based action/event dispatch, smaller view controllers, lazy UI imports, and warning-free layout tests. |
| Tests | Broad coverage across gameplay, AI, control, saves, visibility, UI layout, and edge mechanics. The suite uses useful fakes and avoids live API calls. | Add a clean import gate and invariant/round-trip tests; coverage count alone currently misses cross-feature composition defects. |

## Complexity and maintainability

### Repository scale

- Production Python: **162 modules, 45,078 lines**.
- Tests: **109 files, 32,596 lines**.
- AST inventory: **230 classes and 1,719 functions/methods**.
- Largest production files include `gui/layout_new_game_wizard.py` (1,749 lines), `game_ai/commands.py` (1,576), `entities.py` (1,408), `save_manager.py` (1,375), `custom_unit_templates.py` (1,207), `unit_orders/movement.py` (1,157), and `unit_components/constructor.py` (1,032).

Large files are not automatically bad—the wizard contains much declarative layout—but the repeated concentration around dispatch, object construction, serialization, and movement is a change-risk signal.

### High-risk functions

The following are approximate AST sizes/branch counts, not formal cyclomatic-complexity scores:

| Function | Approx. lines | Approx. branches | Risk |
|---|---:|---:|---|
| `input_processor.context_menu_builder.build_context_menu_options` | 257 | 164 | One catalog encodes authorization, capability, target type, labels, and submenu structure. |
| `game_ai.rules.command_guidance` | 317 | 123 | Human-readable AI rules can drift from executable command validation. |
| `turn_processor.TurnProcessor._process_movement` | 390 | 115 | Movement, AM use, inhibition, jumps, hazards, transfers, and state cleanup are tightly sequenced. |
| `input_processor.context_actions.handle_context_menu_action` | 397 | 111 | A string action router mixes parsing, validation, selection, UI prompts, and order creation. |
| `gui.event_router.process_event` | 248 | 118 | Widget identity and application behavior are joined in one branch tree. |
| `rendering.system_renderer._draw_system_view_order_lines` | 356 | 101 | Rendering reconstructs the semantics of many order types. |
| `game_ai.commands._order_factory` | 377 | 75 | A second large interpretation layer maps public commands to domain orders. |
| `game_ai.commands._validate_unit_command` | 165 | 74 | Validation overlaps order constructors/ability rules and human action paths. |
| `unit_orders.abilities.UseAbilityOrder.execute` | 215 | 64 | Targeting, approach insertion, ownership, range, and activation are coupled. |
| `unit_components.constructor.instantiate_unit_from_template` | 337 | 62 | Every component/config option converges in one constructor. |

Recommended decomposition is vertical rather than cosmetic: each command/order/component type should own a small descriptor containing its parsing, preflight, construction, formatting, and public guidance hooks. That would eliminate several parallel switch statements instead of merely splitting them into arbitrary helper files.

### Comments and docstrings

The AST scan found:

- Module docstrings in **80 of 162 modules** (49.4%).
- Docstrings on **664 of 1,348 public callables** (49.3%). This is presence-only; many are one-line summaries rather than full contracts.
- Approximately **1,154 standalone comment lines**, about 2.6% of production LOC.
- No mutable literal default arguments and no bare `except`, both positive signs.

Documentation coverage is uneven. `game.py`, geometry helpers, and many GUI facades are comparatively well documented. Important gaps cluster in `entities.py`, `events.py`, `game_ai/commands.py`, `game_ai/evaluation.py`, `order_system.py`, `unit_orders/intelligence.py`, component lifecycle methods, render-grid methods, and save serializers/deserializers.

The goal should not be a comment-density target. Some existing comments merely restate control flow—numbered “draw this,” “set up that,” or “loop continues” annotations. The missing material is intent and invariants:

- Who owns an order transition and when is its outcome journaled?
- Which state is canonical versus derived after load?
- At what cadence does an environmental effect run?
- Is an ID allowed to be zero?
- What can a visibility-filtered caller infer from a failure?
- Which functions mutate collections while iterating snapshots?

For non-trivial public functions, use a compact standard: purpose; arguments; return value; raised/normalized failures; side effects; lifecycle/cadence; and security/visibility constraints where applicable. Add comments where a decision is surprising, not where the syntax is obvious.

### Naming and API consistency

The vocabulary is understandable locally but inconsistent across subsystem boundaries:

- External `order_id` is the UUID-like `Order.public_id`, while `Order.order_id` is a different process-local integer. Rename internally or expose explicit `public_order_id`/`local_sequence_id` aliases before a migration.
- `game.turn_manager` is a `TurnProcessor`; “manager” and “processor” should not name the same role.
- `in_hex`, `hex_coord`, `sector`, and `sector_coord` alternate for the same axial coordinate concept.
- Target fields vary among `target_id`, `target_unit_id`, `target_carrier_id`, and object-specific names. That is sometimes semantically useful, but generic code repeatedly guesses which key exists.
- Component types mix bare nouns (`Weapons`, `Sensors`, `Defenses`, `Constructor`) and `*Component` suffixes. A registry-level stable key is more important than renaming every class immediately.
- `PULSAR_SHIELD_DRAIN_PERCENT` actually controls antimatter drain (`turn_processor.py:607`), a misleading name likely left from an earlier design.
- `Position = Vector` provides semantic readability but no runtime distinction; type checking cannot prevent passing a displacement where a point is required.
- Modern built-in generics and older `typing.Dict/List/Optional` styles are mixed. Pick one style supported by the actual minimum Python version.

The `entities` and `game` modules also act as accidental barrel APIs: other modules/tests import types that those files happened to import from their actual owners. This creates circular-import workarounds and makes cleanup dangerous. New code should import from the defining module; existing re-exports should be made explicit with `__all__` and deprecated gradually.

## Documentation audit

### README.md

| Location | Current claim | Runtime reality / recommendation |
|---|---|---|
| Line 18 | Python 3.9+ | The audit ran on 3.12.14; the README mentions 3.14.3. Add CI for the claimed minimum rather than relying on a prose claim. The annotation style depends heavily on postponed annotations. |
| Lines 38, 43 | 5–30 systems; 2–6 players | `GameSettings.validate` does not enforce either bound, and the direct/protocol/GUI paths do not share one validator. |
| Line 97 | “vicitity” | Typo: “vicinity.” |
| Lines 132-133 | Cover is +8/+12/+16% | Code implements +5/+10/+15%. Decide one set and generate the text from constants. |
| Line 145 | Radiation storms degrade accuracy | Radiation damage is currently inert and accuracy has no runtime model. |
| Line 155 | Up to 9 abilities | `AbilityType` and the registry contain 10; Scan for Minefields is omitted from the list. |
| Line 184 | “version-3 observation” | Current observation schema is 5; line 206 correctly says schema 5/command contract 3. Use the precise names consistently. |
| Line 252 | `WORMHOLE_FULLSCREEN=1` forces fullscreen | The parser accepts only case-insensitive `"true"`; setting `1` evaluates false. Accept common booleans or document `true`. |

### docs/REFERENCE.md

| Location | Drift |
|---|---|
| Line 38 | Calls `pathfinding.py` A*. The implementation uses unweighted Dijkstra for systems and cube interpolation for jump waypoints. |
| Line 187 | Says 22 selectable component rows, while `COMPONENT_ROWS` and the following table contain 24. |
| Line 237 | Designate Target is described as increasing accuracy. Code applies +50% damage received (`damage_amplification`). |
| Lines 293-297 | Correctly documents legacy ID zero, but many executors/renderers violate it. |
| Line 454 | Says setup verifies planet ownership/habitability. It verifies ownership only and can choose gas giants. |
| Lines 693-704 | Adds a nonexistent Continental planet; Greenhouse is listed as 55 population/1.0% but code is 35/0.5%; Moon/Asteroid caps are later listed as 25/15 even though lines 318-319 and code use 50/20. The document contradicts itself. |
| Lines 730, 734 | Cover values differ from constants as described above. |
| Lines 731, 743 | Ice/Nitrogen cooldown reduction is not connected to weapons. |
| Lines 744-745 | Oxygen regeneration/splash mechanics are not implemented. |
| Line 749 | Radiation is neither random nor currently damaging; accuracy penalty is absent. |
| Project tree | Omits `game_control.py`, `game_control_protocol.py`, `order_history.py`, `player_controller.py`, the `game_ai/` package, `gui/communications_window.py`, `gui/retrofit_gui/`, `unit_components/trade.py`, and newer gas-giant/stance/trade order modules. |

The reference is valuable but has become a manually maintained second implementation of the rules. Counts and balance values should be generated from registries/constants, while prose explains design intent.

### docs/AGENTIC_AI.md

This is the most accurate of the three documents. Its core claims match the reviewed design:

- observation schema 5, command contract 3, and socket protocol 2;
- visibility-safe state and uniform unavailable-target errors;
- strict command schemas and complete-batch preflight before mutation;
- main-thread application of game changes;
- bounded canonical memory, receipts, and history;
- stale-result rejection and no live API dependency in regression tests.

The primary correction is the exact-once outcome guarantee at lines 261-262: gas-giant entry/exit currently records the wrong terminal outcome. Lines 23-24 should also distinguish **preflight acceptance** from successful commit. The command gateway deliberately reports that commit operations may partially apply, so memory/turn completion semantics should say which stage must succeed before they are persisted.

Runtime enumeration under the import workaround found 40 public AI commands, 34 `OrderType` values, 10 abilities, and 24 component rows. Those counts should be generated into docs or tested as explicit contract snapshots.

## Repository hygiene and cruft

### Mutable user data committed as product data

`data/custom_unit_templates.json` is tracked and currently contains nine ad hoc user/test designs: `Test Design`, `Sensor Ship`, `Cloaked Ship`, `amdrainer`, `Minelayer Ship`, `Ability testing ship`, `IntelShip`, `Small Civilian Station`, and `Medium Orbital Defense Station`. The application treats this as mutable user content.

Ship a deliberate example file if examples are useful, but store user-created designs in an OS-appropriate user-data directory and ignore that runtime file. Otherwise normal gameplay dirties the repository and one developer's experimental designs become product defaults.

### Generated theme committed and rewritten at runtime

`theme_scaled.json` is tracked, but `gui/theme_loader.py:26-77` regenerates and overwrites it based on the current display scale and resolved font paths whenever the manager is created. This is derived, machine-specific state. It can fail in a read-only installation and race between two instances.

Generate it into a temporary/cache path, or construct the scaled theme in memory if `pygame_gui` permits. Keep `theme.json` as the source and ignore the derived artifact.

### Working-directory resource coupling

`utils.resource_path` falls back to `os.path.abspath(".")` (`utils.py:23-31`). Launching the program from outside the repository can make themes/data/fonts disappear. Resolve development assets relative to the module/repository (`Path(__file__).resolve().parent`) and use the PyInstaller bundle path only when it exists. Catch `AttributeError` rather than broad `Exception` for `_MEIPASS` detection.

### Import-time platform side effects

`constants.py:5-15` changes Windows DPI awareness and `:31-55` may initialize/query/quit the Pygame display at import time. Importing constants should not manipulate process-global GUI state. These effects complicate headless tests and make import order significant. Move them into application bootstrap and pass a computed display configuration to UI code.

### Missing quality automation

No repository CI workflow or central `pyproject.toml`/lint/type-check configuration was found. `requirements-dev.txt` contains only pytest. The immediate missing-import blocker is precisely the kind of regression a two-second import job, Ruff/Pyflakes, or a small type-check target would catch.

A pragmatic first quality gate:

1. Install pinned runtime/dev dependencies.
2. Run clean imports in a fresh process.
3. Run Ruff or Pyflakes for undefined names and unused imports.
4. Run pytest with warnings summarized and a modest coverage floor on core logic.
5. Exercise the declared minimum Python and current supported Python.

Avoid turning on hundreds of style rules at once; start with correctness rules and ratchet.

## Test gaps exposed by this audit

The suite is broad, but the confirmed defects share a pattern: individual features are tested in isolation while state transitions across features are not.

Add these regression groups:

1. **Bootstrap smoke:** import `game`, `renderer`, every renderer module, and every test module in a clean process.
2. **Persistence matrix:** for each component, damage it and modify every mutable field, save/load, and compare canonical state. Repeat for base-template and dynamically refitted components.
3. **Timed effects:** save/load mid-effect; destroy source component; destroy source unit; destroy target; stack two sources; verify exact cleanup.
4. **Hazards:** explicit radiation component damage/random selection/accuracy policy; verify each environmental constant advertised to users changes a result.
5. **Campaign invariants:** generated system count, colonizable homeworlds, population at/below cap, unique Normal starts, valid homeworld IDs, and deterministic replay from a seed.
6. **Order history:** every explicit root must produce exactly one terminal event whose outcome matches final status, including gas hiding, replacement, capture, destruction, and synchronous completion.
7. **Legacy IDs:** ID zero through observation, schema parsing, command preflight, order execution, persistence, and rendering.
8. **Mine cadence:** stationary and moving units across two-, three-, and six-player rounds.
9. **Geometry properties:** returned path segments never enter an expanded obstacle except for explicit landing/departure endpoints.
10. **Load failure atomicity:** malformed data at each reconstruction phase leaves the original game byte-for-byte/canonically unchanged.

Property-based testing would be particularly useful for save round trips, ID allocation, galaxy settings, and geometric routing. These areas have compact invariants and large edge spaces.

## Recommended remediation roadmap

### Phase 0 — restore a trustworthy baseline

1. Fix the missing `typing` reference in `rendering/galaxy_renderer.py`.
2. Add a clean import/launch smoke test.
3. Run the full suite normally and make the socket test explicitly skip or adapt only when loopback is genuinely unavailable.
4. Add undefined-name linting in CI.

Exit criterion: the game imports and the full suite passes without an annotation workaround.

### Phase 1 — protect campaign integrity

1. Introduce versioned component persistence and cover every registered component/ability with round-trip tests.
2. Make load transactional and implement explicit version migrations.
3. Rebuild dynamic inhibition zones and all other derived indexes after load.
4. Include minefields and serialized counters in ID allocator reconciliation.
5. Fix timed-effect cleanup on expiry, component destruction, unit destruction, and load.

Exit criterion: a deliberately mutated mid-game state survives a save/load canonical comparison, and invalid saves leave the running campaign unchanged.

### Phase 2 — correct gameplay invariants

1. Fix radiation storm iteration and decide the accuracy model.
2. Fix zero-damage handling with damage reduction.
3. Repair gas-giant order lifecycle and safe exit placement.
4. Enforce colonizable/capped homeworlds and Normal-profile topology.
5. Decide and implement minefield cadence.
6. Replace ID truthiness checks.
7. Correct collision-margin testing.

Exit criterion: each finding has a focused regression test and the rule is documented from a single source of truth.

### Phase 3 — reduce parallel rule implementations

1. Create declarative descriptors for components, abilities, commands, and environmental effects.
2. Generate GUI choices, AI schemas/guidance, persistence keys, and reference tables from those descriptors where practical.
3. Split giant dispatch functions by descriptor/handler rather than by arbitrary file length.
4. Make order transitions and status effects explicit state machines.
5. Establish core/UI import boundaries and remove import-time display side effects.

Exit criterion: adding one component or command does not require editing five unrelated switch statements and two hand-maintained documents.

### Phase 4 — documentation and polish

1. Correct the README and Reference discrepancies listed above.
2. Regenerate the project tree and registry-derived tables.
3. Add contract-focused docstrings to public state-changing functions.
4. Resolve the recurring `pygame_gui` layout/font warnings.
5. Move generated/user data out of version control.

## New design opportunities

These are not required fixes, but they build naturally on the existing architecture.

### 1. Deterministic campaign seeds and replay bundles

Inject a campaign RNG and store its seed/state. A bug report could then include save version, settings, seed, and a bounded order/event stream. Developers could reproduce galaxy layout, radiation targets, wormhole failures, capture rolls, and gas giant exits exactly. The same mechanism enables fair tournament maps and deterministic AI evaluations.

### 2. A declarative mechanics catalog

The project already has registries, constants, component rows, command specs, and ability definitions. Unify them into machine-readable descriptors with stable IDs, display text, requirements, costs, persistence codec, AI exposure, and rule modifiers. Generate:

- unit designer/retrofit rows;
- command JSON schemas and guidance;
- sidebar descriptions;
- save compatibility metadata;
- Reference tables and consistency tests.

This directly addresses the current 22/24 count, 9/10 ability count, balance-value drift, and unimplemented environmental promises.

### 3. Sourced status effects instead of aggregate flags

Represent `damage_reduction`, `damage_amplification`, disabling, sensor penalties, cooldown modifiers, and speed modifiers as effects with `source_id`, `kind`, `magnitude`, `duration`, and stacking policy. Derive aggregate values. Cleanup then becomes deterministic, save state becomes explicit, multiple sources compose safely, and UI/AI can explain *why* a value changed.

### 4. Event-driven turn phases

Have movement emit contact/environment events into a turn context. Minefields consume movement/contact events; environmental systems consume presence events for the active player; cleanup consumes destruction events. This makes cadence visible and prevents global scans from accidentally scaling with player count. It also creates a natural replay/audit log.

### 5. A headless simulation package

Separate the campaign/domain engine from Pygame and GUI imports. The UI would submit actions and render snapshots, while the core could run thousands of deterministic turns in tests or AI evaluation. The current agent command boundary is already a partial prototype of this separation.

### 6. Contract snapshots and compatibility gates

Store golden snapshots for observation schema, command schema, public reason codes, registry stable keys, and save schema. A change then fails tests until its compatibility/migration decision is explicit. This is especially valuable because external AI/Codex clients depend on semantics, not only Python call signatures.

### 7. Canonical state fingerprints

Define a normalized, derived-state-free representation of a campaign and hash it. Use it for save/load round-trip tests, replay verification, stale-command detection, and desynchronization diagnostics. Exclude GUI caches and recomputable visibility indexes; include every rule-relevant component/order/effect field.

## Final conclusion

Wormhole Control has enough structure and tests to evolve into a robust game, and its visibility-safe agent boundary is notably thoughtful. The immediate problem is not a lack of architecture; it is that several cross-cutting contracts—imports, persistence, lifecycle ownership, settings validation, and documentation as rules—are not enforced end to end.

The best next move is a short correctness campaign rather than a broad rewrite. Restore the clean import, make saves transactional and exhaustive, fix the confirmed turn/effect/order defects, and add invariant tests at subsystem boundaries. Once those foundations are reliable, registry-driven rules and a headless deterministic core can reduce both maintenance cost and documentation drift substantially.
