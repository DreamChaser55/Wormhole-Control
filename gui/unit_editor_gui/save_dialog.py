"""
save_dialog.py

Modal confirmation dialog for Unit Designer template saves:
Allows confirming overwrite of an existing template or saving under a new name without modifying the old template.
"""

from __future__ import annotations
import typing
import pygame
import pygame_gui


class SaveConfirmationDialog:
    """Modal dialog prompting the player when saving would overwrite an existing unit design template.

    Provides three distinct actions:
    1. Overwrite: Replaces the existing design with the current modified configuration.
    2. Save as New: Saves the current design under a new name, leaving the original intact.
    3. Cancel: Aborts the save operation without making any changes.
    """

    def __init__(
        self,
        manager: pygame_gui.UIManager,
        screen_res: pygame.Vector2,
        editing_name: str,
        suggested_new_name: typing.Optional[str] = None,
    ):
        self.manager = manager
        self.screen_res = screen_res
        self.editing_name = editing_name

        scale_x = screen_res.x / 1280.0
        scale_y = screen_res.y / 720.0

        win_w = int(520 * scale_x)
        win_h = int(280 * scale_y)
        win_x = int((screen_res.x - win_w) / 2)
        win_y = int((screen_res.y - win_h) / 2)

        self.window = pygame_gui.elements.UIWindow(
            rect=pygame.Rect(win_x, win_y, win_w, win_h),
            manager=manager,
            window_display_title="Save Design Template",
            object_id="#save_confirmation_dialog",
            resizable=False,
        )

        container = self.window.get_container()
        cw, ch = container.get_size()
        pad = int(12 * scale_x)

        # Message explaining the conflict
        msg_h = int(60 * scale_y)
        formatted_html = (
            f"<p>Template <b>'{editing_name}'</b> already exists.</p>"
            f"<p>Overwrite <b>'{editing_name}'</b> or save as a new template?</p>"
        )
        self.msg_box = pygame_gui.elements.UITextBox(
            html_text=formatted_html,
            relative_rect=pygame.Rect(pad, pad, cw - pad * 2, msg_h),
            manager=manager,
            container=container,
            object_id="#save_dialog_message",
        )

        # New Name Label
        lbl_h = int(22 * scale_y)
        lbl_y = pad + msg_h + int(6 * scale_y)
        self.name_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(pad, lbl_y, cw - pad * 2, lbl_h),
            text="Save as New Name:",
            manager=manager,
            container=container,
            object_id="#save_dialog_name_label",
        )

        # New Name Text Entry
        default_name = suggested_new_name if suggested_new_name else f"{editing_name} (Copy)"
        entry_h = int(32 * scale_y)
        entry_y = lbl_y + lbl_h + int(4 * scale_y)
        self.new_name_entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(pad, entry_y, cw - pad * 2, entry_h),
            manager=manager,
            container=container,
            object_id="#save_dialog_name_entry",
            initial_text=default_name,
        )

        # Bottom Action Buttons
        btn_h = int(34 * scale_y)
        btn_y = ch - btn_h - pad
        btn_w = (cw - pad * 4) // 3

        self.overwrite_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(pad, btn_y, btn_w, btn_h),
            text="⚠ Overwrite",
            manager=manager,
            container=container,
            object_id="#save_dialog_overwrite_button",
        )

        self.save_as_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(pad * 2 + btn_w, btn_y, btn_w, btn_h),
            text="➕ Save as New",
            manager=manager,
            container=container,
            object_id="#save_dialog_save_as_button",
        )

        self.cancel_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(pad * 3 + btn_w * 2, btn_y, btn_w, btn_h),
            text="Cancel",
            manager=manager,
            container=container,
            object_id="#save_dialog_cancel_button",
        )

    def process_event(self, event: pygame.event.Event) -> typing.Optional[dict]:
        """Processes pygame GUI events for the save confirmation dialog.

        Returns:
            dict with 'action' ('overwrite', 'save_as_new', 'cancel') if handled, else None.
        """
        if not self.alive():
            return None

        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.overwrite_button:
                return {
                    "action": "overwrite",
                    "target_name": self.editing_name,
                }
            elif event.ui_element == self.save_as_button:
                new_name = self.new_name_entry.get_text().strip() if self.new_name_entry else ""
                return {
                    "action": "save_as_new",
                    "new_name": new_name,
                }
            elif event.ui_element == self.cancel_button:
                return {"action": "cancel"}

        elif event.type == pygame_gui.UI_WINDOW_CLOSE and event.ui_element == self.window:
            return {"action": "cancel"}

        return None

    def kill(self) -> None:
        """Kills the dialog window and destroys child widgets."""
        if self.window and self.window.alive():
            self.window.kill()
        self.window = None

    def alive(self) -> bool:
        """Returns True if the dialog window is still active."""
        return self.window is not None and self.window.alive()
