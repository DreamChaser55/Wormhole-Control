# Wormhole Control playtest — 2026-09-30

## Scope and environment

Read `README.md`, `docs/REFERENCE.md`, `docs/DEVELOPMENT.md`, `docs/AGENTIC_AI.md`, the local control skill, and `docs/CODEX_CONTROL.md`. Played through the real `game_control.py` CLI and its visible Pygame game, against the built-in OpenAI opponent. Source, logs, observations, telemetry and generated AI memory were inspected as permitted for this playtest. No production code was changed.

- Revision: `3e032405804c611c62bcc10c97929bf13e77d92b`.
- Windows; Python 3.12.14; pygame-ce 2.5.7; pygame_gui 0.6.14; OpenAI SDK 2.54.0; httpx 0.28.1.
- Main campaign: `39ab8c9c`; opponent agent: `2c98cb6e`; controller model `gpt-6-luna`, Low reasoning, two semantic repairs.
- Testing profile, two radius-3 systems, full wormhole density, two opposing teams, 100,000 credits / 10,000 metal / 5,000 crystal each. This intentionally provides broad equipment coverage; it is not a Normal-opening balance benchmark.
- Main session uses localhost port 47655. Two earlier attempts on 47653/47654 hit the certificate failure below and were closed.
- Raw request/response evidence and helper scripts are in ignored `.cache/playtest-20260930/`. Runtime files are also ignored. In particular: `transcript.jsonl`, `friendly-designation.json`, `infiltration.json`, `treasury-refund.json`; `saves/ai_telemetry.jsonl`; `saves/agent_memory/39ab8c9c/2c98cb6e/memory.md`.
- Reproduction examples below use this campaign's observed IDs. Substitute IDs from a fresh observation in another campaign. Random generation was not seeded, so the exact geography is not independently reproducible from setup settings alone.

## Confirmed issues

### 1. Built-in AI cannot connect with the default certificate configuration on this Windows installation — P1, environment-dependent

**Observed:** Both initial campaigns stopped on the first AI turn with `APIConnectionError`. A credential-free diagnostic request using `httpx` exposed `CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate`; Windows' standard `urllib` HTTPS client reached the same endpoint and received the expected unauthenticated HTTP 401.

**Impact:** A correctly configured AI campaign can become unusable before the opponent makes any move. The high-level failure does not identify the actionable certificate problem.

**Workaround verified:** Export the Windows certificates trusted for server authentication to a temporary PEM bundle, set `SSL_CERT_FILE` for the new game process, and launch through `game_control.py`. The built-in AI then completed real requests. Certificate verification stayed enabled; credentials were neither printed nor manually transmitted by the diagnostic checks.

**Suggested improvement:** Support the operating system trust store, or document a supported `SSL_CERT_FILE` setup and identify certificate-trust failures with safe diagnostic text. Do not solve this by disabling TLS verification. Relevant code: `game_ai/adapters/openai_responses.py`.

### 2. The control protocol cannot distinguish a failed AI turn from ongoing planning — P1 for unattended control

**Reproduction:** End the Codex turn with an AI opponent whose provider connection fails. Query `status` and `wait_for_turn` after the error is logged.

**Observed:** Status continues to show the AI as active with `codex_ready: false`; waiting times out successfully with `ready: false`. Neither response exposes planning failure, retry state or manual recovery availability. The documented GUI recovery cannot be performed through a protocol action.

**Impact:** A socket-only controller can wait indefinitely without learning that no progress is possible. We had to inspect telemetry/logs to distinguish failure from slow reasoning and launch a fresh test instance.

**Suggested improvement:** Add bounded public AI lifecycle status (`scheduled`, `planning`, `repairing`, `failed`, `manual_recovery`) and a safe error category. Let waiters return an attention-required result on final failure. Consider explicitly scoped retry/skip-failed-AI-turn actions rather than requiring desktop interaction. Relevant code: `game_control_protocol.py`, especially `_state`, and `game_ai/coordinator.py`.

### 3. Legacy ability discovery and preflight accept a friendly Designate Target — P2

**Evidence:** In campaign `39ab8c9c`, the Titan's `command_options.use_ability.targets_by_ability.designate_target` included owned units. At round 2, Designate Target on owned unit 25 was accepted and began approach. At round 3, this command against nearby owned carrier 35 was accepted:

```json
{"type":"use_ability","unit_ids":[36],"ability":"designate_target","target_id":35}
```

Fresh observation then showed a terminal `use_ability` failure with `reason: "failed"`. `game.log` recorded activation failure. The implementation in `unit_components/abilities/designate_target.py` rejects friendly/allied units during activation, so **no friendly damage-amplification effect was demonstrated**.

**Impact:** An impossible target is advertised and accepted, can replace useful work, and can cause unnecessary approach travel. The controller receives an issuance-success receipt for work that could have been rejected immediately.

**Suggested improvement:** Share the activation relationship/range policy with discovery and preflight for legacy abilities, as already done for newer tactical abilities. Audit other legacy unit-targeted abilities rather than assuming this defect affects all of them. Relevant code: `game_ai/rules.py` generic ability-target enumeration, `game_ai/commands.py`, `unit_components/abilities/designate_target.py`.

### 4. Attack options include routes the attacker cannot ever traverse — P2

**Observed:** During rounds 3–5, stationary stations 26/28/30/32 advertised attacks on enemies in another sector. Issuing those advertised attacks succeeded, followed immediately by `execution_failed` history outcomes. Deployed bomber wings also accepted cross-sector attacks that failed. Later the locally confined Patrol Cutter 52 repeatedly advertised attacks on the remote enemy fleet and produced the same failure loop.

**Impact:** Legal-command discovery invites deterministic failures, order replacement and history churn. This is different from an initially feasible pursuit failing because its target moved or became hidden.

**Suggested improvement:** Filter target options by current route feasibility and reject a stationary attacker outside usable firing range, or a wing/local-only craft requiring unavailable inter-sector travel. Preserve legal stationary fire and feasible approaches. Use the existing approach/path policy rather than duplicating it. Relevant code: `game_ai/rules.py` attack target enumeration, `game_ai/commands.py` attack checks, `unit_orders/combat.py`.

**Test context:** The playtest helper deliberately issued advertised attacks on idle units to exercise discovery. These repetitions are evidence of the interface problem, not proof that the built-in opponent repeatedly made the same choice.

### 5. Execution feedback often loses the actionable failure reason — P2

**Observed:** The rejected friendly Designate Target appeared as `failed`; impossible station, wing and cutter attacks appeared as `execution_failed`; unsuccessful wing docking after carrier departure also used generic execution-failure feedback. By comparison, loss of sensor contact correctly reports `target_not_visible` and an explanatory briefing.

**Impact:** The model can identify that work failed but cannot reliably distinguish bad allegiance, absent movement capability, unreachable sector, carrier departure, unsafe placement, or another execution blocker. Repeated generic failures waste planning and can replace otherwise useful work.

**Suggested improvement:** Propagate bounded machine-readable root causes from ability/order validation into order history and briefings. Keep the existing privacy policy: no hidden IDs, target geometry, raw exception text or secrets. Add regression cases for the live failures above. Relevant code: `unit_orders/abilities.py`, `unit_orders/combat.py`, `unit_orders/base.py`, `order_history.py`.

### 6. Transport-error telemetry records zero latency for requests that took seconds — P3

**Observed:** Initial AI requests failed about 9–10 seconds after scheduling, but their telemetry records contain `latency_seconds: 0.0`. `game_ai/coordinator.py::_record_transport_error` hardcodes that value.

**Impact:** Failure latency, provider reliability comparisons and timeout diagnosis are misleading.

**Suggested improvement:** Record monotonic elapsed time from attempt submission through failure, with separate request/backoff/total timings if useful. Keep payload-free exception categories.

### 7. The local control skill contains obsolete protocol and schema guidance — P2 documentation

**Observed:** `.agents/skills/wormhole-control/SKILL.md` says socket protocol 2, command contract 2 and observation schema 4. Runtime and the generated Development table report protocol 3, command contract 22 and observation schema 27. A protocol-2 probe was explicitly rejected with `unsupported_protocol`. The control guide also contains an illustrative observation snippet using schema 26.

**Impact:** An agent following the skill can start with a rejected transport version or misunderstand observation compatibility.

**Suggested improvement:** Link the generated current-version table from the skill instead of repeating mutable version numbers. Update examples or explicitly mark their schema values as illustrative. Extend documentation checks to the local skill and control examples.

### 8. Forced wing return uses an ordinary cancellation reason — P2

At round 83, wing 49 reached 80 turns outside, had its Protect order cancelled, and successfully returned to carrier 35. Its interrupted Protect history event (77) says `reason: "cancelled"`. Orphaned wing 50's interruption in the same round says `wing_endurance_expired`. The same distinction repeated at round 86 for returning wing 53 versus orphaned wing 54. `docs/AGENTIC_AI.md` states that `wing_endurance_expired` identifies interrupted orders; `strikecraft_service.py::reconcile_unit` currently clears a returning wing's explicit orders without setting that cause.

The return/docking mechanics worked, but history makes a forced return look like an ordinary cancellation. Propagate the endurance cause for both mandatory return and expiration, while keeping voluntary cancellation separate. Add a regression assertion to the servicing tests, which currently passed despite this discrepancy.

## Improvements supported by the session

### Reduce observation and planning overhead — high priority

The first successful two-system AI request used **72,785 input tokens**. Quiet turns still used roughly 76,000; combat/repair attempts reached approximately 90,000 or more. A round-10 Codex observation serialized to 302,437 characters: units 143,956; action catalogs 93,951; command catalog 21,932; systems 18,308; ability catalog 16,359. These are JSON character measurements, not tokenizer estimates. Provider token figures come from telemetry.

The catalogue is deduplicated at top level, but per-constructor price lists, command options and extensive capability descriptions still consume substantial context. The AI also made full provider requests on many quiet turns that returned no commands.

Suggestions:

- Measure prompt sections and report cached versus uncached input usage; total input count alone does not establish actual billed cost or caching effectiveness.
- Separate stable rules/catalogues from changing tactical state, preserve a stable cache prefix, and consider compact catalogue references or an optional delta observation protocol.
- Emit constructor price exceptions/shortfalls with shared base prices rather than repeating all quotes where possible.
- Consider an explicit bounded 'continue these orders until event/round' planning result to avoid full requests during quiet travel. Interrupt it on combat, loss, failure, discovery, resource shortage or a deadline.
- Benchmark Normal and Testing separately, with fixed scenarios and map sizes. This run does not establish performance for a six-player, 30-system match.

### Make long journeys legible and evaluate opening pace

Loading ten colonists began in round 1 and completed in round 7; the queued colony at a nearby moon completed in round 51. The offensive movement issued in round 16 reached the enemy home sector around round 30. This follows the documented movement/inhibition rules, but requires many AI requests before a mission pays off.

Expose remaining approach distance, current route leg, egress/jump/arrival phase, drive recharge and a bounded estimate based on current capabilities. Clearly label estimates as conditional. Review inhibition radii, movement speed and initial placement together before changing balance. Avoid treating slow but advancing work as stuck and reissuing it.

### Expose target-independent Fleet Jump blockers

Fleet Jump was listed ready/available while the caster and gathered ships were inside the home planet's known inhibition zone; an attempted cast rejected with `jump_inhibited`. Destination safety is necessarily conditional, but origin inhibition is already known before a destination is chosen. Expose that blocker and identify which **owned** participants prevent jumping, without revealing hidden enemy fields.

### Improve command-catalog field-presence ergonomics

`set_wing_production.required` lists `slot_index`, while the separate top-level `required_nullable_fields` map supplies `template_name`. The full catalog is correct: template presence is mandatory and null clears the slot. This is **not a contract defect**. It is easy for a client that reads only each command's `required` array to miss the second requirement. Consider one per-command presence list plus separate nullability/conditional constraints, and show this distinction in a small client example.

### Keep useful AI lessons and align objectives with actual orders

The opponent repaired invalid station stances and an out-of-range Siege Lance, storing useful lessons. Later memory patches replaced those lessons with broader guidance. At round 30 an objective still mentioned continuing planetary infiltration, while that turn replaced the Titan's work with an attack. This is model planning quality rather than a proven engine defect.

Prefer merging durable lessons over repeatedly replacing the section. Include a compact 'orders this plan will replace' view and check memory objectives against the committed roots. Evaluate tactical focus fire, casualty avoidance and mission preservation with fixed fixtures; one Low-reasoning game cannot establish a model-strength ranking.

### Add reproducible setup and broader bridge lifecycle tools

An optional setup seed and a setup/state export would make live regression scenarios easier to replay. Saving/loading, returning to menu and recovering a failed non-Codex turn currently require GUI workflows. Explicit, validated bridge actions would improve unattended playtesting while preserving the rule that `new_game` cannot silently replace a campaign.

## Verified behavior

- Visible GUI launch and CLI stdout JSON framing; use of the repository virtual environment recovered from a shell with no `python` on PATH.
- Entire-batch rejection: an earlier rename in a batch with an invalid later destination did not apply.
- Idempotent identical mutation replay and rejection of changed content under the same request ID.
- Rejection of stale tokens, legacy protocol, unknown actions, invalid/boolean wait durations, unknown command fields, boolean unit IDs and active-campaign replacement.
- Patrol creation, append without interrupting the leg, individual queued-root cancellation, blocked-queue guidance, and stance preservation while explicit work suspends combat.
- Construction and wing production; per-slot beam/shield overrides; paid-slot edit rejection; production pause and clearing a selected occupied slot.
- Three-resource queued reservations and exact paid-construction cancellation refunds. Cancelling again did not trigger another payment/refund.
- Dismantling completed in round 58: a full-health Patrol Cutter yielded 200 credits, 7.5 metal and 2.5 crystal, matching the documented formula.
- Colony loading, queued colonization, subsequent population growth, income/upkeep and immediate fortification upgrade.
- Sensor contact acquisition/loss, attack cancellation on lost contact, enemy-private order redaction, explicit movement suppressing stance fire, actual ship/wing combat, subsystem targeting, and destruction briefings.
- Deep Scan, deferred Siege Lance charge/impact, Aegis issuance, real opponent carrier production/deployment, and antimatter transfer.
- Infiltration created agent ID **0**, and sabotage with that ID worked, confirming that zero is a valid agent identity.
- Real semantic repair after invalid station stances and out-of-range Titan casts, followed by accepted execution, memory export and bounded telemetry.

## Automated checks

Executed two focused, offline pytest groups; **340 tests passed, plus 10 subtests**. Each invocation reported one warning. These supplement the live session; they do not prove exhaustive gameplay or graphical correctness.

```powershell
.venv/Scripts/python.exe -m pytest tests/test_game_control.py tests/test_ai_coordinator.py tests/test_ability_targeting_guidance.py tests/test_player_command_discovery.py -q --disable-warnings
# 54 passed; 10 subtests passed

.venv/Scripts/python.exe -m pytest tests/test_planetary_warfare.py tests/test_planetary_intel.py tests/test_strikecraft_service.py tests/test_ai_intelligence_interface.py tests/test_construction_reservations.py tests/test_dismantling.py tests/test_titans.py tests/test_movement_payment.py tests/test_patrol_order_queueing.py -q --disable-warnings
# 286 passed
```

## Coverage limits

The GUI remained visible, but this was a protocol-driven session, not a visual/manual UI audit. Designer dialogs, camera controls, human briefings, save/load menus, live save restoration, every celestial hazard, allied team mechanics, every ability, mining/refinery throughput, trade, wormhole stabilization and six-player scale were not all exercised live. Some are covered by the listed offline tests. No claim is made that those features are defect-free.

The final results below describe the observed session, including an unsuccessful invasion; no victory or complete feature coverage is claimed.


## Final live-session results

- Completed **96 rounds against the real built-in AI**, stopping at the start of Codex round 97. The visible GUI remains open on port 47655 for inspection.
- Established Moon 10 in round 51; by round 97 the colony continued growing. The AI also established asteroid colony 5 and upgraded its homeworld to fortification level 3.
- Recruited 40 troops in round 44. The queued assault resolved in round 93 and was repelled: success threshold 24.2%, roll 80.4%, 30 casualties and 10 surviving troops. Fuel/action history and the failure briefing were present; enemy ownership remained unchanged. Successful colony capture and bombardment were not demonstrated live.
- Produced and deployed wings, then crossed their 80-owner-turn endurance boundary. Wings 49/53 returned, docked, reset endurance and relaunched on later owner turns. Wings 50/54, whose mother carrier was in another sector, expired as documented. The history-reason issue is recorded above.
- Built Minelayer 66 and deployed a visible owned anti-ship field with five mines and 300-unit detonation radius. Enemy mine triggering/clearing was not exercised live.
- Sustained combat caused losses on both sides, hull and Weapons-component damage, repeated turret cooldown cycles and Titan charge/impact behavior. Some light attacks caused no damage, consistent with the documented defense rules.
- Final probes returned the same public errors for unavailable unit 45 versus nonexistent unit 999999, and for the hidden Intelligence subsystem versus a nonexistent subsystem. No enemy order layers or private troop/wing/Titan state appeared in the inspected observation. This is a spot check, not a proof of the entire information boundary.
- Replayed the exact first End Turn request at round 97: the cached response returned successfully and before/after live status stayed unchanged.

### Main-campaign telemetry

| Measure | Result |
|---|---:|
| Accepted AI turns | 96 |
| Provider attempts | 102 |
| Rejected attempts / semantic repairs | 6 |
| Total input tokens | 9,264,181 |
| Total output tokens | 68,709 |
| Largest single input | 98,434 |
| Median provider-attempt latency | 7.476 s |
| Largest provider-attempt latency | 21.335 s |

All main-campaign AI turns eventually committed; no final transport failure or game crash was observed after the CA workaround. Latency figures are provider-attempt telemetry, not total turn wall time, and do not include all CLI/presentation overhead. Token totals are not a billing estimate. The two earlier failed campaigns are excluded from this table.

Prioritize secure Windows provider connectivity, observable AI failure/recovery, and target-feasibility/ability preflight consistency. Then improve terminal reasons, version documentation, and context efficiency.
