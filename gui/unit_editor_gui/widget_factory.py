"""
widget_factory.py

Helper functions for UI widget creation in the Unit Designer GUI.
"""

import typing

import pygame
import pygame_gui

from gui.widget_factory import make_button


def replace_dropdown(
    editor,
    old_dropdown: typing.Optional[pygame_gui.elements.UIDropDownMenu],
    options_list: typing.List[str],
    starting_option: str,
    object_id: str,
    group_key: typing.Optional[str] = None,
    override_rect: typing.Optional[pygame.Rect] = None,
) -> pygame_gui.elements.UIDropDownMenu:
    """Rebuilds a UIDropDownMenu widget by killing the old instance and updating tracking structures."""
    rect = override_rect if override_rect is not None else (
        old_dropdown.get_relative_rect() if old_dropdown else pygame.Rect(0, 0, 100, 30)
    )
    container = old_dropdown.ui_container if old_dropdown else editor._panel
    if old_dropdown:
        old_dropdown.kill()

    new_dd = pygame_gui.elements.UIDropDownMenu(
        options_list=options_list,
        starting_option=starting_option,
        relative_rect=rect,
        manager=editor.manager,
        container=container,
        object_id=object_id,
    )

    if old_dropdown and old_dropdown in editor._elements:
        idx = editor._elements.index(old_dropdown)
        editor._elements[idx] = new_dd
    elif new_dd not in editor._elements:
        editor._elements.append(new_dd)

    if group_key and group_key in editor._details_groups:
        group = editor._details_groups[group_key]
        if old_dropdown and old_dropdown in group:
            idx = group.index(old_dropdown)
            group[idx] = new_dd
        elif new_dd not in group:
            group.append(new_dd)

        if editor._selected_component_key != group_key:
            new_dd.hide()
        else:
            new_dd.show()

    return new_dd


def make_help_button(editor, container, title: str):
    """Build a square help control independent of its equipment toggle's state."""
    size = max(24, int(24 * editor.display_config.text_scale))
    button = make_button(pygame.Rect(0, 0, size, size), "?", editor.manager,
                         container, "#editor_help_button")
    button.set_tooltip(f"About {title}")
    return button


def set_wrapped_button_text(button, text: str, minimum_height: int) -> None:
    """Measure wrapped text, then retain a comfortable minimum click target."""
    button.set_text(text)
    width = button.relative_rect.width
    button.set_dimensions((width, -1))
    button.set_dimensions((width, max(minimum_height, button.relative_rect.height)))

