"""GUI action handlers for selection and sidebar-state switching."""
import logging
import typing
from entities import Minefield

logger = logging.getLogger(__name__)


def handle_select_individual_unit(game, action: dict) -> None:
    unit_id = action.get('unit_id')
    shift_pressed = action.get('shift_pressed', False)
    unit = game.galaxy.get_unit_by_id(unit_id) if game.galaxy else None
    if unit:
        if shift_pressed:
            game.deselect_object(unit)
        else:
            game.selected_objects = [unit]
        game.sidebar_needs_update = True


def handle_select_minefield(game, action: dict) -> None:
    mf_id = action.get('minefield_id')
    mf = game.galaxy.get_minefield_by_id(mf_id) if (game.galaxy and mf_id is not None) else None
    if mf:
        game.selected_objects = [mf]
        game.sidebar_needs_update = True


def handle_remove_minefield(game, action: dict) -> None:
    mf_id = action.get('minefield_id', action.get('target_data'))
    mf = None
    if game.galaxy and mf_id is not None:
        mf = game.galaxy.get_minefield_by_id(mf_id)
    if mf is None:
        for obj in getattr(game, 'selected_objects', []):
            if isinstance(obj, Minefield) and (mf_id is None or obj.id == mf_id):
                mf = obj
                break

    if mf is None:
        logger.debug(f"Minefield not found for removal (id: {mf_id}).")
        return

    current_player = game.players[game.current_player_index] if (getattr(game, 'players', None) and 0 <= getattr(game, 'current_player_index', 0) < len(game.players)) else None
    if mf.owner and current_player and mf.owner != current_player:
        logger.warning(f"Player {current_player.name} attempted to remove unowned minefield '{mf.name}' (id: {mf.id}).")
        return

    if game.galaxy:
        game.galaxy.remove_minefield(mf)

    if hasattr(game, 'deselect_object'):
        game.deselect_object(mf)
    elif hasattr(game, 'selected_objects') and mf in game.selected_objects:
        game.selected_objects.remove(mf)

    if getattr(game, 'hovered_object', None) == mf:
        game.hovered_object = None
    if getattr(game, 'sector_view_mouse_hover_object', None) == mf:
        game.sector_view_mouse_hover_object = None

    game.sidebar_needs_update = True
    if hasattr(game, 'visibility_dirty'):
        game.visibility_dirty = True

    logger.debug(f"Minefield '{mf.name}' (id: {mf.id}) removed from game.")


def handle_select_celestial_body(game, action: dict) -> None:
    body_id = action.get('body_id') if action.get('body_id') is not None else action.get('target_data')
    body = game.galaxy.get_celestial_body_by_id(body_id) if (game.galaxy and body_id is not None) else None
    if body:
        game.selected_objects = [body]
        game.sidebar_needs_update = True


def handle_select_hex(game, action: dict) -> None:
    hex_coord = action.get('hex_coord') if action.get('hex_coord') is not None else action.get('target_data')
    if hex_coord is not None and game.galaxy:
        system_name = getattr(game, 'current_system_name', None)
        system = game.galaxy.systems.get(system_name) if system_name else None
        if system:
            h_key = tuple(hex_coord) if isinstance(hex_coord, (list, tuple)) else hex_coord
            if h_key in system.hexes:
                game.selected_objects = [system.hexes[h_key]]
                game.sidebar_needs_update = True


def handle_component_selected(game, action: dict) -> None:
    game.selected_component_name = action.get('component_name')
    game.sidebar_needs_update = True


def handle_switch_unit_sidebar_tab(game, action: dict) -> None:
    game.selected_unit_tab = action.get('tab_name', 'basic_info')
    game.sidebar_needs_update = True


HANDLERS: typing.Dict[str, typing.Callable[[typing.Any, dict], None]] = {
    'select_individual_unit': handle_select_individual_unit,
    'select_minefield': handle_select_minefield,
    'remove_minefield': handle_remove_minefield,
    'select_celestial_body': handle_select_celestial_body,
    'select_hex': handle_select_hex,
    'component_selected': handle_component_selected,
    'switch_unit_sidebar_tab': handle_switch_unit_sidebar_tab,
}
