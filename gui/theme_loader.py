"""Theme loader and UIManager construction for GUI."""
import json
import logging
import pygame
import pygame_gui

from constants import TEXT_SCALE
from utils import resource_path

logger = logging.getLogger(__name__)


def build_ui_manager(screen_res) -> pygame_gui.UIManager:
    """Builds a UIManager using a TEXT_SCALE-scaled copy of theme.json with preloaded fonts.

    Args:
        screen_res: Screen resolution vector exposing .to_tuple().

    Returns:
        pygame_gui.UIManager: Configured manager, falling back to the default theme on error.
    """
    try:
        theme_path = resource_path('theme.json')
        
        # Dynamically scale theme text sizes
        scaled_theme_path = resource_path('theme_scaled.json')
        try:
            with open(theme_path, 'r') as f:
                theme_data = json.load(f)
            
            # Scale fonts and resolve font file paths
            fonts_data = theme_data.get('fonts', {})
            if isinstance(fonts_data, list):
                for font in fonts_data:
                    if 'size' in font:
                        font['size'] = str(max(1, int(int(font['size']) * TEXT_SCALE)))
                    if 'point_size' in font:
                        font['point_size'] = max(1, int(int(font['point_size']) * TEXT_SCALE))
            elif isinstance(fonts_data, dict):
                for font_name, font_info in fonts_data.items():
                    if isinstance(font_info, dict):
                        for path_key in ['regular_path', 'bold_path', 'italic_path', 'bold_italic_path']:
                            if path_key in font_info:
                                font_info[path_key] = resource_path(font_info[path_key])
                        if 'size' in font_info:
                            font_info['size'] = str(max(1, int(int(font_info['size']) * TEXT_SCALE)))
                        if 'point_size' in font_info:
                            font_info['point_size'] = max(1, int(int(font_info['point_size']) * TEXT_SCALE))
            
            # Scale individual element font sizes
            for key, value in theme_data.items():
                if isinstance(value, dict) and 'font' in value and 'size' in value['font']:
                    value['font']['size'] = str(max(1, int(int(value['font']['size']) * TEXT_SCALE)))

            # Scale drop-down menu options list item height
            dropdown_list_theme_id = "drop_down_menu.#drop_down_options_list"
            if dropdown_list_theme_id not in theme_data:
                theme_data[dropdown_list_theme_id] = {"misc": {}}
            elif "misc" not in theme_data[dropdown_list_theme_id]:
                theme_data[dropdown_list_theme_id]["misc"] = {}
            
            # Match the base height of 30 used for the dropdown button in game.py
            scaled_item_height = max(20, int(30 * TEXT_SCALE))
            theme_data[dropdown_list_theme_id]["misc"]["list_item_height"] = str(scaled_item_height)

            # Scale window title bar height for windows
            for window_theme_id in ["window", "#message_window", "message_window", "#new_game_wizard_window", "#load_game_window"]:
                if window_theme_id in theme_data and isinstance(theme_data[window_theme_id], dict) and "misc" in theme_data[window_theme_id]:
                    if "title_bar_height" in theme_data[window_theme_id]["misc"]:
                        orig_tb_height = int(theme_data[window_theme_id]["misc"]["title_bar_height"])
                        theme_data[window_theme_id]["misc"]["title_bar_height"] = str(max(24, int(orig_tb_height * TEXT_SCALE)))

            with open(scaled_theme_path, 'w') as f:
                json.dump(theme_data, f)
            
            theme_path_to_use = scaled_theme_path
        except Exception as e:
            logger.error(f"Error generating scaled theme: {e}")
            theme_path_to_use = theme_path
            
        manager = pygame_gui.UIManager(screen_res.to_tuple(), theme_path_to_use)
    except FileNotFoundError:
        logger.debug("Warning: theme.json not found. Using default UI theme.")
        manager = pygame_gui.UIManager(screen_res.to_tuple())
    except pygame.error as e:
        logger.debug(f"Pygame error initializing UIManager (maybe font issue?): {e}")
        manager = pygame_gui.UIManager(screen_res.to_tuple())

    # Programmatic preloading for problematic fonts
    if manager and manager.ui_theme and manager.ui_theme.get_font_dictionary():
        font_dict = manager.ui_theme.get_font_dictionary()
        
        # Preload DejaVu Sans fonts if registered
        if 'dejavu_sans' in font_dict.known_font_paths:
            for size, is_bold in [(15, False), (14, False), (14, True), (12, True), (12, False)]:
                scaled_size = max(1, int(size * TEXT_SCALE))
                f_id = font_dict.create_font_id(font_size=scaled_size, font_name='dejavu_sans', bold=is_bold, italic=False, antialiased=True)
                if not font_dict.check_font_preloaded(f_id):
                    font_dict.preload_font(font_size=scaled_size, font_name='dejavu_sans', bold=is_bold, italic=False, antialiased=True)

        # Preload Noto Emoji font if registered
        if 'noto_emoji' in font_dict.known_font_paths:
            noto_12_reg_id = font_dict.create_font_id(font_size=max(1, int(12 * TEXT_SCALE)), font_name='noto_emoji', bold=False, italic=False, antialiased=True)
            if not font_dict.check_font_preloaded(noto_12_reg_id):
                font_dict.preload_font(font_size=max(1, int(12 * TEXT_SCALE)), font_name='noto_emoji', bold=False, italic=False, antialiased=True)

    return manager


def create_player_scifi_theme_colors(player_color: typing.Union[pygame.Color, typing.Tuple[int, ...], str]) -> typing.Tuple[pygame.Color, pygame.Color]:
    """Calculates semi-transparent sci-fi background and border colors derived from a player's color.

    Args:
        player_color: Pygame Color, RGB tuple, or color string representing active player.

    Returns:
        Tuple[pygame.Color, pygame.Color]: (bg_color, border_color) where bg_color is semi-transparent
        dark slate tinted with player hue, and border_color is a sci-fi accent border.
    """
    try:
        col = pygame.Color(player_color)
    except (ValueError, TypeError):
        col = pygame.Color(255, 255, 255)

    # Base dark sci-fi slate (12, 18, 30) blended with 18% player color + semi-transparent alpha (200 / 255 ~78% opacity)
    bg_r = min(255, max(0, int(12 * 0.82 + col.r * 0.18)))
    bg_g = min(255, max(0, int(18 * 0.82 + col.g * 0.18)))
    bg_b = min(255, max(0, int(30 * 0.82 + col.b * 0.18)))
    bg_color = pygame.Color(bg_r, bg_g, bg_b, 200)

    # Border accent: Sci-fi slate border (50, 90, 140) blended with 50% player color + alpha 220
    border_r = min(255, max(0, int(50 * 0.5 + col.r * 0.5)))
    border_g = min(255, max(0, int(90 * 0.5 + col.g * 0.5)))
    border_b = min(255, max(0, int(140 * 0.5 + col.b * 0.5)))
    border_color = pygame.Color(border_r, border_g, border_b, 220)

    return bg_color, border_color

