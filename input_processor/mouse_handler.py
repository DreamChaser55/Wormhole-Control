"""Mouse event processing, camera dragging, box selection, and click dispatch."""
import typing
import logging
import pygame
from geometry import Position, distance_sq
import sys
from entities import Unit
from events import UseAbilityEvent
from input_processor.context_menu_builder import (
    build_system_context_menu_options,
    build_sector_context_menu_options,
    build_sector_unit_disambiguation_menu,
)
from input_processor.hover_tracker import get_units_under_mouse

logger = logging.getLogger(__name__)


def is_pixel_in_sector(*args, **kwargs):
    mod = sys.modules.get('input_processor')
    fn = getattr(mod, 'is_pixel_in_sector', None) if mod else None
    if fn is not None and fn is not is_pixel_in_sector:
        return fn(*args, **kwargs)
    import sector_utils
    return sector_utils.is_pixel_in_sector(*args, **kwargs)


def pixels_to_sector_coords(*args, **kwargs):
    mod = sys.modules.get('input_processor')
    fn = getattr(mod, 'pixels_to_sector_coords', None) if mod else None
    if fn is not None and fn is not pixels_to_sector_coords:
        return fn(*args, **kwargs)
    import sector_utils
    return sector_utils.pixels_to_sector_coords(*args, **kwargs)


def sector_coords_to_pixels(*args, **kwargs):
    mod = sys.modules.get('input_processor')
    fn = getattr(mod, 'sector_coords_to_pixels', None) if mod else None
    if fn is not None and fn is not sector_coords_to_pixels:
        return fn(*args, **kwargs)
    import sector_utils
    return sector_utils.sector_coords_to_pixels(*args, **kwargs)



def handle_mouse_button_down(game, gui, event: pygame.event.Event, mouse_pos: Position, gui_action: typing.Optional[dict], click_handler_fn: typing.Callable[[int, Position], None]) -> None:
    """Handles MOUSEBUTTONDOWN events, initiating camera/box drag and dispatching clicks.

    Args:
        game: Target Game instance.
        gui: Target GUI_Handler instance.
        event (pygame.event.Event): Pygame mouse event.
        mouse_pos (Position): Mouse position at press time.
        gui_action (dict, optional): Action returned by gui.process_event if event was captured by UI.
        click_handler_fn (callable): Callback to dispatch mouse click logic.
    """
    clicked_point = mouse_pos
    if event.button == 1 and game.view_mode == 'sector' and not gui_action:
        game.is_dragging_selection_box = True
        game.selection_box_start_pos = clicked_point
    elif event.button == 2 and game.view_mode == 'sector':
        game.is_dragging_camera = True
        game.camera_drag_last_pos = clicked_point

    if not gui_action:
        if not gui.is_mouse_over_context_menu(clicked_point):
            click_handler_fn(event.button, clicked_point)
            if event.button == 1:
                gui.close_context_menu()
    else:
        if event.button == 1:
            action_type = gui_action.get('action')
            if action_type not in ['ui_handled', 'context_menu_select'] and not gui.is_mouse_over_context_menu(clicked_point):
                gui.close_context_menu()


def handle_mouse_button_up(game, mouse_pos: Position, event: pygame.event.Event) -> None:
    """Handles MOUSEBUTTONUP events including camera drag release and box selection resolution.

    Args:
        game: Target Game instance.
        mouse_pos (Position): Current mouse screen coordinates.
        event (pygame.event.Event): Pygame mouse event.
    """
    if event.button == 2 and getattr(game, 'is_dragging_camera', False):
        game.is_dragging_camera = False
    elif event.button == 1 and game.is_dragging_selection_box:
        game.is_dragging_selection_box = False
        start_pos = game.selection_box_start_pos
        end_pos = mouse_pos

        is_a_click = distance_sq(start_pos, end_pos) < 5**2

        if not is_a_click:
            # It's a drag. Perform box selection.
            selection_rect = pygame.Rect(start_pos.to_tuple(), (end_pos.x - start_pos.x, end_pos.y - start_pos.y))
            selection_rect.normalize()

            shift_pressed = _get_shift_pressed()
            selected_units_in_box = []
            current_system = game.galaxy.systems.get(game.current_system_name) if game.galaxy else None
            if current_system and game.current_sector_coord in current_system.hexes:
                hex_obj = current_system.hexes[game.current_sector_coord]
                if hex_obj:
                    for unit in hex_obj.units:
                        if not game.is_unit_visible(unit):
                            continue
                        unit_pixel_pos = sector_coords_to_pixels(unit.position, game.sector_zoom, game.sector_pan_offset)
                        if selection_rect.collidepoint(unit_pixel_pos.to_tuple()):
                            selected_units_in_box.append(unit)

            if shift_pressed:
                # If shift is pressed, we either add to selection or deselect if all are already selected.
                all_in_box_are_selected = all(unit in game.selected_objects for unit in selected_units_in_box) if selected_units_in_box else False

                if all_in_box_are_selected:
                    # Deselect all units in the box
                    for unit in selected_units_in_box:
                        if unit in game.selected_objects:
                            game.selected_objects.remove(unit)
                else:
                    # Add all units in the box to the selection
                    for unit in selected_units_in_box:
                        if unit not in game.selected_objects:
                            game.selected_objects.append(unit)
            else:
                # No shift, so just select the units in the box
                game.selected_objects.clear()
                game.selected_objects.extend(selected_units_in_box)

            game.sidebar_needs_update = True


def handle_mouse_motion(game, mouse_pos: Position) -> None:
    """Updates sector view camera pan offset during middle-click drag.

    Args:
        game: Target Game instance.
        mouse_pos (Position): Current mouse screen coordinates.
    """
    if game.view_mode == 'sector' and getattr(game, 'is_dragging_camera', False):
        dx = mouse_pos.x - game.camera_drag_last_pos.x
        dy = mouse_pos.y - game.camera_drag_last_pos.y
        game.sector_pan_offset.x += dx
        game.sector_pan_offset.y += dy
        if getattr(game, 'zoom_anchor_pixel', None) is not None:
            game.zoom_anchor_pixel.x += dx
            game.zoom_anchor_pixel.y += dy
        game.camera_drag_last_pos = mouse_pos


def _get_shift_pressed() -> bool:
    try:
        return bool(pygame.key.get_mods() & pygame.KMOD_SHIFT)
    except Exception:
        return False


def _get_ctrl_pressed() -> bool:
    try:
        return bool(pygame.key.get_mods() & pygame.KMOD_CTRL)
    except Exception:
        return False


def handle_mouse_click(game, gui, button: int, position: Position) -> None:
    """Handles mouse click events that occur over the main game canvas (outside UI elements).

    Dispatches clicks based on mouse button (1=Left, 2=Middle, 3=Right), modifier keys,
    active view mode (galaxy/system/sector), and pending ability targeting states.

    Args:
        game: Target Game instance.
        gui: Target GUI_Handler instance.
        button (int): Pygame mouse button identifier (1=Left, 2=Middle, 3=Right).
        position (Position): Screen coordinates of the click event.
    """
    is_left_click = (button == 1)
    is_right_click = (button == 3)
    is_middle_click = (button == 2)
    shift_pressed = _get_shift_pressed()

    # --- Pending Ability Targeting Mode ---
    # If an ability awaiting a target is pending, intercept clicks in sector view
    pending = getattr(game, 'pending_ability', None)
    if pending and isinstance(pending, (tuple, list)) and len(pending) > 0 and isinstance(pending[0], str) and game.view_mode == 'sector':
        ability_type_str = pending[0]
        requires_unit = pending[1] if len(pending) > 1 else False
        requires_pos = pending[2] if len(pending) > 2 else False
        selected_units = [u for u in game.selected_objects if isinstance(u, Unit)]

        if selected_units:
            clicked_object = game.sector_view_mouse_hover_object
            clicked_sector_coord = pixels_to_sector_coords(position, game.sector_zoom, game.sector_pan_offset)

            if is_right_click:
                if requires_unit and isinstance(clicked_object, Unit):
                    # Complete unit-targeted ability
                    game.event_bus.publish(UseAbilityEvent(
                        units=selected_units,
                        ability_type_str=ability_type_str,
                        target_unit=clicked_object,
                        shift_pressed=shift_pressed,
                    ))
                    logger.debug(f"Ability {ability_type_str} targeted at unit {clicked_object.name}.")
                    game.pending_ability = None
                    game.sidebar_needs_update = True
                    return  # Consume the click

                elif requires_pos and not isinstance(clicked_object, Unit):
                    # Complete position-targeted ability (clicking on empty space / non-unit)
                    game.event_bus.publish(UseAbilityEvent(
                        units=selected_units,
                        ability_type_str=ability_type_str,
                        target_position=clicked_sector_coord,
                        target_system_name=game.current_system_name,
                        target_hex_coord=game.current_sector_coord,
                        shift_pressed=shift_pressed,
                    ))
                    logger.debug(f"Ability {ability_type_str} targeted at position {clicked_sector_coord}.")
                    game.pending_ability = None
                    game.sidebar_needs_update = True
                    return  # Consume the click

                elif requires_unit and not isinstance(clicked_object, Unit):
                    logger.debug(f"Ability {ability_type_str} requires a unit target. Right-click on a unit or press ESC to cancel.")
                    return  # Consume to prevent opening unwanted context menus

            elif is_left_click:
                # Protect unit selection from accidental left-clicks while in targeting mode
                logger.debug(f"Left-click ignored during targeting mode for {ability_type_str}. Right-click the target to cast, or press ESC to cancel.")
                return  # Consume the click to prevent deselecting or changing selection

    if game.view_mode == 'galaxy':
        clicked_system_name = game.galaxy_view_mouse_hover_system_name
        system_obj = game.galaxy.systems.get(clicked_system_name, None) if game.galaxy else None
        if system_obj:
            if is_left_click:
                game.selected_objects = [system_obj]
                game.sidebar_needs_update = True
                logger.debug(f"Selected object: System {system_obj.name}")
            elif is_middle_click:
                game.view_mode = 'system'
                game.current_system_name = clicked_system_name
                game.sidebar_needs_update = True
                logger.debug(f"Entering system view: {system_obj.name}")
                game.update_view_specific_labels()
        else:
            if is_left_click:
                game.selected_objects.clear()
                game.sidebar_needs_update = True
                logger.debug("Selection cleared")

    elif game.view_mode == 'system':
        if not game.current_system_name or not game.galaxy:
            return
        system = game.galaxy.systems.get(game.current_system_name)
        clicked_hex = game.system_view_mouse_hover_hex
        if clicked_hex and system:
            if is_right_click:
                options = build_system_context_menu_options(game, clicked_hex)
                gui.open_context_menu(position, options, clicked_hex)
            elif is_left_click:
                if clicked_hex in system.hexes:
                    hex_obj = system.hexes[clicked_hex]
                    game.selected_objects = [hex_obj]
                    game.sidebar_needs_update = True
                    logger.debug(f"Selected object: Hex {clicked_hex} in System {system.name}")
            elif is_middle_click:
                game.view_mode = 'sector'
                game.current_sector_coord = clicked_hex
                game.reset_sector_camera()
                game.sidebar_needs_update = True
                logger.debug(f"Entering sector view: Hex {clicked_hex} in System {game.current_system_name}")
                game.update_view_specific_labels()
        else:
            if is_left_click:
                game.selected_objects.clear()
                game.sidebar_needs_update = True
                logger.debug("Selection cleared")
            elif is_middle_click:
                game.view_mode = 'galaxy'
                game.current_system_name = None
                game.sidebar_needs_update = True
                logger.debug("Entering galaxy view")
                game.update_view_specific_labels()

    elif game.view_mode == 'sector':
        zoom = game.sector_zoom
        if not isinstance(zoom, (int, float)):
            zoom = 1.0
        pan_offset = game.sector_pan_offset
        if not isinstance(pan_offset, Position):
            pan_offset = Position(0, 0)

        if is_pixel_in_sector(position, zoom, pan_offset):
            clicked_sector_coord = pixels_to_sector_coords(position, zoom, pan_offset)
            if is_right_click:
                units_under_mouse = get_units_under_mouse(game, position)
                if len(units_under_mouse) >= 2:
                    options, target = build_sector_unit_disambiguation_menu(game, units_under_mouse, clicked_sector_coord)
                    gui.open_context_menu(position, options, target)
                else:
                    clicked_object = units_under_mouse[0] if len(units_under_mouse) == 1 else game.sector_view_mouse_hover_object
                    options, target = build_sector_context_menu_options(game, clicked_object, clicked_sector_coord)
                    gui.open_context_menu(position, options, target)

            elif is_left_click:
                clicked_object = game.sector_view_mouse_hover_object
                if clicked_object:
                    if shift_pressed:
                        if isinstance(clicked_object, Unit):
                            if clicked_object in game.selected_objects:
                                game.selected_objects.remove(clicked_object)
                                logger.debug(f"Deselected unit: {clicked_object.name}")
                            else:
                                game.selected_objects.append(clicked_object)
                                logger.debug(f"Added unit to selection: {clicked_object.name}")
                            game.sidebar_needs_update = True
                    else:
                        game.selected_objects = [clicked_object]
                        obj_type = clicked_object.__class__.__name__
                        obj_name = getattr(clicked_object, 'name', 'Unnamed')
                        game.sidebar_needs_update = True
                        logger.debug(f"Selected object: {obj_type} {obj_name}")
                else:
                    if not shift_pressed:
                        game.selected_objects.clear()
                        game.sidebar_needs_update = True
                        logger.debug("Selection cleared")
