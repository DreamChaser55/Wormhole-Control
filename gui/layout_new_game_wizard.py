"""New Game Wizard – UIWindow-based multi-section configuration panel.

The wizard collects:
  * Players   – count (2-6), per-player name / colour / human-vs-AI
  * Galaxy    – number of systems, system size, wormhole density,
                min/max system distance
  * Economy   – starting credits / metal / crystal / population

Color selection uses a colored swatch panel flanked by ◀/▶ cycle buttons
instead of a UIDropDownMenu (which does not support per-item text colors).

On "Start Game", dispatches {'action': 'start_new_game_with_settings', 'settings': GameSettings}.
On "Cancel", dispatches {'action': 'cancel_new_game_wizard'}.
"""
from __future__ import annotations

import logging
import typing

import pygame
import pygame_gui

from game_settings import (
    GameSettings,
    PlayerConfig,
    PLAYER_COLOR_PALETTE,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Layout constants (unscaled, in logical pixels at 1280×720 reference)
# ---------------------------------------------------------------------------
_WIN_W = 720
_WIN_H = 560

_PAD = 12          # standard internal padding
_ROW_H = 34        # height of a labelled slider / text row
_SECTION_H = 24    # section header height
_BTN_H = 36        # action button height
_BTN_W = 140       # action button width

_PLAYER_ROW_H = 38  # per-player row height
_COLOR_SWATCH_W = 36  # width of the colored swatch panel
_COLOR_CYCLE_BTN_W = 24  # width of the ◀/▶ cycle buttons

_MIN_PLAYERS = 2
_MAX_PLAYERS = 6



# ---------------------------------------------------------------------------
# Public helper
# ---------------------------------------------------------------------------

def build_default_color_name_for_index(idx: int) -> str:
    """Returns the colour-palette name for a given player index (wraps if needed)."""
    return PLAYER_COLOR_PALETTE[idx % len(PLAYER_COLOR_PALETTE)][0]


def _subtract_rect_from_blocker(rect: pygame.Rect, blocker: pygame.Rect) -> typing.List[pygame.Rect]:
    """Splits `rect` into non-overlapping sub-rectangles that lie outside `blocker`."""
    intersection = rect.clip(blocker)
    if intersection.width <= 0 or intersection.height <= 0:
        return [rect]
    result = []
    if rect.top < intersection.top:
        result.append(pygame.Rect(rect.left, rect.top, rect.width, intersection.top - rect.top))
    if rect.bottom > intersection.bottom:
        result.append(pygame.Rect(rect.left, intersection.bottom, rect.width, rect.bottom - intersection.bottom))
    if rect.left < intersection.left:
        result.append(pygame.Rect(rect.left, intersection.top, intersection.left - rect.left, intersection.height))
    if rect.right > intersection.right:
        result.append(pygame.Rect(intersection.right, intersection.top, rect.right - intersection.right, intersection.height))
    return result


# ---------------------------------------------------------------------------
# The wizard window class
# ---------------------------------------------------------------------------

class NewGameWizard:
    """Wraps a ``pygame_gui.elements.UIWindow`` wizard for new-game configuration.

    Args:
        manager: The active pygame_gui UIManager.
        screen_res: Screen resolution Vector (exposes .x and .y).
        scale_x: Horizontal scale factor (screen_width / 1280).
        scale_y: Vertical scale factor (screen_height / 720).
    """

    def __init__(
        self,
        manager: pygame_gui.UIManager,
        screen_res,
        scale_x: float,
        scale_y: float,
    ):
        self.manager = manager
        self.scale_x = scale_x
        self.scale_y = scale_y

        win_w = int(_WIN_W * scale_x)
        win_h = int(_WIN_H * scale_y)
        win_x = (int(screen_res.x) - win_w) // 2
        win_y = (int(screen_res.y) - win_h) // 2

        self.window = pygame_gui.elements.UIWindow(
            rect=pygame.Rect(win_x, win_y, win_w, win_h),
            manager=manager,
            window_display_title="New Game",
            object_id="#new_game_wizard_window",
            resizable=False,
        )

        # Use the actual inner container dimensions (excludes title bar).
        # This avoids buttons being clipped by the window title bar height.
        inner = self.window.get_container().get_size()
        self._content_w = inner[0]
        self._content_h = inner[1]

        # Start with 3 players using the default palette
        self._num_players: int = 3
        self._player_name_entries: typing.List[pygame_gui.elements.UITextEntryLine] = []
        # Color picker state: palette index + two cycle buttons + swatch panel
        self._player_color_indices: typing.List[int] = []
        self._player_color_prev_btns: typing.List[pygame_gui.elements.UIButton] = []
        self._player_color_next_btns: typing.List[pygame_gui.elements.UIButton] = []
        self._player_color_swatches: typing.List[pygame_gui.elements.UIPanel] = []
        self._player_human_buttons: typing.List[pygame_gui.elements.UIButton] = []
        self._player_is_human: typing.List[bool] = []

        # Slider references (value read via .get_current_value())
        self._num_systems_slider: typing.Optional[pygame_gui.elements.UIHorizontalSlider] = None
        self._num_systems_label: typing.Optional[pygame_gui.elements.UILabel] = None
        self._sys_radius_min_slider: typing.Optional[pygame_gui.elements.UIHorizontalSlider] = None
        self._sys_radius_min_label: typing.Optional[pygame_gui.elements.UILabel] = None
        self._sys_radius_max_slider: typing.Optional[pygame_gui.elements.UIHorizontalSlider] = None
        self._sys_radius_max_label: typing.Optional[pygame_gui.elements.UILabel] = None
        self._wormhole_density_slider: typing.Optional[pygame_gui.elements.UIHorizontalSlider] = None
        self._wormhole_density_label: typing.Optional[pygame_gui.elements.UILabel] = None
        self._min_dist_slider: typing.Optional[pygame_gui.elements.UIHorizontalSlider] = None
        self._min_dist_label: typing.Optional[pygame_gui.elements.UILabel] = None
        self._max_dist_slider: typing.Optional[pygame_gui.elements.UIHorizontalSlider] = None
        self._max_dist_label: typing.Optional[pygame_gui.elements.UILabel] = None

        # Economy text entries
        self._credits_entry: typing.Optional[pygame_gui.elements.UITextEntryLine] = None
        self._metal_entry: typing.Optional[pygame_gui.elements.UITextEntryLine] = None
        self._crystal_entry: typing.Optional[pygame_gui.elements.UITextEntryLine] = None
        self._population_entry: typing.Optional[pygame_gui.elements.UITextEntryLine] = None

        # Player count buttons
        self._player_minus_btn: typing.Optional[pygame_gui.elements.UIButton] = None
        self._player_plus_btn: typing.Optional[pygame_gui.elements.UIButton] = None
        self._player_count_label: typing.Optional[pygame_gui.elements.UILabel] = None

        # Player rows panel (rebuilt when count changes)
        self._player_rows_panel: typing.Optional[pygame_gui.elements.UIPanel] = None

        # Action buttons
        self.start_button: typing.Optional[pygame_gui.elements.UIButton] = None
        self.cancel_button: typing.Optional[pygame_gui.elements.UIButton] = None

        # Scrollable container for the main body
        self._scrollable: typing.Optional[pygame_gui.elements.UIScrollingContainer] = None

        self._build_ui()

    # ------------------------------------------------------------------
    # Scaling helpers
    # ------------------------------------------------------------------
    def _sx(self, v: float) -> int:
        return int(v * self.scale_x)

    def _sy(self, v: float) -> int:
        return int(v * self.scale_y)

    # ------------------------------------------------------------------
    # Full UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Constructs all wizard UI elements inside the window."""
        # Bottom action bar (fixed, not scrolled)
        btn_bar_h = self._sy(_BTN_H + _PAD * 2)
        scrollable_h = self._content_h - btn_bar_h

        # --- Scrollable area ---
        scroll_rect = pygame.Rect(
            0, 0,
            self._content_w,
            scrollable_h,
        )
        self._scrollable = pygame_gui.elements.UIScrollingContainer(
            relative_rect=scroll_rect,
            manager=self.manager,
            container=self.window,
            object_id="#wizard_scroll",
        )

        # We'll lay out content vertically within the scrollable container
        cursor_y = _PAD
        inner_w = self._content_w - self._sx(20)  # leave room for scrollbar

        # ── Section: Players ─────────────────────────────────────────
        cursor_y = self._add_section_header("Players", cursor_y, inner_w)

        # Player count row (+/- buttons + count label)
        cursor_y = self._add_player_count_row(cursor_y, inner_w)

        # Individual player rows
        cursor_y = self._build_player_rows(cursor_y, inner_w)

        # ── Section: Galaxy ───────────────────────────────────────────
        cursor_y = self._add_section_header("Galaxy", cursor_y, inner_w)

        cursor_y, self._num_systems_slider, self._num_systems_label = self._add_slider_row(
            "Star Systems:", cursor_y, inner_w,
            min_val=5, max_val=30, start_val=15,
            object_id="#systems_slider",
        )
        cursor_y, self._sys_radius_min_slider, self._sys_radius_min_label = self._add_slider_row(
            "Min System Radius:", cursor_y, inner_w,
            min_val=3, max_val=9, start_val=5,
            object_id="#radius_min_slider",
        )
        cursor_y, self._sys_radius_max_slider, self._sys_radius_max_label = self._add_slider_row(
            "Max System Radius:", cursor_y, inner_w,
            min_val=4, max_val=10, start_val=8,
            object_id="#radius_max_slider",
        )
        cursor_y, self._wormhole_density_slider, self._wormhole_density_label = self._add_slider_row(
            "Wormhole Density:", cursor_y, inner_w,
            min_val=0, max_val=100, start_val=33,
            object_id="#wormhole_slider",
            value_suffix="%",
        )
        cursor_y, self._min_dist_slider, self._min_dist_label = self._add_slider_row(
            "Min System Dist:", cursor_y, inner_w,
            min_val=30, max_val=200, start_val=50,
            object_id="#min_dist_slider",
        )
        cursor_y, self._max_dist_slider, self._max_dist_label = self._add_slider_row(
            "Max System Dist:", cursor_y, inner_w,
            min_val=100, max_val=600, start_val=350,
            object_id="#max_dist_slider",
        )

        # ── Section: Economy ──────────────────────────────────────────
        cursor_y = self._add_section_header("Economy", cursor_y, inner_w)

        cursor_y, self._credits_entry = self._add_numeric_entry_row(
            "Starting Credits:", cursor_y, inner_w, default="20000",
            object_id="#credits_entry",
        )
        cursor_y, self._metal_entry = self._add_numeric_entry_row(
            "Starting Metal:", cursor_y, inner_w, default="10000",
            object_id="#metal_entry",
        )
        cursor_y, self._crystal_entry = self._add_numeric_entry_row(
            "Starting Crystal:", cursor_y, inner_w, default="10000",
            object_id="#crystal_entry",
        )
        cursor_y, self._population_entry = self._add_numeric_entry_row(
            "Homeworld Population:", cursor_y, inner_w, default="50",
            object_id="#population_entry",
        )

        # Resize the scrollable container to fit content
        cursor_y += self._sy(_PAD)
        self._scrollable.set_scrollable_area_dimensions(
            (inner_w, max(cursor_y, scrollable_h))
        )

        # --- Bottom action buttons (not scrolled) ---
        self._add_action_buttons(scrollable_h, btn_bar_h)

    # ------------------------------------------------------------------
    # Widget builder helpers
    # ------------------------------------------------------------------

    def _add_section_header(self, title: str, y: int, width: int) -> int:
        """Adds a bold section header label; returns new y cursor."""
        header_h = self._sy(_SECTION_H)
        top_pad = self._sy(_PAD)
        pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(
                self._sx(_PAD), y + top_pad,
                width - self._sx(_PAD * 2), header_h,
            ),
            text=f"── {title} ──────────────────────────",
            manager=self.manager,
            container=self._scrollable,
            object_id="#wizard_section_header",
        )
        return y + top_pad + header_h + self._sy(4)

    def _add_player_count_row(self, y: int, width: int) -> int:
        """Adds the player count +/- row; returns new y cursor."""
        row_h = self._sy(_ROW_H)
        lbl_w = self._sx(160)
        btn_sz = self._sy(_ROW_H)
        count_lbl_w = self._sx(40)

        pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(self._sx(_PAD), y, lbl_w, row_h),
            text="Number of Players:",
            manager=self.manager,
            container=self._scrollable,
        )

        x_offset = self._sx(_PAD) + lbl_w + self._sx(8)
        self._player_minus_btn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(x_offset, y, btn_sz, row_h),
            text="−",
            manager=self.manager,
            container=self._scrollable,
            object_id="#player_minus_button",
        )
        x_offset += btn_sz + self._sx(4)
        self._player_count_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(x_offset, y, count_lbl_w, row_h),
            text=str(self._num_players),
            manager=self.manager,
            container=self._scrollable,
            object_id="#player_count_label",
        )
        x_offset += count_lbl_w + self._sx(4)
        self._player_plus_btn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(x_offset, y, btn_sz, row_h),
            text="+",
            manager=self.manager,
            container=self._scrollable,
            object_id="#player_plus_button",
        )
        return y + row_h + self._sy(_PAD)

    def _build_player_rows(self, y: int, width: int) -> int:
        """Creates per-player name/color/type rows; returns new y cursor."""
        self._player_name_entries = []
        self._player_color_indices = []
        self._player_color_prev_btns = []
        self._player_color_next_btns = []
        self._player_color_swatches = []
        self._player_human_buttons = []
        self._player_is_human = []

        for i in range(self._num_players):
            y = self._add_single_player_row(i, y, width)

        return y

    def _add_single_player_row(self, index: int, y: int, width: int) -> int:
        """Adds one player row (index label, name entry, colour swatch cycler, human button)."""
        row_h = self._sy(_PLAYER_ROW_H)
        pad = self._sx(_PAD)

        # Index label e.g. "P1"
        idx_lbl_w = self._sx(24)
        pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(pad, y, idx_lbl_w, row_h),
            text=f"P{index + 1}",
            manager=self.manager,
            container=self._scrollable,
        )

        # Name entry
        name_entry_w = self._sx(150)
        name_x = pad + idx_lbl_w + self._sx(6)
        entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(name_x, y, name_entry_w, row_h),
            manager=self.manager,
            container=self._scrollable,
            object_id=f"#player_name_entry_{index}",
        )
        entry.set_text(f"Player {index + 1}")
        self._player_name_entries.append(entry)

        # ── Colour swatch cycler: [◀] [■■■] [▶] ─────────────────────────
        # Use the saved index if available (after a rebuild/restore), or default.
        if index < len(self._player_color_indices):
            color_idx = self._player_color_indices[index]
        else:
            default_name = build_default_color_name_for_index(index)
            color_idx = next(
                (i for i, (n, _) in enumerate(PLAYER_COLOR_PALETTE) if n == default_name),
                index % len(PLAYER_COLOR_PALETTE),
            )
            self._player_color_indices.append(color_idx)

        cycle_btn_w = self._sx(_COLOR_CYCLE_BTN_W)
        swatch_w = self._sx(_COLOR_SWATCH_W)
        color_x = name_x + name_entry_w + self._sx(8)

        prev_btn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(color_x, y, cycle_btn_w, row_h),
            text="◀",
            manager=self.manager,
            container=self._scrollable,
            object_id=f"#player_color_prev_{index}",
        )
        self._player_color_prev_btns.append(prev_btn)

        swatch_panel = pygame_gui.elements.UIPanel(
            relative_rect=pygame.Rect(color_x + cycle_btn_w, y, swatch_w, row_h),
            manager=self.manager,
            container=self._scrollable,
            object_id=f"#player_color_swatch_{index}",
        )
        self._player_color_swatches.append(swatch_panel)

        next_btn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(color_x + cycle_btn_w + swatch_w, y, cycle_btn_w, row_h),
            text="▶",
            manager=self.manager,
            container=self._scrollable,
            object_id=f"#player_color_next_{index}",
        )
        self._player_color_next_btns.append(next_btn)

        color_block_w = cycle_btn_w * 2 + swatch_w

        # Human / AI toggle button
        human_btn_w = self._sx(68)
        human_x = color_x + color_block_w + self._sx(8)
        is_human = True
        btn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(human_x, y, human_btn_w, row_h),
            text="Human",
            manager=self.manager,
            container=self._scrollable,
            object_id=f"#player_type_button_{index}",
        )
        self._player_human_buttons.append(btn)
        self._player_is_human.append(is_human)

        return y + row_h + self._sy(4)

    def _cycle_player_color(self, player_index: int, delta: int) -> None:
        """Cycles the colour for a player by ±1, wrapping around the palette."""
        cur = self._player_color_indices[player_index]
        self._player_color_indices[player_index] = (cur + delta) % len(PLAYER_COLOR_PALETTE)

    def draw_swatches(self, surface: pygame.Surface) -> None:
        """Draws filled colour squares on top of each player's swatch panel.

        Must be called **after** ``manager.draw_ui(surface)`` so the fill
        renders on top of the pygame_gui panel background.
        """
        if not self._scrollable:
            return

        # Find any UIWindow elements layered on top of the wizard window
        blockers: typing.List[pygame.Rect] = []
        if self.manager:
            wizard_layer_found = False
            for sprite in self.manager.get_sprite_group().sprites():
                if sprite is self.window:
                    wizard_layer_found = True
                    continue
                if (
                    wizard_layer_found
                    and isinstance(sprite, pygame_gui.elements.UIWindow)
                    and sprite.alive()
                    and sprite.visible
                ):
                    blockers.append(sprite.get_abs_rect())

        scroll_clip = self._scrollable.get_abs_rect()
        for i, panel in enumerate(self._player_color_swatches):
            if not panel.alive():
                continue
            color_rgb = PLAYER_COLOR_PALETTE[self._player_color_indices[i]][1]
            abs_rect = panel.get_abs_rect()
            clipped = abs_rect.clip(scroll_clip)
            if clipped.width > 0 and clipped.height > 0:
                rects_to_draw = [clipped]
                for b in blockers:
                    next_rects = []
                    for r in rects_to_draw:
                        next_rects.extend(_subtract_rect_from_blocker(r, b))
                    rects_to_draw = next_rects
                    if not rects_to_draw:
                        break
                for sub_r in rects_to_draw:
                    surface.fill(color_rgb, sub_r)

    def _add_slider_row(
        self,
        label: str,
        y: int,
        width: int,
        min_val: int,
        max_val: int,
        start_val: int,
        object_id: str,
        value_suffix: str = "",
    ) -> typing.Tuple[int, pygame_gui.elements.UIHorizontalSlider, pygame_gui.elements.UILabel]:
        """Adds a labelled horizontal slider row; returns (new_y, slider, value_label)."""
        row_h = self._sy(_ROW_H)
        pad = self._sx(_PAD)
        lbl_w = self._sx(170)
        val_lbl_w = self._sx(56)
        slider_w = width - lbl_w - val_lbl_w - pad * 3

        pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(pad, y, lbl_w, row_h),
            text=label,
            manager=self.manager,
            container=self._scrollable,
        )

        slider = pygame_gui.elements.UIHorizontalSlider(
            relative_rect=pygame.Rect(pad + lbl_w, y, slider_w, row_h),
            start_value=start_val,
            value_range=(min_val, max_val),
            manager=self.manager,
            container=self._scrollable,
            object_id=object_id,
        )

        val_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(pad + lbl_w + slider_w + pad, y, val_lbl_w, row_h),
            text=f"{start_val}{value_suffix}",
            manager=self.manager,
            container=self._scrollable,
            object_id=f"{object_id}_value_label",
        )

        return y + row_h + self._sy(4), slider, val_label

    def _add_numeric_entry_row(
        self,
        label: str,
        y: int,
        width: int,
        default: str,
        object_id: str,
    ) -> typing.Tuple[int, pygame_gui.elements.UITextEntryLine]:
        """Adds a labelled text entry row for numeric input; returns (new_y, entry)."""
        row_h = self._sy(_ROW_H)
        pad = self._sx(_PAD)
        lbl_w = self._sx(200)
        entry_w = self._sx(120)

        pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(pad, y, lbl_w, row_h),
            text=label,
            manager=self.manager,
            container=self._scrollable,
        )

        entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(pad + lbl_w, y, entry_w, row_h),
            manager=self.manager,
            container=self._scrollable,
            object_id=object_id,
        )
        entry.set_text(default)
        entry.set_allowed_characters("numbers")

        return y + row_h + self._sy(4), entry

    def _add_action_buttons(self, scrollable_h: int, btn_bar_h: int) -> None:
        """Adds Start Game / Cancel buttons below the scrollable area."""
        btn_h = self._sy(_BTN_H)
        btn_w_start = self._sx(_BTN_W)
        btn_w_cancel = self._sx(_BTN_W)
        bar_y = scrollable_h + (btn_bar_h - btn_h) // 2
        total_btn_w = btn_w_start + self._sx(_PAD) + btn_w_cancel
        bar_x = (self._content_w - total_btn_w) // 2

        self.start_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(bar_x, bar_y, btn_w_start, btn_h),
            text="Start Game",
            manager=self.manager,
            container=self.window,
            object_id="#wizard_start_button",
        )
        self.cancel_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(bar_x + btn_w_start + self._sx(_PAD), bar_y, btn_w_cancel, btn_h),
            text="Cancel",
            manager=self.manager,
            container=self.window,
            object_id="#wizard_cancel_button",
        )

    # ------------------------------------------------------------------
    # Player count change
    # ------------------------------------------------------------------
    def _adjust_player_count(self, delta: int) -> None:
        """Increases or decreases the player count, rebuilding player rows.

        Snapshot/restore is handled entirely by _full_rebuild(), so we do not
        need to manually kill player widgets here first.
        """
        new_count = max(_MIN_PLAYERS, min(_MAX_PLAYERS, self._num_players + delta))
        if new_count == self._num_players:
            return

        self._num_players = new_count
        if self._player_count_label:
            self._player_count_label.set_text(str(self._num_players))

        # Re-enable/disable +/- buttons
        if self._player_minus_btn:
            if self._num_players <= _MIN_PLAYERS:
                self._player_minus_btn.disable()
            else:
                self._player_minus_btn.enable()
        if self._player_plus_btn:
            if self._num_players >= _MAX_PLAYERS:
                self._player_plus_btn.disable()
            else:
                self._player_plus_btn.enable()

        # We rebuild all rows in-place.  Because pygame_gui doesn't support
        # dynamic repositioning of existing widgets easily, we kill and
        # recreate everything in the scrollable container below the
        # player-count row.  A full rebuild is the simplest reliable approach.
        self._full_rebuild()


    def _full_rebuild(self) -> None:
        """Kills the scrollable container and action buttons, then recreates all UI."""
        # Snapshot current values
        snap = self._snapshot()

        # Kill scrollable and buttons
        if self._scrollable:
            self._scrollable.kill()
            self._scrollable = None
        if self.start_button:
            self.start_button.kill()
            self.start_button = None
        if self.cancel_button:
            self.cancel_button.kill()
            self.cancel_button = None

        # Clear internal refs
        self._player_name_entries = []
        self._player_color_indices = []
        self._player_color_prev_btns = []
        self._player_color_swatches = []
        self._player_color_next_btns = []
        self._player_human_buttons = []
        self._player_is_human = []

        # Rebuild
        self._build_ui()

        # Restore snapshot
        self._restore_snapshot(snap)

    # ------------------------------------------------------------------
    # Snapshot / restore for rebuild
    # ------------------------------------------------------------------

    def _snapshot(self) -> dict:
        """Captures current widget values into a plain dict."""
        return {
            "num_players": self._num_players,
            "player_names": [e.get_text() for e in self._player_name_entries],
            "player_colors": [
                PLAYER_COLOR_PALETTE[idx][0] for idx in self._player_color_indices
            ],
            "player_humans": list(self._player_is_human),
            "num_systems": self._num_systems_slider.get_current_value() if self._num_systems_slider else 15,
            "radius_min": self._sys_radius_min_slider.get_current_value() if self._sys_radius_min_slider else 5,
            "radius_max": self._sys_radius_max_slider.get_current_value() if self._sys_radius_max_slider else 8,
            "wormhole_density": self._wormhole_density_slider.get_current_value() if self._wormhole_density_slider else 33,
            "min_dist": self._min_dist_slider.get_current_value() if self._min_dist_slider else 50,
            "max_dist": self._max_dist_slider.get_current_value() if self._max_dist_slider else 350,
            "credits": self._credits_entry.get_text() if self._credits_entry else "20000",
            "metal": self._metal_entry.get_text() if self._metal_entry else "10000",
            "crystal": self._crystal_entry.get_text() if self._crystal_entry else "10000",
            "population": self._population_entry.get_text() if self._population_entry else "50",
        }

    def _restore_snapshot(self, snap: dict) -> None:
        """Restores widget values from a snapshot dict (best-effort)."""
        player_names = snap.get("player_names", [])
        player_colors = snap.get("player_colors", [])  # list of color name strings
        player_humans = snap.get("player_humans", [])

        for i, entry in enumerate(self._player_name_entries):
            if i < len(player_names):
                entry.set_text(player_names[i])
        for i in range(len(self._player_color_indices)):
            if i < len(player_colors):
                saved_name = player_colors[i]
                found_idx = next(
                    (j for j, (n, _) in enumerate(PLAYER_COLOR_PALETTE) if n == saved_name),
                    None,
                )
                if found_idx is not None:
                    self._player_color_indices[i] = found_idx
        for i, is_h in enumerate(player_humans):
            if i < len(self._player_is_human):
                self._player_is_human[i] = is_h
                if self._player_human_buttons[i]:
                    self._player_human_buttons[i].set_text("Human" if is_h else "AI")

        def _restore_slider(slider, value):
            if slider and value is not None:
                slider.set_current_value(value)

        _restore_slider(self._num_systems_slider, snap.get("num_systems"))
        _restore_slider(self._sys_radius_min_slider, snap.get("radius_min"))
        _restore_slider(self._sys_radius_max_slider, snap.get("radius_max"))
        _restore_slider(self._wormhole_density_slider, snap.get("wormhole_density"))
        _restore_slider(self._min_dist_slider, snap.get("min_dist"))
        _restore_slider(self._max_dist_slider, snap.get("max_dist"))

        if self._credits_entry and snap.get("credits"):
            self._credits_entry.set_text(snap["credits"])
        if self._metal_entry and snap.get("metal"):
            self._metal_entry.set_text(snap["metal"])
        if self._crystal_entry and snap.get("crystal"):
            self._crystal_entry.set_text(snap["crystal"])
        if self._population_entry and snap.get("population"):
            self._population_entry.set_text(snap["population"])

    # ------------------------------------------------------------------
    # Event processing
    # ------------------------------------------------------------------

    def has_duplicate_colors(self) -> bool:
        """Returns True if any two active players share the same color assignment."""
        active_indices = self._player_color_indices[:self._num_players]
        return len(set(active_indices)) < len(active_indices)

    def get_validation_errors(self) -> typing.List[str]:
        """Validates all wizard inputs and returns a list of human-readable error messages."""
        errors: typing.List[str] = []

        if self.has_duplicate_colors():
            errors.append("Each player must be assigned a unique color before starting the game.")

        radius_min = int(self._sys_radius_min_slider.get_current_value()) if self._sys_radius_min_slider else 5
        radius_max = int(self._sys_radius_max_slider.get_current_value()) if self._sys_radius_max_slider else 8
        if radius_min > radius_max:
            errors.append(
                f"Min System Radius ({radius_min}) cannot be greater than Max System Radius ({radius_max})."
            )

        min_dist = float(int(self._min_dist_slider.get_current_value())) if self._min_dist_slider else 50.0
        max_dist = float(int(self._max_dist_slider.get_current_value())) if self._max_dist_slider else 350.0
        if min_dist >= max_dist:
            errors.append(
                f"Min System Distance ({int(min_dist)}) must be strictly less than Max System Distance ({int(max_dist)})."
            )

        return errors

    def process_event(self, event: pygame.event.Event) -> typing.Optional[dict]:
        """Processes a pygame event; returns an action dict or None.

        Returns:
            ``{'action': 'start_new_game_with_settings', 'settings': GameSettings}``
            when the player clicks Start Game and validation passes.

            ``{'action': 'duplicate_player_colors_warning', 'message': str}``
            when duplicate player colors are detected.

            ``{'action': 'wizard_settings_error', 'message': str, 'title': str}``
            when settings validation fails.

            ``{'action': 'cancel_new_game_wizard'}`` when the player cancels.

            ``None`` for events consumed internally.
        """
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            element = event.ui_element

            if element is self.start_button:
                validation_errors = self.get_validation_errors()
                if validation_errors:
                    if len(validation_errors) == 1 and self.has_duplicate_colors():
                        return {
                            "action": "duplicate_player_colors_warning",
                            "message": validation_errors[0],
                        }
                    return {
                        "action": "wizard_settings_error",
                        "message": "\n".join(validation_errors),
                        "title": "Invalid Game Settings",
                    }
                return self._build_start_action()

            if element is self.cancel_button:
                return {"action": "cancel_new_game_wizard"}

            if element is self._player_minus_btn:
                self._adjust_player_count(-1)
                return None

            if element is self._player_plus_btn:
                self._adjust_player_count(+1)
                return None

            # Color cycle buttons
            for i, btn in enumerate(self._player_color_prev_btns):
                if element is btn:
                    self._cycle_player_color(i, -1)
                    return None
            for i, btn in enumerate(self._player_color_next_btns):
                if element is btn:
                    self._cycle_player_color(i, +1)
                    return None

            # Human/AI toggle buttons
            for i, btn in enumerate(self._player_human_buttons):
                if element is btn:
                    self._player_is_human[i] = not self._player_is_human[i]
                    btn.set_text("Human" if self._player_is_human[i] else "AI")
                    return None

        elif event.type == pygame_gui.UI_HORIZONTAL_SLIDER_MOVED:
            self._update_slider_labels()

        return None

    def _update_slider_labels(self) -> None:
        """Refreshes all slider value labels from current slider states."""
        def _upd(slider, label, suffix=""):
            if slider and label:
                label.set_text(f"{int(slider.get_current_value())}{suffix}")

        _upd(self._num_systems_slider, self._num_systems_label)
        _upd(self._sys_radius_min_slider, self._sys_radius_min_label)
        _upd(self._sys_radius_max_slider, self._sys_radius_max_label)
        _upd(self._wormhole_density_slider, self._wormhole_density_label, "%")
        _upd(self._min_dist_slider, self._min_dist_label)
        _upd(self._max_dist_slider, self._max_dist_label)

    # ------------------------------------------------------------------
    # Build GameSettings from current widget values
    # ------------------------------------------------------------------

    def _safe_float(self, text: str, fallback: float) -> float:
        try:
            v = float(text.strip())
            return v if v > 0 else fallback
        except ValueError:
            return fallback

    def _safe_int(self, text: str, fallback: int) -> int:
        try:
            v = int(text.strip())
            return v if v > 0 else fallback
        except ValueError:
            return fallback

    def _build_start_action(self) -> dict:
        """Reads all widget values and produces a start_new_game_with_settings action."""
        player_configs: typing.List[PlayerConfig] = []
        for i in range(self._num_players):
            name = (
                self._player_name_entries[i].get_text().strip()
                if i < len(self._player_name_entries)
                else f"Player {i + 1}"
            ) or f"Player {i + 1}"

            if i < len(self._player_color_indices):
                pal_entry = PLAYER_COLOR_PALETTE[self._player_color_indices[i]]
                color = pal_entry[1]
            else:
                color = PLAYER_COLOR_PALETTE[i % len(PLAYER_COLOR_PALETTE)][1]
            is_human = self._player_is_human[i] if i < len(self._player_is_human) else True
            player_configs.append(PlayerConfig(name=name, color=color, is_human=is_human))

        num_systems = int(self._num_systems_slider.get_current_value()) if self._num_systems_slider else 15

        radius_min = int(self._sys_radius_min_slider.get_current_value()) if self._sys_radius_min_slider else 5
        radius_max = int(self._sys_radius_max_slider.get_current_value()) if self._sys_radius_max_slider else 8

        wormhole_pct = int(self._wormhole_density_slider.get_current_value()) if self._wormhole_density_slider else 33
        wormhole_density = wormhole_pct / 100.0

        min_dist = float(int(self._min_dist_slider.get_current_value())) if self._min_dist_slider else 50.0
        max_dist = float(int(self._max_dist_slider.get_current_value())) if self._max_dist_slider else 350.0

        credits_ = self._safe_float(self._credits_entry.get_text() if self._credits_entry else "20000", 20000.0)
        metal = self._safe_float(self._metal_entry.get_text() if self._metal_entry else "10000", 10000.0)
        crystal = self._safe_float(self._crystal_entry.get_text() if self._crystal_entry else "10000", 10000.0)
        population = self._safe_int(self._population_entry.get_text() if self._population_entry else "50", 50)

        settings = GameSettings(
            player_configs=player_configs,
            num_systems=num_systems,
            min_system_distance=min_dist,
            max_system_distance=max_dist,
            wormhole_density=wormhole_density,
            system_radius_min=radius_min,
            system_radius_max=radius_max,
            starting_credits=credits_,
            starting_metal=metal,
            starting_crystal=crystal,
            starting_population=population,
        )

        return {"action": "start_new_game_with_settings", "settings": settings}

    # ------------------------------------------------------------------
    # Lifetime helpers
    # ------------------------------------------------------------------

    @property
    def is_alive(self) -> bool:
        return self.window.alive()

    def kill(self) -> None:
        """Destroys the wizard window and all child elements."""
        if self.window.alive():
            self.window.kill()
