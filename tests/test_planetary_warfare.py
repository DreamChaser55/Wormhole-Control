"""Conquest economics, turn authority, disclosure and transactional persistence."""
import json
import random

import pytest

from constants import HullSize, PlanetType
from domain.celestials import Planet, Moon, ColonizableAsteroid
from geometry import Position
from game_ai.commands import CommandGateway
from game_ai.contracts import Command, CommandBatch, ContractError
from game_ai.observation import build_observation
from planetary_warfare import (
    maximum_defense, defense_view, assault_preview, process_actions, recover, upgrade,
)
from save_manager import serialize_game_state, deserialize_game_state
from tests.support.campaigns import campaign, ship
from unit_components.antimatter import AntimatterStorage
from unit_components.movement import Engines
from unit_components.planetary import TroopTransportComponent, SiegeBatteryComponent
from unit_orders.base import OrderStatus


def world(game, owner=0, cls=Planet, sector=(0, 0), population=50):
    body = cls(sector, 'Sol', PlanetType.TERRAN) if cls is Planet else cls(sector, 'Sol')
    body.owner = game.players[owner]
    body.population = population
    game.galaxy.systems['Sol'].add_celestial_body(body)
    return body


def vessel(game, body, *, siege=False, troops=0):
    unit = ship(game, hull=HullSize.MEDIUM, sector=body.in_hex)
    unit.position = Position(body.collision_radius + 150, 0)
    unit.in_galaxy = game.galaxy
    unit.add_component(Engines(unit, speed=100))
    unit.add_component(AntimatterStorage(unit, max_capacity=200))
    unit.antimatter_component.current_amount = 200
    unit.add_component(SiegeBatteryComponent(unit) if siege else TroopTransportComponent(unit))
    if not siege:
        unit.troop_transport_component.troops = troops
    return unit


def issue(game, *commands):
    return CommandGateway(game).apply_batch(game.players[0], CommandBatch(tuple(Command.from_dict(c) for c in commands)))


def action(unit, body, kind='invade_planet', amount=40, queue=False):
    return dict(type=kind, unit_ids=[unit.id], target_id=body.id, queue=queue,
                **({'amount': amount} if kind != 'bombard_planet' else {}))


def phase(game):
    for system in game.galaxy.systems.values():
        for unit, _ in system.get_all_units():
            if unit.owner == game.players[0]:
                unit.commander_component.update()
    process_actions(game, game.players[0])


@pytest.mark.parametrize('cls', [Planet, Moon, ColonizableAsteroid])
def test_defense_and_upgrade_track(cls):
    game = campaign()
    body = world(game, cls=cls, population=20)
    game.players[0].credits = 2000
    body.defense_readiness = .4
    for level, price in enumerate((250, 500, 750), 1):
        before = game.players[0].credits
        upgrade(game, game.players[0], body)
        assert body.fortification_level == level
        assert game.players[0].credits == before - price
        assert body.defense_readiness == .4
        assert maximum_defense(body) == 10 * (1 + .5 * level)
        with pytest.raises(ValueError):
            upgrade(game, game.players[0], body)
        game.turn_number += 1
    assert defense_view(body)['next_upgrade_cost'] is None


def test_recruitment_is_deferred_and_population_and_cargo_are_conserved():
    game = campaign()
    body = world(game)
    unit = vessel(game, body)
    game.players[0].credits = 100
    assert issue(game, action(unit, body, 'recruit_troops')).accepted
    for _ in range(3):
        unit.commander_component.update()
    assert (body.population, unit.troop_transport_component.troops, game.players[0].credits) == (50, 0, 100)
    phase(game)
    assert (body.population, unit.troop_transport_component.troops, game.players[0].credits) == (42, 40, 20)
    phase(game)
    assert unit.troop_transport_component.troops == 40


@pytest.mark.parametrize('seed,success,remaining', [(1, True, 30), (2, False, 10)])
def test_single_roll_losses_and_capture(seed, success, remaining):
    game = campaign()
    body = world(game, owner=1)
    body.fortification_level = 1
    unit = vessel(game, body, troops=40)
    game.invasion_rng = random.Random(seed)
    assert issue(game, action(unit, body)).accepted
    order = unit.commander_component.current_order
    rng_before = game.invasion_rng.getstate()
    assert assault_preview(body, 40)['success_probability'] == pytest.approx(40/77.5)
    assert game.invasion_rng.getstate() == rng_before
    phase(game)
    assert unit.troop_transport_component.troops == remaining
    assert unit.antimatter_component.current_amount == 180
    assert body.owner == game.players[0 if success else 1]
    assert body.population == 50
    assert order.status == (OrderStatus.COMPLETED if success else OrderStatus.FAILED)
    if success:
        assert body.fortification_level == 0 and body.defense_readiness == .25
    else:
        assert body.defense_readiness == 1
        assert order.failure_reason == 'assault_repulsed'
    state = game.invasion_rng.getstate()
    phase(game)
    assert game.invasion_rng.getstate() == state


def test_bombardment_floor_collateral_and_quiet_recovery():
    game = campaign()
    body = world(game, owner=1)
    unit = vessel(game, body, siege=True)
    assert issue(game, action(unit, body, 'bombard_planet')).accepted
    phase(game)
    assert body.defense_readiness == pytest.approx(.6)
    assert body.population == pytest.approx(49.8)
    phase(game)
    assert body.population == pytest.approx(49.8)
    recover(game)
    assert body.defense_readiness == pytest.approx(.6)
    game.turn_number += 1
    phase(game)
    assert body.defense_readiness == .25
    assert unit.commander_component.current_order.status == OrderStatus.COMPLETED
    assert unit.antimatter_component.current_amount == 180
    recover(game)
    assert body.defense_readiness == .25
    game.turn_number += 1
    recover(game)
    assert body.defense_readiness == .35


def test_bombardment_precedes_assault_regardless_of_unit_id():
    game = campaign()
    body = world(game, owner=1)
    transport = vessel(game, body, troops=40)
    siege = vessel(game, body, siege=True)
    # 0.677: fails against 25 defense, wins after a ten-point siege volley.
    game.invasion_rng = random.Random(19)
    assert issue(game, action(transport, body), action(siege, body, 'bombard_planet')).accepted
    phase(game)
    assert body.owner == game.players[0]
    assert body.population < 50


def test_cancellation_and_invalid_execution_have_no_cost_or_randomness():
    game = campaign()
    body = world(game, owner=1)
    unit = vessel(game, body, troops=40)
    game.invasion_rng = random.Random(1)
    before = game.invasion_rng.getstate()
    assert issue(game, action(unit, body)).accepted
    unit.commander_component.clear_explicit_orders()
    phase(game)
    assert unit.antimatter_component.current_amount == 200
    assert issue(game, action(unit, body)).accepted
    unit.antimatter_component.current_amount = 0
    phase(game)
    assert unit.troop_transport_component.troops == 40
    assert game.invasion_rng.getstate() == before


def test_preflight_recruitment_reservations_and_replacement():
    game = campaign()
    home = world(game, population=9)
    enemy = world(game, owner=1, sector=(1, 0))
    first, second = vessel(game, home), vessel(game, home)
    game.players[0].credits = 1000
    before = serialize_game_state(game)
    result = issue(game, action(first, home, 'recruit_troops', 40), action(second, home, 'recruit_troops', 1))
    assert not result.accepted
    assert home.population == 9 and first.commander_component.current_order is None
    assert serialize_game_state(game)['game_state']['invasion_rng_state'] == before['game_state']['invasion_rng_state']
    result = issue(game, action(first, home, 'recruit_troops', 40), action(first, enemy, amount=40, queue=True))
    assert result.accepted, result.errors
    # Replacing the recruitment cannot continue to finance an invasion.
    result = issue(game, action(first, enemy, amount=40))
    assert not result.accepted
    assert first.commander_component.current_order.order_type.name == 'RECRUIT_TROOPS'


@pytest.mark.parametrize('amount', [True, 1.5, '3', 0, -1])
def test_troop_counts_are_strict_integers(amount):
    with pytest.raises(ContractError):
        Command.from_dict(dict(type='invade_planet', unit_ids=[0], target_id=0, amount=amount))


def test_upgrade_batch_is_atomic_and_does_not_overdraw():
    game = campaign()
    body = world(game)
    game.players[0].credits = 400
    command = dict(type='upgrade_planetary_defenses', unit_ids=[], target_id=body.id)
    result = issue(game, command, command)
    assert not result.accepted
    assert body.fortification_level == 0 and game.players[0].credits == 400
    assert issue(game, command).accepted
    assert game.players[0].credits == 150


def test_save_roundtrip_preserves_roll_and_active_orders_without_replay():
    game = campaign()
    body = world(game, owner=1)
    unit = vessel(game, body, troops=40)
    game.invasion_rng = random.Random(1)
    assert issue(game, action(unit, body)).accepted
    saved = json.loads(json.dumps(serialize_game_state(game)))
    restored = campaign()
    assert deserialize_game_state(restored, saved)
    restored_unit = restored.galaxy.get_unit_by_id(unit.id)
    assert restored_unit.troop_transport_component.troops == 40
    assert restored_unit.antimatter_component.current_amount == 200
    phase(game)
    phase(restored)
    assert restored_unit.troop_transport_component.troops == unit.troop_transport_component.troops
    assert restored.galaxy.get_celestial_body_by_id(body.id).owner.id == body.owner.id
    assert restored.invasion_rng.getstate() == game.invasion_rng.getstate()
    second = json.loads(json.dumps(serialize_game_state(restored)))
    assert deserialize_game_state(restored, second)
    phase(restored)
    assert restored.galaxy.get_unit_by_id(unit.id).troop_transport_component.troops == 30


@pytest.mark.parametrize('field,value', [('defense_readiness', .24), ('fortification_level', 4), ('last_hostile_action_round', 99)])
def test_corrupt_planetary_state_rejects_transactionally(field, value):
    game = campaign()
    body = world(game)
    data = serialize_game_state(game)
    raw = data['galaxy']['systems'][0]['hexes'][0]['celestial_bodies'][0]
    raw[field] = value
    original = game.galaxy
    assert not deserialize_game_state(game, data)
    assert game.galaxy is original and body.population == 50


def test_observation_does_not_disclose_enemy_troops_and_shares_defenses():
    game = campaign()
    body = world(game, owner=1)
    unit = vessel(game, body, troops=37)
    own = build_observation(game, game.players[0])
    assert next(u for u in own['units'] if u['id'] == unit.id)['troop_cargo']['current'] == 37
    enemy_view = build_observation(game, game.players[1])
    for entry in enemy_view['units']:
        if entry['id'] == unit.id:
            assert 'troop_cargo' not in entry
    body_view = next(s for s in own['systems'] if s['name'] == 'Sol')['celestial_bodies'][0]
    assert body_view['planetary_defenses']['current_defense'] == 25


def test_destroyed_cargo_cannot_be_repaired_into_new_troops():
    game = campaign()
    body = world(game)
    unit = vessel(game, body, troops=40)
    unit.take_component_damage(TroopTransportComponent, unit.troop_transport_component.current_hit_points)
    assert unit.troop_transport_component.troops == 0
    unit.heal_components(1000)
    assert unit.troop_transport_component.troops == 0


def test_target_zero_and_empty_colony_guaranteed_capture_without_roll():
    game = campaign()
    body = world(game, owner=1, population=0)
    system = game.galaxy.systems['Sol']
    system.celestial_bodies_by_id.pop(body.id)
    body.id = 0
    system.celestial_bodies_by_id[0] = body
    unit = vessel(game, body, troops=1)
    game.invasion_rng = random.Random(2)
    rng = game.invasion_rng.getstate()
    assert issue(game, action(unit, body, amount=1)).accepted
    phase(game)
    assert body.owner == unit.owner
    assert game.invasion_rng.getstate() == rng


@pytest.mark.parametrize('population', [0, .5, 1])
def test_collateral_never_increases_small_population(population):
    game = campaign()
    body = world(game, owner=1, population=population)
    unit = vessel(game, body, siege=True)
    assert issue(game, action(unit, body, 'bombard_planet')).accepted
    phase(game)
    assert body.population == population and body.owner == game.players[1]


@pytest.mark.parametrize('amount,win_loss,lose_loss', [(1, 1, 1), (3, 1, 3), (5, 2, 4), (40, 10, 30)])
def test_preview_casualty_rounding(amount, win_loss, lose_loss):
    game = campaign()
    body = world(game, owner=1)
    preview = assault_preview(body, amount)
    assert preview['success_casualties'] == win_loss
    assert preview['defeat_casualties'] == lose_loss
    assert 0 < preview['success_probability'] < 1


def test_queued_followup_and_replacement_cannot_repeat_this_round():
    game = campaign()
    body = world(game, population=50)
    unit = vessel(game, body)
    assert issue(game, action(unit, body, 'recruit_troops', 10),
                 action(unit, body, 'recruit_troops', 10, queue=True)).accepted
    phase(game)
    assert unit.troop_transport_component.troops == 10
    phase(game)
    assert unit.troop_transport_component.troops == 10
    assert issue(game, action(unit, body, 'recruit_troops', 5)).accepted
    phase(game)
    assert unit.troop_transport_component.troops == 10
    game.turn_number += 1
    phase(game)
    assert unit.troop_transport_component.troops == 15


@pytest.mark.parametrize('failure', ['equipment', 'destroyed', 'disabled', 'hidden', 'ownership', 'visibility'])
def test_execution_revalidates_without_cost_or_roll(failure, monkeypatch):
    game = campaign()
    body = world(game, owner=1)
    unit = vessel(game, body, troops=40)
    game.invasion_rng = random.Random(1)
    before = game.invasion_rng.getstate()
    assert issue(game, action(unit, body)).accepted
    if failure == 'equipment':
        unit.troop_transport_component.current_hit_points = 0
    elif failure == 'destroyed':
        unit.current_hit_points = 0
    elif failure == 'disabled':
        unit.is_disabled = True
    elif failure == 'hidden':
        unit.is_hidden_in_gas_giant = True
    elif failure == 'ownership':
        body.owner = unit.owner
    else:
        monkeypatch.setattr('game_ai.rules.body_is_public', lambda *args: False)
    phase(game)
    assert unit.antimatter_component.current_amount == 200
    assert unit.troop_transport_component.troops == 40
    assert game.invasion_rng.getstate() == before


def test_later_invasion_revalidates_capture_and_records_one_outcome():
    game = campaign()
    body = world(game, owner=1)
    first, second = vessel(game, body, troops=40), vessel(game, body, troops=40)
    game.invasion_rng = random.Random(1)
    assert issue(game, action(second, body), action(first, body)).accepted
    first_order = first.commander_component.current_order
    second_order = second.commander_component.current_order
    phase(game)
    assert body.owner == first.owner and second.troop_transport_component.troops == 40
    assert second.antimatter_component.current_amount == 200
    assert second_order.status == OrderStatus.FAILED
    expected = random.Random(1)
    expected.random()
    assert game.invasion_rng.getstate() == expected.getstate()
    phase(game)
    history = game.players[0].order_history
    assert sum(e['order_id'] == first_order.public_id for e in history) == 1
    assert sum(e['order_id'] == second_order.public_id for e in history) == 1


def test_capture_refreshes_support_income_espionage_and_private_briefings():
    from domain.players import Player
    from economy import calculate_player_income
    from planetary_warfare import capture
    from unit_components.civilian_habitat import CivilianHabitatComponent
    from unit_components.orbital_defense import OrbitalDefenseComponent
    from unit_components.intelligence import Agent
    from unit_components.enums import SabotageType
    from turn_briefing import begin_window
    game = campaign()
    ally = Player('Ally', (100, 100, 0), team_id=game.players[0].team_id)
    outsider = Player('Outsider', (0, 100, 100))
    game.players.extend([ally, outsider])
    body = world(game, owner=1)
    units = [ship(game, owner=index) for index in range(3)]
    for unit in units:
        unit.add_component(CivilianHabitatComponent(unit))
        unit.add_component(OrbitalDefenseComponent(unit))
    agents = [Agent(p, units[0].id, 'CELESTIAL_BODY', body.id,
                    active_sabotage=SabotageType.ECONOMY, is_discovered=True) for p in (ally, outsider)]
    body.infiltrating_agents.extend(agents)
    for player in game.players:
        begin_window(game, player)
    treasury = [p.credits for p in game.players]
    previous_income = calculate_player_income(game.galaxy, game.players[0])
    assert units[1].civilian_habitat_component.is_active()
    capture(game, body, game.players[0])
    assert calculate_player_income(game.galaxy, game.players[0]) > previous_income
    assert units[0].civilian_habitat_component.is_active()
    assert not units[1].civilian_habitat_component.is_active()
    assert units[2].orbital_defense_component.is_active()
    assert not units[1].orbital_defense_component.is_active()
    assert [u.owner for u in units] == game.players[:3]
    assert [p.credits for p in game.players] == treasury
    assert agents[0].active_sabotage is None
    assert agents[1].active_sabotage == SabotageType.ECONOMY
    assert all(a.is_discovered for a in agents) and body.infiltrating_agents == agents
    assert game.visibility_dirty and game.sidebar_needs_update
    assert any(e.detail == 'Colony lost' for e in game.players[1].briefing.pending)
    assert any(e.detail == 'Colony captured' for e in ally.briefing.pending)
    assert not outsider.briefing.pending


@pytest.mark.parametrize('players', [2, 5])
def test_recovery_runs_once_at_global_round_end(players):
    from domain.players import Player
    from turn_processor import TurnProcessor
    game = campaign()
    for i in range(2, players):
        game.players.append(Player(str(i), (0, i * 30, 0)))
    body = world(game)
    body.defense_readiness = .4
    processor = TurnProcessor(game)
    for i in range(players):
        processor.end_turn()
        assert body.defense_readiness == pytest.approx(.5 if i == players - 1 else .4)


def test_save_during_approach_and_active_bombardment():
    from turn_processor import TurnProcessor
    game = campaign()
    body = world(game, owner=1, population=200)
    siege = vessel(game, body, siege=True)
    siege.position = Position(body.collision_radius + 1100, 0)
    assert issue(game, action(siege, body, 'bombard_planet')).accepted
    assert siege.commander_component.current_order.has_active_sub_orders()
    saved = json.loads(json.dumps(serialize_game_state(game)))
    assert deserialize_game_state(game, saved)
    processor = TurnProcessor(game)
    for _ in range(5):
        processor.end_turn()
        if game.galaxy.get_celestial_body_by_id(body.id).defense_readiness < 1:
            break
    body = game.galaxy.get_celestial_body_by_id(body.id)
    siege = game.galaxy.get_unit_by_id(siege.id)
    assert .25 < body.defense_readiness < 1
    cargo_fuel = siege.antimatter_component.current_amount
    readiness = body.defense_readiness
    saved = json.loads(json.dumps(serialize_game_state(game)))
    assert deserialize_game_state(game, saved)
    process_actions(game, game.players[0])
    assert game.galaxy.get_unit_by_id(siege.id).antimatter_component.current_amount == cargo_fuel
    assert game.galaxy.get_celestial_body_by_id(body.id).defense_readiness == readiness


@pytest.mark.parametrize('state', [None, [], {'$tuple': [3, [], None]}])
def test_malformed_invasion_rng_rejects_without_mutating_game(state):
    game = campaign()
    saved = serialize_game_state(game)
    saved['game_state']['invasion_rng_state'] = state
    original = game.galaxy
    assert not deserialize_game_state(game, saved)
    assert game.galaxy is original


def test_occupied_transport_refit_preserves_cargo_and_installed_cost():
    from refit_validation import evaluate_refit
    from economy import calculate_unit_upkeep
    game = campaign()
    body = world(game)
    unit = vessel(game, body, troops=40)
    before = calculate_unit_upkeep(unit.hull_size, unit.current_hull_usage)
    assert evaluate_refit(unit, 'REMOVE', 'TroopTransportComponent').errors
    unit.troop_transport_component.troops = 1
    assert calculate_unit_upkeep(unit.hull_size, unit.current_hull_usage) == before
    assert evaluate_refit(unit, 'REMOVE', 'TroopTransportComponent').errors
    unit.troop_transport_component.troops = 0
    assert not evaluate_refit(unit, 'REMOVE', 'TroopTransportComponent').errors


def test_fortification_sidebar_uses_same_gateway_rules():
    from gui.sidebar.panels_world import build_celestial_body_panel
    from gui.dynamic_actions import build_button_payload
    from game_actions.unit_actions import handle_planetary_upgrade
    game = campaign()
    body = world(game)
    def upgrade_button():
        return next(row for row in build_celestial_body_panel(game, body)
                    if row.get('action_id') == 'upgrade_planetary_defenses')
    row = upgrade_button()
    assert row['enabled']
    before = game.players[0].credits
    payload = build_button_payload(None, row['action_id'], row['target_data'])
    handle_planetary_upgrade(game, payload)
    assert body.fortification_level == 1 and game.players[0].credits == before - 250
    assert not upgrade_button()['enabled']


@pytest.mark.parametrize('key', ['has_troop_transport_component', 'has_siege_battery_component'])
def test_equipment_design_and_retrofit_controls(key, pygame_context, tmp_path):
    import pygame
    from display_config import DisplayConfig
    from custom_unit_templates import CustomTemplateManager, CustomUnitTemplate
    from gui.unit_editor_gui import UnitEditorWindow
    from gui.retrofit_gui.wizard import RetrofitWizardWindow
    from gui.theme_loader import build_ui_manager
    config = DisplayConfig(1280, 720, False)
    manager = build_ui_manager(config)
    library = CustomTemplateManager(data_file=str(tmp_path / 'designs.json'))
    design = CustomUnitTemplate('Conquest test design', HullSize.MEDIUM)
    design.components.has_engine = True
    design.components.engine_speed = 100
    design.components.has_antimatter_storage = True
    design.components.antimatter_capacity = 100
    setattr(design.components, key, True)
    editor = UnitEditorWindow(manager, config, library)
    try:
        editor.show()
        editor._comp = design.components
        editor._select_component(key)
        if key == 'has_troop_transport_component':
            from gui.unit_editor_gui.param_readers import read_troop_params
            editor._troop_capacity_entry.set_text('35')
            read_troop_params(editor)
            assert editor._comp.troop_capacity == 35
        assert library.save_design(design) == []
        editor.hide()
        game = campaign()
        unit = ship(game, hull=HullSize.MEDIUM)
        unit.add_component(Engines(unit, speed=100))
        unit.add_component(AntimatterStorage(unit, max_capacity=100))
        component = 'TroopTransportComponent' if key == 'has_troop_transport_component' else 'SiegeBatteryComponent'
        wizard = RetrofitWizardWindow(manager, pygame.Vector2(1280, 720), unit, [], component)
        if key == 'has_troop_transport_component':
            wizard._troop_capacity_entry.set_text('35')
            wizard._sync_cost_and_summary()
            assert wizard.calculated_hull_cost == 17.5
        else:
            assert wizard.calculated_hull_cost == 20
        assert wizard.is_valid
    finally:
        manager.clear_and_reset()


def test_unavailable_planet_ids_and_blocked_approach_preserve_cargo():
    from turn_processor import TurnProcessor
    game = campaign()
    target = world(game, owner=1, sector=(1, 0))
    unit = vessel(game, target, troops=40)
    result = issue(game, dict(action(unit, target), target_id=999999))
    assert not result.accepted and result.errors[0].code == 'target_unavailable'
    target.in_system = 'Beta'
    game.galaxy.systems['Sol'].hexes[(1, 0)].celestial_bodies.remove(target)
    game.galaxy.systems['Sol'].celestial_bodies_by_id.pop(target.id)
    game.galaxy.systems['Beta'].add_celestial_body(target)
    game.invasion_rng = random.Random(1)
    before = game.invasion_rng.getstate()
    result = issue(game, action(unit, target))
    # Remote colonies are exact, but the disconnected system cannot be approached.
    if result.accepted:
        TurnProcessor(game).end_turn()
    assert unit.troop_transport_component.troops == 40
    assert unit.antimatter_component.current_amount == 200
    assert game.invasion_rng.getstate() == before


@pytest.mark.parametrize('human', [False, True])
def test_offline_conquest_loop_through_provider_or_human_controls(human, pygame_context, tmp_path, monkeypatch):
    import pygame
    import pygame_gui
    from types import SimpleNamespace
    from display_config import DisplayConfig
    from game_ai.adapters.fake import FakePlanningProvider
    from game_ai.adapters.base import PlanningRequest
    from game_ai.contracts import TurnPlan
    from game_ai.runtime import get_runtime_config
    from gui.theme_loader import build_ui_manager
    from tests.support.ai import EMPTY_PATCH
    from turn_processor import TurnProcessor
    from unit_components.constructor import instantiate_unit_from_template
    game = campaign()
    home = world(game)
    target = world(game, owner=1, population=20)
    target.position = Position(2 * (home.collision_radius + 150), 0)
    location = Position(home.collision_radius + 150, 0)
    transport, siege = [instantiate_unit_from_template(key, game.players[0], 'Sol', (0, 0),
                        location, game.galaxy, game) for key in ('TROOP_TRANSPORT', 'SIEGE_FRIGATE')]
    assert transport.current_hull_usage == siege.current_hull_usage == 48
    assert transport.troop_transport_component.troops == 0
    game.invasion_rng = random.Random(1)
    processor = TurnProcessor(game)
    config = DisplayConfig(1280, 720, False)
    game.gui = SimpleNamespace(game_instance=game, display_config=config, manager=build_ui_manager(config),
                               planetary_window=None, context_menu_panel=None)
    def submit(unit, body, kind, queue=False):
        if human and kind != 'bombard_planet':
            from input_processor.context_actions import handle_context_menu_action
            from gui.event_router import process_event
            game.selected_objects = [unit]
            monkeypatch.setattr('pygame.key.get_mods', lambda: pygame.KMOD_SHIFT if queue else 0)
            handle_context_menu_action(game, kind, body)
            dialog = game.gui.planetary_window
            assert dialog.queue == queue
            assert dialog.amount.get_text() == '40'
            screen = pygame.Surface((1280, 720))
            game.gui.manager.update(.1)
            game.gui.manager.draw_ui(screen)
            pygame.image.save(screen, str(tmp_path / f'{kind}.png'))
            for control in (dialog.submit, dialog.append, dialog.cancel, dialog.amount, dialog.preview):
                assert dialog.window.get_abs_rect().contains(control.get_abs_rect())
            process_event(game.gui, pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, ui_element=dialog.submit))
            assert game.gui.planetary_window is None
        elif human:
            from input_processor.context_actions import handle_context_menu_action
            game.selected_objects = [unit]
            handle_context_menu_action(game, kind, body)
        else:
            plan = TurnPlan.from_dict(dict(plan=[], commands=[action(unit, body, kind, queue=queue)],
                                           memory_patch=EMPTY_PATCH, end_turn=True))
            provider = FakePlanningProvider([plan])
            output = provider.plan_turn(PlanningRequest('test', 'agent', 'One', game.turn_number,
                                                       build_observation(game, unit.owner), {}), get_runtime_config('low'))
            result = CommandGateway(game).apply_batch(unit.owner, output.plan.batch)
            assert result.accepted, result.errors
    try:
        submit(transport, home, 'recruit_troops')
        processor.end_turn()
        assert transport.troop_transport_component.troops == 40
        processor.end_turn()
        submit(siege, target, 'bombard_planet')
        submit(transport, target, 'invade_planet', queue=True)
        processor.end_turn()
        assert target.owner == transport.owner
        assert target.defense_readiness == .25 and transport.troop_transport_component.troops == 30
        saved = json.loads(json.dumps(serialize_game_state(game)))
        assert deserialize_game_state(game, saved)
        assert game.galaxy.get_celestial_body_by_id(target.id).owner == game.players[0]
        assert game.galaxy.get_unit_by_id(transport.id).troop_transport_component.troops == 30
    finally:
        game.gui.manager.clear_and_reset()
