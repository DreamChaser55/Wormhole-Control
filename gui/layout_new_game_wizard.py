"""New Game Wizard – UIWindow-based two-stage configuration panel.

Stage 1: Galaxy Setup & Preview
  * Galaxy generation parameters: system count, radius min/max, wormhole density, min/max distances
  * Procedural galaxy generation with live "Generate Map" button
  * Real-time tactical Map Preview viewport showing systems and wormhole conduits

Stage 2: Factions & Starting Conditions
  * Spawn profile (Normal / Testing)
  * Player count (2-6), per-player name / colour / controller type / team
  * Home System assignment: Random or Specified per player (cycling or clicking map preview)
  * Economy: starting credits / metal / crystal / homeworld population
  * Map Preview continues displaying with player faction color indicators

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
    SpawnProfile,
    DEFAULT_SPAWN_PROFILE,
    normalize_spawn_profile,
)
from player_controller import PlayerController
from galaxy import Galaxy
from rendering.galaxy_renderer import draw_galaxy_preview, get_system_at_preview_point

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Layout constants (unscaled, in logical pixels at 1280×720 reference)
# ---------------------------------------------------------------------------
_WIN_W = 1180
_WIN_H = 640

_PAD = 10          # standard internal padding
_ROW_H = 34        # height of a labelled slider / text row
_SECTION_H = 22    # section header height
_BTN_H = 36        # action button height
_BTN_W = 150       # action button width

_PLAYER_ROW_H = 34  # per-player row height
_COLOR_SWATCH_W = 32  # width of the colored swatch panel
_COLOR_CYCLE_BTN_W = 22  # width of the ◀/▶ cycle buttons

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
    """Wraps a ``pygame_gui.elements.UIWindow`` two-stage wizard for new-game configuration.

    Args:
        manager: The active pygame_gui UIManager.
        screen_res: Screen resolution Vector (exposes .x and .y).
        scale_x: Horizontal scale factor (screen_width / 1280).
        scale_y: Vertical scale factor (screen_height / 720).
        initial_stage: Initial wizard stage to display (1 or 2, default 1).
    """

    def __init__(
        self,
        manager: pygame_gui.UIManager,
        screen_res,
        scale_x: float,
        scale_y: float,
        initial_stage: int = 1,
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
            window_display_title="New Game — Stage 1: Galaxy Setup",
            object_id="#new_game_wizard_window",
            resizable=False,
        )

        inner = self.window.get_container().get_size()
        self._content_w = inner[0]
        self._content_h = inner[1]

        # Stage state: 1 = Galaxy Generation & Preview, 2 = Factions & Economy
        self._stage: int = initial_stage

        # --- Map Generation State ---
        self._num_systems: int = 15
        self._sys_radius_min: int = 6
        self._sys_radius_max: int = 10
        self._wormhole_density: int = 33  # percentage 0-100
        self._min_dist: int = 50
        self._max_dist: int = 350
        self._generated_galaxy: typing.Optional[Galaxy] = None

        # --- Player & Faction State ---
        self._num_players: int = 3
        self._spawn_profile: SpawnProfile = DEFAULT_SPAWN_PROFILE
        self._player_names: typing.List[str] = [f"Player {i + 1}" for i in range(self._num_players)]
        self._player_color_indices: typing.List[int] = [i % len(PLAYER_COLOR_PALETTE) for i in range(self._num_players)]
        self._player_controllers: typing.List[PlayerController] = [
            PlayerController.HUMAN if i == 0 else PlayerController.OPENAI
            for i in range(self._num_players)
        ]
        self._player_ai_reasoning_efforts: typing.List[str] = [
            "medium" if i == 0 else "low" for i in range(self._num_players)
        ]
        self._player_teams: typing.List[int] = [i + 1 for i in range(self._num_players)]
        self._home_system_mode: str = "random"  # "random" or "specified"
        self._player_home_systems: typing.List[typing.Optional[str]] = ["Random"] * self._num_players
        self._selected_player_index_for_home: int = 0

        # --- Economy State ---
        self._credits_str: str = "20000"
        self._metal_str: str = "10000"
        self._crystal_str: str = "10000"
        self._population_str: str = "50"

        # --- Preview Interaction State ---
        self._preview_hovered_system: typing.Optional[str] = None
        self._preview_selected_system: typing.Optional[str] = None

        # Widget references
        self._preview_panel: typing.Optional[pygame_gui.elements.UIPanel] = None
        self._preview_hint_label: typing.Optional[pygame_gui.elements.UILabel] = None
        self._galaxy_stats_label: typing.Optional[pygame_gui.elements.UILabel] = None
        self._generate_map_btn: typing.Optional[pygame_gui.elements.UIButton] = None

        # Stage 1 Slider widgets
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

        # Stage 2 Widgets
        self._scrollable: typing.Optional[pygame_gui.elements.UIScrollingContainer] = None
        self._spawn_profile_button: typing.Optional[pygame_gui.elements.UIButton] = None
        self._home_mode_button: typing.Optional[pygame_gui.elements.UIButton] = None
        self._player_minus_btn: typing.Optional[pygame_gui.elements.UIButton] = None
        self._player_plus_btn: typing.Optional[pygame_gui.elements.UIButton] = None
        self._player_count_label: typing.Optional[pygame_gui.elements.UILabel] = None

        self._player_name_entries: typing.List[pygame_gui.elements.UITextEntryLine] = []
        self._player_color_prev_btns: typing.List[pygame_gui.elements.UIButton] = []
        self._player_color_next_btns: typing.List[pygame_gui.elements.UIButton] = []
        self._player_color_swatches: typing.List[pygame_gui.elements.UIPanel] = []
        self._player_type_buttons: typing.List[pygame_gui.elements.UIButton] = []
        self._player_team_buttons: typing.List[pygame_gui.elements.UIButton] = []
        self._player_home_buttons: typing.List[pygame_gui.elements.UIButton] = []
        self._player_home_labels: typing.List[pygame_gui.elements.UILabel] = []
        self._player_select_labels: typing.List[pygame_gui.elements.UILabel] = []
        self._player_home_prev_btns: typing.List[pygame_gui.elements.UIButton] = []
        self._player_home_next_btns: typing.List[pygame_gui.elements.UIButton] = []

        self._credits_entry: typing.Optional[pygame_gui.elements.UITextEntryLine] = None
        self._metal_entry: typing.Optional[pygame_gui.elements.UITextEntryLine] = None
        self._crystal_entry: typing.Optional[pygame_gui.elements.UITextEntryLine] = None
        self._population_entry: typing.Optional[pygame_gui.elements.UITextEntryLine] = None

        # Action bar buttons
        self.back_button: typing.Optional[pygame_gui.elements.UIButton] = None
        self.cancel_button: typing.Optional[pygame_gui.elements.UIButton] = None
        self.next_button: typing.Optional[pygame_gui.elements.UIButton] = None
        self.start_button: typing.Optional[pygame_gui.elements.UIButton] = None

        # Track dynamically created stage elements to kill upon stage switch
        self._stage_elements: typing.List[pygame_gui.core.UIElement] = []

        # Generate initial map for preview
        self._generate_map()

        # Build active UI
        self._build_ui()

    # ------------------------------------------------------------------
    # Scaling helpers
    # ------------------------------------------------------------------
    def _sx(self, v: float) -> int:
        return int(v * self.scale_x)

    def _sy(self, v: float) -> int:
        return int(v * self.scale_y)

    # ------------------------------------------------------------------
    # Map Generation Logic
    # ------------------------------------------------------------------
    def _generate_map(self) -> None:
        """Generates a procedural Galaxy matching current parameters for preview."""
        temp_settings = GameSettings(
            num_systems=self._num_systems,
            min_system_distance=float(self._min_dist),
            max_system_distance=float(self._max_dist),
            wormhole_density=self._wormhole_density / 100.0,
            system_radius_min=self._sys_radius_min,
            system_radius_max=self._sys_radius_max,
            player_configs=[
                PlayerConfig(f"P{i + 1}", PLAYER_COLOR_PALETTE[i % len(PLAYER_COLOR_PALETTE)][1], team_id=i + 1)
                for i in range(self._num_players)
            ],
        )
        try:
            self._generated_galaxy = Galaxy(num_systems=self._num_systems, settings=temp_settings)
        except Exception as e:
            logger.debug(f"Error generating galaxy in wizard preview: {e}")
            self._generated_galaxy = None

        # Verify assigned home systems still exist in new galaxy
        if self._generated_galaxy and self._generated_galaxy.systems:
            avail_systems = set(self._generated_galaxy.systems.keys())
            for i in range(len(self._player_home_systems)):
                sys_val = self._player_home_systems[i]
                if sys_val and sys_val.lower() != "random" and sys_val not in avail_systems:
                    self._player_home_systems[i] = "Random"
        else:
            self._player_home_systems = ["Random"] * len(self._player_home_systems)

        if self._galaxy_stats_label and self._generated_galaxy:
            sys_cnt = len(self._generated_galaxy.systems)
            wh_cnt = len(self._generated_galaxy.wormholes) // 2
            self._galaxy_stats_label.set_text(f"{sys_cnt} Systems | {wh_cnt} Wormhole Conduits")

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        """Constructs UI elements for the active stage and map preview."""
        # Update window title
        if self._stage == 1:
            self.window.set_display_title("New Game — Stage 1: Galaxy Setup & Preview")
        else:
            self.window.set_display_title("New Game — Stage 2: Factions & Economy")

        btn_bar_h = self._sy(_BTN_H + _PAD * 2)
        main_h = self._content_h - btn_bar_h
        left_w = int(self._content_w * 0.48)
        right_w = self._content_w - left_w - self._sx(_PAD * 2)
        right_x = left_w + self._sx(_PAD)

        # 1. Build Persistent Right-Pane Map Preview
        self._build_preview_panel(right_x, self._sy(_PAD), right_w, main_h - self._sy(_PAD))

        # 2. Build Stage-specific Left-Pane Controls
        if self._stage == 1:
            self._build_stage_1_controls(left_w, main_h)
        else:
            self._build_stage_2_controls(left_w, main_h)

        # 3. Build Bottom Action Bar
        self._build_action_bar(main_h, btn_bar_h)

    def _build_preview_panel(self, x: int, y: int, width: int, height: int) -> None:
        """Constructs the Map Preview container and descriptive labels."""
        self._preview_panel = pygame_gui.elements.UIPanel(
            relative_rect=pygame.Rect(x, y, width, height),
            manager=self.manager,
            container=self.window,
            object_id="#wizard_preview_panel",
        )
        self._stage_elements.append(self._preview_panel)

        header_h = self._sy(_SECTION_H)
        title_lbl = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(self._sx(8), self._sy(4), width - self._sx(16), header_h),
            text="── Galaxy Map Preview ────────────────",
            manager=self.manager,
            container=self._preview_panel,
            object_id="#wizard_section_header",
        )
        self._stage_elements.append(title_lbl)

        hint_h = self._sy(32)
        hint_text = (
            "Galaxy layout preview. Click 'Generate Map' to re-roll."
            if self._stage == 1
            else "Click system on map to assign P1 (Player 1)."
        )
        self._preview_hint_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(self._sx(8), height - hint_h - self._sy(4), width - self._sx(16), hint_h),
            text=hint_text,
            manager=self.manager,
            container=self._preview_panel,
            object_id="#wizard_preview_hint",
        )
        self._stage_elements.append(self._preview_hint_label)

    def _get_preview_screen_rect(self) -> pygame.Rect:
        """Computes the screen bounding box for rendering the map preview."""
        if not self._preview_panel or not self._preview_panel.alive():
            return pygame.Rect(0, 0, 0, 0)
        panel_rect = self._preview_panel.get_abs_rect()
        pad_x = self._sx(10)
        pad_y = self._sy(6)
        header_h = self._sy(_SECTION_H) + pad_y
        hint_h = self._sy(32) + pad_y * 2
        return pygame.Rect(
            panel_rect.x + pad_x,
            panel_rect.y + header_h,
            max(0, panel_rect.width - pad_x * 2),
            max(0, panel_rect.height - header_h - hint_h),
        )

    # ------------------------------------------------------------------
    # Stage 1: Galaxy Parameters Controls
    # ------------------------------------------------------------------
    def _build_stage_1_controls(self, width: int, height: int) -> None:
        """Builds sliders and generation actions for Stage 1."""
        cursor_y = self._sy(_PAD)
        pad = self._sx(_PAD)
        inner_w = width - pad

        # Header
        hdr = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(pad, cursor_y, inner_w, self._sy(_SECTION_H)),
            text="── Galaxy Generation Parameters ────────",
            manager=self.manager,
            container=self.window,
            object_id="#wizard_section_header",
        )
        self._stage_elements.append(hdr)
        cursor_y += self._sy(_SECTION_H + 12)

        # Sliders
        cursor_y, self._num_systems_slider, self._num_systems_label = self._add_slider_row(
            "Star Systems:", cursor_y, inner_w,
            min_val=5, max_val=30, start_val=self._num_systems,
            object_id="#systems_slider",
        )
        cursor_y, self._sys_radius_min_slider, self._sys_radius_min_label = self._add_slider_row(
            "Min System Radius:", cursor_y, inner_w,
            min_val=3, max_val=9, start_val=self._sys_radius_min,
            object_id="#radius_min_slider",
        )
        cursor_y, self._sys_radius_max_slider, self._sys_radius_max_label = self._add_slider_row(
            "Max System Radius:", cursor_y, inner_w,
            min_val=4, max_val=12, start_val=self._sys_radius_max,
            object_id="#radius_max_slider",
        )
        cursor_y, self._wormhole_density_slider, self._wormhole_density_label = self._add_slider_row(
            "Wormhole Density:", cursor_y, inner_w,
            min_val=0, max_val=100, start_val=self._wormhole_density,
            object_id="#wormhole_slider",
            value_suffix="%",
        )
        cursor_y, self._min_dist_slider, self._min_dist_label = self._add_slider_row(
            "Min System Dist:", cursor_y, inner_w,
            min_val=30, max_val=200, start_val=self._min_dist,
            object_id="#min_dist_slider",
        )
        cursor_y, self._max_dist_slider, self._max_dist_label = self._add_slider_row(
            "Max System Dist:", cursor_y, inner_w,
            min_val=100, max_val=600, start_val=self._max_dist,
            object_id="#max_dist_slider",
        )

        # Action: Generate Map button & stats label
        cursor_y += self._sy(12)
        btn_w = self._sx(170)
        btn_h = self._sy(_BTN_H)
        self._generate_map_btn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(pad, cursor_y, btn_w, btn_h),
            text="⟳ Generate Map",
            manager=self.manager,
            container=self.window,
            object_id="#wizard_generate_map_button",
        )
        self._stage_elements.append(self._generate_map_btn)

        stats_text = ""
        if self._generated_galaxy and self._generated_galaxy.systems:
            sys_cnt = len(self._generated_galaxy.systems)
            wh_cnt = len(self._generated_galaxy.wormholes) // 2
            stats_text = f"{sys_cnt} Systems | {wh_cnt} Wormhole Conduits"

        self._galaxy_stats_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(pad + btn_w + self._sx(12), cursor_y, inner_w - btn_w - self._sx(12), btn_h),
            text=stats_text,
            manager=self.manager,
            container=self.window,
            object_id="#wizard_stats_label",
        )
        self._stage_elements.append(self._galaxy_stats_label)

        # Tactical guide / parameter summary card
        cursor_y += btn_h + self._sy(16)
        guide_hdr = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(pad, cursor_y, inner_w, self._sy(_SECTION_H)),
            text="── Galaxy Topology Guide ───────────────",
            manager=self.manager,
            container=self.window,
            object_id="#wizard_section_header",
        )
        self._stage_elements.append(guide_hdr)
        cursor_y += self._sy(_SECTION_H + 6)

        info_lines = [
            "• Star count & distances define cluster scale and FTL travel times.",
            "• System radius sets the number of orbital sector rings per star.",
            "• Wormhole density sets natural conduits linking distant systems.",
        ]
        info_line_h = self._sy(22)
        for line in info_lines:
            lbl = pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(pad + self._sx(4), cursor_y, inner_w - self._sx(8), info_line_h),
                text=line,
                manager=self.manager,
                container=self.window,
                object_id="#wizard_stats_label",
            )
            self._stage_elements.append(lbl)
            cursor_y += info_line_h

    # ------------------------------------------------------------------
    # Stage 2: Factions & Starting Conditions Controls
    # ------------------------------------------------------------------
    def _build_stage_2_controls(self, width: int, height: int) -> None:
        """Builds player rows, spawn profile, home system controls, and economy entries."""
        scroll_rect = pygame.Rect(0, 0, width, height)
        self._scrollable = pygame_gui.elements.UIScrollingContainer(
            relative_rect=scroll_rect,
            manager=self.manager,
            container=self.window,
            object_id="#wizard_scroll",
        )
        self._stage_elements.append(self._scrollable)

        cursor_y = self._sy(_PAD)
        inner_w = width - self._sx(22)

        # Header: Players & Factions
        cursor_y = self._add_section_header("Players & Factions", cursor_y, inner_w)

        # Spawn profile & Home mode row (side-by-side)
        cursor_y = self._add_spawn_and_home_mode_row(cursor_y, inner_w)

        # Player count row (+/- buttons + count label)
        cursor_y = self._add_player_count_row(cursor_y, inner_w)

        # Individual player rows
        cursor_y = self._build_player_rows(cursor_y, inner_w)

        # Header: Economy
        cursor_y = self._add_section_header("Starting Economy", cursor_y, inner_w)

        # 2x2 Economy Grid
        cursor_y = self._build_economy_grid(cursor_y, inner_w)

        cursor_y += self._sy(_PAD)
        self._scrollable.set_scrollable_area_dimensions((inner_w, max(cursor_y, height)))

    def _add_section_header(self, title: str, y: int, width: int) -> int:
        header_h = self._sy(_SECTION_H)
        top_pad = self._sy(6)
        hdr = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(self._sx(_PAD), y + top_pad, width - self._sx(_PAD * 2), header_h),
            text=f"── {title} ──────────────────────────",
            manager=self.manager,
            container=self._scrollable,
            object_id="#wizard_section_header",
        )
        self._stage_elements.append(hdr)
        return y + top_pad + header_h + self._sy(4)

    def _add_spawn_and_home_mode_row(self, y: int, width: int) -> int:
        """Arranges Spawn Profile and Home Systems Mode side-by-side on one row."""
        row_h = self._sy(_ROW_H)
        pad = self._sx(_PAD)

        # Left Column: Spawn Profile
        lbl_w_spawn = self._sx(115)
        btn_w_spawn = self._sx(120)

        lbl_spawn = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(pad, y, lbl_w_spawn, row_h),
            text="Spawn Profile:",
            manager=self.manager,
            container=self._scrollable,
            object_id="#spawn_profile_label",
        )
        self._stage_elements.append(lbl_spawn)

        self._spawn_profile_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(pad + lbl_w_spawn + self._sx(4), y, btn_w_spawn, row_h),
            text=self._spawn_profile.display_name,
            manager=self.manager,
            container=self._scrollable,
            object_id="#spawn_profile_button",
        )
        self._stage_elements.append(self._spawn_profile_button)

        # Right Column: Home Systems Mode
        col2_x = pad + lbl_w_spawn + btn_w_spawn + self._sx(14)
        lbl_w_home = self._sx(125)
        btn_w_home = self._sx(145)

        lbl_home = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(col2_x, y, lbl_w_home, row_h),
            text="Home Systems:",
            manager=self.manager,
            container=self._scrollable,
            object_id="#home_mode_label",
        )
        self._stage_elements.append(lbl_home)

        mode_text = "Mode: Random" if self._home_system_mode == "random" else "Mode: Specified"
        self._home_mode_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(col2_x + lbl_w_home + self._sx(4), y, btn_w_home, row_h),
            text=mode_text,
            manager=self.manager,
            container=self._scrollable,
            object_id="#home_mode_button",
        )
        self._stage_elements.append(self._home_mode_button)

        return y + row_h + self._sy(6)

    def _build_economy_grid(self, y: int, width: int) -> int:
        """Constructs a 2x2 grid for Starting Economy parameters."""
        row_h = self._sy(_ROW_H)
        pad = self._sx(_PAD)

        lbl_w = self._sx(125)
        entry_w = self._sx(100)
        col_w = lbl_w + entry_w
        col2_x = pad + col_w + self._sx(20)

        # Row 1 Left: Starting Credits
        lbl_cred = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(pad, y, lbl_w, row_h),
            text="Starting Credits:",
            manager=self.manager,
            container=self._scrollable,
        )
        self._stage_elements.append(lbl_cred)

        self._credits_entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(pad + lbl_w, y, entry_w, row_h),
            manager=self.manager,
            container=self._scrollable,
            object_id="#credits_entry",
        )
        self._credits_entry.set_text(self._credits_str)
        self._credits_entry.set_allowed_characters("numbers")
        self._stage_elements.append(self._credits_entry)

        # Row 1 Right: Starting Crystal
        lbl_crys = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(col2_x, y, lbl_w, row_h),
            text="Starting Crystal:",
            manager=self.manager,
            container=self._scrollable,
        )
        self._stage_elements.append(lbl_crys)

        self._crystal_entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(col2_x + lbl_w, y, entry_w, row_h),
            manager=self.manager,
            container=self._scrollable,
            object_id="#crystal_entry",
        )
        self._crystal_entry.set_text(self._crystal_str)
        self._crystal_entry.set_allowed_characters("numbers")
        self._stage_elements.append(self._crystal_entry)

        y += row_h + self._sy(6)

        # Row 2 Left: Starting Metal
        lbl_met = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(pad, y, lbl_w, row_h),
            text="Starting Metal:",
            manager=self.manager,
            container=self._scrollable,
        )
        self._stage_elements.append(lbl_met)

        self._metal_entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(pad + lbl_w, y, entry_w, row_h),
            manager=self.manager,
            container=self._scrollable,
            object_id="#metal_entry",
        )
        self._metal_entry.set_text(self._metal_str)
        self._metal_entry.set_allowed_characters("numbers")
        self._stage_elements.append(self._metal_entry)

        # Row 2 Right: Homeworld Population
        lbl_pop = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(col2_x, y, lbl_w, row_h),
            text="Homeworld Pop:",
            manager=self.manager,
            container=self._scrollable,
        )
        self._stage_elements.append(lbl_pop)

        self._population_entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(col2_x + lbl_w, y, entry_w, row_h),
            manager=self.manager,
            container=self._scrollable,
            object_id="#population_entry",
        )
        self._population_entry.set_text(self._population_str)
        self._population_entry.set_allowed_characters("numbers")
        self._stage_elements.append(self._population_entry)

        return y + row_h + self._sy(6)

    def _add_spawn_profile_row(self, y: int, width: int) -> int:
        row_h = self._sy(_ROW_H)
        pad = self._sx(_PAD)
        lbl_w = self._sx(140)
        btn_w = self._sx(110)

        lbl = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(pad, y, lbl_w, row_h),
            text="Spawn Profile:",
            manager=self.manager,
            container=self._scrollable,
            object_id="#spawn_profile_label",
        )
        self._stage_elements.append(lbl)

        self._spawn_profile_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(pad + lbl_w + self._sx(6), y, btn_w, row_h),
            text=self._spawn_profile.display_name,
            manager=self.manager,
            container=self._scrollable,
            object_id="#spawn_profile_button",
        )
        self._stage_elements.append(self._spawn_profile_button)
        return y + row_h + self._sy(6)

    def _cycle_spawn_profile(self) -> None:
        if self._spawn_profile == SpawnProfile.NORMAL:
            self._spawn_profile = SpawnProfile.TESTING
        else:
            self._spawn_profile = SpawnProfile.NORMAL
        if self._spawn_profile_button:
            self._spawn_profile_button.set_text(self._spawn_profile.display_name)

    def _add_home_mode_row(self, y: int, width: int) -> int:
        row_h = self._sy(_ROW_H)
        pad = self._sx(_PAD)
        lbl_w = self._sx(140)
        btn_w = self._sx(140)

        lbl = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(pad, y, lbl_w, row_h),
            text="Home Systems:",
            manager=self.manager,
            container=self._scrollable,
            object_id="#home_mode_label",
        )
        self._stage_elements.append(lbl)

        mode_text = "Mode: Random" if self._home_system_mode == "random" else "Mode: Specified"
        self._home_mode_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(pad + lbl_w + self._sx(6), y, btn_w, row_h),
            text=mode_text,
            manager=self.manager,
            container=self._scrollable,
            object_id="#home_mode_button",
        )
        self._stage_elements.append(self._home_mode_button)
        return y + row_h + self._sy(6)

    def _cycle_home_mode(self) -> None:
        """Toggles between Random and Specified home system assignment modes."""
        if self._home_system_mode == "random":
            self._home_system_mode = "specified"
        else:
            self._home_system_mode = "random"
        if self._home_mode_button:
            mode_text = "Mode: Random" if self._home_system_mode == "random" else "Mode: Specified"
            self._home_mode_button.set_text(mode_text)
        self._full_rebuild()

    def _add_player_count_row(self, y: int, width: int) -> int:
        row_h = self._sy(_ROW_H)
        lbl_w = self._sx(150)
        btn_sz = self._sy(_ROW_H)
        count_lbl_w = self._sx(36)

        lbl = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(self._sx(_PAD), y, lbl_w, row_h),
            text="Number of Players:",
            manager=self.manager,
            container=self._scrollable,
        )
        self._stage_elements.append(lbl)

        x_offset = self._sx(_PAD) + lbl_w + self._sx(6)
        self._player_minus_btn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(x_offset, y, btn_sz, row_h),
            text="−",
            manager=self.manager,
            container=self._scrollable,
            object_id="#player_minus_button",
        )
        self._stage_elements.append(self._player_minus_btn)

        x_offset += btn_sz + self._sx(4)
        self._player_count_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(x_offset, y, count_lbl_w, row_h),
            text=str(self._num_players),
            manager=self.manager,
            container=self._scrollable,
            object_id="#player_count_label",
        )
        self._stage_elements.append(self._player_count_label)

        x_offset += count_lbl_w + self._sx(4)
        self._player_plus_btn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(x_offset, y, btn_sz, row_h),
            text="+",
            manager=self.manager,
            container=self._scrollable,
            object_id="#player_plus_button",
        )
        self._stage_elements.append(self._player_plus_btn)

        return y + row_h + self._sy(8)

    def _build_player_rows(self, y: int, width: int) -> int:
        self._player_name_entries = []
        self._player_color_prev_btns = []
        self._player_color_next_btns = []
        self._player_color_swatches = []
        self._player_type_buttons = []
        self._player_team_buttons = []
        self._player_home_buttons = []
        self._player_home_labels = []
        self._player_select_labels = []
        self._player_home_prev_btns = []
        self._player_home_next_btns = []

        # Ensure state arrays match count
        while len(self._player_names) < self._num_players:
            self._player_names.append(f"Player {len(self._player_names) + 1}")
        while len(self._player_color_indices) < self._num_players:
            self._player_color_indices.append(len(self._player_color_indices) % len(PLAYER_COLOR_PALETTE))
        while len(self._player_controllers) < self._num_players:
            self._player_controllers.append(PlayerController.OPENAI)
            self._player_ai_reasoning_efforts.append("low")
        while len(self._player_teams) < self._num_players:
            self._player_teams.append(len(self._player_teams) + 1)
        while len(self._player_home_systems) < self._num_players:
            self._player_home_systems.append("Random")

        for i in range(self._num_players):
            y = self._add_single_player_block(i, y, width)

        return y

    def _add_single_player_block(self, index: int, y: int, width: int) -> int:
        row_h = self._sy(_PLAYER_ROW_H)
        pad = self._sx(_PAD)

        # Line 1: Index | Name | Swatch | Controller | Team
        idx_lbl_w = self._sx(26)
        idx_lbl = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(pad, y, idx_lbl_w, row_h),
            text=f"P{index + 1}",
            manager=self.manager,
            container=self._scrollable,
        )
        self._stage_elements.append(idx_lbl)

        name_w = self._sx(145)
        name_x = pad + idx_lbl_w + self._sx(6)
        entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(name_x, y, name_w, row_h),
            manager=self.manager,
            container=self._scrollable,
            object_id=f"#player_name_entry_{index}",
        )
        entry.set_text(self._player_names[index])
        self._player_name_entries.append(entry)
        self._stage_elements.append(entry)

        # Color cycler
        cycle_btn_w = self._sx(_COLOR_CYCLE_BTN_W)
        swatch_w = self._sx(_COLOR_SWATCH_W)
        color_x = name_x + name_w + self._sx(8)

        prev_c = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(color_x, y, cycle_btn_w, row_h),
            text="◀",
            manager=self.manager,
            container=self._scrollable,
            object_id=f"#player_color_prev_{index}",
        )
        self._player_color_prev_btns.append(prev_c)
        self._stage_elements.append(prev_c)

        swatch = pygame_gui.elements.UIPanel(
            relative_rect=pygame.Rect(color_x + cycle_btn_w, y, swatch_w, row_h),
            manager=self.manager,
            container=self._scrollable,
            object_id=f"#player_color_swatch_{index}",
        )
        self._player_color_swatches.append(swatch)
        self._stage_elements.append(swatch)

        next_c = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(color_x + cycle_btn_w + swatch_w, y, cycle_btn_w, row_h),
            text="▶",
            manager=self.manager,
            container=self._scrollable,
            object_id=f"#player_color_next_{index}",
        )
        self._player_color_next_btns.append(next_c)
        self._stage_elements.append(next_c)

        # Controller type button
        type_w = self._sx(105)
        type_x = color_x + cycle_btn_w * 2 + swatch_w + self._sx(8)
        controller = self._player_controllers[index]
        effort = self._player_ai_reasoning_efforts[index]
        type_btn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(type_x, y, type_w, row_h),
            text=self._player_type_label(controller, effort),
            manager=self.manager,
            container=self._scrollable,
            object_id=f"#player_type_button_{index}",
        )
        self._player_type_buttons.append(type_btn)
        self._stage_elements.append(type_btn)

        # Team button
        team_w = self._sx(80)
        team_x = type_x + type_w + self._sx(8)
        team_btn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(team_x, y, team_w, row_h),
            text=f"Team {self._player_teams[index]}",
            manager=self.manager,
            container=self._scrollable,
            object_id=f"#player_team_button_{index}",
        )
        self._player_team_buttons.append(team_btn)
        self._stage_elements.append(team_btn)

        # Line 2: Home system assignment
        y += row_h + self._sy(3)
        home_lbl_w = self._sx(50)
        home_lbl = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(pad + idx_lbl_w + self._sx(6), y, home_lbl_w, row_h),
            text="Home:",
            manager=self.manager,
            container=self._scrollable,
        )
        self._player_home_labels.append(home_lbl)
        self._stage_elements.append(home_lbl)

        home_x = pad + idx_lbl_w + self._sx(6) + home_lbl_w + self._sx(6)
        prev_h = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(home_x, y, cycle_btn_w, row_h),
            text="◀",
            manager=self.manager,
            container=self._scrollable,
            object_id=f"#player_home_prev_{index}",
        )
        self._player_home_prev_btns.append(prev_h)
        self._stage_elements.append(prev_h)

        sys_val = self._player_home_systems[index] or "Random"
        if self._home_system_mode == "random":
            sys_val = "Random (Auto)"
        sys_btn_w = self._sx(180)
        home_btn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(home_x + cycle_btn_w, y, sys_btn_w, row_h),
            text=sys_val,
            manager=self.manager,
            container=self._scrollable,
            object_id=f"#player_home_btn_{index}",
        )
        self._player_home_buttons.append(home_btn)
        self._stage_elements.append(home_btn)

        next_h = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(home_x + cycle_btn_w + sys_btn_w, y, cycle_btn_w, row_h),
            text="▶",
            manager=self.manager,
            container=self._scrollable,
            object_id=f"#player_home_next_{index}",
        )
        self._player_home_next_btns.append(next_h)
        self._stage_elements.append(next_h)

        # "click to select" indicator on the right side of the player row
        sel_lbl_x = home_x + cycle_btn_w + sys_btn_w + cycle_btn_w + self._sx(8)
        sel_lbl_w = max(self._sx(140), width - sel_lbl_x - self._sx(4))
        is_target = (index == self._selected_player_index_for_home and self._home_system_mode == "specified")
        sel_lbl = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(sel_lbl_x, y, sel_lbl_w, row_h),
            text="click to select" if is_target else "",
            manager=self.manager,
            container=self._scrollable,
            object_id="#player_select_hint",
        )
        self._player_select_labels.append(sel_lbl)
        self._stage_elements.append(sel_lbl)

        return y + row_h + self._sy(8)

    def _cycle_player_color(self, player_index: int, delta: int) -> None:
        cur = self._player_color_indices[player_index]
        self._player_color_indices[player_index] = (cur + delta) % len(PLAYER_COLOR_PALETTE)

    def _cycle_player_team(self, player_index: int, delta: int = 1) -> None:
        max_teams = max(2, self._num_players)
        cur = self._player_teams[player_index]
        new_team = ((cur - 1 + delta) % max_teams) + 1
        self._player_teams[player_index] = new_team
        if player_index < len(self._player_team_buttons) and self._player_team_buttons[player_index]:
            self._player_team_buttons[player_index].set_text(f"Team {new_team}")

    def _cycle_player_home_system(self, player_index: int, delta: int) -> None:
        """Cycles the home star system for a player among available generated systems."""
        if not self._generated_galaxy or not self._generated_galaxy.systems:
            return
        # If currently in random mode, switch to specified
        if self._home_system_mode != "specified":
            self._home_system_mode = "specified"
            if self._home_mode_button:
                self._home_mode_button.set_text("Mode: Specified")

        self._selected_player_index_for_home = player_index
        sys_list = ["Random"] + sorted(list(self._generated_galaxy.systems.keys()))
        cur_sys = self._player_home_systems[player_index] or "Random"
        cur_idx = sys_list.index(cur_sys) if cur_sys in sys_list else 0
        new_idx = (cur_idx + delta) % len(sys_list)
        new_sys = sys_list[new_idx]
        self._player_home_systems[player_index] = new_sys
        self._preview_selected_system = new_sys if new_sys != "Random" else None
        self._update_home_assignment_ui()

    def _update_home_assignment_ui(self) -> None:
        """Updates home assignment labels, button text, and preview hint label."""
        cur_idx = self._selected_player_index_for_home
        for j in range(self._num_players):
            if j < len(self._player_home_labels) and self._player_home_labels[j]:
                self._player_home_labels[j].set_text("Home:")
            if j < len(self._player_select_labels) and self._player_select_labels[j]:
                hint_text = "click to select" if (j == cur_idx and self._home_system_mode == "specified") else ""
                self._player_select_labels[j].set_text(hint_text)
            if j < len(self._player_home_buttons) and self._player_home_buttons[j]:
                val = self._player_home_systems[j] or "Random"
                disp = "Random (Auto)" if self._home_system_mode == "random" else val
                self._player_home_buttons[j].set_text(disp)

        if self._preview_hint_label and self._stage == 2:
            cur_name = self._player_names[cur_idx] if cur_idx < len(self._player_names) else f"Player {cur_idx + 1}"
            self._preview_hint_label.set_text(
                f"Click map to assign P{cur_idx + 1} ({cur_name}). Home marked in color."
            )

    @staticmethod
    def _player_type_label(controller: PlayerController, reasoning_effort: str) -> str:
        if controller == PlayerController.HUMAN:
            return "Human"
        if controller == PlayerController.CODEX:
            return "Codex"
        labels = {
            "low": "AI: Low",
            "medium": "AI: Medium",
            "high": "AI: High",
        }
        return labels.get(reasoning_effort, "AI: Medium")

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
        row_h = self._sy(_ROW_H)
        pad = self._sx(_PAD)
        lbl_w = self._sx(165)
        val_lbl_w = self._sx(55)
        slider_w = width - lbl_w - val_lbl_w - pad * 2

        lbl = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(pad, y, lbl_w, row_h),
            text=label,
            manager=self.manager,
            container=self.window,
        )
        self._stage_elements.append(lbl)

        slider = pygame_gui.elements.UIHorizontalSlider(
            relative_rect=pygame.Rect(pad + lbl_w, y, slider_w, row_h),
            start_value=start_val,
            value_range=(min_val, max_val),
            manager=self.manager,
            container=self.window,
            object_id=object_id,
        )
        self._stage_elements.append(slider)

        val_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(pad + lbl_w + slider_w + self._sx(4), y, val_lbl_w, row_h),
            text=f"{start_val}{value_suffix}",
            manager=self.manager,
            container=self.window,
            object_id=f"{object_id}_value_label",
        )
        self._stage_elements.append(val_label)

        return y + row_h + self._sy(8), slider, val_label

    def _add_numeric_entry_row(
        self,
        label: str,
        y: int,
        width: int,
        default: str,
        object_id: str,
    ) -> typing.Tuple[int, pygame_gui.elements.UITextEntryLine]:
        row_h = self._sy(_ROW_H)
        pad = self._sx(_PAD)
        lbl_w = self._sx(180)
        entry_w = self._sx(100)

        lbl = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(pad, y, lbl_w, row_h),
            text=label,
            manager=self.manager,
            container=self._scrollable,
        )
        self._stage_elements.append(lbl)

        entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(pad + lbl_w, y, entry_w, row_h),
            manager=self.manager,
            container=self._scrollable,
            object_id=object_id,
        )
        entry.set_text(default)
        entry.set_allowed_characters("numbers")
        self._stage_elements.append(entry)

        return y + row_h + self._sy(4), entry

    # ------------------------------------------------------------------
    # Bottom Action Bar
    # ------------------------------------------------------------------
    def _build_action_bar(self, main_h: int, btn_bar_h: int) -> None:
        btn_h = self._sy(_BTN_H)
        btn_y = main_h + (btn_bar_h - btn_h) // 2

        if self._stage == 1:
            btn_w_next = self._sx(220)
            btn_w_cancel = self._sx(_BTN_W)
            gap = self._sx(_PAD * 2)
            total_w = btn_w_cancel + gap + btn_w_next
            start_x = (self._content_w - total_w) // 2

            self.cancel_button = pygame_gui.elements.UIButton(
                relative_rect=pygame.Rect(start_x, btn_y, btn_w_cancel, btn_h),
                text="Cancel",
                manager=self.manager,
                container=self.window,
                object_id="#wizard_cancel_button",
            )
            self._stage_elements.append(self.cancel_button)

            self.next_button = pygame_gui.elements.UIButton(
                relative_rect=pygame.Rect(start_x + btn_w_cancel + gap, btn_y, btn_w_next, btn_h),
                text="Next: Players & Economy ➔",
                manager=self.manager,
                container=self.window,
                object_id="#wizard_next_button",
            )
            self._stage_elements.append(self.next_button)

            # Assign start_button to next_button for backward compatibility in tests
            self.start_button = self.next_button
            self.back_button = None

        else:
            btn_w_back = self._sx(_BTN_W)
            btn_w_cancel = self._sx(_BTN_W)
            btn_w_start = self._sx(_BTN_W)
            gap = self._sx(_PAD * 2)
            total_w = btn_w_back + gap + btn_w_cancel + gap + btn_w_start
            start_x = (self._content_w - total_w) // 2

            self.back_button = pygame_gui.elements.UIButton(
                relative_rect=pygame.Rect(start_x, btn_y, btn_w_back, btn_h),
                text="◀ Back to Map",
                manager=self.manager,
                container=self.window,
                object_id="#wizard_back_button",
            )
            self._stage_elements.append(self.back_button)

            self.cancel_button = pygame_gui.elements.UIButton(
                relative_rect=pygame.Rect(start_x + btn_w_back + gap, btn_y, btn_w_cancel, btn_h),
                text="Cancel",
                manager=self.manager,
                container=self.window,
                object_id="#wizard_cancel_button",
            )
            self._stage_elements.append(self.cancel_button)

            self.start_button = pygame_gui.elements.UIButton(
                relative_rect=pygame.Rect(start_x + btn_w_back + gap + btn_w_cancel + gap, btn_y, btn_w_start, btn_h),
                text="Start Game",
                manager=self.manager,
                container=self.window,
                object_id="#wizard_start_button",
            )
            self._stage_elements.append(self.start_button)
            self.next_button = None

    # ------------------------------------------------------------------
    # Stage Navigation & Full Rebuild
    # ------------------------------------------------------------------
    def go_to_stage(self, stage: int) -> None:
        """Transitions the wizard to the given stage (1 or 2)."""
        if stage == self._stage:
            return
        snap = self._snapshot()
        self._stage = stage
        self._full_rebuild(snap)

    def _adjust_player_count(self, delta: int) -> None:
        new_count = max(_MIN_PLAYERS, min(_MAX_PLAYERS, self._num_players + delta))
        if new_count == self._num_players:
            return
        snap = self._snapshot()
        self._num_players = new_count
        snap["num_players"] = new_count
        self._full_rebuild(snap)

    def _full_rebuild(self, snap: typing.Optional[dict] = None) -> None:
        """Cleans up dynamic stage elements and recreates UI."""
        if snap is None:
            snap = self._snapshot()

        for elem in self._stage_elements:
            if elem and hasattr(elem, "alive") and elem.alive():
                elem.kill()
        self._stage_elements = []

        self._preview_panel = None
        self._preview_hint_label = None
        self._galaxy_stats_label = None
        self._generate_map_btn = None
        self._scrollable = None
        self._spawn_profile_button = None
        self._home_mode_button = None
        self._player_minus_btn = None
        self._player_plus_btn = None
        self._player_count_label = None
        self.back_button = None
        self.cancel_button = None
        self.next_button = None
        self.start_button = None

        self._player_name_entries = []
        self._player_color_prev_btns = []
        self._player_color_next_btns = []
        self._player_color_swatches = []
        self._player_type_buttons = []
        self._player_team_buttons = []
        self._player_home_buttons = []
        self._player_home_labels = []
        self._player_select_labels = []
        self._player_home_prev_btns = []
        self._player_home_next_btns = []

        self._build_ui()
        self._restore_snapshot(snap)

    # ------------------------------------------------------------------
    # Snapshot / Restore
    # ------------------------------------------------------------------
    def _snapshot(self) -> dict:
        """Captures widget values into state variables and returns snapshot dict."""
        if self._stage == 1:
            if self._num_systems_slider:
                self._num_systems = int(self._num_systems_slider.get_current_value())
            if self._sys_radius_min_slider:
                self._sys_radius_min = int(self._sys_radius_min_slider.get_current_value())
            if self._sys_radius_max_slider:
                self._sys_radius_max = int(self._sys_radius_max_slider.get_current_value())
            if self._wormhole_density_slider:
                self._wormhole_density = int(self._wormhole_density_slider.get_current_value())
            if self._min_dist_slider:
                self._min_dist = int(self._min_dist_slider.get_current_value())
            if self._max_dist_slider:
                self._max_dist = int(self._max_dist_slider.get_current_value())
        elif self._stage == 2:
            for i, entry in enumerate(self._player_name_entries):
                if i < len(self._player_names):
                    self._player_names[i] = entry.get_text().strip() or f"Player {i + 1}"
            if self._credits_entry:
                self._credits_str = self._credits_entry.get_text()
            if self._metal_entry:
                self._metal_str = self._metal_entry.get_text()
            if self._crystal_entry:
                self._crystal_str = self._crystal_entry.get_text()
            if self._population_entry:
                self._population_str = self._population_entry.get_text()

        return {
            "stage": self._stage,
            "num_players": self._num_players,
            "spawn_profile": self._spawn_profile.value,
            "player_names": list(self._player_names),
            "player_colors": [PLAYER_COLOR_PALETTE[idx][0] for idx in self._player_color_indices],
            "player_controllers": [c.value for c in self._player_controllers],
            "player_ai_reasoning_efforts": list(self._player_ai_reasoning_efforts),
            "player_teams": list(self._player_teams),
            "home_system_mode": self._home_system_mode,
            "player_home_systems": list(self._player_home_systems),
            "num_systems": self._num_systems,
            "radius_min": self._sys_radius_min,
            "radius_max": self._sys_radius_max,
            "wormhole_density": self._wormhole_density,
            "min_dist": self._min_dist,
            "max_dist": self._max_dist,
            "credits": self._credits_str,
            "metal": self._metal_str,
            "crystal": self._crystal_str,
            "population": self._population_str,
        }

    def _restore_snapshot(self, snap: dict) -> None:
        """Restores state and widget values from snapshot dict."""
        if "spawn_profile" in snap:
            self._spawn_profile = normalize_spawn_profile(snap["spawn_profile"])
            if self._spawn_profile_button:
                self._spawn_profile_button.set_text(self._spawn_profile.display_name)

        if "home_system_mode" in snap:
            self._home_system_mode = snap["home_system_mode"]
            if self._home_mode_button:
                mode_text = "Mode: Random" if self._home_system_mode == "random" else "Mode: Specified"
                self._home_mode_button.set_text(mode_text)

        player_names = snap.get("player_names", [])
        player_colors = snap.get("player_colors", [])
        player_controllers = snap.get("player_controllers", [])
        player_efforts = snap.get("player_ai_reasoning_efforts", [])
        player_teams = snap.get("player_teams", [])
        player_home_systems = snap.get("player_home_systems", [])

        for i, entry in enumerate(self._player_name_entries):
            if i < len(player_names):
                entry.set_text(player_names[i])
        for i in range(len(self._player_color_indices)):
            if i < len(player_colors):
                saved_name = player_colors[i]
                found_idx = next((j for j, (n, _) in enumerate(PLAYER_COLOR_PALETTE) if n == saved_name), None)
                if found_idx is not None:
                    self._player_color_indices[i] = found_idx
        for i, raw_c in enumerate(player_controllers):
            if i < len(self._player_controllers):
                controller = PlayerController(raw_c)
                self._player_controllers[i] = controller
                effort = player_efforts[i] if i < len(player_efforts) else "medium"
                self._player_ai_reasoning_efforts[i] = effort
                if i < len(self._player_type_buttons) and self._player_type_buttons[i]:
                    self._player_type_buttons[i].set_text(self._player_type_label(controller, effort))
        for i, team_num in enumerate(player_teams):
            if i < len(self._player_teams):
                self._player_teams[i] = team_num
                if i < len(self._player_team_buttons) and self._player_team_buttons[i]:
                    self._player_team_buttons[i].set_text(f"Team {team_num}")
        for i, sys_name in enumerate(player_home_systems):
            if i < len(self._player_home_systems):
                self._player_home_systems[i] = sys_name
                if i < len(self._player_home_buttons) and self._player_home_buttons[i]:
                    disp = "Random (Auto)" if self._home_system_mode == "random" else (sys_name or "Random")
                    self._player_home_buttons[i].set_text(disp)

        def _restore_slider(slider, val):
            if slider and val is not None:
                slider.set_current_value(val)

        _restore_slider(self._num_systems_slider, snap.get("num_systems"))
        _restore_slider(self._sys_radius_min_slider, snap.get("radius_min"))
        _restore_slider(self._sys_radius_max_slider, snap.get("radius_max"))
        _restore_slider(self._wormhole_density_slider, snap.get("wormhole_density"))
        _restore_slider(self._min_dist_slider, snap.get("min_dist"))
        _restore_slider(self._max_dist_slider, snap.get("max_dist"))

        if self._credits_entry and snap.get("credits"):
            self._credits_entry.set_text(str(snap["credits"]))
        if self._metal_entry and snap.get("metal"):
            self._metal_entry.set_text(str(snap["metal"]))
        if self._crystal_entry and snap.get("crystal"):
            self._crystal_entry.set_text(str(snap["crystal"]))
        if self._population_entry and snap.get("population"):
            self._population_entry.set_text(str(snap["population"]))

        if self._stage == 2:
            self._update_home_assignment_ui()

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def has_duplicate_colors(self) -> bool:
        active_indices = self._player_color_indices[:self._num_players]
        return len(set(active_indices)) < len(active_indices)

    def get_map_validation_errors(self) -> typing.List[str]:
        errors: typing.List[str] = []
        radius_min = int(self._sys_radius_min_slider.get_current_value()) if self._sys_radius_min_slider else self._sys_radius_min
        radius_max = int(self._sys_radius_max_slider.get_current_value()) if self._sys_radius_max_slider else self._sys_radius_max
        if radius_min > radius_max:
            errors.append(
                f"Min System Radius ({radius_min}) cannot be greater than Max System Radius ({radius_max})."
            )

        min_d = float(int(self._min_dist_slider.get_current_value())) if self._min_dist_slider else float(self._min_dist)
        max_d = float(int(self._max_dist_slider.get_current_value())) if self._max_dist_slider else float(self._max_dist)
        if min_d >= max_d:
            errors.append(
                f"Min System Distance ({int(min_d)}) must be strictly less than Max System Distance ({int(max_d)})."
            )
        return errors

    def get_validation_errors(self) -> typing.List[str]:
        errors: typing.List[str] = []
        if self._stage == 1:
            return self.get_map_validation_errors()

        if self.has_duplicate_colors():
            errors.append("Each player must be assigned a unique color before starting the game.")

        active_teams = set(self._player_teams[:self._num_players])
        if self._num_players >= 2 and len(active_teams) < 2:
            errors.append("Players must be grouped into at least two different teams.")

        # If in stage 2, also check map constraints
        errors.extend(self.get_map_validation_errors())

        # Validate home systems in specified mode
        if self._home_system_mode == "specified" and self._generated_galaxy:
            avail = set(self._generated_galaxy.systems.keys())
            for i in range(self._num_players):
                sys_val = self._player_home_systems[i]
                if sys_val and sys_val.lower() != "random" and sys_val not in avail:
                    errors.append(f"Home system '{sys_val}' for player {i + 1} does not exist in the galaxy.")

        return errors

    # ------------------------------------------------------------------
    # Event Processing
    # ------------------------------------------------------------------
    def process_event(self, event: pygame.event.Event) -> typing.Optional[dict]:
        """Processes pygame events; returns an action dict or None."""
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            element = event.ui_element

            # Action bar buttons
            if element is self.cancel_button:
                return {"action": "cancel_new_game_wizard"}

            if self._stage == 1 and (element is self.next_button or element is self.start_button):
                errs = self.get_map_validation_errors()
                if errs:
                    return {
                        "action": "wizard_settings_error",
                        "message": "\n".join(errs),
                        "title": "Invalid Game Settings",
                    }
                self.go_to_stage(2)
                return None

            if self._stage == 2 and element is self.back_button:
                self.go_to_stage(1)
                return None

            if self._stage == 2 and element is self.start_button:
                errs = self.get_validation_errors()
                if errs:
                    if len(errs) == 1 and self.has_duplicate_colors():
                        return {
                            "action": "duplicate_player_colors_warning",
                            "message": errs[0],
                        }
                    return {
                        "action": "wizard_settings_error",
                        "message": "\n".join(errs),
                        "title": "Invalid Game Settings",
                    }
                return self._build_start_action()

            # Stage 1: Generate Map
            if element is self._generate_map_btn:
                errs = self.get_map_validation_errors()
                if errs:
                    return {
                        "action": "wizard_settings_error",
                        "message": "\n".join(errs),
                        "title": "Invalid Game Settings",
                    }
                self._snapshot()
                self._generate_map()
                return None

            # Stage 2: Spawn profile & Home mode
            if element is self._spawn_profile_button:
                self._cycle_spawn_profile()
                return None

            if element is self._home_mode_button:
                self._cycle_home_mode()
                return None

            # Stage 2: Player count buttons
            if element is self._player_minus_btn:
                self._adjust_player_count(-1)
                return None
            if element is self._player_plus_btn:
                self._adjust_player_count(+1)
                return None

            # Stage 2: Color cycle buttons
            for i, btn in enumerate(self._player_color_prev_btns):
                if element is btn:
                    self._cycle_player_color(i, -1)
                    return None
            for i, btn in enumerate(self._player_color_next_btns):
                if element is btn:
                    self._cycle_player_color(i, +1)
                    return None

            # Stage 2: Controller type buttons
            for i, btn in enumerate(self._player_type_buttons):
                if element is btn:
                    controller = self._player_controllers[i]
                    effort = self._player_ai_reasoning_efforts[i]
                    if controller == PlayerController.HUMAN:
                        controller = PlayerController.CODEX
                    elif controller == PlayerController.CODEX:
                        controller, effort = PlayerController.OPENAI, "medium"
                    elif effort == "medium":
                        effort = "high"
                    elif effort == "high":
                        effort = "low"
                    else:
                        controller, effort = PlayerController.HUMAN, "medium"
                    self._player_controllers[i] = controller
                    self._player_ai_reasoning_efforts[i] = effort
                    btn.set_text(self._player_type_label(controller, effort))
                    return None

            # Stage 2: Team buttons
            for i, btn in enumerate(self._player_team_buttons):
                if element is btn:
                    self._cycle_player_team(i, +1)
                    return None

            # Stage 2: Home system buttons
            for i, btn in enumerate(self._player_home_prev_btns):
                if element is btn:
                    self._cycle_player_home_system(i, -1)
                    return None
            for i, btn in enumerate(self._player_home_next_btns):
                if element is btn:
                    self._cycle_player_home_system(i, +1)
                    return None
            for i, btn in enumerate(self._player_home_buttons):
                if element is btn:
                    self._selected_player_index_for_home = i
                    if self._home_system_mode != "specified":
                        self._home_system_mode = "specified"
                        if self._home_mode_button:
                            self._home_mode_button.set_text("Mode: Specified")
                    self._update_home_assignment_ui()
                    return None

        elif event.type == pygame_gui.UI_HORIZONTAL_SLIDER_MOVED:
            self._update_slider_labels()

        elif event.type == pygame.MOUSEMOTION:
            preview_rect = self._get_preview_screen_rect()
            if preview_rect.collidepoint(event.pos):
                self._preview_hovered_system = get_system_at_preview_point(
                    event.pos, self._generated_galaxy, preview_rect, scale=self.scale_x
                )
            else:
                self._preview_hovered_system = None

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            preview_rect = self._get_preview_screen_rect()
            if preview_rect.collidepoint(event.pos):
                clicked_sys = get_system_at_preview_point(
                    event.pos, self._generated_galaxy, preview_rect, scale=self.scale_x
                )
                if clicked_sys:
                    if self._stage == 2:
                        idx = self._selected_player_index_for_home
                        if idx < len(self._player_home_systems):
                            self._home_system_mode = "specified"
                            if self._home_mode_button:
                                self._home_mode_button.set_text("Mode: Specified")
                            self._player_home_systems[idx] = clicked_sys
                            self._preview_selected_system = clicked_sys
                            # Advance focus to next player for easy consecutive setup
                            next_idx = (idx + 1) % self._num_players
                            self._selected_player_index_for_home = next_idx
                            self._update_home_assignment_ui()
                    elif self._stage == 1:
                        self._preview_selected_system = clicked_sys
            elif self._stage == 2:
                for idx, lbl in enumerate(self._player_select_labels):
                    if lbl and lbl.alive() and lbl.get_abs_rect().collidepoint(event.pos):
                        self._selected_player_index_for_home = idx
                        if self._home_system_mode != "specified":
                            self._home_system_mode = "specified"
                            if self._home_mode_button:
                                self._home_mode_button.set_text("Mode: Specified")
                        self._update_home_assignment_ui()
                        break

        return None

    def _update_slider_labels(self) -> None:
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
    # Drawing (Map Preview + Player Color Swatches)
    # ------------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        """Renders the custom map preview and color swatches onto the surface."""
        if not self.window.alive() or not self.window.visible:
            return

        # Check for window blockers layered on top
        blockers: typing.List[pygame.Rect] = []
        if self.manager:
            wizard_found = False
            for sprite in self.manager.get_sprite_group().sprites():
                if sprite is self.window:
                    wizard_found = True
                    continue
                if (
                    wizard_found
                    and isinstance(sprite, pygame_gui.elements.UIWindow)
                    and sprite.alive()
                    and sprite.visible
                ):
                    blockers.append(sprite.get_abs_rect())

        # 1. Draw Map Preview
        preview_rect = self._get_preview_screen_rect()
        if preview_rect.width > 0 and preview_rect.height > 0:
            visible_rects = [preview_rect]
            for b in blockers:
                next_rects = []
                for r in visible_rects:
                    next_rects.extend(_subtract_rect_from_blocker(r, b))
                visible_rects = next_rects
                if not visible_rects:
                    break

            if visible_rects:
                # Build home systems mapping for preview
                home_map: typing.Dict[str, typing.List[typing.Any]] = {}
                if self._stage == 2:
                    for i in range(self._num_players):
                        sys_val = self._player_home_systems[i] if i < len(self._player_home_systems) else None
                        if self._home_system_mode == "specified" and sys_val and sys_val.lower() != "random":
                            color_rgb = PLAYER_COLOR_PALETTE[self._player_color_indices[i]][1]
                            mark = type("PlayerMark", (), {"color": color_rgb})()
                            home_map.setdefault(sys_val, []).append(mark)

                draw_galaxy_preview(
                    surface,
                    self._generated_galaxy,
                    preview_rect,
                    home_systems_map=home_map,
                    hovered_system_name=self._preview_hovered_system,
                    selected_system_name=self._preview_selected_system,
                    scale=self.scale_x,
                )

        # 2. Draw Color Swatches (in Stage 2)
        if self._stage == 2:
            self.draw_swatches(surface)

    def draw_swatches(self, surface: pygame.Surface) -> None:
        """Draws player color squares on top of swatch panels."""
        if not self._scrollable or not self._scrollable.alive():
            return

        blockers: typing.List[pygame.Rect] = []
        if self.manager:
            wizard_found = False
            for sprite in self.manager.get_sprite_group().sprites():
                if sprite is self.window:
                    wizard_found = True
                    continue
                if (
                    wizard_found
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

    # ------------------------------------------------------------------
    # Build GameSettings & Action Output
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
        """Builds GameSettings with pregenerated galaxy and player configurations."""
        self._snapshot()

        player_configs: typing.List[PlayerConfig] = []
        for i in range(self._num_players):
            name = (
                self._player_names[i]
                if i < len(self._player_names)
                else f"Player {i + 1}"
            ) or f"Player {i + 1}"

            color = PLAYER_COLOR_PALETTE[self._player_color_indices[i]][1]
            controller = self._player_controllers[i]
            effort = self._player_ai_reasoning_efforts[i]
            team_id = self._player_teams[i]

            home_sys = None
            if self._home_system_mode == "specified" and i < len(self._player_home_systems):
                val = self._player_home_systems[i]
                if val and val.lower() != "random":
                    home_sys = val

            player_configs.append(PlayerConfig(
                name=name,
                color=color,
                controller=controller,
                team_id=team_id,
                ai_reasoning_effort=effort,
                home_system_name=home_sys,
            ))

        credits_ = self._safe_float(self._credits_str, 20000.0)
        metal_ = self._safe_float(self._metal_str, 10000.0)
        crystal_ = self._safe_float(self._crystal_str, 10000.0)
        pop_ = self._safe_int(self._population_str, 50)

        settings = GameSettings(
            player_configs=player_configs,
            num_systems=self._num_systems,
            min_system_distance=float(self._min_dist),
            max_system_distance=float(self._max_dist),
            wormhole_density=self._wormhole_density / 100.0,
            system_radius_min=self._sys_radius_min,
            system_radius_max=self._sys_radius_max,
            starting_credits=credits_,
            starting_metal=metal_,
            starting_crystal=crystal_,
            starting_population=pop_,
            spawn_profile=self._spawn_profile,
            pregenerated_galaxy=self._generated_galaxy,
            home_system_assignment_mode=self._home_system_mode,
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
