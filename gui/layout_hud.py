"""HUD bar layout and updating functions."""
from display_config import display_config_for
import logging
import typing
import pygame
import pygame_gui
from pygame import Color



from .theme_loader import create_player_scifi_theme_colors

if typing.TYPE_CHECKING:
    from domain.players import Player

logger = logging.getLogger(__name__)



def setup_game_ui(gui) -> None:
    """Initializes the Pygame GUI elements for the main game interface.

    Args:
        gui: Target GUI_Handler instance.
    """
    gui.clear_and_reset()

    padding = int(5 * gui.scale_y)

    # --- Side Bar Info Panel (Spans full window height) ---
    side_bar_info_panel_x = gui.screen_res.x - display_config_for(gui).info_box_width
    side_bar_info_panel_y = 0
    side_bar_info_panel_h = gui.screen_res.y

    side_bar_info_panel_rect = pygame.Rect(
        side_bar_info_panel_x,
        side_bar_info_panel_y,
        display_config_for(gui).info_box_width,
        side_bar_info_panel_h
    )

    gui.side_bar_info_panel = pygame_gui.elements.UIPanel(
        relative_rect=side_bar_info_panel_rect,
        starting_height=1,
        manager=gui.manager,
        object_id='#side_bar_info_panel'
    )
    sidebar_area = gui.side_bar_info_panel.get_container().get_rect()
    gui.side_bar_scroll_container = pygame_gui.elements.UIScrollingContainer(
        relative_rect=pygame.Rect(0, 0, sidebar_area.width, sidebar_area.height),
        manager=gui.manager,
        container=gui.side_bar_info_panel,
        allow_scroll_x=False,
        object_id='#sidebar_scroll',
    )

    # --- Top Bar Panel (Spans to left edge of sidebar) ---
    top_panel_width = side_bar_info_panel_x
    top_panel_rect = pygame.Rect(0, 0, top_panel_width, display_config_for(gui).top_bar_height)
    gui.top_bar_panel = pygame_gui.elements.UIPanel(
        relative_rect=top_panel_rect,
        starting_height=1,
        manager=gui.manager,
        object_id='#top_bar'
    )

    # --- Left Section of Top Bar ---
    nav_button_width = int(90 * gui.scale_x)
    nav_button_rect = pygame.Rect(padding, padding, nav_button_width, -1)
    gui.back_button = pygame_gui.elements.UIButton(
        relative_rect=nav_button_rect,
        text='Back',
        manager=gui.manager,
        container=gui.top_bar_panel,
        visible=False,
        object_id='#back_button'
    )
    gui.reset_view_button = pygame_gui.elements.UIButton(
        relative_rect=nav_button_rect,
        text='Reset View',
        manager=gui.manager,
        container=gui.top_bar_panel,
        visible=False,
        object_id='#reset_view_button'
    )

    view_label_width = int(350 * gui.scale_x)
    view_label_rect = pygame.Rect(nav_button_rect.right + padding, padding, view_label_width, -1)
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
    indicator_y = (display_config_for(gui).top_bar_height - indicator_size) // 2

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
        gui.screen_res.y - display_config_for(gui).top_bar_height,
        bottom_panel_width,
        display_config_for(gui).top_bar_height
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

    unit_editor_button_width = int(120 * gui.scale_x)
    unit_editor_button_rect = pygame.Rect(comms_button_rect.right + padding, padding, unit_editor_button_width, -1)
    gui.unit_editor_button = pygame_gui.elements.UIButton(
        relative_rect=unit_editor_button_rect,
        text='Unit Editor',
        manager=gui.manager,
        container=gui.bottom_bar_panel,
        object_id='#unit_editor_button'
    )

    # --- Resource Readouts in Bottom Bar (Spacious Layout) ---
    resource_start_x = unit_editor_button_rect.right + int(20 * gui.scale_x)
    resource_spacing = int(15 * gui.scale_x)
    credits_label_width = int(165 * gui.scale_x)
    metal_label_width = int(145 * gui.scale_x)
    crystal_label_width = int(145 * gui.scale_x)
    population_label_width = int(200 * gui.scale_x)

    credits_x = resource_start_x
    gui.credits_label = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect(credits_x, padding, credits_label_width, -1),
        text="Credits: 0",
        manager=gui.manager,
        container=gui.bottom_bar_panel,
        object_id='#resource_label'
    )

    metal_x = credits_x + credits_label_width + resource_spacing
    gui.metal_label = pygame_gui.elements.UILabel(
        relative_rect=pygame.Rect(metal_x, padding, metal_label_width, -1),
        text="Metal: 0",
        manager=gui.manager,
        container=gui.bottom_bar_panel,
        object_id='#resource_label'
    )
    gui.metal_label.text_horiz_alignment = 'left'
    gui.metal_label.rebuild()

    crystal_x = metal_x + crystal_label_width + resource_spacing
    gui.crystal_label = pygame_gui.elements.UILabel(
        relative_rect=pygame.Rect(crystal_x, padding, crystal_label_width, -1),
        text="Crystal: 0",
        manager=gui.manager,
        container=gui.bottom_bar_panel,
        object_id='#resource_label'
    )
    gui.crystal_label.text_horiz_alignment = 'left'
    gui.crystal_label.rebuild()

    population_x = crystal_x + crystal_label_width + resource_spacing
    gui.population_label = pygame_gui.elements.UILabel(
        relative_rect=pygame.Rect(population_x, padding, population_label_width, -1),
        text="Population: 0",
        manager=gui.manager,
        container=gui.bottom_bar_panel,
        object_id='#resource_label'
    )
    gui.population_label.text_horiz_alignment = 'left'
    gui.population_label.rebuild()

    # --- Galaxy Generation Rect ---
    galaxy_rect_x = 0
    galaxy_rect_y = display_config_for(gui).top_bar_height
    galaxy_rect_width = side_bar_info_panel_x
    galaxy_rect_height = gui.screen_res.y - display_config_for(gui).top_bar_height * 2
    gui.galaxy_generation_rect = pygame.Rect(galaxy_rect_x, galaxy_rect_y, galaxy_rect_width, galaxy_rect_height)

    gui.hide_all_panels()


def update_back_button_visibility(gui) -> None:
    """Toggles top bar navigation button visibility depending on active view mode.

    Shows 'Reset View' in galaxy view and 'Back' in system and sector views.

    Args:
        gui: Target GUI_Handler instance.
    """
    view_mode = getattr(gui.game_instance, 'view_mode', None)
    if gui.back_button:
        should_show_back = view_mode in ('system', 'sector')
        if should_show_back and not gui.back_button.visible:
            gui.back_button.show()
        elif not should_show_back and gui.back_button.visible:
            gui.back_button.hide()
    reset_btn = getattr(gui, 'reset_view_button', None)
    if reset_btn:
        should_show_reset = view_mode == 'galaxy'
        if should_show_reset and not reset_btn.visible:
            reset_btn.show()
        elif not should_show_reset and reset_btn.visible:
            reset_btn.hide()


def update_view_mode_label(gui, text: str) -> None:
    """Updates header text label displaying current camera view mode.

    Args:
        gui: Target GUI_Handler instance.
        text (str): Display string to set on the view mode label.
    """
    if gui.view_mode_label and getattr(gui.view_mode_label, 'text', None) != text:
        gui.view_mode_label.set_text(text)
    gui.update_back_button_visibility()


def update_turn_label(gui, text: str) -> None:
    """Updates header text label displaying current turn number and active player name.

    Args:
        gui: Target GUI_Handler instance.
        text (str): HTML-formatted turn display string.
    """
    if gui.player_turn_label:
        if (
            getattr(gui, '_last_turn_label_text', None) == text
            and getattr(gui.player_turn_label, 'html_text', None) == text
        ):
            return
        gui.player_turn_label.set_text(text)
        gui._last_turn_label_text = text


def update_player_color_indicator(gui, color: Color) -> None:
    """Sets background color of player indicator badge on top HUD bar.

    Args:
        gui: Target GUI_Handler instance.
        color (Color): Pygame Color representing active player.
    """
    if gui.player_color_indicator:
        try:
            valid_color = Color(color)
            color_key = tuple(valid_color)
            if (
                getattr(gui, '_last_player_indicator_color', None) == color_key
                and getattr(gui.player_color_indicator, 'background_colour', None) == valid_color
            ):
                return
            gui.player_color_indicator.background_colour = valid_color
            gui.player_color_indicator.rebuild()
            gui._last_player_indicator_color = color_key
        except (ValueError, TypeError) as e:
            logger.debug(f"Error setting player indicator color ({color}): {e}")


def update_hud_panel_colors(gui, player_color: Color) -> None:
    """Dynamically updates UI panels to opaque sci-fi colors tinted by active player color.

    Args:
        gui: Target GUI_Handler instance.
        player_color (Color): Active player's color.
    """
    bg_color, border_color = create_player_scifi_theme_colors(player_color)
    gui.current_player_bg_color = bg_color
    gui.current_player_border_color = border_color
    theme_sig = (tuple(bg_color), tuple(border_color))

    unit_editor_panel = (
        gui.unit_editor_window._panel
        if (gui.unit_editor_window and getattr(gui.unit_editor_window, '_panel', None))
        else None
    )

    turn_briefing = getattr(gui, 'turn_briefing_window', None)
    turn_briefing_win = (
        turn_briefing.window
        if (
            turn_briefing is not None
            and getattr(turn_briefing, 'window', None) is not None
            and hasattr(turn_briefing.window, 'alive')
            and bool(turn_briefing.window.alive() is True)
        )
        else None
    )

    comms = getattr(gui, 'communications_window', None)
    comms_win = (
        comms.window
        if (
            comms is not None
            and getattr(comms, 'window', None) is not None
            and hasattr(comms.window, 'alive')
            and bool(comms.window.alive() is True)
        )
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
        unit_editor_panel,
        turn_briefing_win,
        comms_win,
    ]

    seen_panels = set()
    for panel in panels:
        if panel is not None and panel not in seen_panels:
            seen_panels.add(panel)
            if (
                getattr(panel, '_wormhole_themed_colors', None) == theme_sig
                and getattr(panel, 'background_colour', None) == bg_color
                and (not hasattr(panel, 'border_colour') or getattr(panel, 'border_colour', None) == border_color)
            ):
                continue
            try:
                panel.background_colour = bg_color
                if hasattr(panel, 'border_colour'):
                    panel.border_colour = border_color
                panel.rebuild()
                panel._wormhole_themed_colors = theme_sig
            except Exception as e:
                logger.debug(f"Error updating panel color for {panel}: {e}")



def update_resource_display(gui, player: 'Player') -> None:
    """Updates credits, metal, and crystal resource readouts and income tooltips for a player.

    Args:
        gui: Target GUI_Handler instance.
        player (Player): Active player entity whose resources to render.
    """
    if gui.credits_label:
        credits_text = f"Credits: {player.credits:.0f}"
        if getattr(gui.credits_label, 'text', None) != credits_text:
            gui.credits_label.set_text(credits_text)

    if gui.metal_label:
        metal_text = f"Metal: {player.metal:.0f}"
        if getattr(gui.metal_label, 'text', None) != metal_text:
            gui.metal_label.set_text(metal_text)
    if gui.crystal_label:
        crystal_text = f"Crystal: {player.crystal:.0f}"
        if getattr(gui.crystal_label, 'text', None) != crystal_text:
            gui.crystal_label.set_text(crystal_text)
    if getattr(gui, 'population_label', None):
        game = getattr(gui, 'game_instance', None)
        pop_cache = getattr(game, '_cached_population_display', None)
        pop_dirty = getattr(game, '_population_display_dirty', True)
        if not pop_dirty and pop_cache is not None and pop_cache[0] is player:
            population = pop_cache[1]
        else:
            from economy import total_population
            population = total_population(getattr(game, 'galaxy', None), player)
            if game is not None and hasattr(game, '_population_display_dirty'):
                game._cached_population_display = (player, population)
                game._population_display_dirty = False
        pop_text = f"Population: {population:,.1f}"
        if getattr(gui.population_label, 'text', None) != pop_text:
            gui.population_label.set_text(pop_text)


ECONOMY_INCOME_HEADER_COLOR = "#50E550"
ECONOMY_UPKEEP_HEADER_COLOR = "#FF6666"
ECONOMY_DIALOG_HEIGHT = 560


def format_economy_breakdown_html(report: dict) -> str:
    """Format the recurring economy report as HTML for the Income and Upkeep dialog."""
    from html import escape

    income, upkeep = report["income"], report["upkeep"]
    details = report["income_breakdown"]
    colonies = sorted(
        details["colonies"],
        key=lambda row: (
            -row["credits"],
            -row["metal"],
            -row["crystal"],
            (row["name"] or "").casefold(),
            row["body_id"],
        ),
    )
    habitats = sorted(
        details["habitats"],
        key=lambda row: (-row["credits"], (row["name"] or "").casefold(), row["unit_id"]),
    )
    upkeep_rows = sorted(
        report["upkeep_breakdown"],
        key=lambda row: (-row["credits"], (row["name"] or "").casefold(), row["unit_id"]),
    )

    net = income - upkeep
    net_color = ECONOMY_UPKEEP_HEADER_COLOR if net < 0 else ECONOMY_INCOME_HEADER_COLOR
    summary_line = (
        f"<b><font color='{ECONOMY_INCOME_HEADER_COLOR}'>Income {income:,.2f}</font>"
        f" · <font color='{ECONOMY_UPKEEP_HEADER_COLOR}'>Upkeep {upkeep:,.2f}</font>"
        f" · <font color='{net_color}'>Net {net:+,.2f}</font></b>"
    )
    rows = [
        summary_line,
        f"<font color='{ECONOMY_INCOME_HEADER_COLOR}'><b>Income from colonies</b></font>",
    ]
    rows.extend(
        f'{escape(row["name"])} ({escape(row["system_name"] or "")}) · {row["credits"]:,.2f} credits'
        f' · {row["metal"]:g} metal · {row["crystal"]:g} crystal'
        for row in colonies
    )
    if not colonies:
        rows.append("No owned colonies.")
    if habitats:
        rows.append(f"<font color='{ECONOMY_INCOME_HEADER_COLOR}'><b>Income from civilian habitats</b></font>")
        rows.extend(
            f'{escape(row["name"])} (#{row["unit_id"]}) · {row["credits"]:,.2f} credits'
            for row in habitats
        )
    if details["siphoned_credits"]:
        rows.append(
            f"<font color='{ECONOMY_INCOME_HEADER_COLOR}'><b>Intelligence income</b></font>"
            f' · {details["siphoned_credits"]:,.2f} credits'
        )
    rows.append(f"<font color='{ECONOMY_UPKEEP_HEADER_COLOR}'><b>Fleet upkeep</b></font>")
    rows.extend(
        f'{escape(row["name"])} (#{row["unit_id"]}) · {row["credits"]:,.2f} credits'
        for row in upkeep_rows
    )
    if not upkeep_rows:
        rows.append("No recurring fleet upkeep.")
    return "<br>".join(rows)


def show_economy_breakdown(gui) -> None:
    from economy import recurring_economy

    game = gui.game_instance
    player = game.current_player
    if player is None:
        return
    report = recurring_economy(game.galaxy, player)
    gui.show_info_dialog(
        format_economy_breakdown_html(report),
        title="Income and Upkeep",
        height=ECONOMY_DIALOG_HEIGHT,
    )


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
    text = f"Comms ({len(unread)})" if unread else "Comms"
    if getattr(gui.comms_button, 'text', None) != text:
        gui.comms_button.set_text(text)
