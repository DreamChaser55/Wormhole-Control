"""ID zero remains opaque and usable through execution, saves and presentation."""
from types import SimpleNamespace
from unittest.mock import Mock
import pygame
import pytest
from geometry import Position
from domain.celestials import Planet, MetalAsteroid, Wormhole
from constants import PlanetType
from unit_components.colony import ColonyComponent
from unit_components.mining import MiningComponent
from unit_components.antimatter import AntimatterStorage
from unit_components.movement import Hyperdrive
from unit_components.enums import HyperdriveType
from unit_orders.combat import AttackOrder, ProtectOrder
from unit_orders.repair import RepairOrder
from unit_orders.refit import RefitOrder
from unit_orders.hangar import DockOrder
from unit_orders.antimatter import TransferAntimatterOrder
from unit_orders.mining import MineOrder, ContinuousMineOrder
from unit_orders.colony import ColonizeOrder, LoadColonistsOrder
from unit_orders.base import OrderStatus
from unit_orders.abilities import UseAbilityOrder
from unit_orders.gas_giant import EnterGasGiantOrder
from gui.sidebar.order_formatting import format_order_state_data
from tests.support.campaigns import campaign, ship, legacy_document


@pytest.mark.parametrize('order_type,key', [
    (AttackOrder, 'target_unit_id'), (ProtectOrder, 'target_unit_id'),
    (RepairOrder, 'target_unit_id'), (RefitOrder, 'target_unit_id'),
    (TransferAntimatterOrder, 'target_unit_id'), (DockOrder, 'target_carrier_id'),
])
def test_target_zero_names_and_sidebar(atmosphere, order_type, key):
    game, _, unit = atmosphere
    target = ship(game, name='Zero target')
    target.id = 0
    order = order_type(unit, {key: 0})
    state = order.get_state_data()
    assert state[key] == 0 and state['target_name'] == 'Zero target'
    assert 'Zero target' in '\n'.join(format_order_state_data(state, game.galaxy))


@pytest.mark.parametrize('order_type', [MineOrder, ContinuousMineOrder])
def test_mining_executor_accepts_body_zero(atmosphere, order_type):
    game, _, unit = atmosphere
    target = MetalAsteroid((1, 0), 'Sol')
    target.id = 0
    game.galaxy.systems['Sol'].add_celestial_body(target)
    game.galaxy.systems['Sol'].move_unit_between_hexes(unit, (1, 0))
    unit.position = Position(200, 0)
    unit.add_component(MiningComponent(unit))
    order = order_type(unit, {'target_id': 0})
    unit.commander_component.add_order(order)
    assert order.status == OrderStatus.IN_PROGRESS
    assert unit.mining_component.mining_target is target


@pytest.mark.parametrize('order_type', [ColonizeOrder, LoadColonistsOrder])
def test_colony_executor_accepts_body_zero(atmosphere, order_type):
    game, _, unit = atmosphere
    target = Planet((0, 0), 'Sol', PlanetType.TERRAN)
    target.id, target.position = 0, unit.position
    game.galaxy.systems['Sol'].add_celestial_body(target)
    unit.add_component(ColonyComponent(unit))
    if order_type is ColonizeOrder:
        unit.colony_component.population_cargo = 10
    else:
        target.owner, target.population = unit.owner, 20
    order = order_type(unit, {'target_id': 0, 'amount': 10})
    unit.commander_component.add_order(order)
    assert order.status == OrderStatus.COMPLETED
    assert target.population == 10


def test_gas_entry_target_zero(atmosphere):
    game, giant, unit = atmosphere
    del game.galaxy.systems['Sol'].celestial_bodies_by_id[giant.id]
    giant.id = 0
    game.galaxy.systems['Sol'].celestial_bodies_by_id[0] = giant
    entry = EnterGasGiantOrder(unit, {'target_id': 0})
    assert entry.get_state_data()['target_name'] == giant.name
    unit.commander_component.add_order(entry)
    assert entry.status == OrderStatus.COMPLETED
    assert unit.hidden_in_gas_giant_id == 0


def test_transfer_updates_target_zero(atmosphere):
    game, _, unit = atmosphere
    target = ship(game)
    target.id, target.position = 0, unit.position
    target.add_component(AntimatterStorage(target, max_capacity=50))
    target.antimatter_component.current_amount = 0
    order = TransferAntimatterOrder(unit, {'target_unit_id': 0})
    unit.commander_component.add_order(order)
    order.update(game.galaxy)
    assert target.antimatter_component.current_amount > 0
    assert order.status != OrderStatus.FAILED


def wormholes(game):
    entry, exit_ = Wormhole((0, 0), 'Sol', 'Beta'), Wormhole((0, 0), 'Beta', 'Sol')
    exit_.id = 0
    entry.exit_wormhole_id, exit_.exit_wormhole_id = exit_.id, entry.id
    for body in (entry, exit_):
        game.galaxy.systems[body.in_system].add_celestial_body(body)
        game.galaxy.wormholes[body.id] = body
    game.galaxy._build_system_graph()
    return entry, exit_


def test_wormhole_exit_zero_executes_and_renders(monkeypatch):
    from unit_orders.movement import ReachWaypointOrder
    from turn_processor import TurnProcessor
    from rendering.galaxy_renderer import draw_galaxy_preview
    game = campaign()
    entry, exit_ = wormholes(game)
    unit = ship(game)
    unit.position, unit.in_galaxy = entry.position, game.galaxy
    unit.add_component(Hyperdrive(unit, drive_type=HyperdriveType.ADVANCED))
    unit.add_component(AntimatterStorage(unit, max_capacity=1000))
    unit.antimatter_component.current_amount = 1000
    order = ReachWaypointOrder(unit, {'destination_system_name': 'Beta', 'destination_hex_coord': (0, 0),
                                      'destination_position': exit_.position})
    unit.commander_component.add_order(order)
    TurnProcessor(game)._process_movement(unit.owner)
    assert unit.in_system == 'Beta' and unit.position == exit_.position
    lines = Mock()
    monkeypatch.setattr(pygame.draw, 'line', lines)
    # Each endpoint contributes one connection. Without zero support only one renders.
    draw_galaxy_preview(pygame.Surface((800, 600)), game.galaxy, pygame.Rect(0, 0, 800, 600))
    assert lines.call_count == 2


@pytest.mark.parametrize('order_type', [AttackOrder, ProtectOrder, UseAbilityOrder])
def test_sector_overlay_targets_zero(atmosphere, order_type):
    from rendering.sector_renderer.sector_overlay_renderer import SectorOverlayRenderer
    game, _, unit = atmosphere
    target = ship(game)
    target.id = 0
    renderer = SectorOverlayRenderer(SimpleNamespace(game=game))
    order = order_type(unit, {'target_unit_id': 0})
    assert renderer.order_targets_sector(order, 'Sol', (0, 0))
    assert not renderer.order_targets_sector(order, 'Beta', (0, 0))
    ability = UseAbilityOrder(unit, {'target_unit_id': 0, 'ability_type': 'ION_BOLT'})
    assert target.name in '\n'.join(format_order_state_data(ability.get_state_data(), game.galaxy))


def test_legacy_zero_survives_migration_command_observation_and_resave():
    from save_manager import deserialize_game_state, serialize_game_state
    from game_ai.observation import build_observation
    from game_ai.commands import CommandGateway, CommandBatch
    from game_ai.contracts import Command
    document = legacy_document('3.2')
    document['galaxy']['systems'][0]['hexes'][0]['units'][0]['id'] = 0
    game = campaign()
    assert deserialize_game_state(game, document)
    unit = game.galaxy.get_unit_by_id(0)
    assert unit is not None
    assert any(view['id'] == 0 for view in build_observation(game, game.players[0])['units'])
    command = Command('move', (0,), system_name='Sol', hex_coord=(0, 0), position=(2000, 0))
    result = CommandGateway(game).apply_batch(game.players[0], CommandBatch((command,)))
    assert result.accepted, result.errors
    assert unit.engines_component.move_target is not None
    assert format_order_state_data(unit.commander_component.current_order.get_state_data(), game.galaxy)
    current_save = serialize_game_state(game)
    assert current_save['galaxy']['systems'][0]['hexes'][0]['units'][0]['id'] == 0
    assert deserialize_game_state(game, current_save)
    assert game.galaxy.get_unit_by_id(0) is not None
