# Agentic AI Architecture

Wormhole Control treats an LLM as an untrusted planning process, not as part of
the authoritative game engine. The model receives a JSON-safe observation,
returns one strict turn plan, and cannot access Python objects, hidden state,
files, or arbitrary tools.

## Turn flow

1. `TurnProcessor.check_and_schedule_ai_turn` retains the normal 500 ms turn
   transition delay, including slot-zero AI players and loaded AI turns.
2. `AgentTurnCoordinator` builds the observation on the Pygame thread and sends
   only plain data to a one-worker background executor.
3. `OpenAIResponsesProvider` makes one non-streaming Responses API request with
   strict JSON Schema output and `store=False`.
4. The coordinator polls the future from `Game.update`.
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
player. It includes:

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

Observation schema 20 gives full body detail in systems containing friendly
units, adjacent systems, and systems with visible enemy activity. Remote systems
retain exact stars and colonized bodies while neutral objects are summarized.
The model can move toward a system navigation anchor to receive exact target IDs
on a later turn. Inhibitor blocker values are intentionally bounded and expose
no identity or geometry for the conflicting inhibition zone.

The observation intentionally excludes enemy resources and hidden entity IDs.
The command gateway independently recomputes visibility for enemy targets, so a
fabricated or remembered hidden ID cannot bypass fog of war.

## Turn-start briefing

Observation schema 20 appends `turn_summary` to the observation JSON included in
every built-in planning request and Codex observation. It contains `from_turn`,
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
recaps are personal. The new journal is separate from `order_history`, whose strict
terminal-outcome format remains unchanged. Event hooks run during actual execution,
never during preflight or save hydration. Pending and current reports are bounded to
128 entries / 32,000 serialized characters, with explicit omission counts.

`conversations` now includes all already-sent transmissions, including messages from
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
| Low | `gpt-5.6-luna` | low |
| Medium (default) | `gpt-5.6-luna` | medium |
| High | `gpt-5.6-luna` | high |

Every choice uses the same 7,000-output-token limit, 120-second timeout, and
40-command turn limit. The player setting changes only the reasoning effort.

The API key loader checks `OPENAI_API_KEY` first, then
`API_keys/OpenAI.key`. The key is loaded lazily when the first AI turn begins.

## Memory and persistence

Every campaign, player, and agent has a stable 8-character hexadecimal short ID. Save version 4.16 embeds:

- `campaign_id`;
- `persistent_id` and `agent_id`;
- selected `ai_reasoning_effort`;
- selected `ai_repair_retries`;
- bounded structured `ai_memory`;
- pending and frozen turn briefings, discovery/economy baselines and human acknowledgement.

Saved identities are required and the save is authoritative. The `memory.md`
sidecar is generated for inspection and is not read back into the campaign.
Only the current save version is supported; unsupported saves are rejected.

Memory contains strategy, objectives, commitments, beliefs, lessons, misc,
and recent execution receipts bounded to 8,000 total characters. Individual turn
receipts are retained whole, dropping the oldest turns in their entirety when the
total limit is exceeded. Text and list counts are bounded before serialization.
Save JSON and memory sidecars use atomic replacement.

## Commands

### Construct customization and combat inspection

Command contract 17 adds optional nullable `turret_type_override` (`mass_driver`,
`beam`, `missile`) and `defense_type_override` (`armor`, `shields`, `point_defense`)
to `construct` and `set_wing_production`. Each applies independently; null preserves
its preset. All turrets
change type without changing stats or variants. All defense strength is summed
into the chosen type with the other two zeroed. Costs, build time, hull use,
component HP, upkeep and default names are preserved; no catalogue entry is added.
A turret override without turrets, or a defense override without positive defense
strength, is rejected.
Non-null overrides on other commands are invalid. Grouped constructors share
choices; wing selection requires one carrier.

The shared pure customization rules run in preflight and execution. Preflight
remains atomic and uses original prices for reservations. Construct choices travel through
approach suborders and paid Constructor jobs; invalid completion fails and refunds
only the owning job. Owner/allied order views include selected overrides.

Observation 20 gives visible enemies only the public `weapons` and `defenses`
sections of `capability_details`, using actual installed equipment. Weapons include
type, variant, damage, range, cooldown/reset/remaining values, target classes and
operating state. Defenses include operating state and Armor/Shields/Point Defense
strengths. Owners and allies receive the same combat details alongside their other
capabilities. Detailed visibility is still required; enemy provenance, orders,
fire targets, hidden components and accounting are not exposed. The model receives
matchup guidance to select counters from observed equipment, not inferred templates.

Response schema v14 and prompt cache v20 apply; socket protocol remains 3.
Save 4.16 / Constructor schema 3 preserve choices with no older-save migration.
Full design editing, refits and human constructor controls are unchanged. Human
bays select wing designs and the same independent turret/defense type overrides
through a production picker that submits `set_wing_production` via the shared gateway.

### Other commands

`rename_unit` is immediate and requires exactly one owned unit in `unit_ids`, a `new_name`
string and `queue=false`. Names are trimmed to remove surrounding whitespace, must contain
1–30 characters, and cannot contain control characters; duplicate names are allowed.
Renaming changes only the displayed name, preserving orders, stance, resources and agents.
It is legal while submerged or equipment is damaged. Validation is shared with human
controls; preflight rejection leaves all names unchanged. Successful commits return a
receipt, and the existing save format preserves the name.

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

The observation and gateway share side-effect-free legality rules. The gateway
also projects guaranteed effects through a batch, allowing a valid
`load_colonists` command to satisfy a later `colonize` command for the same unit
when colonization is queued. Entity-targeted commands (`colonize`, `load_colonists`,
`mine`, `repair`, `attack`, `attack_long_range`, `trade`) require only `target_id` (plus amount/component
if applicable); approach movement is automated, so coordinates (`position`, `hex_coord`,
`system_name`) must be null or omitted. Inhibitor toggles likewise project active dynamic
zones, so overlapping activations are rejected before commit and a preceding
deactivation can make a later activation legal. Replacing pending work releases only its reservations; it cannot undo a colonist load
that already completed synchronously. Environmental hazard constraints are also enforced: commanding strikecraft wings into magnetic storms, or launching wings from a carrier inside a magnetic storm, is rejected at preflight with `hazard_blocked`. Preserve queued prerequisites with `queue=true`. The complete batch remains atomic
at preflight.

Retrofit remains a human editor transaction because it requires a versioned
component-configuration schema and dynamic cost preview. It is not advertised to
the model. Its human editor and Constructor execution now share the Unit Designer's
complete equipment validation, including removals. Saves record the
original refit payer and unpaid salvage; settlement occurs only once. Removal
salvage is granted on successful completion, and failed installation validation
refunds the original payer. No retrofit command is added to the AI contract.

`attack` approaches until all target-eligible turrets are in range.
`attack_long_range` requires functional Weapons and at least one eligible Long Range
variant turret, approaching until all such turrets are in range. Both permit every
eligible turret to fire within its own range and neither retreats. The commands
share `unit_ids`, `target_id`, optional `target_component`, and `queue`; coordinates
are unused. Discovery exposes eligible unit and deployable targets. Missing capability
rejects the entire batch before replacement or cancellation; later capability loss
fails the order without changing it to normal Attack. See [attack rules](REFERENCE.md#queues-and-stances).

For both attacks, a non-null `target_component` halves every turret's listed hull
range for approach and firing, after variant scaling. Each turret holds fire until
strictly inside its own component range, without substituting hull fire while
approaching. Observation turret `range` values remain hull ranges; command catalog
descriptions and built-in planning instructions explain the modifier. Command,
observation and save schemas are unchanged.

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
- Stale responses are discarded when campaign, agent, or turn changes.
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

## Shared order contract (observation 20 / commands 17 / socket 3)

`game_ai.command_spec.COMMAND_SPECS` defines fields, constraints, queue behavior,
capabilities and descriptions. It generates the strict OpenAI command schema and the
socket observation's deduplicated `command_catalog`. Socket commands may omit optional
fields; OpenAI output must include every schema field (unused fields are null).
Validation rejects unknown fields, coercible strings, boolean/fractional IDs, duplicate
units, non-finite coordinates, inappropriate parameters, and batches/groups above
40 commands / 12 units. Immediate commands require `queue=false`. The coordinator
validates the complete turn plan, including `end_turn=true`, before mutation, even for
injected providers. Model, reasoning, timeout and token budgets are unchanged.

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
policy when idle. Stop cancels both layers and selects Do Nothing. Commands:

| Command | Required fields besides type/unit_ids | Meaning |
|---|---|---|
| `cancel_order` | `order_id` (exactly one owned unit) | Cancel one current/queued explicit root. |
| `clear_explicit_orders` | none | Cancel explicit work, preserve stance. |
| `append_patrol_waypoints` | `order_id`, `waypoints` (one owned unit) | Extend a current/queued patrol while preserving its leg. |
| `patrol` | `waypoints` OR complete system/hex/position | Traverse 1–16 waypoints, return to captured start, repeat. |
| `enter_gas_giant` | `target_id` (Gas Giant ID) | Approach and submerge inside a gas giant atmosphere, hiding ship from all sensors. |
| `leave_gas_giant` | none; supports `queue=true` | Depart when Leave reaches the front of the FIFO queue; requires hidden state or prior queued entry. |

`queue=true` creates a separate patrol, never an extension. Routes may contain at most
16 waypoints through AI commands. For human players, the "Add Patrol Waypoint" context menu option extends
patrol routes, while `Shift` consistently queues new orders. Internal
suborders and stance roots cannot be edited individually. Unavailable or foreign order
IDs produce `order_unavailable`; UUID possession grants no authority.

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

Preflight projects order-associated population, construction and docking reservations,
replacement, cancellation, route edits, toggles, agent relocation/sabotage, CI cooldowns,
credits and ship antimatter in array order. It creates no authoritative
orders, charges, component targets or lifecycle events. Construction/refit jobs bind their
charge and cancellation ownership to the initiating order; cancelling a pending sibling
cannot cancel/refund the active job. Refunds go to the original payer at most once.

Commit executes prepared per-unit/player operations sequentially. Results include
`accepted`, `failure_stage`, `retryable`, `applied_count`, `operation_results`, receipts,
indexed errors, `may_have_partial_effects` and `requires_observation`. **applied_count counts
successfully completed operations**, not all mutations. Operations identify command index,
unit, command type, order ID, and applied/failed/unattempted status. On an exception, later
operations are unattempted and the failing operation's effects are uncertain. Dirty flags
are set even on failure. There is no rollback or automatic retry. Luna records partial
results for manual recovery and does not apply the rejected memory patch. Only preflight
and output rejections receive semantic repair requests. Telemetry adds failure stage and
operation outcome counts without prompts, raw observations, analysis or secrets.

`order_history.py` records explicit-root completed/failed/cancelled outcomes exactly once,
including synchronous outcomes, later-turn failures, replacement, destruction and capture.
Child failure codes reach the root. Destruction/capture recording does not invoke refunds.
Issuance receipts are separate from terminal outcomes. Each player (regardless of controller)
retains at most 128 events and 32,000 serialized characters, dropping oldest whole events.
Monotonic event IDs and retention metadata identify duplicates and missing history. An
observation exposes only its active player's journal, not an ally's entire history.

The current save preserves order UUIDs recursively, history/counter, terminal-recording state and
job charges. Missing order identities and payment state are rejected. Restored active orders rebind
actuators/job ownership without replaying startup or refunds; pending orders start on a
subsequent update. Recursively docked units restore too; stance engagements are reacquired.
The strict response schema is `wormhole_control_turn_v14`, and prompt cache key is
`wormhole-control-turn-v20`. No live API call is required for regression testing.

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

## Tactical ability integration

### Environmental resistance toggles

`toggle_ability` is an immediate, single-owned-unit command with `ability` and
`queue=false`; target fields are unused. It accepts `hazard_shielding`,
`radiation_hardening` and `antimatter_containment` when equipped. These use
`activation_mode: toggle` and cannot be cast with `use_ability`. Orders and stance
are preserved. Shared read-only validation supplies human UI, command guidance
and preflight, which projects repeated toggles and current AM in batch order.
Enabling checks combined upkeep but reserves and deducts no fuel. Commit rechecks
authoritative state before applying the prepared enabled/disabled state.

The ability catalogue exposes reduction, protected hazards, ongoing AM and payment
timing. Owned/allied `environmental_resistances` exposes active/operational state
and combined upkeep; owned ability states and command options expose blockers.
Enemy observations gain no equipment or resistance details. Celestial descriptions
retain baseline values. Protection is 75%; upkeep is 2/1/1 AM respectively,
charged before owner-turn environmental hazards even in safe space. Insufficient
fuel disables all active resistances without a partial charge. Hazards, shutdown
rules and rounding are documented in the [reference](REFERENCE.md#environmental-resistance-abilities).
The public catalogue includes Hazard Escort, Radiation Surveyor and Pulsar
Harvester so automated players can construct protected units.

### Cast abilities

Carrier and anti-strikecraft abilities also use the shared `use_ability` contract.
`attack_run` targets a visible enemy ship and replaces explicit work on every
eligible owned bomber belonging to the caster; `evasive_formation` and
`emergency_recovery` target one of its deployed wings. `tracking_lock` targets an
enemy wing; `flak_barrage` has no target or position. None automatically approaches.
Command fields and contract/socket versions remain unchanged.

Ability state includes eligible/participating owned wing IDs and balance modifiers;
Attack Run guidance lists the explicit orders it will replace. Wing observations
include evasion multipliers, weapon suppression and recovery launch locks. Explicit
wing orders expose approach/release/completion progress and remain cancellable.
Public links require visible endpoints; hidden targets and their approach geometry
remain redacted. Pending casts reserve caster AM/cooldown, choosing wings only at
execution. Immediate casts project wing-order replacements in batch order.
Execution rechecks legality. Saves preserve phases and deadlines without replaying
casts or salvos; recovered wings cannot launch before the next owner-turn start.

The six [tactical abilities](REFERENCE.md#deployment-and-link-abilities) share side-effect-free validation
in `tactical_abilities.py` across human controls, observations, preflight and orders.
`tactical_balance.py` centralizes defaults.
The [built-in catalogue](REFERENCE.md#built-in-unit-catalog) includes designs for
every ability. Automated players construct public designs or use equipped ships;
custom design editing is a human workflow.

Observation 20 includes `ability_catalog`, `visible_deployables`, `catalyst_patches` and
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

Preflight projects AM, cooldown use, incoming-link occupancy/cycles, per-source galaxy-wide caps, and cancellation in array order. Immediate multiplication projects recipient gains and shared recipient deadlines before validating the next command. A queued pulse reserves only its caster cost: recipients are determined at execution. Pending pickup, delivery, or travel never finances an immediate cast. Replacing or cancelling pending orders releases reservations. Execution rechecks authoritative state, and batch rejection remains atomic.

`transfer_antimatter` and `take_antimatter` require functional storage, friendly
endpoints, and normal approach capability. Queued pickup/delivery may depend on
preceding resource changes.

Both continuous fuel commands require `source_id` and accept optional `target_id`
and `queue`. For `continuous_resupply`, the source is a star or hydrogen nebula;
for `continuous_antimatter_transport`, it is a loading unit and exactly one actor
is allowed. A unit `target_id` selects a fixed owned/allied recipient. Null or
omitted `target_id` selects Automatic: nearest reachable owned recipients
galaxy-wide, excluding the actor and loading source, with multiple deliveries per
load. Automatic routes may start without demand and wait at their source. Losing
a manual recipient fails the order without substitution; full manual recipients
wait. Harvesters retain 60 AM; transports recalculate buffered return reserves for
each delivery from their current position. Shared source and route validation is
side-effect-free, and batch rejection remains atomic.

Command options expose `source_ids`, manual `target_ids`, destination modes and
ownership scope. Public order parameters expose source, configured target and
derived `destination_mode`; progress exposes `active_destination_id`, phase,
waiting reason and reserve. The active automatic recipient is separate from the
configured target, including across saves. All source, manual target, active
recipient and child approach geometry use recursive disclosure rules. A null
automatic recipient is valid state and does not trigger redaction.

Multiplication observations include radius, projected recipient gains, net AM, caster cooldown, and friendly units' shared recipient recovery. Cast and recipient deadlines live on the unit and persist independently of components. Enemy observations do not expose these deadlines. Save 4.16 uses unit schema 3. Fuel Cache, its deployable kind, and its recovery command have been removed; no compatibility aliases are provided.

The current save stores independent ghost emitters, source provenance, identification, patch allegiance/deadlines, link tuning/deadlines and processed pull phases. Counts are rebuilt from surviving objects. Typed endpoint references and transport phase/wait/reserve state restore without replaying transfers, casts or approach execution.

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
Invalid indices, templates, overrides and unavailable slots reject the complete
batch before mutation. Commit rechecks availability; selections apply in array order.

Every new slot is unselected and builds nothing until configured. The bay has one
shared worker: replenishment keeps priority, followed by the first affordable empty
selected slot in ascending index order. Payment occurs when construction starts.
That slot is reserved until completion. Launch and return retain the same slot;
loss, dismantling and transfer free it without changing its replacement settings.
Incoming wings use the first free unreserved slot regardless of selected design,
and docking never selects or changes production. Docking and replenishment work
without production selections.

`set_wing_production_enabled` remains bay-wide. Selecting or clearing a slot never
changes the pause state; enabling alone never selects designs. Paid work finishes
while paused, and dismantling retains its existing paid-work wait and pause rules.

Owner/allied `capability_details.strikecraft_bay.slots` exposes each `slot_index`,
`production_template`, nullable overrides, `wing_id`, `wing_name`, `status`
(`empty`, `docked`, `launched`, `building`), `production_turns`,
`production_credit_cost` and `edit_blocker`. Unselected costs/durations are null.
The bay exposes `production_enabled`, `constructing`, `construction_slot_index`,
`construction_progress`, `replenishing_unit_id` and `replenish_progress`.
Owned command options expose editable `slot_indices`, `can_clear`, template names,
and override choices. Enemy views receive no production details.

The human component panel labels slots starting at 1 and opens a slot-specific
picker with the same configuration and equipment previews. **No production** clears
the slot on **Select Production**; Cancel, Esc and closing discard edits.
Save 4.16 / Strikecraft Bay schema 5 preserve selections, stable assignments and
paid work without replaying payment or assembly. Command contract 17, observation
20, response schema v14 and prompt cache v20 apply; socket protocol remains 3.

```json
{"type":"set_wing_production","unit_ids":[101],"slot_index":0,"template_name":"FIGHTER_WING","queue":false}
{"type":"set_wing_production","unit_ids":[101],"slot_index":1,"template_name":"LONG_RANGE_BOMBER_WING","turret_type_override":"beam","defense_type_override":"armor","queue":false}
{"type":"set_wing_production","unit_ids":[101],"slot_index":2,"template_name":null,"queue":false}
```

### Celestial observation contract (schema 20)

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
no additional enemy equipment. Command contract 17, socket protocol 3, response
schema v14 and save format 4.16 apply. Prompt cache key is v20.


## Planetary warfare contract

Observation schema 20, command contract 17, response schema v14 and prompt cache
key v20 include planetary warfare; socket protocol 3 retains its envelope.
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
later command. Replacement and cancellation release pending reservations. The whole
batch rejects without mutation or random draws; existing partial-commit reporting
still applies to unexpected execution exceptions.

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
unit action markers, cargo and active approach orders are saved in format 4.16.
Loading and previews never roll or replay planetary effects. See
[planetary warfare](REFERENCE.md#planetary-warfare) for complete balance and controls.

## Wormhole stabilization contract

Observation 20 and command contract 17 expose `stabilize_wormhole`, taking one
owned `unit_ids` entry, a disclosed wormhole `target_id`, and `queue`. Coordinates
are unused. Response schema v14 and prompt cache v20 apply; socket protocol 3 is
unchanged. Human controls commit through the same gateway.

Shared read-only rules validate equipment, disclosure and approach feasibility
before replacing orders. Low fuel is legal and waits for resupply; preflight does
not spend fuel, draw randomness or activate support. Execution revalidates state.
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

Command contract 17 requires `system_name`, `hex_coord`, and `position` for Construct
and position-targeted abilities, as for Move and positional Defend/Patrol. Ability
requirements are conditional on target kind; entity and self targets keep their
existing forms. Shared location validation rejects partial locations before any
batch effects; UI adapters apply the same validation before replacing orders.
Factories preserve the supplied site rather than binding it to the acting unit.
Observation 20 exposes complete authorized order destinations and ability location
requirements. Local-only abilities revalidate sector identity when they execute.
Active construction retains its fixed site and charge owner; displacement outside
build range or sector fails and refunds only that job once. Save 4.16 and Constructor
schema 3 require complete job locations and matching active order ownership.

## Unit dismantling

Contract 17 / observation 20 exposes the shared `dismantle_unit` order:

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
Preflight projects order replacement, cancellations, claims and offline targets;
overlapping jobs, worker/target cycles and conflicting operations reject the batch
without effects. Issue dismantling after observing prior docking/deployment results.
Cancel via the executor's ordinary `cancel_order`. Work progresses once per owner
End Turn; observation, command issuance and loading never advance it or pay salvage.
See [gameplay rules](REFERENCE.md#unit-dismantling) for eligibility and interruptions.
