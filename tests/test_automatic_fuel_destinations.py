"""Shared continuous logistics contracts, live retargeting and disclosure."""
import json

import pytest

from antimatter_logistics import automatic_recipient, delivery_budget
from game_ai.contracts import Command, ContractError
from game_ai.order_view import order_layers
from save_manager import serialize_game_state, deserialize_game_state
from unit_orders.base import OrderStatus
from geometry import Position
from tests.test_antimatter_logistics import (
    vessel, issue, tick, route_scenario, make_route_window, select_endpoint,
)
from tests.test_continuous_resupply import harvesting_scenario


def scenario(harvesting=False, manual=False):
    if harvesting:
        return harvesting_scenario(manual=manual, amount=150)
    game, actor, source, target, command = route_scenario()
    actor.antimatter_component.current_amount = 600
    target.antimatter_component.max_capacity = 600
    if not manual:
        command['target_id'] = None
    return game, actor, source, target, command


@pytest.mark.parametrize('harvesting', [False, True])
def test_automatic_selection_is_owned_only_reachable_and_deterministic(harvesting):
    game, actor, source, target, command = scenario(harvesting)
    # Equal proximity must use unit IDs, independent of sector list ordering.
    target.position = Position(1500, 0)
    other = vessel(game, 'same distance', amount=0, position=(1500, 0))
    ally = vessel(game, 'closer ally', amount=0, position=(actor.position.x, 0), owner=1)
    ally.owner.team_id = actor.owner.team_id
    remote = vessel(game, 'unreachable', amount=0)
    game.galaxy.systems['Sol'].hexes[(0, 0)].units.remove(remote)
    remote.in_system = 'Beta'
    game.galaxy.systems['Beta'].hexes[(0, 0)].units.append(remote)
    for invalid in ('full', 'broken', 'hidden', 'dead'):
        unit = vessel(game, invalid, amount=0, position=(actor.position.x, 0))
        if invalid == 'full':
            unit.antimatter_component.current_amount = 600
        elif invalid == 'broken':
            unit.antimatter_component.current_hit_points = 0
        elif invalid == 'hidden':
            unit.is_hidden_in_gas_giant = True
        else:
            unit.current_hit_points = 0
    game.galaxy.systems['Sol'].hexes[(0, 0)].units.reverse()
    before = actor.antimatter_component.current_amount
    assert automatic_recipient(actor, source, game.galaxy, harvesting=harvesting) is target
    assert actor.antimatter_component.current_amount == before
    target.antimatter_component.current_amount = 600
    assert automatic_recipient(actor, source, game.galaxy, harvesting=harvesting) is other


@pytest.mark.parametrize('harvesting', [False, True])
@pytest.mark.parametrize('invalid', ['enemy', 'removed', 'hidden', 'broken', 'dead', 'unreachable', 'full'])
def test_automatic_retargets_in_flight_without_failing_root(harvesting, invalid):
    game, actor, source, target, command = scenario(harvesting)
    assert issue(game, command).accepted
    order = actor.commander_component.current_order
    tick(game, actor)
    assert order.active_destination_unit_id == target.id
    assert order.sub_orders
    previous_child = order.sub_orders[0]
    alternate = vessel(game, 'alternate', amount=0, position=(actor.position.x + 150, 0))
    if invalid == 'enemy':
        target.owner = game.players[1]
    elif invalid == 'removed':
        game.galaxy.systems['Sol'].hexes[(0, 0)].units.remove(target)
    elif invalid == 'hidden':
        target.is_hidden_in_gas_giant = True
    elif invalid == 'broken':
        target.antimatter_component.current_hit_points = 0
    elif invalid == 'dead':
        target.current_hit_points = 0
    elif invalid == 'full':
        target.antimatter_component.current_amount = 600
    else:
        game.galaxy.systems['Sol'].hexes[(0, 0)].units.remove(target)
        target.in_system = 'Beta'
        game.galaxy.systems['Beta'].hexes[(0, 0)].units.append(target)
    order.update(game.galaxy)
    assert order.status == OrderStatus.IN_PROGRESS
    assert order.active_destination_unit_id == alternate.id
    assert previous_child.status == OrderStatus.CANCELLED
    assert alternate.antimatter_component.current_amount > 0


@pytest.mark.parametrize('harvesting', [False, True])
@pytest.mark.parametrize('invalid', ['enemy', 'removed', 'hidden', 'broken', 'dead'])
def test_manual_recipient_loss_fails_without_substitution(harvesting, invalid):
    game, actor, source, target, command = scenario(harvesting, manual=True)
    target.owner = game.players[1]
    target.owner.team_id = actor.owner.team_id  # Manual allies are supported.
    assert issue(game, command).accepted
    order = actor.commander_component.current_order
    tick(game, actor)
    vessel(game, 'alternative', amount=0, position=(actor.position.x, 0))
    if invalid == 'enemy':
        target.owner.team_id += 100
    elif invalid == 'removed':
        game.galaxy.systems['Sol'].hexes[(0, 0)].units.remove(target)
    elif invalid == 'hidden':
        target.is_hidden_in_gas_giant = True
    elif invalid == 'broken':
        target.antimatter_component.current_hit_points = 0
    else:
        target.current_hit_points = 0
    order.update(game.galaxy)
    assert order.status == OrderStatus.FAILED
    assert order.failure_reason == 'target_unavailable'
    assert not order.sub_orders


@pytest.mark.parametrize('harvesting', [False, True])
def test_automatic_recipient_stays_locked_and_follows_movement(harvesting):
    game, actor, source, target, command = scenario(harvesting)
    assert issue(game, command).accepted
    tick(game, actor)
    order = actor.commander_component.current_order
    child = order.sub_orders[0]
    vessel(game, 'closer newcomer', amount=0, position=(actor.position.x + 100, 0))
    target.position = Position(target.position.x + 100, 0)
    order.update(game.galaxy)
    assert order.active_destination_unit_id == target.id
    assert child.status == OrderStatus.CANCELLED
    assert order.sub_orders[0].parameters['logistics_anchor'][-1] == [target.position.x, 0]


@pytest.mark.parametrize('harvesting', [False, True])
def test_automatic_delivers_to_multiple_units_without_loading_between(harvesting):
    game, actor, source, first, command = scenario(harvesting)
    first.position = Position(actor.position.x + 50, 0)
    first.antimatter_component.current_amount = 575
    second = vessel(game, 'second', amount=0, position=(actor.position.x + 100, 0))
    assert issue(game, command).accepted
    order = actor.commander_component.current_order
    order.update(game.galaxy)  # Leave loading/harvesting.
    order.update(game.galaxy)  # Fill first.
    assert first.antimatter_component.current_amount == 600
    assert order.phase == 'delivering'
    order.update(game.galaxy)  # Donate to second without another pickup.
    assert second.antimatter_component.current_amount == 25
    assert actor.antimatter_component.current_amount >= order.return_reserve


@pytest.mark.parametrize('harvesting', [False, True])
def test_automatic_without_demand_waits_and_resumes(harvesting):
    game, actor, source, target, command = scenario(harvesting)
    target.antimatter_component.current_amount = 600
    assert issue(game, command).accepted
    order = actor.commander_component.current_order
    order.update(game.galaxy)
    assert order.waiting_reason == 'no_destination'
    assert order.active_destination_unit_id is None
    view = order_layers(actor, 'self', {actor.id, source.id, target.id}, {source.id})['current_order']
    assert view['parameters']['destination_mode'] == 'automatic'
    assert view['parameters']['target_id'] is None
    target.antimatter_component.current_amount = 0
    order.update(game.galaxy)
    assert order.phase == 'delivering'


@pytest.mark.parametrize('harvesting', [False, True])
def test_source_loss_and_actor_capability_loss_fail(harvesting):
    for actor_loss in (False, True):
        game, actor, source, target, command = scenario(harvesting)
        assert issue(game, command).accepted
        order = actor.commander_component.current_order
        order.update(game.galaxy)
        if actor_loss:
            actor.antimatter_component.current_hit_points = 0
        elif harvesting:
            game.galaxy.systems['Sol'].hexes[(0, 0)].celestial_bodies.remove(source)
        else:
            source.owner = game.players[1]
        order.update(game.galaxy)
        assert order.status == OrderStatus.FAILED
        assert order.failure_reason == ('capability_unavailable' if actor_loss else 'target_unavailable')


def test_next_transport_delivery_includes_return_budget_and_rejects_unproductive_cargo():
    game, actor, source, target, command = scenario()
    actor.antimatter_component.current_amount = 35
    assert delivery_budget(actor, source, target, game.galaxy) >= 35
    assert automatic_recipient(actor, source, game.galaxy) is None
    target.position = Position(150, 0)
    assert delivery_budget(actor, source, target, game.galaxy) == 0
    assert automatic_recipient(actor, source, game.galaxy) is target


@pytest.mark.parametrize('harvesting', [False, True])
def test_shared_commands_require_source_and_accept_null_or_omitted_recipient(harvesting):
    game, actor, source, target, command = scenario(harvesting)
    for target_value in ('omit', None):
        payload = dict(command)
        if target_value == 'omit':
            payload.pop('target_id')
        assert Command.from_dict(payload).target_id is None
    payload = dict(command)
    payload.pop('source_id')
    with pytest.raises(ContractError):
        Command.from_dict(payload)
    invalid_source = target.id if harvesting else 999999
    previous = actor.commander_component.current_order
    assert not issue(game, dict(command, source_id=invalid_source)).accepted
    assert actor.commander_component.current_order is previous
    assert not issue(game, dict(command, target_id=actor.id)).accepted


@pytest.mark.parametrize('harvesting', [False, True])
def test_active_recipient_redaction_and_save_does_not_pin_automatic_mode(harvesting):
    game, actor, source, target, command = scenario(harvesting)
    assert issue(game, command).accepted
    tick(game, actor)
    view = order_layers(actor, 'self', {actor.id, source.id, target.id}, {source.id})['current_order']
    assert view['parameters']['target_id'] is None
    assert view['progress']['active_destination_id'] == target.id
    hidden = order_layers(actor, 'self', {actor.id, source.id}, {source.id})['current_order']
    assert hidden['parameters'] == {} and hidden['progress'] == {}
    assert all(child['parameters'] == {} for child in hidden['suborders'])
    state = json.loads(json.dumps(serialize_game_state(game)))
    amount = actor.antimatter_component.current_amount
    assert deserialize_game_state(game, state)
    restored = game.galaxy.get_unit_by_id(actor.id)
    route = restored.commander_component.current_order
    assert route.automatic and route.active_destination_unit_id == target.id
    assert restored.antimatter_component.current_amount == amount
    game.galaxy.get_unit_by_id(target.id).owner = game.players[1]
    alternate = vessel(game, 'new recipient', amount=0, position=(restored.position.x + 100, 0))
    route.update(game.galaxy)
    assert route.status == OrderStatus.IN_PROGRESS
    assert route.active_destination_unit_id == alternate.id


def mode_event(window, automatic):
    import pygame
    import pygame_gui
    window.process_event(pygame.event.Event(pygame_gui.UI_DROP_DOWN_MENU_CHANGED,
        ui_element=window.mode, text='Destination: Automatic' if automatic else 'Destination: Manual'))


def test_transport_dialog_automatic_ignores_manual_filters_and_selection(monkeypatch, pygame_context):
    import pygame
    import pygame_gui
    game, actor, source, target, _ = scenario()
    window = make_route_window(game, actor, source)
    emitted = []
    monkeypatch.setattr('tactical_ui.issue', lambda game, command: emitted.append(command) or True)
    try:
        assert not window.automatic
        select_endpoint(window, window.destination, 'unit', target.id)
        mode_event(window, True)
        assert window.start.is_enabled and window.queue.is_enabled and not window.swap.is_enabled
        assert not any(w.is_enabled for w in (window.destination.system, window.destination.hex,
                                             window.destination.search, window.destination.unit))
        mode_event(window, False)
        assert window.destination.state.unit_id == target.id and window.swap.is_enabled
        mode_event(window, True)
        window.process_event(pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, ui_element=window.start))
        assert emitted[-1]['source_id'] == source.id and emitted[-1]['target_id'] is None
    finally:
        window.close()
        game.gui.manager.clear_and_reset()


@pytest.mark.parametrize('nebula', [False, True])
@pytest.mark.parametrize('manual', [False, True])
def test_harvester_context_dialog_multiple_units_and_queue(monkeypatch, pygame_context, nebula, manual):
    import pygame
    import pygame_gui
    from input_processor.context_actions import handle_context_menu_action
    from unit_components.antimatter import AntimatterHarvester
    game, actor, source, target, _ = harvesting_scenario(nebula=nebula)
    second = vessel(game, 'second harvester', position=(1000, 0), moving=True)
    second.add_component(AntimatterHarvester(second))
    setup = make_route_window(game, actor, target)
    setup.close()
    game.selected_objects = [actor, second]
    emitted = []
    monkeypatch.setattr('tactical_ui.issue', lambda game, command: emitted.append(command) or True)
    handle_context_menu_action(game, 'continuous_resupply', source)
    window = game.gui.antimatter_transport_window
    try:
        assert window.automatic and window.source is None and window.start.is_enabled
        assert not window.swap.is_enabled
        if manual:
            mode_event(window, False)
            assert not window.start.is_enabled
            select_endpoint(window, window.destination, 'unit', target.id)
        window.process_event(pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, ui_element=window.queue))
        assert emitted[-1] == dict(type='continuous_resupply', unit_ids=[actor.id, second.id],
                                  source_id=source.id, target_id=target.id if manual else None, queue=True)
    finally:
        window.close()
        game.gui.manager.clear_and_reset()


@pytest.mark.parametrize('harvesting', [False, True])
def test_failed_actual_approach_tries_another_recipient(harvesting):
    game, actor, source, target, command = scenario(harvesting)
    assert issue(game, command).accepted
    order = actor.commander_component.current_order
    order.update(game.galaxy)
    alternate = vessel(game, 'alternate', amount=0, position=(actor.position.x + 50, 0))
    child = order.sub_orders[0]
    child.fail('path_unavailable')  # Actual routing can fail after a successful estimate.
    order.update(game.galaxy)
    assert order.status == OrderStatus.IN_PROGRESS
    assert order.active_destination_unit_id == alternate.id
    assert not order.sub_orders


@pytest.mark.parametrize('harvesting', [False, True])
def test_queue_cancel_and_replace_preserve_continuous_root_semantics(harvesting):
    game, actor, source, target, command = scenario(harvesting)
    assert issue(game, command).accepted
    root = actor.commander_component.current_order
    assert issue(game, dict(command, target_id=target.id, queue=True)).accepted
    queued = actor.commander_component.orders_queue[0]
    view = order_layers(actor, 'self', {actor.id, source.id, target.id}, {source.id})
    assert view['queued_orders'][0]['blocked_by_order_id'] == root.public_id
    assert issue(game, dict(type='cancel_order', unit_ids=(actor.id,), order_id=root.public_id)).accepted
    assert root.status == OrderStatus.CANCELLED
    assert actor.commander_component.current_order is queued
    assert not queued.automatic
    amount = actor.antimatter_component.current_amount
    assert issue(game, command).accepted
    assert queued.status == OrderStatus.CANCELLED
    assert actor.commander_component.current_order.automatic
    assert actor.antimatter_component.current_amount == amount


@pytest.mark.parametrize('harvesting', [False, True])
@pytest.mark.parametrize('field,value', [
    ('phase', 'invalid'), ('waiting_reason', 'invalid'), ('return_reserve', -1),
    ('active_destination_unit_id', True), ('active_destination_unit_id', -1),
    ('active_destination_unit_id', 99999),
])
def test_malformed_saved_route_rejected_transactionally(harvesting, field, value):
    game, actor, source, target, command = scenario(harvesting, manual=True)
    assert issue(game, command).accepted
    order = actor.commander_component.current_order
    state = json.loads(json.dumps(serialize_game_state(game)))
    units = state['galaxy']['systems'][0]['hexes'][0]['units']
    saved_actor = next(unit for unit in units if unit['id'] == actor.id)
    saved_order = saved_actor['components']['Commander']['runtime']['current_order']
    saved_order['runtime_state'][field] = value
    assert not deserialize_game_state(game, state)
    assert game.galaxy.get_unit_by_id(actor.id) is actor
    assert actor.commander_component.current_order is order


@pytest.mark.parametrize('harvesting', [False, True])
def test_command_discovery_exposes_sources_and_allows_no_demand(harvesting):
    from game_ai.observation import build_observation
    game, actor, source, target, command = scenario(harvesting)
    target.antimatter_component.current_amount = target.antimatter_component.max_capacity
    observation = build_observation(game, actor.owner)
    # Keep disclosure tests independent of the observation's top-level grouping.
    from game_ai.rules import command_guidance
    legal, options, _ = command_guidance(game, actor.owner, actor,
        exact_bodies=[source] if harvesting else [], visible_units=[actor, target] if harvesting else [actor, source, target])
    assert command['type'] in legal
    assert source.id in options[command['type']]['source_ids']
    assert options[command['type']]['automatic_when_target_null']
    assert options[command['type']]['automatic_recipient_scope'] == 'owned_galaxy_wide'
    assert observation['schema_version'] == 22
    assert observation['command_catalog']['version'] == 18


@pytest.mark.parametrize('invalid_last', [False, True])
def test_large_human_harvester_selection_preflights_as_one_batch(invalid_last):
    from unit_components.antimatter import AntimatterHarvester
    from tactical_ui import issue as human_issue
    game, actor, source, target, _ = harvesting_scenario(manual=True)
    actors = [actor]
    for _ in range(12):
        unit = vessel(game, 'harvester', moving=True, position=(1000, 0))
        unit.add_component(AntimatterHarvester(unit))
        actors.append(unit)
    if invalid_last:
        actors[-1].harvester_component.current_hit_points = 0
    accepted = human_issue(game, dict(type='continuous_resupply', unit_ids=[u.id for u in actors],
                                     source_id=source.id, target_id=target.id))
    assert accepted is not invalid_last
    assert all((u.commander_component.current_order is None) == invalid_last for u in actors)


@pytest.mark.parametrize('size', [(1000, 700), (2560, 1440)])
@pytest.mark.parametrize('harvesting', [False, True])
@pytest.mark.filterwarnings('error:Label Rect is too small:UserWarning')
def test_shared_dialog_layout(pygame_context, tmp_path, size, harvesting):
    import pygame
    from gui.antimatter_transport_window import AntimatterTransportWindow
    game, actor, source, target, _ = scenario(harvesting)
    screen = pygame.display.set_mode(size)
    setup = make_route_window(game, actor, target, size)
    if harvesting:
        setup.close()
        window = AntimatterTransportWindow(game.gui, actor, source, harvesters=[actor])
    else:
        window = setup
    try:
        game.gui.manager.update(0.1)
        screen.fill((5, 10, 20))
        game.gui.manager.draw_ui(screen)
        path = tmp_path / 'fuel-dialog.png'
        pygame.image.save(screen, str(path))
        print(f'Layout image: {path}')
        outer = window.window.get_container().get_rect()
        for widget in (window.mode, window.body, window.status, window.start, window.queue, window.cancel):
            assert outer.contains(widget.get_abs_rect())
        assert not window.mode.get_abs_rect().colliderect(window.body.get_abs_rect())
        for picker in window._pickers():
            assert window.body.get_abs_rect().contains(picker.unit.get_abs_rect())
        mode_event(window, not harvesting)
        assert window.start.is_enabled == (not harvesting)
    finally:
        window.close()
        game.gui.manager.clear_and_reset()
