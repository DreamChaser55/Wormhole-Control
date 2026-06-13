import pytest
from unittest.mock import MagicMock, patch
from turn_processor import TurnProcessor, TAX_RATE
from geometry import Position
from entities import Planet
from tests.test_unit_components import MockUnit, MockPlayer

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

