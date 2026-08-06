# `game.py` Refactoring Plan

**Status:** Proposed (no code changes made yet)
**Target file:** `game.py` — 1,677 lines
**Goal:** Split the monolithic central controller into focused packages/modules, reducing `game.py` to ~280 lines, **without changing behaviour (except for a small bugfix) or breaking any of the 453 existing tests**.

---

## 1. Current Structure Analysis

`game.py` currently fulfils six unrelated responsibilities. Measured breakdown:

| Lines | Section | Size | Responsibility |
|---|---|---:|---|
| 1–42 | `GameLogFormatter`, `setup_logging()` | 42 | Application logging bootstrap |
| 44–84 | Imports + `CAMERA_SMOOTH_SPEED` | 41 | (~60% of imports are unused today) |
| 87–171 | `Game.__init__` | 83 | Subsystem wiring + state field declarations |
| 172–183 | `reset_sector_camera` | 12 | Sector camera |
| 184–246 | `start_new_game` | 63 | New-game bootstrap |
| 247–325 | `spawn_units` | 79 | Starting-fleet spawning |
| 326–338 | `handle_input`, `deselect_object` | 13 | Thin delegates |
| **339–655** | **`handle_gui_action`** | **317** | **Giant `elif` GUI action dispatcher** |
| 656–680 | `update_sector_camera` | 25 | Sector camera |
| 681–723 | `recompute_visibility`, `is_unit_visible`, `hex_has_presence`, `is_minefield_visible` | 43 | Facade over `visibility.py` |
| 724–761 | `update`, `end_turn` | 38 | Per-frame update / turn advance |
| 762–772 | `update_view_specific_labels` | 11 | HUD label |
| **773–1055** | **`_format_order_state_data`** | **283** | **HTML order-text formatting** |
| 1056–1101 | `_generate_order_data_recursive` | 46 | Recursive order-tree HTML |
| **1102–1503** | **`update_side_bar_content`** | **402** | **Sidebar payload generation** |
| 1504–1545 | `get_player_income`, `get_player_upkeep` | 42 | Economy queries |
| 1546–1565 | `update_player_turn_display` | 20 | Turn/resource HUD |
| 1566–1609 | `draw`, `handle_mouse_wheel` | 44 | Render delegate + camera zoom |
| 1610–1677 | `run`, `save_game`, `load_game`, `quit_to_main_menu`, `__main__` | 68 | Loop & persistence delegates |

**Key finding:** Sidebar + order formatting = **731 lines (44%)**; GUI action dispatch = **317 lines (19%)**. Those two concerns are 63% of the file and neither belongs in the central controller.

### 1.1 Existing architectural precedent to follow

The repo already uses the *facade + sub-module package* pattern successfully:
- `renderer.py` (57 lines) is a thin facade delegating to the `rendering/` package (8 modules).
- `unit_orders/` and `unit_components/` are packages with a re-exporting `__init__.py`.

This refactor applies the identical pattern to `game.py`.

---

## 2. Hard Compatibility Constraints (discovered from the test-suite & callers)

These **must** survive the refactor:

### 2.1 Tests invoke `Game` methods *unbound*, passing a `MagicMock` / non-`Game` object as `self`

| Test file | Call |
|---|---|
| `tests/test_unit_selection_sidebar.py`, `tests/test_sector_sidebar_objects.py`, `tests/test_strikecraft_bay_gui.py`, `tests/test_unit_components.py` | `Game.update_side_bar_content(mock_game)` |
| `tests/test_unit_selection_sidebar.py`, `tests/test_sector_sidebar_objects.py`, `tests/test_minefield.py`, `tests/test_unload_resources_nearest.py` | `Game.handle_gui_action(mock_game, action)` |
| `tests/test_unit_orders.py` | `game._format_order_state_data(state_data)` on a `class MockGame(Game)` that only sets `self.galaxy` |
| `tests/test_sector_camera.py` | `Game.reset_sector_camera(game)`, `Game.handle_mouse_wheel(game, 1)`, `Game.update_sector_camera(game, dt)` with a `DummyGame` that does **not** subclass `Game` |
| `tests/test_turn_processor.py` | `game.get_player_income(player)` / `get_player_upkeep(player)` on `class DummyGame(Game)` with only `self.galaxy` |

➡️ **Consequence (critical design rule):** extracted code must be **module-level functions whose first parameter is `game`**. It must **not** be refactored into collaborator objects created in `Game.__init__` (e.g. `self.sidebar_builder`), because a `MagicMock` "self" has no such attribute and the tests would silently no-op and fail.

### 2.2 Symbols that must remain importable from the `game` module

| Symbol | Consumer |
|---|---|
| `Game` | 20+ tests, `entities.py`/`gui.py`/`unit_components/*` (TYPE_CHECKING) |
| `CAMERA_SMOOTH_SPEED` | `tests/test_sector_camera.py`: `from game import Game, CAMERA_SMOOTH_SPEED` |
| `PROFILE` | `tests/test_strikecraft_bay_gui.py`: `import game as game_module; game_module.PROFILE = False` |
| `setup_logging` | `game.py` `__main__` block (and future entry points) |

### 2.3 External callers of `Game` methods (public API must not change)

| Caller | Methods used |
|---|---|
| `gui.py` | `game_instance.get_player_income/get_player_upkeep`, `handle_gui_action` |
| `save_manager.py` | `game.recompute_visibility()`, `game.update_side_bar_content()`, `game.update_player_turn_display()` + direct state field writes |
| `turn_processor.py` | `game.update_player_turn_display()`, `game.update_side_bar_content()`, `game.pending_ai_turn_end_time` |
| `input_processor.py` | ~50 distinct `game.*` state fields and `handle_gui_action`, `end_turn`, `handle_mouse_wheel`, `reset_sector_camera`, `update_view_specific_labels`, `is_unit_visible` |
| `unit_components/commander.py` | `game_state._generate_order_data_recursive(order, 0)` — **private-looking but is a cross-module API**; keep the method name on `Game`. |
| `entities.py` | `game.deselect_object(self)` |

➡️ **Every method currently on `Game` stays on `Game`** as a one-line delegate. Zero changes to any other existing source file are required (except the README).

---

## 3. Target File Layout

```
game.py                       (~280)  Game class: state, wiring, run loop, thin delegates, entry point
game_logging.py               (~45)   GameLogFormatter, setup_logging
game_setup.py                 (~150)  start_new_game(game), spawn_units(game, homeworld_hexes)
game_camera.py                (~95)   CAMERA_SMOOTH_SPEED + camera reset/update/zoom functions
economy.py                    (~55)   calculate_player_income / calculate_player_upkeep
game_actions/                 (~400)  GUI action dispatch package
├── __init__.py               (~55)   ACTION_HANDLERS registry + handle_gui_action(game, action)
├── app_actions.py            (~110)  Application/menu/navigation/persistence actions
├── unit_actions.py           (~180)  Unit command actions (hangar, stance, orders, abilities)
└── selection_actions.py      (~60)   Selection & sidebar-state actions
sidebar/                      (~780)  Sidebar payload generation package
├── __init__.py               (~25)   Re-exports the public sidebar API
├── builder.py                (~150)  Orchestrator + dispatcher + multi-select + theming
├── order_formatting.py       (~360)  Per-order-type HTML formatters + recursive walker
├── panels_world.py           (~200)  StarSystem / Hex / CelestialBody / Minefield panels
└── panels_unit.py            (~210)  Unit panel: header, tabs, basic-info tab, components tab
```

**13 new files** (2 of them `__init__.py`). Net: `game.py` 1,677 → ~280 lines (−83%).

---

## 4. Module-by-Module Specification

### 4.1 `game_logging.py` — *(from game.py lines 1–42)*

```python
"""Application logging configuration for Wormhole Control."""
import logging

class GameLogFormatter(logging.Formatter): ...   # verbatim move
def setup_logging(log_to_file: bool = False): ...  # verbatim move
```

**In `game.py`:**
```python
from game_logging import GameLogFormatter, setup_logging  # re-exported for back-compat
setup_logging(log_to_file=False)
logger = logging.getLogger(__name__)
```
The import-time `setup_logging(log_to_file=False)` call **stays in `game.py`** (moving it into `game_logging.py` would reconfigure logging for anything importing that module).

---

### 4.2 `game_camera.py` — *(from lines 84, 172–183, 656–680, 1570–1609)*

```python
CAMERA_SMOOTH_SPEED = 12.0

def reset_sector_camera(game) -> None: ...
def update_sector_camera(game, dt: float) -> None: ...
def handle_mouse_wheel(game, scroll_y: int) -> None: ...
```
- Move the function-local `from constants import SECTOR_ZOOM_MIN, SECTOR_ZOOM_MAX, SECTOR_CIRCLE_CENTER_IN_PX` imports to module level (no cycle: `constants` imports nothing from `game`). Note the current code imports `SECTOR_ZOOM_MIN/MAX` **twice** in `handle_mouse_wheel` — dedupe.
- `game.py` re-exports the constant: `from game_camera import CAMERA_SMOOTH_SPEED` (satisfies `from game import CAMERA_SMOOTH_SPEED`).

**Delegates on `Game`:**
```python
def reset_sector_camera(self):            game_camera.reset_sector_camera(self)
def update_sector_camera(self, dt):       game_camera.update_sector_camera(self, dt)
def handle_mouse_wheel(self, scroll_y):   game_camera.handle_mouse_wheel(self, scroll_y)
```
✅ Works with `tests/test_sector_camera.py`'s `DummyGame` (plain object, not a `Game` subclass).

---

### 4.3 `economy.py` — *(from lines 1504–1545)*

```python
def calculate_player_income(galaxy, player) -> float: ...
def calculate_player_upkeep(galaxy, player) -> float: ...
```
- Pure functions over `(galaxy, player)`; module-level imports of `Planet, Moon, ColonizableAsteroid`, `TAX_RATE`, `UPKEEP_COST_PER_HULL_POINT`, `HullSize` (currently imported *inside* the methods).
- `galaxy=None` must return `0.0` (preserves current `if self.galaxy:` guard).

**Delegates:**
```python
def get_player_income(self, player):  return economy.calculate_player_income(self.galaxy, player)
def get_player_upkeep(self, player):  return economy.calculate_player_upkeep(self.galaxy, player)
```
✅ Works with `DummyGame(Game)` that only defines `self.galaxy`.

**Follow-up (out of scope, flag only):** `turn_processor._process_unit_upkeep` duplicates the upkeep formula; it can later call `economy.calculate_player_upkeep`.

---

### 4.4 `game_setup.py` — *(from lines 184–325)*

```python
def start_new_game(game) -> bool: ...
def spawn_units(game, player_homeworld_hexes: dict | None = None) -> None: ...
```
- Owns: galaxy generation, the hard-coded 3-player creation, homeworld assignment, the `SPAWN_*` template table and spawn loop.
- Module imports: `random`, `typing`, `Galaxy/StarSystem`, `Player, Planet, Star, Wormhole`, `Position`, `HexCoord`, `instantiate_unit_from_template`, `BLUE/RED/YELLOW`.
- After this move, `random`, `Galaxy`, and most `entities`/`unit_components` imports leave `game.py`.

**Delegates:** `Game.start_new_game()` / `Game.spawn_units(...)` keep their names (used by `handle_gui_action` and `tests/test_save_load.py`).

---

### 4.5 `sidebar/` package — *(from lines 773–1503; the largest extraction)*

#### `sidebar/order_formatting.py` — *(lines 773–1101)*
Public API:
```python
def format_order_state_data(state_data: dict, galaxy=None) -> list[str]
def generate_order_data_html(order, indent_level: int = 0, galaxy=None) -> str
```
Internal structure (replaces one 283-line `if/elif` chain):
- Module-level colour constants (`MOVE_TYPE_COLOR`, `INFO_COLOR`, … currently redefined on *every* call inside the function).
- A registry `ORDER_FORMATTERS: dict[str, Callable[[dict, dict, Any], list[str]]]` keyed by `order_type`, mapping to one small function per order type:
  `MOVE, REACH_WAYPOINT, TOGGLE_INHIBITOR, PATROL, ATTACK, COLONIZE, LOAD_COLONISTS, MINE, CONTINUOUS_MINE, CONTINUOUS_RESUPPLY, UNLOAD_RESOURCES, TRANSFER_ANTIMATTER, CONSTRUCT, REPAIR, PROTECT, DOCK, DEPLOY_UNIT, DEPLOY_ALL_WINGS, USE_ABILITY`
- Fallback returns `[f"<font color='{INFO_COLOR}'>{order_type} ({status})</font>"]` (unchanged).
- Only `USE_ABILITY` needs `galaxy` (for target-name lookup) — hence the optional `galaxy` parameter.
- Shared helper `_target_name_html(state_data)` deduplicates the identical "lookup_success / target_unit_id / Unknown Target" block currently copy-pasted 4× (ATTACK, TRANSFER_ANTIMATTER, REPAIR, PROTECT).

**Delegates (names preserved — `commander.py` depends on the second one):**
```python
def _format_order_state_data(self, state_data):
    return order_formatting.format_order_state_data(state_data, getattr(self, 'galaxy', None))

def _generate_order_data_recursive(self, order, current_indent_level):
    return order_formatting.generate_order_data_html(order, current_indent_level, getattr(self, 'galaxy', None))
```

#### `sidebar/panels_world.py` — *(lines ~1160–1360)*
```python
def build_system_panel(game, system) -> list[dict]
def build_hex_panel(game, hex_obj) -> list[dict]
def build_celestial_body_panel(game, body) -> list[dict]
def build_minefield_panel(game, minefield) -> list[dict]
def object_button_style(owner) -> str          # shared '#player_x_button' / '#sidebar_neutral_button'
```
`build_celestial_body_panel` internally dispatches per body type (`Star, Planet, Moon, ColonizableAsteroid, MetalAsteroid, Wormhole, DebrisField, AsteroidField, IceField, Nebula, Storm, Comet`) — implemented as a small `isinstance` chain or a type→builder map.

#### `sidebar/panels_unit.py` — *(lines ~1372–1503)*
```python
def build_unit_panel(game, unit) -> list[dict]
def _build_header(game, unit) -> list[dict]        # name entry vs static label, type/hull/template/owner
def _build_tab_buttons(game) -> list[dict]
def _build_basic_info_tab(game, unit) -> list[dict]
def _build_components_tab(game, unit) -> list[dict]
def hit_point_style_id(unit) -> str                # dedupes the 4-branch HP colour ladder (duplicated today)
```
`_build_components_tab` retains the side-effect of normalising `game.selected_component_name` (defaults to `"Commander"` then first option) — required by `tests/test_unit_selection_sidebar.py`.

#### `sidebar/builder.py`
```python
def update_side_bar_content(game) -> None    # full orchestration (guard, profiling, gui push, flag reset)
def build_sidebar_data(game) -> list[dict]   # pure: selection -> data payload
def _apply_player_button_theme(game) -> None # the per-player theme_dict load block
def _build_empty_panel() -> list[dict]
def _build_multi_selection_panel(game) -> list[dict]
```
`update_side_bar_content(game)` is a **verbatim** move of the current method body, so the observable sequence (early return when `not sidebar_needs_update`, `selected_component_name` reset, theme load, `gui.update_side_bar_content(data)`, `sidebar_needs_update = False`, `PROFILE` timers) is byte-for-byte equivalent.

**Delegate:** `def update_side_bar_content(self): sidebar.update_side_bar_content(self)`

#### `sidebar/__init__.py`
```python
from .builder import update_side_bar_content, build_sidebar_data
from .order_formatting import format_order_state_data, generate_order_data_html
__all__ = [...]
```

#### Two behaviour notes:
1. **Unreachable `else` branch (lines ~1494–1503).** The trailing `# --- Default / Unknown ---` `else:` is attached to the `if len==0 / elif len>1 / elif len==1` chain and can never execute. Today an unrecognised single selection therefore renders an **empty** sidebar. Fix: reuse it as the single-selection fallback inside `build_sidebar_data` so unknown objects show "Selected: <Type>" + ID.
2. **`PROFILE` sourcing.** The builder will use `import constants` + `if constants.PROFILE:` so profiling stays runtime-togglable. `tests/test_strikecraft_bay_gui.py` sets `game_module.PROFILE = False`, which will no longer influence the builder — harmless, because `constants.PROFILE` is already `False` and the tests assert nothing about it. `PROFILE` remains imported in `game.py` so the attribute assignment still succeeds.

---

### 4.6 `game_actions/` package — *(from lines 339–655)*

Replaces the 317-line `if/elif` chain with a dispatch registry.

#### `game_actions/__init__.py`
```python
from . import app_actions, unit_actions, selection_actions

ACTION_HANDLERS: dict[str, Callable[[Any, dict], None]] = {
    **app_actions.HANDLERS,
    **unit_actions.HANDLERS,
    **selection_actions.HANDLERS,
}

def handle_gui_action(game, action: dict) -> None:
    handler = ACTION_HANDLERS.get(action.get('action'))
    if handler is None:
        logger.debug(f"Warning: Unhandled GUI action type: {action.get('action')}")
        return
    handler(game, action)
```
Each handler has the uniform signature `handler(game, action) -> None` and is responsible for its own `game.sidebar_needs_update = True` (exactly as today — it is **not** hoisted into the dispatcher, because only some branches set it).

#### `game_actions/app_actions.py`
`new_game`, `show_about`, `quit`, `show_main_menu`, `context_menu_select`, `end_turn`, `toggle_ingame_menu`, `toggle_unit_editor`, `unit_editor_design_saved`, `unit_editor_design_deleted`, `save_game`, `load_game_file`, `quit_to_main_menu`, `navigate_back`, `ui_handled` (no-op).

#### `game_actions/unit_actions.py`
`deploy_ship`, `launch_all_wings`, `recall_ship`, `toggle_build_wing_type`, `unload_resources_nearest`, `lay_minefield` / `lay_minefield_anti_ship` / `lay_minefield_anti_strikecraft` (three keys → one handler), `set_stance`, `cycle_stance`, `rename_unit`, `use_ability`, `stop_unit`, `stop_selected_units`.
Private helpers extracted from the current inline code:
```python
def _iter_friendly_refineries(galaxy, unit)      # replaces the nested triple loop
def _refinery_distance(galaxy, unit, refinery)   # replaces the nested get_dist_to_refinery closure
```

#### `game_actions/selection_actions.py`
`select_individual_unit`, `select_minefield`, `select_celestial_body`, `component_selected`, `switch_unit_sidebar_tab`.

**Delegate:** `def handle_gui_action(self, action): game_actions.handle_gui_action(self, action)`

**Optional new test (recommended):** assert every `action_id` string emitted by `gui.py` / `unit_editor_gui.py` exists in `ACTION_HANDLERS`, so a future typo fails loudly instead of logging a debug warning.

---

### 4.7 What remains in `game.py` (~280 lines)

```python
setup_logging(log_to_file=False); logger = ...

from constants import SCREEN_RES, RED, BLUE, YELLOW, PROFILE, FULLSCREEN, UPKEEP_COST_PER_HULL_POINT
from game_logging import GameLogFormatter, setup_logging
from game_camera import CAMERA_SMOOTH_SPEED
import game_camera, game_setup, game_actions, economy, sidebar
...

class Game:
    def __init__(self): ...                     # unchanged (83 lines) — the only large method left
    # --- delegates ---
    reset_sector_camera / update_sector_camera / handle_mouse_wheel   -> game_camera
    start_new_game / spawn_units                                      -> game_setup
    handle_gui_action                                                 -> game_actions
    update_side_bar_content / _format_order_state_data /
        _generate_order_data_recursive                                -> sidebar
    get_player_income / get_player_upkeep                             -> economy
    handle_input                                                      -> input_processor
    draw                                                              -> renderer
    end_turn                                                          -> turn_manager
    save_game / load_game                                             -> save_manager
    # --- kept in place (small, genuinely controller-level) ---
    update(), run(), deselect_object(), quit_to_main_menu(),
    update_view_specific_labels(), update_player_turn_display(),
    recompute_visibility(), is_unit_visible(), hex_has_presence(), is_minefield_visible()

if __name__ == '__main__': ...                  # unchanged; `python game.py` still works
```

`Game.__init__` keeps its current inline field declarations (they are the canonical state schema that `save_manager.py` and `input_processor.py` read/write; grouping them into sub-objects would be a breaking change and is explicitly **out of scope**).

---

## 5. Import Hygiene (part of the final step)

After the moves, these `game.py` imports become unused and should be deleted (each verified by grep before removal):

- `constants`: `STATION_ICON_SIZE`, `SHIP_ICON_SIZE`, `DEFAULT_SUBLIGHT_SHIP_SPEED`, `DEBUG`, `MAX_UNIT_XP` (→ `sidebar`)
- `utils`: `Timer`, `color_to_hex` (→ `sidebar`)
- `geometry`: `Vector`, `distance_sq`, `distance`
- `hexgrid_utils`: `hex_to_pixel`, `pixel_to_hex`, `get_hex_vertices` (all three unused **today**)
- `sector_utils`: `move_towards_position`, `sector_coords_to_pixels`, `pixels_to_sector_coords`, `random_point_in_sector` (all unused today)
- `entities`: `GameObject`, `HullSize`, `Order`, `AsteroidField`, `DebrisField`, `IceField`, `Nebula`, `Storm`, `Comet`, `Minefield`, `Star`, `Moon`, `ColonizableAsteroid`, `MetalAsteroid`, `Wormhole`, `CelestialBody` (→ `sidebar` / `game_setup`)
- `unit_components`: **all 16 names** (`Engines`, `Hyperdrive`, `HyperdriveType`, `Commander`, `JumpStatus`, `Turret`, `TurretType`, `Weapons`, `HyperspaceInhibitionFieldEmitter`, `Constructor`, `ColonyComponent`, `RepairComponent`, `HangarComponent`, `StrikecraftBayComponent`, `StrikecraftWingComponent`, `AntimatterHarvester`) — only `instantiate_unit_from_template` was ever used, and it moves to `game_setup`
- `events`: all except what `game.py` still needs (`CancelOrdersEvent`, `UseAbilityEvent` move to `game_actions`); `EventBus` stays
- `galaxy`: `Galaxy` (→ `game_setup`), `StarSystem`/`Hex` (→ `sidebar`)
- stdlib: `os` (unused today), `random` (→ `game_setup`), `math` (→ `game_camera`)

**Keep deliberately:** `PROFILE` (back-compat for `game_module.PROFILE`), `setup_logging`/`GameLogFormatter` re-exports, `CAMERA_SMOOTH_SPEED` re-export. Add a short comment on each explaining *why* it is re-exported.

Also: function-local imports inside the moved code (`from unit_orders import ...`, `from constants import ...`, `from unit_components import WingType`, `from events import LayMinefieldEvent`, `from pathfinding import find_intersystem_path`, `import save_manager`) can be promoted to module level in the new files. Verified safe: none of `unit_orders`, `unit_components`, `events`, `pathfinding`, `entities`, `galaxy`, `visibility`, `constants` import `game` at runtime (only under `if typing.TYPE_CHECKING`). `save_manager` keeps its lazy import inside `Game.save_game`/`load_game` (it imports `galaxy`/`entities` heavily and the lazy import documents an intentional boundary).

New modules use type hints only:
```python
import typing
if typing.TYPE_CHECKING:
    from game import Game
```

---

## 6. Execution Order

Each step is independently committable and ends with a green test run. Recommended: one commit per step with message `refactor(game): extract <module>`.

| # | Step | Files touched | Verification |
|---|---|---|---|
| 1 | Extract `game_logging.py` | +1, `game.py` | `py -m pytest` |
| 2 | Extract `game_camera.py` (+ re-export `CAMERA_SMOOTH_SPEED`) | +1, `game.py` | `py -m pytest tests/test_sector_camera.py` then full |
| 3 | Extract `economy.py` | +1, `game.py` | `py -m pytest tests/test_turn_processor.py` then full |
| 4 | Extract `game_setup.py` | +1, `game.py` | `py -m pytest tests/test_save_load.py tests/test_sensors_fog_of_war.py` then full |
| 5a | `sidebar/order_formatting.py` (+ `sidebar/__init__.py`) | +2, `game.py` | `py -m pytest tests/test_unit_orders.py tests/test_unit_components.py` |
| 5b | `sidebar/panels_world.py` | +1 | `py -m pytest tests/test_sector_sidebar_objects.py` |
| 5c | `sidebar/panels_unit.py` | +1 | `py -m pytest tests/test_unit_selection_sidebar.py tests/test_strikecraft_bay_gui.py` |
| 5d | `sidebar/builder.py` (+ `game.py` delegate) | +1, `game.py` | full suite |
| 6 | `game_actions/` package (4 files) | +4, `game.py` | `py -m pytest tests/test_minefield.py tests/test_unload_resources_nearest.py tests/test_unit_selection_sidebar.py tests/test_sector_sidebar_objects.py` then full |
| 7 | Import pruning + docstrings in `game.py` | `game.py` | `py -c "import game"` + full suite |
| 8 | Update `README.md` project-structure block (+ optionally `Wormhole_Control_analysis_report.md` §2.1) | docs | manual review |

**Commands**
```bat
py -m pytest -q                :: expect 453 passed
py -c "import game"            :: import-cycle / import-time smoke check
py game.py                     :: manual smoke: main menu -> New Game -> galaxy/system/sector, select unit,
                               :: check both sidebar tabs, issue an order, end turn, save, load, unit editor
```

### 6.1 Manual smoke checklist (step 8, before final commit)
1. Main menu → About → back → **New Game**.
2. Galaxy → click system (sidebar: wormholes/objects) → middle-click into system → click hex (sidebar: bodies/units/minefields buttons) → middle-click into sector.
3. Sector: mouse-wheel zoom (anchored at cursor, smooth), middle-drag pan, drag-select multiple units.
4. Select 1 unit → rename via text entry → **Basic Info** and **Components** tabs → component dropdown → order-queue HTML renders with colours/indentation.
5. Right-click context menu: issue Move, Attack, Mine; verify the queue text; **Stop Selected Units**.
6. Carrier: Deploy / Launch All Wings / Recall; Minelayer: Lay Minefield; Miner: Unload Resources (nearest).
7. End Turn (resource HUD + turn label + player colour update) → Save Game → Quit to main menu → Load Game.
8. Unit Editor: open, save a design, confirm shipyard constructors refresh (log line), delete design.

---

## 7. Risk Register

| # | Risk | Likelihood | Mitigation |
|---|---|---|---|
| R1 | Tests calling unbound methods with `MagicMock` self break | High if mis-designed | **Design rule §2.1**: extracted code = module functions taking `game`; `Game` methods stay as delegates. No collaborator objects on `self`. |
| R2 | Circular imports (`sidebar` ↔ `game`) | Low | New modules import only leaf modules; `Game` referenced solely under `TYPE_CHECKING`. Verified no runtime `import game` exists outside tests. |
| R3 | `commander.py` breaks (calls `_generate_order_data_recursive`) | Medium | Keep the identically-named delegate on `Game`. Covered by `tests/test_unit_components.py::test_commander_get_sidebar_data_stance_dropdown`. |
| R4 | Silent behaviour drift while moving 700+ lines | Medium | Move code **verbatim**, mechanically renaming `self.` → `game.`; defer all cleanup (registry conversion, helper dedup) to a separate commit within the same step so `git diff` stays reviewable. |
| R5 | `game_module.PROFILE` toggle no longer reaches the sidebar | Low (cosmetic) | Documented in §4.5-note-2; `constants.PROFILE` used instead; no assertions depend on it. |
| R6 | Removing an import that is actually used | Low | Prune only in step 7, one name at a time, each grep-verified, with `py -c "import game"` + full suite after. |
| R7 | Merge conflicts with in-flight work | Medium | Steps are small and sequential; land quickly, rebase between steps. `git revert` of a single step is clean since each step is one commit. |

---

## 8. Definition of Done

- [ ] `game.py` ≤ 300 lines; no method other than `__init__` exceeds ~40 lines.
- [ ] 13 new files created as per §3; no file in the refactor exceeds ~360 lines.
- [ ] `py -m pytest -q` → **453 passed**, zero modifications to any file under `tests/`.
- [ ] No source file other than `game.py` and `README.md` is modified.
- [ ] `from game import Game, CAMERA_SMOOTH_SPEED, setup_logging` and `game_module.PROFILE` still work.
- [ ] `py game.py` runs; §6.1 smoke checklist passes.
- [ ] `README.md` project-structure tree lists the new modules/packages with one-line descriptions.
- [ ] Every new module and public function has a docstring in the existing Google-style format (`Args:` / `Returns:`).

---

## 9. Explicitly Out of Scope

- Restructuring `Game.__init__` state into sub-objects (would break `save_manager.py` / `input_processor.py`).
- Refactoring `gui.py` (~1,800 lines) or `unit_editor_gui.py` (~1,880 lines) — the other two monoliths named in the analysis report; they warrant their own plans.
- De-duplicating the upkeep math in `turn_processor.py` (flagged in §4.3 as a follow-up).
- Any gameplay, balance, or rendering change.
- Renaming `in_hex` → `hex_coord` and the `hangar`/`bay` terminology cleanup (analysis report §4).