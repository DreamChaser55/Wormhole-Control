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
