# README Overhaul — Implementation Plan

## Status
Planning complete. **Not yet implemented.** This document records the full analysis and
the concrete plan to be executed once approved.

## Goal
`README.md` is stale, duplicated in places, and organized in a way that mixes
player-facing and developer-facing content. Replace it with:
1. A **leaner, reorganized `README.md`** aimed at players/newcomers.
2. A **new `docs/REFERENCE.md`** holding the deep reference material (full
   component/ability catalogues, project structure tree, enum listings) that
   was cluttering the old README.

No other files are modified. This is a documentation-only change.

---

## Part 1 — Verified problems in the current `README.md`

### 1.1 Factual errors (checked against source)

| README claim | Reality (source) |
|---|---|
| File tree lists `unit_components/engines.py` and `unit_components/hyperdrive.py` | Neither file exists — `Engines` and `Hyperdrive` classes both live in `unit_components/movement.py` |
| "Unit Components (**15 total**)" | `unit_components/__init__.py` exports 23 component classes; the Unit Designer catalogue (`gui/unit_editor_gui/catalog.py: COMPONENT_ROWS`) lists **21** selectable rows |
| "Special Abilities (**7 total**)" | `AbilityType` (`unit_components/enums.py`) + `unit_components/abilities/registry.py` define **9** abilities — missing **Drain Antimatter** and **Microjump** |
| "Multiple Selection: Drag selection box or **Ctrl+click**" | Code checks **Shift**, not Ctrl (`input_processor.py:184` uses `pygame.KMOD_SHIFT`; `gui/dynamic_actions.py:9` checks `K_LSHIFT`/`K_RSHIFT`) |
| "Resource Display: Credits, Metal, Crystal, **Antimatter**" (as a HUD resource) | HUD only shows Credits/Metal/Crystal labels (`gui/layout_hud.py`); Antimatter is a per-unit storage component, never a player-level pool |
| "Colonizable Bodies: Planets, Moons, **Asteroids (Metal source)**" | Two distinct classes: `ColonizableAsteroid` (colonizable, population) vs `MetalAsteroid` (metal source, not colonizable) — `entities.py:165` and `:181` |
| "**Python 3.8+**" | PEP-585 builtin generics (`list[Turret]`, `list[dict]`) are used as runtime type annotations (`unit_components/weapons.py:99`, `gui/sidebar/builder.py:39`) → requires **Python 3.9+**. Verified working versions in this environment: Python 3.14.3, pygame-ce 2.5.7, pygame_gui 0.6.14 |
| Star types list "G-Type, Red Dwarf, White Dwarf, Neutron Star, Pulsar, Black Hole, etc." | `StarType` enum (`constants.py:217`) actually has **11** members: G_TYPE, RED_DWARF, WHITE_DWARF, NEUTRON_STAR, PULSAR, BLACK_HOLE, RED_GIANT, YELLOW_GIANT, BLUE_GIANT, PROTOSTAR, BROWN_DWARF |
| Space Phenomena list | Omits **Ice Fields** (`entities.py:202` `IceField`) and doesn't mention Nebula/Storm sub-types |
| "Click 'New Game' to start a new campaign" | Clicking New Game opens the **New Game Wizard** first (`gui/handler.py:178`, `gui/layout_new_game_wizard.py`) — player count/color/AI, galaxy params, starting economy — before the campaign begins |

### 1.2 Missing content (present in code, absent from README)
- **New Game Wizard** (`game_settings.py`, `gui/layout_new_game_wizard.py`): 2–6 players, per-player name/color(8-color palette)/human-vs-AI, galaxy generation params (num systems, system radius min/max, wormhole density, min/max system distance), starting credits/metal/crystal/population.
- Keyboard shortcuts: `G` (galaxy view), `S` (system view), `E` (end turn), `ESC` (menu/cancel targeting/back), arrow keys (sector camera pan); mouse wheel zoom; middle-mouse-button drag pan (`input_processor.py`, `game_camera.py`).
- Components absent from the Features list entirely: **Cloaking Device**, **Civilian Habitat**, **Antimatter Storage**, **Commander** (order-queue component always present on units).
- **Unit stances** (5: Do Nothing, Attack in Weapon Range, Attack in Same Sector, Attack in Jump Range, Attack in Same System — `UnitStance` enum).
- **Turret types** (Mass Driver / Beam / Missile) × **turret variants** (Standard / Anti-Strikecraft / Long-Range).
- **Minefield types** (Anti-Ship / Anti-Strikecraft).
- Full **order type** list is under-represented — README only mentions "sublight move, hex jump, wormhole jump, harvest, transfer, repair, minefield, and ability orders" but `OrderType` (`unit_orders/base.py:25`) has 22 members including Patrol, Protect, Attack, Dock, Deploy Unit/All Wings, Continuous Mine, Continuous Resupply, Load Colonists, Construct.
- **Modal error/warning/info dialogs**, semi-transparent sci-fi UI panels tinted by active player color, per-player **sector intel** tracking, resolution-independent theme scaling (`TEXT_SCALE`, `theme_scaled.json`), `WORMHOLE_FULLSCREEN` env var override.
- **Test suite**: 55 files under `tests/`, 545 collected tests, `pytest.ini` (`pythonpath = .`, `testpaths = tests`). No "Development"/"Testing" section exists at all currently.
- **AI limitation**: non-human players are **not implemented** — their turn is auto-ended ~500 ms after starting (`turn_processor.py:42-44`, `game.py: pending_ai_turn_end_time`). This is an important caveat currently undocumented.
- Missing file-tree entries: `game_settings.py`, `galaxy_utils.py`, `order_system.py`, `gui/layout_new_game_wizard.py`, `unit_components/enums.py`, plus 10 undocumented component modules (`antimatter.py`, `movement.py`, `cloaking.py`, `civilian_habitat.py`, `commander.py`, `constructor.py`, `minelayer.py`, `marines.py`, `sensors.py`, `strikecraft.py`), the full `unit_orders/*.py` list (14 files), the full `unit_components/abilities/*.py` list (13 files), `data/`, `fonts/`, `saves/`, `tests/`, `pytest.ini`, `LICENSE`.

### 1.3 Duplicated content in current README (same topic documented 2×)
1. **Resource Economy** — appears under "Features" *and* under "Game Mechanics".
2. **Movement / wormholes / hyperdrives** — appears under "Features" (Wormhole Network + Hyperdrives) *and* under "Game Mechanics" (Movement System).
3. **Marines / minefields** — appears in the Components bullet list *and* again under "Combat & Warfare".
4. **Install instructions** — "Installation & Requirements" section *and* restated as steps 1–2 of "Getting Started".
5. The CIC/icon-graphics design note is stranded as the first bullet under "Game Controls & Interface" — it belongs in the intro, not in a controls section.
6. The ~100-line "Project Structure" tree is sandwiched between player-facing Controls and Game Mechanics sections, breaking the narrative flow.

---

## Part 2 — Target structure

### 2.1 `README.md` (rewritten, leaner, player-facing)

| # | Section | Content | Resolves |
|---|---|---|---|
| 1 | **Wormhole Control** (title + intro) | 2 short paragraphs: what the game is (2D turn-based 4X prototype, pygame-ce + pygame_gui), the multi-scale universe (galaxy → system → sector), and the deliberate icon-based CIC-style aesthetic (folded in from the stray controls bullet) | Dup. #5 |
| 2 | **Status** | Prototype, single-machine hot-seat; explicitly states AI players are not yet implemented and auto-end their turn | New — undocumented limitation |
| 3 | **Getting Started** | Requirements: Python **3.9+** (corrected), pygame-ce, pygame_gui; verified working set (3.14.3 / 2.5.7 / 0.6.14); `pip install pygame-ce pygame_gui`; `python game.py`; then New Game → New Game Wizard (players, galaxy, economy) → play | Dup. #4, Python version fix, Wizard documented |
| 4 | **Controls** | Single table. Mouse: left-click select, **Shift+click** add/remove (fixes Ctrl→Shift error), drag = box select, right-click = context menu, middle-drag = pan, wheel = zoom. Keyboard: `G`/`S`/`E`/`ESC`, arrow keys = pan | Fixes 1.1 Ctrl+click error; adds missing shortcuts |
| 5 | **The Three Views** | One paragraph each: Galaxy / System / Sector, plus what the HUD bars and sidebar show | Consolidates scattered view-navigation bullets |
| 6 | **Core Gameplay** | Six tight subsections, each topic appearing once: **Turns & Players** · **Economy** (Credits/Metal/Crystal + per-unit Antimatter, corrected framing) · **Movement & FTL** (sublight/hex-jump/wormhole/microjump/inhibition, merged) · **Combat** (turrets, defenses, stances, XP bonuses, boarding, minefields, strikecraft, merged) · **Detection** (sensors, fog of war, cloaking, sector intel) · **Expansion** (colonize, mine/refine, construct, civilian habitat) | Resolves Dup. #1, #2, #3; folds in missing components/stances/turret types at a summary level |
| 7 | **Ship Design** | Short prose on the Unit Designer: hull capacity budget, dynamic-vs-fixed component costs, template persistence (`data/custom_unit_templates.json`); link to `docs/REFERENCE.md` for the full component/ability tables | Moves deep detail out |
| 8 | **Saving & Loading** | JSON saves under `saves/`, accessible from main menu and in-game menu | Kept brief, unchanged in substance |
| 9 | **Development** | `python -m pytest` (mention suite size — see verification step for exact count), `pytest.ini` config, JSON data files under `data/`, env/const toggles (`WORMHOLE_FULLSCREEN`, `DEBUG`, `PROFILE`); link to `docs/REFERENCE.md` for the full project structure tree | New section; removes ~100-line tree from README body |
| 10 | **License** | MIT, link to `LICENSE` | Unchanged |

### 2.2 `docs/REFERENCE.md` (new file, developer/deep-reference facing)

1. **Project Structure** — corrected, complete file tree.
   - Remove non-existent `unit_components/engines.py`, `unit_components/hyperdrive.py` (fold into `movement.py` entry).
   - Add: `game_settings.py`, `galaxy_utils.py`, `order_system.py`, `gui/layout_new_game_wizard.py`, `unit_components/enums.py`, and all currently-omitted component modules.
   - Add full `unit_orders/` file list (14 files) and full `unit_components/abilities/` file list (13 files).
   - Add `data/`, `fonts/`, `saves/`, `tests/`, `pytest.ini`, `LICENSE`.
2. **Hull Sizes** table — 6 sizes (`HullSize` enum) with capacity, HP, min antimatter capacity, base build cost/time (from `constants.py` and `custom_unit_templates.py`).
3. **Component Catalogue** table — all **21** Unit Designer rows from `catalog.py: COMPONENT_ROWS`, grouped by role (propulsion, weapons/defense, economy, utility, abilities), each annotated dynamic-vs-fixed cost and hull-size restrictions; plus the two always-present components (`Commander`, and `AntimatterStorage` as a selectable row). Replaces incorrect "15 total" claim.
4. **Abilities** table — all **9**, with exact values sourced live from `ABILITY_DEFINITIONS`:

   | Ability | Cooldown | Duration | Range | AM Cost | Requires | Target |
   |---|---|---|---|---|---|---|
   | Adaptive Forcefield | 8 | 3 | 0 (self) | 20 | Defenses | none |
   | Cluster Warhead | 5 | 0 | 500 | 30 | Weapons | position |
   | Designate Target | 6 | 4 | 450 | 15 | Sensors | unit |
   | Ion Bolt | 7 | 3 | 400 | 25 | Weapons | unit |
   | Missile Batteries | 10 | 4 | 0 (self) | 40 | Weapons | none |
   | Repair Cloud | 8 | 4 | 350 | 35 | Repair | none |
   | Capture Unit | 10 | 0 | 100 | 40 | Marines | unit |
   | Drain Antimatter | 6 | 0 | 300 | 0 | Antimatter Storage | unit |
   | Microjump | 5 | 0 | 600 | 25 | Hyperdrive | position |

   Replaces incorrect "7 total" claim (was missing Drain Antimatter, Microjump).
5. **Order Types** — all 22 `OrderType` members with one-line descriptions (sourced from the inline comments already in `unit_orders/base.py`).
6. **Universe Objects** — 11 star types + harvest multipliers table; 9 planet types; explicit distinction between `ColonizableAsteroid` (colonizable) and `MetalAsteroid` (metal source); Comet (crystal source), Moon, Asteroid/Ice/Debris Fields; Nebula (4 subtypes: Hydrogen/Nitrogen/Oxygen/Dust) and Storm (3 subtypes: Plasma/Magnetic/Radiation).
7. **Enums Quick Reference** — `UnitStance` (5), `TurretType`×`TurretVariant` (3×3), `MinefieldType` (2), `HyperdriveType` (2), `WingType` (2).
8. **Architecture Notes** — brief: event bus (`events.py`) → `OrderSystem` (`order_system.py`); `VisibilityService` fog-of-war snapshots (`visibility.py`); GUI/renderer facade packages (`gui/`, `rendering/`); resolution-independent theming (`TEXT_SCALE`, `theme_scaled.json`).

---

## Part 3 — Execution steps (to run once approved)

1. Create `docs/` directory and write `docs/REFERENCE.md` with the content in §2.2.
2. Rewrite `README.md` in place with the content in §2.1, linking to `docs/REFERENCE.md` from the Ship Design and Development sections.
3. **Verification pass:**
   a. Re-list the actual repository file tree (`Get-ChildItem -Recurse`) and diff every path mentioned in the new `docs/REFERENCE.md` tree against it — fix any mismatch.
   b. Re-derive and cross-check counts against live code: 21 designer components (`len(COMPONENT_ROWS)`), 9 abilities (`len(ABILITY_DEFINITIONS)`), 6 hull sizes (`len(HullSize)`), 11 star types, 9 planet types, 22 order types (`len(OrderType)`) — assert the tables match.
   c. Grep both new files for the old Ctrl+click / 15-components / 7-abilities / Python 3.8 claims to confirm they no longer appear.
   d. Confirm no topic (economy, movement, marines/minefields, install steps) is documented twice across the two files.
   e. Verify all relative links between `README.md` and `docs/REFERENCE.md` resolve.
4. Run `python -m pytest -q` to confirm the documentation-only change has zero impact on the test suite (expected baseline: 8 pre-existing failures / 537 passed, unrelated to this change — see §4).

---

## Part 4 — Out of scope (flagged, not touched by this change)

- **8 pre-existing, unrelated test failures** observed during exploration:
  `tests/test_antimatter_management.py::test_sublight_movement_fails_without_antimatter`,
  `tests/test_antimatter_management.py::test_system_jump_fails_without_antimatter`,
  `tests/test_dynamic_component_scaling.py::test_hyperdrive_jump_cost_by_hull_size`,
  `tests/test_dynamic_sublight_antimatter.py::test_get_sublight_antimatter_cost_per_turn_baseline`,
  `tests/test_dynamic_sublight_antimatter.py::test_get_sublight_antimatter_cost_per_turn_speed_scaling`,
  `tests/test_dynamic_sublight_antimatter.py::test_get_sublight_antimatter_cost_per_turn_hull_scaling`,
  `tests/test_dynamic_sublight_antimatter.py::test_get_sublight_antimatter_cost_per_turn_combined_scaling`,
  `tests/test_dynamic_sublight_antimatter.py::test_turn_processor_sublight_antimatter_consumption`.
  These assert stale antimatter-cost constants (e.g. expect sublight base cost 2.0 / system jump cost 50) that were intentionally lowered in commits `177f77d` and `8daea74` (jump cost now 40, `ENGINE_ANTIMATTER_COST_PER_TURN` now 1.0). This is a source-code/test issue unrelated to documentation and is called out here only so it isn't mistaken for a regression caused by this README work.
- `requirements.txt` is not being added in this pass (README will state the verified versions in prose); can be added as a follow-up if desired.

