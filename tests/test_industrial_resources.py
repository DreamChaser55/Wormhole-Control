"""Industrial resources across prices, commands, production and saved settlement."""
from copy import deepcopy
from dataclasses import replace
import math

import pytest

from campaign_graph import find_unit
from constants import HullSize, PlanetType
from construction_customization import customize_template
from domain.celestials import Moon, Planet, MetalAsteroid, Comet
from game_ai.commands import resource_budget_view
from game_ai.contracts import Command
from game_ai.observation import build_observation
from geometry import Position
from resource_costs import ResourceCost, construction_cost, installation_cost, template_cost, resource_balances
from save_manager import serialize_game_state, deserialize_game_state
from tests.support.campaigns import campaign, ship
from tests.support.commands import issue
from unit_components.constructor import Constructor, instantiate_component_for_unit
from unit_components.mining import MiningComponent, MetalRefineryComponent, CrystalRefineryComponent
from unit_components.movement import Engines
from unit_components.strikecraft import StrikecraftBayComponent
from unit_orders.mining import UnloadResourcesOrder
from unit_orders.refit import RefitOrder
from unit_templates import UNIT_TEMPLATES


def builder(game):
    unit = ship(game)
    unit.add_component(Constructor(unit))
    unit.add_component(Engines(unit, speed=100))
    return unit


def build(unit, *, position=(100, 0), queue=False):
    return Command('construct', (unit.id,), template_name='SHIPYARD_MK1',
                   system_name='Sol', hex_coord=(0, 0), position=position, queue=queue)


def fund(player, cost):
    for name, value in cost.to_dict().items():
        setattr(player, name, value)


@pytest.mark.parametrize('name,expected', [
    ('Small Mining Ship', (946, 36, 12)), ('Metal Refinery Station', (1460, 57, 16)),
    ('Crystal Refinery Station', (1460, 57, 16)), ('Kinetic Frigate', (1865, 71, 23)),
    ('Battleship', (7518, 284, 92)), ('Fighter Wing', (260, 11, 4)),
])
def test_catalogue_prices(name, expected):
    raw = next(t for t in UNIT_TEMPLATES.values() if t['name'] == name)
    assert template_cost(raw) == ResourceCost(*expected)


@pytest.mark.parametrize('hull', list(HullSize))
def test_hull_and_fractional_equipment_pricing(hull):
    base = construction_cost(hull, 0, 123)
    fitted = construction_cost(hull, 2.01, 456)
    assert fitted.credits == 456
    assert fitted.metal > base.metal
    assert base.crystal == 0 and fitted.crystal == 2
    assert installation_cost(2.01, 77) == ResourceCost(77, 3, 2)


def test_overrides_preserve_all_prices_and_time():
    raw = next(t for t in UNIT_TEMPLATES.values() if t['name'] == 'Kinetic Frigate')
    changed = customize_template(raw, 'beam', 'shields')
    assert template_cost(changed) == template_cost(raw)
    assert changed['build_time'] == raw['build_time']


@pytest.mark.parametrize('bad', [-1, math.nan, math.inf, True, '4'])
def test_resource_bundle_rejects_invalid_amounts(bad):
    with pytest.raises(ValueError):
        ResourceCost(metal=bad)


@pytest.mark.parametrize('resource', ['credits', 'metal', 'crystal'])
def test_shortage_rejects_entire_batch_without_charging_or_replacing(resource):
    game = campaign()
    actor, other = builder(game), builder(game)
    player = actor.owner
    cost = template_cost(UNIT_TEMPLATES['SHIPYARD_MK1'])
    fund(player, cost)
    setattr(player, resource, getattr(player, resource) - 0.25)
    before = resource_balances(player)
    result = issue(game, player, Command('rename_unit', (other.id,), new_name='Changed'), build(actor))
    assert not result.accepted and result.failure_stage == 'preflight'
    assert result.errors[0].code == 'insufficient_resources'
    assert resource in result.errors[0].message
    assert other.name == 'ship' and actor.commander_component.current_order is None
    assert resource_balances(player) == before
    assert not cost.pay(player)
    assert resource_balances(player) == before


def test_exact_payment_and_saved_refund_once_to_original_payer():
    game = campaign()
    actor = builder(game)
    cost = template_cost(UNIT_TEMPLATES['SHIPYARD_MK1'])
    fund(actor.owner, cost)
    assert issue(game, actor.owner, build(actor)).accepted
    assert resource_balances(actor.owner) == ResourceCost().to_dict()
    assert resource_budget_view(game, actor.owner)['reserved'] == ResourceCost().to_dict()
    saved = serialize_game_state(game)
    assert deserialize_game_state(game, saved)
    actor = find_unit(game.galaxy, actor.id)
    payer, new_owner = game.players
    before_other = resource_balances(new_owner)
    order = actor.commander_component.current_order
    actor.owner = new_owner
    order.cancel()
    order.cancel()
    assert resource_balances(payer) == cost.to_dict()
    assert resource_balances(new_owner) == before_other


def test_approaching_and_queued_construction_reserve_all_resources():
    game = campaign()
    first, second = builder(game), builder(game)
    cost = template_cost(UNIT_TEMPLATES['SHIPYARD_MK1'])
    fund(first.owner, cost.scaled(2))
    assert issue(game, first.owner, build(first, position=(1500, 0)), build(first, queue=True)).accepted
    before = resource_balances(first.owner)
    budget = resource_budget_view(game, first.owner)
    assert budget['reserved'] == cost.scaled(2).to_dict()
    assert budget['available'] == ResourceCost().to_dict()
    assert not first.constructor_component.current_construction_target
    assert not issue(game, first.owner, build(second)).accepted
    assert resource_balances(first.owner) == before
    # Replacing an unpaid approach releases both promises but refunds no money.
    assert issue(game, first.owner, build(first)).accepted
    assert resource_balances(first.owner) == cost.to_dict()


def test_grouped_build_minerals_are_multiplied_and_rejection_preserves_work():
    game = campaign()
    first, second = builder(game), builder(game)
    cost = template_cost(UNIT_TEMPLATES['SHIPYARD_MK1'])
    fund(first.owner, cost.scaled(2))
    first.owner.metal -= 1
    before = resource_balances(first.owner)
    assert not issue(game, first.owner, replace(build(first), unit_ids=(first.id, second.id))).accepted
    assert resource_balances(first.owner) == before
    assert all(u.commander_component.current_order is None for u in (first, second))


def test_cancellation_refund_can_fund_later_build_in_same_batch():
    game = campaign()
    first, second = builder(game), builder(game)
    cost = template_cost(UNIT_TEMPLATES['SHIPYARD_MK1'])
    fund(first.owner, cost)
    assert issue(game, first.owner, build(first)).accepted
    result = issue(game, first.owner, Command('cancel_orders', (first.id,)), build(second))
    assert result.accepted
    assert resource_balances(first.owner) == ResourceCost().to_dict()
    assert second.constructor_component.current_construction_target


def test_fortification_competes_with_reserved_minerals():
    game = campaign()
    actor = builder(game)
    body = Moon((1, 0), 'Sol')
    body.owner, body.population = actor.owner, 50
    game.galaxy.systems['Sol'].add_celestial_body(body)
    cost = template_cost(UNIT_TEMPLATES['SHIPYARD_MK1'])
    fund(actor.owner, cost + ResourceCost(250, 24, 5))
    upgrade = Command('upgrade_planetary_defenses', target_id=body.id)
    before = resource_balances(actor.owner)
    assert not issue(game, actor.owner, build(actor, position=(1500, 0)), upgrade).accepted
    assert resource_balances(actor.owner) == before and body.fortification_level == 0
    actor.owner.metal += 1
    assert issue(game, actor.owner, build(actor, position=(1500, 0)), upgrade).accepted
    assert resource_balances(actor.owner) == cost.to_dict()
    assert body.fortification_level == 1


@pytest.mark.parametrize('action', ['ADD', 'REMOVE'])
def test_refit_round_trip_and_material_settlement(action):
    from refit_validation import evaluate_refit
    game = campaign()
    actor, target = builder(game), ship(game)
    target.antimatter_component.max_capacity = target.antimatter_component.current_amount = 200
    configuration = {'speed': 73.5}
    if action == 'REMOVE':
        target.add_component(instantiate_component_for_unit('Engines', target, configuration))
    preview = evaluate_refit(target, action, 'Engines', configuration if action == 'ADD' else None)
    assert not preview.errors
    before = resource_balances(actor.owner)
    order = RefitOrder(actor, dict(target_unit_id=target.id, action=action, component_type='Engines',
                                  component_config=configuration if action == 'ADD' else None))
    actor.commander_component.add_order(order)
    charged = resource_balances(actor.owner)
    assert charged == {k: before[k] - preview.resource_cost.to_dict()[k] for k in before}
    assert deserialize_game_state(game, serialize_game_state(game))
    actor = find_unit(game.galaxy, actor.id)
    assert resource_balances(actor.owner) == charged
    actor.constructor_component.finish_refit(game.galaxy)
    expected = {k: charged[k] + preview.resource_salvage.to_dict()[k] for k in before}
    assert resource_balances(actor.owner) == expected
    actor.constructor_component.finish_refit(game.galaxy)
    assert resource_balances(actor.owner) == expected


def test_saved_dismantling_uses_frozen_prices_and_completion_damage():
    from dismantling import process
    game = campaign()
    actor, target = builder(game), ship(game, hull=HullSize.SMALL)
    assert issue(game, actor.owner, Command('dismantle_unit', (actor.id,), target_id=target.id)).accepted
    order = actor.commander_component.current_order
    frozen = ResourceCost.from_dict(order.members[0]['resource_cost'])
    assert deserialize_game_state(game, serialize_game_state(game))
    actor, target = find_unit(game.galaxy, actor.id), find_unit(game.galaxy, target.id)
    before = resource_balances(actor.owner)
    target.current_hit_points = 17
    expected = frozen.scaled(0.5 * 17 / target.max_hit_points)
    order = actor.commander_component.current_order
    for _ in range(order.duration + 2):
        game.turn_number += 1
        process(game, actor.owner)
    assert find_unit(game.galaxy, target.id) is None
    assert resource_balances(actor.owner) == pytest.approx({k: before[k] + expected.to_dict()[k] for k in before})
    order.cancel()
    order.advance(game.galaxy, game.turn_number + 1)
    assert resource_balances(actor.owner) == pytest.approx({k: before[k] + expected.to_dict()[k] for k in before})


@pytest.mark.parametrize('resource', ['metal', 'crystal'])
def test_saved_malformed_charges_reject_without_touching_live_game(resource):
    game = campaign()
    actor = builder(game)
    assert issue(game, actor.owner, build(actor)).accepted
    saved = serialize_game_state(game)
    def corrupt(value):
        if isinstance(value, dict):
            if 'charged_' + resource in value:
                value['charged_' + resource] = -1
            for item in value.values():
                corrupt(item)
        elif isinstance(value, list):
            for item in value:
                corrupt(item)
    corrupt(saved)
    before = resource_balances(actor.owner)
    galaxy = game.galaxy
    assert not deserialize_game_state(game, saved)
    assert game.galaxy is galaxy and resource_balances(actor.owner) == before


def test_wing_worker_skips_unaffordable_slot_and_paid_work_finishes_paused(monkeypatch):
    game = campaign()
    carrier = ship(game)
    bay = StrikecraftBayComponent(carrier, max_slots=2)
    carrier.add_component(bay)
    expensive = deepcopy(UNIT_TEMPLATES['BOMBER_WING'])
    expensive.update(engine_speed=1000)  # Derived material price increases, not its credit hint.
    monkeypatch.setitem(UNIT_TEMPLATES, 'BOMBER_WING', expensive)
    assert bay.set_production(0, 'BOMBER_WING') and bay.set_production(1, 'FIGHTER_WING')
    cost = template_cost(UNIT_TEMPLATES['FIGHTER_WING'])
    fund(carrier.owner, ResourceCost(10000, cost.metal, cost.crystal))
    bay.update(game.galaxy)
    assert bay.construction_slot_index == 1
    after = resource_balances(carrier.owner)
    bay.production_enabled = False
    assert deserialize_game_state(game, serialize_game_state(game))
    carrier = find_unit(game.galaxy, carrier.id)
    bay = carrier.strikecraft_bay_component
    for _ in range(3):
        bay.update(game.galaxy)
    assert len(bay.docked_units) == 1 and not bay.constructing
    assert resource_balances(carrier.owner) == after
    # Replenishment still needs only credits, even at zero minerals.
    bay.docked_units[0].current_hit_points -= 10
    carrier.owner.metal = carrier.owner.crystal = 0
    credits = carrier.owner.credits
    bay.update(game.galaxy)
    bay.update(game.galaxy)
    assert carrier.owner.credits == credits - 35
    assert bay.docked_units[0].current_hit_points == bay.docked_units[0].max_hit_points


def test_mined_cargo_becomes_spendable_only_after_unloading():
    game = campaign()
    actor, miner, refinery = builder(game), ship(game), ship(game)
    mining = MiningComponent(miner, mining_rate=100, mining_range=500, max_cargo=200)
    miner.add_component(mining)
    refinery.add_component(MetalRefineryComponent(refinery))
    refinery.add_component(CrystalRefineryComponent(refinery))
    actor.owner.metal = actor.owner.crystal = 0
    for kind in (MetalAsteroid, Comet):
        body = kind((0, 0), 'Sol')
        body.position = Position(100, 0)
        mining.set_target(body)
        mining.update(game.galaxy)
    assert not issue(game, actor.owner, build(actor)).accepted
    miner.commander_component.add_order(UnloadResourcesOrder(miner, {'target_unit_id': refinery.id}))
    assert actor.owner.metal == actor.owner.crystal == 100
    assert mining.raw_metal_cargo == mining.raw_crystal_cargo == 0
    assert issue(game, actor.owner, build(actor)).accepted


def test_passive_minerals_fund_industry_and_observation_does_not_reveal_enemy_wallet():
    from turn_processor import TurnProcessor
    game = campaign()
    actor = builder(game)
    for kind in (PlanetType.FERROUS, PlanetType.GREENHOUSE):
        body = Planet((1, 0), 'Sol', kind)
        body.owner, body.population = actor.owner, 20
        game.galaxy.systems['Sol'].add_celestial_body(body)
    actor.owner.metal = actor.owner.crystal = 0
    for _ in range(5):
        TurnProcessor(game)._process_resource_generation(actor.owner)
    assert issue(game, actor.owner, build(actor)).accepted
    before = build_observation(game, actor.owner)
    game.players[1].metal = 98765
    game.players[1].crystal = 87654
    assert build_observation(game, actor.owner) == before
    assert before['active_player']['resources']['resource_budget']['reserved'] == ResourceCost().to_dict()


@pytest.mark.parametrize('shortage', ['metal', 'crystal'])
def test_refit_shortage_does_not_install_or_spend(shortage):
    game = campaign()
    actor, target = builder(game), ship(game)
    target.antimatter_component.max_capacity = 200
    setattr(actor.owner, shortage, 0)
    before = resource_balances(actor.owner)
    assert not actor.constructor_component.start_refit(target, 'ADD', 'Engines', {'speed': 100})
    assert target.engines_component is None
    assert actor.constructor_component.current_refit_target is None
    assert resource_balances(actor.owner) == before


@pytest.mark.parametrize('outcome', ['cancel', 'failure'])
def test_paid_installation_refunds_all_resources_once(outcome):
    game = campaign()
    actor, target = builder(game), ship(game)
    target.antimatter_component.max_capacity = 200
    before = resource_balances(actor.owner)
    order = RefitOrder(actor, dict(target_unit_id=target.id, action='ADD', component_type='Engines', component_config={'speed': 100}))
    actor.commander_component.add_order(order)
    assert resource_balances(actor.owner) != before
    if outcome == 'cancel':
        order.cancel()
    else:
        target.current_hit_points = 0
        actor.constructor_component.finish_refit(game.galaxy)
    assert resource_balances(actor.owner) == before
    actor.constructor_component.cancel_refit()
    order.cancel()
    assert resource_balances(actor.owner) == before


def test_dismantling_nested_craft_returns_materials_but_cancel_pays_nothing():
    from dismantling import process
    from unit_components.hangar import HangarComponent
    game = campaign()
    actor, carrier, tiny = builder(game), ship(game), ship(game, hull=HullSize.TINY)
    carrier.add_component(HangarComponent(carrier, max_slots=1))
    assert carrier.hangar_component.dock(tiny, game.galaxy)
    command = Command('dismantle_unit', (actor.id,), target_id=carrier.id)
    before = resource_balances(actor.owner)
    assert issue(game, actor.owner, command).accepted
    actor.commander_component.current_order.cancel()
    assert resource_balances(actor.owner) == before
    assert issue(game, actor.owner, command).accepted
    job = actor.commander_component.current_order
    expected = sum((ResourceCost.from_dict(m['resource_cost']).scaled(.5) for m in job.members), ResourceCost())
    assert len(job.members) == 2
    for _ in range(job.duration + 1):
        game.turn_number += 1
        process(game, actor.owner)
    assert resource_balances(actor.owner) == pytest.approx({k: before[k] + expected.to_dict()[k] for k in before})


def test_inconsistent_saved_refit_payment_is_transactionally_rejected():
    game = campaign()
    actor, target = builder(game), ship(game)
    target.antimatter_component.max_capacity = 200
    actor.commander_component.add_order(RefitOrder(actor, dict(
        target_unit_id=target.id, action='ADD', component_type='Engines', component_config={'speed': 100})))
    saved = serialize_game_state(game)
    def corrupt(value):
        if isinstance(value, dict):
            if 'resource_cost' in value and 'payer_id' in value:
                value['resource_cost']['metal'] += 1
            for item in value.values():
                corrupt(item)
        elif isinstance(value, list):
            for item in value:
                corrupt(item)
    corrupt(saved)
    before, galaxy = resource_balances(actor.owner), game.galaxy
    assert not deserialize_game_state(game, saved)
    assert game.galaxy is galaxy and resource_balances(actor.owner) == before


def test_observation_prices_match_human_budgets_and_distinguish_replacement():
    from game_ai.commands import construction_budget
    game = campaign()
    actor = builder(game)
    cost = template_cost(UNIT_TEMPLATES['SHIPYARD_MK1'])
    fund(actor.owner, cost)
    assert issue(game, actor.owner, build(actor)).accepted
    observed = build_observation(game, actor.owner)
    unit_view = next(u for u in observed['units'] if u['id'] == actor.id)
    options = unit_view['command_options']['construct']
    quote = next(q for q in options['prices'] if q['template_name'] == 'SHIPYARD_MK1')
    assert quote['resource_cost'] == cost.to_dict()
    for queue, field in [(False, 'replacement_shortfall'), (True, 'queued_shortfall')]:
        budget = construction_budget(game, actor.owner, [actor], queue=queue)
        assert quote[field] == cost.shortfall(budget).to_dict()
    assert quote['replacement_shortfall'] == ResourceCost().to_dict()
    assert quote['queued_shortfall'] == cost.to_dict()
    assert 'SHIPYARD_MK1' in options['template_names']
    entry = next(e for e in observed['action_catalogs']['construction_templates'] if e['template_name'] == 'SHIPYARD_MK1')
    assert entry['resource_cost'] == entry['resource_shortfall'] == cost.to_dict()


def test_custom_and_testing_prices_use_canonical_hull_usage(monkeypatch):
    from constants import HULL_CAPACITIES
    from custom_unit_templates import template_from_dict
    from unit_templates import PRIVATE_TEMPLATES, load_testing_templates
    game = campaign()
    actor = builder(game)
    custom = deepcopy(UNIT_TEMPLATES['SHIPYARD_MK1'])
    custom.update(name='Private industrial design', sensor_short_range=123.5)
    monkeypatch.setitem(PRIVATE_TEMPLATES, 'Industrial Custom', custom)
    for key, raw in {'Industrial Custom': custom, **load_testing_templates()}.items():
        normalized = dict(raw, hull_size=raw['hull_size'].name)
        design = template_from_dict(key, normalized)
        cost = template_cost(raw)
        assert cost.metal == math.ceil(HULL_CAPACITIES[design.hull_size] / 2 + design.total_hull_cost)
        assert cost.crystal == math.ceil(design.total_hull_cost / 2)
        assert cost.credits == raw['build_cost']
    assert actor.constructor_component.can_build('Industrial Custom').resource_cost == template_cost(custom)


def test_completed_construction_cannot_return_its_consumed_payment():
    game = campaign()
    actor = builder(game)
    cost = template_cost(UNIT_TEMPLATES['SHIPYARD_MK1'])
    fund(actor.owner, cost)
    assert issue(game, actor.owner, build(actor)).accepted
    order = actor.commander_component.current_order
    actor.constructor_component.finish_construction(game.galaxy)
    assert order.charged_resources == ResourceCost()
    order.refund_charge()
    order.cancel()
    assert resource_balances(actor.owner) == ResourceCost().to_dict()
