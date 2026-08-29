from player_controller import PlayerController
import pytest
from entities import Player, Unit, Minefield, HullSize
from geometry import Position
from utils import HexCoord
from galaxy import StarSystem, Galaxy
from turn_processor import TurnProcessor
from visibility import VisibilityService


class MockGame:
    def __init__(self):
        self.players = [
            Player("Player 1", (0, 0, 255), controller=PlayerController.HUMAN),
            Player("Player 2", (255, 0, 0), controller=PlayerController.OPENAI)
        ]
        self.current_player_index = 0
        self.turn_number = 1
        self.view_mode = "system"
        self.game_started = True
        self.galaxy = Galaxy()
        sys1 = StarSystem("Sol", Position(100.0, 100.0), radius=3)
        self.galaxy.systems["Sol"] = sys1
        self.current_system_name = "Sol"
        self.current_sector_coord = (0, 0)
        self.visibility = None
        self.selected_objects = []

    def deselect_object(self, obj):
        if obj in self.selected_objects:
            self.selected_objects.remove(obj)

    def is_minefield_visible(self, minefield):
        from visibility import is_minefield_visible as vis_is_minefield_visible
        return vis_is_minefield_visible(self.visibility, minefield)


def test_minefield_visibility_per_player():
    game = MockGame()
    p1, p2 = game.players[0], game.players[1]
    
    mf = Minefield(owner=p1, position=Position(100.0, 100.0), in_hex=(0, 0), in_system="Sol")
    game.galaxy.systems["Sol"].hexes[(0, 0)].add_minefield(mf)

    # When P1 is viewer
    game.current_player_index = 0
    game.visibility = VisibilityService.compute(game.galaxy, p1)
    assert game.is_minefield_visible(mf) is True

    # When P2 is viewer
    game.current_player_index = 1
    game.visibility = VisibilityService.compute(game.galaxy, p2)
    assert game.is_minefield_visible(mf) is False


def test_unit_destruction_via_take_damage():
    game = MockGame()
    p1 = game.players[0]
    system = game.galaxy.systems["Sol"]

    unit = Unit(owner=p1, position=Position(100.0, 100.0), in_hex=(0, 0), in_system="Sol", name="Test Frigate", hull_size=HullSize.SMALL, game=game)
    system.hexes[(0, 0)].add_unit(unit)
    game.selected_objects.append(unit)

    assert unit in system.hexes[(0, 0)].units
    assert unit in game.selected_objects

    # Deal lethal damage
    unit.take_damage(9999)

    assert unit.current_hit_points == 0
    assert unit not in system.hexes[(0, 0)].units
    assert unit not in game.selected_objects


def test_lethal_minefield_detonation_removes_unit():
    game = MockGame()
    p1, p2 = game.players[0], game.players[1]
    tp = TurnProcessor(game)
    system = game.galaxy.systems["Sol"]

    # Place minefield with high damage
    mf = Minefield(owner=p1, position=Position(100.0, 100.0), in_hex=(0, 0), in_system="Sol", mines_remaining=1, mine_damage=1000.0, detonation_radius=250.0)
    system.hexes[(0, 0)].add_minefield(mf)

    # Place enemy unit with low HP
    enemy_unit = Unit(owner=p2, position=Position(105.0, 100.0), in_hex=(0, 0), in_system="Sol", name="Fragile Scout", hull_size=HullSize.SMALL, game=game)
    enemy_unit.current_hit_points = 20
    system.hexes[(0, 0)].add_unit(enemy_unit)
    game.selected_objects.append(enemy_unit)

    # Trigger minefield detonation processing
    tp._process_minefield_detonations()

    # Unit should be destroyed and removed from hex and selection
    assert enemy_unit.current_hit_points == 0
    assert enemy_unit not in system.hexes[(0, 0)].units
    assert enemy_unit not in game.selected_objects
    assert len(system.hexes[(0, 0)].minefields) == 0


def test_turn_processor_cleans_up_zero_hp_units():
    game = MockGame()
    p1 = game.players[0]
    tp = TurnProcessor(game)
    system = game.galaxy.systems["Sol"]

    unit = Unit(owner=p1, position=Position(100.0, 100.0), in_hex=(0, 0), in_system="Sol", name="Damaged Ship", hull_size=HullSize.MEDIUM, game=game)
    unit.current_hit_points = 0
    system.hexes[(0, 0)].add_unit(unit)

    assert unit in system.hexes[(0, 0)].units

    tp._cleanup_dead_units()

    assert unit not in system.hexes[(0, 0)].units
