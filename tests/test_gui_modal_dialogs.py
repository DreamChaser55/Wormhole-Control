from player_controller import PlayerController
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
        import tempfile
        import custom_unit_templates as ctm
        self._temp_data_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self._temp_data_file.close()
        self._orig_data_file = ctm._DATA_FILE
        ctm._DATA_FILE = self._temp_data_file.name

        self.game = Game()
        self.gui = self.game.gui

    def tearDown(self):
        if self.gui:
            self.gui.clear_and_reset()
        import custom_unit_templates as ctm
        ctm._DATA_FILE = self._orig_data_file
        if os.path.exists(self._temp_data_file.name):
            os.remove(self._temp_data_file.name)

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

    def test_ai_settings_button_is_disabled_without_ai_players(self):
        self.game.players = [Player("Human", (10, 20, 30), controller=PlayerController.HUMAN)]
        self.gui.show_ingame_menu()
        self.assertIsNotNone(self.gui.ai_settings_button)
        self.assertFalse(self.gui.ai_settings_button.is_enabled)

    def test_ai_settings_dialog_bounds_cancel_and_atomic_apply(self):
        human = Player("Human", (10, 20, 30), controller=PlayerController.HUMAN)
        ai_one = Player(
            "AI One",
            (40, 50, 60),
            controller=PlayerController.OPENAI,
            agent_id="ai-one",
            ai_repair_retries=2,
        )
        ai_two = Player(
            "AI Two",
            (70, 80, 90),
            controller=PlayerController.OPENAI,
            agent_id="ai-two",
            ai_repair_retries=4,
        )
        self.game.players = [human, ai_one, ai_two]
        self.game.game_started = True
        self.gui.show_ingame_menu()
        self.assertTrue(self.gui.ai_settings_button.is_enabled)

        from gui import event_router

        open_event = pygame.event.Event(
            pygame_gui.UI_BUTTON_PRESSED,
            {"ui_element": self.gui.ai_settings_button},
        )
        self.assertEqual(
            event_router.process_event(self.gui, open_event),
            {"action": "ui_handled"},
        )
        dialog = self.gui.ai_settings_dialog
        self.assertEqual([p.name for p in dialog.ai_players], ["AI One", "AI Two"])

        for _ in range(10):
            dialog.process_event(
                pygame.event.Event(
                    pygame_gui.UI_BUTTON_PRESSED,
                    {"ui_element": dialog.plus_buttons[0]},
                )
            )
            dialog.process_event(
                pygame.event.Event(
                    pygame_gui.UI_BUTTON_PRESSED,
                    {"ui_element": dialog.minus_buttons[1]},
                )
            )
        self.assertEqual(dialog.values["ai-one"], 5)
        self.assertEqual(dialog.values["ai-two"], 1)
        self.assertFalse(dialog.plus_buttons[0].is_enabled)
        self.assertFalse(dialog.minus_buttons[1].is_enabled)

        dialog.process_event(
            pygame.event.Event(
                pygame_gui.UI_BUTTON_PRESSED,
                {"ui_element": dialog.cancel_button},
            )
        )
        self.assertEqual(ai_one.ai_repair_retries, 2)
        self.assertEqual(ai_two.ai_repair_retries, 4)

        self.gui.show_ai_settings_dialog()
        dialog = self.gui.ai_settings_dialog
        dialog.values["ai-one"] = 3
        dialog.values["ai-two"] = 5
        self.game.ai_coordinator.state = "thinking"
        apply_action = dialog.process_event(
            pygame.event.Event(
                pygame_gui.UI_BUTTON_PRESSED,
                {"ui_element": dialog.apply_button},
            )
        )
        self.game.handle_gui_action(apply_action)
        self.game.ai_coordinator.state = "idle"
        self.assertEqual(ai_one.ai_repair_retries, 3)
        self.assertEqual(ai_two.ai_repair_retries, 5)
        self.assertIsNone(self.gui.ai_settings_dialog)

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

        # Trying to save without display name should trigger warning modal
        editor_win._display_entry.set_text("")
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
        editor._display_entry.set_text("")  # Invalid: no display name

        event = pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, {"ui_element": editor._save_button})
        from gui import event_router
        event_router.process_event(self.gui, event)

        active_windows = [
            w for w in self.gui.manager.get_sprite_group().sprites()
            if isinstance(w, pygame_gui.windows.UIMessageWindow)
        ]
        self.assertEqual(len(active_windows), 1)

    def test_unit_editor_save_overwrite_confirmation_modal_trigger(self):
        """Test that saving a loaded existing design template opens the SaveConfirmationDialog."""
        from gui.unit_editor_gui.save_dialog import SaveConfirmationDialog
        from custom_unit_templates import ComponentConfig
        tmp_mgr = CustomTemplateManager()
        t = CustomUnitTemplate("Scout Alpha", HullSize.MEDIUM, ComponentConfig(has_engine=True, engine_speed=100.0))
        tmp_mgr.save_design(t)

        editor_win = UnitEditorWindow(self.gui.manager, pygame.Vector2(1280, 720), tmp_mgr)
        editor_win.show()
        editor_win._sync_widgets_from_template(t)
        self.assertEqual(editor_win._editing_name, "Scout Alpha")

        # Modify speed
        editor_win._engine_speed_entry.set_text("150")

        # Press Save button
        event = pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, {"ui_element": editor_win._save_button})
        res = editor_win.process_event(event)

        self.assertEqual(res, "ui_handled")
        self.assertIsNotNone(editor_win._save_dialog)
        self.assertTrue(editor_win._save_dialog.alive())
        self.assertIsInstance(editor_win._save_dialog, SaveConfirmationDialog)
        self.assertEqual(editor_win._save_dialog.editing_name, "Scout Alpha")
        self.assertEqual(editor_win._save_dialog.window.window_display_title, "Save Design Template")

        # Cleanup
        tmp_mgr.delete_design("Scout Alpha")
        editor_win.kill()

    def test_unit_editor_save_overwrite_confirmed(self):
        """Test confirming overwrite replaces the existing design in template manager."""
        from custom_unit_templates import ComponentConfig
        tmp_mgr = CustomTemplateManager()
        t = CustomUnitTemplate("Scout Beta", HullSize.MEDIUM, ComponentConfig(has_engine=True, engine_speed=100.0))
        tmp_mgr.save_design(t)

        editor_win = UnitEditorWindow(self.gui.manager, pygame.Vector2(1280, 720), tmp_mgr)
        editor_win.show()
        editor_win._sync_widgets_from_template(t)
        editor_win._engine_speed_entry.set_text("180")

        # Click Save to open dialog
        save_ev = pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, {"ui_element": editor_win._save_button})
        editor_win.process_event(save_ev)
        self.assertTrue(editor_win._save_dialog.alive())

        # Click Overwrite in dialog
        overwrite_ev = pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, {"ui_element": editor_win._save_dialog.overwrite_button})
        res = editor_win.process_event(overwrite_ev)

        self.assertEqual(res, "design_saved")
        self.assertIsNone(editor_win._save_dialog)
        saved = tmp_mgr.get_design("Scout Beta")
        self.assertIsNotNone(saved)
        self.assertEqual(saved.components.engine_speed, 180.0)

        # Cleanup
        tmp_mgr.delete_design("Scout Beta")
        editor_win.kill()

    def test_unit_editor_save_as_new_from_dialog(self):
        """Test choosing Save as New creates a new template and leaves the original untouched."""
        from custom_unit_templates import ComponentConfig
        tmp_mgr = CustomTemplateManager()
        t = CustomUnitTemplate("Scout Gamma", HullSize.MEDIUM, ComponentConfig(has_engine=True, engine_speed=100.0))
        tmp_mgr.save_design(t)

        editor_win = UnitEditorWindow(self.gui.manager, pygame.Vector2(1280, 720), tmp_mgr)
        editor_win.show()
        editor_win._sync_widgets_from_template(t)
        editor_win._engine_speed_entry.set_text("200")

        # Click Save to open dialog
        save_ev = pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, {"ui_element": editor_win._save_button})
        editor_win.process_event(save_ev)
        self.assertTrue(editor_win._save_dialog.alive())

        # Enter new name and click Save as New
        editor_win._save_dialog.new_name_entry.set_text("Scout Gamma Speedster")
        save_as_ev = pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, {"ui_element": editor_win._save_dialog.save_as_button})
        res = editor_win.process_event(save_as_ev)

        self.assertEqual(res, "design_saved")
        self.assertIsNone(editor_win._save_dialog)

        # Original template must remain intact with original speed
        orig = tmp_mgr.get_design("Scout Gamma")
        self.assertIsNotNone(orig)
        self.assertEqual(orig.components.engine_speed, 100.0)

        # New template must exist with modified speed
        new_design = tmp_mgr.get_design("Scout Gamma Speedster")
        self.assertIsNotNone(new_design)
        self.assertEqual(new_design.components.engine_speed, 200.0)

        # Cleanup
        tmp_mgr.delete_design("Scout Gamma")
        tmp_mgr.delete_design("Scout Gamma Speedster")
        editor_win.kill()

    def test_unit_editor_save_cancel_dialog(self):
        """Test cancelling the save dialog aborts the save operation and leaves templates untouched."""
        from custom_unit_templates import ComponentConfig
        tmp_mgr = CustomTemplateManager()
        t = CustomUnitTemplate("Scout Delta", HullSize.MEDIUM, ComponentConfig(has_engine=True, engine_speed=100.0))
        tmp_mgr.save_design(t)

        editor_win = UnitEditorWindow(self.gui.manager, pygame.Vector2(1280, 720), tmp_mgr)
        editor_win.show()
        editor_win._sync_widgets_from_template(t)
        editor_win._engine_speed_entry.set_text("220")

        # Click Save to open dialog
        save_ev = pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, {"ui_element": editor_win._save_button})
        editor_win.process_event(save_ev)
        self.assertTrue(editor_win._save_dialog.alive())

        # Click Cancel
        cancel_ev = pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, {"ui_element": editor_win._save_dialog.cancel_button})
        res = editor_win.process_event(cancel_ev)

        self.assertEqual(res, "ui_handled")
        self.assertIsNone(editor_win._save_dialog)

        # Original template is unchanged in manager
        orig = tmp_mgr.get_design("Scout Delta")
        self.assertIsNotNone(orig)
        self.assertEqual(orig.components.engine_speed, 100.0)

        # Cleanup
        tmp_mgr.delete_design("Scout Delta")
        editor_win.kill()

    def test_unit_editor_save_as_new_button_direct(self):
        """Test Column 1 Save as New button saves directly for unique names or opens modal for existing names."""
        from custom_unit_templates import ComponentConfig
        tmp_mgr = CustomTemplateManager()
        editor_win = UnitEditorWindow(self.gui.manager, pygame.Vector2(1280, 720), tmp_mgr)
        editor_win.show()

        # 1. Unique brand new design -> direct save
        editor_win._display_entry.set_text("Brand New Ship Unique")
        editor_win._comp.has_engine = True
        save_as_ev = pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, {"ui_element": editor_win._save_as_button})
        res = editor_win.process_event(save_as_ev)

        self.assertEqual(res, "design_saved")
        self.assertIsNotNone(tmp_mgr.get_design("Brand New Ship Unique"))
        self.assertIsNone(editor_win._save_dialog)

        # 2. Duplicate / loaded name -> triggers dialog
        save_as_dup_ev = pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, {"ui_element": editor_win._save_as_button})
        res2 = editor_win.process_event(save_as_dup_ev)
        self.assertEqual(res2, "ui_handled")
        self.assertIsNotNone(editor_win._save_dialog)
        self.assertTrue(editor_win._save_dialog.alive())

        # Cleanup
        tmp_mgr.delete_design("Brand New Ship Unique")
        editor_win.kill()

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
        wizard.go_to_stage(2)

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

    def test_wizard_cycles_and_preserves_controller_and_reasoning_effort(self):
        self.gui.show_new_game_wizard()
        wizard = self.gui.new_game_wizard
        wizard.go_to_stage(2)
        button = wizard._player_type_buttons[0]

        expected_states = (
            (PlayerController.CODEX, "medium", "Codex"),
            (PlayerController.OPENAI, "medium", "AI: Medium"),
            (PlayerController.OPENAI, "high", "AI: High"),
            (PlayerController.OPENAI, "low", "AI: Low"),
            (PlayerController.HUMAN, "medium", "Human"),
        )
        for controller, reasoning_effort, label in expected_states:
            event = pygame.event.Event(
                pygame_gui.UI_BUTTON_PRESSED,
                {"ui_element": button},
            )
            wizard.process_event(event)
            self.assertEqual(wizard._player_controllers[0], controller)
            self.assertEqual(
                wizard._player_ai_reasoning_efforts[0], reasoning_effort
            )
            self.assertEqual(button.text, label)

        wizard.process_event(
            pygame.event.Event(
                pygame_gui.UI_BUTTON_PRESSED,
                {"ui_element": button},
            )
        )
        wizard._full_rebuild()
        self.assertEqual(wizard._player_controllers[0], PlayerController.CODEX)
        self.assertEqual(wizard._player_ai_reasoning_efforts[0], "medium")
        self.assertEqual(wizard._player_type_buttons[0].text, "Codex")

        action = wizard._build_start_action()
        player_config = action["settings"].player_configs[0]
        self.assertEqual(player_config.controller, PlayerController.CODEX)
        self.assertEqual(player_config.ai_reasoning_effort, "medium")

    def test_wizard_invalid_radius_and_distance_error_dialogs(self):
        """Test that Start Game with invalid system radius or distance displays a modal error dialog."""
        self.gui.show_new_game_wizard()
        wizard = self.gui.new_game_wizard
        self.assertIsNotNone(wizard)

        # Unique colors so color validation passes
        wizard._player_color_indices[0] = 0
        wizard._player_color_indices[1] = 1
        wizard._player_color_indices[2] = 2

        # 1. Inverted radius: min=8, max=4
        wizard._sys_radius_min_slider.set_current_value(8)
        wizard._sys_radius_max_slider.set_current_value(4)

        event = pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, {"ui_element": wizard.start_button})
        from gui import event_router
        action = event_router.process_event(self.gui, event)

        self.assertEqual(action, {'action': 'ui_handled'})
        self.assertGreater(len(self.gui.active_dialogs), 0)
        err_dlg = self.gui.active_dialogs[-1]
        self.assertIn("Invalid Game Settings", err_dlg.window_display_title)
        self.assertTrue(wizard.is_alive)

        # Fix radius, but invert distance: min=200, max=100
        wizard._sys_radius_min_slider.set_current_value(4)
        wizard._sys_radius_max_slider.set_current_value(8)
        wizard._min_dist_slider.set_current_value(200)
        wizard._max_dist_slider.set_current_value(100)

        action = event_router.process_event(self.gui, event)
        self.assertEqual(action, {'action': 'ui_handled'})
        err_dlg = self.gui.active_dialogs[-1]
        self.assertIn("Invalid Game Settings", err_dlg.window_display_title)

    def test_game_settings_post_init_validation(self):
        """Test that direct instantiation of GameSettings with invalid settings raises ValueError."""
        from game_settings import GameSettings
        with self.assertRaises(ValueError) as ctx:
            GameSettings(system_radius_min=9, system_radius_max=4)
        self.assertIn("Min System Radius (9) cannot be greater than Max System Radius (4)", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            GameSettings(min_system_distance=200.0, max_system_distance=100.0)
        self.assertIn("Min System Distance (200) must be strictly less than Max System Distance (100)", str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
