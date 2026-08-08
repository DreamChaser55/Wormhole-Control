"""Sidebar view widget factory, section state tracking, and clearing."""
import typing
import pygame
import pygame_gui

from constants import INFO_BOX_WIDTH, TEXT_SCALE


def clear_side_bar_content(gui) -> None:
    """Kills and removes all dynamically added UI elements from the sidebar.

    Args:
        gui: Target GUI_Handler instance.
    """
    for element in gui.side_bar_dynamic_elements:
        if element.alive():
            element.kill()
    gui.side_bar_dynamic_elements.clear()
    gui.dynamic_button_actions.clear()
    gui.dynamic_dropdown_actions.clear()
    gui.unit_name_entry = None


def is_section_expanded(gui, section_id: str) -> bool:
    """Checks if a given UI section is marked as expanded.

    Args:
        gui: Target GUI_Handler instance.
        section_id (str): Identifier of the sidebar section.

    Returns:
        bool: True if section is expanded, False otherwise.
    """
    return gui.expanded_sections.get(section_id, False)


def toggle_section_expansion(gui, section_id: str) -> None:
    """Toggles the expansion state of a given UI section.

    Args:
        gui: Target GUI_Handler instance.
        section_id (str): Identifier of the sidebar section.
    """
    gui.expanded_sections[section_id] = not is_section_expanded(gui, section_id)


def _build_label(gui, item_data: dict, x: int, y: int, width: int, height: int, container, obj_id) -> int:
    text = item_data.get('text', '')
    font = gui.manager.get_theme().get_font(obj_id)
    lines, line_height = gui.wrap_text_to_lines(text, width, font)
    total_height = 0
    for line in lines:
        label_rect = pygame.Rect(x, y + total_height, width, -1)
        label = pygame_gui.elements.UILabel(
            relative_rect=label_rect,
            text=line,
            manager=gui.manager,
            container=container,
            object_id=obj_id
        )
        gui.side_bar_dynamic_elements.append(label)
        total_height += label.get_relative_rect().height
    return total_height


def _build_text_box(gui, item_data: dict, x: int, y: int, width: int, height: int, container, obj_id) -> int:
    html_text = item_data.get('html_text', '')
    text_box_rect = pygame.Rect(x, y, width, height)
    text_box = pygame_gui.elements.UITextBox(
        html_text=html_text,
        relative_rect=text_box_rect,
        manager=gui.manager,
        container=container,
        object_id=obj_id
    )
    gui.side_bar_dynamic_elements.append(text_box)
    return height


def _build_button(gui, item_data: dict, x: int, y: int, width: int, height: int, container, obj_id) -> int:
    text = item_data.get('text', '')
    action_id = item_data.get('action_id', '')
    target_data = item_data.get('target_data', None)
    button_rect = pygame.Rect(x, y, width, -1)
    button = pygame_gui.elements.UIButton(
        relative_rect=button_rect,
        text=text,
        manager=gui.manager,
        container=container,
        object_id=obj_id
    )
    gui.dynamic_button_actions[button] = {'action_id': action_id, 'target_data': target_data}
    gui.side_bar_dynamic_elements.append(button)
    return button.get_relative_rect().height


def _build_inhibitor_button(gui, item_data: dict, x: int, y: int, width: int, height: int, container, obj_id) -> int:
    is_active = item_data.get('is_active', False)
    button_text = "Deactivate Inhibitor" if is_active else "Activate Inhibitor"
    button_rect = pygame.Rect(x, y, width, -1)
    button = pygame_gui.elements.UIButton(
        relative_rect=button_rect,
        text=button_text,
        manager=gui.manager,
        container=container,
        object_id='#toggle_inhibitor_button'
    )
    gui.side_bar_dynamic_elements.append(button)
    return button.get_relative_rect().height


def _build_cloaking_button(gui, item_data: dict, x: int, y: int, width: int, height: int, container, obj_id) -> int:
    is_active = item_data.get('is_active', False)
    button_text = "Deactivate Cloak" if is_active else "Activate Cloak"
    button_rect = pygame.Rect(x, y, width, -1)
    button = pygame_gui.elements.UIButton(
        relative_rect=button_rect,
        text=button_text,
        manager=gui.manager,
        container=container,
        object_id='#toggle_cloaking_button'
    )
    gui.side_bar_dynamic_elements.append(button)
    return button.get_relative_rect().height


def _build_progress_bar(gui, item_data: dict, x: int, y: int, width: int, height: int, container, obj_id) -> int:
    progress = item_data.get('progress', 0)
    total = item_data.get('total', 100)
    progress_bar_rect = pygame.Rect(x, y, width, height)
    progress_bar = pygame_gui.elements.UIProgressBar(
        relative_rect=progress_bar_rect,
        manager=gui.manager,
        container=container,
        object_id='#constructor_progress_bar'
    )
    percent = (progress / total) * 100.0 if total > 0 else 100.0
    progress_bar.set_current_progress(percent)
    gui.side_bar_dynamic_elements.append(progress_bar)
    return height


def _build_drop_down_menu(gui, item_data: dict, x: int, y: int, width: int, height: int, container, obj_id) -> int:
    options_list = item_data.get('options_list', [])
    starting_option = item_data.get('starting_option', '')
    action_id = item_data.get('action_id', '')
    target_data = item_data.get('target_data', None)
    dropdown_rect = pygame.Rect(x, y, width, height)
    dropdown = pygame_gui.elements.UIDropDownMenu(
        options_list=options_list,
        starting_option=starting_option,
        relative_rect=dropdown_rect,
        manager=gui.manager,
        container=container,
        object_id=obj_id
    )
    if action_id:
        gui.dynamic_dropdown_actions[dropdown] = {'action_id': action_id, 'target_data': target_data}
    gui.side_bar_dynamic_elements.append(dropdown)
    return height


def _build_text_entry_line(gui, item_data: dict, x: int, y: int, width: int, height: int, container, obj_id) -> int:
    initial_text = item_data.get('initial_text', '')
    entry_rect = pygame.Rect(x, y, width, height)
    entry = pygame_gui.elements.UITextEntryLine(
        relative_rect=entry_rect,
        manager=gui.manager,
        container=container,
        object_id=obj_id
    )
    max_length = item_data.get('max_length', 0)
    if max_length > 0:
        entry.set_text_length_limit(max_length)
    entry.set_text(initial_text)
    gui.unit_name_entry = entry
    gui.side_bar_dynamic_elements.append(entry)
    return height


_ITEM_BUILDERS = {
    'label': _build_label,
    'text_box': _build_text_box,
    'button': _build_button,
    'inhibitor_button': _build_inhibitor_button,
    'cloaking_button': _build_cloaking_button,
    'progress_bar': _build_progress_bar,
    'drop_down_menu': _build_drop_down_menu,
    'text_entry_line': _build_text_entry_line,
}


def update_side_bar_content(gui, data_list: typing.List[dict]) -> None:
    """Updates the content of the side bar info panel by creating UI elements from structured data.

    Args:
        gui: Target GUI_Handler instance.
        data_list (typing.List[dict]): List of item definition dictionaries.
    """
    if not gui.side_bar_info_panel or not gui.side_bar_info_panel.alive():
        return

    clear_side_bar_content(gui)

    current_y_offset = 5
    element_padding = 3
    gap = 4
    base_container_rect = gui.side_bar_info_panel.get_container().get_rect()
    base_container_width = base_container_rect.width if base_container_rect else INFO_BOX_WIDTH
    indent_size = 15

    rows: typing.List[typing.List[dict]] = []
    current_row: typing.List[dict] = []
    for item_data in data_list:
        if item_data.get('side_by_side', False):
            current_row.append(item_data)
        else:
            if current_row:
                rows.append(current_row)
                current_row = []
            rows.append([item_data])
    if current_row:
        rows.append(current_row)

    for row in rows:
        row_count = len(row)
        row_max_height = 0

        first_item_indent = row[0].get('indent_level', 0)
        start_x = 5 + (first_item_indent * indent_size)
        total_row_width = base_container_width - (first_item_indent * indent_size) - 10
        available_width = total_row_width - ((row_count - 1) * gap)
        item_width = max(1, available_width // row_count)

        for col_idx, item_data in enumerate(row):
            item_type = item_data.get('type')
            object_id_str = item_data.get('object_id', None)
            class_id_str = item_data.get('class_id', None)
            height_from_data = int(item_data.get('height', 25) * TEXT_SCALE)

            target_container_for_element = gui.side_bar_info_panel.get_container()
            current_element_y = current_y_offset
            current_element_x = start_x + col_idx * (item_width + gap)
            current_element_width = item_width

            obj_id = None
            if object_id_str:
                obj_id = pygame_gui.core.ObjectID(object_id=object_id_str, class_id=class_id_str)
            elif class_id_str:
                obj_id = pygame_gui.core.ObjectID(class_id=class_id_str)

            builder = _ITEM_BUILDERS.get(item_type)
            if builder:
                actual_element_total_height = builder(
                    gui, item_data, current_element_x, current_element_y,
                    current_element_width, height_from_data, target_container_for_element, obj_id
                )
            else:
                actual_element_total_height = 0

            if actual_element_total_height > row_max_height:
                row_max_height = actual_element_total_height

        if row_max_height > 0:
            current_y_offset += row_max_height + element_padding
        else:
            current_y_offset += element_padding
