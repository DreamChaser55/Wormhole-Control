import pytest
from entities import Player, Unit, Minefield, HullSize
from geometry import Position
from utils import HexCoord
from constants import (
    MINEFIELD_CREDIT_COST, MINEFIELD_ANTIMATTER_COST, MAX_MINEFIELDS_PER_HEX,
    MINEFIELD_DEFAULT_DAMAGE, MINEFIELD_DEFAULT_MINES, MINEFIELD_DETONATION_RADIUS
)
from unit_components import MinelayerComponent, AntimatterStorage, Sensors
from unit_orders import LayMinefieldOrder, OrderStatus
from visibility import VisibilityService, is_minefield_visible
from galaxy import StarSystem, Galaxy
from turn_processor import TurnProcessor
import save_manager


class MockGame:
    def __init__(self):
        self.players = [
            Player("Player 1", (0, 0, 255), is_human=True),
            Player("Player 2", (255, 0, 0), is_human=False)
        ]
        self.current_player_index = 0
        self.turn_number = 1
        self.view_mode = "system"
        self.galaxy = Galaxy()
        sys1 = StarSystem("Sol", Position(100.0, 100.0), radius=3)
        self.galaxy.systems["Sol"] = sys1
        self.current_system_name = "Sol"
        self.current_sector_coord = (0, 0)
        self.visibility_snapshot = None


def test_minelayer_component_and_resource_cost():
    game = MockGame()
    player1 = game.players[0]
    player1.credits = 1000.0
    system = game.galaxy.systems["Sol"]

    unit = Unit(owner=player1, position=Position(100.0, 100.0), in_hex=(0, 0), in_system="Sol", name="Minelayer Ship", hull_size=HullSize.MEDIUM, game=game)
    unit.antimatter_component.current_amount = 100.0
    
    minelayer = MinelayerComponent(unit)
    unit.add_component(minelayer)

    # Test checking capacity & resource availability
    can_lay, reason = minelayer.can_lay_mine(game.galaxy, "Sol", (0, 0))
    assert can_lay is True

    # Lay first minefield
    mf1 = minelayer.deploy_mine(game.galaxy, "Sol", (0, 0), Position(100.0, 100.0))
    assert mf1 is not None
    assert isinstance(mf1, Minefield)
    assert len(system.hexes[(0, 0)].minefields) == 1
    assert player1.credits == 1000.0 - MINEFIELD_CREDIT_COST
    assert unit.antimatter_component.current_amount == 100.0 - MINEFIELD_ANTIMATTER_COST

    # Lay 2 more to hit max hex limit
    mf2 = minelayer.deploy_mine(game.galaxy, "Sol", (0, 0), Position(110.0, 100.0))
    mf3 = minelayer.deploy_mine(game.galaxy, "Sol", (0, 0), Position(120.0, 100.0))
    assert mf2 is not None and mf3 is not None
    assert len(system.hexes[(0, 0)].minefields) == 3

    # Attempting to lay a 4th minefield should be rejected due to MAX_MINEFIELDS_PER_HEX = 3
    can_lay, reason = minelayer.can_lay_mine(game.galaxy, "Sol", (0, 0))
    assert can_lay is False
    assert "limit" in reason.lower()

    mf4 = minelayer.deploy_mine(game.galaxy, "Sol", (0, 0), Position(130.0, 100.0))
    assert mf4 is None


def test_lay_minefield_order():
    game = MockGame()
    player1 = game.players[0]
    player1.credits = 500.0
    
    unit = Unit(owner=player1, position=Position(0.0, 0.0), in_hex=(0, 0), in_system="Sol", name="Minelayer Ship", hull_size=HullSize.MEDIUM, game=game)
    unit.antimatter_component.current_amount = 50.0
    unit.add_component(MinelayerComponent(unit))

    order = LayMinefieldOrder(unit)
    status = order.execute(game.galaxy)

    assert status == OrderStatus.COMPLETED
    hex_obj = game.galaxy.systems["Sol"].hexes[(0, 0)]
    assert len(hex_obj.minefields) == 1
    assert hex_obj.minefields[0].owner == player1


def test_minefield_stealth_and_visibility():
    game = MockGame()
    p1, p2 = game.players[0], game.players[1]
    
    # Place P1 minefield
    mf = Minefield(owner=p1, position=Position(0.0, 0.0), in_hex=(0, 0), in_system="Sol")
    game.galaxy.systems["Sol"].hexes[(0, 0)].add_minefield(mf)

    # Place P2 enemy sensor ship in same hex with short range sensors
    enemy_scout = Unit(owner=p2, position=Position(10.0, 10.0), in_hex=(0, 0), in_system="Sol", name="Enemy Scout", hull_size=HullSize.SMALL, game=game)
    enemy_scout.add_component(Sensors(enemy_scout, short_range_radius=5000.0, long_range_hexes=2))
    game.galaxy.systems["Sol"].hexes[(0, 0)].add_unit(enemy_scout)

    # Compute visibility snapshot for P2
    snapshot_p2 = VisibilityService.compute(game.galaxy, p2)

    # P2 snapshot should NOT see P1 minefield
    assert is_minefield_visible(snapshot_p2, mf) is False

    # P1 snapshot should see P1 minefield
    snapshot_p1 = VisibilityService.compute(game.galaxy, p1)
    assert is_minefield_visible(snapshot_p1, mf) is True


def test_minefield_contact_detonation():
    game = MockGame()
    p1, p2 = game.players[0], game.players[1]
    tp = TurnProcessor(game)

    system = game.galaxy.systems["Sol"]

    # Place minefield owned by P1
    mf = Minefield(owner=p1, position=Position(100.0, 100.0), in_hex=(0, 0), in_system="Sol", mines_remaining=1, mine_damage=40.0, detonation_radius=250.0)
    system.hexes[(0, 0)].add_minefield(mf)

    # Place enemy unit inside detonation radius
    enemy_unit = Unit(owner=p2, position=Position(120.0, 100.0), in_hex=(0, 0), in_system="Sol", name="Enemy Cruiser", hull_size=HullSize.MEDIUM, game=game)
    system.hexes[(0, 0)].add_unit(enemy_unit)
    initial_hp = enemy_unit.current_hit_points

    # Trigger turn processing detonations
    tp._process_minefield_detonations()

    # Enemy unit should have taken damage
    assert enemy_unit.current_hit_points < initial_hp
    # Minefield had 1 mine; after detonation it should be depleted and removed
    assert len(system.hexes[(0, 0)].minefields) == 0


def test_minefield_save_and_load():
    game = MockGame()
    p1 = game.players[0]

    system = game.galaxy.systems["Sol"]
    mf = Minefield(owner=p1, position=Position(150.0, 200.0), in_hex=(1, 1), in_system="Sol", mines_remaining=4, mine_damage=45.0)
    system.hexes[(1, 1)].add_minefield(mf)

    minelayer_unit = Unit(owner=p1, position=Position(150.0, 200.0), in_hex=(1, 1), in_system="Sol", name="Minelayer Ship", hull_size=HullSize.LARGE, game=game)
    minelayer_unit.add_component(MinelayerComponent(minelayer_unit))
    system.hexes[(1, 1)].add_unit(minelayer_unit)

    # Serialize game state
    state_dict = save_manager.serialize_game_state(game)

    # Deserialize game state
    players_by_id = {p.id: p for p in game.players}
    restored_galaxy = save_manager.deserialize_galaxy(state_dict["galaxy"], players_by_id, game)

    restored_hex = restored_galaxy.systems["Sol"].hexes[(1, 1)]
    assert len(restored_hex.minefields) == 1
    restored_mf = restored_hex.minefields[0]

    assert restored_mf.owner.id == p1.id
    assert restored_mf.position.x == 150.0
    assert restored_mf.position.y == 200.0
    assert restored_mf.mines_remaining == 4
    assert restored_mf.mine_damage == 45.0


def test_gui_lay_minefield_action():
    from events import EventBus, LayMinefieldEvent
    from order_system import OrderSystem

    game = MockGame()
    game.event_bus = EventBus()
    game.order_system = OrderSystem(game, game.event_bus)
    game.sidebar_needs_update = False

    p1 = game.players[0]
    p1.credits = 1000.0

    unit = Unit(owner=p1, position=Position(100.0, 100.0), in_hex=(0, 0), in_system="Sol", name="Minelayer Ship", hull_size=HullSize.MEDIUM, game=game)
    unit.antimatter_component.current_amount = 50.0
    unit.add_component(MinelayerComponent(unit))
    game.galaxy.systems["Sol"].hexes[(0, 0)].add_unit(unit)

    from game import Game
    Game.handle_gui_action(game, {'action': 'lay_minefield', 'unit_id': unit.id, 'shift_pressed': False})


    # Verify order was queued and executed for unit, creating a minefield
    assert len(game.galaxy.systems["Sol"].hexes[(0, 0)].minefields) == 1
    assert p1.credits == 1000.0 - MINEFIELD_CREDIT_COST



