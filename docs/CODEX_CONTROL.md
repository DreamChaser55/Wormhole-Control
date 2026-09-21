# Codex Control Protocol

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

The CLI adds `protocol_version: 3` and a random `request_id` when omitted. Supplying request IDs yourself is recommended for mutating actions so an identical request can be retried safely.

## Transport and process behavior

- Address: `127.0.0.1:47653` by default. The listener never binds to a non-loopback address.
- `ControlService(host=...)` rejects any host other than `127.0.0.1` with
  `ValueError` before creating a socket.
- Port: pass `--port PORT` to either script or set `WORMHOLE_CONTROL_PORT`. An explicit CLI flag wins.
- Framing: one UTF-8 JSON object followed by a newline, with one response per connection.
- Request limit: 1 MiB. Protocol responses may be larger because observations contain visible game state.
- Version: every direct socket request must contain `"protocol_version": 3`.
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
  "protocol_version": 3,
  "request_id": "stable-client-generated-id",
  "action": "status"
}
```

Every response contains the echoed protocol version, request ID, action, success flag, and a public state summary:

```json
{
  "service": "wormhole-control",
  "protocol_version": 3,
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
{"data":{"turn_token":"opaque-value","observation":{"schema_version":19}}}
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

Read `observation.command_catalog`: it contains command contract version 15, shared field
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

New campaigns share the wizard's [setup limits](REFERENCE.md#setup-limits) and
[validation contracts](DEVELOPMENT.md#campaign-setup-contracts). The control
interface additionally requires exactly one Codex player.

## Unit names and covert ships

Use `rename_unit` to change the displayed name of one owned unit without interrupting
orders or spending resources:

```json
{"type":"rename_unit","unit_ids":[42],"new_name":"Patrol Escort 7","queue":false}
```

Replace 42 with an observed owned ID. Names are trimmed, must contain 1–30 characters,
and cannot contain control characters. Duplicate names are allowed. Renaming remains
legal while submerged or equipment is damaged and persists through save/load.

The Covert Intelligence Ship is constructed under the safe name **Patrol Escort**,
matching an ordinary warship with identical visible equipment. Catalog entries expose
`default_unit_name` as the effective initial name. Optional later names should remain
generic; an already safe name requires no change. Enemy observations omit all three
order-layer fields and never expose design identity, actual hull usage, upkeep or
construction/refit details. These rules apply to all enemy units, preserving owners'
and allies' existing access. Observation schema is 12, command contract is 10, and the
socket envelope remains protocol 3.

## Attack range commands

`attack` approaches until every turret eligible to hit its target is in range.
`attack_long_range` requires functional Weapons and at least one eligible Long Range
variant turret, and approaches until all eligible Long Range turrets are in range.
All eligible turrets may fire within their own ranges under either order, and neither
order retreats. Select targets from the unit's command options; both support visible
enemy units and deployables and optional public subsystem targeting.

```json
{"type":"attack_long_range","unit_ids":[101],"target_id":102,"queue":false}
{"type":"attack_long_range","unit_ids":[101],"target_id":102,"target_component":"Weapons","queue":true}
```

These are separate examples; substitute observed IDs. Omit coordinates. Ineligible
units reject the whole command batch before any orders change. Later loss of all
eligible long-range turrets fails the order instead of switching to normal Attack.
The public order type is `attack_long_range`; queueing, cancellation and target
redaction follow the ordinary [order contract](#command-discovery-and-order-control).

## Tactical ability commands

Environmental resistance abilities use a separate immediate command:

```json
{"type":"toggle_ability","unit_ids":[101],"ability":"hazard_shielding","queue":false}
```

The other values are `radiation_hardening` and `antimatter_containment`. Select
exactly one owned unit; omit target fields. The command flips that equipped
resistance without replacing orders. Read `command_options.toggle_ability`,
`ability_states` and `environmental_resistances` for legality and state.
Upkeep is charged before environmental hazards each owner turn, even in safe
space; enabling checks the combined bill but does not reserve fuel. These toggles
cannot be issued through `use_ability` or `cancel_ability`.

Observation schema 19 and command contract 16 expose a deduplicated `ability_catalog`,
visible deployables/patches, public links and authorized per-unit readiness, costs,
targets and persistent deployment counts. Protocol version is 3. The strict
response name is `wormhole_control_turn_v13`; unused OpenAI command fields stay null.


```json
{"type":"use_ability","unit_ids":[101],"ability":"ghost_fleet","system_name":"Sol","hex_coord":[0,0],"position":[200,0]}
{"type":"use_ability","unit_ids":[101],"ability":"tractor_tether","target_id":102}
{"type":"use_ability","unit_ids":[101],"ability":"mine_clearing_sweep","system_name":"Sol","hex_coord":[0,0],"position":[900,0]}
{"type":"use_ability","unit_ids":[101],"ability":"guardian_link","target_id":102}
{"type":"use_ability","unit_ids":[101],"ability":"multiply_antimatter"}
{"type":"use_ability","unit_ids":[101],"ability":"nebula_catalyst","target_id":201,"system_name":"Sol","hex_coord":[0,0],"position":[200,0]}
{"type":"transfer_antimatter","unit_ids":[101],"target_id":102}
{"type":"take_antimatter","unit_ids":[101],"target_id":102,"queue":true}
{"type":"continuous_antimatter_transport","unit_ids":[101],"source_id":102,"target_id":103,"queue":false}
{"type":"continuous_antimatter_transport","unit_ids":[101],"source_id":102,"target_id":null}
{"type":"continuous_resupply","unit_ids":[101],"source_id":201,"target_id":103}
{"type":"continuous_resupply","unit_ids":[101],"source_id":201,"target_id":null}
{"type":"cancel_ability","unit_ids":[101],"ability":"guardian_link","queue":false}
```

These are separate command examples, not an executable batch; substitute IDs from
a fresh observation. Position casts require local range, while unit-targeted
casts and antimatter exchange approach automatically. Nebula Catalyst's `target_id` is a known nebula. Only active Tractor/Guardian links are cancellable. Ghost emitters persist indefinitely with one surviving emitter per deploying ship across the galaxy.

Transfer and Take need functional storage and a friendly/allied target. Take moves
the recipient; Transfer moves the donor. Exchange is limited to 25 AM per owner
turn within 200 units and ends on empty supply or full capacity.

Both continuous commands require `source_id`: a star/hydrogen nebula for
`continuous_resupply`, or a loading unit for `continuous_antimatter_transport`.
The transport command takes one mobile actor. Optional `target_id` pins an
owned/allied recipient; null or omission enables automatic delivery to nearest
reachable owned units galaxy-wide. Automatic routes visit multiple recipients per
load and return to their source to wait when no productive delivery remains.
They exclude their actor and loading source. A lost manual recipient fails; full
manual recipients cause waiting. Harvesters retain 60 AM, while transports reserve
buffered return fuel. Current orders expose configured mode/target separately from
`progress.active_destination_id`, plus phase, waiting reason and reserve. Source,
recipient and approach geometry are redacted when unavailable. See
[antimatter logistics](REFERENCE.md#antimatter-logistics) for route rules.

Multiply Antimatter pays 20 AM, then doubles friendly current fuel within 500 units, capped by storage. Empty tanks gain nothing. The caster and every recipient that gains fuel have independent 30-round deadlines; the recipient deadline is shared across casters. Pulses with no positive net generation are rejected. Read the projected gains and net AM in ability state. Immediate pulse gains can fund later commands in the same batch; queued pulses reserve only their cost, and future pickups/travel cannot finance an immediate cast. Unused strict-response fields, including `source_id`, remain null.

Preflight reserves queued cast costs and slots. Observe newly deployed emitter IDs before targeting them. See the [tactical ability overview](REFERENCE.md#deployment-and-link-abilities) for the other ability rules.

### Strikecraft production

`action_catalogs.wing_templates` discovers built-in wing designs by hull, including
Fighter, Bomber, Interceptor and Long Range Bomber Wings. Each entry exposes its
`wing_type` (`FIGHTER` or `BOMBER`), equipment, prices and effective weapon statistics.
Private player designs are excluded. Fighter-role wings target wings; bomber-role
wings target ships/stations and qualify for carrier Attack Run.

Use `set_wing_production` with exactly one owned carrier, a required `template_name`
from the catalogue, and `queue=false`. Optional `turret_type_override` and
`defense_type_override` use the same choices and pure customization as Construct.
Each command replaces the complete production configuration: omitted/null overrides
reset to the selected template's presets. Overrides change types without changing
variants, statistics, hull use, component HP, price, duration or names.

Selection is free, preserves orders and stance, and is allowed while idle or
replenishing, including when full or short of credits. It is blocked while building
or when the bay is destroyed. Automatic construction pays when it starts; settings
persist for subsequent builds. Existing wings and their replenishment are unchanged.
Invalid templates/equipment/overrides reject the complete batch before mutation;
commit rechecks availability. Multiple selections apply in array order.

Owner/allied `capability_details.strikecraft_bay` includes `production_template`,
`turret_type_override`, `defense_type_override`, progress, costs and production choices.
Owned command options list templates and nullable override choices. Enemy views gain
no production details. Save 4.15 / Strikecraft Bay schema 4 preserve selections and
in-progress builds without replaying payments. New bays start unselected:
`production_template`, `production_turns` and `production_credit_cost` are null.
Explicitly select a built-in design to permit construction on a subsequent bay
update. Enabling production alone cannot select a design; selection preserves the
independent pause state. Null `template_name` commands are rejected, so use the
production toggle to pause after selection. Docking and replenishment do not require
a production selection.

```json
{"type":"set_wing_production","unit_ids":[101],"template_name":"LONG_RANGE_BOMBER_WING","turret_type_override":"beam","defense_type_override":"armor","queue":false}
```


## Turn-start event summary

Every schema-15 observation ends with `turn_summary`: reporting rounds (`from_turn`
and `to_turn`), grouped event `entries`, net `economy` changes, and `omitted_count`.
Read this briefing before choosing orders. It covers the previous End Turn's
resolution and intervening activity through this turn's opening effects. It is
player-scoped and fixed for the entire turn; repeated observations do not consume
or regenerate it. Empty entries indicate no important events. Historical subject
IDs and sectors grant no authority to command currently hidden targets.

The same briefing appears in the human modal and built-in AI prompt. Conversation
history includes all messages received so far, including the current round. Existing
socket protocol 3 and command contract 16 remain unchanged; no acknowledgement
command is required from Codex.


## Planetary commands

Current observation schema is 12 and command contract is 10; socket protocol
remains 3. Discover target choices and blockers in per-unit `command_options` and
fortification choices in player-level options.

| Command | Fields beyond `type` |
|---|---|
| `recruit_troops` | One `unit_ids` entry, colony `target_id`, positive integer `amount`, `queue` |
| `bombard_planet` | One `unit_ids` entry, colony `target_id`, `queue` |
| `invade_planet` | One `unit_ids` entry, colony `target_id`, positive integer `amount`, `queue` |
| `upgrade_planetary_defenses` | Empty `unit_ids`, owned colony `target_id`, `queue=false` |

For example, replace the IDs with observed IDs:

```json
{"type":"recruit_troops","unit_ids":[42],"target_id":7,"amount":40,"queue":false}
{"type":"invade_planet","unit_ids":[42],"target_id":19,"amount":40,"queue":true}
```

Approach is automatic. Only End Turn resolves recruitment, bombardment and assault;
upgrades pay immediately, once per colony per round. The queue preserves recruited
troops as a prerequisite. Each ship acts at most once per round. Invasion previews
are estimates at arrival, and failed assaults require new orders. Preflight reserves
population, credits, cargo and action fuel, without assuming victories or future
income. Hidden and missing targets share `target_unavailable`.

Read `planetary_defenses` on exact colonies and `troop_cargo` on own/allied ships.
The [warfare reference](REFERENCE.md#planetary-warfare) covers range, costs,
casualties and capture. Save 4.15 preserves cargo, approach orders and invasion RNG;
reload does not repeat payments or rolls.

## Wormhole stabilization

Use `stabilize_wormhole` with one owned unit, `target_id` naming a disclosed
wormhole, and optional `queue` (default false). Example command:

```json
{"type":"stabilize_wormhole","unit_ids":[42],"target_id":17,"queue":false}
```

Observe command options before issuing: stations require local range; mobile
units approach automatically. Support begins at End Turn, costs 5 AM per owner
turn and makes both directions safe for everyone, including enemies. Fuel
shortages wait. Cancel the continuous root to release queued work. Observations
expose natural/effective stability and progress without hidden support identities.
See [complete rules](REFERENCE.md#wormhole-stabilization).


### Construction equipment overrides

Command contract 16 supports optional nullable `turret_type_override` and
`defense_type_override` on `construct` and `set_wing_production`, independently. Turret choices are
`mass_driver`, `beam`, `missile`; defense choices are `armor`, `shields`,
`point_defense`. Omission/null retains the template preset.

```json
{"type":"construct","unit_ids":[101],"template_name":"ARTILLERY_DREADNOUGHT","system_name":"Sol","hex_coord":[0,0],"position":[200,0],"turret_type_override":"beam","defense_type_override":"shields","queue":true}
```

All turrets keep their stats and variants. All defense strength moves into the
chosen defense, zeroing the others. Costs, hull usage, build time and upkeep stay
unchanged. Missing equipment rejects the override; a defense override requires
positive total strength. Non-null overrides on other commands are rejected.
Group commands use the same choices per builder. Construct choices survive queues and saves
and appear in owner/allied order parameters. Catalogue entries and names are unchanged.

Observation 19 includes public enemy `capability_details.weapons` and `.defenses`
only for detailed visible contacts. Use their actual equipment to choose counters:
Armor counters Mass Drivers, Shields counter Beams, and Point Defense counters
Missiles. Enemy orders, template identity, accounting and covert components remain
private. Wing production uses the same override choices for future builds; existing units are unchanged.

### Complete positional destinations

Construct, Move, positional Defend, Patrol waypoints, and position-targeted abilities
require `system_name`, integer `hex_coord: [q, r]`, and finite `position: [x, y]`.
Missing/null fields and nonexistent systems or sectors are rejected before commit.
Entity-targeted and self-centered commands retain their target-ID/no-location forms.
Local-only abilities still require the caster to be in the specified sector.

```json
{"type":"construct","unit_ids":[101],"template_name":"CRYSTAL_REFINERY_STATION","system_name":"Epsilon Eridani","hex_coord":[10,-4],"position":[-431.75,-557.65],"queue":false}
```

Destinations stay fixed across queues, approach, and saves. Once a build starts,
displacement out of sector or build range fails it and refunds its charge once.

## Unit dismantling

Contract 16 / observation 19 exposes the shared `dismantle_unit` order:

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
