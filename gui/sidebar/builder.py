"""Sidebar UI payload builder orchestrator."""
import logging
import constants
from utils import Timer, color_to_hex
from entities import CelestialBody, Minefield, Unit
from galaxy import StarSystem, Hex
from .panels_world import (
    build_system_panel, build_hex_panel,
    build_celestial_body_panel, build_minefield_panel, object_button_style
)
from .panels_unit import build_unit_panel

logger = logging.getLogger(__name__)


def _apply_player_button_theme(game) -> None:
    """Loads player-colored button and label styles into the GUI theme manager."""
    if game.players and hasattr(game.gui, 'manager') and game.gui.manager:
        theme_dict = {}
        for p in game.players:
            obj_id = f'#player_{p.name.lower().replace(" ", "_")}_button'
            lbl_id = f'#player_{p.name.lower().replace(" ", "_")}_label'
            hex_col = color_to_hex(p.color)
            theme_dict[obj_id] = {
                "colours": {
                    "normal_text": hex_col,
                    "hovered_text": hex_col,
                    "active_text": hex_col
                },
                "misc": {
                    "text_horiz_alignment": "left"
                }
            }
            theme_dict[lbl_id] = {
                "colours": {
                    "normal_text": hex_col
                },
                "misc": {
                    "text_horiz_alignment": "left"
                }
            }
        try:
            game.gui.manager.get_theme().load_theme(theme_dict)
        except Exception as e:
            logger.debug(f"Error loading player button themes: {e}")


def _build_empty_panel() -> list[dict]:
    """Constructs sidebar data payload when nothing is selected."""
    return [{
        'type': 'label',
        'text': 'Nothing Selected',
        'object_id': '#sidebar_title_label',
        'height': 30
    }]


def _build_multi_selection_panel(game) -> list[dict]:
    """Constructs sidebar data payload when multiple objects are selected."""
    data = [{
        'type': 'label',
        'text': f"{len(game.selected_objects)} units selected",
        'object_id': '#sidebar_title_label',
        'height': 30
    }]
    current_player = game.players[game.current_player_index] if game.players else None
    has_orders_to_stop = any(
        isinstance(obj, Unit) and obj.owner == current_player and obj.commander_component and obj.commander_component.get_active_orders_count() > 0
        for obj in game.selected_objects
    )
    if has_orders_to_stop:
        data.append({
            'type': 'button',
            'text': "Stop Selected Units",
            'object_id': '#sidebar_expand_button',
            'action_id': 'stop_selected_units',
            'target_data': None,
            'height': 25
        })
    for obj in game.selected_objects:
        if isinstance(obj, Unit):
            owner = getattr(obj, 'owner', None)
            data.append({
                'type': 'button',
                'text': obj.name,
                'object_id': object_button_style(owner),
                'class_id': '#sidebar_expand_button',
                'action_id': 'select_individual_unit',
                'target_data': obj.id,
                'height': 25
            })
    return data


def build_sidebar_data(game) -> list[dict]:
    """Builds full GUI element description payload based on game selection state."""
    if not game.selected_objects:
        if (getattr(game, 'view_mode', None) == 'sector'
                and getattr(game, 'current_system_name', None)
                and getattr(game, 'current_sector_coord', None) is not None
                and getattr(game, 'galaxy', None)
                and game.current_system_name in game.galaxy.systems):
            system = game.galaxy.systems[game.current_system_name]
            if game.current_sector_coord in system.hexes:
                return build_hex_panel(game, system.hexes[game.current_sector_coord])
        return _build_empty_panel()
    elif len(game.selected_objects) > 1:
        return _build_multi_selection_panel(game)

    selected_obj = game.selected_objects[0]
    if isinstance(selected_obj, StarSystem):
        return build_system_panel(game, selected_obj)
    elif isinstance(selected_obj, Hex):
        return build_hex_panel(game, selected_obj)
    elif isinstance(selected_obj, CelestialBody):
        return build_celestial_body_panel(game, selected_obj)
    elif isinstance(selected_obj, Minefield):
        return build_minefield_panel(game, selected_obj)
    elif isinstance(selected_obj, Unit):
        return build_unit_panel(game, selected_obj)
    else:
        # Default / Unknown fallback
        return [
            {
                'type': 'label',
                'text': f"Selected: {type(selected_obj).__name__}",
                'object_id': '#sidebar_title_label',
                'height': 30
            },
            {
                'type': 'label',
                'text': f"ID: {getattr(selected_obj, 'id', 'N/A')}",
                'object_id': '#sidebar_info_label',
                'height': 25
            }
        ]


def update_side_bar_content(game) -> None:
    """Constructs and updates the sidebar data payload based on current selections and view mode."""
    if not getattr(game, 'sidebar_needs_update', True):
        return

    if not game.selected_objects or len(game.selected_objects) > 1 or not isinstance(game.selected_objects[0], Unit):
        game.selected_component_name = None

    profile_enabled = getattr(constants, 'PROFILE', False) or getattr(game, 'PROFILE', False)

    if profile_enabled:
        sidebar_timer = Timer()
        sidebar_timer.start()

    _apply_player_button_theme(game)
    data_for_gui = build_sidebar_data(game)

    if profile_enabled:
        gui_update_timer = Timer()
        gui_update_timer.start()

    game.gui.update_side_bar_content(data_for_gui)

    if profile_enabled:
        gui_update_timer.stop()
        logger.debug(f"  [Profile] GUI element recreation took: {gui_update_timer}")

    game.sidebar_needs_update = False

    if profile_enabled:
        sidebar_timer.stop()
        logger.debug(f"  [Profile] Sidebar update took: {sidebar_timer}")
