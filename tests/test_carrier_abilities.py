"""Carrier abilities share order, combat, visibility and persistence contracts."""
import json

import pytest

from constants import HullSize
from geometry import Position
from tests.support.campaigns import campaign, ship
from unit_components.abilities import AbilityComponent, ABILITY_CLASSES
from unit_components.antimatter import AntimatterStorage
from unit_components.enums import AbilityType, TurretType, TurretVariant, WingType
from unit_components.movement import Engines
from unit_components.sensors import Sensors
from unit_components.strikecraft import StrikecraftBayComponent, StrikecraftWingComponent
from unit_components.weapons import Weapons, Turret
from tactical_balance import STRIKECRAFT_ABILITIES
from tactical_abilities import activate, get_instance, validate, combat_hit, start_owner_turn
from strikecraft_abilities import process_flak, reconcile, wing_order
from game_ai.commands import CommandGateway
from game_ai.contracts import Command, CommandBatch
from game_ai.observation import build_observation
from save_manager import serialize_game_state, deserialize_game_state


def scenario():
    game = campaign()
    game.galaxy.game = game
    carrier = ship(game, 'Carrier')
    for comp in (Engines(carrier, speed=50), AntimatterStorage(carrier, max_capacity=1000),
                 Sensors(carrier, short_range_radius=2000, long_range_hexes=2),
                 StrikecraftBayComponent(carrier, max_slots=6),
                 AbilityComponent(carrier, [AbilityType(k) for k in STRIKECRAFT_ABILITIES])):
        carrier.add_component(comp)
    arm(carrier, anti=True, damage=8)
    bomber = make_wing(game, carrier)
    fighter = make_wing(game, carrier, fighter=True)
    enemy = ship(game, 'Enemy ship', owner=1)
    enemy.position = Position(400, 0)
    enemy_wing = make_wing(game, None, fighter=True, owner=1)
    enemy_wing.position = Position(450, 0)
    return game, carrier, bomber, fighter, enemy, enemy_wing


def arm(unit, anti=False, damage=4):
    weapons = Weapons(unit)
    weapons.add_turret(Turret(TurretType.MASS_DRIVER, damage, 200, 2, unit,
                             TurretVariant.ANTI_STRIKECRAFT if anti else TurretVariant.STANDARD))
    unit.add_component(weapons)


def make_wing(game, carrier, fighter=False, owner=0):
    wing = ship(game, 'Fighter' if fighter else 'Bomber', owner=owner, hull=HullSize.STRIKECRAFT_WING)
    wing.position = Position(200, 0)
    wing.add_component(Engines(wing, speed=40))
    comp = StrikecraftWingComponent(wing, WingType.FIGHTER if fighter else WingType.BOMBER)
    comp.mother_carrier = carrier
    wing.add_component(comp)
    arm(wing, anti=fighter)
    if carrier:
        carrier.strikecraft_bay_component.launched_units.append(wing)
    return wing


def issue(game, caster, kind, target=None, queue=False):
    return CommandGateway(game).apply_batch(caster.owner, CommandBatch((Command(
        type='use_ability', unit_ids=(caster.id,), ability=kind, target_id=target.id if target else None, queue=queue),)))


def next_round(game, player=None):
    game.turn_number += 1
    start_owner_turn(game.galaxy, player or game.players[0], game.turn_number)


@pytest.mark.parametrize('kind', sorted(STRIKECRAFT_ABILITIES))
def test_fake_provider_can_cast_carrier_ability(kind):
    from game_ai.adapters.fake import FakePlanningProvider
    from game_ai.adapters.base import PlanningRequest
    from game_ai.contracts import TurnPlan
    from game_ai.runtime import get_runtime_config
    from tests.support.ai import EMPTY_PATCH
    game, carrier, bomber, _, enemy, enemy_wing = scenario()
    targets = {'attack_run': enemy, 'tracking_lock': enemy_wing,
               'evasive_formation': bomber, 'emergency_recovery': bomber}
    target = targets.get(kind)
    command = Command(type='use_ability', unit_ids=(carrier.id,), ability=kind, target_id=target.id if target else None)
    plan = TurnPlan.from_dict({'plan': [], 'commands': [command.to_dict()], 'memory_patch': EMPTY_PATCH, 'end_turn': True})
    observation = build_observation(game, carrier.owner)
    assert observation['ability_catalog']['flak_barrage']['radius'] == 500
    provider = FakePlanningProvider([plan])
    output = provider.plan_turn(PlanningRequest('test', 'agent', 'One', 7, observation, {}), get_runtime_config('low'))
    fuel = carrier.antimatter_component.current_amount
    result = CommandGateway(game).apply_batch(carrier.owner, output.plan.batch)
    assert result.accepted, result.errors
    from tactical_balance import SPECS
    assert carrier.antimatter_component.current_amount == fuel - SPECS[kind].cost
    assert not issue(game, carrier, kind, target).accepted


def test_attack_run_group_reaction_window_and_one_salvo():
    game, carrier, bomber, fighter, target, _ = scenario()
    second = make_wing(game, carrier)
    target.position = Position(350, 0)
    assert issue(game, carrier, 'attack_run', target).accepted
    assert wing_order(bomber) and wing_order(second)
    assert not wing_order(fighter)
    assert bomber.engines_component.effective_speed == 60
    before = target.current_hit_points
    bomber.weapons_component.update(game.galaxy)
    assert target.current_hit_points == before
    next_round(game)
    bomber.weapons_component.update(game.galaxy)
    assert target.current_hit_points == before - 8
    bomber.weapons_component.update(game.galaxy)
    assert target.current_hit_points == before - 8
    from constants import XP_SPEED_BONUS
    assert bomber.engines_component.effective_speed == 40 * bomber.xp_multiplier(XP_SPEED_BONUS)
    assert wing_order(second)


def test_evasion_modifies_both_directions_and_not_hazards():
    game, carrier, bomber, _, target, _ = scenario()
    assert issue(game, carrier, 'evasive_formation', bomber).accepted
    before = bomber.current_hit_points
    combat_hit(bomber, 10, TurretType.MASS_DRIVER)
    assert bomber.current_hit_points == before - 5
    bomber.take_damage(4)
    assert bomber.current_hit_points == before - 9
    turret = bomber.weapons_component.turrets[0]
    turret.target = target
    before = target.current_hit_points
    turret.fire()
    assert target.current_hit_points == before - 3
    for _ in range(3):
        next_round(game)
    before = bomber.current_hit_points
    combat_hit(bomber, 10)
    assert bomber.current_hit_points == before - 10


def test_recovery_aborts_run_and_locks_relaunch():
    game, carrier, bomber, _, target, _ = scenario()
    bomber.position = Position(300, 0)
    assert issue(game, carrier, 'attack_run', target).accepted
    spent = carrier.antimatter_component.current_amount
    assert issue(game, carrier, 'emergency_recovery', bomber).accepted
    assert carrier.antimatter_component.current_amount == spent - 30
    assert bomber.engines_component.effective_speed == 80
    bomber.position = Position(150, 0)
    wing_order(bomber).update(game.galaxy)
    bay = carrier.strikecraft_bay_component
    assert bomber in bay.docked_units
    assert not bay.can_deploy(bomber, game.galaxy)
    next_round(game)
    assert bay.can_deploy(bomber, game.galaxy)


@pytest.mark.parametrize('offset,damage', [(499, 4), (500, 4), (501, 0)])
def test_flak_radius_and_phase_idempotence(offset, damage):
    game, carrier, bomber, _, _, enemy = scenario()
    enemy.position = Position(carrier.position.x + offset, 0)
    assert issue(game, carrier, 'flak_barrage').accepted
    before, friendly_before = enemy.current_hit_points, bomber.current_hit_points
    process_flak(game.galaxy, enemy.owner, game.turn_number)
    process_flak(game.galaxy, enemy.owner, game.turn_number)
    assert enemy.current_hit_points == before - damage
    assert bomber.current_hit_points == friendly_before


def test_tracking_is_caster_only_and_breaks_outside_range():
    game, carrier, _, fighter, _, enemy = scenario()
    assert issue(game, carrier, 'tracking_lock', enemy).accepted
    turret = carrier.weapons_component.turrets[0]
    before = enemy.current_hit_points
    turret.target = enemy
    turret.fire()
    assert enemy.current_hit_points == before - 16
    from strikecraft_abilities import outgoing_multiplier
    assert outgoing_multiplier(fighter, enemy, fighter.weapons_component.turrets[0]) == 1
    enemy.position = Position(1000, 0)
    reconcile(game.galaxy)
    assert not get_instance(carrier, 'tracking_lock').is_active


@pytest.mark.parametrize('kind', sorted(STRIKECRAFT_ABILITIES))
def test_active_ability_save_round_trip(kind):
    game, carrier, bomber, _, enemy, enemy_wing = scenario()
    bomber.position = Position(300, 0)
    target = {'attack_run': enemy, 'tracking_lock': enemy_wing, 'evasive_formation': bomber,
              'emergency_recovery': bomber}.get(kind)
    assert issue(game, carrier, kind, target).accepted
    state = json.loads(json.dumps(serialize_game_state(game)))
    assert state['version'] == '4.3'
    assert deserialize_game_state(game, state)
    restored = game.galaxy.get_unit_by_id(carrier.id)
    assert restored.antimatter_component.current_amount == carrier.antimatter_component.current_amount
    assert get_instance(restored, kind).is_active
    after = json.loads(json.dumps(serialize_game_state(game)))
    after.pop('timestamp')
    state.pop('timestamp')
    assert after == state


def test_no_wing_equipment_and_target_restrictions():
    game, carrier, bomber, _, enemy, enemy_wing = scenario()
    assert validate(carrier, 'evasive_formation', game.galaxy, enemy_wing.id) == 'target_unavailable'
    assert validate(carrier, 'attack_run', game.galaxy, enemy_wing.id) == 'target_unavailable'
    bomber.commander_component.stop_and_idle()
    carrier.strikecraft_bay_component.current_hit_points = 0
    assert not activate(carrier, 'attack_run', game.galaxy, enemy.id)
    assert not bomber.ability_component


@pytest.mark.parametrize('loss', ['disabled', 'sensors', 'bay', 'captured', 'hidden', 'destroyed'])
def test_source_loss_cancels_run_and_removes_speed(loss):
    game, carrier, bomber, _, target, _ = scenario()
    assert issue(game, carrier, 'attack_run', target).accepted
    root = wing_order(bomber)
    if loss == 'disabled':
        carrier.is_disabled = True
    elif loss == 'sensors':
        carrier.sensors_component.current_hit_points = 0
    elif loss == 'bay':
        carrier.strikecraft_bay_component.current_hit_points = 0
    elif loss == 'captured':
        carrier.owner = target.owner
    elif loss == 'hidden':
        carrier.is_hidden_in_gas_giant = True
    else:
        carrier.current_hit_points = 0
    reconcile(game.galaxy)
    assert root.status.name == 'FAILED'
    assert bomber.engines_component.effective_speed == 40
    assert not get_instance(carrier, 'attack_run').is_active


def test_runs_follow_moving_targets_and_cancel_without_refund():
    from turn_processor import TurnProcessor
    game, carrier, bomber, _, target, _ = scenario()
    target.position = Position(650, 0)
    assert issue(game, carrier, 'attack_run', target).accepted
    processor = TurnProcessor(game)
    processor._process_movement(carrier.owner)
    assert bomber.position.x > 200
    target.position = Position(600, 200)
    next_round(game)
    processor._process_movement(carrier.owner)
    assert bomber.position.y > 0
    fuel = carrier.antimatter_component.current_amount
    bomber.commander_component.clear_explicit_orders()
    assert not wing_order(bomber)
    assert bomber.engines_component.effective_speed == 40
    assert carrier.antimatter_component.current_amount == fuel
    assert get_instance(carrier, 'attack_run').cooldown_remaining > 0


def test_evasive_run_damage_uses_both_modifiers_once():
    game, carrier, bomber, _, target, _ = scenario()
    target.position = Position(300, 0)
    assert issue(game, carrier, 'evasive_formation', bomber).accepted
    assert issue(game, carrier, 'attack_run', target).accepted
    next_round(game)
    before = target.current_hit_points
    bomber.weapons_component.update(game.galaxy)
    assert target.current_hit_points == before - 6


def test_flak_overlap_follows_sources_and_ignores_allies():
    from domain.players import Player
    game, carrier, _, _, _, enemy = scenario()
    other = ship(game, 'Second flak ship')
    other.add_component(AntimatterStorage(other, max_capacity=500))
    other.add_component(AbilityComponent(other, [AbilityType.FLAK_BARRAGE]))
    arm(other, anti=True)
    ally = Player('Ally', (100, 100, 200), team_id=carrier.owner.team_id)
    game.players.append(ally)
    allied_wing = make_wing(game, None, owner=2)
    assert issue(game, carrier, 'flak_barrage').accepted
    assert issue(game, other, 'flak_barrage').accepted
    before = enemy.current_hit_points
    process_flak(game.galaxy, enemy.owner, game.turn_number)
    assert enemy.current_hit_points == before - 4
    friendly_before = allied_wing.current_hit_points
    process_flak(game.galaxy, ally, game.turn_number)
    assert allied_wing.current_hit_points == friendly_before
    carrier.position = other.position = Position(-1000, 0)
    next_round(game)
    process_flak(game.galaxy, enemy.owner, game.turn_number)
    assert enemy.current_hit_points == before - 4


def test_flak_evasion_save_and_no_duplicate_damage_after_load():
    game, carrier, bomber, _, _, _ = scenario()
    enemy_carrier = ship(game, 'Enemy carrier', owner=1)
    enemy_carrier.add_component(AntimatterStorage(enemy_carrier, max_capacity=500))
    enemy_carrier.add_component(AbilityComponent(enemy_carrier, [AbilityType.FLAK_BARRAGE]))
    arm(enemy_carrier, anti=True)
    assert issue(game, carrier, 'evasive_formation', bomber).accepted
    assert activate(enemy_carrier, 'flak_barrage', game.galaxy)
    before = bomber.current_hit_points
    process_flak(game.galaxy, carrier.owner, game.turn_number)
    assert bomber.current_hit_points == before - 2
    assert deserialize_game_state(game, json.loads(json.dumps(serialize_game_state(game))))
    process_flak(game.galaxy, game.players[0], game.turn_number)
    assert game.galaxy.get_unit_by_id(bomber.id).current_hit_points == before - 2


def test_projected_recovery_removes_bomber_from_later_run_atomically():
    game, carrier, bomber, _, target, _ = scenario()
    fuel = carrier.antimatter_component.current_amount
    batch = CommandBatch((
        Command(type='use_ability', unit_ids=(carrier.id,), ability='emergency_recovery', target_id=bomber.id),
        Command(type='use_ability', unit_ids=(carrier.id,), ability='attack_run', target_id=target.id),
    ))
    result = CommandGateway(game).apply_batch(carrier.owner, batch)
    assert not result.accepted and result.failure_stage == 'preflight'
    assert carrier.antimatter_component.current_amount == fuel
    assert bomber in carrier.strikecraft_bay_component.launched_units


def test_queued_cast_selects_wings_at_execution():
    from unit_orders.movement import MoveOrder
    game, carrier, bomber, _, target, _ = scenario()
    carrier.commander_component.add_order(MoveOrder(carrier, {
        'destination_system_name': 'Sol', 'destination_hex_coord': (0, 0), 'destination_position': Position(110, 0)}))
    assert issue(game, carrier, 'attack_run', target, queue=True).accepted
    assert not wing_order(bomber)
    later = make_wing(game, carrier)
    move = carrier.commander_component.current_order
    carrier.commander_component.cancel_order(move.order_id)
    assert wing_order(bomber) and wing_order(later)


def test_save_continuation_releases_exactly_one_salvo():
    game, carrier, bomber, _, target, _ = scenario()
    target.position = Position(300, 0)
    assert issue(game, carrier, 'attack_run', target).accepted
    assert deserialize_game_state(game, json.loads(json.dumps(serialize_game_state(game))))
    bomber, target = game.galaxy.get_unit_by_id(bomber.id), game.galaxy.get_unit_by_id(target.id)
    before = target.current_hit_points
    next_round(game)
    bomber.weapons_component.update(game.galaxy)
    bomber.weapons_component.update(game.galaxy)
    assert target.current_hit_points == before - 8


@pytest.mark.parametrize('kind', sorted(STRIKECRAFT_ABILITIES))
def test_human_event_uses_same_gateway_and_no_caster_approach(kind):
    from events import EventBus, UseAbilityEvent
    from order_system import OrderSystem
    game, carrier, bomber, _, enemy, enemy_wing = scenario()
    target = {'attack_run': enemy, 'tracking_lock': enemy_wing, 'evasive_formation': bomber,
              'emergency_recovery': bomber}.get(kind)
    bomber.position = Position(300, 0)
    bus = EventBus()
    OrderSystem(game, bus)
    bus.publish(UseAbilityEvent(units=[carrier], ability_type_str=kind, target_unit=target, shift_pressed=False))
    assert get_instance(carrier, kind).is_active
    assert not carrier.engines_component.move_target


def test_testing_demonstration_designs_validate():
    from unit_templates import load_testing_templates
    from unit_template_validation import validate_library
    designs = load_testing_templates()
    selected = {key: {**designs[key], 'hull_size': designs[key]['hull_size'].name}
                for key in ('SPAWN_CARRIER', 'SPAWN_SHIP_HUGE')}
    assert validate_library(selected, is_builtin=True) == {}


def test_run_timeout_and_cooldowns_do_not_tick_on_other_players_turns():
    game, carrier, bomber, _, target, _ = scenario()
    assert issue(game, carrier, 'attack_run', target).accepted
    root = wing_order(bomber)
    inst = get_instance(carrier, 'attack_run')
    game.turn_number += 1
    start_owner_turn(game.galaxy, game.players[1], game.turn_number)
    assert inst.duration_remaining == 6 and inst.cooldown_remaining == 8
    for _ in range(5):
        next_round(game)
    assert root.status.name == 'FAILED' and root.failure_reason == 'ability_expired'
    assert bomber.engines_component.effective_speed == 40


def test_run_does_not_reset_unready_turrets():
    game, carrier, bomber, _, target, _ = scenario()
    target.position = Position(300, 0)
    turret = bomber.weapons_component.turrets[0]
    turret.current_cooldown = 5
    assert issue(game, carrier, 'attack_run', target).accepted
    next_round(game)
    before = target.current_hit_points
    bomber.weapons_component.update(game.galaxy)
    assert target.current_hit_points == before
    assert turret.current_cooldown == 4
    assert not wing_order(bomber)


def test_run_into_unreachable_magnetic_storm_fails_without_firing():
    from domain.celestials import Storm
    from constants import StormType
    game, carrier, bomber, _, target, _ = scenario()
    bomber.position = Position(0, 0)
    storm = Storm((0, 0), 'Sol', StormType.MAGNETIC)
    storm.position, storm.radius = target.position, 250
    game.galaxy.systems['Sol'].add_celestial_body(storm)
    before = target.current_hit_points
    assert issue(game, carrier, 'attack_run', target).accepted
    root = bomber.commander_component.current_order
    for _ in range(3):
        if root:
            root.update(game.galaxy)
        bomber.weapons_component.update(game.galaxy)
    assert root.status.name == 'FAILED'
    assert target.current_hit_points == before
    assert bomber.position == Position(0, 0)


def test_hidden_run_target_redacts_child_geometry():
    game, carrier, bomber, _, target, _ = scenario()
    target.position = Position(650, 0)
    assert issue(game, carrier, 'attack_run', target).accepted
    sector = game.galaxy.systems['Sol'].hexes[(0, 0)]
    sector.units.remove(target)
    target.in_system = 'Beta'
    game.galaxy.systems['Beta'].hexes[(0, 0)].units.append(target)
    from game_ai.order_view import order_layers
    own_ids = {u.id for u in sector.units if u.owner == carrier.owner}
    view = order_layers(bomber, 'self', own_ids, set())['current_order']
    assert view['target_id'] is None and view['parameters'] == {}
    for child in view['suborders']:
        assert child['target_id'] is None and child['parameters'] == {}


def test_evasion_guardian_and_sabotage_combine_without_base_mutation():
    from unit_components.defenses import Defenses
    game, carrier, bomber, _, target, _ = scenario()
    carrier.add_component(Defenses(carrier, armor=0, shields=0, point_defense=0))
    carrier.ability_component.abilities[AbilityType.GUARDIAN_LINK] = ABILITY_CLASSES[AbilityType.GUARDIAN_LINK]()
    assert issue(game, carrier, 'evasive_formation', bomber).accepted
    assert issue(game, carrier, 'guardian_link', bomber).accepted
    before_wing, before_carrier = bomber.current_hit_points, carrier.current_hit_points
    combat_hit(bomber, 20, TurretType.MASS_DRIVER)
    # Evasion leaves 10; Guardian redirects 3 and retains floor(3 * .75) = 2.
    assert bomber.current_hit_points == before_wing - 7
    assert carrier.current_hit_points == before_carrier - 2
    turret = bomber.weapons_component.turrets[0]
    initial = turret.damage, turret.range, turret.cooldown
    from unit_components.enums import SabotageType
    bomber.is_sabotaged = lambda kind: kind == SabotageType.WEAPONS
    turret.target = target
    before = target.current_hit_points
    turret.fire()
    assert target.current_hit_points == before - 1
    assert (turret.damage, turret.range, turret.cooldown) == initial


def test_legacy_wing_fields_initialize_in_existing_migration_chain():
    game, carrier, bomber, _, _, _ = scenario()
    state = serialize_game_state(game)
    state['version'] = '4.2'
    from save_migrations import raw_units
    for unit in raw_units(state):
        for comp in unit['components'].values():
            if comp['type'] == 'StrikecraftWingComponent':
                for field in ('recovery_ready_round', 'last_flak_round', 'last_flak_owner_id'):
                    comp['runtime'].pop(field)
    assert deserialize_game_state(game, state)
    restored = game.galaxy.get_unit_by_id(bomber.id).strikecraft_wing_component
    assert restored.recovery_ready_round == 0
    assert restored.last_flak_owner_id is None
