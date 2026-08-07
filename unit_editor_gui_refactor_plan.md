# `unit_editor_gui.py` Refactor Plan

## Goal
Split the monolithic `unit_editor_gui.py` (1,773 lines / ~81 KB) — which currently
combines layout creation, state sync, widget creation, dynamic cost
recalculation, and template serialization inside a single `UnitEditorWindow`
class — into a new `gui/unit_editor_gui/` sub-package, following the same
pattern already used for `gui/` (former `gui.py`) and
`rendering/sector_renderer/` (former monolithic renderer).

Decision made with user: **Option 2** — delete the root-level
`unit_editor_gui.py`, update all import sites, and remove 5 confirmed
write-only/dead attributes in the same pass.

---

## 0. Baseline (recorded before any changes)

- Environment: Python 3.14.3, pytest 9.0.3, `pytest.ini` sets `pythonpath = .`.
- `py -3 -m pytest tests/test_unit_editor.py tests/test_dynamic_component_scaling.py tests/test_strikecraft_bay_gui.py -q`
  → **48 passed**.
- Full suite (`Wormhole_Control_analysis_report.md`) previously reported
  **444 passed** for the whole repo — re-verify this exact count after the
  refactor.
- `git log --oneline -8` shows this project's established refactor precedent:
  - `757af6b` / `df4b82e`: `gui.py` → `gui/` package split (handler.py +
    theme_loader/layouts/sidebar_view/context_menu/event_router modules),
    100% backward-compatible facade preserved.
  - `193b120`: `rendering/sector_renderer.py` → `rendering/sector_renderer/`
    sub-package with an `__init__.py` facade re-exporting the public API.
  - Analysis-report items get removed from `Wormhole_Control_analysis_report.md`
    once addressed (`2cb4ef1`, `d2b3dbe`).

## 1. Current file structure (verified via full read + line-numbered scan)

| Lines | Content |
|---|---|
| 1–24 | Module docstring + ASCII layout diagram |
| 26–37 | Imports (`constants`, `custom_unit_templates`, `unit_components`) — **some unused** |
| 39–75 | `COMPONENT_ROWS` (19-entry catalogue), `HULL_SIZE_NAMES`, `TURRET_TYPES`, `TURRET_VARIANTS`, `ABILITY_NAMES`, `HYPERDRIVE_TYPES` |
| 78–97 | `_lerp_color()` helper |
| 100–228 | `UnitEditorWindow.__init__` — design state, panel geometry, ~50 widget-reference field declarations |
| 234–293 | `_build_ui()` orchestrator |
| 295–431 | `_build_col1_config()` (137 lines) — hull dropdown, capacity bar, design key/display name, load/save/delete |
| 433–492 | `_build_col2_components()` (60 lines) — component toggle/cost/select rows |
| 494–817 | `_build_col3_details()` (**324 lines**, largest method) — 13 per-component detail groups + inline `DESCRIPTIONS` dict |
| 819–850 | `_build_col4_summary()` (32 lines) |
| 856–882 | `show()` / `hide()` / `kill()` |
| 888–1013 | `process_event()` (126 lines) — button/dropdown/text-entry dispatch |
| 1019–1042 | `draw()` — capacity bar rendering |
| 1048–1163 | 11 × `_read_*_params()` methods (116 lines total) |
| 1169–1222 | `_current_hull_used()`, `_sync_dynamic_costs()`, `_capacity_text()` |
| 1224–1352 | `_toggle_component`, `_toggle_ability`, `_update_component_toggle_labels`, `_update_ability_toggle_labels`, `_update_capacity_label`, `_on_hull_changed`, `_select_component`, `_refresh_component_details`, `_hide_turret_list` |
| 1354–1416 | `_apply_hull_restrictions()` (63 lines) |
| 1418–1491 | `_do_add_turret()`, `_rebuild_turret_list()` |
| 1493–1556 | `_do_save()`, `_do_delete()` |
| 1558–1691 | `_sync_widgets_from_template()`, `_load_design()`, `_refresh_load_dropdown()` |
| 1693–1773 | `_update_summary()`, `_set_status()` |

## 2. Hard constraints (must not break)

1. **Consumers**: `gui/handler.py`
   - L18 (inside `if typing.TYPE_CHECKING:`): `from unit_editor_gui import UnitEditorWindow`
   - L279 (lazy import inside `open_unit_editor`): `from unit_editor_gui import UnitEditorWindow`
2. **Tests pin the private API directly** (`tests/test_unit_editor.py`,
   `tests/test_dynamic_component_scaling.py`):
   - Module-level: `COMPONENT_ROWS`
   - Construction: `UnitEditorWindow(mgr, pygame.Vector2(...), tmp_mgr)`
   - Attributes: `_selected_component_key`, `_comp_select_btns`, `_details_hdr.text`,
     `_add_turret_button`, `_turrets`, `_repair_rate_entry`, `_repair_range_entry`,
     `_mining_rate_entry`, `_mining_range_entry`, `_mining_max_cargo_entry`,
     `_hangar_slots_entry`, `_strikecraft_bay_slots_entry`, `_inhibitor_radius_entry`,
     `_comp`, `_hull_size`, `_current_hull_used`, `_summary_box`
   - Methods: `_select_component()`, `process_event()`, `show()`, `kill()`,
     `_read_repair_params()`, `_update_summary()` (called directly on a bare
     `UnitEditorWindow.__new__(UnitEditorWindow)` instance with only 6 attrs set
     — see `test_dynamic_component_scaling.py::test_unit_editor_summary_hull_size_scaling`)
3. **`_update_summary` constraint is the strictest one**: it must remain a
   real method on `UnitEditorWindow` that only touches
   `_comp`, `_hull_size`, `_turrets`, `_selected_abilities`, `_current_hull_used`,
   `_summary_box` (per the bare `__new__` test). A thin one-line delegating
   method body is fine; a mixin/multiple-inheritance redesign is NOT safe
   because `__new__` bypasses `__init__` entirely.
4. **`gui/` package conventions to match** (observed in `layout_hud.py`,
   `sidebar_view.py`, `event_router.py`, `context_menu.py`):
   - Lowercase snake_case module names.
   - Module-level functions take the owner object as the first positional
     arg, e.g. `def setup_game_ui(gui) -> None`.
   - `typing.TYPE_CHECKING` guarded imports for cross-module type hints.
   - A package `__init__.py` re-exporting the public facade
     (`gui/__init__.py` → `from .handler import GUI_Handler`).
   - Same pattern in `rendering/sector_renderer/__init__.py`, which
     re-exports classes/constants from its internal sub-modules.

## 3. Target package layout

```
gui/unit_editor_gui/
├── __init__.py           # Facade: re-export UnitEditorWindow, COMPONENT_ROWS, option lists
├── catalog.py            # COMPONENT_ROWS, HULL_SIZE_NAMES, TURRET_TYPES, TURRET_VARIANTS,
│                         #   ABILITY_NAMES, HYPERDRIVE_TYPES, WING_TYPES, COMPONENT_DESCRIPTIONS
├── widget_factory.py     # make_label/make_entry/make_dropdown/make_button helpers + LayoutMetrics
├── window.py             # UnitEditorWindow class: state/geometry init, show/hide/kill,
│                         #   thin delegating methods preserving every existing name
├── layout.py             # build_ui() orchestrator + columns 1 (config), 2 (components), 4 (summary)
├── layout_details.py     # column 3: 13 per-component detail widget groups
├── event_handlers.py     # process_event() dispatch table
├── param_readers.py      # the 11 read_*_params() input-parsing functions
├── cost_model.py         # lerp_color, draw_capacity_bar, current_hull_used,
│                         #   sync_dynamic_costs, capacity_text/label
├── component_state.py    # toggle_component, toggle_ability, toggle-label refresh,
│                         #   on_hull_changed, select_component, refresh_component_details,
│                         #   apply_hull_restrictions
├── turret_editor.py      # do_add_turret, rebuild_turret_list, hide_turret_list
├── template_io.py        # do_save, do_delete, load_design, sync_widgets_from_template,
│                         #   refresh_load_dropdown, set_status
└── summary_view.py       # update_summary() HTML generation
```

Every module stays under ~300 lines. Each has exactly one responsibility,
directly resolving the analysis report's complaint that the file "contains
layout creation, state sync, widget creation, dynamic cost recalculation,
and template serialization in a single class."

## 4. Mechanical transformation rules (behaviour must stay byte-identical)

- Each extracted method `def _foo(self, x): ...` becomes a module-level
  function `def foo(editor, x): ...` in its new module, operating on the
  `UnitEditorWindow` instance (`editor`) via its existing attribute names.
- `UnitEditorWindow` keeps a same-named method that is a 1-line delegate:
  ```python
  def _foo(self, x):
      """<original docstring, verbatim>"""
      return component_state.foo(self, x)
  ```
  This preserves **every** private method name and **every** attribute name
  (~50 fields) so `gui/event_router.py` and all pinned tests need zero
  behavioural changes.
- `_build_col3_details`'s 324 lines of repetitive
  `UILabel(...) / UITextEntryLine(...)` construction calls get compressed
  using `widget_factory` helper functions that pass through the *same*
  `manager`, `container`, `object_id` strings, and `pygame.Rect` geometry —
  purely a de-duplication, not a behavioural change. This is done as a
  **separate, independently-verified step** after the initial 1:1 move
  passes tests (see Step 6.2).
- The inline `DESCRIPTIONS` dict (component descriptions for info-only
  components) moves verbatim into `catalog.COMPONENT_DESCRIPTIONS`.
- `_lerp_color` becomes `cost_model.lerp_color` (was already module-private,
  no external callers found via repo-wide search).

## 5. Import-site updates

| File | Change |
|---|---|
| `gui/handler.py` L18 | `from unit_editor_gui import UnitEditorWindow` → `from .unit_editor_gui import UnitEditorWindow` (under `TYPE_CHECKING`) |
| `gui/handler.py` L279 | Same import, lazy/local form inside `open_unit_editor()` |
| `tests/test_unit_editor.py` L311, 380, 409, 432 | `from unit_editor_gui import ...` → `from gui.unit_editor_gui import ...` |
| `tests/test_dynamic_component_scaling.py` L120 | `from unit_editor_gui import UnitEditorWindow` → `from gui.unit_editor_gui import UnitEditorWindow` |
| `README.md` | Move the `unit_editor_gui.py` bullet out of the flat file list and into the `gui/` package tree, listing the 13 new modules (matching how the `gui/` and `rendering/sector_renderer/` entries are already documented) |
| `Wormhole_Control_analysis_report.md` | Remove the now-resolved §2.1 item 1 (`unit_editor_gui.py` monolith bullet), consistent with how `2cb4ef1` and `d2b3dbe` removed previously-addressed items |
| `unit_editor_gui.py` (root) | Delete. Use `git mv` semantics where practical (i.e. create `gui/unit_editor_gui/window.py` by moving+editing the original file's class body) so history is preserved in git blame/log where feasible |

No circular-import risk: the new package will only import `constants`,
`custom_unit_templates`, `unit_components`, `pygame`, `pygame_gui` — never
`gui.handler` or anything else in `gui/`.

## 6. Confirmed cleanups bundled into this pass

### 6.1 Bug fix
`_read_sensor_params` (original line 1091) references
`DEFAULT_SENSOR_SHORT_RANGE` as a fallback value, but that name is **never
imported** in `unit_editor_gui.py` today — this is a latent `NameError` bug
on the fallback branch (only reachable if `_sensor_short_range_entry` is
`None`). Fix: import `DEFAULT_SENSOR_SHORT_RANGE` from `constants` in the new
`param_readers.py`.

### 6.2 Dead imports to remove
`MIN_ANTIMATTER_CAPACITY`, `calc_engine_hull_cost`, `calc_weapons_hull_cost`,
`calc_defenses_hull_cost`, `calc_hyperdrive_hull_cost` — imported in the
original file but never referenced anywhere in it (verified via
line-numbered regex scan).

### 6.3 Dead / write-only attributes to remove
Verified via a **repo-wide** search (all `.py`, `.json`, `.md` files) that
these are assigned in `unit_editor_gui.py` and never read anywhere else in
the codebase (including tests):
- `self._turret_list_box` (declared, assigned `None`, never used)
- `self._abil_hdr` (declared, assigned `None`, never used — note:
  `abil_hdr` local variable in `_build_col3_details` IS used locally and is
  NOT the same as this dead instance attribute)
- `self._abilities_y_start` (assigned twice, `0` then `c2y`, never read)
- `self._design_name` (assigned `""`, never read or written again — actual
  design key state lives in `_name_entry` / `_editing_key`)
- `self._display_name` (assigned `""`, never read or written again — actual
  display name state lives in `_display_entry`)

These will be removed from `window.py`'s `__init__` and from
`layout.py`'s column-2 builder (the `_abilities_y_start = c2y` assignment).

## 7. Step-by-step execution order

1. Create `gui/unit_editor_gui/` directory with `catalog.py` first (no
   dependencies on the rest), verify it imports cleanly.
2. Create `widget_factory.py` (new helper module, no state).
3. Create `cost_model.py`, `param_readers.py`, `turret_editor.py`,
   `component_state.py`, `template_io.py`, `summary_view.py`,
   `event_handlers.py` — pure function extraction, 1:1 logic move, adjusted
   to take `editor` as first parameter instead of `self`.
4. Create `layout.py` and `layout_details.py` — move the 5 `_build_*`
   methods, converted to module functions taking `editor` + explicit layout
   params, using the **original raw widget construction calls** first (no
   `widget_factory` compression yet, to keep this step lowest-risk).
5. Create `window.py` — the `UnitEditorWindow` class: keep `__init__` logic
   (minus the 5 dead attributes), `show/hide/kill`, and add delegating
   wrapper methods for every method extracted in steps 3–4, preserving
   docstrings and signatures exactly.
6. Create `__init__.py` facade re-exporting `UnitEditorWindow`,
   `COMPONENT_ROWS`, and any other names tests import directly.
7. Update `gui/handler.py` import sites (2 locations).
8. Update `tests/test_unit_editor.py` and
   `tests/test_dynamic_component_scaling.py` import lines.
9. Delete root `unit_editor_gui.py`.
10. Run full test suite; fix any fallout.
11. **Separate follow-up step**: compress `layout_details.py`'s repetitive
    widget construction using `widget_factory` helpers; re-run full test
    suite to confirm no rect/behavioural drift.
12. Update `README.md` project structure tree and
    `Wormhole_Control_analysis_report.md` (remove resolved item).

## 8. Verification checklist

1. `py -3 -m pytest -q` → expect the previously-recorded **444 passed**
   (or the current true baseline count re-measured at Step 0 execution time)
   with no new failures/errors.
2. Targeted re-run:
   `py -3 -m pytest tests/test_unit_editor.py tests/test_dynamic_component_scaling.py tests/test_strikecraft_bay_gui.py -q`
   → expect the same **48 passed** as the pre-refactor baseline.
3. Import smoke test:
   `py -3 -c "from gui import GUI_Handler; from gui.unit_editor_gui import UnitEditorWindow, COMPONENT_ROWS; print('ok')"`
4. Headless functional smoke test (`SDL_VIDEODRIVER=dummy`):
   - Construct `UnitEditorWindow(manager, screen_res, template_manager)`.
   - `show()`.
   - Call `_select_component()` across all 19 `COMPONENT_ROWS` keys, confirm
     `_details_hdr.text` updates and no exceptions.
   - Simulate `UI_BUTTON_PRESSED` on `_add_turret_button`, confirm
     `_turrets` grows by 1.
   - Call `_do_save()` / `_load_design()` round-trip with a temp
     `CustomTemplateManager`.
   - `kill()`, confirm no exceptions and all internal collections clear.
5. `git grep -n "unit_editor_gui"` across the repo → confirm all remaining
   references point at `gui.unit_editor_gui` / `gui/unit_editor_gui/`, with
   no stale root-module references left (except this plan file and the
   analysis report's historical mentions, if retained).
6. Manual review diff of `layout_details.py` before/after the Step 11
   `widget_factory` compression — confirm identical `pygame.Rect` values
   and `object_id` strings per widget.

## 9. Risk assessment

- **Low risk**: the bulk of the work is a mechanical move with thin
  delegating methods; no widget IDs, rects, attribute names, or public
  method signatures change in steps 1–10.
- **Only two semantic edits**: the `DEFAULT_SENSOR_SHORT_RANGE` import fix
  (Step 6.1) and the 5 dead-attribute removals (Step 6.3) — both are
  additive/removal-only and provably safe per the repo-wide dead-code scan
  already performed.
- **Highest-scrutiny step**: Step 11 (widget_factory compression of column
  3) touches the most widget-construction call sites; it is deliberately
  isolated as its own verified step so any rect/geometry regression is easy
  to bisect.
