"""Turn windows, authoritative events, disclosure, retention and persistence."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from campaign_persistence import prepare_campaign
from domain.players import Player
from game_ai.commands import CommandGateway
from game_ai.contracts import Command, CommandBatch
from game_ai.observation import build_observation
from geometry import Position
from save_manager import serialize_game_state, deserialize_game_state
from tests.support.campaigns import campaign, ship
from turn_briefing import (
    MAX_CHARACTERS, MAX_ENTRIES, begin_window, finish_window, initialize_campaign,
    record, refresh_discoveries, state_from_dict, summary_view, unit_event,
)
from turn_processor import TurnProcessor


def setup(count=2):
    game = campaign()
    game.turn_number = 1
    game.galaxy.game = game
    for i in range(2, count):
        game.players.append(Player(f"Player {i}", (10, 20, 30)))
    return game


@pytest.mark.parametrize("count", [2, 6])
def test_window_starts_before_resolution_and_wraps_round(count, monkeypatch):
    game = setup(count)
    initialize_campaign(game)
    owner = game.players[0]
    record(game, owner, "problem", "already seen while planning")
    processor = TurnProcessor(game)
    def resolve(player):
        if player is owner:
            record(game, player, "problem", "own resolution")
            player.credits += 20
        else:
            record(game, owner, "communications", "incoming", name=player.name)
    monkeypatch.setattr(processor, "process_player_turn", resolve)
    for _ in range(count):
        processor.end_turn()
    report = summary_view(owner)
    assert (report["from_turn"], report["to_turn"]) == (1, 2)
    assert len(report["entries"]) == count
    assert report["economy"]["credits"] == 20
    assert "already seen" not in json.dumps(report)
    assert not owner.briefing.collecting
    record(game, owner, "problem", "new planning phase")
    assert summary_view(owner) == report


def test_first_turn_seeds_starters_but_waiting_players_receive_events():
    game = setup()
    ship(game, owner=0)
    target = ship(game, owner=1)
    initialize_campaign(game)
    assert not game.players[0].briefing.current.entries
    assert not game.players[1].briefing.pending
    target.take_damage(3)
    finish_window(game, game.players[1])
    assert game.players[1].briefing.current.from_turn == 0
    assert any(e.amount == 3 for e in game.players[1].briefing.current.entries)


def test_real_new_game_turn_handoff_and_save_load(game_factory, tmp_path):
    from game_settings import GameSettings
    game = game_factory()
    assert game.start_new_game(GameSettings())
    assert not game.current_player.briefing.current.entries
    old_owner = game.current_player
    game.end_turn()
    assert game.current_player is not old_owner
    path = tmp_path / "campaign.json"
    path.write_text(json.dumps(serialize_game_state(game)))
    assert game.load_game(str(path))
    assert game.current_player.briefing.initialized


def test_damage_is_aggregated_even_after_repair_and_zero_damage_is_ignored():
    game = setup()
    unit = ship(game)
    initialize_campaign(game)
    begin_window(game, unit.owner)
    unit.take_damage(3)
    unit.take_damage(4)
    unit.take_damage(0)
    unit.heal_hull(7)
    finish_window(game, unit.owner)
    events = unit.owner.briefing.current.entries
    assert len(events) == 1
    assert (events[0].count, events[0].amount) == (2, 7)


def test_loss_survives_destruction_and_order_cancellation_is_not_duplicated():
    from unit_orders.movement import MoveOrder
    game = setup()
    unit = ship(game, name="Lost ship")
    order = MoveOrder(unit, {"destination_position": Position(200, 0)})
    order._journal_root = True
    order._issuing_player = unit.owner
    unit.commander_component.orders_queue.append(order)
    initialize_campaign(game)
    begin_window(game, unit.owner)
    unit.destroy()
    unit.destroy()
    finish_window(game, unit.owner)
    assert [(e.category, e.name) for e in unit.owner.briefing.current.entries] == [("loss", "Lost ship")]


def test_capture_and_carrier_cargo_losses_and_temporary_expiry():
    from unit_components.abilities.capture_unit import CaptureUnitAbility
    from unit_components.marines import MarinesComponent
    from unit_components.strikecraft import StrikecraftBayComponent
    game = setup()
    carrier = ship(game)
    bay = StrikecraftBayComponent(carrier, max_slots=2)
    carrier.add_component(bay)
    bay.slots[0]['production_template_name'] = "FIGHTER_WING"
    bay.construction_slot_index = 0
    bay.finish_auto_construction(game.galaxy)
    wing = bay.docked_units[0]
    captor = ship(game, owner=1)
    captor.add_component(MarinesComponent(captor, marines_count=1000))
    target = ship(game, name="Prize")
    temporary = ship(game, name="Expired platform")
    temporary.lifetime = 0
    initialize_campaign(game)
    begin_window(game, carrier.owner)
    assert CaptureUnitAbility().on_activate(SimpleNamespace(unit=captor), game.galaxy, target_unit_id=target.id)
    carrier.destroy()
    temporary.destroy()
    finish_window(game, game.players[0])
    events = game.players[0].briefing.current.entries
    assert any(e.category == "capture" and e.subject_id == target.id for e in events)
    losses = {e.subject_id for e in events if e.category == "loss"}
    assert losses == {carrier.id, wing.id}


def test_shared_tactical_events_but_private_production():
    game = setup(3)
    game.players[2].team_id = game.players[0].team_id
    unit = ship(game)
    initialize_campaign(game)
    begin_window(game, unit.owner)
    unit.take_damage(5)
    unit_event(unit, "development", "Construction completed", private=True)
    assert any(e.category == "combat" for e in game.players[2].briefing.pending)
    assert not any(e.category == "development" for e in game.players[2].briefing.pending)
    assert not game.players[1].briefing.pending  # No sensors for this observer.


def test_hidden_attacker_and_covert_equipment_do_not_leak():
    from tactical_abilities import combat_hit
    from unit_components.intelligence import IntelligenceComponent
    game = setup()
    own = ship(game, name="Defender")
    hidden = ship(game, name="SECRET", owner=1)
    hidden.position = Position(4500, 0)
    initialize_campaign(game)
    begin_window(game, own.owner)
    combat_hit(own, 4, attacker=hidden)
    assert "SECRET" not in json.dumps([e.__dict__ for e in own.owner.briefing.pending])
    assert any("unknown attacker" in e.detail for e in own.owner.briefing.pending)
    hidden.position = own.position
    hidden.add_component(IntelligenceComponent(hidden))
    refresh_discoveries(game)
    before = len(own.owner.briefing.pending)
    hidden.take_component_damage(IntelligenceComponent, 999)
    assert len(own.owner.briefing.pending) == before


def test_anonymous_presence_has_no_identity_and_vanishing_is_not_a_loss():
    game = setup()
    observer = ship(game)
    observer.sensors_component.short_range_radius = 1
    observer.sensors_component.long_range_hexes = 2
    initialize_campaign(game)
    begin_window(game, observer.owner)
    enemy = ship(game, name="Secret", owner=1, sector=(1, 0))
    refresh_discoveries(game)
    presence = next(e for e in observer.owner.briefing.pending if "radar" in e.detail)
    assert presence.subject_id is None and presence.name == "" and presence.count == 1
    enemy.is_hidden_in_gas_giant = True
    refresh_discoveries(game)
    assert not any(e.category == "loss" for e in observer.owner.briefing.pending)
    assert "Secret" not in json.dumps(summary_view(observer.owner))


def test_intelligence_discovery_is_shared_but_not_sent_to_infiltrator():
    from unit_components.intelligence import Agent
    game = setup(3)
    game.players[2].team_id = game.players[0].team_id
    host = ship(game)
    spy = Agent(game.players[1], source_unit_id=999, target_type="UNIT", target_id=host.id)
    host.infiltrating_agents.append(spy)
    initialize_campaign(game)
    begin_window(game, host.owner)
    spy.is_discovered = True
    refresh_discoveries(game)
    assert any(e.category == "intelligence" for e in host.owner.briefing.pending)
    assert any(e.category == "intelligence" for e in game.players[2].briefing.pending)
    assert not any(e.category == "intelligence" for e in game.players[1].briefing.pending)
    assert "999" not in json.dumps([e.__dict__ for e in host.owner.briefing.pending])


def test_failed_order_is_recorded_directly_without_historical_target_data():
    from unit_orders.movement import MoveOrder
    from order_history import record_outcome
    game = setup()
    unit = ship(game)
    initialize_campaign(game)
    begin_window(game, unit.owner)
    order = MoveOrder(unit, {"target_name": "secret", "target_id": 9000})
    order._journal_root = True
    order._issuing_player = unit.owner
    record_outcome(order, "failed", "path_unavailable")
    record_outcome(order, "failed", "path_unavailable")
    assert len(unit.owner.briefing.pending) == 1
    assert "secret" not in unit.owner.briefing.pending[0].detail
    assert "path unavailable" in unit.owner.briefing.pending[0].detail


def test_production_colony_and_mines_record_authoritative_results():
    from domain.celestials import Planet
    from domain.minefields import Minefield
    from constants import PlanetType
    from unit_components.colony import ColonyComponent
    from unit_components.constructor import Constructor
    from unit_components.strikecraft import StrikecraftBayComponent
    game = setup()
    unit = ship(game)
    constructor = Constructor(unit)
    unit.add_component(constructor)
    colony = ColonyComponent(unit)
    unit.add_component(colony)
    colony.population_cargo = 10
    body = Planet((1, 0), "Sol", planet_type=PlanetType.TERRAN)
    game.galaxy.systems["Sol"].add_celestial_body(body)
    bay = StrikecraftBayComponent(unit, max_slots=2)
    unit.add_component(bay)
    bay.slots[0]['production_template_name'] = "FIGHTER_WING"
    initialize_campaign(game)
    begin_window(game, unit.owner)
    constructor.create_unit_from_template(game.galaxy, "SCOUT", unit.owner, "Sol", (0, 0), Position(1000, 0))
    bay.construction_slot_index = 0
    bay.finish_auto_construction(game.galaxy)
    assert colony.unload_population(body, 10)
    details = [e.detail for e in unit.owner.briefing.pending]
    assert "Construction completed" in details
    assert "Wing construction completed" in details
    assert "Colony established" in details
    mine = Minefield(game.players[1], Position(100, 0), (0, 0), "Sol")
    mine.detonate_against(unit)
    assert any(e.category == "hazard" for e in unit.owner.briefing.pending)


def test_retention_prioritizes_loss_and_counts_omissions():
    game = setup()
    initialize_campaign(game)
    player = game.players[0]
    begin_window(game, player)
    record(game, player, "loss", "Destroyed", subject_id=1)
    for i in range(200):
        record(game, player, "discovery", "x" * 500, subject_id=i + 2)
    finish_window(game, player)
    report = summary_view(player)
    assert report["entries"][0]["category"] == "loss"
    assert len(report["entries"]) <= MAX_ENTRIES
    assert len(json.dumps(report, ensure_ascii=False)) <= MAX_CHARACTERS
    assert len(report["entries"]) + report["omitted_count"] == 201


@pytest.mark.parametrize("acknowledged", [True, False])
def test_save_round_trip_keeps_frozen_and_pending_reports(acknowledged):
    game = setup()
    unit = ship(game)
    initialize_campaign(game)
    begin_window(game, unit.owner)
    unit.take_damage(2)
    finish_window(game, unit.owner)
    unit.owner.briefing.acknowledged = acknowledged
    record(game, game.players[1], "problem", "Pending next turn")
    before = [p.briefing.to_dict() for p in game.players]
    restored = prepare_campaign(serialize_game_state(game)).state
    assert [p.briefing.to_dict() for p in restored.players] == before


@pytest.mark.parametrize("mutation", [
    lambda b: b.update(sequence=True),
    lambda b: b.update(acknowledged="yes"),
    lambda b: b["baseline"].update(credits=float("nan")),
    lambda b: b["current"].update(from_turn=100),
    lambda b: b["current"].update(omitted_count=-1),
    lambda b: b.update(seen={"hidden": []}),
])
def test_invalid_briefing_rejects_transactionally(mutation):
    game = setup()
    initialize_campaign(game)
    data = serialize_game_state(game)
    original_players = game.players
    mutation(data["players"][0]["briefing"])
    assert not deserialize_game_state(game, data)
    assert game.players is original_players


def test_observations_and_rejected_preflight_do_not_consume_or_create_reports():
    game = setup()
    unit = ship(game)
    initialize_campaign(game)
    begin_window(game, unit.owner)
    record(game, unit.owner, "problem", "Existing issue")
    finish_window(game, unit.owner)
    state = deepcopy(unit.owner.briefing.to_dict())
    first = build_observation(game, unit.owner)
    first["turn_summary"]["entries"].clear()
    second = build_observation(game, unit.owner)
    assert second["turn_summary"]["entries"]
    result = CommandGateway(game).apply_batch(unit.owner, CommandBatch((Command(type="attack", unit_ids=(unit.id,), target_id=999),)))
    assert not result.accepted
    assert unit.owner.briefing.to_dict() == state
    assert state_from_dict(state).to_dict() == state


def test_revealed_mines_and_disabled_operations_are_reported():
    from domain.minefields import Minefield
    game = setup()
    unit = ship(game)
    field = Minefield(game.players[1], Position(100, 0), (0, 0), "Sol")
    game.galaxy.systems["Sol"].hexes[(0, 0)].minefields.append(field)
    initialize_campaign(game)
    begin_window(game, unit.owner)
    field.reveal_to(unit.owner)
    unit.is_disabled = True
    TurnProcessor(game)._process_movement(unit.owner)
    refresh_discoveries(game)
    assert any(e.category == "problem" for e in unit.owner.briefing.pending)
    assert any(e.subject_id == field.id and e.category == "discovery" for e in unit.owner.briefing.pending)


def test_refit_success_has_one_personal_completion():
    from unit_components.constructor import Constructor
    game = setup()
    builder, target = ship(game), ship(game, name="Refit target")
    target.antimatter_component.max_capacity = 200
    constructor = Constructor(builder)
    builder.add_component(constructor)
    initialize_campaign(game)
    begin_window(game, builder.owner)
    assert constructor.start_refit(target, "ADD", "Engines", {"speed": 100})
    constructor.finish_refit(game.galaxy)
    constructor.finish_refit(game.galaxy)
    assert target.engines_component is not None
    assert len([e for e in builder.owner.briefing.pending if e.detail == "Refit completed"]) == 1


def test_deployable_damage_and_destruction_are_visible_but_cleanup_is_not_a_loss():
    from domain.deployables import Deployable
    game = setup()
    owner = game.players[0]
    ship(game)
    sector = game.galaxy.systems["Sol"].hexes[(0, 0)]
    cache = Deployable(owner, Position(100, 0), (0, 0), "Sol", "ghost_fleet", 900, game.galaxy)
    recovered = Deployable(owner, Position(200, 0), (0, 0), "Sol", "ghost_fleet", 900, game.galaxy)
    sector.deployables.extend([cache, recovered])
    initialize_campaign(game)
    begin_window(game, owner)
    cache.take_damage(999, cause="plasma")
    recovered.destroy(reason="cleanup")
    assert any(e.category == "hazard" and e.subject_id == cache.id for e in owner.briefing.pending)
    assert [e.subject_id for e in owner.briefing.pending if e.category == "loss"] == [cache.id]


@pytest.mark.parametrize("field,value", [("event_id", 900), ("category", []), ("hex_coord", [True, 0]), ("amount", -1), ("turn", 999)])
def test_invalid_event_payload_is_rejected(field, value):
    game = setup()
    initialize_campaign(game)
    player = game.players[0]
    begin_window(game, player)
    record(game, player, "problem", "Existing issue")
    finish_window(game, player)
    raw = player.briefing.to_dict()
    raw["current"]["entries"][0][field] = value
    with pytest.raises(ValueError):
        state_from_dict(raw)
