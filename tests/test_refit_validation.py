"""Designer parity and authoritative retrofit lifecycle regressions."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from constants import HullSize, HULL_CAPACITIES
from custom_unit_templates import CustomUnitTemplate, ABILITY_REQUIRED_COMPONENTS, TurretConfig
from domain.coordinates import HexCoord
from domain.players import Player
from domain.units import Unit
from events import EventBus
from galaxy import Galaxy, StarSystem
from geometry import Position
from refit_validation import COMPONENT_SPECS, evaluate_refit, installed_configuration
from unit_components.constructor import Constructor, instantiate_component_for_unit
from unit_components.enums import AbilityType, WingType
from unit_components.sensors import Sensors
from unit_components.strikecraft import StrikecraftWingComponent
from unit_orders.base import OrderStatus
from unit_orders.refit import RefitOrder
from unit_template_validation import equipment_errors, PARAMETER_MINIMUMS


@pytest.fixture
def world():
    payer = Player('Payer', (1, 2, 3))
    ally = Player('Ally', (3, 2, 1), team_id=payer.team_id)
    payer.credits = ally.credits = 100000
    galaxy = Galaxy()
    galaxy.systems['Sol'] = StarSystem('Sol', Position(0, 0))
    game = SimpleNamespace(galaxy=galaxy, players=[payer, ally], current_player_index=0,
                           gui=None, event_bus=EventBus(), sidebar_needs_update=False)
    galaxy.game = game
    def unit(name):
        result = Unit(payer, Position(0, 0), HexCoord(0, 0), 'Sol', name, HullSize.HUGE, game=game)
        result.antimatter_component.max_capacity = result.antimatter_component.current_amount = 200
        galaxy.systems['Sol'].add_unit(result)
        return result
    actor, target = unit('Constructor'), unit('Target')
    actor.add_component(Constructor(actor))
    return game, payer, ally, actor, target


def empty_equipment(unit, hull=HullSize.HUGE):
    unit.components.clear()
    unit.hull_size = hull
    unit.hull_capacity = HULL_CAPACITIES[hull]
    unit._update_hull_usage()


def issue(world, name, config=None, action='ADD'):
    game, _, _, actor, target = world
    order = RefitOrder(actor, dict(target_unit_id=target.id, component_type=name,
                                  component_config=config or {}, action=action,
                                  cost_credits=1, time_to_build=999))
    actor.commander_component.add_order(order)
    return order


def finish(world):
    world[3].constructor_component.finish_refit(world[0].galaxy)


@pytest.mark.parametrize('hull', list(HullSize))
@pytest.mark.parametrize('name', list(COMPONENT_SPECS))
def test_every_component_and_hull_matches_designer(world, hull, name):
    target = world[-1]
    empty_equipment(target, hull)
    result = evaluate_refit(target, 'ADD', name)
    assert result.proposed is not None
    expected = CustomUnitTemplate('Equivalent design', hull, result.proposed)
    assert result.errors == expected.validate()
    if not result.errors:
        assert result.hull_cost == pytest.approx(expected.total_hull_cost)
        installed = instantiate_component_for_unit(name, target, result.configuration)
        target.add_component(installed)
        assert installed_configuration(target) == result.proposed
        assert target.current_hull_usage == pytest.approx(expected.total_hull_cost)


@pytest.mark.parametrize('role,variant,valid', [
    ('FIGHTER', 'ANTI_STRIKECRAFT', True), ('FIGHTER', 'STANDARD', False),
    ('FIGHTER', 'LONG_RANGE', False), ('BOMBER', 'ANTI_STRIKECRAFT', False),
    ('BOMBER', 'STANDARD', True), ('BOMBER', 'LONG_RANGE', True),
])
def test_wing_weapon_roles(world, role, variant, valid):
    target = world[-1]
    empty_equipment(target, HullSize.STRIKECRAFT_WING)
    target.add_component(StrikecraftWingComponent(target, wing_type=WingType[role]))
    result = evaluate_refit(target, 'ADD', 'Weapons', dict(turrets=[
        dict(type='BEAM', variant=variant, damage=1, range=1, cooldown=3)]))
    assert bool(result.errors) is not valid


@pytest.mark.parametrize('name,config', [
    ('Hyperdrive', {'drive_type': 'ADVANCED'}),
    ('CloakingDevice', {'device_type': 'ADVANCED'}),
])
def test_advanced_modules_rejected_on_tiny(world, name, config):
    target = world[-1]
    empty_equipment(target, HullSize.TINY)
    assert any('ADVANCED' in e for e in evaluate_refit(target, 'ADD', name, config).errors)


@pytest.mark.parametrize('ability', list(AbilityType))
def test_all_ability_dependencies_and_removals(world, ability):
    target = world[-1]
    empty_equipment(target)
    requirements = ABILITY_REQUIRED_COMPONENTS.get(ability.value, [])
    config = {'ability_types': [ability.value]}
    for flag in requirements:
        name = next(name for name, spec in COMPONENT_SPECS.items() if spec.flag == flag)
        result = evaluate_refit(target, 'ADD', name)
        assert not result.errors
        target.add_component(instantiate_component_for_unit(name, target, result.configuration))
    result = evaluate_refit(target, 'ADD', 'AbilityComponent', config)
    assert not result.errors
    target.add_component(instantiate_component_for_unit('AbilityComponent', target, result.configuration))
    for flag in requirements:
        name = next(name for name, spec in COMPONENT_SPECS.items() if spec.flag == flag)
        result = evaluate_refit(target, 'REMOVE', name)
        assert any('requires component' in e for e in result.errors)
        component = next(c for cls, c in target.components.items() if cls.__name__ == name)
        component.current_hit_points = 0
        assert not equipment_errors(target.hull_size, installed_configuration(target))


@pytest.mark.parametrize('name,config', [
    ('Engines', {'speed': float('nan')}), ('Engines', {'speed': float('inf')}),
    ('Engines', {'speed': True}), ('Engines', {'speed': '100'}),
    ('Engines', {'speed': -1}), ('Engines', {'speed': 10 ** 400}),
    ('Sensors', {'long_range_hexes': 1.5}), ('Sensors', {'long_range_hexes': True}),
    ('Hyperdrive', {'drive_type': 'UNKNOWN'}), ('CloakingDevice', {'device_type': 'UNKNOWN'}),
    ('AbilityComponent', {'ability_types': ['missing']}),
    ('AbilityComponent', {'ability_types': ['microjump', 'microjump']}),
    ('IntelligenceComponent', {'has_counter_intelligence': 'false'}),
    ('Weapons', {'turrets': [{}]}), ('Weapons', {'turrets': None}),
    ('Weapons', {'turrets': [dict(type='BEAM', damage=1, range=1, cooldown=.5)]}),
])
def test_invalid_inputs_never_charge_or_start(world, name, config):
    game, payer, _, actor, target = world
    empty_equipment(target)
    credits = payer.credits
    assert evaluate_refit(target, 'ADD', name, config).errors
    assert not actor.constructor_component.start_refit(target, 'ADD', name, config)
    assert payer.credits == credits
    assert actor.constructor_component.current_refit_target is None


def test_long_range_base_cost_and_snapshot(world):
    target = world[-1]
    config = {'turrets': [dict(type='BEAM', variant='LONG_RANGE', damage=10, range=300, cooldown=2)],
              'hull_cost': .001}
    result = evaluate_refit(target, 'ADD', 'Weapons', config)
    expected = TurretConfig('BEAM', 10, 300, 2, 'LONG_RANGE')
    from custom_unit_templates import calc_weapons_hull_cost
    assert result.hull_cost == pytest.approx(calc_weapons_hull_cost([expected]))
    order = issue(world, 'Weapons', config)
    assert order.parameters['cost_credits'] == round(result.hull_cost * 30)
    assert order.parameters['time_to_build'] == max(1, round(result.hull_cost / 5))
    finish(world)
    assert installed_configuration(target).turrets == [expected]
    assert target.weapons_component.turrets[0].range == 900
    assert order.status == OrderStatus.COMPLETED


def test_empty_weapons_bay_is_not_given_an_unpriced_turret(world):
    assert issue(world, 'Weapons', {'turrets': []}).status == OrderStatus.IN_PROGRESS
    finish(world)
    assert world[-1].weapons_component.turrets == []
    assert world[-1].weapons_component.hull_cost == 0


def test_strict_existing_errors_and_last_component(world):
    target = world[-1]
    empty_equipment(target, HullSize.TINY)
    target.add_component(instantiate_component_for_unit('Hyperdrive', target, {'drive_type': 'ADVANCED'}))
    target.add_component(Sensors(target, short_range_radius=0, long_range_hexes=0))
    assert evaluate_refit(target, 'ADD', 'Defenses').errors
    assert not evaluate_refit(target, 'REMOVE', 'Hyperdrive').errors
    target.remove_component(type(target.hyperdrive_component))
    assert any('At least one' in e for e in evaluate_refit(target, 'REMOVE', 'Sensors').errors)


def test_busy_direct_job_cannot_be_overwritten(world):
    _, payer, _, actor, target = world
    constructor = actor.constructor_component
    assert constructor.start_refit(target, 'ADD', 'Engines')
    job = deepcopy(constructor.current_refit_target)
    credits = payer.credits
    assert not constructor.start_refit(target, 'ADD', 'Defenses')
    assert constructor.current_refit_target == job and payer.credits == credits


def test_failed_completion_refunds_original_payer_once(world):
    _, payer, ally, actor, target = world
    target.owner = ally
    credits, ally_credits = payer.credits, ally.credits
    order = issue(world, 'Engines')
    assert payer.credits < credits and ally.credits == ally_credits
    # A concurrent installation wins; completion must not overwrite it.
    existing = instantiate_component_for_unit('Engines', target, {'speed': 20})
    target.add_component(existing)
    finish(world)
    assert order.status == OrderStatus.FAILED
    assert target.engines_component is existing
    assert payer.credits == credits and ally.credits == ally_credits
    finish(world)
    order.cancel()
    assert payer.credits == credits


def test_salvage_only_on_success_and_dependencies_rechecked(world):
    _, payer, _, actor, target = world
    target.add_component(instantiate_component_for_unit('Engines', target, {'speed': 100}))
    credits = payer.credits
    order = issue(world, 'Engines', action='REMOVE')
    assert payer.credits == credits
    target.add_component(instantiate_component_for_unit('TradeComponent', target))
    finish(world)
    assert order.status == OrderStatus.FAILED and target.engines_component
    assert payer.credits == credits
    target.remove_component(type(target.trade_component))
    actor.commander_component.current_order = None
    order = issue(world, 'Engines', action='REMOVE')
    salvage = actor.constructor_component.current_refit_target['salvage_due']
    finish(world)
    assert order.status == OrderStatus.COMPLETED
    assert payer.credits == credits + salvage
    finish(world)
    assert payer.credits == credits + salvage


def test_cancellation_has_no_salvage(world):
    _, payer, _, _, target = world
    credits = payer.credits
    order = issue(world, 'Sensors', action='REMOVE')
    order.cancel()
    finish(world)
    assert target.sensors_component and payer.credits == credits


def test_zero_available_agents_and_fuel_do_not_invalidate_installed_design(world):
    target = world[-1]
    result = evaluate_refit(target, 'ADD', 'IntelligenceComponent', {'agents_capacity': 2})
    target.add_component(instantiate_component_for_unit('IntelligenceComponent', target, result.configuration))
    target.intelligence_component.agents_count = 0
    target.antimatter_component.current_amount = 0
    assert installed_configuration(target).intelligence_agents_count == 2
    assert not evaluate_refit(target, 'ADD', 'Engines').errors


@pytest.mark.parametrize('field,minimum', list(PARAMETER_MINIMUMS.items()))
def test_every_parameter_minimum_at_execution_boundary(world, field, minimum):
    target = world[-1]
    empty_equipment(target)
    name, parameter = next((name, parameter) for name, spec in COMPONENT_SPECS.items()
                           for parameter, mapped in spec.fields.items() if mapped == field)
    accepted = evaluate_refit(target, 'ADD', name, {parameter: minimum})
    assert not accepted.errors
    rejected = evaluate_refit(target, 'ADD', name, {parameter: minimum - 1})
    assert any(field in error for error in rejected.errors)


def test_designer_turret_numeric_policy_does_not_gain_new_bounds(world):
    target = world[-1]
    config = {'turrets': [dict(type='BEAM', damage=-1, range=-1, cooldown=0)]}
    result = evaluate_refit(target, 'ADD', 'Weapons', config)
    assert not result.errors
    assert CustomUnitTemplate('Same policy', target.hull_size, result.proposed).validate() == []


def test_advanced_zero_radius_installs_exactly_the_validated_configuration(world):
    target = world[-1]
    result = evaluate_refit(target, 'ADD', 'CloakingDevice', {'device_type': 'ADVANCED', 'area_radius': 0})
    assert not result.errors
    order = issue(world, 'CloakingDevice', result.configuration)
    finish(world)
    assert order.status == OrderStatus.COMPLETED
    assert target.cloaking_component.area_radius == 0
    assert target.cloaking_component.hull_cost == 0


def test_queued_prerequisite_uses_completed_equipment(world):
    _, _, _, actor, target = world
    first = issue(world, 'Engines')
    second = issue(world, 'TradeComponent')
    assert second.status == OrderStatus.PENDING
    finish(world)
    actor.commander_component.update()
    assert first.status == OrderStatus.COMPLETED
    assert second.status == OrderStatus.IN_PROGRESS
    finish(world)
    assert second.status == OrderStatus.COMPLETED and target.trade_component


def test_approach_parent_completes_after_refit_child(world):
    _, _, _, actor, target = world
    actor.add_component(instantiate_component_for_unit('Engines', actor, {'speed': 100}))
    actor.position = Position(1000, 0)
    order = issue(world, 'Engines')
    assert len(order.sub_orders) == 2
    # Resolve approach deterministically; the real refit child must own settlement.
    actor.position = Position(0, 0)
    order.sub_orders[0].status = OrderStatus.COMPLETED
    order.update(world[0].galaxy)
    assert actor.constructor_component.refit_order_id == order.sub_orders[0].public_id
    finish(world)
    order.update(world[0].galaxy)
    assert order.status == OrderStatus.COMPLETED and target.engines_component


@pytest.mark.parametrize('change', ['owner', 'destroyed', 'capacity'])
def test_completion_checks_live_target_and_refunds(world, change):
    _, payer, ally, _, target = world
    credits = payer.credits
    order = issue(world, 'Engines')
    if change == 'owner':
        ally.team_id = payer.team_id + 1
        target.owner = ally
    elif change == 'destroyed':
        target.current_hit_points = 0
    else:
        target.current_hull_usage = target.hull_capacity
    finish(world)
    assert order.status == OrderStatus.FAILED
    assert target.engines_component is None and payer.credits == credits


def test_occupied_bay_rechecked_at_completion(world):
    target = world[-1]
    result = evaluate_refit(target, 'ADD', 'HangarComponent')
    target.add_component(instantiate_component_for_unit('HangarComponent', target, result.configuration))
    order = issue(world, 'HangarComponent', action='REMOVE')
    target.hangar_component.docked_units.append(world[3])
    finish(world)
    assert order.status == OrderStatus.FAILED and target.hangar_component


@pytest.mark.parametrize('legacy', [False, True])
@pytest.mark.parametrize('outcome', ['success', 'cancel', 'invalid'])
def test_saved_removal_settles_exactly_once(legacy, outcome):
    from tests.support.campaigns import campaign, ship
    from save_manager import serialize_game_state, deserialize_game_state
    from campaign_graph import find_unit
    from save_migrations import migrate_save
    game = campaign()
    actor, target = ship(game, 'Builder'), ship(game, 'Target')
    target.antimatter_component.max_capacity = target.antimatter_component.current_amount = 200
    actor.add_component(Constructor(actor))
    target.add_component(instantiate_component_for_unit('Engines', target, {'speed': 100}))
    payer = game.players[0]
    payer.credits = 5000
    order = RefitOrder(actor, dict(target_unit_id=target.id, action='REMOVE', component_type='Engines'))
    actor.commander_component.add_order(order)
    salvage = actor.constructor_component.current_refit_target['salvage_due']
    state = serialize_game_state(game)
    assert state['version'] == '4.2'
    if legacy:
        state['version'] = '4.1'
        def strip(value):
            if isinstance(value, dict):
                if value.get('type') == 'Constructor':
                    job = value['runtime']['current_refit_target']
                    if job:
                        job.pop('payer_id')
                        job.pop('salvage_due')
                for child in value.values():
                    strip(child)
            elif isinstance(value, list):
                for child in value:
                    strip(child)
        strip(state)
        state['players'][0]['credits'] += salvage  # historical upfront payment
        migrated, _ = migrate_save(state)
        assert migrate_save(migrated)[0] == migrated
    assert deserialize_game_state(game, state)
    actor, target = find_unit(game.galaxy, actor.id), find_unit(game.galaxy, target.id)
    order = actor.commander_component.current_order
    ctor = actor.constructor_component
    if outcome == 'cancel':
        order.cancel()
    elif outcome == 'invalid':
        target.add_component(instantiate_component_for_unit('TradeComponent', target))
    ctor.finish_refit(game.galaxy)
    expected = 5000 + (salvage if legacy or outcome == 'success' else 0)
    assert game.players[0].credits == expected
    assert order.status == {'success': OrderStatus.COMPLETED, 'cancel': OrderStatus.CANCELLED,
                            'invalid': OrderStatus.FAILED}[outcome]
    order.cancel()
    ctor.finish_refit(game.galaxy)
    assert game.players[0].credits == expected


def test_migration_finds_original_payer_on_nested_units():
    from save_migrations import migrate_save
    job = dict(target_unit_id=9, action='REMOVE', component_type='Engines', component_config={},
               cost_credits=0, time_to_build=1)
    raw = dict(owner_id=2, components={
        'Constructor': dict(type='Constructor', runtime=dict(current_refit_target=job, refit_order_id='job')),
        'Commander': dict(type='Commander', runtime=dict(current_order=dict(public_id='job', runtime_state=dict(charged_player_id=1)))),
    })
    state = dict(version='4.1', galaxy=dict(systems=[dict(hexes=[dict(
        units=[dict(owner_id=2, components={'HangarComponent': dict(runtime=dict(docked_units=[raw]))})],
        celestial_bodies=[dict(hidden_units=[deepcopy(raw)])])])]))
    migrated, _ = migrate_save(state)
    sector = migrated['galaxy']['systems'][0]['hexes'][0]
    for unit in [sector['units'][0]['components']['HangarComponent']['runtime']['docked_units'][0],
                 sector['celestial_bodies'][0]['hidden_units'][0]]:
        assert unit['components']['Constructor']['runtime']['current_refit_target']['payer_id'] == 1
        assert unit['components']['Constructor']['runtime']['current_refit_target']['salvage_due'] == 0
