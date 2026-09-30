"""Live-playtest failures reproduced with real offline game entities."""
import pytest

from constants import HullSize
from game_ai.contracts import Command
from game_ai.observation import build_observation
from geometry import Position
from tests.support.commands import world, issue
from tests.support.combat import create_combat_ship
from unit_components.abilities import AbilityComponent
from unit_components.antimatter import AntimatterStorage
from unit_components.enums import AbilityType, TurretVariant
from unit_components.marines import MarinesComponent
from unit_components.strikecraft import StrikecraftWingComponent
from unit_components.enums import WingType
from unit_orders.base import OrderStatus
from unit_orders.abilities import UseAbilityOrder
from unit_orders.combat import AttackOrder
from unit_orders.movement import MoveOrder


def abilities(unit):
    unit.add_component(AntimatterStorage(unit, max_capacity=1000))
    unit.add_component(MarinesComponent(unit, marines_count=20))
    unit.add_component(AbilityComponent(unit, [AbilityType.DESIGNATE_TARGET, AbilityType.CAPTURE_UNIT,
                                             AbilityType.DRAIN_ANTIMATTER, AbilityType.ION_BOLT]))


def observed(game, player, unit):
    return next(item for item in build_observation(game, player)['units'] if item['id'] == unit.id)


@pytest.mark.parametrize('kind', ['designate_target', 'capture_unit', 'drain_antimatter'])
@pytest.mark.parametrize('allied', [False, True])
def test_hostile_legacy_abilities_exclude_friendly_targets_and_reject_before_replacement(kind, allied):
    game, player, enemy, unit = world()
    abilities(unit)
    if allied:
        enemy.team_id = player.team_id
    target = create_combat_ship(game.galaxy, enemy if allied else player, 'Friendly', (0, 0), pos=(100, 0))
    root = MoveOrder(unit, {'destination_system_name': 'Sol', 'destination_hex_coord': (0, 0), 'destination_position': Position(900, 0)})
    unit.commander_component.add_order(root)
    before = (unit.name, unit.antimatter_component.current_amount, list(player.order_history))
    assert target.id not in observed(game, player, unit)['command_options']['use_ability']['targets_by_ability'][kind]
    result = issue(game, player, Command('rename_unit', (unit.id,), new_name='Changed'),
                   Command('use_ability', (unit.id,), ability=kind, target_id=target.id))
    assert not result.accepted and result.errors[0].code == 'invalid_relation'
    assert unit.commander_component.current_order is root
    assert before == (unit.name, unit.antimatter_component.current_amount, player.order_history)
    assert not unit.ability_component.activate(AbilityType(kind), game.galaxy, target_unit_id=target.id)
    assert before[1] == unit.antimatter_component.current_amount


def test_legacy_execution_reports_relation_and_capture_blockers():
    game, player, enemy, unit = world()
    abilities(unit)
    target = create_combat_ship(game.galaxy, player, 'Friendly', (0, 0), pos=(100, 0))
    order = UseAbilityOrder(unit, {'ability_type': 'designate_target', 'target_unit_id': target.id})
    unit.commander_component.add_order(order)
    assert order.status == OrderStatus.FAILED and player.order_history[-1]['reason'] == 'invalid_relation'
    target.owner = enemy
    result = issue(game, player, Command('use_ability', (unit.id,), ability='capture_unit', target_id=target.id))
    assert not result.accepted and result.errors[0].code == 'target_not_disabled'


def test_ion_bolt_retains_its_existing_allied_target_policy():
    game, player, _, unit = world()
    abilities(unit)
    target = create_combat_ship(game.galaxy, player, 'Friendly', (0, 0), pos=(100, 0))
    result = issue(game, player, Command('use_ability', (unit.id,), ability='ion_bolt', target_id=target.id))
    assert result.accepted and target.is_disabled


def test_drain_discovery_does_not_disclose_enemy_fuel():
    game, player, enemy, unit = world()
    abilities(unit)
    target = create_combat_ship(game.galaxy, enemy, 'Enemy', (0, 0), pos=(100, 0))
    target.add_component(AntimatterStorage(target, max_capacity=100))
    full = observed(game, player, unit)['command_options']['use_ability']['targets_by_ability']['drain_antimatter']
    target.antimatter_component.current_amount = 0
    empty = observed(game, player, unit)['command_options']['use_ability']['targets_by_ability']['drain_antimatter']
    assert full == empty and target.id in empty


@pytest.mark.parametrize('command', ['attack', 'attack_long_range'])
@pytest.mark.parametrize('craft,reason', [('station', 'hyperdrive_unavailable'), ('wing', 'sector_unreachable'), ('cutter', 'hyperdrive_unavailable')])
def test_impossible_cross_sector_attacks_are_not_advertised_or_accepted(command, craft, reason):
    game, player, enemy, unit = world()
    target = create_combat_ship(game.galaxy, enemy, 'Enemy', (0, 1), pos=(100, 0))
    create_combat_ship(game.galaxy, player, 'Scout', (0, 1))
    unit.remove_component(type(unit.hyperdrive_component))
    if craft == 'station':
        unit.remove_component(type(unit.engines_component))
    elif craft == 'wing':
        unit.hull_size = HullSize.STRIKECRAFT_WING
        unit.add_component(StrikecraftWingComponent(unit, WingType.BOMBER))
    else:
        unit.hull_size = HullSize.TINY
    unit.weapons_component.turrets[0].variant = TurretVariant.LONG_RANGE
    assert target.id not in observed(game, player, unit)['command_options'][command]['target_ids']
    result = issue(game, player, Command(command, (unit.id,), target_id=target.id))
    assert not result.accepted and result.errors[0].code == reason
    assert unit.commander_component.current_order is None and not player.order_history
    direct = AttackOrder(unit, {'target_unit_id': target.id})
    unit.commander_component.add_order(direct)
    assert direct.status == OrderStatus.FAILED and player.order_history[-1]['reason'] == reason


def test_station_can_fire_its_longer_turret_but_cannot_approach():
    game, player, enemy, unit = world()
    unit.remove_component(type(unit.engines_component))
    target = create_combat_ship(game.galaxy, enemy, 'Enemy', (0, 0), pos=(500, 0))
    from unit_components.weapons import Turret
    from unit_components.enums import TurretType
    unit.weapons_component.add_turret(Turret(TurretType.BEAM, range=800, damage=20, cooldown=1, parent_unit=unit))
    assert target.id in observed(game, player, unit)['command_options']['attack']['target_ids']
    assert issue(game, player, Command('attack', (unit.id,), target_id=target.id)).accepted
    root = unit.commander_component.current_order
    assert root.status == OrderStatus.IN_PROGRESS and not root.sub_orders
    target.position = Position(1500, 0)
    result = issue(game, player, Command('attack', (unit.id,), target_id=target.id))
    assert not result.accepted and result.errors[0].code == 'engines_unavailable'
    assert unit.commander_component.current_order is root


def test_feasible_sector_approach_remains_legal():
    game, player, enemy, unit = world()
    target = create_combat_ship(game.galaxy, enemy, 'Enemy', (0, 1), pos=(100, 0))
    create_combat_ship(game.galaxy, player, 'Scout', (0, 1))
    unit.add_component(AntimatterStorage(unit, max_capacity=1000))
    assert target.id in observed(game, player, unit)['command_options']['attack']['target_ids']
    assert issue(game, player, Command('attack', (unit.id,), target_id=target.id)).accepted
    assert unit.commander_component.current_order.sub_orders


def test_carrier_departure_fails_docking_with_actionable_root_reason():
    from unit_components.strikecraft import StrikecraftBayComponent
    from unit_orders.hangar import DockOrder
    game, player, _, wing = world()
    game.game_started = True
    from turn_briefing import begin_window, finish_window, summary_view
    begin_window(game, player)
    wing.hull_size = HullSize.STRIKECRAFT_WING
    wing.add_component(StrikecraftWingComponent(wing, WingType.BOMBER))
    carrier = create_combat_ship(game.galaxy, player, 'Carrier', (0, 0), pos=(500, 0))
    carrier.add_component(StrikecraftBayComponent(carrier, max_slots=1))
    carrier.strikecraft_bay_component.assign_wing(wing, 0)
    carrier.strikecraft_bay_component.launched_units.append(wing)
    root = DockOrder(wing, {'target_carrier_id': carrier.id})
    wing.commander_component.add_order(root)
    assert root.status == OrderStatus.IN_PROGRESS and root.sub_orders
    sector = game.galaxy.systems['Sol'].hexes[(0, 0)]
    sector.remove_unit(carrier)
    carrier.in_hex = (0, 1)
    game.galaxy.systems['Sol'].hexes[(0, 1)].add_unit(carrier)
    root.update(game.galaxy)
    assert root.status == OrderStatus.FAILED and not root.sub_orders
    assert len(player.order_history) == 1
    assert player.order_history[-1]['reason'] == 'carrier_out_of_sector'
    finish_window(game, player)
    assert 'carrier out of sector' in str(summary_view(player)).lower()


def test_failed_deployment_retains_docked_unit_and_reports_unsafe_placement(monkeypatch):
    from unit_components.hangar import HangarComponent
    from unit_orders.hangar import DeployUnitOrder
    game, player, _, child = world()
    child.hull_size = HullSize.TINY
    carrier = create_combat_ship(game.galaxy, player, 'Carrier', (0, 0), pos=(500, 0))
    carrier.add_component(HangarComponent(carrier, max_slots=4))
    assert carrier.hangar_component.dock(child, game.galaxy)
    monkeypatch.setattr('unit_components.hangar.find_deployment_position', lambda *args: None)
    order = DeployUnitOrder(carrier, {'docked_unit_id': child.id})
    carrier.commander_component.add_order(order)
    assert order.status == OrderStatus.FAILED
    assert child in carrier.hangar_component.docked_units
    assert player.order_history[-1]['reason'] == 'unsafe_placement'
