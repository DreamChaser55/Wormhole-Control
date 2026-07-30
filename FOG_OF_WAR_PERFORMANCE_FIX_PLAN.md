# Sector-View Fog of War — Performance Diagnosis & Fix Plan

**Status:** Plan (ready for implementation)
**Scope:** `rendering/sector_renderer.py` (`_draw_fog_of_war`, `_fill_circle_clipped`, helpers), `tests/test_sector_fog_of_war.py`, `tests/test_sector_range_circles.py`
**Reported symptom:** Poor performance of fog of war in sector view, particularly when zoomed in.

---

## 1. Executive Summary

Fog of war in the sector view is rebuilt from scratch **every single frame** using
**Python-level scanline loops** that issue one `pygame.draw.line` call per screen row —
once for the sector boundary disc, then once more per friendly unit sensor cut-out.

At 1920×1080 with the default starting fleet (11 friendly units in the homeworld hex),
this is roughly **12,000 Python-level draw calls per frame**, measured at **~97 ms/frame**
(~10 FPS) on this machine. The exact same rasterization done with clipped
`pygame.draw.circle` (C level) costs **~3.2 ms**, and with caching + early-outs the
typical frame cost drops to **~0–0.9 ms**.

The scanline approach was introduced deliberately, based on a premise that is **false for
pygame-ce 2.5.7**: that `pygame.draw.circle` cost scales with `radius_px` even when clipped.
Measurements below disprove this.

**Target outcome:** sector view holds 60 FPS at all zoom levels with fog enabled.

---

## 2. Where the Problem Lives

| Location | Issue |
|---|---|
| `rendering/sector_renderer.py:809-903` `_draw_fog_of_war` | Full per-frame rebuild via Python scanline loops (`pygame.draw.line` per row) for the disc **and** for every sensor cut-out. No caching, no early-outs, no overdraw culling, unbounded full-screen clear/blit. |
| `rendering/sector_renderer.py:260-320` `_fill_circle_clipped` | Same Python scanline pathology (used by `_blit_uncached_circle` → storms / inhibitor fallbacks). |
| `rendering/sector_renderer.py:242-258` `_circle_covers_viewport` | Only tests the *whole screen*; cannot be reused to test coverage of an arbitrary sub-rect (needed for the early-outs). |
| `rendering/sector_renderer.py:433-436` (call site) | `_draw_fog_of_war` is invoked unconditionally once per sector-view frame. |
| `rendering/sector_renderer.py:394-401` (cache reset) | `_fog_of_war_surface` is reset on sector change; new cache state must be invalidated in the same place. |

Relevant constants (`constants.py`):

```
SECTOR_CIRCLE_RADIUS_IN_PX   = SCREEN_RES.y // 2      # 540 at 1080p
SECTOR_CIRCLE_RADIUS_LOGICAL = 5000.0
SECTOR_ZOOM_MIN / MAX        = 0.8 / 15.0
DEFAULT_SENSOR_SHORT_RANGE   = 2000.0                 # logical units
FOG_OF_WAR_COLOR             = (40, 40, 50, 55)
```

---

## 3. Root Cause Analysis

### 3.1 The per-row Python loop is the bottleneck

`_draw_fog_of_war` paints the disc and then punches each sensor cut-out with:

```python
for y in range(vis_top, vis_bottom):
    ...
    pygame.draw.line(fog_surf, COLOR, (x_left, y), (x_right - 1, y))
```

Measured on this machine (**pygame-ce 2.5.7, SDL 2.32.10, Python 3.14.3**, 1920×1080 SRCALPHA):

| Operation (per frame) | Cost |
|---|---|
| 11 viewport-clipped circles via the **current Python scanline loop** | **97.06 ms** |
| 11 viewport-clipped circles via `pygame.draw.circle` (C, clipped) | **3.22 ms** |
| Full-screen SRCALPHA `fill((0,0,0,0))` | 0.18 ms |
| Full-screen per-pixel-alpha `blit` | 0.83 ms |
| Proposed full rebuild (clear + disc + 11 large cut-outs + blit) | 5.06 ms |
| Cached path (blit only) | 0.94 ms |

→ The Python row loop is a **~30× penalty** over the equivalent C-level call.

### 3.2 Why zooming in makes it collapse

* At zoom 1.0, a default sensor circle is `2000 × 540 / 5000 ≈ 216 px` → ~430 rows per unit.
* At max zoom (15.0), `dynamic_radius = 8100 px` → sensor radius `≈ 3240 px`, larger than the
  viewport. Each cut-out's clipped region now spans the **entire screen height (1080 rows)**
  and each row spans nearly the full width → both the Python call count *and* the pixel
  overdraw hit their maximum simultaneously.
* The starting homeworld hex spawns **11 units per player** (`game.spawn_units`), so
  `11 × 1080 ≈ 12,000` `pygame.draw.line` calls per frame is the **default** state, not a
  pathological one.
* The sector disc itself takes the `_circle_covers_viewport` → flat-fill fast path once zoomed
  in, which is why zoomed-out is "only" slow (~9 ms for the disc loop) while zoomed-in is
  catastrophic: what remains is entirely the per-unit cut-out loops.

### 3.3 The premise behind the scanline code is false on pygame-ce 2.5.7

The in-code justification reads:

> *"Manual scanline fill, bounded to the visible rows only … unlike `pygame.draw.circle`
> (even with a surface clip rect set), whose scanline loop iterates the full `2*radius_px`
> rows even when almost all of them fall outside the clip."*

Measured filled `pygame.draw.circle` cost on a 1920×1080 SRCALPHA surface:

| Radius | Cost | Notes |
|---|---|---|
| 540 | 0.192 ms | |
| 3 240 | 0.542 ms | typical max-zoom sensor radius |
| 20 000 | 0.484 ms | |
| 100 000 | 0.901 ms | absurd radius, still sub-ms |
| 3 240 with a 100×100 surface clip | **0.018 ms** | clip is honoured and cost collapses |

Cost is effectively **radius-independent and clip-bounded**. Additionally verified:

```python
s.fill((40, 40, 50, 55))
pygame.draw.circle(s, (0, 0, 0, 0), (960, 540), 200)
s.get_at((960, 540))  # -> Color(0, 0, 0, 0)   (hole punched)
s.get_at((10, 10))    # -> Color(40, 40, 50, 55) (fog intact)
```

`pygame.draw.*` uses **replace** (not blend) semantics, so drawing `(0,0,0,0)` punches holes
in the fog exactly like the current loop does — the visual result is preserved.

### 3.4 Secondary problems (all in `_draw_fog_of_war`)

1. **No caching.** The game is turn-based: unit positions and sensor state only change during
   turn processing, and the camera is static on the vast majority of frames. Yet the fog is
   fully re-rasterized every frame.
2. **No "fully revealed" early-out.** Zooming onto your own ship normally means one sensor
   circle covers the whole viewport, i.e. the correct output is *no fog at all* — but the code
   still fills the disc, punches N cut-outs and blits a full-screen alpha surface.
3. **Redundant overdraw.** The 11 spawn units sit ~200 logical units apart with identical
   sensor radii, so their circles overlap almost entirely; each one repaints most of the
   screen. This is why even the C-level version still measures ~5 ms with 11 large cut-outs.
4. **Work not bounded to the fog's actual area.** `fog_surf.fill((0,0,0,0))` and
   `screen.blit(fog_surf, (0, 0))` always cover the whole screen (~1.0 ms combined) even when
   the disc occupies a small part of it.

### 3.5 Out of scope (noted for completeness)

* Fog is blitted at step **1b** of `draw_sector_view`, *before* celestial bodies and units are
  drawn, so foreground objects are never dimmed by fog. That is a **visual design** question,
  not a performance one — no change proposed here.
* `_draw_fog_of_war` only considers units in the currently viewed hex, while
  `VisibilityService` works galaxy-wide. Consistent with current design; unchanged.
* `_draw_range_ring` outline circles were measured at 0.039 ms (r=3240) / 0.452 ms (r=40000)
  and are **not** a contributing factor.

---

## 4. Fix Plan

### Stage 1 — Replace scanline rasterization with clipped, C-level circle drawing

**1a. Generalize the coverage test.**

```python
def _circle_covers_rect(self, center_px, radius_px, rect) -> bool:
    """True if every corner of `rect` lies inside the disc (a disc is convex,
    so all four corners inside => the whole rect is interior)."""

def _circle_covers_viewport(self, center_px, radius_px) -> bool:
    """Kept as a thin wrapper over _circle_covers_rect for existing callers/tests."""
    return self._circle_covers_rect(center_px, radius_px, self.screen.get_rect())
```

**1b. Add one shared rasterization primitive.**

```python
MAX_SAFE_CIRCLE_RADIUS_PX = 250_000  # defensive clamp against absurd derived radii

def _fill_circle_on_surface(self, surface, center_px, radius_px, rgba, clip_rect) -> bool:
    """Rasterize a filled circle onto `surface` with *replace* semantics,
    bounded to `clip_rect`. Returns True if anything was painted.

    - cull:      circle bbox ∩ clip_rect empty            -> return False
    - fast path: circle covers clip_rect entirely          -> surface.fill(rgba, clip_rect)
    - normal:    set_clip(clip_rect) + pygame.draw.circle  -> restore previous clip
    """
```

Notes:
* Save/restore the previous clip (`old = surface.get_clip()` … `surface.set_clip(old)`) so the
  helper is safe to call from any context.
* Clamp `radius_px` to `MAX_SAFE_CIRCLE_RADIUS_PX` (still guaranteed to cover the viewport at
  that size) to keep the C loop bounded for pathological sensor/zoom combinations.

**1c. Rewrite `_draw_fog_of_war` to use `_fill_circle_on_surface`** for both the disc fill
(`FOG_OF_WAR_COLOR`) and each cut-out (`(0, 0, 0, 0)`). All `for y in range(...)` /
`pygame.draw.line` loops in this function are deleted.

### Stage 2 — Early-outs and cut-out culling

New structure of `_draw_fog_of_war`:

1. **Compute `fog_rect`** = `screen_rect ∩ disc_bbox`. If empty → clear cache state, return.
   (Fog only ever exists inside the disc, so `fog_rect` bounds *all* fog work: clear, fill,
   cut-outs and blit.)
2. **Collect eligible cut-outs** once, into a small list of `(center_px, radius_px)`:
   friendly owner, `sensors_component` present, `not is_destroyed`, `has_short_range`,
   `radius_px > 0`, bbox intersects `fog_rect`.
3. **Fully-revealed short-circuit:** if any single cut-out satisfies
   `_circle_covers_rect(center, radius, fog_rect)` → the whole visible fog area is revealed.
   Clear the surface region, mark the cached state as "fully revealed", and **skip the disc
   rasterization and the blit entirely**. This is the common zoomed-in case → ~0 ms.
4. **Containment culling:** sort cut-outs by descending radius; skip any circle `B` contained
   in an already-drawn circle `A` (`dist(A, B) + r_B <= r_A`). O(n²) with tiny n, removes
   redundant overdraw for stacked/clustered fleets.
5. Rasterize disc, then remaining cut-outs, all clipped to `fog_rect`.
6. `screen.blit(fog_surf, fog_rect.topleft, area=fog_rect)`.

### Stage 3 — Frame-to-frame caching (the win for static frames)

The fog image is a pure function of camera + friendly-sensor state, both of which are static
on most frames (turn-based game, camera only moves on input).

```python
# new instance state (initialize in __init__, reset alongside _fog_of_war_surface)
self._fog_cache_key = None      # tuple signature of everything the fog depends on
self._fog_blit_rect = None      # rect to blit on a cache hit; None => nothing to blit
```

**Cache key** (cheap to build: a handful of attribute reads per friendly unit):

```python
key = (
    screen_size,                                  # (w, h)
    self._last_cached_sector,                     # (system_name, hex_coord)
    round(dynamic_radius, 1),                     # zoom
    round(pan.x, 1), round(pan.y, 1),             # pan
    id(current_player),
    tuple((round(cx, 1), round(cy, 1), r) for cx, cy, r in cutouts),
)
```

* **Cache hit** (`key == self._fog_cache_key`): skip *all* rasterization; if
  `self._fog_blit_rect` is not `None`, blit that rect only (~0.3–0.9 ms); otherwise (the
  fully-revealed case) do nothing at all.
* **Cache miss:** clear `fog_rect ∪ previous_fog_rect` (so stale pixels from a larger previous
  rect can't linger), rebuild per Stage 2, then store the new key and blit rect.
* **Invalidation:** in `draw_sector_view`'s sector-change block (where `_fog_of_war_surface`
  is already set to `None`) also reset `_fog_cache_key` / `_fog_blit_rect`; the screen-size
  check in the allocation path must reset the key too.
* Compare keys with `==` (not dict hashing) so `MagicMock` players/units used in tests behave
  predictably.

### Stage 4 — Instrumentation

Extend `zoom_render_stats` (and `_update_zoom_render_stats`) with:

```
'fog_rebuilds'      # frames where the fog was rasterized
'fog_cache_hits'    # frames served straight from the cached surface
'fog_full_reveal'   # frames skipped entirely (viewport fully inside a sensor circle)
```

This makes any future regression measurable rather than anecdotal, matching the existing
`direct_draw_fallbacks` / `range_circle_fills` counters.

### Stage 5 — Fix the same pathology in `_fill_circle_clipped` (recommended)

`_fill_circle_clipped` (→ `_blit_uncached_circle`, used by storms and the inhibitor fallback)
contains the identical Python row loop. Replace its partial-coverage branch with
`_fill_circle_on_surface(self._range_circle_surface, ..., clip_rect=rect)`.

Semantics are preserved: the scratch surface is painted with *replace* semantics and then
alpha-**blitted** onto the overlay, so overlapping fills still accumulate alpha (source-over),
which is what `test_blit_uncached_circle_blends_instead_of_replacing` and
`test_fill_circle_clipped_blends_instead_of_replacing` assert.

**Test change required:** `tests/test_sector_range_circles.py::test_fill_circle_clipped_partial_coverage_uses_scanline_fill`
currently *asserts the slow path* (`pygame.draw.line` call count > 0). It must be rewritten to
assert the pixel result plus clipped-`draw.circle` usage, and renamed accordingly
(e.g. `test_fill_circle_clipped_partial_coverage_uses_clipped_circle`).

Also update the now-inaccurate docstrings/comments in `_fill_circle_clipped`,
`_blit_uncached_circle` and `_draw_fog_of_war` that claim `pygame.draw.circle` is
radius-bound even when clipped.

### Stage 6 — Optional: half-resolution fog mask (only if more headroom is needed)

Add `FOG_RENDER_DOWNSCALE = 2` (constants) and rasterize the fog mask into a
`(w//2, h//2)` surface, upscaling on blit. Cuts remaining pixel work ~4× on rebuild frames
(≈5 ms → ≈1.5 ms in the 11-large-cut-out worst case) and — with `smoothscale` — yields a
*softer* fog boundary. Trade-off: a slightly blurrier / 2-px-stepped fog edge.

**Recommendation:** defer. Stages 1–3 already remove the bottleneck; revisit only if
profiling on a very large fleet still shows rebuild frames dominating.

---

## 5. Expected Performance

| Frame type (1080p, 11 friendly units, max zoom) | Before | After |
|---|---|---|
| Static camera (typical) | ~97 ms | **~0.3–0.9 ms** (cached blit) |
| Zoomed in onto own ship (viewport inside sensor range) | ~97 ms | **~0 ms** (fully-revealed skip) |
| Camera actively zooming/panning (cache miss) | ~97 ms | **~1–5 ms** (Stage 2 culling reduces this further) |
| Zoomed out (disc smaller than viewport) | ~9 ms + cut-outs | **< 1 ms** |

---

## 6. Test Plan

### 6.1 Must keep passing (existing, `tests/test_sector_fog_of_war.py`)

* `test_surface_created`, `test_surface_reused` (surface identity is reused across frames)
* `test_no_units_fog_covers_centre`
* `test_large_sensor_clears_centre` — note the test geometry (r=290 px disc centred in an
  800×600 canvas) means the sensor circle does **not** cover `fog_rect`, so the
  fully-revealed short-circuit is not taken and the centre pixel is still inspectable.
* `test_destroyed_sensor_no_cutout`, `test_enemy_no_cutout`, `test_surface_reset_on_sector_change`

**Helper update:** `_make_renderer` builds the renderer via `__new__` and sets a fixed
attribute list, so it must be extended with `_fog_cache_key = None` and
`_fog_blit_rect = None` (and any new `zoom_render_stats` keys).

### 6.2 New regression tests

| Test | Assertion |
|---|---|
| `test_fog_never_uses_python_scanline_lines` | `pygame.draw.line` is patched and **never called** during `_draw_fog_of_war` (guards the 30× regression from coming back). |
| `test_fog_rebuild_uses_clipped_circle` | `pygame.draw.circle` is used for disc/cut-outs, and no allocation larger than the screen occurs at `SECTOR_ZOOM_MAX`. |
| `test_fog_cached_across_identical_frames` | Second identical call performs **zero** rasterization (`pygame.draw.circle` call count 0) but still blits; `fog_cache_hits` increments. |
| `test_fog_cache_invalidated_by_zoom_pan_and_unit_change` | Changing `dynamic_radius`, pan offset, or a unit's position/sensor radius triggers a rebuild. |
| `test_fog_skipped_when_sensor_covers_viewport` | With a viewport-covering sensor circle: no blit onto `screen`, fog surface fully transparent, `fog_full_reveal` increments. |
| `test_fog_cutout_contained_in_larger_is_skipped` | Two concentric cut-outs (one inside the other) result in a single circle rasterization. |
| `test_fog_offscreen_disc_is_culled` | Pan the disc fully off-screen → no rasterization and no blit. |
| `test_fog_blit_bounded_to_fog_rect` | The blit `area=` rect never exceeds `screen_rect ∩ disc_bbox`. |

### 6.3 Affected by Stage 5

* Rewrite `test_fill_circle_clipped_partial_coverage_uses_scanline_fill` (see Stage 5).
* Verify unchanged: `test_fill_circle_clipped_never_allocates_a_surface_larger_than_the_screen`,
  `..._reuses_persistent_surface_across_frames`, `..._covering_viewport_uses_rect_fill_not_scanline_loop`,
  `..._culls_when_offscreen`, `..._blends_instead_of_replacing`,
  `test_blit_uncached_circle_*`, all `_draw_range_ring` / `_draw_unit_range_circles` tests.

### 6.4 Full-suite gate

Run the whole suite (`pytest`) — `test_sector_render_cache.py`, `test_sector_camera.py`,
`test_sensors_fog_of_war.py`, `test_resolution_independence.py` and
`test_sector_tactical_grid.py` all touch adjacent code paths.

---

## 7. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| ±1 px differences in fog/cut-out edges (pygame's rasterizer vs the hand-rolled loop) | Visually equivalent for a 55-alpha overlay; tests assert alpha at representative pixels, not exact edge geometry. |
| Cache serving a stale image after a game-state change that isn't in the key | Key includes sector, screen size, zoom, pan, player, and every cut-out's position + radius — i.e. every input the renderer actually reads. Sector change already nukes the surface. |
| New instance attributes break tests that build the renderer via `__new__` | Only `tests/test_sector_fog_of_war.py` does this; its helper is updated in the same change. |
| Pathological radius from custom sensor designs at max zoom | `MAX_SAFE_CIRCLE_RADIUS_PX` clamp + the covers-rect fast path (measured 0.9 ms even at r=100 000). |
| Hidden reliance on `_circle_covers_viewport`'s exact signature | Kept as a wrapper delegating to `_circle_covers_rect`. |

---

## 8. Implementation Checklist

- [ ] **Stage 1** — `_circle_covers_rect` + `_circle_covers_viewport` wrapper; add
      `_fill_circle_on_surface`; rewrite `_draw_fog_of_war` rasterization (delete both row loops).
- [ ] **Stage 2** — `fog_rect` computation + cull, cut-out collection, fully-revealed
      short-circuit, containment culling, `fog_rect`-bounded clear/blit.
- [ ] **Stage 3** — `_fog_cache_key` / `_fog_blit_rect`, cache hit path, invalidation on
      sector change + screen-size change + camera/unit change.
- [ ] **Stage 4** — `fog_rebuilds` / `fog_cache_hits` / `fog_full_reveal` in `zoom_render_stats`
      and `_update_zoom_render_stats`.
- [ ] **Stage 5** — port `_fill_circle_clipped` to `_fill_circle_on_surface`; update its
      docstrings and the affected range-circle test.
- [ ] **Tests** — update `_make_renderer` helper; add the eight new regression tests from §6.2.
- [ ] **Verification** — run full `pytest`; sanity-check in game at zoom 1 and zoom 15 with a
      single unit and with the full 11-unit spawn fleet selected/deselected.
- [ ] **Stage 6 (deferred)** — half-resolution fog mask, only if profiling still demands it.

---

## 9. Appendix — Benchmark Reproduction

```powershell
$env:SDL_VIDEODRIVER='dummy'; py -3 -c "import pygame,math,time; pygame.init(); w,h=1920,1080; s=pygame.Surface((w,h),pygame.SRCALPHA); scr=pygame.Surface((w,h)); cx,cy,r=960,540,3240; f=lambda y:(max(0,int(cx-math.sqrt(max(0,r*r-(y-cy)**2)))), min(w,int(cx+math.sqrt(max(0,r*r-(y-cy)**2))))); t=time.perf_counter(); [[pygame.draw.line(s,(0,0,0,0),(f(y)[0],y),(f(y)[1]-1,y)) for y in range(h)] for k in range(110)]; d1=time.perf_counter()-t; t=time.perf_counter(); [pygame.draw.circle(s,(0,0,0,0),(cx,cy),r) for k in range(110)]; d2=time.perf_counter()-t; print('scanline 11/frame ms: %.2f' % (d1/10*1000)); print('draw.circle 11/frame ms: %.2f' % (d2/10*1000))"
```

Observed output (pygame-ce 2.5.7, SDL 2.32.10, Python 3.14.3, Windows 11):

```
scanline 11 circles/frame ms: 97.06
draw.circle 11 circles/frame ms: 3.22
full-screen SRCALPHA fill ms: 0.18
full-screen alpha blit ms: 0.83
r=540  ms/circle: 0.192
r=3240 ms/circle: 0.542
r=20000 ms/circle: 0.484
r=100000 ms/circle: 0.901
r=3240 with 100x100 clip ms: 0.018
proposed full fog rebuild (11 cutouts) ms: 5.057
cached-blit-only frame ms: 0.941
outline ring r=3240 w=2 ms: 0.039
outline ring r=40000 w=2 ms: 0.452
```
