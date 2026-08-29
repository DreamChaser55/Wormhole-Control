---
name: wormhole-control
description: Play or control the Wormhole Control game through its localhost Codex JSON interface. Use when the user asks Codex to start, play, continue, observe, command, or take turns in Wormhole Control.
---

# Wormhole Control

Control the visible game from the repository root with `python game_control.py '<json>'`. Read [the protocol guide](../../../docs/CODEX_CONTROL.md) when exact action or command fields are needed.

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
5. Send 1–40 commands with `command`, the current token, and a fresh request ID. Successful batches accumulate without ending the turn. If validation rejects a batch, use its errors and the same still-active observation; none of that batch was applied.
6. Repeat `command` as needed, then send `end_turn` with the current token and a fresh request ID.
7. Continue with `wait_for_turn` until the user’s requested play session is complete.

For an uncertain transport result on `new_game`, `command`, or `end_turn`, retry the exact serialized request with the same request ID. Never reuse that ID for changed content. Parse only the single compact JSON line on stdout; diagnostics on stderr are not protocol data.
