import os
import unittest
import pygame
import pygame_gui

os.environ["SDL_VIDEODRIVER"] = "dummy"

from geometry import Vector
from gui import GUI_Handler
from game import Game
from custom_unit_templates import CustomTemplateManager, CustomUnitTemplate
from gui.unit_editor_gui.window import UnitEditorWindow
from gui.unit_editor_gui.template_io import do_save, do_delete
from entities import Unit, Player, HullSize, Wormhole
from unit_components import Commander, UnitStance
from unit_orders import MoveOrder
from game_actions import handle_gui_action


class TestGUIModalDialogs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1280, 720))

    def setUp(self):
        self.game = Game()
        self.gui = self.game.gui

    def tearDown(self):
        if self.gui:
            self.gui.clear_and_reset()

    def test_show_message_dialogs(self):
        """Test creating info, warning, and error modal dialogs via GUI_Handler."""
        info_dlg = self.gui.show_info_dialog("Info body message", title="System Info")
        self.assertIsInstance(info_dlg, pygame_gui.windows.UIMessageWindow)
        self.assertEqual(len(self.gui.active_dialogs), 1)

        warn_dlg = self.gui.show_warning_dialog("Warning message", title="Caution")
        self.assertIsInstance(warn_dlg, pygame_gui.windows.UIMessageWindow)
        self.assertEqual(len(self.gui.active_dialogs), 2)

        err_dlg = self.gui.show_error_dialog("Error occurred", title="Critical Failure")
        self.assertIsInstance(err_dlg, pygame_gui.windows.UIMessageWindow)
        self.assertEqual(len(self.gui.active_dialogs), 3)

        # Verify scaled title bar height and close button font sizing
        from constants import TEXT_SCALE
        expected_tb_h = int(30 * TEXT_SCALE)
        self.assertAlmostEqual(info_dlg.title_bar_height, expected_tb_h, delta=2)
        if info_dlg.close_window_button:
            expected_close_font_size = int(18 * TEXT_SCALE)
            self.assertAlmostEqual(info_dlg.close_window_button.font.point_size, expected_close_font_size, delta=2)

    def test_clear_and_reset_cleans_dialogs(self):
        """Test that clear_and_reset destroys active modal dialogs."""
        self.gui.show_warning_dialog("Test warning")
        self.gui.show_error_dialog("Test error")
        self.assertEqual(len(self.gui.active_dialogs), 2)

        self.gui.clear_and_reset()
        self.assertEqual(len(self.gui.active_dialogs), 0)

    def test_save_game_success_and_load_failure_modal(self):
        """Test modal dialogs during save success and load failure."""
        self.game.game_started = True
        self.game.start_new_game()

        # Save game should spawn an info dialog
        save_path = self.game.save_game("test_modal_save.json")
        self.assertIsNotNone(save_path)
        self.assertGreater(len(self.gui.active_dialogs), 0)

        # Clean up save file
        if os.path.exists(save_path):
            os.remove(save_path)

        self.gui.clear_and_reset()

        # Load non-existent save file should spawn an error dialog
        result = self.game.load_game("non_existent_invalid_path.json")
        self.assertFalse(result)
        self.assertGreater(len(self.gui.active_dialogs), 0)
        err_dlg = self.gui.active_dialogs[-1]
        self.assertIn("Load Game Error", err_dlg.window_display_title)

    def test_unit_editor_validation_modal(self):
        """Test unit designer invalid save triggers warning popup."""
        tmp_mgr = CustomTemplateManager()
        editor_win = UnitEditorWindow(self.gui.manager, pygame.Vector2(1280, 720), tmp_mgr)

        # Trying to save without design key should trigger warning modal
        editor_win._name_entry.set_text("")
        editor_win._display_entry.set_text("Display Name")
        res = do_save(editor_win)
        self.assertIsNone(res)

        active_windows = [
            w for w in self.gui.manager.get_sprite_group().sprites()
            if isinstance(w, pygame_gui.windows.UIMessageWindow)
        ]
        self.assertEqual(len(active_windows), 1)

    def test_unit_editor_single_modal_on_event(self):
        """Test that clicking save button in unit editor spawns exactly 1 modal (no double-spawn)."""
        self.gui.open_unit_editor(self.game.custom_template_manager)
        editor = self.gui.unit_editor_window
        editor._name_entry.set_text("")  # Invalid: no design key

        event = pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, {"ui_element": editor._save_button})
        from gui import event_router
        event_router.process_event(self.gui, event)

        active_windows = [
            w for w in self.gui.manager.get_sprite_group().sprites()
            if isinstance(w, pygame_gui.windows.UIMessageWindow)
        ]
        self.assertEqual(len(active_windows), 1)

    def test_disallowed_stance_warning_modal(self):
        """Test setting disallowed stance triggers warning popup dialog."""
        self.game.start_new_game()
        player = self.game.players[0]
        from utils import HexCoord
        from geometry import Position
        unit = Unit(
            name="Test Ship",
            owner=player,
            hull_size=HullSize.MEDIUM,
            position=Position(0, 0),
            in_hex=HexCoord(0, 0),
            in_system="Sol",
            game=self.game
        )
        unit.add_component(Commander(unit))
        unit.commander_component.allowed_stances = [UnitStance.DO_NOTHING]
        self.game.galaxy.systems['Sol'].add_unit(unit)

        action = {'action': 'set_stance', 'unit_id': unit.id, 'stance_display_name': UnitStance.ATTACK_SAME_SYSTEM.display_name}
        handle_gui_action(self.game, action)

        self.assertGreater(len(self.gui.active_dialogs), 0)
        warn_dlg = self.gui.active_dialogs[-1]
        self.assertIn("Invalid Stance", warn_dlg.window_display_title)

    def test_wizard_duplicate_player_colors_warning(self):
        """Test that Start Game with duplicate player colors displays a modal warning dialog."""
        self.gui.show_new_game_wizard()
        wizard = self.gui.new_game_wizard
        self.assertIsNotNone(wizard)

        # Force identical colors for active players (e.g. both palette index 0)
        wizard._player_color_indices[0] = 0
        wizard._player_color_indices[1] = 0

        self.assertTrue(wizard.has_duplicate_colors())

        # Simulate pressing Start Game button
        event = pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, {"ui_element": wizard.start_button})
        from gui import event_router
        action = event_router.process_event(self.gui, event)

        # Should be handled by GUI (modal dialog shown), not start new game
        self.assertEqual(action, {'action': 'ui_handled'})
        self.assertGreater(len(self.gui.active_dialogs), 0)
        warn_dlg = self.gui.active_dialogs[-1]
        self.assertIn("Duplicate Player Colors", warn_dlg.window_display_title)
        self.assertTrue(wizard.is_alive)

        # Ensure drawing GUI with modal dialog open clips swatches cleanly
        dummy_surface = pygame.Surface((1280, 720))
        self.gui.draw(dummy_surface)

        # Now assign unique colors
        wizard._player_color_indices[0] = 0
        wizard._player_color_indices[1] = 1
        wizard._player_color_indices[2] = 2
        self.assertFalse(wizard.has_duplicate_colors())

        # Press Start Game again
        action = event_router.process_event(self.gui, event)
        self.assertEqual(action['action'], 'start_new_game_with_settings')


if __name__ == '__main__':
    unittest.main()
