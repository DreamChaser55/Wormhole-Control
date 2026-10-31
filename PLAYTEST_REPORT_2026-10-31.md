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

The opponent responded sensibly to combat, used anti-strikecraft abilities, repaired an invalid plan, and withdrew a damaged scout. Two transient local control failures recovered safely without duplicate actions or state loss.

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

## Gameplay and interface improvement suggestions

### S02 — Planning payloads repeat substantial static and inapplicable information

The initial plan used about 51,000 input tokens despite a two-system map and four starting units. Early telemetry recorded a stable catalog of 109,211 characters and a dynamic section of 60,882 characters. Later observations exceeded 270 KB. Numerous actors repeat dismantling targets whose only result is `capability_unavailable`, and substantial rules/options recur across units.

Offer a compact observation/planning representation, deduplicate static catalogs, and omit target lists for categorically unavailable capabilities. Maintain schema discovery and fog-of-war guarantees. Consider an optional inexpensive “continue existing commitments” path during genuinely quiet turns, while retaining full planning for meaningful state changes. Zero-command plans alone do not prove that no reasoning was needed, especially during combat. Final telemetry measurements appear above; no monetary cost estimate is inferred.

### S06 — Offer fuel-service priorities and an optional partial-load departure threshold

At round 89 the automatic harvester selected Refinery 45 (164.25/200 antimatter), while Tender 44 had only 21.83/150 and was consuming 5 per turn to hold the wormhole stable. This matches the nearest-affordable-recipient policy in `antimatter_logistics.py:359`; it is not a violation of that policy. `unit_orders/fuel_transport.py` also waits for a full harvester tank before departing. Together, distance priority and full-load batching can delay urgent service.

Consider optional recipient priorities or an urgency score based on time until a unit stops working, plus a configurable minimum delivery load. Preserve the existing return-fuel reserve checks. The current manual-target and manual-transfer options are useful, but require intervention to protect continuous services.

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
| Wing replacement and recall | The lost bomber's replacement cost 259 credits, 11 metal, and 4 crystal; Wing 58 completed at resolution turn 93, retained the beam/shield overrides, and was deployed and commanded after observation. Recon Wing 41 returned to the moving carrier and reset its endurance. |
| Fuel starvation and recovery | Tender 44 stopped at round 94 with 1.83 antimatter; both wormholes reverted to natural stability 69, and a crossing colonizer took instability damage. Taking 50 antimatter from nearby Frigate 43 preserved the donor's attack order. Reissuing stabilization restored both endpoints to 100 at round 97. |
| Gas giant hiding | The scout's queued entry/exit completed at resolution turn 95. A second entry left it hidden through later rounds, with explicit hiding fields and only permitted commands exposed. An external movement attempt at round 97 was rejected as `invalid_state` without emerging the ship. |

## Evidence and limitations

The ignored local directory `saves/playtest_20261031/` contains the request/response pairs, `index.jsonl`, per-round observations, per-round opponent memory copies, protocol check results, encoding probes, and recorder scripts. `metrics.json` contains the final aggregates; `final_reload_check.json` records the final equality/token check. Checkpoint saves are named `saves/playtest_20261031_roundNNN.json`; the final save is `saves/playtest_20261031_final_round101.json`. Telemetry is in `saves/ai_telemetry.jsonl`; filter by campaign `96fe094c` because the file also contains older runs. `game.log` is likewise cumulative. The Markdown report is the only intended tracked deliverable; ignored evidence is retained locally and will not accompany a commit unless explicitly included.

This is one seeded campaign and a set of targeted interface probes, not exhaustive feature coverage. No deliberate provider outage, credential failure, transport break, or partial-commit fault was injected. Semantic repair and two naturally occurring transport interruptions were observed; manual AI retry/skip, exhausted repair budgets, and partial-commit recovery were not exercised. The two negative transport results are retained in the index; reusing the request IDs overwrote their per-request response files with successful retry responses.

Other untested areas include Titan powers and capacity, most specialized abilities, diplomacy/messages, trade, espionage, minefields, boarding/capture, planetary bombardment/invasion, general hangars for non-wing craft, refitting, multiplayer/human handoff, and most GUI workflows. Recruitment was tested, but no invasion completed. Repair covered hull damage, not destroyed subsystems. Wing replacement and recall were tested, but endurance exhaustion and damaged-wing replenishment were not. Only crystal mining/refining was exercised directly. Suggestions above do not claim that every suspected edge case is a reproduced bug.

Preserve the successful atomic-preflight, token, fog-of-war, and save-restoration behavior while addressing the remaining findings.
