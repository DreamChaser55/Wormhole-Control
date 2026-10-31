# Wormhole Control playtest — 2026-10-31

## Scope and environment

This report records a live game against the built-in agentic opponent, controlled through `python game_control.py`. The requested `README.md`, `docs/REFERENCE.md`, `docs/DEVELOPMENT.md`, and `docs/AGENTIC_AI.md` were read before play, together with the game-control skill and control-interface documentation. Findings distinguish observed defects, opponent decisions, and design suggestions. No game source or production configuration was changed.

- Repository revision: `b4ff43da3fe18e91caf2c7add1fbeb46ae584ea6`.
- Windows, Python 3.14.3; visible local game process.
- Campaign `96fe094c`; seed `20261031`; Normal start; two systems, radius 3, wormhole density 1, default successful generation spacing.
- Codex Playtester versus Luna Rival, opposing teams. Built-in opponent: `gpt-6-luna`, medium reasoning, two configured repair retries, agent `580a1eaa`.
- Initial resources: 20,000 credits, 1,000 metal, 500 crystal; initial home population 50.
- All mutations went through the JSON control interface. Saves, logs, telemetry, memory sidecars, and source were read for diagnosis, as authorized. Enemy targets for gameplay came from public observations.
- The recorder explicitly set UTF-8 for child-process input/output.
- UI inspection covered the galaxy view and Reset View. The user stopped computer-use automation with Escape; subsequent play continued exclusively through the control interface.

## Result and run measurements

**Completed 100 full rounds: 100 player turns and 100 opponent turns, ending at the start of round 101.** The game remains open there. There was no campaign reset, checkpoint replay, or confirmed crash. Both the early and final save/reload checks reproduced the complete parsed observation exactly and rejected the old token afterward.

The strongest defects are the wormhole route detour (F02) and successful docking being recorded as cancellation (F08). The opponent also discarded almost-finished construction (F03), but it later responded sensibly to combat, used anti-strikecraft abilities, repaired an invalid plan, and withdrew a damaged scout. Two transient local control failures recovered safely; their cause remains unresolved (F07).

| Measurement | Result |
| --- | --- |
| Completed rounds verified from receipts and AI telemetry | Exactly 1–100, with observations for 1–101 |
| Final save | `saves/playtest_20261031_final_round101.json` |
| Final save/reload | Full observation equal; fresh token; old-token end turn rejected |
| Accepted opponent plans | 100 |
| Total opponent planning attempts | 101: one preflight rejection at turn 72, followed by a successful automatic repair |
| Accepted zero-command plans | 73; many preserved ongoing travel, construction, and logistics |
| Provider/commit failures requiring manual recovery | None observed |
| Recorded control calls | 299, including negative probes and retries; standalone startup/status/encoding probes are additional |
| Command coverage | 33 command types probed; 32 successfully applied through the player interface |
| Observation response size | 183,584–298,988 bytes |
| AI request latency | Median 11.09 s; maximum 55.537 s; total 1,365.551 s across all 101 attempts |
| AI input tokens | 6,328,048 total: 3,401,500 cached and 2,926,548 uncached |
| AI output tokens | 115,332 |
| Input tokens per attempt | Minimum 51,066; median 57,690; maximum 79,427 |
| Final player treasury | 6,603.30 credits; 319.5 metal; 903.5 crystal |

At the endpoint, the player held two colonies and 18 units including the submerged scout and docked recon wing; the opponent held three colonies and 13 units. The player lost one bomber in combat and deliberately dismantled one cutter; automatic production replaced the bomber. The opponent's home shipyard survived with damage, and the opposing scout survived the artillery engagement. The match remained in progress; this report does not claim a victory. Ongoing work includes mining, resupply, combat movement, and colony approaches. The scout is safely submerged with only 2 antimatter, and the refueled stabilizer is active.

Round numbers below refer to the observation at the start of the player's turn unless an event's resolution turn is stated explicitly. Aggregate AI measurements include the rejected attempt and its repair, and cover only campaign `96fe094c`.

## Confirmed defects and actionable findings

### F02 — Replacing an order near a wormhole creates an unnecessary out-and-back detour (high priority)

**Observed:** Artillery Frigate 43 was approaching Procyon's wormhole 25 and stood approximately `[175.19, 0]` from its center at round 59. Replacing its movement order with a legal long-range attack against visible enemy Shipyard 30 generated these first route legs: `[1875.19, 0]` in the same wormhole sector, then `[0, 0]` in that sector, then the destination wormhole in Kepler-186. The ship actually reversed direction: positions were approximately 375 at round 61, 475 at round 62, and 675 at round 64. The destination remained in the other system.

**Impact:** A routine tactical order change adds roughly 3,400 units of unnecessary movement, about 34 owner turns at this ship's speed, plus fuel. This strongly discourages adapting orders during the already lengthy travel phase.

**Likely source:** `unit_orders/movement.py:830` adds an inhibition escape before selecting the intersystem route. The direct-wormhole branch at `:871` then routes the same ship back to the wormhole center. Departure from the entry wormhole through that wormhole should not require first escaping its own field.

**Suggestion:** Choose the actual next transport leg before applying departure inhibition. Skip the generic escape when the next leg is local approach to, or transit through, the current entry wormhole. Add a regression with a ship already inside the entry wormhole's field and an order replaced with a cross-system attack.

**Evidence:** Artillery Frigate 43 in `round_059.json`, `round_061.json`, `round_062.json`, and `round_064.json` under the evidence directory.

### F03 — Opponent cancels a nearly completed build after inferring a completion that did not happen (medium priority)

**Observed:** At AI turn 35, Shipyard 30 replaced a Colonizer build that had completed 17 of 18 construction turns with another Colonizer build at a different position. The cancellation refunded the paid resources, but discarded 17 turns of production. The memory snapshot after AI turn 34 correctly said to preserve the 16/18 build; the next memory incorrectly asserted that the previous Colonizer had completed, although no new unit appeared. The save's order history records the original order as cancelled at turn 35. Replacement Colonizer 47 finally completed at resolution turn 52.

**Impact:** The opponent loses expansion time and undermines its own stated strategy. This was a decision-quality failure in an accepted plan, not an API or command-validation failure. Most other turns preserved existing work correctly.

**Suggestion:** Treat the current order and explicit completion history as authoritative over remembered elapsed time. Expose a replacement consequence such as “cancels 17/18 completed construction turns” in options/receipts, and add this snapshot to planning evaluations. Consider a preflight warning for replacing paid work close to completion without preventing deliberate replacement.

**Evidence:** `memory_round_035_580a1eaa.md`, `memory_round_036_580a1eaa.md`; cancelled root order `e3b7fc0e584a4e9ca54c5c8b22e7f15c` in the campaign save history; matching construction cancellation/start entries in `game.log`.

### F04 — Third-party logging filter misses the active `httpcore2` logger family (medium priority)

**Observed:** `game.log` contains DEBUG HTTP response-header traces from `httpcore2.http11`, including account/project/request identifiers and rate metadata. The configured quiet list covers `httpcore` and `httpx2`, but not `httpcore2`. No API key or prompt-body leak was observed; this report deliberately omits the header values.

**Impact:** Normal gameplay creates noisy diagnostic output and exposes more account metadata than expected when logs are shared for support.

**Suggestion:** Include the active transport's logger hierarchy in the suppression policy and redact sensitive response metadata independently of package naming. Test representative `httpcore`, `httpcore2`, `httpx`, and `httpx2` records without real credentials.

**Evidence/source:** `game_logging.py:7`; `httpcore2.http11` entries during this campaign in `game.log`.

### F05 — Wormhole approach is described as leaving an inhibition field (medium/low priority)

**Observed:** At round 32, Carrier 37 was moving inward from approximately `[875.19, 0]` toward the entry wormhole center, but its journey reported `phase: egress`. The human label for that phase is “Leaving inhibition field.” The actual movement continued correctly in this case.

**Impact:** Both agents and users receive the opposite explanation of what the ship is doing. This is separate from F02's actual detour.

**Likely source:** `game_ai/order_view.py:59` classifies a local leg as egress whenever it is not in the final destination sector; `:69` reinforces that classification inside any known inhibition zone. `:129` supplies the human label.

**Suggestion:** Distinguish entry-wormhole approach from departure escape and destination approach using the active leg's purpose. Validate phase labels against direction and waypoint semantics.

**Evidence:** Carrier 37 in `round_032.json`.

### F06 — Reset View does not frame a small generated galaxy usefully (low priority)

**Observed:** The two-system galaxy at round 21 occupied a tiny cluster near the bottom-left of a 1707×960 game window, leaving most of the viewport empty. Reset View (`R`) retained that framing.

**Likely source:** `game_camera.py`, `reset_galaxy_camera`, restores fixed zoom and zero pan rather than fitting occupied system bounds.

**Suggestion:** Fit generated systems with padding, or offer separate “Fit systems” and “Full galaxy bounds” controls. Test both sparse two-system and dense maps.

**Evidence:** `saves/playtest_20261031/galaxy_reset_round21.png`. Other UI workflows were not evaluated after computer-use was stopped.

### F07 — Two transient control failures; the error text does not identify the failure phase (unresolved, medium priority)

**Observed:** At round 91, request `pt-91276a5376934dff9e7f6e1faec66a6f` returned CLI exit 2 and `connection_failed` after 6.169 seconds, with “No Wormhole Control server is listening.” A subsequent status request immediately found the same campaign, round, and token. It did not print the launch message. Retrying the original request with its original ID/token succeeded, and the game continued. No checkpoint replay was needed. No corresponding traceback appeared in `game.log`.

The same symptom recurred on the end-turn request at round 99 (`pt-d9e2f449967b4d619433f4add09be60b`), after 8.036 seconds. Retrying that exact request also succeeded and ended round 99 once.

**Interpretation:** The interruption's cause is unconfirmed. It is not evidence that the game crashed or lost state. The existing main exception branch groups connection refusal and timeouts under the same definitive message, which makes diagnosis harder.

**Suggestion:** Improve the diagnostics to elucidate the cause of such failures. Preserve the underlying transport phase/cause in structured CLI errors, distinguish connection refusal from connection/read timeout, and include a retry hint that retains the request ID. Keep startup/runtime stderr somewhere inspectable rather than discarding all child-process stderr. Investigate intermittent local transport failures under a long-running session; these two recovered events do not establish a deterministic engine defect.

**Evidence/source:** The failed and successful entries for the same request ID in `saves/playtest_20261031/index.jsonl`; `_send`, `_launch_game`, and `main` in `game_control.py`.

### F08 — Successful manual wing docking is recorded as cancelled (medium priority)

**Observed:** Recon Wing 41 received `dock_in_strikecraft_bay` at round 83 and successfully docked in moving Carrier 37 at resolution turn 94. At round 96 it was present in the carrier's docked list, ready for launch, with endurance reset to 80. However, order-history event 47 records its explicit `dock` order `5193668762fa4d908f0820cdc340121a` as `outcome: cancelled`, `reason: cancelled`, turn 94. No command cancelled that wing's docking order.

**Impact:** The terminal journal contradicts the actual successful action. An agent using completion history can infer failure, replan needlessly, or write incorrect memory even though the bay state is correct.

**Likely source:** `unit_orders/hangar.py:90` calls `docking_component.dock(...)` before setting the dock order to completed. `unit_components/strikecraft.py:470` clears explicit orders during docking. The dedicated recovery path in `unit_orders/strikecraft.py:192` already marks completion before this cleanup, but the ordinary docking path does not. Approach-wrapped roots need the same protection, not just their internal docking child.

**Suggestion:** Record the successful explicit root's completion before cleanup cancels remaining work, without declaring completion on a failed dock. Test both immediate in-range docking and approach-to-moving-carrier docking, asserting exactly one `completed` terminal event and preserved docked state after save/load.

**Evidence:** `round_095.json` and `round_096.json`, carrier bay state and order-history event 47; the round-83 docking request in the evidence directory.

## Gameplay and interface improvement suggestions

### S01 — Early expansion and first contact take many low-decision turns

The initial colony mission was issued at turn 1 after loading 20 colonists. It settled the second home-system planet at resolution turn 48, visible at round 49. The opponent's first additional colony also appeared around that point. Carrier 37, completed at turn 20, reached a useful position in the rival home sector only at resolution turn 61. These missions progressed; they were not frozen. The existing documentation already acknowledges slow travel.

Consider a faster match preset, shorter early inhibition approaches, or starter propulsion tuned for smaller maps. Event-driven advancement could help quiet periods if it stops for contacts, combat, shortages, completed production, and failed orders. Retain explicit user control over irreversible turn advancement.

### S02 — Planning payloads repeat substantial static and inapplicable information

The initial plan used about 51,000 input tokens despite a two-system map and four starting units. Early telemetry recorded a stable catalog of 109,211 characters and a dynamic section of 60,882 characters. Later observations exceeded 270 KB. Numerous actors repeat dismantling targets whose only result is `capability_unavailable`, and substantial rules/options recur across units.

Offer a compact observation/planning representation, deduplicate static catalogs, and omit target lists for categorically unavailable capabilities. Maintain schema discovery and fog-of-war guarantees. Consider an optional inexpensive “continue existing commitments” path during genuinely quiet turns, while retaining full planning for meaningful state changes. Zero-command plans alone do not prove that no reasoning was needed, especially during combat. Final telemetry measurements appear above; no monetary cost estimate is inferred.

### S03 — Show active construction progress at the top level of approach-wrapped orders

Constructor 27's refinery construction retained an outer construction order with an empty `progress` object while the inner active construction node held the actual completed/required turns. The full tree contains the information, so this is not lost state. A consistent root `active_phase` and construction progress summary would reduce recursive parsing and make idle, approaching, building, and stalled states easier to distinguish.

Similarly, Harvester 29 reported `phase: harvesting` together with `waiting_reason: no_destination` while successfully accumulating fuel at the pulsar (49.33 at round 86, 71.87 at round 87). Recipients needed fuel, but the current load was insufficient for a viable delivery. Distinguishing “building delivery reserve” from “no eligible recipient” would make this healthy state easier to recognize. Falling fuel during the preceding approach was explained by movement plus pulsar drain; it was not a harvesting failure.

### S04 — Generate close-spaced sparse maps more reliably

An initial valid two-system configuration with seed `20261031`, minimum spacing 50 and maximum spacing 100 failed after 100 placement attempts, placing only one system. The failure was safe and left the main menu intact. Default spacing succeeded. Consider sampling within valid annuli of existing systems rather than repeatedly sampling the full galaxy, or report the feasible region/placement constraints more explicitly. This is a generation robustness suggestion, not evidence of state corruption.

### S05 — Consider a balanced starting-resource option

This seed gave the player an ice homeworld and nearby crystal sources, but no local metal asteroid. The rival had a ferrous homeworld with metal income and a local metal asteroid. The starting metal reserve supports an initial fleet, but the player's ongoing metal supply requires travel or another strategy. Asymmetric starts can be intentional; an optional comparable-resource start would make competitive playtests easier to interpret.

### S06 — Offer fuel-service priorities and an optional partial-load departure threshold

At round 89 the automatic harvester selected Refinery 45 (164.25/200 antimatter), while Tender 44 had only 21.83/150 and was consuming 5 per turn to hold the wormhole stable. This matches the nearest-affordable-recipient policy in `antimatter_logistics.py:359`; it is not a violation of that policy. `unit_orders/fuel_transport.py` also waits for a full harvester tank before departing. Together, distance priority and full-load batching can delay urgent service.

Consider optional recipient priorities or an urgency score based on time until a unit stops working, plus a configurable minimum delivery load. Preserve the existing return-fuel reserve checks. The current manual-target and manual-transfer options are useful, but require intervention to protect continuous services.

### S07 — Account for a new colony's growth when reusing its colonizer

The opponent founded Moon 23 at resolution turn 90, then loaded 10 colonists from it on turn 91. That left approximately 0.1 population; the final save shows only 0.110462 at round 101. The action was legal and preserved the required residual population, but left the new colony with negligible growth and income for the remaining test.

Consider an AI planning preference for a meaningful retained population, with exceptions for urgent evacuation or deliberate rapid expansion. Compare the value of a new expedition against the donor colony's recovery time. This is a strategy-quality suggestion, not a command-validation defect.

## Validation and coverage

The following were exercised through the running game's control interface, with request/response records retained:

| Area | Observed result |
| --- | --- |
| Launch and lifecycle | CLI launch, visible game, main menu, start-game validation, and rejection of replacing an active campaign worked. Failed generation left the menu usable. |
| Retry identity | Exact request replay returned the cached response; changed content under the same ID returned `request_id_conflict`. |
| Turn authority | Stale command/end-turn tokens and commands/observations on the opponent's turn were rejected. |
| Input contracts | Boolean IDs, unknown command fields, missing required position, unsupported protocol, unknown action, and invalid wait bounds were rejected. |
| Batch preflight | A batch containing a valid rename followed by an invalid move applied neither operation. A 41-command batch was rejected. |
| Fog of war | A hidden enemy ID and an absent ID returned the same generic `target_unavailable`; the failed probes left unit state unchanged. Visible enemy weapons were public while fuel, orders, and private hull accounting were omitted. |
| Save/load | Save, return to menu, and reload at rounds 12 and 101 reproduced the full parsed observation exactly, including order IDs, progress, and resources. The final check also preserved hidden/docked units and continuous services. Old tokens were rejected. Traversal and overwrite-without-permission checks passed. |
| Order management | Patrol append preserved its ID and active leg; queued movement exposed its blocker; cancelling the queued order and clearing explicit orders preserved the stance. |
| Economy | Paid construction reserved all three resources. Same-turn cancellation of a Missile Platform refunded exactly 400 credits, 15 metal, and 5 crystal. A second cancellation produced no second refund. |
| Construction customization | Beam/shield overrides appeared correctly on the completed Artillery Frigate, including weapon range/cooldown and defense values. |
| Colonies and income | Colonist loading, colonization, population growth, mineral income, and the Civilian Habitat's income operated. |
| Fuel logistics | Continuous resupply harvested at a pulsar and delivered to multiple ships; reserve behavior and environmental drain were visible. |
| Wormholes | Unstable transit damaged the scout by 8 HP. A tender subsequently maintained both endpoints at effective stability 100, with 5 antimatter upkeep per owner turn. |
| Carriers | Slot validation, production, overrides, queued deployment after travel, future-template changes, and enable/disable controls worked. Changing the future template did not replace an existing Recon Wing or erase movement orders. |
| Dismantling | A full-health Patrol Cutter went offline during its three-turn dismantling and returned exactly 200 credits, 7.5 metal, and 2.5 crystal. |
| Mining | The drone's one-shot mine plus queued unload filled 40 raw crystal and delivered all 40 to the refinery at resolution turn 68. A larger ship and the drone were also assigned continuous mining. |
| Environmental ability | A 75-unit sublight move in debris caused 2 HP damage without shielding. Four equivalent shielded moves caused no further integer HP loss; each consumed 0.75 movement antimatter plus 2 ability upkeep. The toggle was disabled afterward. |
| Subsystem targeting | Bomber Wing 38 hit Shipyard 30's Constructor for 5 component damage at resolution turn 70 while leaving hull HP at 50. Switching to a hull attack subsequently reduced hull HP to 45. |
| Natural AI repair | At AI turn 72, a stationary shipyard's out-of-range build was rejected during preflight with zero applied operations. The automatic repair attempt corrected the location and succeeded on the same turn; no manual skip or retry was needed. |
| Manual fuel transfer | Refinery 45 transferred 35.75 antimatter to Escort 51 over two owner turns, filling the recipient to 100 and leaving the donor at 164.25. An unsupported `amount` field in an earlier operator request was correctly rejected without effects. |
| Repair | Repair Ship 55 restored Escort 51 from 98 to 100 HP at resolution turn 85 and charged 2 credits. |
| Long-range weapons | Artillery Frigate 43 hit the visible invading Scout 52 for 20 hull HP at resolution turn 87. |
| Opponent combat abilities and loss | The opponent used Tracking Lock and Flak Barrage against Bomber Wing 38. The wing was destroyed at resolution turn 90; its carrier slot became empty and the loss appeared in the briefing. |
| Troop recruitment | Transport 54 recruited 20 troops at resolution turn 90, paying 40 credits and 4 population before ordinary growth/income. Cargo showed 20/40 afterward. |
| Transient transport recovery | Failures at rounds 91 and 99 recovered with each original request ID and token, without losing state or advancing a turn twice. |
| Wing replacement and recall | The lost bomber's replacement cost 259 credits, 11 metal, and 4 crystal; Wing 58 completed at resolution turn 93, retained the beam/shield overrides, and was deployed and commanded after observation. Recon Wing 41 returned to the moving carrier and reset its endurance; its incorrect journal outcome is F08. |
| Fuel starvation and recovery | Tender 44 stopped at round 94 with 1.83 antimatter; both wormholes reverted to natural stability 69, and a crossing colonizer took instability damage. Taking 50 antimatter from nearby Frigate 43 preserved the donor's attack order. Reissuing stabilization restored both endpoints to 100 at round 97. |
| Gas giant hiding | The scout's queued entry/exit completed at resolution turn 95. A second entry left it hidden through later rounds, with explicit hiding fields and only permitted commands exposed. An external movement attempt at round 97 was rejected as `invalid_state` without emerging the ship. |

## Evidence and limitations

The ignored local directory `saves/playtest_20261031/` contains the request/response pairs, `index.jsonl`, per-round observations, per-round opponent memory copies, protocol check results, encoding probes, and recorder scripts. `metrics.json` contains the final aggregates; `final_reload_check.json` records the final equality/token check. Checkpoint saves are named `saves/playtest_20261031_roundNNN.json`; the final save is `saves/playtest_20261031_final_round101.json`. Telemetry is in `saves/ai_telemetry.jsonl`; filter by campaign `96fe094c` because the file also contains older runs. `game.log` is likewise cumulative. The Markdown report is the only intended tracked deliverable; ignored evidence is retained locally and will not accompany a commit unless explicitly included.

This is one seeded campaign and a set of targeted interface probes, not exhaustive feature coverage. No deliberate provider outage, credential failure, transport break, or partial-commit fault was injected. Semantic repair and two naturally occurring transport interruptions were observed; manual AI retry/skip, exhausted repair budgets, and partial-commit recovery were not exercised. The two negative transport results are retained in the index; reusing the request IDs overwrote their per-request response files with successful retry responses.

Other untested areas include Titan powers and capacity, most specialized abilities, diplomacy/messages, trade, espionage, minefields, boarding/capture, planetary bombardment/invasion, general hangars for non-wing craft, refitting, multiplayer/human handoff, and most GUI workflows. Recruitment was tested, but no invasion completed. Repair covered hull damage, not destroyed subsystems. Wing replacement and recall were tested, but endurance exhaustion and damaged-wing replenishment were not. Only crystal mining/refining was exercised directly. Suggestions above do not claim that every suspected edge case is a reproduced bug.

Recommended follow-up order: fix F02/F08, add regression coverage from the retained snapshots, improve AI commitment/population decisions, then evaluate payload size and pacing on several seeds. Preserve the successful atomic-preflight, token, fog-of-war, and save-restoration behavior while making those changes.
