# Codex Control Protocol v2

Wormhole Control exposes a loopback-only JSON service so Codex can play one visible GUI campaign without calling the OpenAI API. The game remains authoritative: socket workers parse and queue requests, while `Game.update()` performs every read and mutation on the Pygame thread.

## Quick start

Run commands from the repository root. `game_control.py` connects to an existing game or launches `game.py` with the same Python interpreter, waits up to 15 seconds, and retries the request.

```powershell
python .\game_control.py '{"action":"status"}'
```

For requests that are inconvenient to quote, pipe one JSON object through stdin:

```powershell
@'
{
  "action": "new_game",
  "request_id": "campaign-2026-08-29",
  "settings": {
    "players": [
      {"name": "Codex", "controller": "codex", "team_id": 1},
      {"name": "Rival", "controller": "openai", "team_id": 2,
       "ai_reasoning_effort": "medium", "ai_repair_retries": 2}
    ]
  }
}
'@ | python .\game_control.py -
```

The CLI adds `protocol_version: 2` and a random `request_id` when omitted. Supplying request IDs yourself is recommended for mutating actions so an identical request can be retried safely.

## Transport and process behavior

- Address: `127.0.0.1:47653` by default. The listener never binds to a non-loopback address.
- Port: pass `--port PORT` to either script or set `WORMHOLE_CONTROL_PORT`. An explicit CLI flag wins.
- Framing: one UTF-8 JSON object followed by a newline, with one response per connection.
- Request limit: 1 MiB. Protocol responses may be larger because observations contain visible game state.
- Version: every direct socket request must contain `"protocol_version": 2`.
- Shutdown: exiting the GUI closes the listener and resolves pending requests with `server_stopping`.

`game_control.py` writes exactly one compact JSON response to stdout. Launch and error diagnostics go to stderr. Its exit statuses are:

| Exit | Meaning |
|---:|---|
| `0` | The game accepted the request (`ok: true`). |
| `1` | The game or protocol rejected it (`ok: false`). |
| `2` | CLI input, launch, handshake, timeout, or transport failure. |

Use `--no-launch` when a missing listener should be reported instead of starting the GUI.

## Common envelope

Request:

```json
{
  "protocol_version": 2,
  "request_id": "stable-client-generated-id",
  "action": "status"
}
```

Every response contains the echoed protocol version, request ID, action, success flag, and a public state summary:

```json
{
  "service": "wormhole-control",
  "protocol_version": 2,
  "request_id": "stable-client-generated-id",
  "action": "status",
  "ok": true,
  "state": {
    "game_started": true,
    "view_mode": "galaxy",
    "campaign_id": "a1b2c3d4",
    "turn_number": 1,
    "current_player": {
      "id": 0,
      "name": "Codex",
      "team_id": 1,
      "controller": "codex"
    },
    "codex_ready": true
  },
  "data": {}
}
```

Rejected requests set `ok` to `false` and add:

```json
{"error":{"code":"stale_turn_token","message":"The turn token is missing or stale."}}
```

Malformed socket input is queued back to the Pygame thread before its error response is built, so it also receives the public state summary without allowing socket workers to read live game state.

## Actions

### `status`

Returns the common public state. It is also the handshake used by the CLI to distinguish this service from another process using the same port.

```json
{"action":"status"}
```

### `new_game`

Creates a campaign only while the GUI is at the main menu. `settings.players` must contain 2–6 players, exactly one `codex` controller, and at least two distinct positive `team_id` values.

Each player requires `name`, `controller`, and `team_id`. Optional fields are `color` (three RGB integers), and—for `openai` controllers only—`ai_reasoning_effort` (`low`, `medium`, or `high`) and `ai_repair_retries` (1–5). Controller values are `human`, `openai`, and `codex`.

Optional galaxy/economy fields use `GameSettings` defaults when absent:

```json
{
  "action": "new_game",
  "request_id": "new-game-001",
  "settings": {
    "players": [
      {"name":"Codex","controller":"codex","team_id":1,"color":[30,120,255]},
      {"name":"Adversary","controller":"openai","team_id":2,"color":[220,40,40],
       "ai_reasoning_effort":"high","ai_repair_retries":3}
    ],
    "num_systems": 15,
    "min_system_distance": 50,
    "max_system_distance": 350,
    "wormhole_density": 0.3333333333,
    "system_radius_min": 6,
    "system_radius_max": 10,
    "starting_credits": 20000,
    "starting_metal": 10000,
    "starting_crystal": 10000,
    "starting_population": 50
  }
}
```

Unknown setup or player fields are rejected. An active campaign is never replaced.

### `observe`

Requires the active player to be controlled by Codex. It returns a new opaque turn token when the active turn changes, plus the existing fog-of-war-safe observation used by built-in AI players.

```json
{"action":"observe","request_id":"observe-001"}
```

```json
{"data":{"turn_token":"opaque-value","observation":{"schema_version":5}}}
```

Treat the observation as the only permitted source of game facts. Never infer hidden targets from saves, source files, logs, rendered pixels, or previous campaigns. IDs and available options in an old observation may be stale.

### `command`

Requires the current `turn_token` and 1–40 command objects accepted by the existing command gateway. The full batch is preflighted atomically. A validation failure applies none of it and leaves the Codex turn active. A successful call does not end the turn, so several calls may build the turn incrementally.

```json
{
  "action": "command",
  "request_id": "turn-1-orders-a",
  "turn_token": "opaque-value",
  "commands": [
    {"type":"move","unit_ids":[17],"system_name":"Sol","hex_coord":[1,0],"position":[0,0]},
    {"type":"set_stance","unit_ids":[17],"stance":"attack_weapon_range"}
  ]
}
```

On success, `data` contains `accepted`, `applied_count`, `receipts`, `operation_results`,
`failure_stage: null`, `retryable: false`, `may_have_partial_effects: false`,
`requires_observation: false`, and the unchanged token. Preflight rejection has
`failure_stage: "preflight"`, indexed errors in `error.details`, and zero applied operations.
Unexpected commit failure has `failure_stage: "commit"`, `retryable: false`, retained
successful receipts, and applied/failed/unattempted operation results. `applied_count`
counts successfully completed operations; the failing operation may itself have mutated
state. Its effects are marked uncertain. The previous mutation token is invalidated,
`turn_token` is null, and a successful fresh observation is required before another
command or socket end-turn. No rollback or automatic semantic retry is performed. Supported command shapes and visible option lists are carried in each observation; see [Agentic AI Architecture](AGENTIC_AI.md) for additional command-gateway context.

### `end_turn`

Requires the current token. It processes all accumulated orders and advances to the next player.

```json
{"action":"end_turn","request_id":"turn-1-end","turn_token":"opaque-value"}
```

The End Turn button remains available in the GUI during a Codex turn. If it is clicked manually, any prior token becomes stale.

### `wait_for_turn`

Waits between 1 and 600 seconds for the Codex player. It returns immediately if Codex is already active, otherwise it holds that connection without blocking the Pygame loop.

```json
{"action":"wait_for_turn","request_id":"wait-002","timeout_seconds":120}
```

When ready, `data` contains `ready: true`, an observation, and the current token. A normal timeout is a successful response with `data.ready: false`.

## Idempotent retries

The server caches the last 256 responses to mutating actions (`new_game`, `command`, and `end_turn`). Retrying the exact same JSON payload with the same non-empty `request_id` returns the cached response without applying it again. Reusing that ID for different JSON returns `request_id_conflict`.

Keep the same request ID only when recovering from an uncertain transport result. Use a fresh ID for each intentional mutation, including each incremental command batch.

## Errors

Common codes include:

| Code | Cause |
|---|---|
| `unsupported_protocol`, `unknown_action` | Invalid envelope or protocol version. |
| `request_id_required`, `request_id_conflict` | Missing mutating ID or unsafe ID reuse. |
| `game_not_started`, `campaign_active` | Action conflicts with campaign lifecycle. |
| `not_codex_turn`, `no_codex_player` | Codex cannot act or wait in the current campaign state. |
| `stale_turn_token` | Missing token, advanced turn, reload, or manual End Turn. Observe again when ready. |
| `invalid_settings`, `invalid_players`, `invalid_codex_count`, `invalid_teams` | New-game schema or bounds violation. |
| `invalid_commands`, `invalid_command_contract`, `commands_rejected` | Batch shape or game-rule validation failure. |
| `invalid_timeout` | Wait duration is outside 1–600 seconds. |
| `request_too_large`, `invalid_json` | Socket framing or request-size error. |
| `server_stopping`, `server_timeout`, `internal_error` | Lifecycle or unexpected processing failure. |

## Codex sandbox permissions

The normal control command starts a visible local GUI process and connects to a localhost socket. A restricted Codex environment may ask the user to approve those actions. Request approval for the specific Python launch/control command and port; do not disable the sandbox, bind a public interface, inspect saves to recover game state, or substitute an OpenAI API key. The controller itself makes no OpenAI API call and requires no API key.

## Command discovery and order control

Read `observation.command_catalog`: it contains command contract version 3, shared field
schemas, required fields, defaults, group/batch limits, capability requirements, and queue
semantics. Do not inspect implementation code to discover commands. Sparse commands default
`queue` to false; optional unused fields must be absent or null. Strings such as `"false"`,
unknown fields, duplicate/boolean/fractional IDs and non-finite coordinates are rejected.
Old protocol versions are rejected with an explicit client-upgrade error.

Read `observation.intelligence` for controllable owned agents and discovered hostile agents,
and `observation.player_commands` for legal player-level `sabotage` and `relocate_agent`
options. These two commands use `unit_ids: []`, execute immediately, require `queue: false`,
and never disturb ship orders. Allied agents can extend sensor vision but are not identified
or controllable. Intelligence and CI ship command options list only currently actionable
infiltration, extraction, sweep, and elimination choices.

Friendly units separate `standing_order`, `current_order` and `queued_orders`. The old
`orders` array is gone. Use public UUID `order_id` values for editing, not internal integers.
Explicit work suspends stance combat, including explicit Move. Changing stance preserves
work. `cancel_orders` is full Stop; `clear_explicit_orders` preserves the selected stance.
Continuous orders can block later queue entries until cancelled. Receipts confirm issuance;
`order_history` supplies bounded, persistent terminal outcomes with retention metadata.

Example command objects (wrap in a `command` request with a fresh request ID and token):

```json
{"type":"patrol","unit_ids":[17],"waypoints":[
  {"system_name":"Sol","hex_coord":[0,0],"position":[500,0]},
  {"system_name":"Sol","hex_coord":[0,1],"position":[100,200]}
]}
```

```json
{"type":"append_patrol_waypoints","unit_ids":[17],"order_id":"observed-public-uuid","waypoints":[
  {"system_name":"Sol","hex_coord":[0,1],"position":[400,200]}
]}
```

```json
{"type":"cancel_order","unit_ids":[17],"order_id":"observed-public-uuid"}
```

```json
{"type":"clear_explicit_orders","unit_ids":[17]}
```

```json
{"type":"infiltrate_unit","unit_ids":[17],"target_id":42}
```

```json
{"type":"infiltrate_planet","unit_ids":[17],"target_id":73}
```

```json
{"type":"sabotage","unit_ids":[],"agent_id":9,"sabotage_type":"engines","queue":false}
```

```json
{"type":"relocate_agent","unit_ids":[],"agent_id":9,"target_id":43,"queue":false}
```

```json
{"type":"extract_agent","unit_ids":[17],"agent_id":9}
```

```json
{"type":"ci_sweep","unit_ids":[21],"queue":false}
```

```json
{"type":"eliminate_agent","unit_ids":[21],"agent_id":12}
```

Patrol routes accept 1–16 waypoints or a single complete destination triplet. They return to
the position captured when the patrol starts and repeat. Appending preserves the current
leg. `queue=true` always creates another explicit root. Internal/stance orders cannot be
cancelled individually. `order_unavailable` means the order is no longer editable for that
owned unit; observe current roots rather than guessing identities.

## Recovery distinctions

- **Preflight/output rejection:** no command effects occurred. Correct the plan using the
  indexed errors and submit a new intentional request ID. The token remains valid.
- **Partial commit failure:** earlier successful operations remain applied, the failed
  operation may have uncertain effects, and later operations were not attempted. Observe
  successfully before another mutation or end-turn (`observation_required` otherwise).
- **Uncertain transport outcome:** replay the identical payload with its original request
  ID; never retry changed content under that ID. Cached failure responses are replayed too.
  Cache retention is the last 256 mutation responses in this running service; after restart
  or eviction, observe/reconcile before attempting an uncertain action again.
