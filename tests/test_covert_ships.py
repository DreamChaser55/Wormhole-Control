"""Covert construction, enemy inspection and shared unit naming behavior."""
import copy
import json
from concurrent.futures import Future
from types import SimpleNamespace

import pytest

from domain.players import Player
from game_actions.unit_actions import handle_rename_unit
from game_ai.adapters.fake import FakePlanningProvider
from game_ai.contracts import Command, CommandBatch, ContractError, TurnPlan
from game_ai.coordinator import AgentTurnCoordinator
from game_ai.observation import build_observation
from game_control_protocol import ControlService, PROTOCOL_VERSION
from geometry import Position
from gui.sidebar.panels_unit import build_unit_panel
from player_controller import PlayerController
from save_manager import serialize_game_state, deserialize_game_state
from tests.support.ai import EMPTY_PATCH
from tests.support.campaigns import campaign
from tests.support.commands import issue
from turn_processor import TurnProcessor
from unit_catalog import describe_template, validate_builtin_catalog
from unit_components.constructor import instantiate_unit_from_template
from unit_naming import rename_unit
from unit_orders.base import Order, OrderType, OrderStatus
from unit_templates import UNIT_TEMPLATES


def create(game, key, owner=0, position=(100, 100)):
    return instantiate_unit_from_template(key, game.players[owner], 'Sol', (0, 0),
                                          Position(*position), game.galaxy, game)


@pytest.fixture
def covert_world():
    game = campaign()
    game.sidebar_needs_update = game.visibility_dirty = False
    game.gui = SimpleNamespace(is_section_expanded=lambda key: True)
    game._generate_order_data_recursive = lambda order, indent: order.order_type.name
    ordinary = create(game, 'PATROL_ESCORT')
    covert = create(game, 'COVERT_INTELLIGENCE_SHIP')
    observer = create(game, 'PATROL_ESCORT', owner=1, position=(200, 100))
    return game, ordinary, covert, observer


def panel(game, unit, viewer=1, component=None):
    game.current_player_index = viewer
    game.selected_unit_tab = 'components' if component else 'basic_info'
    game.selected_component_name = component
    return build_unit_panel(game, unit)


def unit_view(game, viewer, unit):
    return next(v for v in build_observation(game, game.players[viewer])['units'] if v['id'] == unit.id)


def test_twins_equipment_catalog_and_intelligence_operations(covert_world):
    game, ordinary, covert, observer = covert_world
    assert ordinary.name == covert.name == 'Patrol Escort'
    assert covert.template_name == 'Covert Intelligence Ship'
    assert ordinary.current_hull_usage == 33 and covert.current_hull_usage == 48
    ordinary_components = {type(c).__name__: c.to_state() for c in ordinary.components.values()}
    covert_components = {type(c).__name__: c.to_state() for c in covert.components.values()
                         if c is not covert.intelligence_component}
    # Commander root UUIDs are identities, not different equipment.
    ordinary_components.pop('Commander')
    covert_components.pop('Commander')
    assert ordinary_components == covert_components
    assert covert.intelligence_component.available_agents == 2
    assert not covert.intelligence_component.has_counter_intelligence
    assert ordinary.cloaking_component is covert.cloaking_component is None
    for key, cost, turns in [('PATROL_ESCORT', 1490, 17), ('COVERT_INTELLIGENCE_SHIP', 1940, 20)]:
        entry = describe_template(key, UNIT_TEMPLATES[key])
        assert entry['default_unit_name'] == 'Patrol Escort'
        assert (entry['credit_cost'], entry['turns']) == (cost, turns)
    assert issue(game, covert.owner, Command('infiltrate_unit', (covert.id,), target_id=observer.id)).accepted
    assert observer.has_infiltrating_agent_from(covert.owner)
    assert covert.intelligence_component.available_agents == 1


@pytest.mark.parametrize('renamed', [False, True])
@pytest.mark.parametrize('damaged', [False, True])
def test_enemy_twins_indistinguishable_with_private_orders(covert_world, renamed, damaged):
    game, ordinary, covert, observer = covert_world
    if renamed:
        rename_unit(ordinary, 'Vanguard')
        rename_unit(covert, 'Vanguard')
    if damaged:
        covert.intelligence_component.current_hit_points = 0
    active = Order(covert, OrderType.INFILTRATE_UNIT, {'target_id': 12345})
    active.status = OrderStatus.IN_PROGRESS
    active.add_sub_order(Order(covert, OrderType.MOVE, {'destination_position': Position(444, 555)}))
    covert.commander_component.current_order = active
    covert.commander_component.orders_queue.append(Order(covert, OrderType.EXTRACT_AGENT, {'agent_id': 98765}))
    covert.weapons_component.turrets[0].target = observer
    for component in (None, 'Commander', 'Weapons', 'Defenses', 'Intelligence'):
        left = panel(game, ordinary, component=component)
        right = panel(game, covert, component=component)
        assert left == right
        text = json.dumps(right)
        assert 'Template:' not in text and 'Upkeep:' not in text
        assert 'Intelligence' not in text and 'INFILTRATE' not in text and '98765' not in text
    ordinary_view = unit_view(game, 1, ordinary)
    covert_view = unit_view(game, 1, covert)
    ordinary_view.pop('id')
    covert_view.pop('id')
    assert ordinary_view == covert_view
    assert not {'standing_order', 'current_order', 'queued_orders'} & covert_view.keys()
    observer_view = unit_view(game, 1, observer)
    targets = observer_view['command_options']['attack']['target_components']
    assert targets[str(ordinary.id)] == targets[str(covert.id)]
    errors = [issue(game, game.players[1], Command('attack', (observer_view['id'],),
              target_id=covert.id, target_component=component)).errors
              for component in ('IntelligenceComponent', 'NonexistentComponent')]
    assert errors[0] == errors[1]


def test_component_inspectors_do_not_bypass_target_privacy(covert_world):
    from domain.celestials import MetalAsteroid
    game, _, covert, _ = covert_world
    repairer = create(game, 'FLEET_REPAIR_SHIP')
    miner = create(game, 'EXPEDITION_MINER')
    body = MetalAsteroid((0, 0), 'Sol')
    body.name = 'Private asteroid destination'
    covert.name = 'Private repair destination'
    game.players.append(Player('Ally', (0, 0, 200), team_id=covert.owner.team_id))
    for unit, component, field, target in (
        (repairer, repairer.repair_component, 'target', covert),
        (miner, miner.mining_component, 'mining_target', body),
    ):
        for tab in (None, component.DISPLAY_NAME):
            setattr(component, field, None)
            idle = panel(game, unit, 1, tab)
            setattr(component, field, target)
            assert panel(game, unit, 1, tab) == idle
        for viewer in (0, 2):
            assert target.name in json.dumps(panel(game, unit, viewer, component.DISPLAY_NAME))


@pytest.mark.parametrize('viewer', [0, 2])
def test_owners_and_allies_keep_design_and_order_details(covert_world, viewer):
    game, _, covert, _ = covert_world
    game.players.append(Player('Ally', (0, 0, 200), team_id=covert.owner.team_id))
    covert.commander_component.current_order = Order(covert, OrderType.INFILTRATE_UNIT)
    text = json.dumps(panel(game, covert, viewer))
    assert 'Template: Covert Intelligence Ship' in text
    assert '48/50' in text and 'Upkeep:' in text and 'Infiltrate Unit' in text
    assert 'INFILTRATE_UNIT' in json.dumps(panel(game, covert, viewer, 'Commander'))
    assert 'Intelligence' in json.dumps(panel(game, covert, viewer, 'Intelligence'))
    view = unit_view(game, viewer, covert)
    assert view['current_order']['type'] == 'infiltrate_unit'
    assert 'IntelligenceComponent' in view['components']


@pytest.mark.parametrize('job', ['construction', 'refit'])
def test_enemy_constructor_activity_is_private(covert_world, job):
    game, _, covert, _ = covert_world
    builder = create(game, 'CONSTRUCTOR_MK1')
    constructor = builder.constructor_component
    game.players.append(Player('Ally', (0, 0, 200), team_id=builder.owner.team_id))
    if job == 'construction':
        assert issue(game, builder.owner, Command('construct', (builder.id,),
                     template_name='COVERT_INTELLIGENCE_SHIP', position=(300, 100))).accepted
    else:
        assert constructor.start_refit(covert, 'REMOVE', 'IntelligenceComponent')
    for component in (None, 'Constructor'):
        text = json.dumps(panel(game, builder, 1, component))
        assert 'COVERT_INTELLIGENCE_SHIP' not in text and 'IntelligenceComponent' not in text
        assert 'progress_bar' not in text and 'Refitting' not in text and 'Constructing' not in text
        for viewer in (0, 2):
            friendly = json.dumps(panel(game, builder, viewer, component))
            assert ('Constructing' if job == 'construction' else 'Refitting') in friendly


def test_construction_enters_enemy_turn_with_cover_name(covert_world):
    game, _, _, observer = covert_world
    builder = create(game, 'CONSTRUCTOR_MK1')
    assert issue(game, builder.owner, Command('construct', (builder.id,),
                 template_name='COVERT_INTELLIGENCE_SHIP', position=(300, 100))).accepted
    before = {u.id for u in game.galaxy.systems['Sol'].hexes[(0, 0)].units}
    constructor = builder.constructor_component
    constructor.construction_progress = constructor.time_to_build - 1
    TurnProcessor(game).end_turn()
    assert game.players[game.current_player_index] is observer.owner
    built = next(u for u in game.galaxy.systems['Sol'].hexes[(0, 0)].units if u.id not in before)
    assert built.intelligence_component.available_agents == 2
    assert built.name == unit_view(game, 1, built)['name'] == 'Patrol Escort'
    assert 'Covert' not in json.dumps(panel(game, built))


@pytest.mark.parametrize('name', ['A', 'x' * 30, '  Étoile  ', 'Patrol Escort'])
def test_human_and_gateway_renaming_preserve_unit_state(covert_world, name):
    game, ordinary, covert, observer = covert_world
    assert issue(game, covert.owner, Command('infiltrate_unit', (covert.id,), target_id=observer.id)).accepted
    assert issue(game, covert.owner, Command('move', (covert.id,), system_name='Sol',
                 hex_coord=(0, 0), position=(800, 100))).accepted
    commander = covert.commander_component
    current, stance = commander.current_order, commander.stance
    credits, fuel = covert.owner.credits, covert.antimatter_component.current_amount
    agent = covert.intelligence_component.deployed_agents[0]
    game.selected_objects = [ordinary]
    handle_rename_unit(game, {'new_name': name})
    result = issue(game, covert.owner, Command('rename_unit', (covert.id,), new_name=name))
    assert result.accepted and result.applied_count == 1
    assert ordinary.name == covert.name == name.strip()
    assert game.sidebar_needs_update and result.receipts
    assert commander.current_order is current and commander.stance is stance
    assert (covert.owner.credits, covert.antimatter_component.current_amount) == (credits, fuel)
    assert covert.intelligence_component.deployed_agents[0] is agent
    assert covert.template_name == 'Covert Intelligence Ship'
    restored = campaign()
    assert deserialize_game_state(restored, serialize_game_state(game))
    saved = restored.galaxy.get_unit_by_id(covert.id)
    assert saved.name == name.strip() and saved.template_name == covert.template_name
    assert saved.commander_component.current_order.public_id == current.public_id
    assert saved.intelligence_component.deployed_agents[0].id == agent.id


@pytest.mark.parametrize('name', [None, 12, '', '   ', 'x' * 31, 'a\nb', '\tEscort', 'Escort\x7f'])
def test_invalid_names_reject_human_command_and_default_metadata(covert_world, name):
    game, ordinary, covert, _ = covert_world
    game.selected_objects = [ordinary]
    handle_rename_unit(game, {'new_name': name})
    assert ordinary.name == 'Patrol Escort'
    result = issue(game, covert.owner, Command('rename_unit', (covert.id,), new_name=name))
    assert not result.accepted and covert.name == 'Patrol Escort'
    raw = copy.deepcopy(UNIT_TEMPLATES['COVERT_INTELLIGENCE_SHIP'])
    raw['hull_size'] = raw['hull_size'].name
    raw['default_unit_name'] = name
    assert any('default_unit_name' in error for error in validate_builtin_catalog({'COVERT': raw})['COVERT'])


def test_rename_contract_ownership_atomicity_and_hidden_guidance(covert_world):
    game, ordinary, covert, observer = covert_world
    raw = {'type': 'rename_unit', 'unit_ids': [covert.id], 'new_name': 'Escort 7', 'queue': False}
    command = Command.from_dict(raw)
    assert Command.from_dict(command.to_dict()) == command
    for invalid in ({'unit_ids': []}, {'unit_ids': [ordinary.id, covert.id]}, {'queue': True}, {'amount': 1}):
        with pytest.raises(ContractError):
            Command.from_dict({**raw, **invalid})
    for uid in (observer.id, 999999):
        result = issue(game, covert.owner, command, Command('rename_unit', (uid,), new_name='Bad'))
        assert not result.accepted and result.errors[0].code == 'unit_unavailable'
        assert covert.name == 'Patrol Escort'
    ally = Player('Ally', (0, 0, 200), team_id=covert.owner.team_id)
    game.players.append(ally)
    allied_unit = create(game, 'PATROL_ESCORT', owner=2)
    assert not issue(game, covert.owner, Command('rename_unit', (allied_unit.id,), new_name='Unauthorized')).accepted
    game.selected_objects = [observer]
    handle_rename_unit(game, {'new_name': 'Unauthorized'})
    assert observer.name == 'Patrol Escort'
    covert.is_hidden_in_gas_giant = True
    covert.engines_component.current_hit_points = 0
    covert.commander_component.current_hit_points = 0
    view = unit_view(game, 0, covert)
    assert 'rename_unit' in view['supported_commands'] and 'rename_unit' in view['legal_commands']
    assert issue(game, covert.owner, command).accepted
    assert covert.name == 'Escort 7'


def test_socket_rename_uses_shared_gateway(covert_world):
    game, _, covert, _ = covert_world
    game.current_player = covert.owner
    covert.owner.controller = PlayerController.CODEX
    service = ControlService(game, port=0)
    observed = service._dispatch_or_wait({'protocol_version': PROTOCOL_VERSION, 'action': 'observe'}, Future())
    assert observed['data']['observation']['schema_version'] == 7
    assert observed['data']['observation']['command_catalog']['version'] == 6
    result = service._dispatch_or_wait({'protocol_version': PROTOCOL_VERSION, 'action': 'command',
        'request_id': 'rename', 'turn_token': observed['data']['turn_token'],
        'commands': [{'type': 'rename_unit', 'unit_ids': [covert.id], 'new_name': 'Resolute'}]}, Future())
    assert result['ok'] and result['data']['accepted']
    assert covert.name == unit_view(game, 1, covert)['name'] == 'Resolute'


def test_fake_ai_provider_renames_through_real_coordinator(covert_world, monkeypatch):
    game, _, covert, _ = covert_world
    game.current_player = covert.owner
    covert.owner.controller = PlayerController.OPENAI
    ended = []
    game.end_turn = lambda: ended.append(covert.name)
    command = Command('rename_unit', (covert.id,), new_name='Valiant')
    plan = TurnPlan(('Assign a warship name.',), CommandBatch((command,)), EMPTY_PATCH)
    # Full strict schema roundtrip includes new_name and null unused fields.
    plan = TurnPlan.from_dict(plan.to_dict(), strict=True)
    provider = FakePlanningProvider([plan])
    coordinator = AgentTurnCoordinator(game, provider=provider)
    monkeypatch.setattr(coordinator, '_write_memory', lambda *args: None)
    monkeypatch.setattr(coordinator, '_record_telemetry', lambda *args, **kwargs: None)
    try:
        assert coordinator.start_current_turn()
        coordinator._future.result(timeout=5)
        coordinator.update()
        assert ended == ['Valiant']
        assert provider.requests[0].observation['command_catalog']['commands']['rename_unit']['unit_selection'] == 'one'
        assert any('Valiant' in receipt for receipt in covert.owner.last_ai_report['receipts'])
    finally:
        coordinator.shutdown()
