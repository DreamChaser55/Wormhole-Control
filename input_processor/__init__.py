"""Input processing and event dispatch package for Wormhole Control."""
from input_processor.processor import InputProcessor
from input_processor.hover_tracker import update_hover_states
from input_processor.keyboard_handler import handle_keyboard_panning, handle_key_down
from input_processor.mouse_handler import (
    handle_mouse_button_down,
    handle_mouse_button_up,
    handle_mouse_motion,
    handle_mouse_click,
)
from input_processor.context_menu_builder import (
    build_system_context_menu_options,
    build_sector_context_menu_options,
    get_refit_context_options,
    get_ability_context_options,
)
from input_processor.context_actions import handle_context_menu_action

# Re-export spatial utilities for backward compatibility with test monkeypatches
from sector_utils import (
    is_pixel_in_sector,
    pixels_to_sector_coords,
    sector_coords_to_pixels,
    sector_radius_to_pixels,
)

__all__ = [
    "InputProcessor",
    "update_hover_states",
    "handle_keyboard_panning",
    "handle_key_down",
    "handle_mouse_button_down",
    "handle_mouse_button_up",
    "handle_mouse_motion",
    "handle_mouse_click",
    "build_system_context_menu_options",
    "build_sector_context_menu_options",
    "get_refit_context_options",
    "get_ability_context_options",
    "handle_context_menu_action",
    "is_pixel_in_sector",
    "pixels_to_sector_coords",
    "sector_coords_to_pixels",
    "sector_radius_to_pixels",
]
