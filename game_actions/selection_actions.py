"""GUI action handlers for selection and sidebar-state switching."""
import typing


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


def handle_select_celestial_body(game, action: dict) -> None:
    body_id = action.get('body_id') if action.get('body_id') is not None else action.get('target_data')
    body = game.galaxy.get_celestial_body_by_id(body_id) if (game.galaxy and body_id is not None) else None
    if body:
        game.selected_objects = [body]
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
    'select_celestial_body': handle_select_celestial_body,
    'component_selected': handle_component_selected,
    'switch_unit_sidebar_tab': handle_switch_unit_sidebar_tab,
}
