# Fog of War & `Sensors` Component — Implementation Plan

This document describes the full design and step-by-step implementation plan for
adding **fog of war** and a modular **`Sensors`** unit component to *Wormhole
Control*.

---

## 1. Goals & Requirements

From the task specification:

1. Add **fog of war** to the game.
2. Add a **`Sensors`** unit component.
3. **Short-range sensors** work only within the same sector, and additionally
   have a **limited detection radius** inside that sector (they do *not* cover
   the whole hex).
4. **Long-range sensors** detect enemy **presence** in neighbouring sectors
   (and the sensor's own sector), but do **not** reveal specific ships or their
   exact locations.
5. **Celestial objects are always visible.**
6. **Enemy units are visible only if in range of a friendly unit's sensors.**

"Friendly" = owned by the current (viewing) player. There is no alliance system,
so friendly means own units only. The viewing player is
`game.players[game.current_player_index]` (hot-seat prototype; all players are
human by default).

---

## 2. Visibility Model

For each enemy unit, visibility resolves to one of three states, evaluated with
this **priority order**:

| State | Meaning | How it's earned |
|-------|---------|-----------------|
| **DETAILED** | Enemy unit fully drawn, hoverable, selectable, targetable. | Enemy is in the **same sector (hex)** as a friendly unit whose `Sensors` has a short-range radius, **and** within that radius (Euclidean distance in sector-logical coordinates). |
| **PRESENCE** | A **generic, non-positional** "enemy present" indicator only. No ship identity, count-agnostic, no position. | Enemy's hex is within a friendly long-range sensor's ring coverage (`0 .. long_range_hexes`, i.e. including the sensor's own hex), and the enemy is *not* already DETAILED. |
| **HIDDEN** | Not rendered at all; cannot be interacted with. | Neither of the above. |

Additional always-true rules:

- **Celestial bodies** (stars, planets, moons, asteroids, fields, nebulae,
  storms, comets, wormholes) are **always visible**, including enemy-owned
  planets and their owner highlight rings.
- **Friendly units** (owned by the viewer) are **always visible**.

Key consequence (confirmed with stakeholder): an enemy in the **same hex** as a
friendly long-range unit but **outside** short-range radius shows as
**PRESENCE**. If it then enters any friendly short-range radius, it upgrades to
**DETAILED**. With only short-range sensors and the enemy beyond radius, it is
**HIDDEN**.

Granularity:
- **DETAILED** is computed **per enemy unit** (distance test).
- **PRESENCE** is computed **per hex** (a hex is "presence-covered" and contains
  at least one enemy that is not individually DETAILED).

---

## 3. `Sensors` Component Design

New component class `Sensors(UnitComponent)` in `unit_components/sensors.py`.

### Fields
- `short_range_radius: float` — logical detection radius inside the same sector.
  (Sector logical radius is `SECTOR_CIRCLE_RADIUS_LOGICAL = 5000`.)
- `long_range_hexes: int` — ring count for presence detection. `0` = no
  long-range capability; `1` = immediate neighbour ring (default upgrade). Ring
  coverage always includes ring 0 (the unit's own hex).

### Convenience properties
- `has_short_range -> bool` : `short_range_radius > 0`.
- `has_long_range -> bool`  : `long_range_hexes > 0`.

### Class attributes (following existing component conventions)
- `DISPLAY_NAME = "Sensors"`
- `SIDEBAR_ORDER = 6` (after Constructor=5; adjust if collisions).

### `get_sidebar_data(game_state)`
Extends base to show:
- `Short Range: <radius>` (or "None" when 0).
- `Long Range: <n> hex(es)` (or "None" when 0).

### Defaults / baseline
Every `Unit` receives a **default baseline `Sensors`** in `Unit.__init__`
(mirroring the existing auto-added `Commander` and `AntimatterStorage`):
- `short_range_radius = DEFAULT_SENSOR_SHORT_RANGE`
- `long_range_hexes = 0`
- `hull_cost = 0` (baseline consumes no hull, so existing hull math and tests are
  unaffected).

Rationale: a unit must at least perceive nearby enemies in its own sector to
fight coherently (turrets fire at same-hex targets). Long-range is an explicit
upgrade via templates or the unit editor. (If a "no baseline sensing" variant is
ever desired, the default can be removed — but this plan implements the
baseline.)

### Hull-cost formula (dynamic, used by the editor & custom templates)
```
sensors_hull_cost = ceil(short_range_radius / SENSOR_RANGE_PER_HULL_POINT)
                    + long_range_hexes * SENSOR_LONG_RANGE_HULL_COST_PER_HEX
```
Baseline (auto-added) sensors always use `hull_cost = 0` regardless of the
formula; the formula applies to editor/template-defined upgraded sensors.

---

## 4. New Constants (`constants.py`)

```python
# --- Sensors / Fog of War ---
DEFAULT_SENSOR_SHORT_RANGE: float = 2000.0     # logical units (sector radius = 5000)
SENSOR_RANGE_PER_HULL_POINT: float = 1000.0    # hull points per unit of short-range radius
SENSOR_LONG_RANGE_HULL_COST_PER_HEX: int = 5   # hull points per long-range ring
DEFAULT_SENSOR_LONG_RANGE_HEXES: int = 1       # default ring count for a long-range upgrade

# Fog visuals
FOG_PRESENCE_COLOR = (200, 60, 60)             # generic enemy-presence marker color
FOG_TINT_COLOR = (0, 0, 0, 60)                 # optional faint shading for non-detailed hexes (system view)
```

---

## 5. Hex Neighbour / Ring Helper (`hexgrid_utils.py`)

Add utilities for axial neighbour and ring lookups:

```python
HEX_DIRECTIONS = [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]

def hex_neighbors(coord):
    """Return the 6 axial neighbours of a hex coordinate."""
    q, r = coord
    return [(q + dq, r + dr) for dq, dr in HEX_DIRECTIONS]

def hexes_within_range(coord, n):
    """Return all hex coords within `n` rings of `coord`, INCLUDING `coord`
    itself (ring 0). n <= 0 returns just [coord]."""
    q0, r0 = coord
    if n <= 0:
        return [coord]
    results = []
    for dq in range(-n, n + 1):
        for dr in range(max(-n, -dq - n), min(n, -dq + n) + 1):
            results.append((q0 + dq, r0 + dr))
    return results
```
(`hex_distance` already exists in `geometry.py`; the ring helper avoids repeated
distance calls.)

---

## 6. Visibility Service (`visibility.py` — new module)

A small, stateless-per-call service that computes the visibility snapshot for a
given viewer.

### Data structures produced
```python
class VisibilitySnapshot:
    viewer: Player
    visible_enemy_unit_ids: set[int]          # DETAILED enemy unit ids
    presence_hexes: set[tuple[str, HexCoord]] # (system_name, hex) with undetailed enemies detected
```

### Algorithm (`compute(galaxy, viewer) -> VisibilitySnapshot`)
1. **Gather friendly sensor coverage** in a single pass over all units:
   - `short_by_hex: dict[(sys, hex)] -> list[(position, radius)]` for friendly
     units with `has_short_range`.
   - `long_range_covered: set[(sys, hex)]` — for each friendly unit with
     `has_long_range`, add every hex in `hexes_within_range(unit.in_hex,
     long_range_hexes)` (constrained to hexes that exist in that system) as
     `(sys, hex)`.
2. **Resolve enemy units** in a second pass:
   - For each enemy unit `E` (owner != viewer):
     - **DETAILED** if any `(pos, radius)` in `short_by_hex[(E.in_system,
       E.in_hex)]` satisfies `distance(pos, E.position) <= radius` →
       add `E.id` to `visible_enemy_unit_ids`.
     - Else if `(E.in_system, E.in_hex) in long_range_covered` → add
       `(E.in_system, E.in_hex)` to `presence_hexes` (PRESENCE).
     - Else HIDDEN (recorded implicitly by absence).

Complexity is O(units) with small per-hex lists — trivial for prototype scale
(dozens of units). Galaxy-wide computation is fine and keeps all views correct.

### Public helpers
```python
def is_unit_visible(snapshot, unit) -> bool:
    """Friendly units always True; enemy units True only if DETAILED."""

def hex_has_presence(snapshot, system_name, hex_coord) -> bool:
    """True if that hex should show a generic enemy-presence marker."""
```

---

## 7. `game.py` Integration

- Import the visibility service and store a snapshot on the `Game` instance:
  `self.visibility: Optional[VisibilitySnapshot] = None`.
- Add `Game.recompute_visibility()` that sets `self.visibility =
  VisibilityService.compute(self.galaxy, self.players[self.current_player_index])`.
- Call `recompute_visibility()`:
  - In `update()` each frame **guarded by a dirty flag** `self.visibility_dirty`
    (recompute only when dirty), and
  - Set `self.visibility_dirty = True` at: end of turn (`end_turn`), turn start
    (`update_player_turn_display` / after `current_player_index` change), and any
    time it's cheap/safe to over-invalidate. For robustness in the prototype,
    recomputing every frame is acceptable; the dirty-flag is an optimization.
- Add thin convenience methods on `Game`:
  - `is_unit_visible(unit)` → delegates to the snapshot (viewer = current player).
  - `hex_has_presence(system_name, hex_coord)` → delegates to the snapshot.
- **Sidebar filtering** in `update_side_bar_content()` (the Hex-selection branch
  that lists `hex_obj.units`): skip enemy units that are not DETAILED. Optionally
  append a single "Enemy presence detected" line when the hex has presence but no
  detailed enemy units.

---

## 8. Rendering Integration

### 8.1 System View (`rendering/system_renderer.py`)
In the per-hex unit-drawing block ("Draw units"):
- Split each hex's `unit_list` into:
  - **friendly units** (always drawn),
  - **detailed enemy units** (drawn normally — `game.is_unit_visible(unit)`),
  - **hidden enemy units** (not drawn).
- If the hex has enemies that are hidden **and**
  `game.hex_has_presence(system, hex)` is True, draw a **single generic presence
  marker** on the hex — e.g., a `FOG_PRESENCE_COLOR` diamond / "?" glyph centered
  in the hex — instead of the real enemy icons. This never encodes counts or
  positions.
- (Optional) Apply a faint `FOG_TINT_COLOR` polygon over hexes with no friendly
  detailed coverage. Celestial bodies remain drawn (drawn before/independent of
  the tint), satisfying "celestial objects always visible."
- Selection/hover highlight logic for units must also respect visibility (only
  applies to friendly or DETAILED enemies, which is naturally handled because
  hidden enemies won't be in `selected_objects` — see input changes).

### 8.2 Sector View (`rendering/sector_renderer.py`)
The sector view renders the single hex `current_sector_coord`:
- When iterating `units_to_draw`, **skip enemy units** for which
  `game.is_unit_visible(unit)` is False (do not draw icon, name, health bar, dots,
  or order lines).
- If the viewed hex has hidden enemies **and**
  `game.hex_has_presence(current_system, current_sector_coord)` is True, draw a
  **non-positional HUD indicator** — e.g., a fixed-position label/icon such as
  "⚠ Enemy presence detected" near the top of the sector viewport (using the
  existing font cache). This deliberately avoids drawing anything at the enemies'
  true coordinates so positions are not leaked.
- Celestial bodies are always drawn (unchanged).
- Friendly move/attack order lines are unaffected.

### 8.3 Galaxy View (`rendering/galaxy_renderer.py`)
No change required: the galaxy view does not render enemy unit icons (only
systems, wormholes, and the current player's own order lines). Systems remain
fully visible.

---

## 9. Input / Selection Integration (`input_processor.py`)

Hidden enemy units must be non-interactive to prevent information leaks:

- **`update_hover_states()` (sector branch):** when building the hover candidate
  list, skip enemy units that are not DETAILED (`game.is_unit_visible`). Celestial
  bodies and friendly/DETAILED units remain hoverable.
- **Box selection (`MOUSEBUTTONUP`):** exclude non-visible enemy units from
  `selected_units_in_box` (box-select already only targets units in the current
  hex; add a visibility check).
- **Left-click selection:** since hover already excludes hidden enemies,
  `clicked_object` will not be a hidden enemy. No extra work beyond the hover
  fix, but add a defensive `is_unit_visible` guard where a `Unit` is selected.
- **Right-click context menu:** because `clicked_object` comes from hover, hidden
  enemies won't produce attack/target options. No additional change needed beyond
  the hover fix; add a defensive guard so attack options never reference hidden
  enemies.

---

## 10. Constructor / Template Wiring (`unit_components/constructor.py`)

In `create_unit_from_template()`, add handling for the sensors flags (placed near
the other component blocks). Support the new canonical flags **and** map the
existing unused legacy `has_scanner` placeholder to sensors for backward
compatibility:

```python
# Sensors: prefer explicit new flags; fall back to legacy has_scanner.
has_sensors = template.get("has_sensors", template.get("has_scanner", False))
if has_sensors:
    short_range = template.get("sensor_short_range", DEFAULT_SENSOR_SHORT_RANGE)
    long_range_hexes = template.get("sensor_long_range_hexes", 0)
    # legacy scanner implies at least short-range; grant long-range if requested
    hull_cost = template.get(
        "sensors_hull_cost",
        template.get("scanner_hull_cost", 0),
    )
    # Replace the default baseline Sensors with the template-specified one:
    new_unit.remove_component(Sensors)
    new_unit.add_component(Sensors(
        new_unit,
        short_range_radius=short_range,
        long_range_hexes=long_range_hexes,
        hull_cost=hull_cost,
    ))
```

Notes:
- `Sensors` must be imported at the top of `constructor.py`.
- Because `Unit.__init__` already adds a baseline `Sensors`, template units simply
  **replace** it when they specify richer sensors (or keep the baseline if the
  template does not).

---

## 11. Custom Unit Templates (`custom_unit_templates.py`)

- Add a dynamic-cost helper:
  ```python
  def calc_sensors_hull_cost(short_range_radius, long_range_hexes):
      base = math.ceil(short_range_radius / SENSOR_RANGE_PER_HULL_POINT) if short_range_radius > 0 else 0
      return base + max(0, long_range_hexes) * SENSOR_LONG_RANGE_HULL_COST_PER_HEX
  ```
- Extend `ComponentConfig`:
  - `has_sensors: bool = False`
  - `sensor_short_range: float = DEFAULT_SENSOR_SHORT_RANGE`
  - `sensor_long_range_hexes: int = 0`
  - `@property sensors_hull_cost` → uses `calc_sensors_hull_cost` when enabled,
    else 0.
- Include `sensors_hull_cost` in `CustomUnitTemplate.total_hull_cost`.
- Add sensors to `_template_to_dict` / `_dict_to_template` round-tripping
  (`has_sensors`, `sensor_short_range`, `sensor_long_range_hexes`,
  `sensors_hull_cost`).
- Add sensors to the `any_component` list in `validate()` so a sensors-only
  design is considered meaningful. No hull-size restriction (sensors allowed on
  all hulls, including strikecraft).

---

## 12. Unit Editor GUI (`unit_editor_gui.py`)

- Add a component row to `COMPONENT_ROWS`:
  ```python
  {"key": "has_sensors", "label": "Sensors", "cost_key": "sensors_hull_cost",
   "default_cost": 2, "is_dynamic": True},
  ```
- Add editor sub-controls in the Component Details column (Column 4):
  - A text entry for **short-range radius** (writes `sensor_short_range`).
  - A text entry (or small dropdown 0/1/2) for **long-range rings**
    (writes `sensor_long_range_hexes`).
- Wire the `UI_TEXT_ENTRY_CHANGED` / dropdown handlers to read these into
  `self._comp`, call `_sync_dynamic_costs()` and `_update_summary()`.
- Add `has_sensors` to `_sync_dynamic_costs()`'s dynamic-values dict so the cost
  label live-updates.

---

## 13. Data Templates (`data/unit_templates.json`)

- Convert the existing unused `has_scanner` / `scanner_hull_cost` entries into the
  new canonical fields. Suggested mapping:
  - Units currently marked `"has_scanner": true` (CONSTRUCTOR_MK1,
    SHIPYARD_MK1, REPAIR_STATION_SMALL, STATION_MK1) → give them a real sensors
    upgrade, e.g.:
    ```json
    "has_sensors": true,
    "sensor_short_range": 3000.0,
    "sensor_long_range_hexes": 1,
    "sensors_hull_cost": 8
    ```
    (Stations/shipyards act as long-range sensor pickets.)
  - Units with `"has_scanner": false` keep only the default baseline sensors
    (no `has_sensors` key needed).
- The legacy `has_scanner` keys can be left in place (ignored) or removed; the
  constructor fallback handles both. Recommended: replace them to keep data clean.

---

## 14. Tests (`tests/test_sensors_fog_of_war.py` — new)

Add unit tests (pytest, consistent with existing tests) covering:

1. **Baseline sensors exist:** a freshly created `Unit` has a `Sensors` component
   with `short_range_radius == DEFAULT_SENSOR_SHORT_RANGE` and
   `long_range_hexes == 0`, `hull_cost == 0`.
2. **Short-range detail within radius:** enemy in the same hex within a friendly
   unit's `short_range_radius` → `visible_enemy_unit_ids` contains it;
   `is_unit_visible` True.
3. **Short-range miss (same hex, beyond radius, no long-range):** enemy in same
   hex but outside radius → HIDDEN (not visible, not presence).
4. **Long-range same-hex presence:** friendly long-range unit + enemy in the same
   hex beyond short radius → hex in `presence_hexes`, enemy id NOT in
   `visible_enemy_unit_ids`.
5. **Long-range neighbour presence:** enemy in a neighbour hex of a friendly
   long-range unit → that neighbour hex in `presence_hexes`; enemy not DETAILED.
6. **Detail overrides presence:** enemy in short radius is DETAILED even if also
   long-range-covered (not double-counted as presence).
7. **Friendly always visible:** friendly unit always `is_unit_visible` True
   regardless of sensors.
8. **Celestial always visible / hit-test exclusion:** hidden enemy is excluded
   from sector hover candidates (or a direct visibility check), while a celestial
   body in the same hex remains selectable.
9. **Template wiring:** a template with `has_sensors`/legacy `has_scanner` builds
   a unit whose `Sensors` reflects the specified ranges (replacing the baseline).

---

## 15. Edge Cases & Non-Goals

Handled:
- Presence markers appear only when a hex actually contains ≥1 enemy that is not
  DETAILED (no false "presence" on empty neighbour hexes).
- Hidden enemies cannot be hovered, selected, box-selected, attacked, or listed
  in the sidebar.
- Baseline sensors have `hull_cost = 0`, so existing hull-capacity tests and
  spawned starter units are unaffected.
- Galaxy view unaffected (no enemy icons there).
- Sensor ring coverage is clamped to hexes that actually exist in the system.

Out of scope (possible follow-ups, not implemented here):
- Sensor jamming/interference from `AsteroidField` / `Nebula` (the asteroid-field
  sidebar text already hints at this; could reduce effective ranges later).
- Persistent "explored/last-seen" memory of enemy positions (current model is
  live line-of-sight only).
- Alliance/shared-vision between players.
- AI use of sensor information (AI turns are currently auto-passed).

---

## 16. Files Touched Summary

| File | Change |
|------|--------|
| `constants.py` | New sensor/fog constants. |
| `unit_components/sensors.py` | **New** `Sensors` component. |
| `unit_components/__init__.py` | Export `Sensors`. |
| `entities.py` | Import `Sensors`, auto-add baseline in `Unit.__init__`, add `sensors_component` property. |
| `hexgrid_utils.py` | `hex_neighbors`, `hexes_within_range`, `HEX_DIRECTIONS`. |
| `visibility.py` | **New** `VisibilityService` / `VisibilitySnapshot` + helpers. |
| `game.py` | Store/refresh visibility snapshot; `is_unit_visible` / `hex_has_presence`; sidebar filtering. |
| `rendering/system_renderer.py` | Hide/replace enemy icons per hex; presence marker; optional fog tint. |
| `rendering/sector_renderer.py` | Skip hidden enemies; non-positional presence HUD. |
| `input_processor.py` | Exclude hidden enemies from hover/selection/context. |
| `unit_components/constructor.py` | Build `Sensors` from template (+ legacy `has_scanner`). |
| `custom_unit_templates.py` | Sensors config, dynamic cost, validation, round-trip. |
| `unit_editor_gui.py` | Sensors row + range/ring controls + live cost. |
| `data/unit_templates.json` | Convert `has_scanner` → sensors fields. |
| `tests/test_sensors_fog_of_war.py` | **New** test coverage. |

---

## 17. Implementation Checklist

- [ ] Add sensor constants to `constants.py`.
- [ ] Create `Sensors` component (`unit_components/sensors.py`) + export.
- [ ] Add default baseline `Sensors` + `sensors_component` property to `Unit`.
- [ ] Add `hex_neighbors` / `hexes_within_range` to `hexgrid_utils.py`.
- [ ] Implement `VisibilityService` (`visibility.py`): per-enemy detail + per-hex
      presence (incl. ring 0).
- [ ] Hook visibility computation + sidebar enemy filtering into `game.py`.
- [ ] Apply fog of war in `system_renderer` (enemy icons / presence marker).
- [ ] Apply fog of war in `sector_renderer` (enemy detail / non-positional
      presence HUD).
- [ ] Exclude hidden enemies from hover/selection/context in `input_processor`.
- [ ] Wire `Sensors` into `constructor.create_unit_from_template` (+ legacy
      `has_scanner`).
- [ ] Add `Sensors` to `custom_unit_templates.py` (dynamic cost, validation).
- [ ] Add `Sensors` row + options to `unit_editor_gui.py`.
- [ ] Update `data/unit_templates.json` sensor flags.
- [ ] Add tests (`tests/test_sensors_fog_of_war.py`).
