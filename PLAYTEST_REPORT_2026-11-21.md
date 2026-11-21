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

## 5. Discovered Bugs & Engine Issues

### [MEDIUM] Bug 4: `TakeAntimatterOrder` / Unit Approach Does Not Refresh Moving Target Coordinates Mid-Flight

- **Observed (Turns 75–91, `Colonizer #71` & `Harvester #72`):**
  - When `#71` had `take_antimatter` targeting `#72` while `#72` had `give_antimatter` targeting `#71`, `#72` flew past `#71` and donated 25 AM on Turn 89. On Turn 91, `#71` (now mobile again) flew **away** from `#72` toward `[-917.85, -709.47]` — where `#72` had been on Turn 75 — while `#72` chased `#71` from behind!
- **Root Cause:**
  - Unlike `AttackOrder` (which `Commander.prepare_for_movement()` refreshes every turn at `unit_components/commander.py:601-603`), `TakeAntimatterOrder` / `GiveAntimatterOrder` only recompute target standoff positions when the current `MoveOrder` suborder finishes.
- **Suggested Fix:**
  - Refresh moving-unit approach waypoints in `prepare_for_movement()` (or when target displacement exceeds transfer range) for unit-targeted support orders (`give_antimatter`, `take_antimatter`, `repair`, `protect`) just like `AttackOrder`.

---

### [MEDIUM] Bug 5: Enemy `turn_summary` Discloses Exact Internal Component Damage From Wormhole Instability

- **Observed (Turn 178, `Escort Carrier #94`):**
  - When our `Escort Carrier #94` crossed Wormhole 68 into Betelgeuse `[1, 3]`, it took **24 component damage to Defenses** while its hull stayed `100/100 HP`.
  - Yet Luna's Turn 178 `memory.md` recorded: *"Enemy Escort Carrier 94 sighted at Betelgeuse wormhole sector [1,3]; took 24 HP of wormhole-instability damage."*
- **Root Cause (`turn_briefing.py:163-199`):**
  - `unit_event()` records `hazard` events for every player with visibility of the unit whenever `private=False`. While `component_is_public` hides covert Intelligence components, it still exposes exact component HP damage amounts on public components like `Defenses` to enemy observers, even though enemy component HP is otherwise hidden in observations.
- **Suggested Fix:**
  - Mark internal component-damage hazard/wormhole events as `private=True` (owner/allies only), or omit exact component damage numbers for enemy observers (reporting only hull damage or component destruction).

---

### [MEDIUM] Bug 6: Homeworld Sector Reported as `"Newly explored sector"` on Turn 12 & Unaggregated Discovery Entries

- **Observed (Turn 13):**
  - When our first `Scout #77` (with `long_range_hexes: 1`) completed at our homeworld `Epsilon Eridani [0, 2]`, `turn_summary` fired **7 separate** `[discovery] Newly explored sector` entries — including **`Epsilon Eridani [0, 2]`**, our own homeworld sector that we had owned and occupied since Turn 1!
- **Root Cause (`turn_briefing.py:239-241`):**
  - `_discoveries()` derives explored sectors from `player.sector_intel`, which is populated by long-range hex sensors rather than starting colony/unit presence. Because starter units have `long_range_hexes == 0`, the homeworld sector wasn't in `state.seen` at campaign start.
- **Suggested Fix:**
  - Record sectors containing owned colonies/units into `player.sector_intel` (or baseline `state.seen`) during campaign initialization so your homeworld sector is never reported as "newly explored" mid-game. Consider optionally aggregating multiple simultaneous sector discoveries per system in briefings.

---

### [MEDIUM] Bug 7: Flat Mitigation Makes Bomber Wings Deal Zero Damage to Basic Patrol Escorts Without Feedback

- **Observed (Turns 180–186, `Betelgeuse [1, 3]`):**
  - `Bomber Wing #95` (5-damage Beam turret) and `Escort Carrier #94` (precision-targeting `Weapons`) fired 7+ shots at Luna's standard `Patrol Escort #102` (`6.0` Armor / `6.0` Shields / `6.0` PD), dealing **0 damage every single shot** (`#102` stayed at `100/100 HP` until Beam Frigate Alpha `#86` arrived with 10-damage turrets on Turn 201!).
  - Furthermore, `turn_summary` reported `[combat] Attacked by Bomber Wing (Antigravity) subj=Patrol Escort#102 amt=0.0` without clarifying that damage was fully negated by defenses (and Luna's memory noted *"no damage amount reported"*).
- **Suggested Fix:**
  - Review Bomber Wing base turret damage (5 dmg vs. 6.0 shields/armor on even the cheapest medium escort makes unbuffed Bomber Wings completely ineffective against almost every Medium+ combat ship without `Attack Run`'s 2× bonus — and `Escort Carrier` does **not** even equip `Attack Run`!). Either raise Bomber Wing per-shot damage (e.g., 8–10 with longer cooldown) or introduce a minimum chip-damage / percentage-mitigation floor.
  - Surface `"deflected / 0 damage"` explicitly in combat briefings so human and AI players know when a matchup cannot penetrate defenses.

---

### [LOW] Bug 8: `continuous_resupply` Rejects Low-Fuel Harvesters That Can Still Reach Their Source Star

- **Observed (Turn 120, `Harvester #72`):**
  - At `25/300 AM` in `Epsilon Eridani [0, 2]`, issuing `continuous_resupply` from Star 15 (`[0, 0]`, only ~18 AM away) immediately failed with `insufficient_resources`. Yet issuing `move` to Star 15 + queued `continuous_resupply` succeeded and recovered `#72` completely!
- **Suggested Fix:**
  - Allow `continuous_resupply` to start its `returning_to_source` leg whenever current AM is sufficient to reach the harvest source (without requiring the full `60 AM` delivery reserve or delivery-leg buffer before harvesting!).

---

### [LOW] Bug 9: Minor Logging, Receipt & Observation Polish

1. **`HexHexCoord` log typo:** `game.log` contained **239** occurrences of `HexHexCoord(q=..., r=...)` from `ReachWaypointOrder.check_completion_conditions` (`"Hex"` prefix concatenated onto `repr(HexCoord)`).
2. **Stale unit name in same-batch receipts (Turn 68):** Sending `rename_unit` (`#86` → `"Beam Frigate Alpha"`) followed by `set_stance` in the same batch returned `"Renamed unit 86 to Beam Frigate Alpha."` then `"Set Kinetic Frigate stance to attack_same_sector."` (pre-rename name).
3. **`Movement resumed after fuel wait` categorized as `[problem]`:** Triggered on Turns 77, 166, 201 (and on Turn 77 fired when replacing a failed jump with a sublight order, even though the ship had never entered a fuel wait). Should use a neutral/info category (`logistics` or `development`) and clear wait flags cleanly when orders are replaced.
4. **Wormhole `is_solid: true` with `collision_radius: 0.0`:** Disclosed wormhole bodies report `"is_solid": true` alongside `"collision_radius": 0.0` (while `docs/REFERENCE.md` describes them as having 0 collision radius). Setting `is_solid: false` (or clarifying in schema docs) would be cleaner.

---

## 6. Agentic AI (Luna) Strategic & Planning Observations

Overall, Luna played a surprisingly coherent, bug-free 204-turn campaign (expanded to 4 colonies + 2 more colonizers in flight, fortified all colonies to Level 3, built Metal & Crystal refineries, Orbital Bastion, Deep Survey Ship, and adaptively built Flak Escorts to counter our Carrier!). However, inspecting `memory.md` and `ai_telemetry.jsonl` revealed clear strategic weaknesses:

1. **Over-deference to broken/stuck automatic orders:** Luna watched `Shipyard 73` sit stalled at `0/80 AM` for ~50 turns (Turns 41–92) before manually issuing `give_antimatter[74](73)`, repeatedly writing *"Harvester 76's automatic service-priority delivery remains active; monitor progress"*. Even after fixing Bug 1 in the engine, adding a prompt heuristic ("if a builder remains fuel-stalled for >3 turns, dispatch an explicit `give_antimatter`") will make the AI much more resilient.
2. **11-turn Colonizer retry loop despite writing a lesson against it (Turns 76–86):** After Colonizer 75's jump failed (`5.75 AM` vs. `10 AM`), Luna re-issued the exact same `load_colonists + colonize` batch on 10 of the next 11 turns — even on Turn 86, the very turn it wrote `[colonizer/fuel]` into `## Lessons`! (Encouragingly, once persisted in Turn 86 memory, that lesson **did** stop the loop on Turn 87.)
   - *Suggestion:* Highlight recent `jump_fuel_failure` blockers directly inside `command_options.load_colonists` / `colonize` (e.g., `"fuel_warning": "Current AM (5.75) cannot cover jump (10.0)"`) so the model sees the blocker right next to the action rather than only in `order_history`.
3. **Premature out-of-sector `use_ability(flak_barrage)` (Turn 183):** Luna cast `flak_barrage` (3-turn duration, 35 AM, 8-turn cooldown) on `Flak Escort #106` while `#106` was still in `Betelgeuse [-2, 2]` — not even in the same sector as our wings in `[1, 3]`! Worse, casting with `queue=false` cancelled `#106`'s active `attack` order, forcing a Turn 184 re-issue, and the aura expired before `#106` got within 500 units.
   - *Suggestion:* Add an explicit `tactical_readiness_note` (or `enemies_in_ability_radius` count) to self-centered combat ability states (`flak_barrage`, `adaptive_forcefield`, `repair_cloud`) so the AI doesn't fire short-duration local auras out of range or in empty sectors.
4. **Slow combat mobilization due to rigid "preserve active work" bias:** When our Carrier + Bomber/Recon Wings invaded Betelgeuse `[1, 3]` on Turn 178–179, Luna left `Flak Escort #106` on a routine Colonizer refuel for 2 turns and never pulled `Patrol Escort #90` off Harvester escort duty, even while `Patrol Escort #102` fought alone and ran dry of AM.
   - *Suggestion:* Tune the system prompt so home-system enemy invasions explicitly override "preserve non-urgent utility orders" for combat ships (especially hard-counters like Flak Escorts vs. visible Carriers/Wings).
5. **Fleet monoculture & late reconnaissance:** Across 204 turns, Luna built only `PATROL_ESCORT` (×3) and `FLAK_ESCORT` (×2) — zero Frigates, Cruisers, Carriers, Artillery, or Raiders — and did not finish its first recon ship (`DEEP_SURVEY_SHIP #104`) until Turn 157, never scouting outside Betelgeuse.
6. **Suboptimal Constructor `move`-then-`construct` habit:** Luna repeatedly issued `move` to a mining sector first and only issued `construct` after arrival (wasting 6–9 turns per refinery), even though `construct` automatically handles approach.
7. **Quiet-turn cost & latency:** 67.2% of Luna's turns issued `cmds=[]`, yet many quiet turns still consumed 1,000–2,500 reasoning tokens and 15–28 seconds whenever any unit had a fuel wait. Trimming redundant per-unit `command_options` on units with healthy active work (extending `trim_quiet` to reduce the 95 KB `units` payload) would substantially cut latency, cost, and cache erosion.
8. **Repetitive `important_events` entries during multi-turn waits/combat:** Luna occasionally filled `important_events` with turn-by-turn status repeats (e.g., Turns 26–29 *"Planet 53 remained observed unowned"*, Turns 179–185 repeated 0-damage attack notices), though its 5-turn consolidation pass usually cleaned them up later.

---

## 7. Gameplay & UX Improvement Suggestions

1. **Add an optional `amount` parameter to `give_antimatter` and `take_antimatter`:** Currently, manual transfers either fill the recipient or completely empty the donor (`0 AM`), making it impossible for a ship to donate e.g. `30 AM` to jump-start a stranded Harvester without stranding itself. Allowing an optional `amount` (defaulting to full/empty) solves a major real logistics frustration for both human and AI players.
2. **Prevent `continuous_resupply` from stranding Harvesters via `give_antimatter` + queued `continuous_resupply`:** Combined with Bug 8 (allowing low-fuel Harvesters to fly to their star), adding a `preserve_reserve` option or `amount` cap on `give_antimatter` prevents accidental self-stranding.
3. **Expose active-unit count & prompt-size budget tips in AI telemetry/dashboard:** The local telemetry in `saves/ai_telemetry.jsonl` was invaluable for diagnosing latency and cache decay; optionally logging `active_unit_count` and `memory_chars` alongside `prompt_metrics` would make scalability profiling even easier.
4. **Update `docs/CODEX_CONTROL.md` Windows PowerShell quick-start:** Use stdin piping (`'{"action":"status"}' | python .\game_control.py -`) for the PowerShell example so Windows PowerShell 5.1 users don't hit quote-stripping errors on step 1.
