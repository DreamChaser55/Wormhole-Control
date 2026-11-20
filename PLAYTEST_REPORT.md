# Wormhole Control playtest

20 November 2026 · Windows · Python 3.14.3

## Campaign

I launched the visible game with `DEBUG_LOG=true` through `python game_control.py` and played Codex Expedition against Luna Coalition, the integrated live OpenAI player. I used the Normal spawn profile, seed `20261120`, two radius-3 systems, and separate teams. Each faction started with 20,000 credits, 1,000 metal, 500 crystal, and a requested population of 50 subject to homeworld capacity. Luna used `gpt-6-luna` at Low reasoning with two semantic repair retries. The campaign ID is `2dc33dae`. Runtime code came from `6e34919a0a3d`. The repository advanced to `c1640120ccb8` during the run, a commit that only deleted the previous report.

I chose orders from player-visible observations and used the debug log, telemetry, saves, and AI memory to verify outcomes. The scope follows the project manuals and the local protocol and uses bridge version 4, observation schema 54, and command contract 28. [README](README.md) · [Reference](docs/REFERENCE.md) · [Development](docs/DEVELOPMENT.md) · [Agentic AI](docs/AGENTIC_AI.md) · [Codex Control](docs/CODEX_CONTROL.md)

I completed **100 full rounds, 200 resolved player turns**, and saved at the start of round 101 with Codex active. Both factions were still in play. Codex held three colonies and had 13 deployed units. Luna held the Procyon entrance and destroyed the Codex scout, artillery frigate, and long-range bomber wing. The siege and invasion fleets were still approaching their colony targets at the cutoff. [Final save](saves/pt26-final-r101.json) · [Round 101 observation](saves/pt26/r101-start.json.gz)

## Live AI results

| Measure | Result |
| --- | ---: |
| AI turns resolved | 100 |
| Recorded planning attempts | 101 |
| First-attempt plans accepted | 99 of 100 |
| Semantic repairs | 1, accepted on the next attempt |
| Accepted turns with no new orders | 64 |
| Median / p95 / maximum recorded latency | 7.03 s / 10.07 s / 31.43 s |
| Input tokens | 6,687,682 |
| Cached input tokens | 3,686,351 |
| Uncached input tokens | 3,001,331 |
| Output tokens | 72,121 |
| Total reported tokens | 6,759,803 |

The gateway recorded no live terminal AI failure or partial commit. The round-69 reload canceled one planning attempt that is absent from the telemetry. Many zero-command turns let active construction and travel continue. Luna established a colony, fortified two worlds, used reconnaissance and perimeter defense, pursued the scout, and adapted to bombers with Tracking Lock and Flak Barrage. [Telemetry](saves/ai_telemetry.jsonl) · [AI memory](saves/agent_memory/2dc33dae/d5fdf1b8/memory.md)

## Confirmed findings

### Medium · A destination in the wormhole exit sector gets unnecessary egress waypoints

In round 40, I sent Artillery Frigate 40 from Rigel to `[1000, -500]` in Procyon `[2, -3]`, the sector where the wormhole arrives. After the transit waypoint at `[0, 0]`, the plan sent the ship out to `[-636.91, 1764.57]`, then to `[1677.22, -838.61]`, and then back inside the field to the requested point. Siege Frigate 48 reproduced the route pattern in round 60 with a different exit heading. The wormhole blocks jumps within its field and permits sublight travel there.

The artillery route initially quoted 51 owner turns and 84 AM. Just before crossing, it quoted 31 turns and 55 AM. After the crossing consumed one turn and 25 AM, the forecast dropped to 12 turns and 12 AM while the active waypoint was still 1,876 units away and the frigate moved at 100 units per turn. I switched to combat at that point, so the discrepancy is in the planned route and forecast. Plan a collision-checked local leg from the exit when the destination is in that sector. Use the same geometry for the active route and its estimate. [Round 40 route](saves/pt26/r040-artillery-departure.json.gz) · [Pre-crossing](saves/pt26/r060-start.json.gz) · [Post-crossing](saves/pt26/r061-start.json.gz) · [Route planner](unit_orders/movement.py#L890)

### Medium · Jump failure loses the actionable fuel reason

Luna's Colonizer 32 loaded 10 colonists on round 59 and set out for Asteroid 20. The debug log identifies insufficient antimatter at its attempted jump on round 74. The saved order history records only `execution_failed`. The movement order maps the drive's generic error state to that code. At round 100 the AI remembered the stalled mission and had an objective to refuel the colonizer, which still had 5.75 AM and its 10 passengers.

Carry the bounded fuel failure code from the jump attempt to the parent order and the next briefing. Include the next jump's cost and shortfall in the planner's recovery context so it can arrange a transfer. [Launcher stderr, lines 107277 and 107286](saves/control_stderr.log) · [Final order history](saves/pt26-final-r101.json) · [Waypoint completion check](unit_orders/movement.py#L219)

### Medium · Paid fortifications are missing from the next owner briefing

I upgraded Rigel Planet 3 in round 1 and Moon 11 in round 73. Both upgrades applied. The Moon 11 upgrade debited exactly 250 credits, 25 metal, and 5 crystal. A two-upgrade batch in the same round correctly rejected with `cooldown_active` and applied zero operations. Neither the round-2 nor the round-74 opening briefing showed the upgrade, although the reference specifies a private upgrade report.

The general briefing window opens at End Turn. The upgrade calls the recorder during planning, when the owner's window is closed. Retain immediate private upgrade events for the next opening briefing and add a regression that issues the upgrade before End Turn. [Round 1 after orders](saves/pt26/r001-after.json.gz) · [Round 2 briefing](saves/pt26/r002-start.json.gz) · [Round 73 upgrade](saves/pt26/r073-fortification-retest.json.gz) · [Round 74 briefing](saves/pt26/r074-start.json.gz) · [Briefing recorder](turn_briefing.py#L133) · [Upgrade rule](docs/REFERENCE.md#planetary-warfare)

### Low · The socket accepts movement for a launched wing before the required observation

In round 64, the Escort Carrier's options advertised `requires_observation_after: true`. Launch plus Move in the same batch correctly rejected with `unit_unavailable` and applied zero operations. I then launched the Long Range Bomber Wing in one batch and immediately submitted a separate Move using its previously advertised bay ID and the same turn token. The bridge accepted the Move without an intervening observation. The next observation showed the wing deployed with the Move active.

The bridge records newly created IDs, while launch changes the containment of an existing ID. Track stored-to-deployed transitions as well, or narrow the advertised contract if the observation is intended as guidance. The earlier round-47 launch-plus-rename probe exercised a separate path because renaming explicitly supports stored craft. [CLI trace](saves/pt26/cli.jsonl) · [Round 64 deployed observation](saves/pt26/r064-bomber-deployed.json.gz) · [Bridge command handler](game_control_protocol.py#L327) · [Deployment contract](docs/AGENTIC_AI.md#commit-guarantees-and-lifecycle-feedback)

### Low · A transmission can render as several AI memory receipts

Luna sent one reply in round 4. Comms and telemetry showed one transmission. The memory sidecar displayed it as two action bullets, breaking at a semicolon inside the quoted message. The coordinator joins receipt strings with that punctuation and the Markdown renderer splits on it. Pass individual receipts to the renderer so message punctuation survives. The sidecar header also says it was generated from a save file even when the coordinator refreshes it during live play. Describe it as an export of current agent memory. [Comms export](saves/comms/2dc33dae/comms.md) · [Round 69 checkpoint with the original receipt](saves/pt26-active-ai-r069.json) · [Receipt assembly](game_ai/coordinator.py#L346) · [Markdown formatter](game_ai/memory.py#L247)

### Low · Canceled planning is absent from attempt telemetry

In round 69, a short wait returned `ready: false` with Luna in `planning`. I saved, returned to the menu, and reloaded the same round with Luna active. The replacement plan completed and the next observation advanced to round 70 once. The campaign telemetry contains a single accepted row for round 69 and no record of the retired plan. The docs describe an entry for every attempt. Record cancellations with elapsed time and unavailable usage so an interrupted turn can be reconstructed. [CLI trace](saves/pt26/cli.jsonl) · [Telemetry](saves/ai_telemetry.jsonl) · [Failure behavior](docs/AGENTIC_AI.md#failure-behavior)

### Low · Completed recruitment still advertises a pending action

The round-92 briefing and order history recorded 35 troops recruited on round 91. Troop Transport 47 had the 35 troops aboard and the same root reported `status: completed` and `active: false`, but the progress phase said `awaiting_owner_turn_resolution`. The root cleared in round 93. Derive the phase from terminal status before checking for approach or resolution so a planner can immediately recognize the transport as available. [Round 92 observation](saves/pt26/r092-start.json.gz) · [Order view](game_ai/order_view.py#L305)

### Low · AI commitments retain a destroyed combat target

The round-100 memory commitments still directed Flak Escort 50 to attack Long Range Bomber Wing 45 at 6 HP. The same memory recorded its confirmed destruction on round 99, and the accepted round-100 plan targeted the surviving bomber. Reconcile explicit combat commitments with terminal events during the requested fifth-round review. Retain the confirmed loss in important events. [AI memory](saves/agent_memory/2dc33dae/d5fdf1b8/memory.md) · [Telemetry](saves/ai_telemetry.jsonl)

## Gameplay and AI improvements

- **Prevent the empty-hold plan at the source.** In round 31 the live AI ordered Colonizer 32 to settle asteroid 20 with no colonists. The gateway rejected the batch atomically. One repair added a load of 10 at Planet 16 and queued settlement. The initial and repaired attempts took 7.03 s and 8.72 s. Put the conditional load-then-colonize action next to empty cargo in the planning context and keep this post-settlement case in evaluations. [Telemetry](saves/ai_telemetry.jsonl)
- **Give the AI stronger guidance on messages to rivals.** In its round-4 reply to a scouting inquiry, Luna volunteered its homeworld, its colonizer's destination, and two builds in progress. It followed up in round 10 asking for scouting information. Keep the option to negotiate and have the planner consider what tactical information each recipient should receive. [Conversation export](saves/comms/2dc33dae/comms.md)
- **Shorten the quiet opening or make its progress easier to read.** The first Codex colony order went in during round 1 and established Moon 11 in round 28. The Deep Survey Ship started in round 20 and reached its ordered position in round 55, matching the initial 35-turn estimate. The first detailed enemy ship contact appeared in round 38. These timings fit the current rules even on a compact map. An optional short-game start or more visible multi-turn milestones would help players who want earlier strategic choices. [Mission pacing](docs/AGENTIC_AI.md#evaluation) · [Round 29 briefing](saves/pt26/r029-start.json.gz) · [Survey route](saves/pt26/r020-survey-route.json.gz)
- **Quote travel and action fuel together for planetary orders.** In round 64 the bombardment options described the 10 AM volley and eligibility. The recruited transport's invasion preview focused on the 20 AM action and current or historical odds. The transport still had an estimated 80 owner turns of approach at the end of the run. Add the travel estimate and likely fuel remaining on arrival to recruitment, bombardment, and invasion previews. This would help planners decide whether to dispatch a tanker before committing a long journey. [Round 64 siege observation](saves/pt26/r064-siege-expedition.json.gz) · [Round 101 observation](saves/pt26/r101-start.json.gz) · [Planetary command contract](docs/AGENTIC_AI.md#planetary-warfare-contract)
- **Prioritize fuel and mineral supply alongside defensive construction.** Luna ordered six escorts and an Orbital Bastion and ended with 49 metal, 532 crystal, and about 2,912 credits. Its Bastion stalled for fuel at 26 of 29 turns, and the depleted colonizer remained idle. Surface near-term service and resource bottlenecks alongside the production queue. Give the planner an explicit fallback from new spending to mining, deliveries, or fuel recovery when these bottlenecks threaten existing work. [Telemetry](saves/ai_telemetry.jsonl) · [AI memory](saves/agent_memory/2dc33dae/d5fdf1b8/memory.md) · [Final save](saves/pt26-final-r101.json)
- **Reduce repeated prompt detail on quiet turns.** The median attempt used 67,637 input tokens, including 31,136 uncached tokens. Compacted changing context grew from about 53,000 characters in the first request to a peak of 145,000 on this two-system map. Keep the cacheable catalog, and measure reducing repeated option and estimate rows when the active orders and contacts have changed little. [Telemetry](saves/ai_telemetry.jsonl)
- **Make debug logs easier to scan.** The full launcher stderr reached 23.4 MB. About 97% of its logged records came from DEBUG pathfinding, and the rotating game log reached its three-backup limit. Separate route previews from actual movement traces so turn resolution and AI events are easier to find during long runs. [Launcher stderr](saves/control_stderr.log) · [Logging reference](docs/DEVELOPMENT.md#unit-references-in-logs)

## Verification

- **Bridge and persistence.** Tested launch, status, observation, command batches, End Turn, normal wait timeout, active-campaign protection, setup/state export, save listing, explicit overwrite, and reload. An invalid mixed batch applied zero operations. Replaying the same mutation ID returned the cached response and changing its payload conflicted. Stale turn tokens rejected. The round-8 reload retained balances, orders, history, and the frozen briefing and rotated the token. The round-69 reload during planning resumed the same AI owner turn. A premature retry during active planning rejected.
- **Economy and production.** Loaded and settled colonists twice. Tested queued price reservations, release of an unpaid reservation, a paid construction cancellation with a full three-resource refund, and fixed construction site validation. Applied weapon and defense overrides to Artillery Frigate 40. The mining ship delivered 100 crystal by round 71 and another 100 by round 98. The carrier produced two independently configured wings, paused and resumed production, and dismantled a docked wing for 129.5 credits, 5.5 metal, and 2 crystal. Clearing a production slot preserved its existing wing.
- **Movement, combat, and information.** Crossed the wormhole with the scout, observed detailed contacts and their public equipment, and received anonymous radar presence for undetailed contacts. Luna destroyed the scout and later the artillery frigate, which fired back at long range. Carrier bombers launched and engaged the defending escorts. A wing patrol accepted a waypoint edit and a Unicode rename while retaining its root. Docking and an immediate relaunch in one batch correctly rejected with `wing_service_required`.
- **Fuel and planetary operations.** An atmospheric queue with Move before Leave rejected atomically. The valid queue waited for fuel, resumed after a transfer, and completed Enter, Leave, and Move. The transport recruited 35 troops for 70 credits and 7 population before growth and upkeep. It then set out to invade. The siege frigate received a bombardment order. The destabilizer activated in round 96 and both endpoints showed 70% effective stability and 7.5 AM crossing loss from round 97 onward. Upkeep deducted 5 AM per owner turn. [Round 97 observation](saves/pt26/r097-start.json.gz)
- **Offline regression coverage.** 621 selected tests passed. They covered AI cancellation and failed-turn recovery, partial commit, briefings, wing production, wormhole stabilization, planetary warfare, attack visibility, fuel logistics, dismantling, and Titans. The Windows execution environment required scoped local socket access for Python's event loop.

The existing game credential supplied the live opponent. Usage figures come from provider telemetry. The live exercise used one seed and one reasoning setting. Manual mouse interaction, visual layout, allied coordination, and 80-turn wing endurance were outside the live scope.

## Evidence

- [CLI action and assertion trace](saves/pt26/cli.jsonl) and [compressed observations](saves/pt26/)
- [Game debug log](game.log), [launcher stderr](saves/control_stderr.log), and [AI telemetry](saves/ai_telemetry.jsonl)
- [AI memory sidecar](saves/agent_memory/2dc33dae/d5fdf1b8/memory.md) and [campaign comms](saves/comms/2dc33dae/comms.md)
- [Round 8 checkpoint](saves/pt26-checkpoint-r008.json) and [round 69 AI checkpoint](saves/pt26-active-ai-r069.json)
- [Round 101 final save](saves/pt26-final-r101.json)
