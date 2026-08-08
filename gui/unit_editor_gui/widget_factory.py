"""
widget_factory.py

Helper functions for UI widget creation in the Unit Designer GUI.
"""

import typing

import pygame
import pygame_gui


def make_label(
    rect: pygame.Rect,
    text: str,
    manager: pygame_gui.UIManager,
    container: pygame_gui.core.UIContainer,
    object_id: str = "#comp_cost_label",
) -> pygame_gui.elements.UILabel:
    """Creates a UILabel widget with standard parameters."""
    return pygame_gui.elements.UILabel(
        relative_rect=rect,
        text=text,
        manager=manager,
        container=container,
        object_id=object_id,
    )


def make_entry(
    rect: pygame.Rect,
    text: str,
    manager: pygame_gui.UIManager,
    container: pygame_gui.core.UIContainer,
    object_id: str = "#turret_entry",
) -> pygame_gui.elements.UITextEntryLine:
    """Creates a UITextEntryLine widget initialized with text."""
    entry = pygame_gui.elements.UITextEntryLine(
        relative_rect=rect,
        manager=manager,
        container=container,
        object_id=object_id,
    )
    entry.set_text(text)
    return entry


def make_dropdown(
    rect: pygame.Rect,
    options: list,
    starting_option: str,
    manager: pygame_gui.UIManager,
    container: pygame_gui.core.UIContainer,
    object_id: str = "#hd_type_dropdown",
) -> pygame_gui.elements.UIDropDownMenu:
    """Creates a UIDropDownMenu widget."""
    return pygame_gui.elements.UIDropDownMenu(
        options_list=options,
        starting_option=starting_option,
        relative_rect=rect,
        manager=manager,
        container=container,
        object_id=object_id,
    )


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


def make_button(
    rect: pygame.Rect,
    text: str,
    manager: pygame_gui.UIManager,
    container: pygame_gui.core.UIContainer,
    object_id: str = "#comp_toggle_button",
) -> pygame_gui.elements.UIButton:
    """Creates a UIButton widget."""
    return pygame_gui.elements.UIButton(
        relative_rect=rect,
        text=text,
        manager=manager,
        container=container,
        object_id=object_id,
    )

