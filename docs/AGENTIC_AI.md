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
7. The memory patch and execution receipts are bounded, persisted, and the turn
   ends.

No API call is made for a human player. Tests and evaluation use injected fake
providers by default, so they do not consume API credits.

## Information boundary

`game_ai.observation.build_observation` recomputes visibility for the active
player. It includes:

- the active player's economy;
- public system topology, navigation anchors, detailed nearby bodies (including planetary traits, colonizability, passive mineral yields, and antimatter harvesting sources/multipliers), and summaries of remote neutral bodies;
- owned and allied units;
- enemy units only when detailed visibility permits them (concealed from long-range radar presence when cloaked or inside nebulae or asteroid fields);
- celestial fields (asteroid, debris, ice) with density parameters (`density`, `max_hull_size`) that restrict hulls exceeding the field's maximum allowable hull, rejecting forbidden commands with `hazard_blocked`;
- space storms (plasma, magnetic, radiation) and black hole event horizons that inflict active environmental hazards (strikecraft wings are banned from entering or launching in magnetic storms, but are immune to negative field effects and can enter fields of all densities);
- visible minefields;
- undetailed enemy-presence hexes without count, identity, owner, or strength;
- per-owned-unit supported commands, currently legal commands, conditional
  command sequences, bounded option values, ability state, cargo, inhibitor
  state and activation eligibility, and other public capability details;
- owned embedded agents, discovered hostile agents on friendly/allied hosts,
  bounded player-level sabotage/relocation options, and Intelligence/CI ship options;
- one deduplicated construction-template catalog;
- diplomatic message history grouped by partner faction in chronological order (`conversations`).

Observation schema 5 gives full body detail in systems containing friendly
units, adjacent systems, and systems with visible enemy activity. Remote systems
retain exact stars and colonized bodies while neutral objects are summarized.
The model can move toward a system navigation anchor to receive exact target IDs
on a later turn. Inhibitor blocker values are intentionally bounded and expose
no identity or geometry for the conflicting inhibition zone.

The observation intentionally excludes enemy resources and hidden entity IDs.
The command gateway independently recomputes visibility for enemy targets, so a
fabricated or remembered hidden ID cannot bypass fog of war.

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

Every campaign, player, and agent has a stable 8-character hexadecimal short ID. Save version 3.2 embeds:

- `campaign_id`;
- `persistent_id` and `agent_id`;
- selected `ai_reasoning_effort`;
- selected `ai_repair_retries`;
- bounded structured `ai_memory`.

Missing identities migrate automatically upon save loading. The save is
authoritative. The `memory.md` sidecar is generated for inspection and is not
read back into the campaign.

Memory contains strategy, objectives, commitments, beliefs, lessons, misc,
and recent execution receipts bounded to 8,000 total characters. Individual turn
receipts are retained whole, dropping the oldest turns in their entirety when the
total limit is exceeded. Text and list counts are bounded before serialization.
Save JSON and memory sidecars use atomic replacement.

## Commands

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
`mine`, `repair`, `attack`, `trade`) require only `target_id` (plus amount/component
if applicable); approach movement is automated, so coordinates (`position`, `hex_coord`,
`system_name`) must be null or omitted. Inhibitor toggles likewise project active dynamic
zones, so overlapping activations are rejected before commit and a preceding
deactivation can make a later activation legal. Replacing pending work releases only its reservations; it cannot undo a colonist load
that already completed synchronously. Environmental hazard constraints are also enforced: commanding strikecraft wings into magnetic storms, or launching wings from a carrier inside a magnetic storm, is rejected at preflight with `hazard_blocked`. Preserve queued prerequisites with `queue=true`. The complete batch remains atomic
at preflight.

Retrofit remains a human editor transaction because it requires a versioned
component-configuration schema and dynamic cost preview. It is not advertised to
the model.

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

## Shared order contract (observation 5 / commands 3 / socket 2)

`game_ai.command_spec.COMMAND_SPECS` defines fields, constraints, queue behavior,
capabilities and descriptions. It generates the strict OpenAI command schema and the
socket observation's deduplicated `command_catalog`. Socket commands may omit optional
fields; OpenAI output must include every schema field (unused fields are null).
Validation rejects unknown fields, coercible strings, boolean/fractional IDs, duplicate
units, non-finite coordinates, inappropriate parameters, and batches/groups above
40 commands / 12 units. Immediate commands require `queue=false`. The coordinator
validates the complete turn plan, including `end_turn=true`, before mutation, even for
injected providers. Model, reasoning, timeout and token budgets are unchanged.

Owned/allied units expose `standing_order`, `current_order` and `queued_orders`; the
legacy flattened `orders` array is removed. Types and statuses are readable strings.
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

Save 3.2 preserves order UUIDs recursively, history/counter, terminal-recording state and
job charges. Legacy orders get new UUIDs and empty histories. Restored active orders rebind
actuators/job ownership without replaying startup or refunds; pending orders start on a
subsequent update. Recursively docked units restore too; stance engagements are reacquired.
The strict response schema is `wormhole_control_turn_v3`, and prompt cache key is
`wormhole-control-turn-v4`. No live API call is required for regression testing.
