"""In-game menu (pause menu) and load game dialog layout functions."""
import typing

import pygame
import pygame_gui

from game_ai.runtime import (
    MAX_REPAIR_RETRIES,
    MIN_REPAIR_RETRIES,
    normalize_repair_retries,
)

_INGAME_MENU_BUTTONS = [
    ('resume_button', 'Resume', '#resume_button'),
    ('ai_settings_button', 'AI Settings', '#ai_settings_button'),
    ('unit_editor_button', 'Unit Editor', '#unit_editor_button'),
    ('save_game_button', 'Save Game', '#save_game_button'),
    ('ingame_load_game_button', 'Load Game', '#ingame_load_game_button'),
    ('quit_to_menu_button', 'Quit to Main Menu', '#quit_to_menu_button'),
]


class AISettingsDialog:
    """Modal editor for per-AI semantic-repair retry limits."""

    def __init__(self, gui) -> None:
        self.gui = gui
        self.ai_players = [
            player
            for player in getattr(gui.game_instance, "players", [])
            if not getattr(player, "is_human", True)
        ]
        self.values = {
            str(player.agent_id): normalize_repair_retries(
                getattr(player, "ai_repair_retries", None)
            )
            for player in self.ai_players
        }
        self.minus_buttons: typing.List[pygame_gui.elements.UIButton] = []
        self.plus_buttons: typing.List[pygame_gui.elements.UIButton] = []
        self.value_labels: typing.List[pygame_gui.elements.UILabel] = []

        window_width = int(520 * gui.scale_x)
        row_height = int(42 * gui.scale_y)
        window_height = int((170 + 42 * len(self.ai_players)) * gui.scale_y)
        window_rect = pygame.Rect(
            (gui.screen_res.x - window_width) // 2,
            (gui.screen_res.y - window_height) // 2,
            window_width,
            window_height,
        )
        self.window = pygame_gui.elements.UIWindow(
            rect=window_rect,
            manager=gui.manager,
            window_display_title="AI Settings",
            object_id="#ai_settings_window",
        )

        pad_x = int(16 * gui.scale_x)
        content_width = window_width - int(48 * gui.scale_x)
        pygame_gui.elements.UITextBox(
            html_text=(
                "Repair retries are additional requests made after invalid AI "
                "output. Changes take effect on each AI player's next turn."
            ),
            relative_rect=pygame.Rect(
                pad_x, int(8 * gui.scale_y), content_width, int(52 * gui.scale_y)
            ),
            manager=gui.manager,
            container=self.window,
            object_id="#ai_settings_explanation",
        )

        name_width = int(290 * gui.scale_x)
        control_width = int(38 * gui.scale_x)
        y = int(66 * gui.scale_y)
        for index, player in enumerate(self.ai_players):
            pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(pad_x, y, name_width, row_height),
                text=str(player.name),
                manager=gui.manager,
                container=self.window,
                object_id="#ai_settings_player_name",
            )
            controls_x = pad_x + name_width
            minus = pygame_gui.elements.UIButton(
                relative_rect=pygame.Rect(
                    controls_x, y, control_width, row_height
                ),
                text="−",
                manager=gui.manager,
                container=self.window,
                object_id=f"#ai_repair_retries_minus_{index}",
            )
            value = pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(
                    controls_x + control_width, y, control_width, row_height
                ),
                text=str(self.values[str(player.agent_id)]),
                manager=gui.manager,
                container=self.window,
                object_id=f"#ai_repair_retries_value_{index}",
            )
            plus = pygame_gui.elements.UIButton(
                relative_rect=pygame.Rect(
                    controls_x + control_width * 2, y, control_width, row_height
                ),
                text="+",
                manager=gui.manager,
                container=self.window,
                object_id=f"#ai_repair_retries_plus_{index}",
            )
            self.minus_buttons.append(minus)
            self.value_labels.append(value)
            self.plus_buttons.append(plus)
            y += row_height

        button_width = int(120 * gui.scale_x)
        button_height = int(36 * gui.scale_y)
        button_y = window_height - int(76 * gui.scale_y)
        center_x = window_width // 2
        self.apply_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(
                center_x - button_width - int(8 * gui.scale_x),
                button_y,
                button_width,
                button_height,
            ),
            text="Apply",
            manager=gui.manager,
            container=self.window,
            object_id="#ai_settings_apply_button",
        )
        self.cancel_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(
                center_x + int(8 * gui.scale_x),
                button_y,
                button_width,
                button_height,
            ),
            text="Cancel",
            manager=gui.manager,
            container=self.window,
            object_id="#ai_settings_cancel_button",
        )
        self._refresh_bounds()

    @property
    def is_alive(self) -> bool:
        return self.window is not None and self.window.alive()

    def kill(self) -> None:
        if self.is_alive:
            self.window.kill()

    def _refresh_bounds(self) -> None:
        for index, player in enumerate(self.ai_players):
            current = self.values[str(player.agent_id)]
            self.value_labels[index].set_text(str(current))
            if current <= MIN_REPAIR_RETRIES:
                self.minus_buttons[index].disable()
            else:
                self.minus_buttons[index].enable()
            if current >= MAX_REPAIR_RETRIES:
                self.plus_buttons[index].disable()
            else:
                self.plus_buttons[index].enable()

    def process_event(self, event: pygame.event.Event) -> typing.Optional[dict]:
        if event.type != pygame_gui.UI_BUTTON_PRESSED:
            return None
        element = event.ui_element
        for index, button in enumerate(self.minus_buttons):
            if element is button:
                agent_id = str(self.ai_players[index].agent_id)
                self.values[agent_id] = max(
                    MIN_REPAIR_RETRIES, self.values[agent_id] - 1
                )
                self._refresh_bounds()
                return {"action": "ui_handled"}
        for index, button in enumerate(self.plus_buttons):
            if element is button:
                agent_id = str(self.ai_players[index].agent_id)
                self.values[agent_id] = min(
                    MAX_REPAIR_RETRIES, self.values[agent_id] + 1
                )
                self._refresh_bounds()
                return {"action": "ui_handled"}
        if element is self.apply_button:
            values = dict(self.values)
            self.gui.close_ai_settings_dialog()
            return {
                "action": "update_ai_repair_retries",
                "values": values,
            }
        if element is self.cancel_button:
            self.gui.close_ai_settings_dialog()
            return {"action": "ui_handled"}
        return None


def setup_ingame_menu(gui) -> None:
    """Initializes the Pygame GUI elements for the in-game menu interface.

    Args:
        gui: Target GUI_Handler instance.
    """
    num_buttons = len(_INGAME_MENU_BUTTONS)
    button_height = int(40 * gui.scale_y)
    button_width = int(200 * gui.scale_x)
    internal_padding = int(15 * gui.scale_y)
    panel_width = int(300 * gui.scale_x)
    panel_height = internal_padding + num_buttons * (button_height + internal_padding)

    menu_rect = pygame.Rect(
        (gui.screen_res.x - panel_width) // 2,
        (gui.screen_res.y - panel_height) // 2,
        panel_width,
        panel_height
    )
    gui.ingame_menu_panel = pygame_gui.elements.UIPanel(
        relative_rect=menu_rect,
        starting_height=2,
        manager=gui.manager,
        object_id='#ingame_menu_panel'
    )

    current_y = internal_padding

    for attr_name, text, object_id in _INGAME_MENU_BUTTONS:
        button_rel_rect = pygame.Rect(
            (panel_width - button_width) // 2,
            current_y,
            button_width,
            -1
        )
        button = pygame_gui.elements.UIButton(
            relative_rect=button_rel_rect,
            text=text,
            manager=gui.manager,
            container=gui.ingame_menu_panel,
            object_id=object_id
        )
        setattr(gui, attr_name, button)
        current_y += button_height + internal_padding

    refresh_ai_settings_button(gui)


def refresh_ai_settings_button(gui) -> None:
    button = getattr(gui, "ai_settings_button", None)
    if button is None:
        return
    has_ai_players = any(
        not getattr(player, "is_human", True)
        for player in getattr(gui.game_instance, "players", [])
    )
    if has_ai_players:
        button.enable()
    else:
        button.disable()


def show_load_game_dialog(gui) -> None:
    """Displays a dialog window listing available save files to load.

    Args:
        gui: Target GUI_Handler instance.
    """
    import save_manager
    saves = save_manager.list_save_files()

    window_width = int(520 * gui.scale_x)
    window_height = int(420 * gui.scale_y)
    window_rect = pygame.Rect(
        (gui.screen_res.x - window_width) // 2,
        (gui.screen_res.y - window_height) // 2,
        window_width,
        window_height
    )

    if gui.load_save_window and gui.load_save_window.alive():
        gui.load_save_window.kill()

    gui.load_save_window = pygame_gui.elements.UIWindow(
        rect=window_rect,
        manager=gui.manager,
        window_display_title="Load Saved Game",
        object_id='#load_game_window'
    )

    item_list = []
    gui.save_file_paths = {}
    for s in saves:
        display_text = f"{s['filename']} (Turn {s['turn_number']} - {s['current_system']})"
        item_list.append(display_text)
        gui.save_file_paths[display_text] = s['filepath']

    if not item_list:
        item_list = ["No saved games found."]

    list_rect = pygame.Rect(int(10 * gui.scale_x), int(10 * gui.scale_y), window_width - int(45 * gui.scale_x), int(290 * gui.scale_y))
    gui.load_save_selection_list = pygame_gui.elements.UISelectionList(
        relative_rect=list_rect,
        item_list=item_list,
        manager=gui.manager,
        container=gui.load_save_window,
        object_id='#save_selection_list'
    )

    btn_w = int(120 * gui.scale_x)
    btn_h = int(35 * gui.scale_y)
    btn_y = int(315 * gui.scale_y)

    gui.load_save_confirm_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((window_width // 2 - btn_w - 10, btn_y), (btn_w, btn_h)),
        text='Load',
        manager=gui.manager,
        container=gui.load_save_window,
        object_id='#load_confirm_button'
    )

    gui.load_save_cancel_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((window_width // 2 + 10, btn_y), (btn_w, btn_h)),
        text='Cancel',
        manager=gui.manager,
        container=gui.load_save_window,
        object_id='#load_cancel_button'
    )
