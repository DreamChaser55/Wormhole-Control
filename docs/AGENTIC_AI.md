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
6. Accepted orders are committed on the Pygame thread. A rejected batch gets
   one semantic repair request; a second rejection becomes a recoverable UI
   error.
7. The memory patch and execution receipts are bounded, persisted, and the turn
   ends.

No API call is made for a human player. Tests and evaluation use injected fake
providers by default, so they do not consume API credits.

## Information boundary

`game_ai.observation.build_observation` recomputes visibility for the active
player. It includes:

- the active player's economy;
- public system topology and celestial bodies;
- owned and allied units;
- enemy units only when detailed visibility permits them;
- visible minefields;
- undetailed enemy-presence hexes without count, identity, owner, or strength;
- per-owned-unit legal actions, ability state, stances, cargo, construction
  choices, and other public capability details.

The observation intentionally excludes enemy resources and hidden entity IDs.
The command gateway independently recomputes visibility for enemy targets, so a
fabricated or remembered hidden ID cannot bypass fog of war.

## OpenAI adapter

The adapter uses the current Responses API and strict `text.format` JSON Schema.
It does not enable model tools and does not chain response IDs. Each turn is
self-contained from the observation plus canonical memory.

Profiles are defined in `game_ai/profiles.py`:

| Profile | Model | Reasoning | Intended use |
|---|---|---|---|
| Fast | `gpt-5.6-luna` | low | inexpensive, high-volume play |
| Balanced | `gpt-5.6-terra` | medium | default quality/cost tradeoff |
| Strategic | `gpt-5.6-sol` | high | strongest long-horizon planning |

The API key loader checks `OPENAI_API_KEY` first, then
`API_keys/OpenAI.key`. The key is loaded lazily when the first AI turn begins.

## Memory and persistence

Every campaign, player, and agent has a stable UUID. Save version 2 embeds:

- `campaign_id`;
- `persistent_id` and `agent_id`;
- selected `ai_profile`;
- bounded structured `ai_memory`.

Older saves migrate automatically by generating missing identities. The save is
authoritative. The `memory.md` sidecar is generated for inspection and is not
read back into the campaign.

Memory contains strategy, objectives, commitments, beliefs, lessons, and the
twenty most recent execution receipts. Text and list counts are bounded before
serialization. Save JSON and memory sidecars use atomic replacement.

## Commands

The strict contract currently supports movement, patrol, combat, protection,
colonization, colonist loading, construction, repair, mining, continuous
mining, unloading, docking and carrier deployment, antimatter transfer/resupply, minefields, trade,
continuous trade, stances, inhibitor/cloaking toggles, and abilities.

Retrofit remains a human editor transaction because it requires a versioned
component-configuration schema and dynamic cost preview. Intelligence agent
operations likewise remain on the engine/UI path until their hidden-information
contract is separated from UI discovery state. Neither is advertised to the
model.

## Failure behavior

- SDK retries transient transport failures up to two times.
- Invalid command batches receive one model repair attempt.
- Stale responses are discarded when campaign, agent, or turn changes.
- On final failure, the error is shown and End Turn is re-enabled.
- The API key and prompt contents are never logged.
- Token counts, latency, model, response ID, and command outcomes are appended
  to ignored `saves/ai_telemetry.jsonl`.

## Evaluation

`game_ai.evaluation` defines provider-independent fixture cases and scores:

- schema/turn completion;
- required and forbidden command coverage;
- command budgets;
- latency;
- input/output token use.

Inject `FakePlanningProvider` for deterministic CI. Live model comparisons are
explicitly opt-in by constructing `OpenAIResponsesProvider`. Keep fixed
observations, seeds, model snapshots, and game balance constants with any
published result so regressions can be reproduced.
