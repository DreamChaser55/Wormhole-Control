# Agentic AI Architecture

Wormhole Control treats an LLM as an untrusted planning process, not as part of
the authoritative game engine. The model receives a JSON-safe observation,
returns one strict turn plan, and cannot access Python objects, hidden state,
files, or arbitrary tools. See the [current formats and protocols](DEVELOPMENT.md#current-formats-and-protocols)
for the independent save, observation, command and transport identifiers.

## Turn flow

1. `TurnProcessor.check_and_schedule_ai_turn` retains the normal 500 ms turn
   transition delay, including slot-zero AI players and loaded AI turns.
2. `AgentTurnCoordinator` builds the observation on the Pygame thread and sends
   only plain data to one background asyncio loop. One provider request may run,
   with at most one pending replacement while obsolete work is being cancelled.
3. `OpenAIResponsesProvider` makes one non-streaming Responses API request with
   strict JSON Schema output and `store=False`.
4. The coordinator polls completion from `Game.update`; all commands, memory,
   telemetry and UI effects remain on the Pygame thread.
5. `CommandGateway` preflights the entire batch. Hidden and nonexistent targets
   deliberately return the same `target_unavailable` error.
6. Accepted orders are committed on the Pygame thread. A retryable rejection
   gets another semantic request containing the immediately preceding plan and
   its exact errors while the active AI player's snapshotted budget remains.
   Commit and transport failures are not semantically retried.
7. Only after successful commit are the bounded memory patch and execution
   receipts persisted and the turn ended. Preflight acceptance alone is not
   commit success; unexpected commit exceptions enter manual recovery without
   applying the rejected memory patch.

No API call is made for a human player. Tests and evaluation use injected fake
providers by default, so they do not consume API credits.

## Information boundary

`game_ai.observation.build_observation` recomputes visibility for the active
player, recording covered-sector intel and shared ghost identification.
`VisibilityService.compute(record_intel=False)` calculates coverage without those
persistent writes; load reconciliation and selected tactical/deployable checks use
that mode. Other target checks retain the recording default, as described in the
[preflight guarantees](#commit-guarantees-and-lifecycle-feedback). The observation includes:

- the active player's economy;
- public system topology, navigation anchors, detailed nearby bodies (including planetary traits, colonizability, passive mineral yields, and antimatter harvesting sources/multipliers), and summaries of remote neutral bodies;
- owned and allied units;
- enemy units only when detailed visibility permits them (concealed from long-range radar presence when cloaked or inside nebulae or asteroid fields);
- celestial fields (asteroid, debris, ice) with density parameters (`density`, `max_hull_size`), solidity status (`is_solid: false`), and exact `effect_radius` values that restrict hulls exceeding the field's maximum allowable hull, rejecting forbidden commands with `hazard_blocked`;
- space storms (plasma, magnetic, radiation) and nebulae exposing `is_solid: false` and exact `effect_radius`, along with separately scoped black-hole and pulsar hazards (strikecraft wings are banned from entering or launching in magnetic storms, but ignore field drag and debris abrasion and can enter fields of all densities);
- visible minefields;
- undetailed enemy-presence hexes without count, identity, owner, or strength;
- per-owned-unit supported commands, currently legal commands, conditional
  command sequences, bounded option values, ability state, cargo, inhibitor
  state and activation eligibility, and other public capability details;
- owned embedded agents, discovered hostile agents on friendly/allied hosts,
  bounded player-level sabotage/relocation options, and Intelligence/CI ship options;
- one deduplicated construction-template catalog;
- diplomatic message history grouped by partner faction in chronological order (`conversations`).

Observations give full body detail in systems containing friendly
units, adjacent systems, and systems with visible enemy activity. Remote systems
retain exact stars and colonized bodies while neutral objects are summarized.
The model can move toward a system navigation anchor to receive exact target IDs
on a later turn. Inhibitor blocker values are intentionally bounded and expose
no identity or geometry for the conflicting inhibition zone.

The observation intentionally excludes enemy resources and hidden entity IDs.
The command gateway independently recomputes visibility for enemy targets, so a
fabricated or remembered hidden ID cannot bypass fog of war.

## Turn-start briefing

Every built-in planning request and Codex observation includes `turn_summary`
in its observation JSON. It contains `from_turn`,
`to_turn`, priority-ordered `entries`, net `economy` changes, and `omitted_count`.
Turn zero as `from_turn` means campaign setup. Each entry has an event ID, round,
category, historical subject ID/name/sector where authorized, detail, occurrence
count and total amount. Anonymous radar entries have no subject ID, name or unit
count. An empty entries list means no important events.

The engine collects committed events from just before the player's previous End
Turn resolution through the next owner-turn opening effects. It freezes the report
before presentation and AI scheduling. Observations, semantic repairs and manual
retries reuse that report without consuming it. Current observation visibility and
command legality take precedence over historical references. No additional model
request creates the summary, and model settings and command contracts are unchanged.

Human, built-in and Codex controllers share the same disclosure rules and report
content. Allied combat and discoveries are shared; production, economic and order
recaps are personal. The briefing journal is separate from the terminal outcomes
in `order_history`. Event hooks run during actual execution,
never during preflight or save hydration. Pending and current reports are bounded to
128 entries / 32,000 serialized characters, with explicit omission counts.

`conversations` includes all already-sent transmissions, including messages from
earlier players in the current round, matching human Comms timing. Briefings contain
counts by sender; message text stays in conversation history.

## OpenAI adapter

The adapter uses the current Responses API and strict `text.format` JSON Schema.
It does not enable model tools and does not chain response IDs. The initial
request is self-contained from the observation plus canonical memory. Repair
requests additionally include the latest rejected plan and errors; rejected
memory patches are never applied.

The Luna-only runtime is defined in `game_ai/runtime.py`:

| Player choice | Model | Reasoning |
|---|---|---|
| Low | `gpt-6-luna` | low |
| Medium (default) | `gpt-6-luna` | medium |
| High | `gpt-6-luna` | high |

Every choice uses the same 7,000-output-token limit, 120-second timeout, and
40-command turn limit. The player setting changes only the reasoning effort.
The timeout applies to each SDK request attempt; up to two transport retries can
extend total elapsed time. Reset cancellation also interrupts retry backoff.

The adapter uses `AsyncOpenAI` with foreground, non-streaming requests and
`store=False`. Providers implement `async plan_turn(request, runtime_config)` and
idempotent `async aclose()`. They must yield during I/O and propagate cancellation
after bounded cleanup. The coordinator owns its provider, including an injected
provider, and closes it on the same loop that performs requests. The OpenAI adapter
closes SDK clients it creates; an explicitly injected client remains caller-owned.
Foreground cancellation terminates the awaited HTTP connection, as described in
the [Responses cancellation documentation](https://developers.openai.com/api/docs/guides/background#limits);
no stored background response or polling job is created.

The API key loader checks `OPENAI_API_KEY` first, then
`API_keys/OpenAI.key`. The key is loaded lazily when the first AI turn begins.

## Memory and persistence

New campaigns, players, and AI agents receive stable 8-character hexadecimal short
IDs. Persistence also accepts readable IDs containing only ASCII letters, digits,
underscores and hyphens, excluding Windows reserved device names. The current save embeds:

- `campaign_id`;
- `persistent_id` and `agent_id`;
- selected `ai_reasoning_effort`;
- selected `ai_repair_retries`;
- bounded structured `ai_memory`;
- pending and frozen turn briefings, discovery/economy baselines and human acknowledgement.

Saved identities are required and the save is authoritative. The `memory.md`
sidecar is generated for inspection and is not read back into the campaign.
Only the current save version is supported; unsupported saves are rejected.
Malformed identities and noncanonical player configuration are rejected before
hydration, without generating replacement IDs or normalizing saved settings.
Persistent-player IDs and AI-agent IDs are each unique ignoring case within their respective
string-identity namespaces. See [player validation](SAVE_FORMAT.md#player-identities-and-configuration).

Memory and communication exports independently validate IDs and check resolved
destination and temporary-file containment before writing. Existing filesystem
links cannot redirect exports outside the save root or appropriate sidecar tree.
Sidecar export failures are reported without invalidating an already committed
save or AI turn; sidecars remain derived inspection files.

Memory contains separately bounded strategy, objectives, commitments, beliefs,
lessons and misc sections, plus recent execution receipts. The 8,000-character
combined cap applies only to those receipts, not to the entire memory. Individual turn
receipts are retained whole, dropping the oldest turns in their entirety when the
total limit is exceeded. Text and list counts are bounded before serialization.
Save JSON and memory sidecars use atomic replacement.

## Shared order contract

`game_ai.command_spec.COMMAND_SPECS` defines fields, constraints, queue behavior,
capabilities and descriptions. It generates the strict OpenAI command schema and the
socket observation's deduplicated `command_catalog`. Socket commands may omit optional
fields; OpenAI output must include every schema field (unused fields are null).
Validation rejects unknown fields, coercible strings, boolean/fractional IDs, duplicate
units, non-finite coordinates, inappropriate parameters, and batches/groups above
40 commands / 12 units. Immediate commands require `queue=false`. The coordinator
validates the complete turn plan, including `end_turn=true`, before mutation, even for
injected providers.

These shared rules apply to built-in AI and socket commands, and to human controls
that submit through the gateway. Human order controls follow the same engine
lifecycle; their selection behavior is described in the [reference](REFERENCE.md#queues-and-stances).
For an order-producing command, `queue=true` appends an explicit root; `queue=false`
replaces explicit work after preflight succeeds. Immediate commands apply their
own documented effect rather than implicitly replacing orders. Preserve a queued
prerequisite by appending its dependent order instead of replacing it.

Preflight uses shared legality queries against live state plus preceding projected
effects. Commit callbacks and executing orders recheck applicable live conditions,
including capability, targets, resources and location. Acceptance means issuable
work, not guaranteed arrival, safe placement or eventual completion. An order can
start and finish synchronously during issuance, or fail during later resolution.
See [commit guarantees](#commit-guarantees-and-lifecycle-feedback) for reservations,
settlement, receipts and failure stages.

Owned/allied units expose separate `standing_order`, `current_order` and
`queued_orders` sections. Types and statuses are readable strings.
Standing policy records suspension and its transient engagement. Explicit roots have
opaque UUID `order_id` values, separate from internal integer actuator ownership IDs.
All explicit root identities remain visible. Expanded suborders are limited to 32
nodes per unit and depth 6, prioritizing the active chain; waypoint previews contain
at most 16 entries, with omitted counts. Continuous orders identify blocked queue
entries as guidance. Progress contains actual engine phase/counters, never invented ETAs.

Explicit work suspends stance attacks; explicit Move also suppresses stance combat.
Changing stance preserves explicit work. Clearing explicit work resumes the selected
policy when idle. Stop cancels both layers and selects Do Nothing.

`set_stance` requires installed Weapons with at least one turret, independent of
weapon damage or turret cooldowns. Unarmed units omit it from `supported_commands`,
`legal_commands` and `command_options`, and expose `capability_details.allowed_stances: []`.
Every stance request on an unarmed unit, including `do_nothing`, rejects with
`capability_unavailable`. Their owned/allied `standing_order` remains a passive
Do Nothing policy with no engagement; use `cancel_orders` for Stop. Human stance
selection and cycling use the same gateway. Preflight rejects mixed armed/unarmed
groups atomically, and commit rechecks equipment and stance eligibility.

| Command | Required fields besides type/unit_ids | Meaning |
|---|---|---|
| `cancel_orders` | none | Stop both order layers and select Do Nothing. |
| `cancel_order` | `order_id` (exactly one owned unit) | Cancel one current/queued explicit root. |
| `clear_explicit_orders` | none | Cancel explicit work, preserve stance. |
| `append_patrol_waypoints` | `order_id`, `waypoints` (one owned unit) | Extend a current/queued patrol while preserving its leg. |
| `patrol` | `waypoints` OR complete system/hex/position | Traverse 1–16 waypoints, return to captured start, repeat. |
| `enter_gas_giant` | `target_id` (Gas Giant ID) | Approach and submerge inside a gas giant atmosphere, hiding ship from all sensors. |
| `leave_gas_giant` | none; supports `queue=true` | Depart when Leave reaches the front of the FIFO queue; requires hidden state or prior queued entry. |

`queue=true` creates a separate patrol, never an extension. Routes may contain at most
16 waypoints through AI commands. For human players, the "Add Patrol Waypoint" context menu option extends
patrol routes, while `Shift` consistently queues new orders. Internal
suborders and stance roots cannot be edited individually. Mandatory system roots
such as [wing servicing](#strikecraft-endurance-contract) have their own command
locks. Unavailable or foreign order IDs produce `order_unavailable`; UUID
possession grants no authority.

Friendly capabilities expose actual turret types, variants, ranges, cooldowns and target
classes, sensor and hyperdrive base/effective ranges, drive functionality/status, support
ranges, defend radius, and cloak state/activation/upkeep. Engine helpers supply effective
values (including XP and sabotage). Hardware support is distinct from current legality;
"legal" means issuable now, not guaranteed eventual success.

`game_ai.intelligence` is the shared, side-effect-free disclosure and legality policy.
The `intelligence` observation section identifies an owned agent's source ship, public
host and active sabotage, but not whether the host has discovered it. It identifies only
discovered enemy agents on friendly or allied hosts, without source ship or sabotage.
Allied agents contribute sensor sharing but are neither identified nor controllable.
Top-level `player_commands` carries legal `sabotage` and `relocate_agent` choices;
infiltration, extraction, CI sweep and elimination are unit commands. Missing, hidden,
foreign and stale agents uniformly return `agent_unavailable`; guessed hidden and
nonexistent world targets uniformly return `target_unavailable`.

`component_visibility.py` supplies the shared disclosure/subsystem policy for AI and UI.
Enemy Intelligence components are neither listed nor precision-targetable. Hidden and
nonexistent subsystem guesses return the same error. Public order serializers never dump
raw parameters, persistence or sidebar state. Hidden target references and their derived
movement geometry are redacted recursively; player-issued fixed coordinates remain intent.
Outcome history contains no target references, names, coordinates or raw exceptions.

## Commit guarantees and lifecycle feedback

The complete batch is preflighted before any prepared operation runs. Rejection
applies none of the batch: live orders, balances, targets and lifecycle events are
unchanged. The disposable projection may update its own ledger, reserve resources
and allocate public order UUIDs; it creates no authoritative orders or charges and
does not execute gameplay effects or draw their random outcomes.

This guarantees no command effects on rejection, not complete read-only access:
enemy-unit lookup and the remote-body disclosure fallback currently recompute
visibility with intel recording enabled. They can refresh sector-intel timestamps
and shared ghost identification even if the batch rejects. Pure visibility callers
must explicitly pass `record_intel=False`.

Preflight projects order-associated population, construction and docking reservations,
replacement, cancellation, route edits, toggles, agent relocation/sabotage, CI cooldowns,
credits and ship antimatter in array order. Construction credits are reserved only from
the initiating player's treasury; allied/enemy build queues cannot reduce that
budget. Allied docking and colony-population reservations still share capacity.
Only guaranteed effects can support later commands; feature sections specify which
effects are immediate and which merely reserve resources until execution.

Replacement or cancellation releases the affected pending reservations, not effects
already completed synchronously (such as a colonist load). Construction/refit jobs
bind their charge and cancellation ownership to the initiating order; cancelling a
pending sibling cannot cancel/refund the active job. Eligible refunds go to the
recorded original payer at most once. Pending unpaid jobs have no charge to refund;
salvage and destruction/capture settlement follow their feature-specific rules.

Commit executes prepared per-unit/player operations sequentially. Results include
`accepted`, `failure_stage`, `retryable`, `applied_count`, `operation_results`, receipts,
indexed errors, `may_have_partial_effects` and `requires_observation`. **applied_count counts
successfully completed operations**, not all mutations. Operations identify command index,
unit, command type, order ID, and applied/failed/unattempted status.

| Result | `accepted` | `failure_stage` | `retryable` | Partial effects / observation required |
|---|---|---|---|---|
| Preflight rejection | false | `preflight` | true | Both false; zero applied operations and indexed errors. |
| Completed commit | true | null | false | Both false; receipts and results for completed operations. |
| Commit exception | false | `commit` | false | Both true; retained receipts and applied/failed/unattempted results. |

On an exception, later operations are unattempted and the failing operation's
effects are uncertain. Earlier
completed operations remain applied. Dirty flags are set even on failure. Commit
failures require a fresh observation before deciding what to do next. There is no
rollback or automatic retry. Luna records partial results for manual recovery and
does not apply the rejected memory patch. Only preflight
and output rejections receive semantic repair requests. Telemetry adds failure stage and
operation outcome counts without prompts, raw observations, analysis or secrets.

`order_history.py` records explicit-root completed/failed/cancelled outcomes exactly once,
including synchronous outcomes, later-turn failures, replacement, destruction and capture.
Child failure codes reach the root. Destruction/capture recording does not invoke refunds.
Issuance receipts are separate from terminal outcomes. Each player (regardless of controller)
retains at most 128 events and 32,000 serialized characters, dropping oldest whole events.
Monotonic event IDs and retention metadata identify duplicates and missing history. An
observation exposes only its active player's journal, not an ally's entire history.

Order identities, history and charge ownership persist under the
[save restoration contract](SAVE_FORMAT.md#component-and-ability-schemas).
Socket token invalidation and request-ID recovery belong to the
[control guide](CODEX_CONTROL.md#recovery-distinctions). Format identifiers are in
the [generated version table](DEVELOPMENT.md#current-formats-and-protocols).

### Gameplay invariant guidance

For [gas-giant queue blocking](REFERENCE.md#gas-giant-atmospheric-hiding), inspect
`blocked_by_order_id` and use `cancel_order`, `clear_explicit_orders`, or a
replacement Leave to unblock departure. Preflight projects entry/departure
requirements; acceptance does not guarantee safe exit placement.

Use the canonical [damage](REFERENCE.md#weapons-and-damage),
[minefield](REFERENCE.md#minefields) and [spawn-profile](REFERENCE.md#spawn-profiles)
rules. Numeric object ID `0` is valid; only `None`/JSON `null` means a missing ID.

Friendly/allied turrets expose `effective_cooldown` for a shot at their current
position alongside base `cooldown` and `cooldown_remaining`. Already-exposed
celestial bodies carry numeric `environmental_effects`; no extra bodies or enemy
equipment are revealed. These fields follow the [environmental rules](REFERENCE.md#environmental-fields).

## Commands

### Construct customization and combat inspection

The command contract supports optional nullable `turret_type_override` (`mass_driver`,
`beam`, `missile`) and `defense_type_override` (`armor`, `shields`, `point_defense`)
on `construct` and `set_wing_production`. Each applies independently; null preserves
its preset. Non-null overrides on other commands are invalid. Grouped constructors
share choices; wing selection requires one carrier. See the
[customization rules](REFERENCE.md#automated-construction-customization) for equipment
requirements, combat effects and preserved design statistics.

Customization follows the [shared validation contract](#shared-order-contract)
and [job settlement guarantees](#commit-guarantees-and-lifecycle-feedback), using
original prices for reservations. Construct choices travel through approach
suborders and paid jobs; owner/allied order views include the selected overrides.

For visible enemies, observations expose only the public `weapons` and `defenses`
sections of `capability_details`, using actual installed equipment. Weapons include
type, variant, damage, range, cooldown/reset/remaining values, target classes and
operating state. Defenses include operating state and Armor/Shields/Point Defense
strengths. Owners and allies receive the same combat details alongside their other
capabilities. Detailed visibility is still required; enemy provenance, orders,
fire targets, hidden components and accounting are not exposed. The model receives
matchup guidance to select counters from observed equipment, not inferred templates.

Full design editing and refits are human workflows. Human bays select wing designs
and overrides through a production picker that submits `set_wing_production` via
the shared gateway. Persistence follows the [save contract](SAVE_FORMAT.md#fixed-destination-validation).

### Other commands

`rename_unit` is immediate and requires exactly one owned unit in `unit_ids`, a `new_name`
string and `queue=false`. Names are trimmed to remove surrounding whitespace, must contain
1–30 characters, and cannot contain control characters; duplicate names are allowed.
Renaming changes only the displayed name, preserving orders, stance, resources and agents.
It is legal while submerged or equipment is damaged. Human controls share validation;
the [commit guarantees](#commit-guarantees-and-lifecycle-feedback) apply. Names persist in saves.

The Covert Intelligence Ship and ordinary Patrol Escort have identical public equipment.
The covert template's `default_unit_name` is Patrol Escort; construction applies it before
publishing the ship. The catalog exposes each template's effective initial name, falling
back to its display name when no override exists. Keep safe generic names; an existing
Patrol Escort name needs no further renaming.

Every enemy unit omits `standing_order`, `current_order` and `queued_orders`. Template
identity, actual hull usage, upkeep and construction/refit details are private in both
interfaces. Owners and allies retain their existing detail. This prevents inspection from
identifying covert equipment; observed actions or discovered espionage can still be clues.

The strict contract currently supports movement, patrol, combat (with optional
subsystem targeting via `target_component`), positional defense (`defend`), protection,
colonization, colonist loading, construction, repair, mining, continuous
mining, unloading, docking (hangar and strikecraft bay) and carrier deployment, antimatter transfer/resupply, minefields, trade,
continuous trade, stances, inhibitor/cloaking toggles, diplomatic communications (`send_message`),
developer feedback (`message_developer`), abilities, and all intelligence operations:
`infiltrate_unit`, `infiltrate_planet`, `sabotage`, `relocate_agent`, `extract_agent`,
`ci_sweep`, and `eliminate_agent`.

The [batch projection](#commit-guarantees-and-lifecycle-feedback) allows a valid
`load_colonists` command to satisfy a later `colonize` command for the same unit
when colonization is queued. Entity-targeted commands (`colonize`, `load_colonists`,
`mine`, `repair`, `attack`, `attack_long_range`, `trade`) require only `target_id` (plus amount/component
if applicable); approach movement is automated, so coordinates (`position`, `hex_coord`,
`system_name`) must be null or omitted. Inhibitor toggles likewise project active dynamic
zones, so overlapping activations are rejected before commit and a preceding
deactivation can make a later activation legal. Commanding strikecraft wings into
magnetic storms, or launching wings from a carrier inside one, is rejected with
`hazard_blocked`. See [queue semantics](#shared-order-contract) for preserving prerequisites.

Retrofit remains a human editor transaction because it requires a versioned
component-configuration schema and dynamic cost preview. It is not advertised to
the model. Its human editor and Constructor execution share the Unit Designer's
complete equipment validation, including removals. See [field refitting](REFERENCE.md#field-refitting)
for costs and settlement, and [retrofit persistence](SAVE_FORMAT.md#retrofit-settlement)
for saved payer and salvage ownership.

`attack` and `attack_long_range` share `unit_ids`, `target_id`, optional
`target_component`, and `queue`; coordinates are unused. Discovery exposes eligible
unit and deployable targets. The long-range command requires functional Weapons and
an eligible Long Range turret; losing that capability fails the order rather than
changing it to normal Attack. See [attack rules](REFERENCE.md#queues-and-stances)
for approach/firing behavior and the 50% subsystem range modifier. Observation
turret `range` values remain hull ranges; command guidance explains the modifier.

Both attack commands require continuing detailed visibility to the attacking owner's
shared sensors/intelligence. Lost contact permanently cancels the active attack and
its approach with `target_not_visible`, reported once in the owner's order history and
briefing. Radar presence is insufficient. Checks run before movement/firing and at the
end of every player's turn, including opponents' turns. Reappearance does not revive
the cancelled order. Queued attacks revalidate when activated; other queued work,
stances and parent Patrol/Protect/Defend missions remain intact. These checks do not
run as mutations during observations or preflight. Loading restores no bindings to a
hidden target and defers cancellation/history to the first gameplay validation.

## Failure behavior

- SDK retries transient transport failures up to two times.
- Invalid command batches and malformed model outputs receive 1–5 semantic
  repair retries, configured per AI player from the in-game **AI Settings**
  dialog and defaulting to 2. The initial submission is not counted as a retry.
- Each semantic repair is a complete replacement response made with the
  player's selected reasoning effort. The retry budget is not sent to the
  model. The HUD turn status label updates to show the active retry attempt
  (e.g., `revising... retry 1/2`).
- Transport, authentication, quota, timeout, and commit failures do not consume
  semantic repairs.
- The retry limit is snapshotted when an AI turn begins, so in-match edits take
  effect on that AI player's next turn.
- Reset immediately invalidates the request generation and schedules cancellation
  without blocking the game loop. Stale successes and errors are discarded when
  generation, campaign, agent, turn or controller changes.
- Replacement planning starts after the previous request's cleanup actually
  finishes. The HUD shows `cancelling previous request…` during retirement.
  Cancelling a completion future alone does not release the provider. If the
  request does not retire within two seconds, the replacement fails into manual
  recovery; no additional worker or overlapping provider call is created. Retry
  can succeed after the obsolete request finally retires.
- Shutdown is idempotent and permanently stops submissions. It cancels requests,
  closes owned provider resources, and stops/joins the loop within a five-second
  total budget. Incomplete cleanup produces a payload-free warning; the daemon
  runtime thread cannot hold process exit open.
- On final failure, the error is shown and End Turn is re-enabled.
- Third-party SDK request-body logging is suppressed; API keys, observations,
  memory, prompts, analysis, and raw model output are never logged.
- Unexpected command preparation/commit diagnostics include stage, command index
  and type, exception class, and traceback frame locations only. They omit
  exception messages, payloads, source lines and locals. Public results follow
  the [commit guarantees](#commit-guarantees-and-lifecycle-feedback).
- Every attempt appends bounded telemetry to ignored
  `saves/ai_telemetry.jsonl`, including attempt index, model, reasoning, token
  use, latency, command summaries, errors, and whether another retry followed.
- Developer feedback transmissions (`message_developer`) are appended as
  human-readable Markdown entries to ignored `saves/ai_feedback.md` and logged to
  `game.log`.

## Evaluation

`game_ai.evaluation` defines provider-independent fixture cases and scores:

- schema/turn completion;
- required and forbidden command coverage;
- command budgets;
- latency;
- input/output token use.

Inject `FakePlanningProvider` for deterministic CI. Live reasoning-effort
comparisons are explicitly opt-in by constructing `OpenAIResponsesProvider`.
Evaluation runners are asynchronous: await `run_evaluation`,
`compare_reasoning_efforts` or `compare_gateway_reasoning_efforts`. A standalone
caller owns the provider and must await `provider.aclose()` in `finally` on the
same loop. Use one outer `asyncio.run()` for that complete evaluation lifecycle.
`colony_opening_case` reproduces the zero-cargo opening decision, and
`compare_reasoning_efforts` runs the same fixed cases at Low, Medium, and High
without changing production settings.
For an end-to-end semantic comparison, `colony_opening_gateway_case` builds a
fresh executable game fixture for each run and `compare_gateway_reasoning_efforts`
reports real gateway acceptance, attempts, repairs used, aggregate latency, and
input/output tokens at each reasoning effort. Transport and commit failures are
not retried by this harness, matching production behavior.
Keep fixed observations, seeds, model snapshots, and game balance constants
with any published result so regressions can be reproduced.

## Tactical ability integration

### Environmental resistance toggles

`toggle_ability` is an immediate, single-owned-unit command with `ability` and
`queue=false`; target fields are unused. It accepts `hazard_shielding`,
`radiation_hardening` and `antimatter_containment` when equipped. These use
`activation_mode: toggle` and cannot be cast with `use_ability`. Orders and stance
are preserved. Shared read-only validation supplies human UI, command guidance
and preflight, which projects repeated toggles and current AM in batch order.
Enabling checks combined upkeep but reserves and deducts no fuel. Applying the
prepared state follows the [shared execution checks](#shared-order-contract).

The ability catalogue exposes reduction, protected hazards, ongoing AM and payment
timing. Owned/allied `environmental_resistances` exposes active/operational state
and combined upkeep; owned ability states and command options expose blockers.
Enemy observations gain no equipment or resistance details. Celestial descriptions
retain baseline values. Protection, upkeep timing, shutdown rules and rounding
are documented in the [reference](REFERENCE.md#environmental-resistance-abilities).
The public catalogue includes Hazard Escort, Radiation Surveyor and Pulsar
Harvester so automated players can construct protected units.

### Cast abilities

Carrier and anti-strikecraft abilities also use the shared `use_ability` contract.
`attack_run` targets a visible enemy ship and replaces explicit work on every
eligible owned bomber belonging to the caster; `evasive_formation` and
`emergency_recovery` target one of its deployed wings. `tracking_lock` targets an
enemy wing; `flak_barrage` has no target or position. None automatically approaches.

Ability state includes eligible/participating owned wing IDs and balance modifiers;
Attack Run guidance lists the explicit orders it will replace. Wing observations
include evasion multipliers, weapon suppression and recovery launch locks. Explicit
wing orders expose approach/release/completion progress and remain cancellable.
Public links require visible endpoints; hidden targets and their approach geometry
remain redacted. Pending casts reserve caster AM/cooldown, choosing wings only at
execution. Immediate casts project wing-order replacements in batch order.
These follow the [shared execution checks](#shared-order-contract). Saves preserve
phases and deadlines under the [tactical state contract](SAVE_FORMAT.md#tactical-state);
recovered wings cannot launch before the next owner-turn start.
Ordinary cast readiness also requires functional storage for positive AM costs.
Projected fuel may satisfy affordability but cannot substitute for working storage.
Activation payment and rejection behavior follow the [ability rules](REFERENCE.md#abilities).

The six [tactical abilities](REFERENCE.md#deployment-and-link-abilities) share side-effect-free validation
in `tactical_abilities.py` across human controls, observations, preflight and orders.
`tactical_balance.py` centralizes defaults.
The [built-in catalogue](REFERENCE.md#built-in-unit-catalog) includes designs for
every ability. Automated players construct public designs or use equipped ships;
custom design editing is a human workflow.

Observations include `ability_catalog`, `visible_deployables`, `catalyst_patches` and
`ability_links`. Authorized ability state includes actual blockers/readiness,
cooldown/duration, active targets, ongoing AM, reserved casts, persistent deployment
counts/caps and Guardian tuning. Speed includes Tractor; environmental values
include relation-filtered Catalyst enhancements. Minefield records disclose only
revealed geometry/counts. Persistent objects report `persistent: true` without a
remaining lifetime. Enemy object views omit historical source IDs and public links
require both endpoints visible. Ghost signals use ordinary
`undetailed_enemy_presence`, without decoy flags, hidden IDs, counts or strength.

`use_ability` distinguishes unit targets, position targets and Catalyst's nebula
ID plus position. `multiply_antimatter` is a self-centered pulse with no target;
`cancel_ability` is immediate and accepts active Tractor/Guardian links. Typed
celestial/deployable references participate in recursive order redaction.

Within the [batch projection](#commit-guarantees-and-lifecycle-feedback), tactical
casts reserve AM, cooldown use, incoming-link occupancy/cycles and per-source
galaxy-wide caps. Immediate multiplication projects recipient gains and shared
recipient deadlines before the next command. A queued pulse reserves only its
caster cost: recipients are determined at execution. Pending pickup, delivery or
travel never finances an immediate cast.

`transfer_antimatter` and `take_antimatter` require functional storage, friendly
endpoints, and normal approach capability. Queued pickup/delivery may depend on
preceding resource changes.

Both continuous fuel commands require `source_id` and accept optional `target_id`
and `queue`. For `continuous_resupply`, the source is a star or hydrogen nebula;
for `continuous_antimatter_transport`, it is a loading unit and exactly one actor
is allowed. A unit `target_id` selects a fixed owned/allied recipient. Null or
omitted `target_id` selects Automatic delivery to eligible owned recipients.
See [antimatter logistics](REFERENCE.md#antimatter-logistics) for recipient selection,
waiting/failure conditions and reserves. Source and route checks follow the
[shared order contract](#shared-order-contract).

Command options expose `source_ids`, manual `target_ids`, destination modes and
ownership scope. Public order parameters expose source, configured target and
derived `destination_mode`; progress exposes `active_destination_id`, phase,
waiting reason and reserve. The active automatic recipient is separate from the
configured target, including across saves. All source, manual target, active
recipient and child approach geometry use recursive disclosure rules. A null
automatic recipient is valid state and does not trigger redaction.

Multiplication observations include radius, projected recipient gains, net AM,
caster cooldown and friendly units' shared recipient recovery. Enemy observations
do not expose these deadlines. Their component-independent lifetime is described
in [antimatter persistence](SAVE_FORMAT.md#antimatter-state); deployments and links
follow [tactical persistence](SAVE_FORMAT.md#tactical-state).

### Strikecraft production

`action_catalogs.wing_templates` lists built-in Fighter, Bomber, Interceptor,
Long Range Bomber and Recon Wings, with roles, equipment, prices and effective
weapon statistics. Private designs are excluded. Fighter-role wings target wings;
bomber-role wings target ships/stations and qualify for Attack Run.

Use `set_wing_production` with exactly one owned carrier, required zero-based
`slot_index`, explicitly supplied `template_name`, and `queue=false`. Each command
replaces only that slot's template and independent `turret_type_override` and
`defense_type_override`. Null/omitted overrides restore the template presets.
Explicit `template_name: null` clears the slot and requires null/omitted overrides;
omitting `template_name` is invalid. Overrides retain existing customization rules,
statistics, variants, prices and construction duration.

Selection is free, preserves orders and stance, and works while occupied,
replenishing, paused or short of credits. Only the slot under construction is
locked. Existing wings retain their equipment; changes configure future replacements.
Selection follows the [shared order contract](#shared-order-contract) and
[ordered commit guarantees](#commit-guarantees-and-lifecycle-feedback).

New slots build nothing until selected. `set_wing_production_enabled` is bay-wide
and independent of slot selection. The [production rules](REFERENCE.md#built-in-unit-catalog)
own worker priority, payment timing, slot assignment, replenishment and pause behavior.

Owner/allied `capability_details.strikecraft_bay.slots` exposes each `slot_index`,
`production_template`, nullable overrides, `wing_id`, `wing_name`, `status`
(`empty`, `docked`, `launched`, `building`), `production_turns`,
`production_credit_cost` and `edit_blocker`. Unselected costs/durations are null.
The bay exposes `production_enabled`, `constructing`, `construction_slot_index`,
`construction_progress`, `replenishing_unit_id` and `replenish_progress`.
Owned command options expose editable `slot_indices`, `can_clear`, template names,
and override choices. Enemy views receive no production details.

Human slot labels start at 1; command indices start at 0. See the
[production picker](REFERENCE.md#built-in-unit-catalog) for controls and
[component persistence](SAVE_FORMAT.md#component-and-ability-schemas) for selections,
assignments and paid work.

```json
{"type":"set_wing_production","unit_ids":[101],"slot_index":0,"template_name":"FIGHTER_WING","queue":false}
{"type":"set_wing_production","unit_ids":[101],"slot_index":1,"template_name":"LONG_RANGE_BOMBER_WING","turret_type_override":"beam","defense_type_override":"armor","queue":false}
{"type":"set_wing_production","unit_ids":[101],"slot_index":2,"template_name":null,"queue":false}
```

### Celestial observation contract

Already-exposed bodies use readable uppercase `subtype` names (`MAGNETIC`,
`BLACK_HOLE`, etc.). `collision_radius` and `inhibition_field_radius` describe
independent boundaries; non-solid bodies additionally expose `effect_radius`.
Mechanical radii retain full precision. `environmental_effects` retains existing
modifier keys and adds speed, concealment, sensor suppression, wing exceptions,
and `hazards`. Each hazard specifies kind, amount/basis, target, timing, scope,
radius, affected unit classes, and any sublight-movement/speed requirement.
Black-hole hazards have their own radius; pulsar hazards cover the whole sector.

`environmental_rules` contains complete explanations of stacking, cooldown floors,
damage classification, harvesting range, timing and exceptions. Humans can expand
**Full rules** in body panels to read these explanations; the default view uses
concise colored summaries. The built-in AI continues to receive the complete
explanations in its observation; repository documentation is not implicitly
included in its request.

Friendly/allied `capability_details.engines.effective_speed` includes current
terrain drag; `sensors.effective_long_range_hexes` includes magnetic suppression.
Base speed and sensor ranges remain available separately. Unit
`environmental_modifiers` includes current cover, drag, sensor suppression and
relation-filtered Catalyst enhancements; body values describe baseline terrain.
Catalyst patch records describe only the enhancement relevant to their nebula.

Enrichment preserves existing body visibility and remote summaries and exposes
no additional enemy equipment.


## Planetary warfare contract

`planetary_warfare.py` supplies shared eligibility, previews and resolution, with
initial tuning in `planetary_balance.py`. Human controls commit the same commands.

`recruit_troops`, `bombard_planet` and `invade_planet` each take one owned ship,
`target_id` and `queue`; recruitment and invasion also require positive integer
`amount`. `upgrade_planetary_defenses` takes empty `unit_ids`, an owned colony
`target_id` and `queue=false`. Typed celestial references use surface-aware approach
routing. Effects wait for End Turn except immediate fortification upgrades.

Preflight projects recruitment population, credits and cargo in batch order.
Queued recruitment can enable a queued invasion. Invasions reserve committed fuel
and worst-case casualties; projected victories and future income never finance a
later command. Reservation release and failure handling follow the
[commit guarantees](#commit-guarantees-and-lifecycle-feedback); preflight never
consumes invasion randomness.

Exact colony observations include `planetary_defenses`; own/allied ships include
`troop_cargo`. Enemy cargo remains private. Command options expose costs, ranges,
amount limits, blockers, probabilities and casualty outcomes. Recheck these before
issuing an order; arrival can change odds. Recruitment is private to the owner;
combat and capture briefings disclose only authorized participants' information.

After ordinary unit updates and cleanup, a snapshot resolves recruitment,
bombardment, then invasion in unit-ID order. An enduring unit round marker prevents
extra actions through replacement, refits or capture. Execution revalidates live
orders, targets, allegiance, deployment, visibility, equipment, cargo and resources.
Invalid actions neither charge nor consume invasion randomness. Quiet-round recovery
runs once globally after growth. Colony support and income are derived from current
ownership; capture invalidates visibility/sidebar state and stops newly allied sabotage.

A dedicated campaign RNG supplies invasion rolls. Its state, colony defenses,
unit action markers, cargo and active approach orders are saved in the current format.
Loading and previews never roll or replay planetary effects. See
[planetary warfare](REFERENCE.md#planetary-warfare) for complete balance and controls.

## Wormhole stabilization contract

The shared command contract exposes `stabilize_wormhole`, taking one
owned `unit_ids` entry, a disclosed wormhole `target_id`, and `queue`. Coordinates
are unused. Human controls commit through the same gateway.

Equipment, disclosure and approach feasibility follow the
[shared validation contract](#shared-order-contract). Low fuel is legal and waits
for resupply; issuing the order does not activate paid support.
The continuous root exposes actual approach/maintaining/waiting/disabled progress
and blocks following orders. Target references and derived geometry use normal
recursive redaction. Owned/allied units expose `wormhole_stabilizer` capability
and operating state; enemies expose only ordinary public equipment details.

Already-disclosed wormholes retain natural `stability` and add
`effective_stability` and `stabilized`. These public connection properties reveal
no supporting unit IDs, counts or locations and disclose no additional bodies.
The public Logistics catalogue includes the Tender and Station designs.
See [stabilization rules](REFERENCE.md#wormhole-stabilization) for payment timing,
all-player benefits, interruptions and automatic fuel recovery.


## Fixed positional destinations

The shared command contract requires `system_name`, `hex_coord`, and `position` for Construct
and position-targeted abilities, as for Move and positional Defend/Patrol. Ability
requirements are conditional on target kind; entity and self targets keep their
existing forms. Partial locations fail the [shared validation contract](#shared-order-contract);
UI adapters apply the same location validation before replacing orders.
Factories preserve the supplied site rather than binding it to the acting unit.
Observations expose complete authorized order destinations and ability location
requirements. Local-only abilities revalidate sector identity when they execute.
Active construction retains its fixed site; displacement outside build range or
sector fails the job under the [settlement guarantees](#commit-guarantees-and-lifecycle-feedback).
See [fixed construction sites](REFERENCE.md#fixed-construction-sites) and
[saved destination validation](SAVE_FORMAT.md#fixed-destination-validation).

## Unit dismantling

See also the [strikecraft endurance contract](#strikecraft-endurance-contract).

The shared command contract exposes the `dismantle_unit` order:

```json
{"type":"dismantle_unit","unit_ids":[101],"target_id":202,"queue":false}
{"type":"set_wing_production_enabled","unit_ids":[303],"enabled":true,"queue":false}
```

Use exactly one owned executor: a separate Constructor for ships/stations, or the
owning carrier for an already-docked wing. The production toggle is immediate and
requires a strict boolean. Design selection leaves the production toggle unchanged.
`command_options.dismantle_unit.targets` provides blockers, recursive members,
current refund estimates, total duration, discarded cargo and paid-work waits.
Owned/allied details expose dismantling phase/progress and bay production state;
enemy-private component and order information remains hidden.

Membership and Designer valuations freeze when work begins. Refunds depend on HP
at completion and cannot finance subsequent commands in the issuing batch.
The [projection ledger](#commit-guarantees-and-lifecycle-feedback) tracks claims and
offline targets; overlapping jobs, worker/target cycles and conflicting operations
are invalid. Issue dismantling after observing prior docking/deployment results.
Cancel via the executor's ordinary `cancel_order`. Work progresses once per owner
End Turn; observation, command issuance and loading never advance it or pay salvage.
See [gameplay rules](REFERENCE.md#unit-dismantling) for eligibility and interruptions.

## Strikecraft endurance contract

Observations include owned/allied `wing_service`: `turns_outside` (capped at 80),
`endurance_limit`, `turns_remaining`, disclosed `mother_carrier_id`, `return_required`,
`return_blocker`, `carrier_available`, `launch_locked`, `ready_round`, and `status`
(`deployed`, `returning`, `servicing`, `ready`). Docked wings expose this inside their
carrier's `capability_details.strikecraft_bay.docked_units`. Enemies receive none of
these private fields. Unavailable carrier references are redacted.

The engine advances endurance once at the beginning of each deployed wing's owner
End Turn, independent of controller. At 80 it replaces all explicit work with
`return_for_service`, exposed with `origin: system` and `cancellable: false`, and
suppresses weapons and stance activity. Only `rename_unit` remains legal. Conflicting
commands reject with `wing_service_required`; carrier Attack Run and Emergency
Recovery cannot replace the return. The [shared order contract](#shared-order-contract)
applies to this lock, including docking followed by relaunch in one batch.

See [endurance and servicing](REFERENCE.md#strikecraft-endurance-and-servicing) for
return, expiration and docking rules. Briefings report forced returns and expiration;
`wing_endurance_expired` identifies interrupted orders. Planning, observations and
loading do not advance the timer. Clock terminology is defined in
[turn timing](DEVELOPMENT.md#turn-timing).

The current save and Wing component schema persist the counter, last processed
round, return order and launch deadline. See the [current formats and protocols](DEVELOPMENT.md#current-formats-and-protocols).
