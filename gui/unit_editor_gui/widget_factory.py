"""
widget_factory.py

Helper functions for UI widget creation in the Unit Designer GUI.
"""

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
