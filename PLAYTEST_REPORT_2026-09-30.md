# Wormhole Control playtest — 30 September 2026

## Session and method

Read `README.md`, `docs/REFERENCE.md`, `docs/DEVELOPMENT.md`, and
`docs/AGENTIC_AI.md`, plus the repository control skill and `docs/CODEX_CONTROL.md`.
Played the visible application through the `game_control.py` CLI. A small adaptive
driver invoked that CLI as a subprocess; it did not mutate live Python objects or
substitute a fake planning provider. All gameplay requests and responses were
recorded. Logs, telemetry, memory sidecars and implementation code were inspected
to investigate findings, as authorized for this playtest.

Configuration:

- Campaign `8237e193`; AI agent `e29226a1`.
- Seed `9302026`; Testing profile; two radius-3 systems; wormhole density 1.
- Playtester: Codex controller, team 1. AI Rival: built-in OpenAI controller,
  Low reasoning, two semantic repair retries.
- Each player started with 100,000 credits, 10,000 metal, 5,000 crystal and the
  Testing fleet. This exercises features sooner but does not measure Normal
  opening balance or ordinary resource scarcity.
- Local socket protocol 4; observation 28; command contract 23.
- The default port had an incompatible pre-existing service. This checkout was
  launched on `127.0.0.1:47654`, leaving that session untouched.
- `python` was absent from PATH; `.venv/Scripts/python.exe game_control.py` worked.

## Findings requiring fixes

### F1 — P1: enemy current antimatter leaks through observations

**Observed:** detailed enemy views include exact current and maximum antimatter.
Enemy Titan 48 exposed 1,850/2,000 at round 2, 1,131.76/2,000 at round 30, and
1,488.29/2,000 at round 52. These values came directly from ordinary Codex
observations, not privileged log inspection.

**Expected:** `docs/AGENTIC_AI.md` explicitly says enemy fuel availability is
private and checked at execution. Revealing current fuel permits opponents to
time attacks, fuel-draining abilities and travel interception using private state.

**Cause:** `_unit_view` in `game_ai/observation.py` serializes `antimatter`
unconditionally before its self/ally and enemy branches.

**Recommendation:** omit enemy current fuel from the shared observation. Decide
separately whether public equipment policy allows disclosing tank capacity. Add
an information-boundary regression check for both socket and built-in provider
observations, including damaged tanks and changing fuel.

Other sampled enemy private fields—explicit/standing orders, troop cargo, wing
service state and template identity—were absent. This finding does not establish
that every other information boundary is correct.

### F2 — P2: gas-giant orders redact a disclosed celestial target and journey

**Reproduction:** order ship 25 to `enter_gas_giant` at disclosed Planet 2. During
its approach, inspect an observation that also contains Planet 2 in Tau Ceti.
The root and its approach children show `target_id: null`,
`target_visibility: unavailable`, empty parameters and no journey progress.
This persisted across several rounds and through save/reload. Even the completed
entry at round 61 still reported the target unavailable, while
`hidden_in_gas_giant_id` correctly identified Planet 2.

**Cause:** `EnterGasGiantOrder.target_fields` in `unit_orders/gas_giant.py` declares
`target_id` as kind `unit`. `game_ai/order_view.py` consequently checks the planet
against visible unit IDs and recursively redacts its geometry.

**Impact:** controllers cannot distinguish a healthy long approach from missing
target information or a stalled mission. Execution itself succeeded: the original
entry and queued exit both completed at owner resolution 50.

**Recommendation:** declare the target as `celestial`, ensure the generated Move
approach uses the same reference kind, and verify disclosed/undisclosed target
serialization and save round-trips.

### F3 — P2: impossible inter-system mining is advertised and accepted

**Reproduction:** Small Mining Ship 69 was in Tau Ceti, with a functioning Basic
Hyperdrive, full fuel and no cargo. Its `mine` and `continuous_mine` options
advertised asteroid IDs 17 and 20, both in Proxima Centauri. Issuing `mine` against
17 returned success. Resolution failed with `path_unavailable`, leaving no active
order. Repeating the same legal option reproduced the failure in subsequent
rounds. The Basic drive cannot traverse the connection.

**Cause:** `command_guidance` in `game_ai/rules.py` builds mining targets from all
exact mineable bodies without per-actor route filtering. The mining command path
in `game_ai/commands.py` accepts the target without rejecting this known drive
limitation before constructing the order.

**Impact:** a controller following advertised options can repeatedly spend its
turn on an impossible mission. There are no mining resources in this seed's home
system, which makes the misleading options especially consequential.

Acceptance is documented as distinct from guaranteed completion; changed hazards
or lost capabilities can legitimately cause later failure. This case is a known,
unchanged equipment/topology blocker, rather than a later change.

**Recommendation:** filter targets using known route feasibility, or advertise
target-specific blockers. Reject deterministically impossible approaches during
preflight while preserving the existing orders. Apply the same audit to other
entity-targeted utility commands.

### F4 — P3: generated gas-giant rule contradicts the detailed reference

The observation's Planet 2 `environmental_rules` says "Tiny through Huge ships"
can enter an atmosphere. The detailed atmospheric-hiding section in
`docs/REFERENCE.md` says Tiny through Titan. The earlier body-description excerpt
there also says Tiny through Huge. The current shared eligibility should determine
one canonical description. Titan atmosphere entry was not executed in this run;
this is a confirmed documentation inconsistency, not a claim about its resolution.

### F5 — P2: the shared game log was truncated and became sparse/binary

During the live session, `game.log` acquired a fresh startup preamble timestamped
22:38:29, followed by a large NUL-filled gap, despite campaign `8237e193` continuing
without a transport failure or restart in the recorded control requests. One
inspection measured 5,147,714 bytes, of which 4,013,702 were NUL bytes; the first
NUL was at byte offset 719. `rg` consequently treated it as a binary file.

`game_logging.configure_logging` opens the common relative `game.log` with
`mode='w'`. A second writer opening/truncating that path while an older writer
retains its file offset can produce exactly this result. A pre-existing game
service and other campaign telemetry were present; the exact process responsible
for this later truncation was not identified. Concurrent-writer attribution is an
inference, while the missing/binary log content is directly observed.

To prevent these issues, limit the game service to one running process only. When the service is launched, detecting any preexisting running process should result in an error.

## AI behavior and interface improvements

### Improve wing-production guidance and model reliability

At round 3 the AI submitted four invalid bay slot indices. All four commands were
rejected atomically; a semantic repair succeeded and memory recorded the carrier's
four-slot limit. At round 4 an output omitted `slot_index`; contract validation
rejected it and repair succeeded. At round 30 a target ability was out of range;
repair removed it and preserved valid wing attacks.

The validation/recovery boundary worked. Improve the prompt's small, concrete
wing-production examples and emphasize actor-specific `slot_indices` rather than
inferring indices from another carrier. Keep required-field guidance adjacent to
each command. Add these actual mistakes to provider evaluation fixtures. Treat
repeated repairs as a measured model-quality/cost concern, not an engine crash.

### Make travel and ability blockers easier to interpret

A one-sector colony mission involved loading, leaving a planetary inhibition
field, jumping and approaching the next body. The Huge ship's colony approach
estimated another 41 owner turns at round 17; it was destroyed at round 26 before
arrival. The scout's original gas-giant entry took until resolution 50. The
inter-system exploration trip also took many tens of owner turns.

These timings follow the large tactical distances and slow Testing engines.
Evaluate pacing separately on Normal settings before changing balance. Improve
briefing/sidebar emphasis on egress, recharge, fuel waits and approximate total
mission duration. Ability states sometimes report `capability_unavailable` while
showing an intact ability with a positive cooldown; a specific cooldown blocker
would be clearer.

### Preserve progress and separate acceptance from completion

The AI generally preserved its long colony and infiltration missions during
quiet turns and issued zero-command plans when there was no useful change. It
reacted to contact loss and recorded constraints in memory. Early attacks and
intelligence orders sometimes replaced one another; compare remaining journey
time and mission value before replacement. A controller should also consult
terminal `order_history` before reissuing a previously failed option—the mining
probe illustrates the loop that otherwise results.

Keep issuance receipts, terminal results and historical briefings distinct. The
current event IDs and cancellation reasons are useful and should remain stable.

### Deduplicate durable lessons by meaning and retain specific constraints

By round 81, the AI's 16 retained lessons contained many near-duplicates of
"preserve useful orders" and "use currently visible legal targets." The early
concrete carrier slot-count and required-slot-index lessons were no longer in that
window. Exact-text distinctness does not prevent paraphrased generic advice from
displacing useful constraints. Prefer structured error/command keys, merging
equivalent advice and preserving specific learned blockers. This is observed
memory-quality degradation; it does not prove that eviction caused a later error.

## Checks that worked

- The CLI launched this checkout's GUI and connected on the alternate local port.
- Multi-command issuance, sparse optional fields, queued construction and
  load-then-colonize orders were accepted.
- Patrol extension preserved the existing root; individual cancellation worked.
- Renaming preserved ordinary unit state.
- A batch containing a valid rename followed by an incomplete Move rejected
  atomically; the original name remained unchanged.
- Unknown target IDs returned `target_unavailable`; stale turn tokens rejected.
- Omitting the wing template rejected with guidance to explicitly supply it or
  null. An unarmed shipyard rejected even `do_nothing` stance changes.
- Identical serialized mutation/request-ID replay returned the same cached
  response. Changed commands under the same request ID rejected with
  `request_id_conflict`.
- At round 61, a 20-Battleship queued batch exceeded the projected budget and
  rejected with indexed `insufficient_resources` errors; no partial batch was
  applied.
- Save at round 31, explicit return to menu and load succeeded. Resources, unit
  IDs, systems, intelligence, conversations, order history and the frozen turn
  summary matched before/after. The expected Testing-catalogue removal on load
  did not prevent existing normal-design builds from continuing.
- Enemy contact loss cancelled attacks with `target_not_visible`, recorded once
  in terminal history and reported in the briefing.
- Wing production, launch, override selection, combat losses and replacement
  production ran. An attempted damaged-wing recall was interrupted by destruction;
  that is not evidence of successful replenishment.
- In the closing checks, Evasive Formation and Emergency Recovery were accepted;
  recovery completed for wing 80, reset its outside counter to zero and exposed
  its service-ready round. Production pause and explicit-null slot clearing/restoring
  also worked. A 41-command batch and a 13-unit group rejected before mutation.
- Docked bomber 82 was dismantled successfully in resolution 103, returning
  129.5 credits, 5.5 metal and 2 crystal. The receipt/history and following
  briefing reported completion and salvage. Production remained paused.
- The separate queued Siege Lance charged in resolution 103 and impacted rival
  Titan 48 in resolution 104, recording 437 hull damage in the next briefing.
  Flak Barrage also produced hits against enemy wings.
- Deep Scan revealed contacts and expired; antimatter multiplication and Aegis
  executed. Rival Siege Lance charged and dealt its subsequent impact, killing
  the original Huge colony ship. Combat and losses appeared in later briefings.
- Automatic resupply began its source approach; this is distinct from proof of a
  completed delivery.
- Gas-giant entry and queued departure completed. A fresh entry exposed hidden
  state; issuing an unrelated Move while already submerged rejected, and Leave
  remained available.
- AI semantic repair preserved the match and wrote accepted memory/receipts.

The initial closing Siege Lance was intentionally followed by a replacing Flak
Barrage order, so its cancellation is a controller sequencing outcome, not failed
Titan execution. A separate queued cast was used for the final impact check.

## Environment and evidence limitations

Startup logged permission-denied warnings for preferences and custom designs in
`%LOCALAPPDATA%/WormholeControl`. This execution environment restricts those paths.
The built-in/Testing catalogue and game ran. Do not classify these warnings as a
gameplay regression; use an isolated writable `WORMHOLE_USER_DATA_DIR` for future
controlled runs.

This was an interface-driven visible-GUI playtest, not a pixel/layout or manual
mouse-and-keyboard audit. It did not comprehensively test every ability, team
cooperation, private designs/refits, trade, arbitrary map seeds or every recovery
failure category. Negative preflight probes were deliberate. No commit failure or
provider transport failure was artificially injected into this live match.

Raw local evidence is in `.cache/playtest_20260930/requests.jsonl`,
`protocol_probes.jsonl`, `reload_comparison.json` and observation snapshots.
AI attempts can be isolated in `saves/ai_telemetry.jsonl` by campaign `8237e193`;
memory is `saves/agent_memory/8237e193/e29226a1/memory.md`.
These cache/save paths are ignored artifacts, not tracked report dependencies.
Only this campaign's telemetry is used for measurements; other campaign records
exist in the same telemetry file.

## Final session results

Completed **104 global rounds**: 100 main playtest rounds and four closing-check
rounds, with **104 Codex and 104 built-in AI owner-turn resolutions**. Stopped at
the beginning of Codex round 105. The application remains running on port 47654,
ready for inspection. Saved to `saves/playtest_20260930_final_round105.json`;
the earlier checkpoint is `saves/playtest_20260930_round31.json`.

Tested revision: `9ae3111853d930ee06bdfc252f9f9a539152325c`. No gameplay source
changes were made. The control strategy emphasized coverage and probes rather
than optimal competitive play; some early movement/cast orders were deliberately
or inadvertently replaced while testing queue behavior. Combat losses and the
small hazardous map restricted how much economy expansion could complete.

| Measurement | Recorded result |
| --- | --- |
| AI accepted plans | 104, covering every round 1–104 |
| AI attempts | 113 |
| Repaired planning failures | 8 preflight rejections; 1 invalid-output rejection |
| Final AI failure / manual retry or skip | None |
| Commit failure / observed transport failure | None in the campaign archive |
| Provider attempt latency | Median 7.700 s; maximum 26.639 s |
| Recorded input tokens | 9,103,142 |
| Cached / uncached input tokens | 3,954,847 / 5,148,295 |
| Recorded output tokens | 77,842 |
| Recorded CLI actions | 359, plus 3 separate request-ID replay/conflict probes |
| Observation samples | 120 |
| Requested command types | 25; includes deliberate rejected probes |
| Distinct personal terminal history events | 105: 58 completed, 33 cancelled, 14 failed |
| Final treasury | 67,716.029354897 credits; 10,061.5 metal; 4,750 crystal |
| Final disclosed fleet | 14 owned top-level unit views; 14 detailed enemy views |

Most personal failures were the repeated mining feasibility probe (12 attempts)
and two later wing attacks reporting `hyperdrive_unavailable`. The latter involved
moving combat targets and are recorded as execution outcomes, without asserting a
separate engine defect. Both homeworlds remained with their original owners.

End-to-end coverage still missing: colony establishment (the original colony ship
was destroyed), a completed invasion/capture, actual bombardment damage, a completed
mining/refinery delivery, completed automatic fuel delivery, wormhole stabilization,
mine deployment/clearing, and mandatory 80-turn wing return. Recruitment completed;
invasion and bombardment approaches remained in progress at the checkpoint. Early
wings were destroyed or recalled before an 80-turn expiry. Completed docked-wing
dismantling and voluntary emergency recovery are verified separately. These limits
are explicit; accepted orders alone do not count as completed mechanics.

`summary.json`, filtered `ai_telemetry.jsonl`, `final_ai_memory.md` and
`final_observation.json` in the evidence directory preserve the final measurements.
The report prioritizes the enemy-fuel leak, disclosed gas-giant target redaction,
impossible mining options and log preservation before model/pacing refinements.
