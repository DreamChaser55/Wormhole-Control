import pytest
from unittest.mock import MagicMock, patch
from turn_processor import TurnProcessor, TAX_RATE
from geometry import Position
from entities import Planet
from tests.test_unit_components import MockUnit, MockPlayer
from constants import UPKEEP_COST_PER_HULL_POINT, HullSize

def test_end_turn_advances_player():
    game = MagicMock()
    player1 = MockPlayer("Player 1")
    player2 = MockPlayer("Player 2")
    player2.is_human = True
    game.players = [player1, player2]
    game.current_player_index = 0
    
    tp = TurnProcessor(game)
    with patch.object(tp, 'process_turn') as mock_process:
        tp.end_turn()
        mock_process.assert_called_once()
        assert game.current_player_index == 1
        game.update_player_turn_display.assert_called_once()
        game.update_side_bar_content.assert_called_once()

def test_process_resource_generation():
    game = MagicMock()
    player = MockPlayer("Human Player")
    player.credits = 1000.0
    game.players = [player]
    game.current_player_index = 0
    
    # Mock celestial bodies in systems
    planet1 = MagicMock(spec=Planet)
    planet1.owner = player
    planet1.population = 50.0
    
    planet2 = MagicMock(spec=Planet)
    planet2.owner = player
    planet2.population = 100.0
    
    # Planet owned by another player (should not count)
    other_player = MockPlayer("AI Player")
    planet_other = MagicMock(spec=Planet)
    planet_other.owner = other_player
    planet_other.population = 500.0
    
    system1 = MagicMock()
    system1.get_all_celestial_bodies.return_value = [
        ((0, 0), planet1),
        ((0, 1), planet2),
        ((0, 2), planet_other)
    ]
    
    game.galaxy.systems = {"Sol": system1}
    
    tp = TurnProcessor(game)
    tp._process_resource_generation(player)
    
    # Expected generated credits: (50 + 100) * TAX_RATE = 150 * 0.1 = 15.0
    assert player.credits == 1015.0

def test_process_movement_sublight():
    game = MagicMock()
    player = MockPlayer("Player 1")
    unit = MockUnit()
    unit.owner = player
    
    # Setup engine component
    from unit_components import Engines
    engines = MagicMock()
    engines.speed = 10.0
    engines.move_target = Position(100.0, 0.0)
    unit.components = {Engines: engines}
    unit.position = Position(0.0, 0.0)
    
    system = MagicMock()
    system.get_all_units.return_value = [(unit, (0, 0))]
    game.galaxy.systems = {"Sol": system}
    
    tp = TurnProcessor(game)
    tp._process_movement(player)
    
    # Unit should move towards target position by speed (10.0 units)
    assert unit.position.x == 10.0
    assert unit.position.y == 0.0

def test_process_population_growth():
    game = MagicMock()
    planet = MagicMock(spec=Planet)
    
    system = MagicMock()
    system.get_all_celestial_bodies.return_value = [((0, 0), planet)]
    game.galaxy.systems = {"Sol": system}
    
    tp = TurnProcessor(game)
    tp._process_population_growth()
    planet.update_population.assert_called_once()


def test_process_combat():
    from unit_components import Weapons, Turret, TurretType
    game = MagicMock()
    player1 = MockPlayer("Player 1")
    player2 = MockPlayer("Player 2")
    game.players = [player1, player2]
    game.current_player_index = 0
    
    unit1 = MockUnit()
    unit1.owner = player1
    unit2 = MockUnit()
    unit2.owner = player2
    
    weapons = Weapons(unit1)
    turret = Turret(
        turret_type=TurretType.MASS_DRIVER,
        damage=25,
        range=100.0,
        cooldown=1,
        parent_unit=unit1
    )
    weapons.add_turret(turret)
    unit1.add_component(weapons)
    
    unit1.position = Position(0, 0)
    unit2.position = Position(10, 0)
    unit2.current_hit_points = 100
    
    weapons.set_target(unit2)
    
    system = MagicMock()
    system.get_all_units.return_value = [(unit1, (0, 0)), (unit2, (0, 0))]
    game.galaxy.systems = {"Sol": system}
    
    tp = TurnProcessor(game)
    tp._process_unit_updates(player1)
    
    # Target unit should have taken damage from unit1's turret
    assert unit2.current_hit_points == 75


def test_process_unit_updates():
    game = MagicMock()
    player = MockPlayer("Human Player")
    game.players = [player]
    game.current_player_index = 0
    
    unit = MockUnit()
    unit.owner = player
    
    system = MagicMock()
    system.get_all_units.return_value = [(unit, (0, 0))]
    game.galaxy.systems = {"Sol": system}
    
    # Spy on unit.update
    unit.update = MagicMock()
    
    tp = TurnProcessor(game)
    tp._process_unit_updates(player)
    
    unit.update.assert_called_once()


def test_process_orders():
    from unit_components import Commander
    from unit_orders import Order, OrderStatus
    
    game = MagicMock()
    player = MockPlayer("Player 1")
    game.players = [player]
    game.current_player_index = 0
    
    unit = MockUnit()
    unit.owner = player
    
    commander = Commander(unit)
    unit.add_component(commander)
    
    order = MagicMock(spec=Order)
    order.order_id = 1
    order.status = OrderStatus.PENDING
    order.is_completed.return_value = False
    
    commander.add_order(order)
    
    system = MagicMock()
    system.get_all_units.return_value = [(unit, (0, 0))]
    game.galaxy.systems = {"Sol": system}
    
    tp = TurnProcessor(game)
    tp.process_turn()
    
    # Order execution should be triggered via commander.update() -> order.execute()
    order.execute.assert_called_once()


# --- Unit Upkeep Tests ---

def _make_upkeep_unit(player, hull_usage, hull_size=HullSize.TINY, is_temporary=False):
    """Helper that returns a MockUnit configured for upkeep tests."""
    unit = MockUnit()
    unit.owner = player
    unit.current_hull_usage = hull_usage
    unit.hull_size = hull_size
    unit.is_temporary = is_temporary
    return unit


def _make_upkeep_game(units):
    """Helper that returns a mock game whose galaxy has a single system containing `units`."""
    game = MagicMock()
    system = MagicMock()
    system.get_all_units.return_value = [(u, (0, 0)) for u in units]
    game.galaxy.systems = {"Sol": system}
    return game


def test_process_unit_upkeep_basic():
    """Upkeep is correctly deducted from player credits."""
    player = MockPlayer("Player 1")
    player.credits = 1000.0

    unit = _make_upkeep_unit(player, hull_usage=10)
    game = _make_upkeep_game([unit])

    tp = TurnProcessor(game)
    tp._process_unit_upkeep(player)

    expected = 10 * UPKEEP_COST_PER_HULL_POINT
    assert player.credits == pytest.approx(1000.0 - expected)


def test_process_unit_upkeep_clamps_to_zero():
    """Credits never go below zero even when upkeep exceeds the balance."""
    player = MockPlayer("Player 1")
    player.credits = 0.05  # Less than the upkeep that will be charged

    unit = _make_upkeep_unit(player, hull_usage=200)  # 200 * 0.01 = 2.0 upkeep
    game = _make_upkeep_game([unit])

    tp = TurnProcessor(game)
    tp._process_unit_upkeep(player)

    assert player.credits == 0.0


def test_process_unit_upkeep_skips_temporary_units():
    """Temporary units (e.g. Missile Platforms) are excluded from upkeep."""
    player = MockPlayer("Player 1")
    player.credits = 1000.0

    temp_unit = _make_upkeep_unit(player, hull_usage=50, is_temporary=True)
    game = _make_upkeep_game([temp_unit])

    tp = TurnProcessor(game)
    tp._process_unit_upkeep(player)

    assert player.credits == 1000.0  # No credits deducted


def test_process_unit_upkeep_skips_strikecraft():
    """Strikecraft wings are excluded from upkeep charges."""
    player = MockPlayer("Player 1")
    player.credits = 1000.0

    wing = _make_upkeep_unit(player, hull_usage=5, hull_size=HullSize.STRIKECRAFT_WING)
    game = _make_upkeep_game([wing])

    tp = TurnProcessor(game)
    tp._process_unit_upkeep(player)

    assert player.credits == 1000.0  # No credits deducted


def test_process_unit_upkeep_multiple_units():
    """Upkeep accumulates correctly across multiple units owned by the same player."""
    player = MockPlayer("Player 1")
    player.credits = 500.0
    other_player = MockPlayer("Player 2")

    unit_a = _make_upkeep_unit(player, hull_usage=10)       # 10 * 0.01 = 0.10
    unit_b = _make_upkeep_unit(player, hull_usage=25)       # 25 * 0.01 = 0.25
    unit_enemy = _make_upkeep_unit(other_player, hull_usage=100)  # should not count

    game = _make_upkeep_game([unit_a, unit_b, unit_enemy])

    tp = TurnProcessor(game)
    tp._process_unit_upkeep(player)

    expected = (10 + 25) * UPKEEP_COST_PER_HULL_POINT
    assert player.credits == pytest.approx(500.0 - expected)


def test_game_get_player_income():
    from game import Game
    from entities import Planet
    
    class DummyGame(Game):
        def __init__(self):
            self.galaxy = MagicMock()

    game = DummyGame()
    player = MockPlayer("Player 1")
    
    planet1 = MagicMock(spec=Planet)
    planet1.owner = player
    planet1.population = 100.0
    
    planet2 = MagicMock(spec=Planet)
    planet2.owner = player
    planet2.population = 50.0
    
    other_player = MockPlayer("Player 2")
    planet_other = MagicMock(spec=Planet)
    planet_other.owner = other_player
    planet_other.population = 200.0
    
    system = MagicMock()
    system.get_all_celestial_bodies.return_value = [
        ((0, 0), planet1),
        ((0, 1), planet2),
        ((0, 2), planet_other)
    ]
    game.galaxy.systems = {"Sol": system}
    
    from constants import TAX_RATE
    expected_income = (100.0 + 50.0) * TAX_RATE
    assert game.get_player_income(player) == pytest.approx(expected_income)


def test_game_get_player_upkeep():
    from game import Game
    
    class DummyGame(Game):
        def __init__(self):
            self.galaxy = MagicMock()
            
    game = DummyGame()
    player = MockPlayer("Player 1")
    
    unit_a = _make_upkeep_unit(player, hull_usage=10)       # counts
    unit_b = _make_upkeep_unit(player, hull_usage=25)       # counts
    unit_temp = _make_upkeep_unit(player, hull_usage=50, is_temporary=True)  # skipped
    unit_wing = _make_upkeep_unit(player, hull_usage=5, hull_size=HullSize.STRIKECRAFT_WING)  # skipped
    
    other_player = MockPlayer("Player 2")
    unit_enemy = _make_upkeep_unit(other_player, hull_usage=100)  # skipped
    
    system = MagicMock()
    system.get_all_units.return_value = [
        (unit_a, (0, 0)),
        (unit_b, (0, 0)),
        (unit_temp, (0, 0)),
        (unit_wing, (0, 0)),
        (unit_enemy, (0, 0))
    ]
    game.galaxy.systems = {"Sol": system}
    
    expected_upkeep = (10 + 25) * UPKEEP_COST_PER_HULL_POINT
    assert game.get_player_upkeep(player) == pytest.approx(expected_upkeep)

