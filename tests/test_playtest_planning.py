"""Observed provider mistakes, semantic repair and durable constraint retention."""
import asyncio
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from game_ai.adapters.base import PlanningOutputError, RepairIssue
from game_ai.adapters.fake import FakePlanningProvider
from game_ai.contracts import Command, CommandBatch, TurnPlan
from game_ai.coordinator import AgentTurnCoordinator
from game_ai.evaluation import playtest_gateway_cases, compare_gateway_reasoning_efforts
from game_ai.memory import AgentMemory, rejection_lessons
from player_controller import PlayerController
from tests.support.ai import EMPTY_PATCH


def plan(*commands, patch=None):
    return TurnPlan((), CommandBatch(tuple(commands), True), patch or EMPTY_PATCH)


@pytest.mark.parametrize('combat', [True, False])
def test_october_target_and_obstacle_errors_repair_from_public_guidance(combat):
    from game_ai.evaluation import october_playtest_gateway_cases
    case = october_playtest_gateway_cases()[0 if combat else 1]
    request, validate = case.build()
    actor = next(u for u in request.observation['units'] if u['id'] == 101)
    if combat:
        assert 201 not in actor['command_options']['attack']['target_ids']
        assert 202 in actor['command_options']['attack']['target_ids']
        invalid = Command('attack', (101,), target_id=201)
        repaired = Command('attack', (101,), target_id=202)
        error = 'capability_unavailable'
    else:
        anchor = request.observation['systems'][0]['navigation_anchor']
        assert anchor['position_is_move_endpoint'] is False
        assert anchor['collision_radius'] > 0
        invalid = Command('move', (101,), system_name='Sol', hex_coord=(0, 0), position=tuple(anchor['position']))
        repaired = Command('move', (101,), system_name='Sol', hex_coord=(0, 0), position=(2500, 0))
        error = 'invalid_destination'
    rejected = validate(plan(Command('rename_unit', (101,), new_name='Must not apply'), invalid))
    assert not rejected.accepted and rejected.applied_count == 0
    assert rejected.errors[0].code == error
    provider = FakePlanningProvider([plan(invalid), plan(repaired)])
    async def run():
        try:
            return await compare_gateway_reasoning_efforts(provider, [case], efforts=('medium',))
        finally:
            await provider.aclose()
    score = asyncio.run(run())['medium'].scores[0]
    assert score.accepted and score.attempts == 2 and score.retries_used == 1
    assert provider.requests[1].repair_context.errors[0].code == error


class ObservedMistakeProvider(FakePlanningProvider):
    """Replay the actual mistake categories, then use the repair's current options."""
    async def plan_turn(self, request, config):
        if request.repair_context is None:
            if 'required' in request.agent_id:
                self.requests.append(request)
                raise PlanningOutputError('invalid_contract', 'set_wing_production requires slot_index.',
                    provider='fake', model=config.model, reasoning_effort=config.reasoning_effort)
            if any(unit['id'] == 103 for unit in request.observation['units']):
                self._plans.append(plan(Command('use_ability', (103,), ability='siege_lance', target_id=201)))
            else:
                self._plans.append(plan(*(Command('set_wing_production', (101,), slot_index=i, template_name='BOMBER_WING')
                                          for i in range(4, 8))))
        else:
            self._plans.append(plan(Command('set_wing_production', (101,), slot_index=0, template_name='BOMBER_WING')))
        return await super().plan_turn(request, config)


@pytest.mark.parametrize('index', [0, 1, 2])
def test_observed_errors_repair_with_real_gateway_fixtures(index):
    case = playtest_gateway_cases()[index]
    # Give the invalid-output provider a stable signal without changing fixture state.
    if index == 1:
        from dataclasses import replace
        build = case.build
        def with_missing_field():
            request, validate = build()
            return replace(request, agent_id='required-slot-index'), validate
        case = replace(case, build=with_missing_field)
    provider = ObservedMistakeProvider([])
    async def run():
        try:
            return await compare_gateway_reasoning_efforts(provider, [case], efforts=('low',))
        finally:
            await provider.aclose()
    score = asyncio.run(run())['low'].scores[0]
    assert score.accepted and score.attempts == 2 and score.retries_used == 1
    assert provider.requests[1].repair_context.errors
    if index == 0:
        assert len(provider.requests[1].repair_context.errors) == 4
        assert all(error.code == 'invalid_parameters' for error in provider.requests[1].repair_context.errors)
    elif index == 1:
        assert provider.requests[1].repair_context.errors[0].code == 'invalid_contract'
    else:
        assert provider.requests[1].repair_context.errors[0].code == 'out_of_range'


def test_generic_paraphrases_do_not_evict_precise_carrier_and_field_constraints():
    memory = AgentMemory(lessons=['Carrier 69 has four slots indexed 0–3.',
                                 'set_wing_production requires explicit slot_index.'])
    generic = ['Preserve useful ongoing orders.', 'Keep active missions.', 'Avoid replacing useful work.',
               '[preserve_work] Retain ongoing orders.', 'Use currently visible legal targets.',
               'Only select targets listed in the current observation.', 'Use disclosed legal target IDs.',
               'Only attack visible targets.', 'Preserve useful mine orders.']
    for turn in range(1, 105):
        memory.apply_patch({'lessons': [generic[turn % len(generic)]]}, turn=turn)
    assert len(memory.lessons) == 4
    assert memory.lessons[:2] == ['Carrier 69 has four slots indexed 0–3.', 'set_wing_production requires explicit slot_index.']
    restored = AgentMemory.from_dict(memory.to_dict())
    assert restored.lessons == memory.lessons
    restored.apply_patch({'lessons': ['[set_wing_production/slot_index/unit-69] Use indices [0,1,2,3].',
                                      '[set_wing_production/slot_index/unit-69] Recheck current editable indices [0,2,3].']}, turn=105)
    assert sum('slot_index/unit-69' in text for text in restored.lessons) == 1
    assert restored.lessons[-1].endswith('[0,2,3].')


def test_repair_constraints_are_saved_only_after_successful_commit():
    rejected = plan(Command('set_wing_production', (69,), slot_index=4, template_name='BOMBER_WING'),
                    patch={'lessons': ['Rejected plan lesson must not persist.']})
    observation = {'units': [{'id': 69, 'command_options': {'set_wing_production': {'slot_indices': [0, 1, 2, 3]}}}]}
    issues = (RepairIssue(0, 'invalid_parameters', 'Slot index is out of bounds.'),)
    precise = rejection_lessons(rejected, issues, observation)
    assert 'slot_indices [0, 1, 2, 3]' in precise[0]
    player = SimpleNamespace(id=1, name='AI', agent_id='agent', controller=PlayerController.OPENAI, ai_memory={}, ai_repair_retries=2)
    game = SimpleNamespace(current_player=player, players=[player], game_started=True,
        campaign_id='repair-memory', turn_number=3, gui=None, end_turn=Mock())
    coordinator = AgentTurnCoordinator(game, provider=FakePlanningProvider([rejected, plan()]))
    from game_ai.commands import CommandError, CommandResult
    with patch('game_ai.coordinator.build_observation', return_value=observation), \
         patch('game_ai.coordinator.CommandGateway') as gateway, \
         patch.object(coordinator, '_write_memory'), patch.object(coordinator, '_record_telemetry'):
        gateway.return_value.apply_batch.side_effect = [CommandResult(False, errors=(CommandError(0, 'invalid_parameters', issues[0].message),)), CommandResult(True)]
        try:
            assert coordinator.start_current_turn()
            coordinator._future.result(timeout=2)
            coordinator.update()
            assert player.ai_memory == {}
            coordinator._future.result(timeout=2)
            coordinator.update()
            assert player.ai_memory['lessons'] == precise
            game.end_turn.assert_called_once()
        finally:
            coordinator.shutdown()
