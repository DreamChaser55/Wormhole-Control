"""Independent state comparisons, registry coverage, and load failure isolation."""
from collections import deque
from copy import deepcopy
from dataclasses import fields as dataclass_fields
from enum import Enum
from types import SimpleNamespace
from unittest.mock import Mock
import json
import random

import pytest

from entities import Player, GameObject, Unit, Minefield, Planet
from galaxy import Galaxy, StarSystem, Hex
from geometry import Position, Vector
from constants import HullSize, PlanetType
from unit_components import (
    Agent, UnitComponent, Commander, Weapons, Turret, TurretType, TurretVariant,
    AbilityComponent, AbilityType, Engines, Sensors, HyperspaceInhibitionFieldEmitter,
    HangarComponent, StrikecraftBayComponent, StrikecraftWingComponent,
    IntelligenceComponent, MiningComponent, Constructor, RepairComponent,
)
from unit_components.abilities import AbilityInstance
from unit_components.abilities.registry import ABILITY_CLASSES
from unit_components.persistence import component_registry, restore_component
from unit_orders import MoveOrder, AttackOrder, Order, OrderStatus
from campaign_graph import iter_objects, iter_units, find_unit
from campaign_persistence import prepare_campaign, reconcile
from save_manager import serialize_game_state, deserialize_game_state, serialize_unit, deserialize_unit


@pytest.fixture(autouse=True)
def preserve_allocators():
    owners = ((GameObject, "object_counter"), (Player, "player_counter"), (Agent, "agent_counter"), (Order, "order_counter"))
    saved = [(cls, field, getattr(cls, field)) for cls, field in owners]
    rng = random.getstate()
    yield
    for cls, field, value in saved:
        setattr(cls, field, value)
    random.setstate(rng)


def campaign():
    galaxy = Galaxy.__new__(Galaxy)
    galaxy.systems, galaxy.wormholes, galaxy.system_graph = {}, {}, {}
    galaxy.generation_x_min = galaxy.generation_y_min = 0
    galaxy.generation_x_max = galaxy.generation_y_max = 1000
    for name in ("Sol", "Beta"):
        system = StarSystem.__new__(StarSystem)
        system.name, system.position, system.radius = name, Position(10, 20), 1
        system.hexes = {(0, 0): Hex(0, 0, name), (1, 0): Hex(1, 0, name)}
        system.celestial_bodies_by_id = {}
        system.in_galaxy = galaxy
        galaxy.systems[name] = system
    players = [Player("One", (0, 200, 0)), Player("Two", (200, 0, 0))]
    game = SimpleNamespace(galaxy=galaxy, players=players, turn_number=7, current_player_index=0,
        view_mode="sector", current_system_name="Sol", current_sector_coord=(0, 0),
        campaign_id="integrity", conversations={}, message_counter=40, game_started=True,
        selected_objects=[], hovered_object=None, deselect_object=lambda obj: None)
    return game


def ship(game, name="ship", owner=0, sector=(0, 0), system="Sol", hull=HullSize.HUGE):
    unit = Unit(game.players[owner], Position(100, 0), sector, system, name, hull, game)
    game.galaxy.systems[system].hexes[sector].units.append(unit)
    return unit


def value_snapshot(value):
    """Independent of to_state/STATE_FIELDS; new unclassified instance fields fail."""
    if isinstance(value, Enum):
        return (type(value).__name__, value.name)
    if isinstance(value, Vector):
        return (value.x, value.y)
    if isinstance(value, (GameObject, Player)):
        return (type(value).__name__, value.id)
    if isinstance(value, Order):
        # Runtime order IDs and stance descendants are intentionally transient.
        excluded = {"unit", "order_id", "parent_order", "_issuing_player", "_journal_root", "_legacy_charge"}
        return {k: value_snapshot(v) for k, v in vars(value).items() if k not in excluded}
    if isinstance(value, AbilityInstance):
        return {k: value_snapshot(v) for k, v in vars(value).items()}
    if hasattr(value, "__dataclass_fields__"):
        return {f.name: value_snapshot(getattr(value, f.name)) for f in dataclass_fields(value)
                if f.name not in ("parent_unit", "target", "target_component_type")}
    if isinstance(value, dict):
        return {k if isinstance(k, (str, int)) else repr(k): value_snapshot(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, deque)):
        return [value_snapshot(v) for v in value]
    if isinstance(value, set):
        return sorted(value_snapshot(v) for v in value)
    return value


def component_snapshot(component):
    # These are pointers/caches reconstructed from explicit orders and ownership.
    excluded = {"unit", "_saved_refs", "standing_order", "_restored_pending", "_deployed_agents",
                "move_target", "move_target_order_id", "hex_jump_target", "wormhole_jump_target", "jump_target_order_id"}
    data = {k: value_snapshot(v) for k, v in vars(component).items() if k not in excluded}
    if isinstance(component, Constructor):
        data["build_range"] = component.build_range  # class default is also mutable configuration
    return data


def canonical(game):
    objects = {}
    for obj, container in iter_objects(game.galaxy):
        excluded = {"game", "in_galaxy", "components", "infiltrating_agents", "_ability_effects", "_destroyed"}
        data = {k: value_snapshot(v) for k, v in vars(obj).items() if k not in excluded}
        if isinstance(obj, Unit):
            data["components"] = {cls.__name__: component_snapshot(c) for cls, c in obj.components.items()}
        data["agents"] = [{k: value_snapshot(v) for k, v in vars(a).items() if k not in ("attached_to", "_source_unit")} for a in obj.infiltrating_agents] if hasattr(obj, "infiltrating_agents") else []
        objects[obj.id] = data
    return {"objects": objects, "players": [value_snapshot(vars(p)) for p in game.players],
            "turn": game.turn_number, "player_index": game.current_player_index,
            "counters": (GameObject.object_counter, Player.player_counter, Agent.agent_counter, game.message_counter),
            "conversations": value_snapshot(game.conversations)}


def mutate(component, target):
    component.hull_cost = 9.25
    component.max_hit_points = 117
    component.current_hit_points = 3
    # Exercise every numeric and boolean instance field with a non-default value.
    excluded = {"hull_cost", "max_hit_points", "current_hit_points"}
    for name, val in list(vars(component).items()):
        if name in excluded:
            continue
        if type(val) is bool:
            setattr(component, name, not val)
        elif type(val) is int:
            setattr(component, name, val + 2)
        elif type(val) is float:
            setattr(component, name, val + 1.25)
    if isinstance(component, Weapons):
        component.turrets = [Turret(t, 17.5, 140.25, 3, component.unit, v, current_cooldown=2)
                             for t in TurretType for v in TurretVariant]
    if isinstance(component, AbilityComponent):
        component.abilities = {t: cls(cooldown_remaining=5, is_active=cls.DEFINITION.duration > 0,
            duration_remaining=2 if cls.DEFINITION.duration else 0, target_unit_id=target.id,
            target_position=Position(13.5, -10), spawned_unit_ids=[]) for t, cls in ABILITY_CLASSES.items()}
    if isinstance(component, (MiningComponent, RepairComponent)):
        # Type is validated in graph tests; component codec preserves the ID independently.
        setattr(component, "mining_target" if isinstance(component, MiningComponent) else "target", target)
    if isinstance(component, StrikecraftWingComponent):
        component.mother_carrier = target
    if isinstance(component, Constructor):
        component.build_range = 777.5
        component.current_construction_target = ("FIGHTER_WING", Position(5, 6))
        component.current_refit_target = {"target_unit_id": target.id, "action": "ADD", "component_type": "Engines",
            "component_config": {"speed": 73.5}, "cost_credits": 100, "time_to_build": 3}
        component.construction_order_id = "a" * 32
        component.refit_order_id = "b" * 32


def test_registry_covers_every_concrete_component_and_ability():
    assert set(component_registry().values()) == set(UnitComponent.__subclasses__())
    assert set(ABILITY_CLASSES) == set(AbilityType)
    for cls in component_registry().values():
        assert "STATE_CONFIG" in cls.__dict__
        assert "STATE_RUNTIME" in cls.__dict__


@pytest.mark.parametrize("name", sorted(component_registry()))
def test_every_component_round_trip_with_nondefault_state(name):
    game = campaign()
    unit, target = ship(game), ship(game, "target")
    component = component_registry()[name](unit)
    unit.add_component(component)
    mutate(component, target)
    state = json.loads(json.dumps(component.to_state()))
    restored = restore_component(state, unit, {p.id: p for p in game.players}, game)
    restored.resolve_state({target.id: target})
    if isinstance(restored, Commander):
        # There are no explicit orders in this component fixture.
        unit.__dict__.pop("_saved_commander_data", None)
    assert component_snapshot(restored) == component_snapshot(component)


@pytest.mark.parametrize("atype", list(ABILITY_CLASSES))
def test_every_ability_definition_and_runtime_round_trip(atype):
    instance = ABILITY_CLASSES[atype](cooldown_remaining=7, is_active=True, duration_remaining=2,
        target_unit_id=932, target_position=Position(13.5, -4.2), spawned_unit_ids=[77, 78])
    instance.definition = deepcopy(instance.definition)
    instance.definition.range += 19.5
    instance.definition.antimatter_cost += 3
    restored = AbilityInstance.from_state(json.loads(json.dumps(instance.to_state())))
    assert type(restored) is type(instance)
    assert value_snapshot(restored) == value_snapshot(instance)


def mutated_campaign():
    game = campaign()
    source, target = ship(game), ship(game, "target", owner=1)
    source.template_name = "A_TEMPLATE_THAT_NO_LONGER_EXISTS"
    for cls in (Engines, Weapons, Constructor, IntelligenceComponent):
        component = cls(source)
        source.add_component(component)
        mutate(component, target)
    source.constructor_component.current_refit_target = None
    source.constructor_component.current_construction_target = None
    source.constructor_component.construction_order_id = source.constructor_component.refit_order_id = None
    source.sensors_component.current_hit_points = 0
    source.add_component(AbilityComponent(source, [AbilityType.ION_BOLT, AbilityType.DESIGNATE_TARGET,
                                                  AbilityType.ADAPTIVE_FORCEFIELD, AbilityType.MISSILE_BATTERIES]))
    source.antimatter_component.current_amount = 200
    for atype in source.ability_component.abilities:
        assert source.ability_component.activate(atype, game.galaxy, target_unit_id=target.id)
    source.ability_component.abilities[AbilityType.ION_BOLT].duration_remaining = 1
    inhibitor = ship(game, "inhibitor", sector=(1, 0))
    inhibitor.add_component(HyperspaceInhibitionFieldEmitter(inhibitor, radius=123.5))
    assert inhibitor.inhibitor_component.set_active(True, game.galaxy).allowed
    carrier = ship(game, "carrier")
    carrier.add_component(HangarComponent(carrier, max_slots=8))
    carrier.add_component(StrikecraftBayComponent(carrier, max_slots=5))
    child = ship(game, "docked", hull=HullSize.TINY)
    assert carrier.hangar_component.dock(child, game.galaxy)
    child.add_component(HangarComponent(child, max_slots=2))
    nested = ship(game, "nested", hull=HullSize.TINY)
    assert child.hangar_component.dock(nested, game.galaxy)
    wing = ship(game, "wing")
    wing.add_component(StrikecraftWingComponent(wing))
    wing.strikecraft_wing_component.mother_carrier = carrier
    carrier.strikecraft_bay_component.launched_units.append(wing)
    giant = Planet((1, 0), "Beta", PlanetType.GAS_GIANT)
    game.galaxy.systems["Beta"].hexes[(1, 0)].celestial_bodies.append(giant)
    hidden = ship(game, "hidden", system="Beta", sector=(1, 0))
    game.galaxy.systems["Beta"].hexes[(1, 0)].units.remove(hidden)
    giant.hidden_units.append(hidden)
    hidden.is_hidden_in_gas_giant, hidden.hidden_in_gas_giant_id = True, giant.id
    agent = Agent(game.players[0], source.id, "UNIT", target.id)
    agent.attached_to, agent._source_unit = target, source
    target.infiltrating_agents.append(agent)
    source.intelligence_component._deployed_agents.append(agent)
    source.intelligence_component.agents_count -= 1
    minefield = Minefield(game.players[0], Position(0, 500), (1, 0), "Sol")
    minefield.id = GameObject.object_counter + 100
    GameObject.object_counter = minefield.id + 47
    minefield.revealed_to_player_ids.add(game.players[1].id)
    game.galaxy.systems["Sol"].hexes[(1, 0)].minefields.append(minefield)
    move = MoveOrder(child, {"destination_system_name": "Sol", "destination_hex_coord": (0, 0), "destination_position": Position(450, 70)})
    child.commander_component.orders_queue = deque([move])
    # A current order is intentionally used so load must not promote queued work.
    attack = AttackOrder(child, {"target_unit_id": target.id})
    child.commander_component.current_order = attack
    child.commander_component.current_hit_points = 1
    game.players[0].sector_intel[("Sol", (0, 0))] = 2
    Player.player_counter += 20
    Agent.agent_counter += 30
    return game


def test_mutated_campaign_canonical_round_trip_and_reconciliation(tmp_path):
    import save_manager
    game = mutated_campaign()
    before = canonical(game)
    path = tmp_path / "midgame.json"
    # Exercise the actual atomic writer and file reader, not just dict hydration.
    save_manager.save_game_to_file(game, str(path))
    restored = campaign()
    assert save_manager.load_game_from_file(restored, str(path))
    assert canonical(restored) == before
    prepared = prepare_campaign(json.loads(path.read_text()))
    snapshot = canonical(prepared.state)
    reconcile(prepared.state)
    assert canonical(prepared.state) == snapshot
    assert deserialize_game_state(restored, json.loads(json.dumps(serialize_game_state(restored))))
    assert canonical(restored) == before
    zone = restored.galaxy.systems["Sol"].hexes[(1, 0)].dynamic_inhibition_zones
    emitter = next(u for u, _ in iter_units(restored.galaxy) if u.name == "inhibitor")
    assert zone[emitter.id].radius == 123.5
    assert all(u.game is restored and u.in_galaxy is restored.galaxy for u, _ in iter_units(restored.galaxy))
    assert GameObject.object_counter > max(o.id for o, _ in iter_objects(restored.galaxy))
    assert ship(restored).id == before["counters"][0]


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(version="99.0"),
    lambda d: d["game_state"].update(current_player_index=999),
    lambda d: d["game_state"].update(object_counter=-1),
    lambda d: d["players"].append(deepcopy(d["players"][0])),
    lambda d: d["galaxy"]["systems"][0]["hexes"][0]["units"][0]["components"]["Commander"].update(schema_version=999),
    lambda d: d["galaxy"]["systems"][0]["hexes"][0]["units"][0].update(position=[float("nan"), 0]),
    lambda d: d["galaxy"]["systems"][0]["hexes"][0]["units"].append(deepcopy(d["galaxy"]["systems"][0]["hexes"][0]["units"][0])),
    lambda d: d["galaxy"]["systems"][0]["hexes"][0]["units"][0].update(owner_id=999999),
    lambda d: d["galaxy"]["systems"][0]["hexes"][0]["units"][0]["components"].update(Unknown={}),
])
def test_invalid_save_preserves_running_campaign(mutation):
    game = campaign()
    unit = ship(game)
    game.selected_objects = [unit]
    game.ai_coordinator = Mock()
    data = serialize_game_state(game)
    before, identities, rng = canonical(game), dict(vars(game)), random.getstate()
    counter = Order.order_counter
    mutation(data)
    assert not deserialize_game_state(game, data)
    assert canonical(game) == before
    assert all(vars(game)[k] is value for k, value in identities.items())
    assert random.getstate() == rng and Order.order_counter == counter
    assert not game.ai_coordinator.mock_calls


@pytest.mark.parametrize("stage", ["validate_document", "reconcile"])
def test_injected_failure_is_transactional(monkeypatch, stage):
    import campaign_persistence
    game = mutated_campaign()
    payload = serialize_game_state(game)
    before, rng, order_counter = canonical(game), random.getstate(), Order.order_counter
    def fail(*args, **kwargs):
        raise RuntimeError("injected failure")
    monkeypatch.setattr(campaign_persistence, stage, fail)
    assert not deserialize_game_state(game, payload)
    assert canonical(game) == before
    assert random.getstate() == rng
    assert Order.order_counter == order_counter


@pytest.mark.parametrize("end", ["expiry", "component_damage", "remove", "replace", "source_destroy", "target_destroy", "load_expired"])
def test_effect_cleanup_is_owned_and_idempotent(end):
    game = campaign()
    first, second, target = ship(game, "first"), ship(game, "second"), ship(game, "target", owner=1)
    for source in (first, second):
        source.add_component(AbilityComponent(source, [AbilityType.ION_BOLT, AbilityType.DESIGNATE_TARGET]))
        for atype in source.ability_component.abilities:
            assert source.ability_component.activate(atype, game.galaxy, target_unit_id=target.id)
    component = first.ability_component
    assert target.damage_amplification == 1.0
    if end == "expiry":
        for ability in component.abilities.values():
            ability.duration_remaining = 1
        component.update(game.galaxy)
    elif end == "component_damage":
        first.take_component_damage(AbilityComponent, 100000)
    elif end == "remove":
        first.remove_component(AbilityComponent)
    elif end == "replace":
        first.add_component(AbilityComponent(first))
    elif end == "source_destroy":
        first.destroy()
    elif end == "target_destroy":
        target.destroy()
        assert all(not a.is_active for s in (first, second) for a in s.ability_component.abilities.values())
        return
    elif end == "load_expired":
        for ability in component.abilities.values():
            ability.duration_remaining = 0
        assert deserialize_game_state(game, serialize_game_state(game))
        target, first, second = (find_unit(game.galaxy, u.id) for u in (target, first, second))
        component = first.ability_component
    component.on_destroyed()
    component.on_destroyed()
    assert target.is_disabled and target.disabled_by_unit_ids == {second.id}
    assert target.damage_amplification == 0.5
    second.destroy()
    assert not target.is_disabled and target.damage_amplification == 0


def test_docked_source_effects_expire_and_platform_cleanup_survives_load():
    from turn_processor import TurnProcessor
    game = campaign()
    source, target, carrier = ship(game, hull=HullSize.TINY), ship(game, "target", owner=1), ship(game, "carrier")
    source.add_component(AbilityComponent(source, [AbilityType.ION_BOLT, AbilityType.MISSILE_BATTERIES]))
    source.ability_component.activate(AbilityType.ION_BOLT, game.galaxy, target_unit_id=target.id)
    source.ability_component.activate(AbilityType.MISSILE_BATTERIES, game.galaxy)
    platforms = list(source.ability_component.abilities[AbilityType.MISSILE_BATTERIES].spawned_unit_ids)
    carrier.add_component(HangarComponent(carrier, max_slots=20))
    assert carrier.hangar_component.dock(source, game.galaxy)
    assert deserialize_game_state(game, serialize_game_state(game))
    for _ in range(4):
        TurnProcessor(game)._process_unit_updates(game.players[0])
    assert not find_unit(game.galaxy, target.id).is_disabled
    assert all(find_unit(game.galaxy, uid) is None for uid in platforms)


def legacy_document(version):
    """Historical wire fixtures are intentionally independent of the current writer."""
    order = {"order_type": "MOVE", "status": "PENDING", "parameters": {
        "destination_system_name": "Sol", "destination_hex_coord": [0, 0],
        "destination_position": [200, 100]}, "sub_orders": []}
    if version == "3.2":
        order.update(public_id="0123456789abcdef0123456789abcdef", runtime_state={}, outcome_recorded=False)
    unit = {"id": 10, "owner_id": 0, "name": "Legacy ship", "position": [100, 0],
        "in_system": "Sol", "in_hex": [0, 0], "hull_size": "SMALL", "template_name": None,
        "current_hit_points": 40, "max_hit_points": 50, "damage_reduction": 0.75,
        "is_disabled": True, "disabled_by_unit_ids": [123], "components": {
            "Commander": {}, "AntimatterStorage": {"max_capacity": 60, "current_amount": 15},
            "Engines": {"speed": 37.5, "hull_cost": 1.875}, "Sensors": {"short_range_radius": 567.5, "long_range_hexes": 1}}}
    if version in (None, "3.0"):
        unit["orders"] = [order]
    else:
        unit["commander"] = {"stance": "attack_weapon_range", "current_order": order, "orders_queue": []}
    data = {"game_state": {"turn_number": 8, "current_player_index": 0, "view_mode": "galaxy",
        "current_system_name": "Sol", "current_sector_coord": [0, 0], "object_counter": 500, "player_counter": 20,
        "message_counter": 7, "campaign_id": "legacy-fixture"},
        "players": [{"id": 0, "controller": "human", "name": "Legacy", "color": [0, 100, 200], "credits": 1250}],
        "galaxy": {"systems": [{"name": "Sol", "position": [10, 20], "radius": 1, "hexes": [{
            "q": 0, "r": 0, "in_system": "Sol", "units": [unit], "minefields": [], "celestial_bodies": [
                {"id": 1, "class_name": "Star", "position": [0, 0], "in_system": "Sol", "in_hex": [0, 0]},
                {"id": 2, "class_name": "Nebula", "position": [1000, 0], "in_system": "Sol", "in_hex": [0, 0]},
                {"id": 3, "class_name": "Storm", "position": [-1000, 0], "in_system": "Sol", "in_hex": [0, 0]},
            ]}]}]}, "conversations": []}
    if version is not None:
        data["version"] = version
    return data


@pytest.mark.parametrize("version", [None, "3.0", "3.1", "3.2"])
def test_declared_legacy_migrations_are_stable_and_preserve_recoverable_state(version):
    from constants import StarType, NebulaType, StormType
    from save_migrations import migrate_save
    data = legacy_document(version)
    original = deepcopy(data)
    migrated, warnings = migrate_save(data)
    assert data == original
    assert migrated["version"] == "4.0" and warnings
    assert migrate_save(migrated) == (migrated, [])
    game = campaign()
    assert deserialize_game_state(game, data)
    unit = find_unit(game.galaxy, 10)
    assert unit.engines_component.speed == 37.5
    assert unit.sensors_component.short_range_radius == 567.5
    assert unit.antimatter_component.current_amount == 15
    assert not unit.is_disabled and unit.damage_reduction == 0
    assert unit.commander_component.current_order is not None
    assert unit.commander_component.current_order.status is OrderStatus.PENDING
    if version == "3.2":
        assert unit.commander_component.current_order.public_id == "0123456789abcdef0123456789abcdef"
    bodies = game.galaxy.systems["Sol"].hexes[(0, 0)].celestial_bodies
    assert bodies[0].star_type is StarType.G_TYPE
    assert bodies[1].nebula_type is NebulaType.HYDROGEN
    assert bodies[2].storm_type is StormType.PLASMA
    assert GameObject.object_counter == 500 and Player.player_counter == 20
    expected = canonical(game)
    assert deserialize_game_state(game, json.loads(json.dumps(serialize_game_state(game))))
    assert canonical(game) == expected


def test_legacy_unrecoverable_dynamic_configuration_is_an_explicit_failure():
    game = campaign()
    data = legacy_document("3.2")
    data["galaxy"]["systems"][0]["hexes"][0]["units"][0]["components"]["Weapons"] = {}
    errors = []
    before = canonical(game)
    assert not deserialize_game_state(game, data, on_error=errors.append)
    assert "configuration was not saved" in errors[0]
    assert canonical(game) == before


@pytest.mark.parametrize("stage", ["migrate_save", "deserialize_unit", "restore_component", "visibility"])
def test_failure_during_hydration_and_reconciliation_preserves_all_counters(monkeypatch, stage):
    import save_migrations, save_manager, unit_components.persistence, visibility
    game = mutated_campaign()
    data = serialize_game_state(game)
    before, identities, rng, order_counter = canonical(game), dict(vars(game)), random.getstate(), Order.order_counter
    def fail(*args, **kwargs):
        raise ValueError("injected late load failure")
    module, name = {"migrate_save": (save_migrations, "migrate_save"), "deserialize_unit": (save_manager, "deserialize_unit"),
                    "restore_component": (unit_components.persistence, "restore_component"),
                    "visibility": (visibility.VisibilityService, "compute")}[stage]
    monkeypatch.setattr(module, name, fail)
    assert not deserialize_game_state(game, data)
    assert canonical(game) == before
    assert all(vars(game)[k] is v for k, v in identities.items())
    assert random.getstate() == rng and Order.order_counter == order_counter


@pytest.mark.parametrize("wire", ['{"version":', '{"version":"4.0","version":"3.2"}', 'null'])
def test_invalid_json_does_not_touch_ai_or_campaign(tmp_path, wire):
    from game import Game
    game = campaign()
    source = ship(game)
    game.selected_objects = [source]
    game.gui, game.ai_coordinator = Mock(), Mock()
    game.ai_coordinator.state = "planning"
    game.pending_ai_turn_end_time = 12345
    path = tmp_path / "bad.json"
    path.write_text(wire)
    before, selection = canonical(game), game.selected_objects
    assert not Game.load_game(game, str(path))
    assert canonical(game) == before and game.selected_objects is selection
    assert game.ai_coordinator.state == "planning"
    assert game.pending_ai_turn_end_time == 12345
    game.ai_coordinator.reset.assert_not_called()
    game.gui.show_error_dialog.assert_called_once()


def test_post_commit_presentation_failure_is_not_reported_as_rejected_save(tmp_path):
    from game import Game
    game = campaign()
    saved = campaign()
    saved.turn_number = 23
    ship(saved)
    path = tmp_path / "valid.json"
    path.write_text(json.dumps(serialize_game_state(saved)))
    game.gui, game.ai_coordinator = Mock(), Mock()
    game.gui.show_game_ui.side_effect = RuntimeError("renderer unavailable")
    game.check_and_schedule_ai_turn = Mock()
    assert Game.load_game(game, str(path))
    assert game.turn_number == 23
    game.ai_coordinator.reset.assert_called_once()
    game.check_and_schedule_ai_turn.assert_called_once()
    game.gui.show_error_dialog.assert_not_called()


def test_resume_and_next_tick_do_not_replay_paid_replenishment_or_ability_activation():
    from turn_processor import TurnProcessor
    game = campaign()
    carrier, target = ship(game, "carrier"), ship(game, "target", owner=1)
    carrier.add_component(StrikecraftBayComponent(carrier, max_slots=1))
    wing = ship(game, "wing", hull=HullSize.STRIKECRAFT_WING)
    wing.add_component(StrikecraftWingComponent(wing))
    wing.current_hit_points = wing.max_hit_points - 10
    assert carrier.strikecraft_bay_component.dock(wing, game.galaxy)
    bay = carrier.strikecraft_bay_component
    bay.replenishing_unit, bay.replenish_progress = wing, 0
    game.players[0].credits -= 35
    carrier.add_component(AbilityComponent(carrier, [AbilityType.ION_BOLT, AbilityType.ADAPTIVE_FORCEFIELD]))
    for atype in carrier.ability_component.abilities:
        assert carrier.ability_component.activate(atype, game.galaxy, target_unit_id=target.id)
        carrier.ability_component.abilities[atype].duration_remaining = 1
    ammo = Weapons(carrier)
    ammo.turrets = [Turret(TurretType.BEAM, 10, 200, 5, carrier, current_cooldown=4)]
    carrier.add_component(ammo)
    saved = serialize_game_state(game)
    expected_credits, expected_fuel = game.players[0].credits, carrier.antimatter_component.current_amount
    TurnProcessor(game)._process_unit_updates(game.players[0])
    expected = canonical(game)
    assert deserialize_game_state(game, saved)
    carrier = find_unit(game.galaxy, carrier.id)
    assert game.players[0].credits == expected_credits
    assert carrier.antimatter_component.current_amount == expected_fuel
    assert carrier.weapons_component.turrets[0].current_cooldown == 4
    TurnProcessor(game)._process_unit_updates(game.players[0])
    assert canonical(game) == expected
    assert game.players[0].credits == expected_credits
    assert not find_unit(game.galaxy, target.id).is_disabled
    assert carrier.damage_reduction == 0


def test_empty_or_removed_template_components_are_not_resurrected(monkeypatch):
    import save_manager
    game = campaign()
    unit = ship(game)
    unit.template_name = "FIGHTER_WING"
    unit.remove_component(Sensors)
    unit.add_component(Weapons(unit))  # Deliberately empty turret inventory is valid.
    monkeypatch.setattr(save_manager, "_build_unit_from_template", Mock(side_effect=AssertionError("template access")))
    assert deserialize_game_state(game, serialize_game_state(game))
    restored = find_unit(game.galaxy, unit.id)
    assert restored.sensors_component is None
    assert restored.weapons_component.turrets == []


def test_queue_without_current_order_is_preserved_until_next_tick():
    game = campaign()
    unit = ship(game)
    unit.add_component(Engines(unit, speed=20))
    order = MoveOrder(unit, {"destination_system_name": "Sol", "destination_hex_coord": (0, 0),
                             "destination_position": Position(400, 0)})
    unit.commander_component.orders_queue.append(order)
    before = canonical(game)
    assert deserialize_game_state(game, serialize_game_state(game))
    unit = find_unit(game.galaxy, unit.id)
    assert canonical(game) == before
    assert unit.commander_component.current_order is None
    assert unit.commander_component.orders_queue[0].public_id == order.public_id
    unit.commander_component.update()
    assert unit.commander_component.current_order.public_id == order.public_id
    assert not unit.commander_component.orders_queue


@pytest.mark.parametrize("end", ["unit_destroy", "bay_remove"])
def test_destroyed_carrier_detaches_surviving_wings_before_save(end):
    game = campaign()
    carrier, wing = ship(game, "carrier"), ship(game, "wing")
    carrier.add_component(StrikecraftBayComponent(carrier))
    wing.add_component(StrikecraftWingComponent(wing))
    wing.strikecraft_wing_component.mother_carrier = carrier
    carrier.strikecraft_bay_component.launched_units.append(wing)
    if end == "unit_destroy":
        carrier.destroy()
    else:
        carrier.remove_component(StrikecraftBayComponent)
    assert wing.strikecraft_wing_component.mother_carrier is None
    before = canonical(game)
    assert deserialize_game_state(game, serialize_game_state(game))
    assert canonical(game) == before


@pytest.mark.parametrize("job", ["construction", "refit"])
def test_paid_job_survives_load_completes_or_refunds_once(job):
    from unit_orders import ConstructOrder, RefitOrder
    game = campaign()
    builder, target = ship(game, "builder"), ship(game, "target")
    builder.add_component(Constructor(builder))
    game.players[0].credits = 100000
    if job == "construction":
        order = ConstructOrder(builder, {"unit_template_name": "CONSTRUCTOR_MK1", "target_position": Position(400, 0)})
    else:
        order = RefitOrder(builder, {"target_unit_id": target.id, "action": "ADD", "component_type": "Defenses",
            "component_config": {"armor": 50, "shields": 50, "point_defense_strength": 0, "hull_cost": 10},
            "cost_credits": 300, "time_to_build": 3})
    builder.commander_component.add_order(order)
    assert order.status is OrderStatus.IN_PROGRESS
    charge = 100000 - game.players[0].credits
    assert charge > 0
    builder.constructor_component.update(game.galaxy)
    before, saved = canonical(game), serialize_game_state(game)
    assert deserialize_game_state(game, saved)
    assert canonical(game) == before
    builder = find_unit(game.galaxy, builder.id)
    restored_order = builder.commander_component.current_order
    assert restored_order.public_id == order.public_id
    restored_order.cancel()
    restored_order.cancel()
    assert game.players[0].credits == 100000
    assert builder.constructor_component.current_construction_target is None
    assert builder.constructor_component.current_refit_target is None
    assert deserialize_game_state(game, saved)
    builder = find_unit(game.galaxy, builder.id)
    for _ in range(50):
        builder.constructor_component.update(game.galaxy)
        builder.commander_component.update()
        if builder.commander_component.current_order is None:
            break
    assert builder.commander_component.current_order is None
    assert game.players[0].credits == 100000 - charge
    if job == "refit":
        from unit_components import Defenses
        assert find_unit(game.galaxy, target.id).get_component(Defenses).armor == 50
    else:
        assert len(list(iter_units(game.galaxy))) == 3


def test_observed_minefield_id_overrides_stale_serialized_counter():
    game = campaign()
    ship(game)
    field = Minefield(game.players[0], Position(800, 0), (0, 0), "Sol")
    field.id = GameObject.object_counter + 1000
    game.galaxy.systems["Sol"].hexes[(0, 0)].minefields.append(field)
    data = serialize_game_state(game)
    data["game_state"]["object_counter"] = 0
    assert deserialize_game_state(game, data)
    assert ship(game).id == field.id + 1


@pytest.mark.parametrize("mutation", [
    lambda a, unit: a.update(schema_version=2),
    lambda a, unit: a["runtime"].update(duration_remaining=-1),
    lambda a, unit: a["runtime"].update(spawned_unit_ids=[unit.id]),
    lambda a, unit: a["definition"].update(ability_type={"$enum": "AbilityType", "name": "ION_BOLT"}),
])
def test_invalid_ability_state_is_transactional(mutation):
    game = campaign()
    unit = ship(game)
    unit.add_component(AbilityComponent(unit, [AbilityType.ADAPTIVE_FORCEFIELD]))
    assert unit.ability_component.activate(AbilityType.ADAPTIVE_FORCEFIELD, game.galaxy)
    data = serialize_game_state(game)
    ability = data["galaxy"]["systems"][0]["hexes"][0]["units"][0]["components"]["AbilityComponent"]["runtime"]["abilities"][0]
    before, objects = canonical(game), dict(vars(game))
    mutation(ability, unit)
    assert not deserialize_game_state(game, data)
    assert canonical(game) == before
    assert all(vars(game)[k] is value for k, value in objects.items())
