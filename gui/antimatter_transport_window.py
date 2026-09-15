"""A modal for configuring a fixed antimatter delivery route."""

import pygame
import pygame_gui
from pygame_gui.elements import UIWindow, UILabel, UIDropDownMenu, UIButton

from antimatter_logistics import exchange_blocker


def is_open(gui):
    dialog = getattr(gui, "antimatter_transport_window", None)
    return bool(dialog and dialog.window.alive() is True)


class AntimatterTransportWindow:
    def __init__(self, gui, unit, source):
        self.gui, self.unit = gui, unit
        self.game = gui.game_instance
        screen = gui.manager.get_root_container().get_rect()
        scale = max(1.0, screen.height / 720.0)
        width = min(screen.width - 24, round(760 * scale))
        height = min(screen.height - 24, round(380 * scale))
        self.window = UIWindow(
            pygame.Rect(
                (screen.width - width) // 2,
                (screen.height - height) // 2,
                width,
                height,
            ),
            gui.manager,
            window_display_title="Continuous Antimatter Transport",
        )
        self.window.set_blocking(True)
        content_width, content_height = self.window.get_container().get_size()
        pad = round(20 * scale)
        gap = round(16 * scale)
        row_height = round(40 * scale)
        label_width = round(125 * scale)
        field_x = pad + label_width + gap
        field_width = content_width - field_x - pad
        button_width = (content_width - 2 * pad - 2 * gap) // 3
        button_y = content_height - pad - row_height
        candidates = [
            candidate
            for system in self.game.galaxy.systems.values()
            for sector in system.hexes.values()
            for candidate in sector.units
            if exchange_blocker(unit, candidate, self.game.galaxy) is None
        ]
        candidates.sort(key=lambda u: (u.name, u.id))
        self.targets = {
            f"{u.name} #{u.id} — {u.in_system} {u.in_hex}": u.id for u in candidates
        }
        choices = list(self.targets)
        source_label = next(
            label for label, uid in self.targets.items() if uid == source.id
        )
        destination_label = next(
            (label for label in choices if label != source_label), source_label
        )
        UILabel(
            pygame.Rect(pad, pad, content_width - 2 * pad, row_height),
            f"Transporter: {unit.name}",
            gui.manager,
            container=self.window,
        )
        UILabel(
            pygame.Rect(pad, round(80 * scale), label_width, row_height),
            "Source",
            gui.manager,
            container=self.window,
        )
        self.source = UIDropDownMenu(
            choices,
            source_label,
            pygame.Rect(field_x, round(80 * scale), field_width, row_height),
            gui.manager,
            container=self.window,
        )
        UILabel(
            pygame.Rect(pad, round(140 * scale), label_width, row_height),
            "Destination",
            gui.manager,
            container=self.window,
        )
        self.destination = UIDropDownMenu(
            choices,
            destination_label,
            pygame.Rect(field_x, round(140 * scale), field_width, row_height),
            gui.manager,
            container=self.window,
        )
        UILabel(
            pygame.Rect(pad, round(200 * scale), content_width - 2 * pad, row_height),
            "Partial loads • Automatic return fuel reserve",
            gui.manager,
            container=self.window,
        )
        self.start = UIButton(
            pygame.Rect(pad, button_y, button_width, row_height),
            "Start route",
            gui.manager,
            container=self.window,
        )
        self.queue = UIButton(
            pygame.Rect(pad + button_width + gap, button_y, button_width, row_height),
            "Queue route",
            gui.manager,
            container=self.window,
        )
        self.cancel = UIButton(
            pygame.Rect(
                content_width - pad - button_width, button_y, button_width, row_height
            ),
            "Cancel",
            gui.manager,
            container=self.window,
        )

    def close(self):
        self.window.kill()
        self.gui.antimatter_transport_window = None

    @staticmethod
    def selected(dropdown):
        value = dropdown.selected_option
        return value[0] if isinstance(value, tuple) else value

    def process_event(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.close()
        elif (
            event.type == pygame_gui.UI_WINDOW_CLOSE and event.ui_element == self.window
        ):
            self.close()
        elif event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.cancel:
                self.close()
            elif event.ui_element in (self.start, self.queue):
                from tactical_ui import issue

                command = {
                    "type": "continuous_antimatter_transport",
                    "unit_ids": [self.unit.id],
                    "source_id": self.targets[self.selected(self.source)],
                    "target_id": self.targets[self.selected(self.destination)],
                    "queue": event.ui_element == self.queue,
                }
                if issue(self.game, command):
                    self.close()
        return True
