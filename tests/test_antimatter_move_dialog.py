import os
import unittest
import pygame
import pygame_gui

os.environ["SDL_VIDEODRIVER"] = "dummy"

from geometry import Position
from utils import HexCoord
from game import Game
from entities import Unit, Player, HullSize, Wormhole
from unit_components import Engines, Hyperdrive, HyperdriveType, AntimatterStorage
from unit_orders import calculate_required_antimatter, MoveOrder
from events import IssueMoveOrderEvent, JumpInterhexEvent, JumpWormholeEvent
from custom_unit_templates import get_hyperdrive_system_jump_cost, get_hyperdrive_hex_jump_cost
from constants import ENGINE_ANTIMATTER_COST_PER_TURN, DEFAULT_ANTIMATTER_CAPACITY


class TestAntimatterMoveDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1280, 720))

    def setUp(self):
        self.game = Game()
        self.game.start_new_game()
        self.gui = self.game.gui
        self.player = self.game.players[0]

        # Setup test unit
        self.unit = Unit(
            name="Test Explorer",
            owner=self.player,
            hull_size=HullSize.MEDIUM,
            position=Position(0.0, 0.0),
            in_hex=HexCoord(0, 0),
            in_system="Sol",
            game=self.game
        )
        self.unit.add_component(Engines(self.unit, speed=100.0))
        self.unit.add_component(Hyperdrive(self.unit, drive_type=HyperdriveType.ADVANCED, jump_range=5))
        self.unit.add_component(AntimatterStorage(self.unit, max_capacity=200.0))

        # Add unit to galaxy
        self.game.galaxy.systems["Sol"].add_unit(self.unit)

    def tearDown(self):
        if self.gui:
            self.gui.clear_and_reset()

    def test_calculate_required_antimatter_sublight(self):
        """Test calculation of antimatter for sub-light movement within same hex."""
        # Moving from (0,0) to (300,300) -> distance ~424.26, speed 100 -> 5 turns -> 5 * 1.0 = 5.0 AM
        cost = calculate_required_antimatter(
            self.unit,
            self.game.galaxy,
            destination_system_name="Sol",
            destination_hex_coord=HexCoord(0, 0),
            destination_position=Position(300.0, 300.0)
        )
        self.assertEqual(cost, 5.0)

    def test_calculate_required_antimatter_hex_jump(self):
        """Test calculation of antimatter for single hex jump."""
        expected_cost = get_hyperdrive_hex_jump_cost(HullSize.MEDIUM)
        cost = calculate_required_antimatter(
            self.unit,
            self.game.galaxy,
            destination_system_name="Sol",
            destination_hex_coord=HexCoord(2, -1)
        )
        self.assertEqual(cost, expected_cost)

    def test_calculate_required_antimatter_intersystem_jump(self):
        """Test calculation of antimatter for inter-system wormhole jump."""
        # Sol to Alpha Centauri via wormhole
        expected_sys_cost = get_hyperdrive_system_jump_cost(HullSize.MEDIUM)
        expected_hex_cost = get_hyperdrive_hex_jump_cost(HullSize.MEDIUM)

        cost = calculate_required_antimatter(
            self.unit,
            self.game.galaxy,
            destination_system_name="Alpha Centauri",
            destination_hex_coord=HexCoord(0, 0)
        )
        # Should include system jump cost and any hex jump costs to reach/exit wormholes
        self.assertGreaterEqual(cost, expected_sys_cost)

    def test_move_order_sufficient_antimatter_succeeds(self):
        """Test issuing move order with sufficient antimatter assigns order without error modal."""
        self.unit.antimatter_component.current_amount = 200.0
        self.unit.commander_component.clear_orders()

        event = IssueMoveOrderEvent(
            units=[self.unit],
            system_name="Sol",
            sector_coord=HexCoord(2, -1),
            destination=Position(0.0, 0.0),
            shift_pressed=False
        )
        self.game.order_system.handle_issue_move_order(event)

        self.assertEqual(self.unit.commander_component.get_active_orders_count(), 1)
        self.assertEqual(len(self.gui.active_dialogs), 0)

    def test_move_order_insufficient_antimatter_shows_error_modal(self):
        """Test issuing move order with insufficient antimatter blocks order and spawns error modal."""
        # Set antimatter to 0 so unit cannot make any jump or move
        self.unit.antimatter_component.current_amount = 0.0
        self.unit.commander_component.clear_orders()

        event = IssueMoveOrderEvent(
            units=[self.unit],
            system_name="Sol",
            sector_coord=HexCoord(2, -1),
            destination=Position(0.0, 0.0),
            shift_pressed=False
        )
        self.game.order_system.handle_issue_move_order(event)

        # Order should be blocked
        self.assertEqual(self.unit.commander_component.get_active_orders_count(), 0)

        # Modal dialog should be displayed
        self.assertGreater(len(self.gui.active_dialogs), 0)
        dialog = self.gui.active_dialogs[-1]
        self.assertIsInstance(dialog, pygame_gui.windows.UIMessageWindow)
        self.assertIn("Insufficient Antimatter", dialog.window_display_title)


if __name__ == "__main__":
    unittest.main()
