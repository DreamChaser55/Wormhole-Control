"""Editor-owned modal for equipment help."""

import pygame
import pygame_gui

from display_config import DisplayConfig


class _DescriptionWindow(pygame_gui.elements.UIWindow):
    def process_event(self, event: pygame.event.Event) -> bool:
        # Children get events first. Consume remaining pointer events here so
        # scrolling or releasing a mouse button cannot reach the editor below.
        return super().process_event(event) or event.type in (
            pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION, pygame.MOUSEWHEEL,
        )


class DescriptionDialog:
    def __init__(self, manager: pygame_gui.UIManager, config: DisplayConfig, title: str, body: str):
        scale = config.text_scale
        margin = max(8, int(20 * scale))
        width = min(int(600 * config.width / 1280), config.width - 2 * margin)
        height = min(int(420 * config.height / 720), config.height - 2 * margin)
        rect = pygame.Rect((config.width - width) // 2, (config.height - height) // 2, width, height)
        self.window = _DescriptionWindow(
            rect, manager, window_display_title=title, resizable=False,
            object_id="#editor_description_dialog",
        )
        self.window.set_blocking(True)
        container = self.window.get_container()
        width, height = container.get_size()
        pad = max(6, int(12 * scale))
        button_h = max(24, int(32 * scale))
        button_w = max(70, int(100 * scale))
        self.text_box = pygame_gui.elements.UITextBox(
            body, pygame.Rect(pad, pad, width - 2 * pad, height - button_h - 3 * pad),
            manager, container=container,
        )
        self.close_button = pygame_gui.elements.UIButton(
            pygame.Rect(width - pad - button_w, height - pad - button_h, button_w, button_h),
            "Close", manager, container=container,
        )

    def process_event(self, event: pygame.event.Event) -> bool:
        """Return True on dismissal, including the native window close event."""
        if (event.type == pygame_gui.UI_BUTTON_PRESSED and event.ui_element is self.close_button
                or event.type == pygame_gui.UI_WINDOW_CLOSE and event.ui_element is self.window):
            self.kill()
            return True
        return False

    def owns_element(self, element) -> bool:
        """Identify dialog UI events, including nested scrollbar controls."""
        if element in (self.window, self.window.close_window_button, self.window.title_bar):
            return True
        container = self.window.get_container()
        while element is not None:
            if element is container:
                return True
            parent = getattr(element, "ui_container", None)
            if parent is element:
                break
            element = parent
        return False

    def kill(self) -> None:
        self.window.kill()
