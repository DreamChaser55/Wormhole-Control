"""HUD bar layout and updating functions."""
import logging
import typing
import pygame
import pygame_gui
from pygame import Color

from constants import TOP_BAR_HEIGHT, INFO_BOX_WIDTH

from .theme_loader import create_player_scifi_theme_colors

if typing.TYPE_CHECKING:
    from entities import Player

logger = logging.getLogger(__name__)



def setup_game_ui(gui) -> None:
    """Initializes the Pygame GUI elements for the main game interface.

    Args:
        gui: Target GUI_Handler instance.
    """
    gui.clear_and_reset()

    padding = int(5 * gui.scale_y)

    # --- Side Bar Info Panel (Spans full window height) ---
    side_bar_info_panel_x = gui.screen_res.x - INFO_BOX_WIDTH
    side_bar_info_panel_y = 0
    side_bar_info_panel_h = gui.screen_res.y

    side_bar_info_panel_rect = pygame.Rect(
        side_bar_info_panel_x,
        side_bar_info_panel_y,
        INFO_BOX_WIDTH,
        side_bar_info_panel_h
    )

    gui.side_bar_info_panel = pygame_gui.elements.UIPanel(
        relative_rect=side_bar_info_panel_rect,
        starting_height=1,
        manager=gui.manager,
        object_id='#side_bar_info_panel'
    )

    # --- Top Bar Panel (Spans to left edge of sidebar) ---
    top_panel_width = side_bar_info_panel_x
    top_panel_rect = pygame.Rect(0, 0, top_panel_width, TOP_BAR_HEIGHT)
    gui.top_bar_panel = pygame_gui.elements.UIPanel(
        relative_rect=top_panel_rect,
        starting_height=1,
        manager=gui.manager,
        object_id='#top_bar'
    )

    # --- Left Section of Top Bar ---
    back_button_width = int(60 * gui.scale_x)
    back_button_rect = pygame.Rect(padding, padding, back_button_width, -1)
    gui.back_button = pygame_gui.elements.UIButton(
        relative_rect=back_button_rect,
        text='Back',
        manager=gui.manager,
        container=gui.top_bar_panel,
        visible=False,
        object_id='#back_button'
    )

    view_label_width = int(350 * gui.scale_x)
    view_label_rect = pygame.Rect(back_button_rect.right + padding, padding, view_label_width, -1)
    gui.view_mode_label = pygame_gui.elements.UILabel(
        relative_rect=view_label_rect,
        text=f"View: {gui.game_instance.view_mode.capitalize()}",
        manager=gui.manager,
        container=gui.top_bar_panel,
        object_id='#view_label'
    )
    gui.view_mode_label.text_horiz_alignment = 'left'

    # --- Right Section of Top Bar ---
    end_turn_button_width = int(100 * gui.scale_x)
    end_turn_button_rect = pygame.Rect(
        top_panel_width - end_turn_button_width - padding,
        padding,
        end_turn_button_width,
        -1
    )
    gui.end_turn_button = pygame_gui.elements.UIButton(
        relative_rect=end_turn_button_rect,
        text='End Turn',
        manager=gui.manager,
        container=gui.top_bar_panel,
        object_id='#end_turn_button'
    )

    indicator_size = int(15 * min(gui.scale_x, gui.scale_y))
    turn_label_width = int(320 * gui.scale_x)
    turn_label_right = end_turn_button_rect.left - padding
    turn_label_left = max(view_label_rect.right + indicator_size + 2 * padding, turn_label_right - turn_label_width)
    indicator_x = turn_label_left - indicator_size - padding
    indicator_y = (TOP_BAR_HEIGHT - indicator_size) // 2

    indicator_rect = pygame.Rect(
        indicator_x,
        indicator_y,
        indicator_size,
        indicator_size
    )
    gui.player_color_indicator = pygame_gui.elements.UIPanel(
        relative_rect=indicator_rect,
        manager=gui.manager,
        container=gui.top_bar_panel,
        object_id='#player_color_indicator'
    )

    actual_turn_width = end_turn_button_rect.left - padding - turn_label_left
    turn_label_rect = pygame.Rect(
        turn_label_left,
        padding,
        actual_turn_width,
        -1
    )
    gui.player_turn_label = pygame_gui.elements.UITextBox(
        html_text="",
        relative_rect=turn_label_rect,
        manager=gui.manager,
        container=gui.top_bar_panel,
        object_id='#turn_label'
    )

    # --- Expanded Bottom Bar Panel (Spans to left edge of sidebar) ---
    bottom_panel_width = side_bar_info_panel_x
    bottom_panel_rect = pygame.Rect(
        0,
        gui.screen_res.y - TOP_BAR_HEIGHT,
        bottom_panel_width,
        TOP_BAR_HEIGHT
    )
    gui.bottom_bar_panel = pygame_gui.elements.UIPanel(
        relative_rect=bottom_panel_rect,
        starting_height=1,
        manager=gui.manager,
        object_id='#bottom_bar'
    )

    # --- Action Buttons in Bottom Bar (Left Aligned) ---
    menu_button_width = int(60 * gui.scale_x)
    menu_button_rect = pygame.Rect(padding, padding, menu_button_width, -1)
    gui.menu_button = pygame_gui.elements.UIButton(
        relative_rect=menu_button_rect,
        text='Menu',
        manager=gui.manager,
        container=gui.bottom_bar_panel,
        object_id='#menu_button'
    )

    comms_button_width = int(95 * gui.scale_x)
    comms_button_rect = pygame.Rect(menu_button_rect.right + padding, padding, comms_button_width, -1)
    gui.comms_button = pygame_gui.elements.UIButton(
        relative_rect=comms_button_rect,
        text='Comms',
        manager=gui.manager,
        container=gui.bottom_bar_panel,
        object_id='#comms_button'
    )

    # --- Resource Readouts in Bottom Bar (Spacious Layout) ---
    resource_start_x = comms_button_rect.right + int(25 * gui.scale_x)
    resource_spacing = int(20 * gui.scale_x)
    credits_label_width = int(220 * gui.scale_x)
    metal_label_width = int(180 * gui.scale_x)
    crystal_label_width = int(180 * gui.scale_x)

    credits_x = resource_start_x
    gui.credits_label = pygame_gui.elements.UILabel(
        relative_rect=pygame.Rect(credits_x, padding, credits_label_width, -1),
        text="Credits: 0",
        manager=gui.manager,
        container=gui.bottom_bar_panel,
        object_id='#resource_label'
    )
    gui.credits_label.text_horiz_alignment = 'left'
    gui.credits_label.tool_tip_delay = 0.3
    gui.credits_label.tool_tip_wrap_width = int(200 * gui.scale_x)

    metal_x = credits_x + credits_label_width + resource_spacing
    gui.metal_label = pygame_gui.elements.UILabel(
        relative_rect=pygame.Rect(metal_x, padding, metal_label_width, -1),
        text="Metal: 0",
        manager=gui.manager,
        container=gui.bottom_bar_panel,
        object_id='#resource_label'
    )
    gui.metal_label.text_horiz_alignment = 'left'

    crystal_x = metal_x + metal_label_width + resource_spacing
    gui.crystal_label = pygame_gui.elements.UILabel(
        relative_rect=pygame.Rect(crystal_x, padding, crystal_label_width, -1),
        text="Crystal: 0",
        manager=gui.manager,
        container=gui.bottom_bar_panel,
        object_id='#resource_label'
    )
    gui.crystal_label.text_horiz_alignment = 'left'

    # --- Galaxy Generation Rect ---
    galaxy_rect_x = 0
    galaxy_rect_y = TOP_BAR_HEIGHT
    galaxy_rect_width = side_bar_info_panel_x
    galaxy_rect_height = gui.screen_res.y - TOP_BAR_HEIGHT * 2
    gui.galaxy_generation_rect = pygame.Rect(galaxy_rect_x, galaxy_rect_y, galaxy_rect_width, galaxy_rect_height)

    gui.hide_all_panels()


def update_back_button_visibility(gui) -> None:
    """Toggles back button visibility depending on active view mode (hidden on galaxy view).

    Args:
        gui: Target GUI_Handler instance.
    """
    if gui.back_button:
        if gui.game_instance.view_mode in ['system', 'sector']:
            gui.back_button.show()
        else:
            gui.back_button.hide()


def update_view_mode_label(gui, text: str) -> None:
    """Updates header text label displaying current camera view mode.

    Args:
        gui: Target GUI_Handler instance.
        text (str): Display string to set on the view mode label.
    """
    if gui.view_mode_label:
        gui.view_mode_label.set_text(text)
    gui.update_back_button_visibility()


def update_turn_label(gui, text: str) -> None:
    """Updates header text label displaying current turn number and active player name.

    Args:
        gui: Target GUI_Handler instance.
        text (str): HTML-formatted turn display string.
    """
    if gui.player_turn_label:
        gui.player_turn_label.set_text(text)


def update_player_color_indicator(gui, color: Color) -> None:
    """Sets background color of player indicator badge on top HUD bar.

    Args:
        gui: Target GUI_Handler instance.
        color (Color): Pygame Color representing active player.
    """
    if gui.player_color_indicator:
        try:
            valid_color = Color(color)
            gui.player_color_indicator.background_colour = valid_color
            gui.player_color_indicator.rebuild()
        except (ValueError, TypeError) as e:
            logger.debug(f"Error setting player indicator color ({color}): {e}")


def update_hud_panel_colors(gui, player_color: Color) -> None:
    """Dynamically updates UI panels to semi-transparent sci-fi colors tinted by active player color.

    Args:
        gui: Target GUI_Handler instance.
        player_color (Color): Active player's color.
    """
    bg_color, border_color = create_player_scifi_theme_colors(player_color)
    gui.current_player_bg_color = bg_color
    gui.current_player_border_color = border_color

    unit_editor_panel = (
        gui.unit_editor_window._panel
        if (gui.unit_editor_window and getattr(gui.unit_editor_window, '_panel', None))
        else None
    )

    panels = [
        getattr(gui, 'top_bar_panel', None),
        getattr(gui, 'bottom_bar_panel', None),
        getattr(gui, 'side_bar_info_panel', None),
        getattr(gui, 'ingame_menu_panel', None),
        getattr(gui, 'context_menu_panel', None),
        getattr(gui, 'main_menu_panel', None),
        getattr(gui, 'about_panel', None),
        unit_editor_panel
    ]

    seen_panels = set()
    for panel in panels:
        if panel is not None and panel not in seen_panels:
            seen_panels.add(panel)
            try:
                panel.background_colour = bg_color
                if hasattr(panel, 'border_colour'):
                    panel.border_colour = border_color
                panel.rebuild()
            except Exception as e:
                logger.debug(f"Error updating panel color for {panel}: {e}")



def update_resource_display(gui, player: 'Player') -> None:
    """Updates credits, metal, and crystal resource readouts and income tooltips for a player.

    Args:
        gui: Target GUI_Handler instance.
        player (Player): Active player entity whose resources to render.
    """
    if gui.credits_label:
        gui.credits_label.set_text(f"Credits: {player.credits:.0f}")

        total_income = gui.game_instance.get_player_income(player)
        total_upkeep = gui.game_instance.get_player_upkeep(player)
        net_change = total_income - total_upkeep
        sign = "+" if net_change >= 0 else ""
        net_color = "#00FF00" if net_change >= 0 else "#FF4040"

        tooltip_text = (
            f"Income: <font color='#00FF00'>+{total_income:.1f}</font><br>"
            f"Upkeep: <font color='#FF4040'>-{total_upkeep:.1f}</font><br>"
            f"Net: <font color='{net_color}'>{sign}{net_change:.1f}</font>"
        )
        gui.credits_label.tool_tip_text = tooltip_text
        if gui.credits_label.tool_tip is not None:
            gui.credits_label.tool_tip.text_block.set_text(tooltip_text)
    if gui.metal_label:
        gui.metal_label.set_text(f"Metal: {player.metal:.0f}")
    if gui.crystal_label:
        gui.crystal_label.set_text(f"Crystal: {player.crystal:.0f}")


def update_comms_button(gui) -> None:
    """Updates the comms button text and badge indicator if unread messages are waiting.

    Args:
        gui: Target GUI_Handler instance.
    """
    if not gui.comms_button:
        return
    current_player = getattr(gui.game_instance, 'current_player', None)
    if not current_player:
        return
    unread = gui.game_instance.get_unread_messages_for_player(current_player.id)
    if unread:
        gui.comms_button.set_text(f"Comms ({len(unread)})")
    else:
        gui.comms_button.set_text("Comms")
