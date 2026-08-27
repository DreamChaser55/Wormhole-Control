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
- public system topology, navigation anchors, detailed nearby bodies, and
  summaries of remote neutral bodies;
- owned and allied units;
- enemy units only when detailed visibility permits them;
- visible minefields;
- undetailed enemy-presence hexes without count, identity, owner, or strength;
- per-owned-unit supported commands, currently legal commands, conditional
  command sequences, bounded option values, ability state, cargo, inhibitor
  state and activation eligibility, and other public capability details;
- one deduplicated construction-template catalog;
- incoming messages transmitted by other players during previous turns (`incoming_messages`).

Observation schema 3 gives full body detail in systems containing friendly
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

Every campaign, player, and agent has a stable UUID. Save version 2.2 embeds:

- `campaign_id`;
- `persistent_id` and `agent_id`;
- selected `ai_reasoning_effort`;
- selected `ai_repair_retries`;
- bounded structured `ai_memory`.

Missing identities migrate automatically upon save loading. The save is
authoritative. The `memory.md` sidecar is generated for inspection and is not
read back into the campaign.

Memory contains strategy, objectives, commitments, beliefs, lessons, misc,
and the twenty most recent execution receipts. Text and list counts are bounded
before serialization. Save JSON and memory sidecars use atomic replacement.

## Commands

The strict contract currently supports movement, patrol, combat (with optional
subsystem targeting via `target_component`), positional defense (`defend`), protection,
colonization, colonist loading, construction, repair, mining, continuous
mining, unloading, docking and carrier deployment, antimatter transfer/resupply, minefields, trade,
continuous trade, stances, inhibitor/cloaking toggles, diplomatic communications (`send_message`), and abilities.

The observation and gateway share side-effect-free legality rules. The gateway
also projects guaranteed effects through a batch, allowing a valid
`load_colonists` command to satisfy a later `colonize` command for the same unit
when colonization is queued. Inhibitor toggles likewise project active dynamic
zones, so overlapping activations are rejected before commit and a preceding
deactivation can make a later activation legal. A replacing command does not
retain a projected colonization prerequisite. The complete batch remains atomic
at preflight.

Retrofit remains a human editor transaction because it requires a versioned
component-configuration schema and dynamic cost preview. Intelligence agent
operations likewise remain on the engine/UI path until their hidden-information
contract is separated from UI discovery state. Neither is advertised to the
model.

## Failure behavior

- SDK retries transient transport failures up to two times.
- Invalid command batches and malformed model outputs receive 1–5 semantic
  repair retries, configured per AI player from the in-game **AI Settings**
  dialog and defaulting to 2. The initial submission is not counted as a retry.
- Each semantic repair is a complete replacement response made with the
  player's selected reasoning effort. The retry budget is not sent to the
  model.
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
