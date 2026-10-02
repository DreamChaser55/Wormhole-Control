# Wormhole Control playtest — 2 October 2026

**Completed: 105 full Normal rounds against the live AI, plus seven staged tactical rounds.** The most significant findings are moving-recipient fuel-delivery starvation and incorrect fuel-blocker previews for tankless wings. The visible game was left at the Normal campaign's round 106, ready for Codex.

## Scope and method

Read `README.md`, `docs/REFERENCE.md`, `docs/DEVELOPMENT.md`, `docs/AGENTIC_AI.md`, the Codex control guide, and the repository's wormhole-control skill. Launched the visible GUI using the `game_control.py` status interface and played through its JSON commands. The shell had no `python` on PATH, so commands used the existing `.venv/Scripts/python.exe`. No dependencies, credentials, gameplay code, or AI runtime settings were changed.

The main Normal campaign is `dab8edd7`, seed `20261002`: two radius-3 systems, full wormhole density, 20,000 credits, 3,000 metal, 1,500 crystal, and 50 starting population per player. Codex and the built-in OpenAI opponent are on opposing teams. The opponent uses `gpt-6-luna`, Low reasoning, and two repair retries. Extra minerals were chosen to support broader construction coverage. Results therefore do not represent default-mineral scarcity or Medium/High strength.

Main-campaign play and tactical commands went through the CLI. A local helper recorded exact requests, responses, and full round observations under `.cache/playtest_20261002/`. Logs, telemetry, and AI memory were inspected with the user's playtesting authorization; gameplay decisions used observed targets and options. The window remained visible (`Wormhole Control`, Python process 2904). This is an engine/interface playtest, not a mouse-driven visual QA pass. The tactical fixture's saved-state preparation is described separately below.

## Run results and AI measurements

Here a **full round** means one resolved Codex turn and one resolved opponent turn. The main run resolved rounds 1–105, ending at the beginning of round 106: **210 player-turn resolutions**. The tactical supplement resolved seven further rounds in its own campaign: 14 player-turn resolutions. No failed AI turns were skipped or manually retried.

| Main Normal run metric | Result |
| --- | ---: |
| Live AI attempts / accepted plans | 105 / 105 |
| Semantic repairs / final failures / commit failures | 0 / 0 / 0 |
| AI turns with zero new commands | 75 |
| AI commands issued | 43 |
| Provider latency, minimum / median / maximum | 2.848 / 5.290 / 18.993 s |
| Sum of provider attempt latencies | 613.657 s |
| Input tokens, minimum / median / maximum per attempt | 50,181 / 57,244 / 65,618 |
| Total input / output tokens | 6,058,897 / 47,684 |
| Cached / uncached input tokens | 3,489,304 / 2,569,593 |

These are recorded provider token counts, not character estimates or a monetary estimate. Filter `saves/ai_telemetry.jsonl` by campaign `dab8edd7`; that file contains older sessions too. The main opponent issued 9 loads, 11 colonizations, 12 fortification upgrades, 7 construction commands, 1 continuous resupply, and 3 individual cancellations. Acceptance does not mean all resulting orders completed.

The Codex faction ended with three colonies (populations 100.00, 19.06, and 11.73), 7,055.21 credits, 2,263.5 metal, and 1,279.5 crystal. The miner carried **144 raw metal**, which had not yet been unloaded into the treasury. The main opponent's saved fleet contained its starter support units and six Colonizers, with no military production; its stationary Shipyard remained unused. This is evidence about this single Low-reasoning run.

The tactical AI completed **7/7** plans without repairs or final failures and issued 22 commands, including attacks, repairs, carrier production, and abilities. Its input size was 70,433–73,759 tokens per attempt. The staged proximity encouraged substantially more tactical activity than the Normal opening.

## Findings

### F1 — Moving recipients starve continuous fuel deliveries (P1, reproduced)

The automatic harvester reached the Sol pulsar, filled to 300 AM, and selected moving Scout 34. From round 35 through round 62 it stayed at `[-2594.23, -1496.67]` in `Sol:[0,0]`. The observation said `phase: delivering`, `waiting_reason: null`, and exposed a pending child Move with a new identity after successive updates. The scout continued moving and consuming fuel, but the supplier made no progress.

**Reproduction:** start `continuous_resupply` from a star with a recipient following a multi-turn Move/Patrol. Let the harvester finish loading while the recipient changes position every owner turn. Compare consecutive positions and child orders. Stop the recipient without replacing the supplier's order: in this run the existing delivery began executing at round 63, and harvester displacement resumed by round 64.

**Cause:** `ContinuousFuelDeliveryOrder._advance_approach()` in `unit_orders/fuel_transport.py` compares an exact anchor including recipient coordinates. A changed anchor cancels the child before it executes/updates, and the enclosing update creates another pending approach. The common base also serves depot transport and manual routes; those additional combinations were not all separately reproduced.

**Improvement:** preserve useful approach progress while tracking recipient identity, or execute a bounded movement step when replanning. Add a regression with an out-of-range moving recipient over several real turn resolutions, for both transport and harvesting. Surface a stalled/replanning reason instead of a reassuring delivery phase with no wait.

### F2 — Invalid positional destinations are accepted before immediate failure (P2, reproduced)

At round 14, Scout 34's Move to `[600,0]` in its home sector was accepted even though Planet 3 has radius 562.5 and the required 50-unit clearance makes that point invalid. Move to `[6000,0]` was also accepted despite the sector's 5000-unit boundary. Both returned successful issuance receipts, while the immediately following observation already showed `status: failed`, `failure_reason: path_unavailable`; terminal events were recorded correctly.

The shared location validator verifies shape and sector existence, but does not reject these known geometric impossibilities before replacement. The contract distinguishes issuance from completion, but the clearance-band documentation specifically says such destinations are rejected. A successful command response alone cannot distinguish an active mission from this synchronous failure.

**Improvement:** validate known boundary/clearance blockers before replacing explicit work. Keep the public preflight and execution rules aligned. Include synchronously terminal outcomes in receipts/results, or explicitly direct clients to observe after positional issuance. Verify that a rejected impossible destination preserves an existing paid build and its reservation/refund state.

### F3 — Ordinary Move incorrectly permits destinations inside solid bodies (P3, reproduced; decision recorded)

Move to Planet 3's center `[0,0]` was accepted for Constructor 27 at round 2, replacing its paid Scout build. A separate Scout 34 actually reached `[0,0]` and completed its Move by round 23. This is inside a body exposed as `is_solid: true`, with collision radius 562.5. No colonization or atmospheric-entry command was involved.

`geometry.compute_avoidance_waypoints()` explicitly retains a legacy landing/departure exception for original endpoints inside physical bodies. This explains the observed behavior; the decision below confirms that ordinary Move allowing such destinations is a gameplay defect.

**Decision (user, 2 October 2026):** the Move order must not support landing inside solid bodies.

**Required improvement:** reject ordinary Move destinations inside solid bodies before cancelling prior work. Remove the legacy interior-endpoint exception from ordinary Move; any specialized approach/entry behavior must remain scoped to its authorized operation. Align validation, execution, documentation, and command guidance with this rule. Verify rejection for planets, stars, and other solids, and preservation of existing paid work on rejection. This report records the decision; the gameplay fix has not yet been implemented.

### F4 — Newly launched actors need a separate observation/command batch (P3, interface improvement)

At round 43, a batch containing `deploy_unit` for docked Bomber 39 followed by `set_stance` on that wing rejected atomically with `unit_unavailable`; the wing was not deployed. The round-49 sequence of deployment, observation, then stance succeeded. This is safe, but awkward for clients accustomed to other projected prerequisites in the shared gateway.

**Improvement:** document deployment sequencing explicitly in `conditional_commands` or the command catalog, or project newly deployed actors into subsequent command lookup. Preserve atomic rejection. This limitation should not be mistaken for partial commit or a missing wing.

### F5 — Servicing launch errors use inconsistent public codes (P3, reproduced)

Docking and immediately relaunching Bomber 39 in one batch rejected with `wing_service_required`. After a separate successful docking, an individual same-turn launch rejected with `capability_unavailable` and the message that a recovered wing cannot relaunch until next owner turn. Both enforced the correct lock; the observation correctly exposed `ready_round: 32` and `launch_locked: true`.

**Improvement:** return the same specific code for the same servicing blocker in projected and live state. Retain the existing human-readable messages and readiness metadata.

### F6 — Tankless wing travel falsely reports a fuel blocker (P2, reproduced)

At round 80 Recon Wing 37 was flying its patrol in the home sector, with 55 deployed owner turns. Its journey preview reported `phase: blocked`, `waiting_reason: storage_unavailable`, `next_step_antimatter: 1.32`, and `estimated_remaining_antimatter: 2.64`. The wing has no tank and correctly moved for free during actual resolution. This contradicts the documented wing exception and could make an agent cancel useful work or attempt impossible refuelling.

**Improvement:** use the same wing exemption in journey fuel estimates and blocker reporting as in actual movement payment. Compare consecutive wing positions against previews in a regression; include Patrol, docking, and mandatory return journeys.

## Suggestions requiring broader balance/performance evidence

- **Mission pacing:** the first neighboring lunar colony took roughly 45 owner resolutions to settle, dominated by leaving and entering natural inhibition fields. At round 25 a Scout patrol to the enemy home sector estimated another 87 owner turns and 111 AM, exceeding its 100-AM tank. The estimates usefully explain the work, but this makes a small Normal match very quiet. Starting units should spawn closer to the edge of the homeworld's inhibition field, so they (or any units constructed by them) can leave it quicker.
- **Readable enums:** unit `hull_size` and connection `maximum_hull` appeared as numeric strings such as `"4"`, while field limits use readable names such as `LARGE`. Publish readable hull names or a clear mapping consistently.
- **Low AI strategy:** the early opponent maximized home fortifications and committed to six Colonizer builds on its mobile Constructor while leaving the starting Shipyard idle. Its memories correctly preserved useful missions, but this single run merits checking balanced production, idle-builder usage, and defensive investment. Do not extrapolate to other reasoning settings or seeds.
- **Coverage guidance:** command success means issuance, not completion. Provide a short controller example that reads terminal history, recognizes synchronous failure, preserves travelling work, and handles observations between deployment and new-actor actions.

## Confirmed working behavior

- Atomic rejection for malformed multi-command batches; unknown fields, empty/41-command batches, unauthorized units, unarmed stances, and stale tokens rejected appropriately.
- Hidden enemy unit 30 and nonexistent unit 999999 returned the same `target_unavailable` result when attacked, preserving the disclosure boundary.
- Identical request-ID replay returned an identical rename response. Changed content under that ID returned `request_id_conflict`. Replaying round-62 End Turn returned the cached response without another resolution.
- Unsupported protocol, unknown action, invalid wait duration, malformed CLI JSON, and recovery when no AI turn had failed produced bounded errors. Attempting a second launch on another port returned the existing-game diagnosis and preserved the active GUI.
- Fixed construction sites, queued reservations, completion history, population loading/settlement, growth, habitat income, and three-resource charging progressed through real turns.
- Slot discovery, explicit nullable production selection, missing-field/out-of-range-slot validation, and customized wing construction worked. Bomber 39 had the requested Beam long-range turret and Armor-only defense while preserving range 292.5 and cooldown 9.
- Per-wing docking reset endurance and enforced next-owner-turn launch readiness. Production pause and clearing a selection preserved existing wings.
- Patrol creation, waypoint appending without replacement, individual cancellation, and stance changes preserving explicit work worked.
- Round-31 save/load restored the **entire observation exactly**, including all unit queues, construction progress, wing slots, economy, order history, briefings, and conversations. The token changed and the old token was rejected. Duplicate saves, traversal names, active-campaign replacement, and compatibility listing were handled correctly.
- The reconnaissance wing had 79 deployed owner turns at round 104 and entered system-controlled `return_for_service` at round 105. Stop, Move, and stance changes all rejected with `wing_service_required`; rename remained allowed. Its enduring count stayed capped at 80. It was still returning when the 105-round session ended; automatic return docking was not observed to completion.
- Dismantling Patrol Cutter 51 took three owner resolutions and paid exactly **200 credits, 7.5 metal, and 2.5 crystal** at round 87. Two intervening observations advanced neither work nor balances. Offline state and discarded cargo were disclosed.
- Recruitment completed with 20 troops aboard Transport 50 at round 88. Two lunar settlements completed, and colony population/cargo changes were reflected in later observations.
- The carrier's receiver-initiated fuel pickup delivered 25 AM then 6 AM on successive turns, filled its tank, and reduced the donor by the same 31 AM; movement consumed fuel separately.
- An attack on moving enemy Colonizer 36 cancelled once at round 87 with `target_not_visible`, retained its stance, and later stance engagement reacquired the reappearing contact. Enemy observations omitted orders, template/accounting fields, and antimatter. A guessed private Intelligence subsystem rejected with `target_unavailable`.

## Staged tactical supplement

Campaign `572a0e25` used the Testing profile, the same seed and small map, and opposing Codex/Low OpenAI teams. A separate seed save was copied into `playtest_20261002_tactical_encounter.json`; only the rival fleet's sector/location metadata and positions were changed to place its 12 units near the Codex fleet. HP, equipment, resources, bodies, controllers, and the main Normal save were preserved. The fixture was loaded through `game_control.py`; commands then used newly observed IDs and capabilities. As documented, loading a Testing save retained its ships and used the Normal construction catalogue.

This was **seven rounds of an artificial close encounter**, not evidence that ordinary Normal map travel produced the same battle. It covered:

- Normal turret firing, hull damage, cooldowns, destruction of the rival Tiny Ship, and historical combat briefings. A repair order restored the Codex carrier from 193 to 200 HP; subsequent enemy fire damaged it again. The opponent also repaired its Titan.
- Infiltration producing **agent ID 0**, engines sabotage, immediate relocation to another observed host, weapons sabotage, and extraction. ID 0 worked throughout; extraction removed the agent from the owned-agent observation. CI Sweep's issuance/payment path was exercised without discovering an enemy agent.
- Fleet Jump rejection with `jump_inhibited`, including disclosed gathered participants. Successful Fleet Jump relocation was not tested.
- Queued Aegis, Deep Scan, Carrier Supremacy, and Siege Lance casts. Issuance reserved casts without paying their activation costs; the initial 25-AM decrease came from CI Sweep. The queued powers executed on successive owner resolutions. Both factions used Siege Lance; the Codex Lance reduced the rival Titan from 1600 to 1381 HP. This was actual combat resolution, not a preview.
- Bomber production, deployment, Attack Run, and Evasive Formation. The bomber hit for **15 HP**, matching `10 base × 2 salvo × 0.75 outgoing evasion`. Emergency Recovery returned it to its bay, reset endurance, and exposed its next-owner-turn readiness.
- Multiply Antimatter restored the Titan from 1275 to its 2000-AM cap and applied recipient recovery state. Cancelling Deep Scan ended its active effect while retaining its 16-turn cooldown.

No additional confirmed defect was found in these tactical operations. This small fixture does not establish overall combat balance.

## Evidence and saved state

- [Round-31 save](saves/playtest_20261002_round31.json) and [final Normal save](saves/playtest_20261002_final_round106.json).
- [Testing seed](saves/playtest_20261002_tactical_seed.json), [staged encounter](saves/playtest_20261002_tactical_encounter.json), and [tactical final save](saves/playtest_20261002_tactical_final_round8.json).
- `.cache/playtest_20261002/transcript.jsonl`: exact Normal CLI requests/responses, exit status, and latency; `round_001.json` through `round_106.json`: round observations. Additional observations in the same round replace that round's snapshot, while the transcript retains each response.
- `.cache/playtest_20261002/tactical/transcript.jsonl` and tactical round snapshots; `.cache/playtest_20261002/main_statistics.json`: campaign-filtered telemetry and token totals.
- `saves/agent_memory/dab8edd7/59ed131e/memory.md`, `saves/ai_telemetry.jsonl`, and `game.log`: AI intent, receipts, attempt measurements, and execution diagnostics. These files are generated/ignored artifacts; the report is the intended repository deliverable.

The final Normal save was restored after the supplement. Positions, resources, explicit orders, history, briefings, and every observation section other than one transient stance engagement matched. The in-progress stance pursuit was cleared on load, consistent with `unit_orders/stance.py` describing that engagement subtree as transient; the selected stance remained intact. No additional turn was advanced while restoring it.

## Offline checks and limitations

Ran the existing `tests/test_playtest_ai_recovery.py` and `tests/test_collision_avoidance.py`: **30 passed in 1.60 seconds**. These cover fake-provider recovery and navigation regressions separately from the live campaigns. All 112 live AI attempts succeeded initially; live timeout/authentication/partial-commit recovery was therefore not observed. Offline results do not establish live failure reliability. No code fixes or new automated tests were added.

Mouse/keyboard interactions, visual layouts, private human designs/refits, allied team sharing, planetary bombardment/invasion outcomes, completed trade routes, completed mineral delivery, gas-giant entry/exit, environmental resistance toggles, wormhole stabilization, successful Fleet Jump, anti-wing tracking/flak damage, agent elimination, and all other abilities were not exhaustively tested. They remain follow-up coverage; acceptance and approach alone are not claimed as completion.
