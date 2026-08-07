# `gui.py` Refactoring Plan -> `gui/` Package

**Status:** Proposed (no code changes made yet)
**Target file:** `gui.py` - 1,620 lines / 79 KB (single class `GUI_Handler` + one module function)
**Goal:** Split the monolithic UI manager into a focused `gui/` package (11 modules, none > ~320 lines), **and** move the leaked inhibitor-toggle game logic into `game_actions/unit_actions.py`, without changing observable behaviour and without breaking any of the 453 existing tests.

**Verified baseline:** `py -m pytest --collect-only -q` -> `453 tests collected` (Python 3.14.3).

---

## 1. Current Structure Analysis

`gui.py` currently fulfils nine unrelated responsibilities. Measured breakdown:

| Lines | Section | Size | Responsibility |
|---|---|---:|---|
| 1-20 | Imports | 20 | `os` and `PROFILE` imported but never used |
| 23-39 | `_editor_action_to_gui_action()` | 17 | Unit-editor action string -> GUI action payload |
| 50-129 | `__init__`: theme scaling + `UIManager` + font preloading | 80 | Rewrites `theme.json` -> `theme_scaled.json`, preloads DejaVu/Noto fonts |
| 131-197 | `__init__`: ~50 widget/state field declarations | 67 | Canonical widget-attribute schema |
| 199-235 | `clear_and_reset` | 37 | Teardown of every panel + field reset |
| 238-303 | `hide_all_panels`, `show_main_menu`, `show_about_screen`, `show_game_ui`, `toggle/show/hide_ingame_menu`, `is_ingame_menu_open` | 66 | Screen visibility state machine |
| 306-365 | `setup_main_menu` | 60 | Main-menu layout |
| 366-449 | `setup_about_screen` | 84 | About-screen layout + hard-coded HTML blob |
| **450-605** | **`setup_game_ui`** | **156** | Top/bottom bars, resource labels, sidebar panel, `galaxy_generation_rect` |
| 607-708 | `setup_ingame_menu` | 102 | Pause menu (5 near-identical copy-pasted button blocks) |
| 710-771 | `show_load_game_dialog` | 62 | Save-file selection window |
| **773-1084** | **`process_event`** | **312** | Monolithic event router: 72 lines static buttons, 24 inhibitor, 45 context menu, 102 dynamic sidebar, 32 pause menu, 45 text-entry/dropdown/editor |
| 1086-1110 | `update`, `draw` | 25 | Per-frame manager update + galaxy border draw |
| 1112-1124 | `is_any_text_entry_focused` | 13 | Keyboard-focus query |
| 1126-1167 | `open/close/is_open/process` unit editor | 42 | Unit-editor window bridge |
| 1169-1237 | `update_back_button_visibility`, `update_view_mode_label`, `update_turn_label`, `update_player_color_indicator`, `update_resource_display` | 69 | HUD text/colour updaters |
| 1239-1255 | `clear_side_bar_content`, `is_section_expanded`, `toggle_section_expansion` | 17 | Sidebar element/state bookkeeping |
| 1257-1340 | `wrap_text_to_lines` | 84 | Pure pixel-width text wrapper (touches no instance state) |
| **1342-1522** | **`update_side_bar_content`** | **181** | Sidebar widget factory: row grouping + 8-branch item-type chain |
| 1524-1571 | `open_context_menu` | 48 | Context menu + submenu construction |
| 1573-1620 | `close_context_menu`, `is_mouse_over_context_menu`, `is_mouse_over_gui_panels` | 47 | Teardown + hit-testing |

### 1.1 Key Findings

1. **Three hotspots are 40% of the file**: `process_event` (312), `update_side_bar_content` (181), `setup_game_ui` (156).
2. **Screen-layout code is 464 lines** (main menu, about, HUD, pause menu, load dialog) and is pure widget construction - trivially extractable with no logic risk.
3. `wrap_text_to_lines` (84 lines) is a **pure function** that only uses `self` for the method binding.
4. The analysis report's phrase *"build menu elements"* does **not** map to a separate menu: the build/deploy/wing-type buttons are emitted as sidebar payload dicts by `unit_components/strikecraft.py` and merely *decoded* inside `process_event`'s dynamic-button chain (lines 903-1004). That concern therefore maps onto the new `dynamic_actions.py` - **no separate build-menu module is warranted**.
5. **Leaked game logic (to be fixed):** lines 831-855 handle `#toggle_inhibitor_button` by constructing a `ToggleInhibitorOrder` and calling `inhibitor.toggle(galaxy_ref=...)` *inside the GUI layer*. This is the only place in the codebase where the GUI mutates game state instead of emitting an action dict. Every other button returns a payload consumed by `game_actions/`.

### 1.2 Existing Architectural Precedent to Follow

The repo already uses **module-level functions taking the owner object as the first parameter, with the class keeping one-line delegate methods**:

- `game.py` -> `game_camera.py`, `economy.py`, `game_setup.py`, `game_actions/`, `sidebar/`
- `sidebar/` and `game_actions/` are packages with a re-exporting `__init__.py`, relative sibling imports (`from .panels_world import ...`), and Google-style docstrings (`Args:` / `Returns:`).
- `renderer.py` (57 lines) is a thin facade over the `rendering/` package.

This refactor applies the identical pattern to `gui.py`.

### 1.3 Design Alternatives Considered (and rejected)

| Option | Verdict |
|---|---|
| **Mixin classes** (`class GUI_Handler(HudMixin, SidebarMixin, ...)`) | Preserves `self.*` verbatim and needs no delegates, but the pattern appears nowhere in this repo and makes attribute ownership implicit. **Rejected.** |
| **Sub-controller objects with `parent` back-refs** (the `rendering/sector_renderer/` pattern) | Good when each sub-renderer owns its own caches, but here ~50 widget attributes are read directly by `input_processor.py`, `rendering/galaxy_renderer.py` and the tests, requiring ~45 forwarding properties. **Rejected.** |
| **Module functions taking `gui` + thin delegates** | Matches the dominant repo convention; lowest risk for the test suite. **CHOSEN.** |

---

## 2. Hard Compatibility Constraints (grep-verified)

### 2.1 `from gui import GUI_Handler` must keep working

Only two importers exist:

| Caller | Line |
|---|---|
| `game.py` | `19: from gui import GUI_Handler` |
| `tests/test_text_field_focus.py` | `6: from gui import GUI_Handler` |

A `gui/` package whose `__init__.py` re-exports `GUI_Handler` satisfies both. **`gui.py` must be deleted in the same commit** - a package and a same-named top-level module cannot sensibly coexist on `sys.path`.

### 2.2 Every public method and widget attribute must stay on the instance

| Consumer | Members used |
|---|---|
| `game.py` | `show_main_menu`, `show_game_ui`, `clear_and_reset`, `update`, `update_view_mode_label`, `update_turn_label`, `update_player_color_indicator`, `update_resource_display` |
| `input_processor.py` | `process_event`, `is_any_text_entry_focused`, `is_ingame_menu_open`, `is_unit_editor_open`, `show_main_menu`, `open_context_menu`, `close_context_menu`, `is_mouse_over_context_menu`, `galaxy_generation_rect`, `manager.ui_group.sprites()` |
| `renderer.py` | `draw(surface)` |
| `game_camera.py` | `is_mouse_over_gui_panels` |
| `game_actions/app_actions.py` | `show_about_screen`, `show_main_menu`, `toggle_ingame_menu`, `is_unit_editor_open`, `open_unit_editor`, `close_unit_editor`, `update_back_button_visibility` |
| `sidebar/builder.py` | `manager.get_theme().load_theme(...)`, `update_side_bar_content(data_list)` |
| `unit_components/commander.py` (line 281) | `is_section_expanded(section_key)` |
| `rendering/galaxy_renderer.py` (lines 34, 35, 44, 162, 163) | `galaxy_generation_rect` |
| `tests/test_save_load.py` (lines 134-140) | `setup_main_menu`, `show_load_game_dialog`, `load_game_button`, `load_save_window`, `load_save_confirm_button`, `load_save_cancel_button` |
| `tests/test_text_field_focus.py` | ctor `GUI_Handler(Position(800,600), game)`, `.manager`, `is_any_text_entry_focused`, `patch.object(gui, 'process_event'/'is_ingame_menu_open'/'is_unit_editor_open')` |
| `tests/test_ability_context_menu.py` (line 168) | `patch.object(game.gui, 'open_context_menu')` |
| `tests/test_sector_camera.py` (line 105) | `gui.is_mouse_over_gui_panels` (MagicMock) |

**Design rule:** extracted code becomes module functions whose first parameter is `gui`; `GUI_Handler` keeps a one-line delegate for each. All state stays as attributes on the handler instance. No sub-objects, no property forwarding -> `patch.object` and direct attribute reads in tests keep working unchanged.

### 2.3 Behaviour that must not drift

- Calls back into the game object: `game_instance.get_player_income/get_player_upkeep`, `.selected_objects`, `.sidebar_needs_update`, `.galaxy`, `.view_mode`.
- `resource_path()` resolves against **CWD** (`utils.py:27` -> `os.path.abspath(".")`), **not** the module directory, so `theme.json` / `theme_scaled.json` loading is unaffected by moving code into a subpackage. Verify by smoke test anyway.
- Lazy imports must **stay lazy**: `save_manager` (load dialog), `unit_editor_gui` (open editor), `entities` (inhibitor branch, being removed - see 4.11).
- `self.manager.set_visual_debug_mode(True)` is currently unconditional - **keep as-is**, it is not a refactor concern.
- `process_event` returns a 3-way contract that `input_processor.py:83-88` depends on: an action dict / `{'action': 'ui_handled'}` / `None`.
- The `elif` ordering inside `process_event` is **precedence-significant** and must be preserved exactly.

---

## 3. Target File Layout

```
gui/
├── __init__.py              (~25)   Re-exports GUI_Handler (+ _editor_action_to_gui_action)
├── handler.py               (~320)  GUI_Handler: ctor/state fields, clear_and_reset, screen
│                                    visibility, update/draw, unit-editor bridge, hit-testing,
│                                    and one-line delegates to every sibling module
├── theme_loader.py          (~95)   build_ui_manager(screen_res): scaled-theme generation + fonts
├── layout_main_menu.py      (~155)  setup_main_menu(gui), setup_about_screen(gui)
├── layout_ingame_menu.py    (~175)  setup_ingame_menu(gui), show_load_game_dialog(gui)
├── layout_hud.py            (~240)  setup_game_ui(gui) + HUD updaters
├── sidebar_view.py          (~215)  update_side_bar_content(gui, data_list) widget factory,
│                                    clear_side_bar_content, section-expansion helpers
├── text_layout.py           (~95)   wrap_text_to_lines(text, max_pixel_width, font)
├── context_menu.py          (~110)  open/close/hit-test + enter_submenu/leave_submenu
├── event_router.py          (~195)  process_event(gui, event) dispatch + _editor_action_to_gui_action
└── dynamic_actions.py       (~150)  Sidebar dynamic button/dropdown -> action-payload registry
```

Plus **one modified existing file**: `game_actions/unit_actions.py` (+`handle_toggle_inhibitor`) and **one new test file**: `tests/test_inhibitor_gui_action.py`.

**11 new files** in `gui/`; `gui.py` deleted. Largest file ~320 lines (down from 1,620).

---

## 4. Module-by-Module Specification

### 4.1 `gui/__init__.py`

```python
"""GUI management package (top bar, sidebar, context menu, and menus)."""
from .handler import GUI_Handler
from .event_router import _editor_action_to_gui_action

__all__ = ['GUI_Handler', '_editor_action_to_gui_action']
```

Mirrors `sidebar/__init__.py`. `_editor_action_to_gui_action` is re-exported purely to preserve the old module surface.

### 4.2 `gui/theme_loader.py` - *(from lines 50-129)*

```python
def build_ui_manager(screen_res) -> pygame_gui.UIManager:
    """Builds a UIManager using a TEXT_SCALE-scaled copy of theme.json with preloaded fonts.

    Args:
        screen_res: Screen resolution vector exposing .to_tuple().

    Returns:
        pygame_gui.UIManager: Configured manager, falling back to the default theme on error.
    """
```

Verbatim move of the `try/except FileNotFoundError/pygame.error` cascade, the `theme_scaled.json` writer (font size/point_size scaling, font path resolution, per-element font scaling, `drop_down_menu.#drop_down_options_list` `list_item_height`), and both font-preload blocks. In `handler.__init__`: `self.manager = build_ui_manager(self.screen_res)` followed by the existing `set_visual_debug_mode(True)` call.

**Imports:** `json`, `logging`, `pygame`, `pygame_gui`, `constants.TEXT_SCALE`, `utils.resource_path`.

### 4.3 `gui/layout_main_menu.py` - *(306-449)*

- `setup_main_menu(gui)` - panel + title + 4 buttons (New Game / Load Game / About / Quit).
- `setup_about_screen(gui)` - panel + title + text box + back button.

The long About HTML string becomes a module-level `_ABOUT_HTML` constant (byte-identical text).

### 4.4 `gui/layout_ingame_menu.py` - *(607-771)*

- `setup_ingame_menu(gui)` - the five copy-pasted button blocks collapse into one loop over a module-level spec:
  ```python
  _INGAME_MENU_BUTTONS = [
      ('resume_button',           'Resume',            '#resume_button'),
      ('unit_editor_button',      'Unit Editor',       '#unit_editor_button'),
      ('save_game_button',        'Save Game',         '#save_game_button'),
      ('ingame_load_game_button', 'Load Game',         '#ingame_load_game_button'),
      ('quit_to_menu_button',     'Quit to Main Menu', '#quit_to_menu_button'),
  ]
  ```
  Rect maths, `num_buttons = 5` panel-height calc, top-to-bottom order and `setattr(gui, attr, button)` assignment preserve current behaviour exactly.
- `show_load_game_dialog(gui)` - verbatim, keeping the **lazy** `import save_manager`.

### 4.5 `gui/layout_hud.py` - *(450-605, 1169-1237)*

`setup_game_ui(gui)` plus `update_back_button_visibility`, `update_view_mode_label`, `update_turn_label`, `update_player_color_indicator`, `update_resource_display`. Grouped together because they build **and** mutate the same widgets. `galaxy_generation_rect` assignment and the trailing `hide_all_panels()` call stay in `setup_game_ui`. The unused local `element_height` (line 454) is dropped.

### 4.6 `gui/text_layout.py` - *(1257-1340)*

```python
def wrap_text_to_lines(text_to_wrap: str, max_pixel_width: int, font) -> tuple[list[str], int]:
```

Takes no `gui` parameter. Character-level fallback for over-wide words and the `pygame.error` guards move verbatim. `GUI_Handler.wrap_text_to_lines(self, ...)` remains as a delegate for API compatibility.

### 4.7 `gui/sidebar_view.py` - *(1239-1255, 1342-1522)*

```python
def clear_side_bar_content(gui) -> None
def is_section_expanded(gui, section_id: str) -> bool
def toggle_section_expansion(gui, section_id: str) -> None
def update_side_bar_content(gui, data_list: list[dict]) -> None
```

The 8-branch `if item_type == ...` chain becomes a builder table:
```python
_ITEM_BUILDERS = {
    'label': _build_label, 'text_box': _build_text_box, 'button': _build_button,
    'inhibitor_button': _build_inhibitor_button, 'progress_bar': _build_progress_bar,
    'drop_down_menu': _build_drop_down_menu, 'text_entry_line': _build_text_entry_line,
}
```

Each `_build_*(gui, item_data, rect, obj_id, container)` returns the consumed height and appends to `gui.side_bar_dynamic_elements` / `gui.dynamic_button_actions` / `gui.dynamic_dropdown_actions` / `gui.unit_name_entry` exactly as today. Row grouping (`side_by_side`), `indent_level`, `TEXT_SCALE` height maths, `ObjectID` construction, and the `row_max_height` / `current_y_offset` accumulation stay in the orchestrator loop untouched - this is the contract exercised by `test_unit_selection_sidebar.py`, `test_sector_sidebar_objects.py`, `test_strikecraft_bay_gui.py`, `test_unit_components.py`.

### 4.8 `gui/context_menu.py` - *(1524-1596, plus 858-901 submenu logic)*

```python
def open_context_menu(gui, position, options, target) -> None
def close_context_menu(gui) -> None
def is_mouse_over_context_menu(gui, mouse_pos) -> bool
def enter_submenu(gui, button_index) -> None   # push child menu with a back item
def leave_submenu(gui) -> None                 # restore parent options
def handle_button_index(gui, index) -> dict | None  # submenu / back / normal select
```

`handle_button_index` returns `{'action': 'ui_handled'}` for submenu navigation or `{'action': 'context_menu_select', 'action_id': ..., 'target': ...}` (closing the menu) otherwise - removing ~45 lines of menu-stack manipulation from the event router. Submenu detection (`isinstance(action_id, list)`), the arrow suffix, `__submenu_back__` sentinel, and `context_menu_parent_options/position` bookkeeping move verbatim.

### 4.9 `gui/event_router.py` - *(773-1084)*

```python
def _editor_action_to_gui_action(editor_action: str) -> dict | None
def process_event(gui, event) -> dict | None
def _route_button_pressed(gui, event) -> dict | None
def _route_text_entry_finished(gui, event) -> dict | None
def _route_drop_down_changed(gui, event) -> dict | None
```

Static-widget matching becomes an ordered `(attr_name, payload | callable)` table so the `elif event.ui_element == self.X` ladder shrinks to a loop, **preserving the current precedence order exactly**:

1. main menu (new_game / load_game-dialog / about / quit)
2. load-save dialog (cancel / confirm)
3. about back
4. in-game HUD (end_turn / back)
5. `#toggle_inhibitor_button` -> now returns an action payload (see 4.11, moved out of the GUI)
6. context-menu buttons -> `context_menu.handle_button_index`
7. dynamic sidebar buttons -> `dynamic_actions.build_button_payload`
8. pause menu (menu / resume / save / load / quit-to-menu / unit-editor)
9. unit-editor fallthrough + `DEBUG` logging

The trailing "editor consumed this event" re-check and the `handled_by_manager` -> `{'action': 'ui_handled'}` fallback keep their current position at the end of `process_event`.

### 4.10 `gui/dynamic_actions.py` - *(903-1004, 1051-1069)*

Registry mirroring `game_actions/__init__.py`:
```python
def _shift_pressed() -> bool
PAYLOAD_BUILDERS: dict[str, Callable[[GUI_Handler, str, Any], dict | None]]
DROPDOWN_BUILDERS: dict[str, Callable[[GUI_Handler, Any, str], dict]]
def build_button_payload(gui, action_id, target_data) -> dict | None
def build_dropdown_payload(gui, action_id, target_data, selected_text) -> dict
```

Covers `unload_resources_nearest`, the three `lay_minefield*` ids (with the `anti_strikecraft` / `anti_ship` mapping), `toggle_orders_queue` (side-effecting: toggles `gui.expanded_sections` and sets `sidebar_needs_update`), `cycle_stance`, `deploy_ship`, `toggle_build_wing_type`, `launch_all_wings`, `recall_ship`, `use_ability`, `select_individual_unit`, `select_minefield`, `select_celestial_body`, `switch_unit_sidebar_tab`, `stop_unit`, `stop_selected_units`; and `set_stance` / generic passthrough for dropdowns. A shared `_shift_pressed()` replaces the four duplicated `pygame.key.get_pressed()` blocks. Unknown ids return `None`, matching today's fall-through. Dead locals `current_state_before_toggle` / `current_state_after_toggle` (lines 929/931) are dropped.

### 4.11 Inhibitor toggle: GUI -> `game_actions` *(INCLUDED per user decision)*

**Remove** from the GUI (old `gui.py:831-855`) the `from entities import Unit, ToggleInhibitorOrder` import, the selected-object loop, the `ToggleInhibitorOrder` construction and the `inhibitor_component.toggle(galaxy_ref=...)` call.

**`gui/event_router.py`** emits instead, at the same precedence position (matched by `event.ui_element.object_ids[-1] == '#toggle_inhibitor_button'`):
```python
{'action': 'toggle_inhibitor', 'shift_pressed': _shift_pressed()}
```

**`game_actions/unit_actions.py`** gains, in the file's established style:
```python
def handle_toggle_inhibitor(game, action: dict) -> None:
    """Toggles hyperspace inhibitor fields on all selected owned units.

    Args:
        game: Target game instance.
        action (dict): Action payload containing the 'shift_pressed' queueing flag.
    """
    shift_pressed = action.get('shift_pressed', False)
    for unit in game.selected_objects:
        if isinstance(unit, Unit) and unit.inhibitor_component:
            if shift_pressed:
                turn_on = not unit.inhibitor_component.is_active
                unit.commander_component.add_order(
                    ToggleInhibitorOrder(unit, {'turn_on': turn_on}))
                logger.debug(f"Queued TOGGLE_INHIBITOR order for {unit.name}.")
            else:
                success = unit.inhibitor_component.toggle(galaxy_ref=game.galaxy)
                logger.debug(
                    f"Directly toggled inhibitor for {unit.name}." if success
                    else f"Direct inhibitor toggle failed for {unit.name}.")
    game.sidebar_needs_update = True
```

- Import `ToggleInhibitorOrder` from `unit_orders` at module top (the file already does `from unit_orders import DeployAllWingsOrder, DeployUnitOrder, DockOrder, UnloadResourcesOrder`; `unit_orders/__init__.py` exports `ToggleInhibitorOrder`) - **not** from `entities`, matching the module's existing convention. `Unit` is already imported at the top of `unit_actions.py`.
- Register `'toggle_inhibitor': handle_toggle_inhibitor` in the `HANDLERS` dict.
- **Owner check:** the current GUI code has **no** owner check (it iterates all `selected_objects` unconditionally). Preserve that behaviour verbatim to avoid a functional change; do not silently add `unit.owner == current_player`.
- **Behaviour delta (documented & accepted):** the return value changes from `{'action': 'ui_handled'}` to `{'action': 'toggle_inhibitor', ...}`. `input_processor.py:85-88` passes any truthy action to `handle_gui_action` identically and `continue`s on mouse events either way, so click flow is unchanged.
- **New test** `tests/test_inhibitor_gui_action.py`: (a) direct toggle calls `inhibitor_component.toggle` once with the galaxy ref; (b) `shift_pressed=True` queues a `ToggleInhibitorOrder` with the inverted `turn_on`; (c) `'toggle_inhibitor'` is present in `game_actions.ACTION_HANDLERS`. Invoked as `Game.handle_gui_action(mock_game, action)`, matching the existing test style in `test_minefield.py` / `test_unload_resources_nearest.py`.

### 4.12 What remains in `gui/handler.py` (~320 lines)

- `__init__`: `screen_res`, `scale_x/scale_y`, `build_ui_manager(...)`, `set_visual_debug_mode(True)`, and the **unchanged** ~50 field declarations (the schema read by `test_save_load.py`, `input_processor.py`, `galaxy_renderer.py`).
- Kept in place: `clear_and_reset`, `hide_all_panels`, `show_main_menu`, `show_about_screen`, `show_game_ui`, `toggle_ingame_menu`, `show_ingame_menu`, `hide_ingame_menu`, `is_ingame_menu_open`, `update`, `draw`, `is_any_text_entry_focused`, `is_mouse_over_gui_panels`, `open_unit_editor`, `close_unit_editor`, `is_unit_editor_open`, `process_unit_editor_event`.
- 19 one-line delegates in `game.py`'s exact style:
  ```python
  def setup_main_menu(self):
      """Creates the main menu UI elements."""
      layout_main_menu.setup_main_menu(self)
  ```

---

## 5. Import Hygiene (final step, one grep-verified name at a time)

- Delete `import os` (line 9) and `PROFILE` from the `constants` import - both unused today.
- Distribute the rest: `INFO_BOX_WIDTH`/`TEXT_SCALE` -> `sidebar_view`; `TOP_BAR_HEIGHT`/`INFO_BOX_WIDTH` -> `layout_hud`; `CONTEXT_MENU_WIDTH`/`CONTEXT_MENU_ITEM_HEIGHT` -> `context_menu`; `DEBUG` -> `event_router`; `BLUE` -> `handler`; `TEXT_SCALE`/`resource_path` -> `theme_loader`; `ContextMenuOption` -> `context_menu` + `handler` (field annotations); `Vector` -> `handler`; `Position` -> `handler`/`context_menu`.
- Keep the declared-but-unused `side_bar_scroll_bar` attribute (removing it is a visible schema change with no benefit).
- Delete stale `__pycache__/gui.cpython-314.pyc` after removing `gui.py` (not importable, but misleading).

---

## 6. Migration Steps - one squashed commit per module, `py -m pytest -q` after each

| # | Step | Guard tests / verification |
|---|---|---|
| 0 | Baseline `py -m pytest -q` | **453 passed** |
| 1 | `mkdir gui`; `git mv gui.py gui/handler.py`; add `gui/__init__.py` re-export | 453 passed; `py -c "import gui; print(gui.__file__)"` -> `gui\__init__.py` |
| 2 | Extract `theme_loader.py` | 453 passed; `theme_scaled.json` regenerates identically (diff against a pre-refactor copy) |
| 3 | Extract `layout_main_menu.py` | 453 passed |
| 4 | Extract `layout_ingame_menu.py` | 453 passed - `test_save_load::test_gui_load_dialog_trigger` |
| 5 | Extract `layout_hud.py` | 453 passed - `test_turn_display`, `test_resolution_independence` |
| 6 | Extract `text_layout.py` | 453 passed |
| 7 | Extract `sidebar_view.py` | 453 passed - `test_unit_selection_sidebar`, `test_sector_sidebar_objects`, `test_strikecraft_bay_gui`, `test_unit_components` |
| 8 | Extract `context_menu.py` | 453 passed - `test_ability_context_menu` |
| 9 | Extract `dynamic_actions.py` | 453 passed - `test_minefield`, `test_unload_resources_nearest` |
| 10 | Extract `event_router.py` | 453 passed |
| 11 | **Inhibitor move** -> `game_actions/unit_actions.py` + `tests/test_inhibitor_gui_action.py` | **453 + 3 = 456 passed** |
| 12 | Import hygiene + README project-structure tree update | 456 passed; `py -c "import game"` OK; 6.1 smoke checklist |

### 6.1 Manual Smoke Checklist (before the final commit)

1. Main menu -> About -> back -> **New Game**; Load Game dialog opens/cancels from both main menu and pause menu.
2. Galaxy -> system -> sector navigation; `Back` button visible only in system/sector; galaxy border rect drawn in galaxy view.
3. Sidebar: select 1 unit -> rename via text entry -> Basic Info / Components tabs -> component dropdown -> `[+] Queued` order-queue expand/collapse; multi-select shows **Stop Selected Units**.
4. Right-click context menu including **submenu -> "Back"** navigation; issue Move/Attack/Mine and verify queue text.
5. Carrier Deploy / Launch All Wings / Recall; minelayer Lay Minefield (both types); miner Unload Resources; stance dropdown + cycle.
6. **Inhibitor: Activate/Deactivate with and without Shift** - direct toggle succeeds/fails with the same log lines; Shift queues a `TOGGLE_INHIBITOR` order visible in the queue.
7. End Turn -> resource HUD + turn label + player-colour indicator update; hover Credits for the income/upkeep/net tooltip.
8. Save -> Quit to main menu -> Load.
9. Unit Editor: open, dropdown change, save design, delete design, close (verify the shipyard-refresh log line).

---

## 7. Risk Register

| # | Risk | Likelihood | Mitigation |
|---|---|---|---|
| R1 | A test patches or reads a moved member and breaks | High if mis-designed | Design rule 2.2 - every method stays on the instance as a delegate; state stays on `self`. Consumer list grep-verified. |
| R2 | `gui.py` and `gui/` both present -> ambiguous import | Low | Step 1 uses `git mv`, so the module disappears in the same commit; verify with `py -c "import gui; print(gui.__file__)"`. |
| R3 | Behaviour drift while moving `process_event` (312 lines) | Medium | The `elif` order is precedence-significant - transcribe the ladder into the dispatch table in the documented order and re-read the diff side-by-side against the original before committing. |
| R4 | Circular imports | Low | New modules import only leaves (`constants`, `utils`, `geometry`, `pygame`, `pygame_gui`) + relative siblings; `Game`/`Player`/`UnitEditorWindow` stay under `TYPE_CHECKING`; `entities`/`save_manager`/`unit_editor_gui` imports stay lazy. |
| R5 | Theme path resolution changes in a subpackage | Low | `resource_path` is CWD-based (`utils.py:27`) - verified; still smoke-check that `theme_scaled.json` regenerates at repo root. |
| R6 | Sidebar row-layout maths subtly altered during builder extraction | Medium | Builders return the same `actual_element_total_height`; the `row_max_height` / `current_y_offset` accumulation stays in the orchestrator untouched. |
| R7 | Inhibitor behaviour change (return payload) breaks click flow | Low | `input_processor.py:85-88` treats any truthy action identically; covered by the new test + smoke item 6. |
| R8 | Adding an owner check to the inhibitor handler silently changes gameplay | Low | Explicitly **not** added (4.11); documented as a follow-up. |

---

## 8. Definition of Done

- [ ] `gui.py` deleted; `gui/` package with 11 modules; no file > ~320 lines.
- [ ] `py -m pytest -q` -> **456 passed** (453 existing + 3 new), zero modifications to existing files under `tests/`.
- [ ] Only `gui/`, `game_actions/unit_actions.py`, `tests/test_inhibitor_gui_action.py` and `README.md` are touched.
- [ ] `from gui import GUI_Handler` works; `py game.py` runs; 6.1 smoke checklist passes.
- [ ] No GUI module constructs orders or mutates unit components - all game state changes flow through `game_actions`.
- [ ] Every new module and public function has a Google-style docstring (`Args:` / `Returns:`) matching `sidebar/`.
- [ ] README project-structure tree replaces the `gui.py` line with the `gui/` package listing, and `game_actions/unit_actions.py`'s description mentions inhibitor toggling.

---

## 9. Explicitly Out of Scope

- `unit_editor_gui.py` (1,880 lines) - the other monolith named in the analysis report; warrants its own plan.
- Any visual, layout, balance or gameplay change; theme JSON edits; reviewing `set_visual_debug_mode(True)`.
- Replacing the sidebar dict-payload protocol with typed objects/dataclasses.
- Implementing a scrollable sidebar (`side_bar_scroll_bar` is declared but unused).
- Adding an owner check to the inhibitor toggle (behaviour-preserving refactor only).
- The `in_hex` -> `hex_coord` rename and `hangar`/`bay` terminology cleanup (analysis report 4).

---

