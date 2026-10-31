"""Optional fuel priorities and departure levels preserve reserve and save rules."""
import json
from types import SimpleNamespace

import pytest

from antimatter_logistics import automatic_recipient
from constants import HullSize, StarType
from domain.celestials import Star, Wormhole
from game_ai.contracts import Command, ContractError
from game_ai.observation import build_observation
from geometry import Position
from save_manager import serialize_game_state, deserialize_game_state
from tests.support.campaigns import campaign, ship
from tests.support.commands import issue
from turn_processor import TurnProcessor
from unit_components.antimatter import AntimatterStorage, AntimatterHarvester
from unit_components.movement import Engines
from unit_components.wormhole_stabilizer import WormholeStabilizerComponent
from unit_orders.wormhole_stabilizer import StabilizeWormholeOrder
from wormhole_stabilization import process_support


def scenario(harvesting=True, amount=100):
    game = campaign()
    game.galaxy.game = game

    def vessel(name, fuel, capacity, x):
        unit = ship(game, name, hull=HullSize.MEDIUM)
        unit.position = Position(x, 0)
        unit.add_component(AntimatterStorage(unit, max_capacity=capacity))
        unit.antimatter_component.current_amount = fuel
        return unit

    actor = vessel('Fuel service', amount, 150, 1000)
    actor.add_component(Engines(actor, speed=100))
    if harvesting:
        actor.add_component(AntimatterHarvester(actor))
        source = Star(in_system='Sol', star_type=StarType.G_TYPE)
        source.in_hex = (0, 0)
        game.galaxy.systems['Sol'].add_celestial_body(source)
    else:
        source = vessel('Source depot', 600, 600, 1000)
    depot = vessel('Refinery', 164.25, 200, 1100)
    tender = vessel('Tender', 26.83, 150, 1400)
    tender.add_component(WormholeStabilizerComponent(tender))
    entry, exit_ = Wormhole((0, 0), 'Sol', 'Beta'), Wormhole((0, 0), 'Beta', 'Sol')
    entry.position = Position(1400, 0)
    entry.exit_wormhole_id, exit_.exit_wormhole_id = exit_.id, entry.id
    for body in (entry, exit_):
        game.galaxy.systems[body.in_system].add_celestial_body(body)
        game.galaxy.wormholes[body.id] = body
    tender.commander_component.add_order(StabilizeWormholeOrder(tender, {'target_id': entry.id}))
    process_support(game, tender.owner)
    assert tender.antimatter_component.current_amount == pytest.approx(21.83)
    kind = 'continuous_resupply' if harvesting else 'continuous_antimatter_transport'
    return game, actor, source, depot, tender, kind


def test_service_priority_chooses_low_fuel_stabilizer_and_preserves_donor_reserve():
    game, actor, source, depot, tender, kind = scenario()
    assert automatic_recipient(actor, source, game.galaxy, harvesting=True) is depot
    assert automatic_recipient(actor, source, game.galaxy, harvesting=True, priority='service_urgency') is tender
    command = Command(kind, (actor.id,), source_id=source.id, recipient_priority='service_urgency', minimum_load_fraction=.5)
    assert issue(game, actor.owner, command).accepted
    root = actor.commander_component.current_order
    root.update(game.galaxy)
    assert root.phase == 'delivering' and root.active_destination_unit_id == tender.id
    for _ in range(10):
        TurnProcessor(game)._process_movement(actor.owner)
        actor.commander_component.update()
    assert actor.antimatter_component.current_amount >= 60
    assert tender.antimatter_component.current_amount > 21.83


@pytest.mark.parametrize('manual', [False, True])
def test_new_urgent_service_preempts_only_automatic_destinations(manual):
    game, actor, source, depot, tender, kind = scenario()
    tender.antimatter_component.current_amount = 150
    assert issue(game, actor.owner, Command(kind, (actor.id,), source_id=source.id,
                                          target_id=depot.id if manual else None,
                                          minimum_load_fraction=.5, recipient_priority='service_urgency')).accepted
    root = actor.commander_component.current_order
    root.update(game.galaxy)
    assert root.active_destination_unit_id == depot.id
    tender.antimatter_component.current_amount = 1
    root.update(game.galaxy)
    assert root.active_destination_unit_id == (depot.id if manual else tender.id)


def test_urgent_recipient_still_requires_affordable_reachable_delivery():
    game, actor, source, depot, tender, _ = scenario()
    game.galaxy.systems['Sol'].remove_unit(tender)
    tender.in_system = 'Beta'
    game.galaxy.systems['Beta'].add_unit(tender)
    assert automatic_recipient(actor, source, game.galaxy, harvesting=True, priority='service_urgency') is depot


@pytest.mark.parametrize('harvesting', [False, True])
def test_partial_departure_preferences_survive_load_without_execution(harvesting):
    game, actor, source, depot, tender, kind = scenario(harvesting)
    assert issue(game, actor.owner, Command(kind, (actor.id,), source_id=source.id,
                                          minimum_load_fraction=.5, recipient_priority='service_urgency')).accepted
    root = actor.commander_component.current_order
    root.update(game.galaxy)
    assert root.phase == 'delivering' and actor.antimatter_component.current_amount < 150
    observation = build_observation(game, actor.owner)
    public = next(u for u in observation['units'] if u['id'] == actor.id)['current_order']
    assert public['parameters']['recipient_priority'] == 'service_urgency'
    assert public['parameters']['minimum_load_fraction'] == .5
    payload = json.loads(json.dumps(serialize_game_state(game)))
    errors = []
    assert deserialize_game_state(game, payload, on_error=errors.append), errors
    restored = game.galaxy.get_unit_by_id(actor.id)
    assert restored.antimatter_component.current_amount == actor.antimatter_component.current_amount
    assert restored.commander_component.current_order.phase == root.phase
    assert restored.commander_component.current_order.active_destination_unit_id == tender.id
    assert restored.commander_component.current_order.minimum_load_fraction == .5


def test_low_departure_threshold_does_not_waive_harvester_reserve():
    game, actor, source, depot, tender, kind = scenario(amount=40)
    assert issue(game, actor.owner, Command(kind, (actor.id,), source_id=source.id, minimum_load_fraction=.25)).accepted
    root = actor.commander_component.current_order
    root.update(game.galaxy)
    assert root.phase == 'harvesting' and root.public_waiting_reason == 'building_delivery_reserve'
    assert actor.antimatter_component.current_amount == 40


@pytest.mark.parametrize('field,value', [('minimum_load_fraction', 0), ('minimum_load_fraction', 1.1),
                                        ('minimum_load_fraction', True), ('minimum_load_fraction', float('nan')),
                                        ('recipient_priority', 'unknown')])
def test_invalid_preferences_reject_before_commands_or_load_replace_state(field, value):
    game, actor, source, depot, tender, kind = scenario()
    raw = dict(type=kind, unit_ids=[actor.id], source_id=source.id, **{field: value})
    with pytest.raises(ContractError):
        Command.from_dict(raw)
    assert issue(game, actor.owner, Command(kind, (actor.id,), source_id=source.id)).accepted
    root = actor.commander_component.current_order
    saved = json.loads(json.dumps(serialize_game_state(game)))
    # Locate the independent serialized root through the saved galaxy graph.
    def corrupt(value):
        if isinstance(value, dict):
            if value.get('public_id') == root.public_id:
                value['parameters'][field] = value_to_store
                return True
            return any(corrupt(child) for child in value.values())
        return any(corrupt(child) for child in value) if isinstance(value, list) else False
    value_to_store = value
    assert corrupt(saved)
    assert not deserialize_game_state(game, saved)
    assert actor.commander_component.current_order is root


def test_dialog_emits_selected_policy_and_departure_threshold(pygame_context, monkeypatch):
    import pygame
    import pygame_gui
    from display_config import DisplayConfig
    from gui.antimatter_transport_window import AntimatterTransportWindow
    from gui.theme_loader import build_ui_manager
    game, actor, source, _, _, _ = scenario()
    config = DisplayConfig(1280, 720, False)
    gui = SimpleNamespace(game_instance=game, display_config=config, manager=build_ui_manager(config))
    window = AntimatterTransportWindow(gui, actor, source, harvesters=[actor])
    gui.antimatter_transport_window = window
    sent = []
    monkeypatch.setattr('tactical_ui.issue', lambda game, command: sent.append(command) or True)
    try:
        window.process_event(pygame.event.Event(pygame_gui.UI_DROP_DOWN_MENU_CHANGED,
                             ui_element=window.priority, text='Priority: Fuel service urgency'))
        window.process_event(pygame.event.Event(pygame_gui.UI_DROP_DOWN_MENU_CHANGED,
                             ui_element=window.departure, text='Depart at: 50% tank'))
        window.process_event(pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, ui_element=window.start))
        assert sent[0]['recipient_priority'] == 'service_urgency'
        assert sent[0]['minimum_load_fraction'] == .5
    finally:
        window.close()
        gui.manager.clear_and_reset()
