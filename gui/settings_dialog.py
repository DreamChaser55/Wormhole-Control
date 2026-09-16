"""Shared application settings editor for both menus."""
import pygame
import pygame_gui

from app_preferences import AppPreferences, TurnSummaryMode, save_preferences

MODE_LABELS = {
    TurnSummaryMode.ALWAYS: "Always show turn summary",
    TurnSummaryMode.AUTOMATIC: "Automatic",
    TurnSummaryMode.NEVER: "Do not show turn summary",
}


def is_open(gui):
    dialog = getattr(gui, "settings_dialog", None)
    return isinstance(dialog, SettingsDialog) and dialog.window.alive()


class SettingsDialog:
    def __init__(self, gui):
        self.gui = gui
        self.mode = gui.game_instance.preferences.turn_summary_mode
        width = min(int(gui.screen_res.x) - 24, int(640 * gui.scale_x))
        height = min(int(gui.screen_res.y) - 24, int(440 * gui.scale_y))
        self.window = pygame_gui.elements.UIWindow(
            pygame.Rect((gui.screen_res.x - width) // 2, (gui.screen_res.y - height) // 2, width, height),
            manager=gui.manager, window_display_title="Settings", resizable=False)
        self.window.set_blocking(True)
        content_width, content_height = self.window.get_container().get_size()
        pad = max(8, int(14 * gui.scale_x))
        row = max(30, int(42 * gui.scale_y))
        inner_width = content_width - 2 * pad
        pygame_gui.elements.UILabel(
            pygame.Rect(pad, pad, inner_width, row), "Turn summary mode",
            manager=gui.manager, container=self.window)
        self.dropdown = pygame_gui.elements.UIDropDownMenu(
            list(MODE_LABELS.values()), MODE_LABELS[self.mode],
            pygame.Rect(pad, pad + row, inner_width, row), manager=gui.manager, container=self.window)
        self.explanation = pygame_gui.elements.UITextBox(
            "Always: includes quiet turns.<br>Automatic: significant events only.<br>"
            "Do not show: no automatic popups.<br><br>"
            "Applies to all campaigns and human players. You can always open Esc → Turn Summary.",
            pygame.Rect(pad, pad + 2 * row, inner_width, content_height - 4 * row - 3 * pad),
            manager=gui.manager, container=self.window)
        self.error = pygame_gui.elements.UILabel(
            pygame.Rect(pad, content_height - 2 * row - pad, inner_width, row), "",
            manager=gui.manager, container=self.window)
        button_width = int(120 * gui.scale_x)
        self.apply_button = pygame_gui.elements.UIButton(
            pygame.Rect(content_width - 2 * button_width - 2 * pad, content_height - row - pad, button_width, row),
            "Apply", manager=gui.manager, container=self.window)
        self.cancel_button = pygame_gui.elements.UIButton(
            pygame.Rect(content_width - button_width - pad, content_height - row - pad, button_width, row),
            "Cancel", manager=gui.manager, container=self.window)

    def owns(self, element):
        while element is not None:
            if element in (self.window, self.window.get_container(), self.window.close_window_button):
                return True
            parent = getattr(element, "ui_container", None)
            if parent is element:
                return False
            element = parent
        return False

    def process_event(self, event):
        element = getattr(event, "ui_element", None)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.gui.close_settings_dialog()
            return
        if event.type == pygame_gui.UI_WINDOW_CLOSE and element is self.window:
            self.gui.close_settings_dialog()
            return
        if element is not None and not self.owns(element):
            return
        if event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED and element is self.dropdown:
            self.mode = next(mode for mode, label in MODE_LABELS.items() if label == event.text)
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if element in (self.cancel_button, self.window.close_window_button):
                self.gui.close_settings_dialog()
                return
            if element is self.apply_button:
                preferences = AppPreferences(self.mode)
                try:
                    save_preferences(preferences)
                except (OSError, ValueError):
                    self.error.set_text("Could not save settings. Please try again.")
                    return
                self.gui.game_instance.preferences = preferences
                self.gui.close_settings_dialog()
                return
        self.gui.manager.process_events(event)
