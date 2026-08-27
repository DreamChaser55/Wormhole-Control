"""Tactical communications window for inter-player messaging."""
import logging
import typing
import pygame
import pygame_gui

if typing.TYPE_CHECKING:
    from gui.handler import GUI_Handler
    from entities import Player

logger = logging.getLogger(__name__)


def _color_to_hex(color: typing.Any) -> str:
    """Converts a tuple or pygame.Color to a hex string for HTML formatting."""
    try:
        r = int(color[0])
        g = int(color[1])
        b = int(color[2])
        return f"#{r:02X}{g:02X}{b:02X}"
    except (IndexError, TypeError, ValueError):
        return "#00E5FF"


class CommunicationsWindow:
    """Modal/overlay window for viewing and sending inter-player diplomatic transmissions."""

    def __init__(self, gui: 'GUI_Handler') -> None:
        self.gui = gui
        self.game = gui.game_instance
        self.manager = gui.manager

        window_width = int(640 * gui.scale_x)
        window_height = int(490 * gui.scale_y)
        window_rect = pygame.Rect(
            (gui.screen_res.x - window_width) // 2,
            (gui.screen_res.y - window_height) // 2,
            window_width,
            window_height,
        )

        self.window = pygame_gui.elements.UIWindow(
            rect=window_rect,
            manager=self.manager,
            window_display_title="Diplomatic Subspace Transceiver",
            object_id="#communications_window",
        )

        pad_x = int(12 * gui.scale_x)
        pad_y = int(8 * gui.scale_y)
        content_width = window_width - int(48 * gui.scale_x)

        # Header Info Banner
        header_height = int(32 * gui.scale_y)
        self.header_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(pad_x, pad_y, content_width, header_height),
            text="Subspace Comms Network — Send transmissions to any faction across space.",
            manager=self.manager,
            container=self.window,
            object_id="#comms_header_label",
        )

        # Transmission Log Text Box
        log_y = pad_y + header_height + int(4 * gui.scale_y)
        log_height = int(280 * gui.scale_y)
        self.log_text_box = pygame_gui.elements.UITextBox(
            html_text="",
            relative_rect=pygame.Rect(pad_x, log_y, content_width, log_height),
            manager=self.manager,
            container=self.window,
            object_id="#comms_log_text_box",
        )

        # Recipient Selection & Compose Section
        controls_y = log_y + log_height + int(10 * gui.scale_y)
        row_height = int(34 * gui.scale_y)

        # Recipient Label
        label_width = int(80 * gui.scale_x)
        self.recipient_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(pad_x, controls_y, label_width, row_height),
            text="Recipient:",
            manager=self.manager,
            container=self.window,
            object_id="#comms_recipient_label",
        )

        # Build other players list for dropdown
        self.recipient_map: typing.Dict[str, int] = {}
        dropdown_options: typing.List[str] = []
        current_player = self.game.current_player
        current_id = getattr(current_player, "id", None)

        for p in getattr(self.game, "players", []):
            if p.id != current_id:
                p_type = "Human" if getattr(p, "is_human", True) else f"AI: {getattr(p, 'ai_reasoning_effort', 'medium').capitalize()}"
                display_name = f"{p.name} ({p_type})"
                self.recipient_map[display_name] = p.id
                dropdown_options.append(display_name)

        if not dropdown_options:
            dropdown_options = ["No other factions"]
            self.recipient_map["No other factions"] = -1

        dropdown_width = int(240 * gui.scale_x)
        dropdown_x = pad_x + label_width + int(6 * gui.scale_x)
        self.recipient_dropdown = pygame_gui.elements.UIDropDownMenu(
            options_list=dropdown_options,
            starting_option=dropdown_options[0],
            relative_rect=pygame.Rect(dropdown_x, controls_y, dropdown_width, row_height),
            manager=self.manager,
            container=self.window,
            object_id="#comms_recipient_dropdown",
        )

        # Message Input Row
        input_y = controls_y + row_height + int(10 * gui.scale_y)
        btn_width = int(110 * gui.scale_x)
        input_width = content_width - btn_width - int(8 * gui.scale_x)

        self.message_input = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(pad_x, input_y, input_width, row_height),
            manager=self.manager,
            container=self.window,
            placeholder_text="Type transmission (max 500 chars)...",
            object_id="#comms_message_input",
        )

        self.send_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(pad_x + input_width + int(8 * gui.scale_x), input_y, btn_width, row_height),
            text="Transmit",
            manager=self.manager,
            container=self.window,
            object_id="#comms_send_button",
        )

        # Populate message log
        self.refresh_message_log()

    @property
    def is_alive(self) -> bool:
        """Returns True if the underlying window element is active and alive."""
        return bool(self.window and self.window.alive())

    def refresh_message_log(self) -> None:
        """Refreshes the HTML text content in the message log textbox."""
        if not self.log_text_box or not self.log_text_box.alive():
            return

        current_player = self.game.current_player
        current_id = getattr(current_player, "id", None)
        all_messages = getattr(self.game, "messages", [])

        # Filter messages involving current player
        player_messages = [
            m for m in all_messages
            if m.get("recipient_id") == current_id or m.get("sender_id") == current_id
        ]

        if not player_messages:
            self.log_text_box.set_text(
                "<br><font color='#78909C'><i>[Subspace Log Empty] No transmissions recorded on this frequency yet.<br>"
                "Select a recipient below and transmit a diplomatic message.</i></font>"
            )
            return

        players_by_id = {p.id: p for p in getattr(self.game, "players", [])}
        html_lines = []

        for msg in player_messages:
            turn_sent = msg.get("turn_sent", 1)
            sender_id = msg.get("sender_id", 0)
            recipient_id = msg.get("recipient_id", 0)
            text = msg.get("text", "").replace("<", "&lt;").replace(">", "&gt;")

            sender_player = players_by_id.get(sender_id)
            recipient_player = players_by_id.get(recipient_id)

            sender_name = sender_player.name if sender_player else f"Player {sender_id}"
            recipient_name = recipient_player.name if recipient_player else f"Player {recipient_id}"

            sender_color = _color_to_hex(getattr(sender_player, "color", (0, 229, 255)))
            recipient_color = _color_to_hex(getattr(recipient_player, "color", (255, 255, 255)))

            if sender_id == current_id:
                # Outgoing transmission
                header = (
                    f"<b>[Turn {turn_sent}]</b> "
                    f"<font color='{sender_color}'><b>{sender_name} (You)</b></font> "
                    f"➔ <font color='{recipient_color}'><b>{recipient_name}</b></font>:"
                )
            else:
                # Incoming transmission
                is_new = not msg.get("read_by_recipient", False)
                new_badge = " <font color='#FFEA00'><b>[NEW]</b></font>" if is_new else ""
                header = (
                    f"<b>[Turn {turn_sent}]</b> "
                    f"<font color='{sender_color}'><b>{sender_name}</b></font>{new_badge} "
                    f"➔ <font color='{recipient_color}'><b>{recipient_name} (You)</b></font>:"
                )

            html_lines.append(f"{header}<br>&nbsp;&nbsp;<font color='#ECEFF1'>{text}</font><br>")

        formatted_html = "<br>".join(html_lines)
        self.log_text_box.set_text(formatted_html)

        # Mark incoming messages as read once viewed
        if current_id is not None:
            self.game.mark_messages_as_read(current_id)

    def send_current_message(self) -> bool:
        """Sends the message currently typed in the text entry line to the selected recipient."""
        if not self.message_input or not self.recipient_dropdown:
            return False

        raw = self.recipient_dropdown.selected_option
        selected_display = raw[0] if isinstance(raw, tuple) else str(raw) if raw else None
        if not selected_display:
            return False

        recipient_id = self.recipient_map.get(selected_display, -1)
        if recipient_id < 0:
            return False

        text = self.message_input.get_text().strip()
        if not text:
            return False

        current_player = self.game.current_player
        if not current_player:
            return False

        success = self.game.send_message(current_player, recipient_id, text)
        if success:
            self.message_input.set_text("")
            self.refresh_message_log()
            logger.debug(f"[CommsWindow] Transmitted message to player {recipient_id}: '{text}'")
        return success

    def process_event(self, event: pygame.event.Event) -> typing.Optional[dict]:
        """Processes UI events targeting the communications window.

        Args:
            event (pygame.event.Event): Event to process.

        Returns:
            Optional[dict]: Action payload or None.
        """
        if not self.is_alive:
            return None

        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if self.send_button and event.ui_element == self.send_button:
                self.send_current_message()
                return {'action': 'ui_handled'}

        elif event.type == pygame_gui.UI_TEXT_ENTRY_FINISHED:
            if self.message_input and event.ui_element == self.message_input:
                self.send_current_message()
                return {'action': 'ui_handled'}

        elif event.type == pygame_gui.UI_WINDOW_CLOSE:
            if event.ui_element == self.window:
                self.close()
                return {'action': 'ui_handled'}

        return None

    def close(self) -> None:
        """Closes and kills the communications window."""
        if self.window and self.window.alive():
            self.window.kill()
        self.window = None
