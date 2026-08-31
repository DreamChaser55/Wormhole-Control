---
name: wormhole-control
description: Play or control the Wormhole Control game through its localhost Codex JSON interface. Use when the user asks Codex to start, play, continue, observe, command, or take turns in Wormhole Control.
---

# Wormhole Control

Control the visible game from the repository root with `python game_control.py '<json>'` (socket protocol 2). Discover command shapes from `observation.command_catalog` (contract 2), including required fields, defaults, limits and queue semantics. Read [the protocol guide](../../../docs/CODEX_CONTROL.md) for envelope and recovery details.

## Rules

- Treat the `observation` returned by `observe` or `wait_for_turn` as the only permitted source of game-state facts.
- If you are playing a serious game, do not inspect saves, logs, process memory, source-defined scenario data, or pixels to discover hidden state. If you are playtesting, you are allowed to inspect everything.
- Do not call the OpenAI API and do not request an API key. The Codex CLI bridge is the controller.
- Keep the GUI visible. If the sandbox asks to approve launching Python or connecting to localhost, explain the scoped action and request approval.
- Treat turn tokens as opaque and replace the stored token whenever a new observation returns one.

## Play loop

1. Send `status` with a unique request ID.
2. If no campaign exists and the user asked to start one, send `new_game` with 2–6 players, exactly one `codex` controller, and at least two teams. Otherwise, do not replace an active campaign.
3. When `state.codex_ready` is true, send `observe`. When another controller is active, send `wait_for_turn` with `timeout_seconds` from 1–600.
4. Reason only from the returned observation and choose commands using its visible IDs, capabilities, availability, and bounded options.
5. Send 1–40 commands (at most 12 unique owned units per command) with `command`, the current token, and a fresh request ID. Successful batches accumulate without ending the turn. A `failure_stage: preflight` rejection applies nothing; correct it using indexed errors. A `failure_stage: commit` failure may leave partial effects: inspect applied/failed/unattempted `operation_results`, then successfully observe again before issuing commands or ending the turn. Never replay a failed batch as a new intentional request.
6. Repeat `command` as needed, then send `end_turn` with the current token and a fresh request ID.
7. Continue with `wait_for_turn` until the user’s requested play session is complete.

For an uncertain transport result on `new_game`, `command`, or `end_turn`, retry the exact serialized request with the same request ID. Never reuse that ID for changed content. Parse only the single compact JSON line on stdout; diagnostics on stderr are not protocol data.

The running service caches its last 256 mutation responses, including failures. After a restart or cache eviction, observe and reconcile uncertain effects rather than assuming an old request ID remains safe to retry.

## Stances and orders

Observation schema 4 separates `standing_order`, `current_order`, and `queued_orders`; do not expect the old `orders` array. Preserve useful work. Explicit work, including Move, suspends stance combat; changing stance preserves that work. `clear_explicit_orders` retains stance, while `cancel_orders` is full Stop and selects Do Nothing. `cancel_order` cancels one observed explicit root using its opaque UUID `order_id`; internal suborders and stance roots cannot be individually cancelled.

Create patrols with 1–16 complete `waypoints`, or the single destination shorthand. A patrol traverses its route, returns to its captured starting position, and repeats. `queue=true` creates a separate patrol and never extends a route. Use `append_patrol_waypoints` with an existing patrol's UUID to extend it without interrupting the active leg. Continuous roots can block later queue entries until cancelled; the observation reports this as guidance.

Hardware support differs from current legality: legal commands can be issued now but may still fail during execution. Consult tactical ranges and visible target options. Do not guess hidden subsystem names. Command receipts confirm issuance; `order_history` records actual completed/failed/cancelled outcomes with event IDs and retention metadata. Use those IDs to avoid treating repeated observations as new events.
