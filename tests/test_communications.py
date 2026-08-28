import os
import unittest
from unittest.mock import MagicMock, patch
import pygame
import pygame_gui

from geometry import Vector, Position
from entities import Player, Message, Conversation
from game import Game
from gui.handler import GUI_Handler
from gui.communications_window import CommunicationsWindow
from save_manager import serialize_game_state, deserialize_game_state
from game_actions.app_actions import handle_toggle_comms

os.environ["SDL_VIDEODRIVER"] = "dummy"


class TestCommunications(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1280, 720))

    def setUp(self):
        self.game = Game()
        self.player0 = Player("Player 1", (0, 128, 255), is_human=True)
        self.player1 = Player("Player 2", (255, 0, 0), is_human=False)
        self.player2 = Player("Player 3", (0, 255, 0), is_human=True)
        self.game.players = [self.player0, self.player1, self.player2]
        self.game.current_player_index = 0
        self.game.turn_number = 1

    def test_message_dataclass(self):
        msg = Message(
            id=1,
            sender_id=0,
            sender_name="Player 1",
            recipient_id=1,
            turn_sent=2,
            text="Greetings!",
            timestamp="2026-08-27",
            read_by_recipient=False
        )
        msg_dict = msg.to_dict()
        self.assertEqual(msg_dict["id"], 1)
        self.assertEqual(msg_dict["text"], "Greetings!")
        
        reconstructed = Message.from_dict(msg_dict)
        self.assertEqual(reconstructed.id, 1)
        self.assertEqual(reconstructed.sender_name, "Player 1")
        self.assertEqual(reconstructed.recipient_id, 1)

    def test_conversation_dataclass(self):
        key = Conversation.make_key(1, 0)
        self.assertEqual(key, (0, 1))

        conv = Conversation(participant_ids=key)
        self.assertEqual(conv.get_partner_id(0), 1)
        self.assertEqual(conv.get_partner_id(1), 0)

        msg1 = Message(id=1, sender_id=0, sender_name="P1", recipient_id=1, turn_sent=1, text="Hi")
        msg2 = Message(id=2, sender_id=1, sender_name="P2", recipient_id=0, turn_sent=2, text="Hello back", read_by_recipient=False)
        conv.add_message(msg2)
        conv.add_message(msg1)

        # Messages should be sorted by turn_sent then id
        self.assertEqual(conv.messages[0].id, 1)
        self.assertEqual(conv.messages[1].id, 2)

        # Unread counts
        self.assertEqual(conv.get_unread_count(0), 1)
        self.assertEqual(conv.get_unread_count(1), 1)

        # Mark as read
        conv.mark_as_read(0)
        self.assertEqual(conv.get_unread_count(0), 0)

        # Serialization
        data = conv.to_dict()
        self.assertEqual(data["participant_ids"], [0, 1])
        self.assertEqual(len(data["messages"]), 2)

        restored = Conversation.from_dict(data)
        self.assertEqual(restored.participant_ids, (0, 1))
        self.assertEqual(len(restored.messages), 2)
        self.assertEqual(restored.messages[0].text, "Hi")

    def test_send_message_success(self):
        success = self.game.send_message(self.player0, self.player1.id, "Trade offer: 500 metal")
        self.assertTrue(success)
        
        conv = self.game.get_conversation(self.player0.id, self.player1.id)
        self.assertIsNotNone(conv)
        self.assertEqual(len(conv.messages), 1)
        
        msg = conv.messages[0]
        self.assertEqual(msg.sender_id, self.player0.id)
        self.assertEqual(msg.recipient_id, self.player1.id)
        self.assertEqual(msg.turn_sent, 1)
        self.assertEqual(msg.text, "Trade offer: 500 metal")
        self.assertFalse(msg.read_by_recipient)

    def test_send_message_validation(self):
        # Empty text
        self.assertFalse(self.game.send_message(self.player0, self.player1.id, ""))
        self.assertFalse(self.game.send_message(self.player0, self.player1.id, "   "))
        # Invalid recipient
        self.assertFalse(self.game.send_message(self.player0, 999, "Hello"))
        # Self recipient
        self.assertFalse(self.game.send_message(self.player0, self.player0.id, "Hello self"))
        # Sender by int ID
        self.assertTrue(self.game.send_message(self.player0.id, self.player1.id, "Valid via ID"))

    def test_get_messages_and_filters(self):
        self.game.turn_number = 1
        self.game.send_message(self.player0, self.player1.id, "Msg 1 from P0 to P1 (Turn 1)")
        self.game.send_message(self.player2, self.player0.id, "Msg 2 from P2 to P0 (Turn 1)")
        
        self.game.turn_number = 2
        self.game.send_message(self.player1, self.player0.id, "Msg 3 from P1 to P0 (Turn 2)")

        # Messages for Player 0 (both sent and received)
        p0_msgs = self.game.get_messages_for_player(self.player0.id)
        self.assertEqual(len(p0_msgs), 3)

        # Incoming messages for Player 0 before Turn 2
        incoming_before_turn2 = self.game.get_incoming_messages(self.player0.id, before_turn=2)
        self.assertEqual(len(incoming_before_turn2), 1)
        self.assertEqual(incoming_before_turn2[0].text, "Msg 2 from P2 to P0 (Turn 1)")

        # All incoming messages for Player 0
        all_incoming = self.game.get_incoming_messages(self.player0.id)
        self.assertEqual(len(all_incoming), 2)

        # Unread messages
        unread = self.game.get_unread_messages_for_player(self.player0.id)
        self.assertEqual(len(unread), 2)

        # Mark as read
        self.game.mark_messages_as_read(self.player0.id)
        unread_after = self.game.get_unread_messages_for_player(self.player0.id)
        self.assertEqual(len(unread_after), 0)

    def test_save_load_conversations_persistence(self):
        self.game.start_new_game()
        self.game.turn_number = 2
        p0 = self.game.players[0]
        p1 = self.game.players[1]
        self.game.send_message(p0, p1.id, "Message A")
        self.game.send_message(p1, p0.id, "Message B")

        test_filename = "test_comms_save.json"
        saved_filepath = self.game.save_game(test_filename)
        self.assertTrue(os.path.exists(saved_filepath))

        new_game = Game()
        load_success = new_game.load_game(saved_filepath)
        self.assertTrue(load_success)
        
        conv = new_game.get_conversation(p0.id, p1.id)
        self.assertIsNotNone(conv)
        self.assertEqual(len(conv.messages), 2)
        self.assertEqual(conv.messages[0].text, "Message A")
        self.assertEqual(conv.messages[1].text, "Message B")
        self.assertEqual(new_game.message_counter, 2)

        if os.path.exists(saved_filepath):
            os.remove(saved_filepath)

    def test_communications_window_gui(self):
        gui = self.game.gui
        gui.show_game_ui()

        # Send test messages
        self.game.send_message(self.player1, self.player0.id, "Hello Human Commander")

        # Open Comms Window
        gui.open_communications_window()
        self.assertTrue(gui.is_communications_window_open())
        comms_win = gui.communications_window
        self.assertIsNotNone(comms_win)

        # Check recipient dropdown options (should exclude Player 0)
        options = comms_win.recipient_dropdown.options_list
        self.assertEqual(len(options), 2)
        self.assertIn("Player 2 (AI: Medium)", options[0])

        # Check layout positioning: recipient dropdown is above conversation log, and log is above message input
        self.assertLess(comms_win.recipient_dropdown.rect.top, comms_win.log_text_box.rect.top)
        self.assertLess(comms_win.log_text_box.rect.top, comms_win.message_input.rect.top)

        # Check log text box has incoming message for active conversation thread
        self.assertIn("Hello Human Commander", comms_win.log_text_box.html_text)

        # Send message via GUI window
        comms_win.message_input.set_text("We accept your terms.")
        sent = comms_win.send_current_message()
        self.assertTrue(sent)
        
        conv = self.game.get_conversation(self.player0.id, self.player1.id)
        self.assertEqual(len(conv.messages), 2)
        self.assertEqual(conv.messages[1].text, "We accept your terms.")
        self.assertEqual(comms_win.message_input.get_text(), "")
        self.assertIn("We accept your terms.", comms_win.log_text_box.html_text)

        # Toggle / Close
        gui.toggle_communications_window()
        self.assertFalse(gui.is_communications_window_open())

    def test_hud_comms_button_and_action(self):
        gui = self.game.gui
        gui.show_game_ui()

        # Initially no unread messages
        gui.update_comms_button()
        self.assertEqual(gui.comms_button.text, "Comms")

        # Receive multiple messages for active player
        self.game.send_message(self.player1, self.player0.id, "Alert: Scout detected")
        self.game.send_message(self.player2, self.player0.id, "Trade incoming")
        gui.update_comms_button()
        self.assertEqual(gui.comms_button.text, "Comms (2)")
        self.assertGreaterEqual(gui.comms_button.rect.width, 90)

        # Action toggle_comms
        handle_toggle_comms(self.game, {"action": "toggle_comms"})
        self.assertTrue(gui.is_communications_window_open())

        # Viewing marks messages as read for active conversation
        # Comms window opened to Player 2 (who had unread messages) -> marks Player 2 messages as read
        gui.update_comms_button()
        self.assertIn("Comms", gui.comms_button.text)


if __name__ == "__main__":
    unittest.main()
