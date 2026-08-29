import os
import unittest
import pygame
import pygame_gui

os.environ["SDL_VIDEODRIVER"] = "dummy"

from game import Game
from turn_processor import TurnProcessor
from entities import Unit, Player, HullSize, Planet
from geometry import Position
from utils import HexCoord
from unit_components import (
    Commander, Engines, Hyperdrive, HyperdriveType, ColonyComponent,
    RepairComponent, MiningComponent, MinelayerComponent, AntimatterHarvester,
    AbilityComponent, AbilityType
)
from events import (
    IssueMoveOrderEvent, IssuePatrolOrderEvent, JumpInterhexEvent, JumpWormholeEvent, ColonizeEvent, RepairUnitEvent,
    MineEvent, DockEvent, ContinuousResupplyEvent, LayMinefieldEvent
)
from unit_orders import MoveOrder, UseAbilityOrder
from game_actions import unit_actions


class TestInGameErrorDialogs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1280, 720))

    def setUp(self):
        self.game = Game()
        self.game.start_new_game()
        self.gui = self.game.gui
        self.player = self.game.players[0]
        self.player.is_human = True

    def tearDown(self):
        if self.gui:
            self.gui.clear_and_reset()

    def test_move_order_without_engines_shows_warning(self):
        unit = Unit(
            owner=self.player, position=Position(0, 0), in_hex=HexCoord(0, 0),
            in_system="Sol", name="Engine-less Scout", hull_size=HullSize.SMALL, game=self.game
        )
        unit.add_component(Commander(unit))
        self.game.order_system.handle_issue_move_order(
            IssueMoveOrderEvent([unit], "Sol", HexCoord(0, 0), Position(100, 100), False)
        )
        self.assertGreater(len(self.gui.active_dialogs), 0)
        dlg = self.gui.active_dialogs[-1]
        self.assertIn("No Engines", dlg.window_display_title)
        self.assertIn("no sub-light engines", dlg.text_block.html_text)

    def test_destroyed_engines_block_move_and_patrol_orders(self):
        unit = Unit(
            owner=self.player, position=Position(0, 0), in_hex=HexCoord(0, 0),
            in_system="Sol", name="Disabled Scout", hull_size=HullSize.SMALL, game=self.game
        )
        engines = Engines(unit, speed=100)
        engines.current_hit_points = 0
        unit.add_component(engines)

        self.game.order_system.handle_issue_move_order(
            IssueMoveOrderEvent([unit], "Sol", HexCoord(0, 0), Position(100, 100), False)
        )
        self.game.order_system.handle_issue_patrol_order(
            IssuePatrolOrderEvent([unit], "Sol", HexCoord(0, 0), Position(100, 100), False)
        )

        self.assertEqual(unit.commander_component.get_active_orders_count(), 0)
        self.assertGreaterEqual(len(self.gui.active_dialogs), 2)
        for dlg in self.gui.active_dialogs[-2:]:
            self.assertIn("Engines Destroyed", dlg.window_display_title)
            self.assertIn("until they are repaired", dlg.text_block.html_text)

    def test_context_menu_hides_sublight_actions_for_destroyed_engines(self):
        from input_processor.context_menu_builder import build_sector_context_menu_options

        unit = Unit(
            owner=self.player, position=Position(0, 0), in_hex=HexCoord(0, 0),
            in_system="Sol", name="Disabled Scout", hull_size=HullSize.SMALL, game=self.game
        )
        engines = Engines(unit, speed=100)
        engines.current_hit_points = 0
        unit.add_component(engines)
        self.game.selected_objects = [unit]

        options, _ = build_sector_context_menu_options(self.game, None, Position(100, 100))
        action_ids = {action_id for _label, action_id in options}
        self.assertNotIn("issue_move_order", action_ids)
        self.assertNotIn("issue_patrol_order", action_ids)

        engines.current_hit_points = 1
        options, _ = build_sector_context_menu_options(self.game, None, Position(100, 100))
        action_ids = {action_id for _label, action_id in options}
        self.assertIn("issue_move_order", action_ids)
        self.assertIn("issue_patrol_order", action_ids)

    def test_interhex_jump_without_hyperdrive_shows_warning(self):
        unit = Unit(
            owner=self.player, position=Position(0, 0), in_hex=HexCoord(0, 0),
            in_system="Sol", name="No-Drive Frigate", hull_size=HullSize.MEDIUM, game=self.game
        )
        unit.add_component(Commander(unit))
        self.game.order_system.handle_jump_interhex(
            JumpInterhexEvent([unit], "Sol", HexCoord(1, 0), False)
        )
        self.assertGreater(len(self.gui.active_dialogs), 0)
        dlg = self.gui.active_dialogs[-1]
        self.assertIn("No Hyperdrive", dlg.window_display_title)
        self.assertIn("no hyperdrive module", dlg.text_block.html_text)

    def test_dock_large_ship_shows_warning(self):
        carrier = Unit(
            owner=self.player, position=Position(0, 0), in_hex=HexCoord(0, 0),
            in_system="Sol", name="Carrier Base", hull_size=HullSize.LARGE, game=self.game
        )
        battleship = Unit(
            owner=self.player, position=Position(0, 0), in_hex=HexCoord(0, 0),
            in_system="Sol", name="Heavy Battleship", hull_size=HullSize.LARGE, game=self.game
        )
        battleship.add_component(Commander(battleship))

        self.game.order_system.handle_dock(
            DockEvent([battleship], carrier, False)
        )
        self.assertGreater(len(self.gui.active_dialogs), 0)
        dlg = self.gui.active_dialogs[-1]
        self.assertIn("Invalid Dock Target", dlg.window_display_title)
        self.assertIn("cannot dock", dlg.text_block.html_text)

    def test_colonize_without_cargo_shows_warning(self):
        colony_ship = Unit(
            owner=self.player, position=Position(0, 0), in_hex=HexCoord(0, 0),
            in_system="Sol", name="Colony Vessel", hull_size=HullSize.MEDIUM, game=self.game
        )
        colony_ship.add_component(Commander(colony_ship))
        col_comp = ColonyComponent(colony_ship)
        col_comp.population_cargo = 0
        colony_ship.add_component(col_comp)

        target_planet = Planet(HexCoord(0, 0), "Sol", Position(10, 10))
        target_planet.name = "Terra Nova"

        self.game.order_system.handle_colonize(
            ColonizeEvent([colony_ship], target_planet, False)
        )
        self.assertGreater(len(self.gui.active_dialogs), 0)
        dlg = self.gui.active_dialogs[-1]
        self.assertIn("Cannot Colonize", dlg.window_display_title)
        self.assertIn("no colonists in cargo", dlg.text_block.html_text)

    def test_mining_without_module_shows_warning(self):
        scout = Unit(
            owner=self.player, position=Position(0, 0), in_hex=HexCoord(0, 0),
            in_system="Sol", name="Scout Ship", hull_size=HullSize.SMALL, game=self.game
        )
        scout.add_component(Commander(scout))
        target_asteroid = Planet(HexCoord(0, 0), "Sol", Position(10, 10))
        target_asteroid.name = "Asteroid A"

        self.game.order_system.handle_mine(
            MineEvent([scout], target_asteroid, False)
        )
        self.assertGreater(len(self.gui.active_dialogs), 0)
        dlg = self.gui.active_dialogs[-1]
        self.assertIn("No Mining Module", dlg.window_display_title)
        self.assertIn("lacks a Mining Component", dlg.text_block.html_text)

    def test_route_planning_no_advanced_drive_warning(self):
        unit = Unit(
            owner=self.player, position=Position(0, 0), in_hex=HexCoord(0, 0),
            in_system="Sol", name="Corvette", hull_size=HullSize.SMALL, game=self.game
        )
        unit.add_component(Commander(unit))
        unit.add_component(Engines(unit, speed=100))
        hd = Hyperdrive(unit, drive_type=HyperdriveType.BASIC, jump_range=3)
        unit.add_component(hd)

        move_order = MoveOrder(unit, {
            "destination_system_name": "Alpha Centauri",
            "destination_hex_coord": HexCoord(0, 0),
            "destination_position": Position(0, 0)
        })
        move_order.execute(self.game.galaxy)
        self.assertGreater(len(self.gui.active_dialogs), 0)
        dlg = self.gui.active_dialogs[-1]
        self.assertIn("Route Planning Failed", dlg.window_display_title)
        self.assertIn("requires an Advanced Hyperdrive", dlg.text_block.html_text)

    def test_unload_resources_nearest_empty_cargo_warning(self):
        miner = Unit(
            owner=self.player, position=Position(0, 0), in_hex=HexCoord(0, 0),
            in_system="Sol", name="Miner", hull_size=HullSize.MEDIUM, game=self.game
        )
        miner.add_component(Commander(miner))
        mining_comp = MiningComponent(miner)
        mining_comp.raw_metal_cargo = 0
        mining_comp.raw_crystal_cargo = 0
        miner.add_component(mining_comp)

        self.game.galaxy.systems["Sol"].add_unit(miner)
        unit_actions.handle_unload_resources_nearest(self.game, {"unit_id": miner.id})
        self.assertGreater(len(self.gui.active_dialogs), 0)
        dlg = self.gui.active_dialogs[-1]
        self.assertIn("Cargo Empty", dlg.window_display_title)
        self.assertIn("has no raw metal or crystal cargo", dlg.text_block.html_text)

    def test_ability_prevalidation_capture_warning(self):
        attacker = Unit(
            owner=self.player, position=Position(0, 0), in_hex=HexCoord(0, 0),
            in_system="Sol", name="Boarding Craft", hull_size=HullSize.MEDIUM, game=self.game
        )
        enemy_player = Player("Enemy", (255, 0, 0), is_human=False)
        target_unit = Unit(
            owner=enemy_player, position=Position(5, 5), in_hex=HexCoord(0, 0),
            in_system="Sol", name="Enemy Frigate", hull_size=HullSize.MEDIUM, game=self.game
        )
        target_unit.add_component(Engines(target_unit, speed=100))
        attacker.add_component(Commander(attacker))
        ac = AbilityComponent(attacker, ability_types=[AbilityType.CAPTURE_UNIT])
        attacker.add_component(ac)

        self.game.galaxy.systems["Sol"].add_unit(attacker)
        self.game.galaxy.systems["Sol"].add_unit(target_unit)

        order = UseAbilityOrder(attacker, {
            "ability_type": AbilityType.CAPTURE_UNIT.value,
            "target_unit_id": target_unit.id
        })
        order.execute(self.game.galaxy)
        self.assertGreater(len(self.gui.active_dialogs), 0)
        dlg = self.gui.active_dialogs[-1]
        self.assertIn("Capture Failed", dlg.window_display_title)
        self.assertIn("must be disabled first", dlg.text_block.html_text)

    def test_upkeep_depletion_warning(self):
        unit = Unit(
            owner=self.player, position=Position(0, 0), in_hex=HexCoord(0, 0),
            in_system="Sol", name="Capital Ship", hull_size=HullSize.LARGE, game=self.game
        )
        unit.current_hull_usage = 500
        self.game.galaxy.systems["Sol"].add_unit(unit)

        self.player.credits = 0.0
        tp = TurnProcessor(self.game)
        tp._process_unit_upkeep(self.player)
        self.assertGreater(len(self.gui.active_dialogs), 0)
        dlg = self.gui.active_dialogs[-1]
        self.assertIn("Upkeep Shortage", dlg.window_display_title)
        self.assertIn("Treasury depleted", dlg.text_block.html_text)
    def test_move_order_cross_sector_without_hyperdrive_shows_warning(self):
        """Move order to a different hex on a unit without hyperdrive should show 'No Hyperdrive' dialog."""
        unit = Unit(
            owner=self.player, position=Position(0, 0), in_hex=HexCoord(0, 0),
            in_system="Sol", name="Slow Freighter", hull_size=HullSize.MEDIUM, game=self.game
        )
        unit.add_component(Commander(unit))
        unit.add_component(Engines(unit, speed=100))

        self.game.order_system.handle_issue_move_order(
            IssueMoveOrderEvent([unit], "Sol", HexCoord(1, 0), Position(0, 0), False)
        )
        # Order should be blocked
        self.assertEqual(unit.commander_component.get_active_orders_count(), 0)
        # Warning dialog should be displayed
        self.assertGreater(len(self.gui.active_dialogs), 0)
        dlg = self.gui.active_dialogs[-1]
        self.assertIn("No Hyperdrive", dlg.window_display_title)
        self.assertIn("no hyperdrive module", dlg.text_block.html_text)

    def test_wormhole_jump_without_hyperdrive_shows_warning(self):
        """Wormhole jump on a unit without hyperdrive should show 'No Hyperdrive' dialog."""
        unit = Unit(
            owner=self.player, position=Position(0, 0), in_hex=HexCoord(0, 0),
            in_system="Sol", name="Drifter Barge", hull_size=HullSize.MEDIUM, game=self.game
        )
        unit.add_component(Commander(unit))
        unit.add_component(Engines(unit, speed=100))
        self.game.galaxy.systems["Sol"].add_unit(unit)

        # Find any wormhole in Sol to use as the event target
        wormhole = None
        for wh in self.game.galaxy.wormholes.values():
            if wh.in_system == "Sol" and wh.exit_system_name:
                wormhole = wh
                break
        self.assertIsNotNone(wormhole, "Test requires at least one wormhole in Sol")

        self.game.order_system.handle_jump_wormhole(
            JumpWormholeEvent([unit], wormhole, False)
        )
        self.assertGreater(len(self.gui.active_dialogs), 0)
        dlg = self.gui.active_dialogs[-1]
        self.assertIn("No Hyperdrive", dlg.window_display_title)
        self.assertIn("no hyperdrive module", dlg.text_block.html_text)


if __name__ == "__main__":
    unittest.main()
