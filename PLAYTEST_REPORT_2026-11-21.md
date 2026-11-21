# Wormhole Control — 205-Turn Playtest Report (2026-11-21)

## 1. Executive Summary & Playtest Setup

This report documents a **205-turn live playtest** of **Wormhole Control** driven through the `python game_control.py` local control interface (Protocol v4, Observation Schema v59, Command Contract v28) against the integrated live OpenAI AI (**Luna**, `gpt-6-luna`, `medium` reasoning effort) with `DEBUG_LOG=true`.

| Parameter | Value |
|---|---|
| **Campaign ID / Seed** | `babda014` / `20261121` |
| **Players** | `Antigravity` (`codex`, Team 1, Epsilon Eridani) vs. `Luna` (`openai`, Team 2, `medium` reasoning, 2 repair retries, Betelgeuse) |
| **Galaxy Settings** | 4 systems (`Epsilon Eridani`, `Proxima Centauri`, `Rigel`, `Betelgeuse`), radius 3–4, wormhole density `0.65`, Normal spawn (`20,000` credits, `1,000` metal, `500` crystal, `50` pop) |
| **Turns Played** | Turns 1–205 (204 completed AI turns, 205 OpenAI API attempts) |
| **Debug & Telemetry Logs** | `game.log` (13,977 lines, **0** `[WARNING]`/`[ERROR]`/`[CRITICAL]`/tracebacks), `saves/ai_telemetry.jsonl`, `saves/agent_memory/babda014/abc4d3e6/memory.md`, `saves/comms.md` |
| **Checkpoints Saved** | `saves/playtest_t62.json`, `saves/playtest_t100.json` (used for live save/load roundtrip), `saves/playtest_t205.json` |

### High-Level Verdict

- **Core engine & protocol stability are strong:** 205 turns ran with zero crashes, zero exceptions, zero commit failures, zero protocol mismatches, and a clean mid-campaign `save_game → return_to_menu → load_game` roundtrip at Turn 100.
- **Built-in AI schema reliability is outstanding:** Luna achieved a **99.5% first-attempt acceptance rate** (**204 accepted turns, only 1 semantic repair** on Turn 181, which succeeded on Retry 1), with zero failed turns and coherent multi-turn memory reconciliation.
- **Significant gameplay & AI bottlenecks were uncovered:** The single highest-impact discovery is a **critical antimatter-logistics bug** (`service_fuel_horizon()` excludes active/stalled construction and lacks recipient hysteresis) that interacted with `protect` to trap Luna's Harvester in a self-feeding bodyguard loop and **starve Luna's Shipyard for ~70 turns**. Several additional order-lifecycle, mining, movement, privacy, balance, and AI-planning issues were also identified and verified in code.

---

## 2. Antigravity Playtesting Workflow Notes (Codex Skill Compatibility)

Because `.agents/skills/wormhole-control/SKILL.md` was authored for OpenAI Codex CLI, two Windows/Antigravity environment differences surfaced immediately and should be noted if running future playtests in Antigravity:

1. **Detached child processes are terminated between `run_command` calls in Antigravity:**
   - When `game_control.py` auto-launches `game.py` (`CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS`), Antigravity's per-command job/session cleanup terminates the spawned `game.py` once `game_control.py` exits.
   - **Workaround used:** Launch `DEBUG_LOG=true python game.py --port 47653` once as an Antigravity daemon (`IsDaemon=true`), then drive all game commands through `python game_control.py --no-launch -`. This worked flawlessly for the entire 205-turn session.
2. **PowerShell 5.1 JSON argument quoting in `docs/CODEX_CONTROL.md`:**
   - The quick-start example `python .\game_control.py '{"action":"status"}'` in `docs/CODEX_CONTROL.md` fails under Windows PowerShell 5.1 (`Invalid JSON: Expecting property name enclosed in double quotes`) because PowerShell 5.1 strips inner double quotes when passing arguments to native binaries.
   - Piping UTF-8 JSON over stdin (`'{"action":"status"}' | python .\game_control.py -` with `$OutputEncoding = [System.Text.UTF8Encoding]::new($false)`) works reliably. Updating the PowerShell quick-start snippet in `docs/CODEX_CONTROL.md` to use stdin piping (or escaped quotes) will prevent first-run friction on Windows.

---

## 3. Quantitative AI & Telemetry Performance (204 Turns)

From `saves/ai_telemetry.jsonl` (campaign `babda014`, Turns 1–204):

| Metric | Value |
|---|---|
| Total API Attempts / Completed Turns | 205 attempts / 204 turns |
| First-Attempt Acceptance / Repairs | 203 / 204 (99.5%) first-try; **1** repair (Turn 181, succeeded on attempt 1) |
| Zero-Command Turns | 137 / 204 (67.2%) |
| Total AI Wall Latency | 3,263.3 s (54.4 min) |
| Latency (Avg / Median / Min / P95 / Max) | **15.92 s** / 14.43 s / 5.32 s / 29.86 s / 41.27 s |
| Total Input Tokens (Cached / Uncached) | 15,107,642 (7,524,540 cached = **49.8%**, 7,583,102 uncached) |
| Total Output Tokens (Reasoning Share) | 345,332 (241,000 reasoning = **69.8%**) |

### Prompt Size & Cache Efficiency Scaling Over Campaign Length

| Turn | Latency | Input Tokens | Cached Input | Cache % | Output (Reason) | `units` (raw → compact chars) | `order_history` (compact) | `quiet_quote_rows_omitted` |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 31.6 s | 57,569 | 0 | 0.0% | 2,596 (1,848) | 63,022 → 15,092 | 125 | 0 |
| 2 | 20.5 s | 60,151 | 36,885 | 61.3% | 1,986 (1,419) | 69,949 → 22,422 | 371 | 28 |
| 50 | 15.0 s | 65,377 | 36,885 | 56.4% | 1,528 (993) | 92,539 → 31,807 | 1,884 | 67 |
| 100 | 8.0 s | 71,795 | 36,885 | 51.4% | 838 (429) | 108,313 → 42,091 | 6,658 | 56 |
| 150 | 21.4 s | 77,165 | 36,885 | 47.8% | 2,012 (1,624) | 136,522 → 50,797 | 9,066 | 99 |
| 181 (a=0) | 31.4 s | 92,866 | 36,885 | 39.7% | 3,939 (2,775) | 180,005 → 85,262 | 11,628 | 0 |
| 204 | 18.8 s | 98,182 | 36,885 | 37.6% | 2,171 (1,515) | 201,318 → 95,707 | 14,595 | 0 |

**Key takeaway:** Prompt caching worked consistently (`36,885` cached prefix tokens on every single turn from Turn 2 onward), and shared-value compaction saved ~32K–67K characters per request. However, as fleet size reached just ~14 units on a 4-system map, the dynamic `units` section grew **6.3×** (15 KB → 95.7 KB compact; 201 KB raw) and `order_history` reached 14.6 KB, pushing input tokens toward 100K/turn and eroding cache hit rate from 61.3% to 37.6%. On larger 15–30 system late-game maps with 30+ units, dynamic prompt growth could become a major cost and latency bottleneck.

### Luna's Command Mix (Turns 1–204)

`colonize` (18), `load_colonists` (17), `give_antimatter` (16), `construct` (14), `upgrade_planetary_defenses` (12), `move` (7), `attack` (6), `take_antimatter` (5), `continuous_resupply` (4), `protect` (4), `cancel_order` (3), `send_message` (2), `use_ability` (2), `continuous_mine` (1), `defend` (1).

---

## 4. What Worked Well (Verified Subsystems)

- **Protocol & Preflight Atomicity:** Rejections (`target_out_of_range` on Turn 13, `capability_unavailable` on Turn 138 for `set_stance` on unarmed Siege Frigate) cleanly applied 0 operations, preserved turn tokens, and returned exact indexed error details.
- **Transactional Persistence (`save_game` / `return_to_menu` / `load_game`):** Roundtrip at Turn 100 preserved all units, orders, UUIDs, budgets, and Luna's agent memory with zero drift.
- **Equipment Customization Overrides:** Both `construct` (`KINETIC_FRIGATE` with `turret_type_override: "beam"`, `defense_type_override: "shields"` → 2 Beam turrets + 27.0 Shields) and `set_wing_production` (`BOMBER_WING` with `beam` + `shields` → Beam turret + 1.5 Shields) applied accurately and persisted into live combat.
- **Strikecraft Lifecycle:** `set_wing_production`, `deploy_all_wings` + observe-then-command workflow, tankless wing flight (`antimatter_per_shot: 0.0`), target-class filtering (Recon Wing excluded `attack` against non-wing Patrol Escort), endurance counter (`turns_outside`), and `dock_in_strikecraft_bay` all functioned cleanly.
- **Wormhole Stabilization:** `stabilize_wormhole` raised Wormhole 28 from `41%` (`14.75` AM crossing loss) to `100%` (`0.0` loss, `stability_status: "stabilized"`), allowing Escort Carrier `#94` to cross loss-free, then cleanly transitioned to `waiting_for_antimatter` when fuel ran low on Turn 147.
- **Unit Dismantling:** `dismantle_unit` on Patrol Cutter `#101` refunded exact 50% salvage with fractional minerals preserved (`198` credits, `7.5` metal, `2.5` crystal).
- **Planetary Warfare & Fortifications:** `upgrade_planetary_defenses` and `recruit_troops` (`40` troops recruited onto `#103`) worked cleanly.
- **Covert Ship Naming & Enemy Information Boundary:** `COVERT_INTELLIGENCE_SHIP` constructed cleanly as `Patrol Escort` with 2 agents; visible enemies properly hid orders, fuel, upkeep, and template identity while exposing public weapons and defenses.
- **Diplomacy & AI Self-Correction:** Luna exchanged grounded, non-leaking diplomatic messages (`saves/comms.md`), recorded `[target:ID]` combat commitments, and its self-authored memory lesson `[colonizer/fuel]` broke its own retry loop on Turn 87.

---

## 6. Agentic AI (Luna) Strategic & Planning Observations

Overall, Luna played a surprisingly coherent, bug-free 204-turn campaign (expanded to 4 colonies + 2 more colonizers in flight, fortified all colonies to Level 3, built Metal & Crystal refineries, Orbital Bastion, Deep Survey Ship, and adaptively built Flak Escorts to counter our Carrier!). However, inspecting `memory.md` and `ai_telemetry.jsonl` revealed clear strategic weaknesses:

1. **Premature out-of-sector `use_ability(flak_barrage)` (Turn 183):** Luna cast `flak_barrage` (3-turn duration, 35 AM, 8-turn cooldown) on `Flak Escort #106` while `#106` was still in `Betelgeuse [-2, 2]` — not even in the same sector as our wings in `[1, 3]`! Worse, casting with `queue=false` cancelled `#106`'s active `attack` order, forcing a Turn 184 re-issue, and the aura expired before `#106` got within 500 units.
   - *Suggestion:* Add an explicit `tactical_readiness_note` (or `enemies_in_ability_radius` count) to self-centered combat ability states (`flak_barrage`, `adaptive_forcefield`, `repair_cloud`) so the AI doesn't fire short-duration local auras out of range or in empty sectors.
2. **Quiet-turn cost & latency:** 67.2% of Luna's turns issued `cmds=[]`, yet many quiet turns still consumed 1,000–2,500 reasoning tokens and 15–28 seconds whenever any unit had a fuel wait. Trimming redundant per-unit `command_options` on units with healthy active work (extending `trim_quiet` to reduce the 95 KB `units` payload) would substantially cut latency, cost, and cache erosion.

---

## 7. Gameplay & UX Improvement Suggestions

1. **Add an optional `amount` parameter to `give_antimatter` and `take_antimatter`:** Currently, manual transfers either fill the recipient or completely empty the donor (`0 AM`), making it impossible for a ship to donate e.g. `30 AM` to jump-start a stranded Harvester without stranding itself. Allowing an optional `amount` (defaulting to full/empty) solves a major real logistics frustration for both human and AI players.
2. **Prevent `continuous_resupply` from stranding Harvesters via `give_antimatter` + queued `continuous_resupply`:** Combined with Bug 8 (allowing low-fuel Harvesters to fly to their star), adding a `preserve_reserve` option or `amount` cap on `give_antimatter` prevents accidental self-stranding.
3. **Expose active-unit count & prompt-size budget tips in AI telemetry/dashboard:** The local telemetry in `saves/ai_telemetry.jsonl` was invaluable for diagnosing latency and cache decay; optionally logging `active_unit_count` and `memory_chars` alongside `prompt_metrics` would make scalability profiling even easier.
4. **Update `docs/CODEX_CONTROL.md` Windows PowerShell quick-start:** Use stdin piping (`'{"action":"status"}' | python .\game_control.py -`) for the PowerShell example so Windows PowerShell 5.1 users don't hit quote-stripping errors on step 1.
