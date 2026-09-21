"""Stable mixed-production slots across commands, lifecycle and persistence."""
from copy import deepcopy

import pytest

from game_ai.contracts import Command, ContractError
from game_ai.observation import build_observation
from save_manager import serialize_game_state, deserialize_game_state, serialize_unit
from tests.support.campaigns import campaign
from tests.support.commands import issue
from tests.test_wing_production import world, create, command
from unit_templates import UNIT_TEMPLATES


def finish_build(game, bay):
    if not bay.constructing:
        bay.update(game.galaxy)
    assert bay.constructing
    index = bay.construction_slot_index
    duration = bay.production_template(index)['build_time']
    for _ in range(duration):
        bay.update(game.galaxy)
    assert not bay.constructing
    return next(u for u in bay.docked_units if u.id == bay.slots[index]['wing_id'])


def test_mixed_slots_build_serially_and_preserve_overrides_and_payments():
    game, carrier, bay = world()
    templates = ('FIGHTER_WING', 'BOMBER_WING', 'RECON_WING')
    turrets = ('beam', 'mass_driver', 'missile')
    credits = carrier.owner.credits
    commands = [command(carrier, key, slot_index=i, turret_type_override=turrets[i],
                        defense_type_override='armor') for i, key in enumerate(templates)]
    assert issue(game, carrier.owner, *commands).accepted
    assert carrier.owner.credits == credits and not bay.constructing
    for index, key in enumerate(templates):
        bay.update(game.galaxy)
        assert bay.construction_slot_index == index
        assert len(bay.docked_units) == index
        credits -= UNIT_TEMPLATES[key]['build_cost']
        assert carrier.owner.credits == credits
        wing = finish_build(game, bay)
        assert wing.template_name == UNIT_TEMPLATES[key]['name'] and bay.slot_for_wing(wing) == index
        assert all(t.turret_type.value == turrets[index] for t in wing.weapons_component.turrets)
        assert carrier.owner.credits == credits
    bay.validate_assignments()


def test_worker_skips_unselected_and_unaffordable_slots():
    game, carrier, bay = world()
    assert bay.set_production(1, 'FIGHTER_WING')
    assert bay.set_production(2, 'INTERCEPTOR_WING')
    carrier.owner.credits = UNIT_TEMPLATES['INTERCEPTOR_WING']['build_cost']
    bay.update(game.galaxy)
    assert bay.construction_slot_index == 2
    assert carrier.owner.credits == 0
    wing = finish_build(game, bay)
    assert bay.slot_for_wing(wing) == 2
    assert bay.slots[0]['wing_id'] is bay.slots[1]['wing_id'] is None


def test_occupied_slot_replacement_does_not_change_existing_wing_or_shift_slots():
    game, carrier, bay = world()
    for i in range(2):
        assert bay.set_production(i, 'FIGHTER_WING')
    first, second = finish_build(game, bay), finish_build(game, bay)
    before = serialize_unit(second)
    assert issue(game, carrier.owner, command(carrier, 'BOMBER_WING', slot_index=1,
                                             turret_type_override='beam')).accepted
    assert serialize_unit(second) == before
    assert bay.deploy(first, game.galaxy)
    assert bay.slot_for_wing(first) == 0 and bay.get_used_slots() == 2
    second.destroy()
    assert bay.slot_for_wing(first) == 0 and bay.slots[1]['wing_id'] is None
    replacement = finish_build(game, bay)
    assert replacement.template_name == UNIT_TEMPLATES['BOMBER_WING']['name']
    assert bay.slot_for_wing(replacement) == 1
    assert bay.dock(first, game.galaxy) and bay.slot_for_wing(first) == 0
    bay.validate_assignments()


def test_clear_occupied_slot_keeps_replenishment_and_pause_state():
    game, carrier, bay = world()
    assert bay.set_production(0, 'BOMBER_WING', 'beam', 'armor')
    wing = finish_build(game, bay)
    bay.production_enabled = False
    before = serialize_unit(wing)
    assert issue(game, carrier.owner, command(carrier, None)).accepted
    assert serialize_unit(wing) == before and not bay.production_enabled
    assert bay.slots[0] == dict(production_template_name=None, turret_type_override=None,
                                defense_type_override=None, wing_id=wing.id)
    wing.current_hit_points -= 10
    credits = carrier.owner.credits
    bay.update(game.galaxy)
    bay.update(game.galaxy)
    assert wing.current_hit_points == wing.max_hit_points and carrier.owner.credits == credits - 35
    wing.destroy()
    bay.production_enabled = True
    for _ in range(5):
        bay.update(game.galaxy)
    assert not bay.constructing and not bay.docked_units


def test_only_building_slot_is_locked_and_batch_rejection_is_atomic():
    game, carrier, bay = world()
    assert bay.set_production(0, 'FIGHTER_WING')
    bay.update(game.galaxy)
    assert issue(game, carrier.owner, command(carrier, 'BOMBER_WING', slot_index=1)).accepted
    before = bay.to_state(), carrier.owner.credits
    result = issue(game, carrier.owner, command(carrier, None, slot_index=1), command(carrier, None))
    assert not result.accepted and (bay.to_state(), carrier.owner.credits) == before
    assert issue(game, carrier.owner, command(carrier, 'RECON_WING', slot_index=1,
                                             turret_type_override='beam'),
                 command(carrier, 'BOMBER_WING', slot_index=1)).accepted
    assert bay.slots[1]['turret_type_override'] is None
    view = next(u for u in build_observation(game, carrier.owner)['units'] if u['id'] == carrier.id)
    assert 0 not in view['command_options']['set_wing_production']['slot_indices']
    assert 1 in view['command_options']['set_wing_production']['slot_indices']
    assert view['capability_details']['strikecraft_bay']['slots'][0]['edit_blocker'] == 'slot_constructing'


@pytest.mark.parametrize('grouped', [False, True])
def test_full_bay_accepts_returning_wings_through_gateway(grouped):
    game, carrier, bay = world()
    wings = []
    for _ in range(bay.max_slots):
        wing = create(game, 'FIGHTER_WING')
        assert bay.dock(wing, game.galaxy)
        wings.append(wing)
    for wing in wings[:2]:
        assert bay.deploy(wing, game.galaxy)
    assert not bay.free_slot_indices()
    groups = [wings[:2]] if grouped else [[wing] for wing in wings[:2]]
    commands = [Command('dock_in_strikecraft_bay', tuple(u.id for u in group), target_id=carrier.id) for group in groups]
    assert issue(game, carrier.owner, *commands).accepted
    assert all(wing in bay.docked_units for wing in wings)
    assert [slot['wing_id'] for slot in bay.slots] == [wing.id for wing in wings]


def test_transfer_releases_old_slot_and_cannot_take_construction_reservation():
    game, carrier, bay = world()
    assert bay.set_production(0, 'FIGHTER_WING')
    wing = finish_build(game, bay)
    assert bay.deploy(wing, game.galaxy)
    other = create(game, 'ESCORT_CARRIER')
    destination = other.strikecraft_bay_component
    assert destination.set_production(0, 'BOMBER_WING')
    destination.update(game.galaxy)
    if destination.max_slots == 1:
        assert not issue(game, carrier.owner, Command('dock_in_strikecraft_bay', (wing.id,), target_id=other.id)).accepted
        destination = create(game, 'FLEET_CARRIER').strikecraft_bay_component
        other = destination.unit
        assert destination.set_production(0, 'BOMBER_WING')
        destination.update(game.galaxy)
    assert issue(game, carrier.owner, Command('dock_in_strikecraft_bay', (wing.id,), target_id=other.id)).accepted
    assert destination.slot_for_wing(wing) == 1 and bay.slots[0]['wing_id'] is None
    assert wing not in bay.launched_units and wing.strikecraft_wing_component.mother_carrier is other
    assert destination.slots[1]['production_template_name'] is None
    replacement = finish_build(game, destination)
    assert destination.slot_for_wing(replacement) == 0 and replacement.template_name == UNIT_TEMPLATES['BOMBER_WING']['name']
    bay.validate_assignments()
    destination.validate_assignments()


def test_paid_construction_reserves_last_capacity_but_allows_assigned_return():
    game, carrier, bay = world()
    assert bay.set_production(0, 'BOMBER_WING')
    bay.update(game.galaxy)
    wings = []
    for _ in range(bay.max_slots - 1):
        wing = create(game, 'FIGHTER_WING')
        assert bay.dock(wing, game.galaxy)
        wings.append(wing)
    incoming = create(game, 'RECON_WING')
    assert not bay.can_dock(incoming)
    assert not bay.dock(incoming, game.galaxy)
    assert not issue(game, carrier.owner, Command('dock_in_strikecraft_bay', (incoming.id,),
                                                 target_id=carrier.id)).accepted
    returning = wings[0]
    assert bay.deploy(returning, game.galaxy)
    assert issue(game, carrier.owner, Command('dock_in_strikecraft_bay', (returning.id,),
                                             target_id=carrier.id)).accepted
    finished = finish_build(game, bay)
    assert bay.slot_for_wing(finished) == 0 and bay.get_used_slots() == bay.max_slots
    bay.validate_assignments()


@pytest.mark.parametrize('index', [None, -1, True, 0.0, '0', 100])
def test_invalid_slot_indices_reject_without_mutation(index):
    game, carrier, bay = world()
    before = bay.to_state(), carrier.owner.credits
    assert not issue(game, carrier.owner, command(carrier, slot_index=index)).accepted
    assert (bay.to_state(), carrier.owner.credits) == before


def test_command_requires_explicit_nullable_template_and_scoped_slot_field():
    with pytest.raises(ContractError, match='explicit template_name'):
        Command.from_dict(dict(type='set_wing_production', unit_ids=[0], slot_index=0))
    clear = Command.from_dict(dict(type='set_wing_production', unit_ids=[0], slot_index=0, template_name=None))
    assert Command.from_dict(clear.to_dict()) == clear
    with pytest.raises(ContractError, match='null equipment'):
        Command.from_dict({**clear.to_dict(), 'turret_type_override': 'beam'})
    with pytest.raises(ContractError, match='does not use slot_index'):
        Command.from_dict(dict(type='cancel_orders', unit_ids=[0], slot_index=0))


def test_mixed_slots_roundtrip_preserves_launched_assignment_and_paid_job():
    game, carrier, bay = world()
    for i, key in enumerate(('FIGHTER_WING', 'BOMBER_WING', 'RECON_WING')):
        assert bay.set_production(i, key)
    wing = finish_build(game, bay)
    assert bay.deploy(wing, game.galaxy)
    bay.update(game.galaxy)
    bay.update(game.galaxy)
    bay.production_enabled = False
    before = bay.to_state(), carrier.owner.credits
    restored = campaign()
    assert deserialize_game_state(restored, serialize_game_state(game))
    loaded = restored.galaxy.get_unit_by_id(carrier.id).strikecraft_bay_component
    assert (loaded.to_state(), loaded.unit.owner.credits) == before
    assert loaded.slot_for_wing(loaded.launched_units[0]) == 0
    loaded.update(restored.galaxy)
    assert loaded.slots[1]['wing_id'] is not None and loaded.slots[2]['wing_id'] is None
    assert loaded.unit.owner.credits == before[1]


@pytest.mark.parametrize('corruption', ['count', 'duplicate', 'missing', 'nonwing', 'wrong_carrier',
                                      'occupied_build', 'unselected_build', 'bool_index', 'progress'])
def test_invalid_slot_graph_rejects_save_transactionally(corruption):
    game, carrier, bay = world()
    assert bay.set_production(0, 'FIGHTER_WING')
    wing = finish_build(game, bay)
    assert bay.deploy(wing, game.galaxy)
    data = deepcopy(serialize_game_state(game))
    units = [u for system in data['galaxy']['systems'] for sector in system['hexes'] for u in sector['units']]
    saved = next(u for u in units if u['id'] == carrier.id)
    runtime = next(c['runtime'] for c in saved['components'].values() if c['type'] == 'StrikecraftBayComponent')
    if corruption == 'count': runtime['slots'].pop()
    elif corruption == 'duplicate': runtime['slots'][1]['wing_id'] = wing.id
    elif corruption == 'missing': runtime['slots'][0]['wing_id'] = 999999
    elif corruption == 'nonwing': runtime['slots'][0]['wing_id'] = carrier.id
    elif corruption == 'wrong_carrier':
        saved_wing = next(u for u in units if u['id'] == wing.id)
        next(c for c in saved_wing['components'].values() if c['type'] == 'StrikecraftWingComponent')['runtime']['mother_carrier'] = None
    elif corruption == 'occupied_build': runtime['construction_slot_index'] = 0
    elif corruption == 'unselected_build': runtime['construction_slot_index'] = 1
    elif corruption == 'bool_index': runtime['construction_slot_index'] = False
    elif corruption == 'progress': runtime['construction_progress'] = 1
    before = bay.to_state(), carrier.owner.credits, game.galaxy
    assert not deserialize_game_state(game, data)
    assert (bay.to_state(), carrier.owner.credits, game.galaxy) == before


def test_socket_and_strict_provider_share_per_slot_configuration():
    import json
    from concurrent.futures import Future
    from types import SimpleNamespace
    from game_control_protocol import ControlService
    from game_ai.adapters.openai_responses import OpenAIResponsesProvider
    from game_ai.adapters.base import PlanningRequest
    from game_ai.runtime import get_runtime_config
    from player_controller import PlayerController
    from tests.support.ai import EMPTY_PATCH
    game, carrier, bay = world()
    game.gui = None
    game.current_player = carrier.owner
    carrier.owner.controller = PlayerController.CODEX
    service = ControlService(game, port=0)
    observed = service._dispatch_or_wait(dict(protocol_version=3, action='observe'), Future())
    assert observed['data']['observation']['schema_version'] == 20
    reply = service._dispatch_or_wait(dict(protocol_version=3, action='command', request_id='slots',
        turn_token=observed['data']['turn_token'], commands=[
            dict(type='set_wing_production', unit_ids=[carrier.id], slot_index=0, template_name='FIGHTER_WING'),
            dict(type='set_wing_production', unit_ids=[carrier.id], slot_index=1, template_name='BOMBER_WING')]), Future())
    assert reply['ok'] and reply['data']['accepted']
    assert bay.slots[0]['production_template_name'] == 'FIGHTER_WING'
    assert bay.slots[1]['production_template_name'] == 'BOMBER_WING'
    requested = command(carrier, None, slot_index=1)
    output = dict(plan=[], commands=[requested.to_dict()], memory_patch=EMPTY_PATCH, end_turn=True)

    def fake_response(**kwargs):
        schema = kwargs['text']['format']
        assert schema['strict'] and schema['name'] == 'wormhole_control_turn_v14'
        assert 'slot_index' in schema['schema']['properties']['commands']['items']['required']
        assert kwargs['prompt_cache_key'] == 'wormhole-control-turn-v20'
        return SimpleNamespace(id='fake', output_text=json.dumps(output), usage=None)

    provider = OpenAIResponsesProvider(client=SimpleNamespace(responses=SimpleNamespace(create=fake_response)))
    result = provider.plan_turn(PlanningRequest('campaign', 'agent', 'AI', 1, {}, {}), get_runtime_config('low'))
    assert result.plan.batch.commands[0] == requested
    assert issue(game, carrier.owner, *result.plan.batch.commands).accepted
    assert bay.slots[1]['production_template_name'] is None
    assert bay.slots[0]['production_template_name'] == 'FIGHTER_WING'
