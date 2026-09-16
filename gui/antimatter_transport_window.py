"""A modal for configuring a fixed antimatter delivery route."""

from dataclasses import dataclass

import pygame
import pygame_gui
from pygame_gui.elements import (
    UIWindow, UILabel, UIDropDownMenu, UIButton, UITextEntryLine,
    UIScrollingContainer,
)

from antimatter_logistics import exchange_blocker
from display_config import display_config_for


def is_open(gui):
    dialog = getattr(gui, "antimatter_transport_window", None)
    return bool(dialog and dialog.window.alive() is True)


def _selected(dropdown):
    value = dropdown.selected_option
    return value[0] if isinstance(value, tuple) else value


@dataclass
class _EndpointState:
    unit_id: int | None = None
    system: str | None = None
    hex_coord: tuple | None = None
    query: str = ""
    unavailable: bool = False


class _EndpointPicker:
    """Independent endpoint filters and stable selection, separate from widgets."""

    def __init__(self, dialog, title, y, state):
        self.dialog, self.state, self.title = dialog, state, title
        self.choices = {}
        self.rects = {}
        self.system = self.hex = self.unit = None
        row, gap, width = dialog.row, dialog.gap, dialog.body_width
        manager, container = dialog.gui.manager, dialog.body
        UILabel(pygame.Rect(0, y, width, row), title, manager, container=container)
        y += row + gap
        half = (width - gap) // 2
        self.rects['system'] = pygame.Rect(0, y, half, row)
        self.rects['hex'] = pygame.Rect(half + gap, y, width - half - gap, row)
        self.search = UITextEntryLine(
            pygame.Rect(0, y + row + gap, width, row), manager,
            container=container, placeholder_text="Search by unit name or ID",
        )
        self.rects['unit'] = pygame.Rect(0, y + 2 * (row + gap), width, row)
        self.refresh()

    def _dropdown(self, name, choices, value, enabled=True):
        label = next(label for label, candidate in choices.items() if candidate == value)
        widget = getattr(self, name)
        if (widget is None or self.choices[name] != choices
                or _selected(widget) != label):
            if widget is not None:
                widget.kill()
            widget = UIDropDownMenu(
                list(choices), label, self.rects[name], self.dialog.gui.manager,
                container=self.dialog.body,
                object_id=("#transport_destination_dropdown"
                           if self.title == "Destination" else None),
                expansion_height_limit=round(180 * self.dialog.scale),
            )
            setattr(self, name, widget)
        self.choices[name] = choices
        widget.enable() if enabled else widget.disable()

    def refresh(self):
        candidates, state = self.dialog.candidates, self.state
        systems = sorted({u.in_system for u in candidates.values()}, key=str.casefold)
        if state.system not in systems:
            state.system, state.hex_coord = None, None
        hexes = sorted({tuple(u.in_hex) for u in candidates.values()
                        if u.in_system == state.system})
        if state.hex_coord not in hexes:
            state.hex_coord = None
        self._dropdown('system', {'All systems': None, **{s: s for s in systems}}, state.system)
        self._dropdown('hex', {'All hexes': None, **{str(h): h for h in hexes}},
                       state.hex_coord, enabled=state.system is not None)

        query = state.query.strip().casefold()
        id_query = query.removeprefix('#')
        matches = [u for u in candidates.values()
                   if (state.system is None or u.in_system == state.system)
                   and (state.hex_coord is None or u.in_hex == state.hex_coord)
                   and (not query or query in u.name.casefold()
                        or (id_query.isdecimal() and id_query in str(u.id)))]
        if state.unit_id is not None and state.unit_id not in candidates:
            state.unavailable = True
        if state.unit_id not in {u.id for u in matches}:
            state.unit_id = None
        placeholder = "Select a unit…" if matches else "No matching units"
        choices = {placeholder: None}
        choices.update({f"{u.name} #{u.id} — {u.in_system} {u.in_hex}": u.id
                        for u in matches})
        self._dropdown('unit', choices, state.unit_id, enabled=bool(matches))

    def process_event(self, event):
        if event.type == pygame_gui.UI_TEXT_ENTRY_CHANGED and event.ui_element == self.search:
            self.state.query = event.text
        elif event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
            name = next((name for name in self.choices
                         if event.ui_element == getattr(self, name)), None)
            if name is None or event.text not in self.choices[name]:
                return False
            value = self.choices[name][event.text]
            if name == 'system':
                self.state.system, self.state.hex_coord = value, None
            elif name == 'hex':
                self.state.hex_coord = value
            else:
                self.state.unit_id, self.state.unavailable = value, False
        else:
            return False
        self.refresh()
        return True


class AntimatterTransportWindow:
    def __init__(self, gui, unit, source):
        self.gui, self.unit = gui, unit
        self.game = gui.game_instance
        screen = gui.manager.get_root_container().get_rect()
        self.scale = scale = display_config_for(gui).text_scale
        self.row, self.gap = row, gap = round(34 * scale), round(8 * scale)
        pad = round(16 * scale)
        width = min(screen.width - 24, round(900 * scale))
        height = min(screen.height - 24, round(640 * scale))
        self.window = UIWindow(
            pygame.Rect((screen.width - width) // 2, (screen.height - height) // 2,
                        width, height),
            gui.manager, window_display_title="Continuous Antimatter Transport",
        )
        self.window.set_blocking(True)
        content_width, content_height = self.window.get_container().get_size()
        field_width = content_width - 2 * pad
        UILabel(pygame.Rect(pad, pad, field_width, row), f"Transporter: {unit.name}",
                gui.manager, container=self.window)

        button_y = content_height - pad - row
        status_y = button_y - gap - row
        explanation_y = status_y - row
        body_y = pad + row + gap
        self.body = UIScrollingContainer(
            pygame.Rect(pad, body_y, field_width, explanation_y - gap - body_y),
            gui.manager, container=self.window, allow_scroll_x=False,
        )
        section_height = 4 * row + 3 * gap
        swap_y = section_height + gap
        destination_y = swap_y + row + gap
        self.body.set_scrollable_area_dimensions(
            (field_width, destination_y + section_height + gap))
        self.body_width = self.body.get_container().get_size()[0]
        self._refresh_candidates()
        self.source = _EndpointPicker(self, "Source", 0, _EndpointState(
            unit_id=source.id, system=source.in_system, hex_coord=tuple(source.in_hex)))
        self.destination = _EndpointPicker(self, "Destination", destination_y, _EndpointState())
        self.swap = UIButton(
            pygame.Rect(0, swap_y, self.body_width, row), "Swap source and destination",
            gui.manager, container=self.body,
        )
        UILabel(pygame.Rect(pad, explanation_y, field_width, row),
                "Partial loads • Automatic return fuel reserve",
                gui.manager, container=self.window)
        self.status = UILabel(pygame.Rect(pad, status_y, field_width, row), "",
                              gui.manager, container=self.window)
        button_width = (field_width - 2 * gap) // 3
        for index, (name, text) in enumerate((('start', 'Start route'),
                                            ('queue', 'Queue route'), ('cancel', 'Cancel'))):
            setattr(self, name, UIButton(
                pygame.Rect(pad + index * (button_width + gap), button_y, button_width, row),
                text, gui.manager, container=self.window,
            ))
        self._update_actions()

    def _refresh_candidates(self):
        candidates = [u for system in self.game.galaxy.systems.values()
                      for sector in system.hexes.values() for u in sector.units
                      if exchange_blocker(self.unit, u, self.game.galaxy) is None]
        self.candidates = {u.id: u for u in sorted(candidates, key=lambda u: (u.name.casefold(), u.id))}

    def _update_actions(self):
        source, destination = self.source.state, self.destination.state
        if source.unavailable or destination.unavailable:
            missing = 'Source' if source.unavailable else 'Destination'
            message = f"{missing} unit unavailable. Select another unit."
        elif source.unit_id is None or destination.unit_id is None:
            message = "Select a source and a destination."
        elif source.unit_id == destination.unit_id:
            message = "Source and destination must be different units."
        else:
            message = ""
        self.status.set_text(message)
        for button in (self.start, self.queue, self.swap):
            button.disable() if message else button.enable()
        return not message

    def close(self):
        self.window.kill()
        self.gui.antimatter_transport_window = None

    def process_event(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.close()
        elif event.type == pygame_gui.UI_WINDOW_CLOSE and event.ui_element == self.window:
            self.close()
        elif self.source.process_event(event) or self.destination.process_event(event):
            self._update_actions()
        elif event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.cancel:
                self.close()
            elif event.ui_element in (self.start, self.queue, self.swap):
                # Endpoints may have been destroyed, moved, or changed allegiance since opening.
                self._refresh_candidates()
                for picker in (self.source, self.destination):
                    picker.refresh()
                if not self._update_actions():
                    return True
                if event.ui_element == self.swap:
                    self.source.state, self.destination.state = self.destination.state, self.source.state
                    for picker in (self.source, self.destination):
                        picker.search.set_text(picker.state.query)
                        picker.refresh()
                    self._update_actions()
                    return True
                from tactical_ui import issue

                command = {
                    "type": "continuous_antimatter_transport",
                    "unit_ids": [self.unit.id],
                    "source_id": self.source.state.unit_id,
                    "target_id": self.destination.state.unit_id,
                    "queue": event.ui_element == self.queue,
                }
                if issue(self.game, command):
                    self.close()
        return True
