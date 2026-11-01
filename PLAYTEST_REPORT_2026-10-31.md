# Wormhole Control playtest — 31 October 2026

## Session and scope

Completed **106 full rounds against the live built-in AI**: 106 Codex turns and 106 AI turns, or 212 individual player-turn resolutions. The visible game was controlled exclusively through `python game_control.py` and is left on the Codex turn at round **107**. The extra rounds reached the original bomber's 80-turn servicing threshold and completed a controlled environmental comparison.

The main findings are a Windows cold-start failure, a durable false AI lesson apparently caused by confusing a population forecast with an outcome, and inflated travel-time estimates. The command gateway remained stable through the run. Two AI mistakes were rejected and repaired automatically.

- Revision: `499d6b87dab3104712049b07939805c155790701`.
- Platform: Windows; Python 3.14.3.
- Documents read: `README.md`, `docs/REFERENCE.md`, `docs/DEVELOPMENT.md`, `docs/AGENTIC_AI.md`, plus the Wormhole Control skill and `docs/CODEX_CONTROL.md`.
- Campaign: `987feaa6`; seed `20261031`; Normal profile; three radius-3 systems; wormhole density `1.0`; default economy and starting population.
- Players: Codex Playtest, team 1, versus AI Rival, team 2. Built-in opponent: `gpt-6-luna`, Medium reasoning, two semantic repair retries.
- Starting homes: Sirius for Codex, Procyon for the AI. Codex's Greenhouse homeworld caps the configured 50 starting population at 35, as documented.
- Live provider use was explicitly approved by the user. Existing credentials were used by the game; no credentials were inspected or printed.
- No game implementation was modified. Disposable recording helpers and request/response evidence are under ignored `saves/playtest_20261031/`.

## Completed-session results

| Measurement | Result |
| --- | --- |
| Completed rounds / saved position | 106; start of round 107, Codex active, no attention required. |
| Final save | `saves/playtest_20261031_final_round107.json`. |
| Recorded in-campaign control requests | 358, including observations, intentional rejection tests, replay and lifecycle checks. |
| AI requests / completed AI turns | 108 provider attempts; all 106 AI turns completed. |
| Semantic repair | Two initial preflight rejections, each followed by one successful repair; no final AI failure. |
| Accepted AI commands / no-command turns | 50 commands; 73 accepted no-command turns. |
| AI attempt latency | Median 13.958 s; nearest-rank p95 26.498 s; maximum 39.329 s. Summed attempt latency 1,580.977 s, not total wall-clock session duration. |
| Provider input tokens | 6,928,736: 3,450,857 cached and 3,477,879 uncached. |
| Provider output / total tokens | 164,901 output; 7,093,637 total. These are telemetry usage figures, not a price estimate. |
| Codex terminal order outcomes | 46 completed, 9 cancelled, zero failed; intentional invalid commands were rejected before becoming orders. |
| Privacy audit | No tested private fields exposed across recorded enemy observations (9 distinct enemy contacts) or 1,296 repeated unknown/historical-world records. |
| Runtime failures | No commit exception, provider failure, final AI failure, or error/traceback record in `game.log` observed. |
| Final Codex colonies | Homeworld 28 plus Moon 34 and Ice world 26. |
| Final Codex treasury | Approximately 743.41 credits, 236.5 metal, 566 crystal. |

The final save preserves an ongoing battle and future missions; this was a bounded playtest, not a victory-condition run. Scout 48 is deliberately fuel-starved from the logistics test, and the Troop Transport's invasion is still travelling. Hazard Escort 69's protection was re-enabled after the comparison. The temporary launcher helper was stopped, and a final status request confirmed the visible game remained available.

## Evidence and reproducibility

- `saves/playtest_20261031/rpc.jsonl`: complete timestamped control requests, responses, CLI exit codes, and elapsed times.
- `saves/playtest_20261031/boundary_checks.json`: deliberate negative tests and their expected rejections.
- `saves/playtest_20261031/analysis.json` and `cli_checks.json`: aggregate metrics and malformed-input results.
- `saves/playtest_20261031/environment_protected.json` and `environment_unprotected.json`: controlled debris comparison snapshots.
- `saves/ai_telemetry.jsonl`: filter by campaign `987feaa6` to isolate this session.
- `saves/agent_memory/987feaa6/7b1c42b0/memory.md`: opponent's current generated memory sidecar.
- `saves/playtest_20261031/ai_memory_early.md` and `ai_memory_final.md`: preserved early/final memory evidence; the false population lesson remained present at turn 106.
- `game.log` and `saves/control_stderr.log`: execution and startup diagnostics. These are runtime files, not committed report attachments.
- `saves/playtest_20261031_round002.json`: baseline save used for an actual save → main menu → load round trip.

## Confirmed issues and observations

### P2 — Windows cold start can fail before auto-launch

**Observed:** The documented initial status command returned `connect_timeout` instead of launching the game. The same result occurred with permission to access the host's localhost interface. A separate four-second socket probe against the absent listener returned `ConnectionRefusedError`, Windows errno `10061`, after **2.017 seconds**.

**Cause supported by source inspection:** `game_control._send()` uses a one-second connection timeout. `main()` launches only on `connection_refused`, correctly avoiding automatic launches after ambiguous timeouts. On this host, the timeout expires before Windows reports refusal, making the normal cold-start path unreachable.

**Reproduction:** With no listener on `127.0.0.1:47653`, run the README/control-guide status invocation. Compare the one-second CLI result with a socket connection allowed more than two seconds to report refusal.

**Workaround used:** A disposable wrapper called the same `game_control.main()` with a minimum three-second initial connection probe. The normal launcher then started the visible GUI and returned a valid main-menu status. No product file was changed.

**Suggested improvement:** Make the initial connection probe configurable and choose a Windows-compatible default; preserve the distinction between refusal and uncertain transport outcomes. Add a delayed-refusal regression test and troubleshooting guidance. Restricted-environment localhost failures encountered separately are environment limitations, not additional game bugs.

### P2 — AI stores a false lesson about a successful colony load

**Observed:** By turn 5, the opponent's durable memory contained:

> `[load_colonists/source-population] Prefer load_colonists.targets[].population_advice.recommended_amount; loading the maximum from Planet 2 left only 0.25 population and a long recovery.`

The execution log instead records **25 colonists loaded** from Planet 2. The round-2 save records **25.25 population remaining** on that Ice world. The AI followed the half-population advice; it did not nearly empty the source. Its memory also tells future planning to let that source recover before further recruitment.

**Impact:** A false, durable account of an earlier action can distort later expansion choices even when the engine and command advice behaved correctly. The sidecar is a faithful export of AI memory, not authoritative evidence that the lesson's claim happened.

**Connection to commit `9f89f68` (investigated following the user's pointer):** That commit added `population_advice` and the hypothetical `population_after_maximum_load` / `recovery_rounds_after_maximum_load` fields. The initial round-2 save contains the accepted turn-1 memory, which correctly commits to loading **25** and contains **no lessons**. With the actual next-turn population **25.25**, growth **0.01**, capacity **60**, and cargo space **75**, the new helper returns:

```json
{"recommended_amount":12,"recommended_retained_population":12.625,"population_after_maximum_load":0.25,"recovery_rounds_after_maximum_load":464}
```

Thus the false memory's **0.25** exactly matches a forecast about a *possible next maximum load*, rather than the population after the load that actually executed. This is strong evidence of forecast/outcome confusion; the model's internal reasoning is not available, so the causal interpretation remains an inference. Searches found no runtime S07 text or hardcoded false lesson. Commit `9f89f68` does not directly seed AI memory. Its advisory calculation is mathematically correct for that hypothetical action.

**Suggested improvement:** Clearly group the forecast under a hypothetical next-load scenario, alongside explicit `current_population` and `hypothetical_load_amount`, rather than leaving the residual easy to mistake for current state. State explicitly in the prompt that the forecast is not a report of the previous load. Derive factual loading outcomes from structured execution feedback and include requested/loaded amount plus actual retained population. Add a live-model evaluation fixture contrasting actual **25.25** with hypothetical **0.25**; the existing arithmetic/privacy tests do not measure this semantic error. Preserve advisory semantics and historical-intel privacy; this finding does not justify making larger loads illegal.

### P3 — Two live AI mistakes needed semantic repair

| Round | Initial rejected plan | Automatic correction |
| --- | --- | --- |
| 69 | Patrol Escort 56 tried to attack strikecraft Wing 54 with an ineligible standard turret: `capability_unavailable`, “No eligible weapons for this target.” The entire two-command batch applied zero operations. | Removed that attack and applied the other valid attack by unit 64; accepted on attempt 1. |
| 73 | Scout 49 selected an obstructed destination: `invalid_destination`, “Destination is inside an obstacle or its clearance band.” Zero operations applied. | Submitted a valid Move on attempt 1. The rejected coordinates are not present in the intentionally bounded telemetry, so this report does not identify which obstacle was selected. |

Both turns completed within the configured repair budget. Correct target-eligibility and movement lessons appeared in durable memory. This validates the recovery mechanism while identifying two live-model reliability cases (2 of 106 turns).

**Suggested improvement:** Add these cases to live-model evaluations. Keep eligible target classes prominent when choosing combat targets, and make safe exploration destinations easy to derive. Public system anchors are at star centers; a safe navigation point or explicit warning would help prevent treating a physical anchor as a legal Move endpoint. The round-73 evidence does not establish that a star anchor caused that particular rejection.

### P3 — A final jump's travel estimate includes unnecessary recharge

**Observed:** At round 49, Scout 48 had one remaining route leg, a ready drive, zero current recharge, and a final same-system jump from Procyon `(2, -3)` to `(-3, 0)`, arrival `(0, -3500)`. Its observation estimated **4 remaining owner turns**. The next observation showed the destination reached and the Move recorded completed at resolution turn **49**: only one End Turn was needed. No destination, equipment or intervening order changed.

**Source support:** `game_ai/order_view.py:115` uses `estimate_approach().turns` for the public journey estimate. In `antimatter_logistics.py`, every jump adds `drive.RECHARGE_DURATION + 1`, including the terminal jump. This charges the estimate for recovery after travel has already finished. A separately issued one-jump probe at round 54 advertised the same four-turn estimate and completed at resolution turn **54**, reproducing the discrepancy independently.

**Suggested improvement:** Separate arrival time from readiness for a subsequent jump. Charge recharge only when another route leg actually needs a ready drive, accounting for any recharge concurrent with sublight travel. Keep conservative fuel-service reserves distinct from the user-facing remaining travel estimate. Add a behavioral check comparing a ready terminal jump's preview with its actual completion, including a route with further jumps as a separate case.

### P3 — An unchanged fuel wait repeats a significant briefing warning

**Observed:** Scout 48 exhausted its 22 AM on the deliberately under-fuelled gas-giant approach. It correctly stopped moving and retained its order with `waiting_reason: insufficient_antimatter`. Resolutions **79–106** generated **28 successive** `Movement blocked: insufficient antimatter` briefing events, with new event IDs, despite unchanged fuel and position.

**Impact:** The current-order wait already explains the persistent condition. Repeating the same problem adds planning noise; by the documented shared briefing/Automatic-mode rules it can also keep prompting a human player. The latter UI consequence was not tested by clicking the human modal.

**Suggested improvement:** Emit the significant event on entry into the fuel wait, then use a persistent unit warning or optional periodic reminder. Report recovery or a materially different problem as a new event. Keep the wait visible in every observation.

## Further improvement suggestions

- Add safe action-specific metadata to telemetry summaries, such as construction template, wing slot/template, ability and requested loading amount. The existing type/unit/target summaries cannot alone establish what amount was requested or which template was selected. Keep raw prompts, credentials and full model output excluded.
- Provide advisory time/fuel quotes before issuing a new approach mission. At round 64, Scout 48 had **22 AM**; after issuing Gas Giant entry, its journey disclosed **30 AM** required and **26 estimated owner turns**. This correctly remains legal, but pre-issuance guidance would help planners prepare resupply before replacing useful work.
- Clarify gas-giant queue documentation by interface. The general reference describes Enter → Move → Leave as a blocking queue, whereas the socket gateway rejected that projected sequence atomically with `invalid_state`. That protective validation is useful; identify which interfaces can create the documented blocked state and show a valid automated sequence.
- Distinguish returning to a fuel source from waiting there. At rounds 84–90, Harvester 43 reported `phase: harvesting` and `waiting_reason: no_destination` while its source-return journey was actively advancing (15, 14, 13, 12, 10, then 8 estimated turns). `fuel_transport._return_to_source()` retains the reason for returning until arrival. A return phase or separate return reason would avoid presenting this productive movement as a current wait. This was not a stuck logistics order.
- Add explicit phase/refinery guidance to Continuous Mine. At round 64 it showed full raw-metal cargo but an empty root `progress` object; its later child journey explained the delivery. The richer Continuous Resupply phase model is useful precedent.
- Improve wrong-mode ability errors. Calling `use_ability` for the equipped, ready `hazard_shielding` toggle returned “Ability hazard_shielding is unavailable on unit 69.” The correct `toggle_ability` command succeeded. Naming that command in the error would help semantic repair distinguish an equipped toggle from absent equipment.
- Make verbose runtime logging opt-in or rotate it. By the end, `game.log` and `control_stderr.log` had each grown to about **24.3 MB**. The detailed movement traces were useful for diagnosis, but two continuously appended verbose files are costly over repeated sessions. Retain bounded, useful diagnostics at the normal logging level.

## Validation and coverage

| Area | Result |
| --- | --- |
| Normal campaign creation | Correct starting units, default resources, unique homes, and homeworld population cap. |
| Opening batch | Seven operations accepted: load, queued colonization, automatic fuel service, two builds, another queued build, and fortification upgrade. |
| Resource reservations | Queued builds appear separately from paid work and reduce the three-resource available budget. |
| Stale turn token | Rejected with `stale_turn_token`. |
| Exact mutation replay after advancing | Returned the original cached receipt and original order IDs; no second application. |
| Request ID reused for changed content | Rejected with `request_id_conflict`. |
| Atomic preflight | Valid rename plus an obstructed Move rejected at command index 1; zero operations applied. |
| Unarmed stance | Rejected with `capability_unavailable`, including Do Nothing, as documented. |
| Boolean actor ID, unknown field, 31-character name | Rejected before commit with contract errors. |
| 41-command batch | Rejected with `invalid_commands`. |
| Nonexistent target | Uniform `target_unavailable` response. |
| Rejection side effects | Before/after observations had identical units, resource values, and order history. |
| Rename during paid construction | Accepted and preserved the build. |
| Unicode name | `Prieskum Šíp` survived the UTF-8 CLI request and observation round trip. Console rendering artifacts were not corruption in stored JSON. |
| Save existing name without overwrite | `save_exists`; protected existing save. |
| Save path traversal | `invalid_save_name`. |
| Save / menu / load | Successful; every observation section compared equal before/after, with a fresh turn token. |
| Patrol extension | Preserved root UUID and appended a complete waypoint. |
| Continuous queue blocking | Queued Move advertised the patrol's `blocked_by_order_id`. |
| Individual patrol cancellation | Cancelled the observed root and promoted the queued inter-system Move. |
| Carrier slot contract | Missing `template_name` rejected; index 2 rejected on a two-slot bay; explicit null accepted to clear a selection. |
| Paused production settings | Configured slots while paused; configuration was free and did not resume production. |
| Equipment overrides | Deployed Bomber had mass-driver/point-defense equipment; Long Range Bomber retained its beam/shield overrides. |
| Future production on occupied slot | Changing that slot to Recon did not alter the existing Long Range Bomber. |
| Tankless wing flight | Movement showed zero propulsion cost and no storage blocker. |
| In-game communications | Transmission and AI reply appeared chronologically; the next briefing reported incoming communications. |
| Insufficient queued construction budget | Rejected with exact credit shortfall before replacing a paid carrier build. |
| Recovery misuse | Retry/skip on a healthy Codex turn returned `ai_recovery_unavailable`. |
| Invalid wait / unknown action | Returned `invalid_timeout` / `unknown_action`. |
| CLI malformed inputs | Invalid UTF-8, NaN, non-object JSON, multiple objects, oversized payload and port 0 each produced exactly one JSON response and exit 2. |
| Completed opening colony / economy | Colony established at resolution 45; habitat completed at 46 and added its documented income. |
| Reuse of young colony ship | Loading the advised 7 from Moon 34 retained more than 10 population; second colonization was queued. |
| Lost-contact attack cancellation | Carrier and Long Range Bomber attacks both cancelled at resolution 49 with `target_not_visible`; briefing and terminal history recorded the outcomes. |
| Historical enemy colony | Ownership was dated `last_known`; population/defenses omitted and invasion probability null. |
| Recruitment/invasion projection | Recruitment of 20 followed by queued invasion accepted using the projected cargo prerequisite. Execution is tracked separately. |
| Gas-giant invalid projected queue | Enter → Move → Leave rejected before any operation applied. |
| Status during AI planning | A status request returned in 0.319 seconds while AI round 81 was planning and another client was waiting. This measures CLI round-trip responsiveness, not rendered FPS. |
| Wing docking/relaunch projection | Dock + relaunch in one batch rejected atomically with `wing_service_required`. Actual docking showed `launch_locked: true`; a separate same-turn relaunch also rejected. |
| Later serviced launch | Recon Wing 68 launched after its advertised ready round. |
| Cross-carrier docking | Long Range Bomber 54 adopted Fleet Carrier 62; new mother and servicing deadline appeared in its bay. |
| Dismantling | Six owner resolutions removed Shipyard 52 and paid exactly 425 credits, 16.5 metal and 5 crystal at resolution 82. |
| Construction overrides across long queue | Artillery Frigate 67 completed with both turrets changed to beam, their variants/ranges preserved, and combined 15 shields. |
| Carrier abilities | Evasive Formation activated; Attack Run exposed earliest release and replaced eligible bomber work; Emergency Recovery created a boosted return order and docking; repeated runs accepted after cooldown. |
| Resistance toggle | Wrong cast mode rejected; enabling via `toggle_ability` preserved the Move UUID and charged no immediate fuel, exposing the 2-AM upkeep. |
| Mining and refining | Miner carried 100 raw metal without adding it to the spendable balance; delivery at resolution 96 added exactly 100 metal and emptied the raw cargo. |
| Second colony / passive yield | Planet 26 settled at resolution 93; subsequent crystal income increased from 3 to 5 per round. |
| Competing colony mission | AI unit 46's colonization root recorded one `invalid_target` failure at resolution 93, when Planet 26 became enemy-owned. Its later memory correctly redirected the expedition to Planet 15. This expected order failure did not fail the AI turn. |
| Live semantic repair | Rounds 69 and 73 each rejected before mutation and succeeded on the first repair; typed lessons persisted. |
| Precision firing | At resolution 104, the Artillery Frigate dealt 15 damage to Kinetic Frigate 59's Engines; the briefing identified the public subsystem. |
| Mandatory 80-turn wing service | Bomber 53, launched on turn 24, triggered return at resolution 103, docked with mother 51, reset endurance to zero and advertised ready round 104. |
| Repair | Small Repair Ship 73 restored Carrier 51 from 64 to 88 hull HP over resolutions 104–106. |
| Resistance upkeep and real hazard | With protection active, Hazard Escort 69 moved 75 units in Medium debris at resolution 105, retained 100 HP and paid 2.75 AM including upkeep. Disabling protection preserved the same Move; the next equal step cost 0.75 AM and dealt exactly 2 hull HP. Protection was restored before saving. |

Supplementary offline verification: **125 passed, 10 subtests passed** across `tests/test_game_control.py`, `tests/test_ai_contracts.py`, `tests/test_ai_order_contract.py`, and `tests/test_playtest_ai_recovery.py` (11.74 seconds). The first attempt could not write the restricted environment's default temporary directory; rerunning with a workspace-local temporary directory succeeded. This is an environment workaround, not a game regression.

After investigating commit `9f89f68`, `tests/test_colony_planning.py` also passed all **3** cases (0.30 seconds), including the 10.1-population advisory case. Total supplementary verification: **128 tests plus 10 subtests**. These arithmetic/state tests passing does not establish that a live model interprets a forecast correctly.

## Limits of the evidence

This is one seeded live-model match, not a reproducibility guarantee for identical future model decisions. Engine arithmetic, the final-jump estimate discrepancy and command validation have direct evidence; the explanation of the false model lesson remains a well-supported inference.

No final AI failure or partial commit occurred, so successful manual retry/skip recovery was covered by the existing offline checks rather than a live forced failure. Normal construction pacing and starting resources kept Titans outside this run. Allied-team sharing, espionage, trade, boarding, mine deployment, bombardment, completed invasion, positive gas-giant entry/exit, victory conditions and long-term save/cache eviction were not exhaustively exercised. Gas-giant entry remained fuel-blocked by design. Receipts for ongoing missions establish issuance, not eventual completion.