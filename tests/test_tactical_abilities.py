"""Gameplay, persistence and public gateway acceptance for tactical abilities."""
import json
import pytest

from tests.support.campaigns import campaign, ship
from constants import HullSize, NebulaType
from domain.celestials import Nebula
from domain.minefields import Minefield
from domain.players import Player
from geometry import Position
from unit_components.abilities import AbilityComponent
from unit_components.enums import AbilityType
from unit_components.movement import Engines
from unit_components.antimatter import AntimatterStorage, AntimatterHarvester
from unit_components.sensors import Sensors
from unit_components.defenses import Defenses
from unit_components.minelayer import MinelayerComponent
from game_ai.commands import CommandGateway
from game_ai.contracts import Command, CommandBatch
from game_ai.observation import build_observation
from save_manager import serialize_game_state, deserialize_game_state
from tactical_abilities import (SPECS, activate, availability, deployments, start_owner_turn,
                                process_pulls, combat_hit, cancel, validate)
from tactical_balance import STRIKECRAFT_ABILITIES


def equipped(game, name='caster', owner=0, hull=HullSize.HUGE):
    unit = ship(game, name, owner=owner, hull=hull)
    for component in (Engines(unit, speed=100), AntimatterStorage(unit, max_capacity=1000),
                      Sensors(unit, short_range_radius=1000, long_range_hexes=2), Defenses(unit, armor=0, shields=0, point_defense=0),
                      MinelayerComponent(unit), AntimatterHarvester(unit),
                      AbilityComponent(unit, [AbilityType(k) for k in SPECS])):
        unit.add_component(component)
    return unit


def issue(game, unit, kind, **kwargs):
    return CommandGateway(game).apply_batch(unit.owner, CommandBatch((Command(type='use_ability', unit_ids=(unit.id,), ability=kind, **kwargs),)))


@pytest.fixture
def catalyst_scenario():
    game = campaign()
    caster = equipped(game)
    body = Nebula((0, 0), 'Sol', NebulaType.HYDROGEN)
    body.position, body.radius = Position(200, 0), 1000
    game.galaxy.systems['Sol'].add_celestial_body(body)
    return game, caster, body


@pytest.mark.parametrize('missing', [None, 'has_sensors', 'has_antimatter_storage'])
def test_catalyst_design_requires_sensors_and_storage(missing):
    from custom_unit_templates import CustomUnitTemplate
    design = CustomUnitTemplate('Storage Catalyst', HullSize.HUGE)
    design.components.has_ability_component = True
    design.components.abilities = ['nebula_catalyst']
    design.components.has_sensors = True
    design.components.has_antimatter_storage = True
    design.components.antimatter_capacity = 300
    design.components.has_antimatter_harvester = False
    if missing:
        setattr(design.components, missing, False)
        assert design.validate() == [f"Ability 'Nebula Catalyst' requires component '{missing}'."]
    else:
        assert design.validate() == []


@pytest.mark.parametrize('harvester_state', ['absent', 'destroyed'])
def test_catalyst_gateway_works_without_operational_harvester(catalyst_scenario, harvester_state):
    game, caster, body = catalyst_scenario
    if harvester_state == 'absent':
        caster.remove_component(AntimatterHarvester)
    else:
        caster.harvester_component.current_hit_points = 0
    observation = build_observation(game, caster.owner)
    assert list(observation['ability_catalog']['nebula_catalyst']['equipment']) == [
        'has_sensors', 'has_antimatter_storage']
    fuel = caster.antimatter_component.current_amount
    result = issue(game, caster, 'nebula_catalyst', target_id=body.id, position=(200, 0))
    assert result.accepted, result.errors
    assert caster.antimatter_component.current_amount == fuel - SPECS['nebula_catalyst'].cost
    assert len(deployments(game.galaxy, caster.id, 'nebula_catalyst')) == 1
    assert caster.ability_component.abilities[AbilityType.NEBULA_CATALYST].cooldown_remaining == SPECS['nebula_catalyst'].cooldown


@pytest.mark.parametrize('component_type', [Sensors, AntimatterStorage])
@pytest.mark.parametrize('state', ['absent', 'destroyed'])
def test_catalyst_unavailable_without_operational_prerequisite(catalyst_scenario, component_type, state):
    game, caster, body = catalyst_scenario
    storage = caster.antimatter_component
    if state == 'absent':
        caster.remove_component(component_type)
    else:
        caster.get_component(component_type).current_hit_points = 0
    fuel = storage.current_amount
    assert availability(caster, 'nebula_catalyst', game.galaxy) == 'capability_unavailable'
    assert not activate(caster, 'nebula_catalyst', game.galaxy, body.id, Position(200, 0))
    assert storage.current_amount == fuel
    assert not deployments(game.galaxy, caster.id, 'nebula_catalyst')
    assert caster.ability_component.abilities[AbilityType.NEBULA_CATALYST].is_ready


def test_catalyst_gateway_rejects_insufficient_fuel(catalyst_scenario):
    game, caster, body = catalyst_scenario
    caster.remove_component(AntimatterHarvester)
    fuel = SPECS['nebula_catalyst'].cost - 1
    caster.antimatter_component.current_amount = fuel
    result = issue(game, caster, 'nebula_catalyst', target_id=body.id, position=(200, 0))
    assert not result.accepted
    assert result.errors[0].code == 'insufficient_resources'
    assert caster.antimatter_component.current_amount == fuel
    assert not deployments(game.galaxy, caster.id, 'nebula_catalyst')


def test_catalyst_historical_definition_preserved_but_current_requirements_apply(catalyst_scenario):
    from dataclasses import replace
    game, caster, body = catalyst_scenario
    instance = caster.ability_component.abilities[AbilityType.NEBULA_CATALYST]
    instance.definition = replace(instance.definition,
        required_components=['has_sensors', 'has_antimatter_harvester'])
    saved_ability = instance.to_state()
    fuel = caster.antimatter_component.current_amount
    state = json.loads(json.dumps(serialize_game_state(game)))
    assert deserialize_game_state(game, state)
    restored = game.galaxy.get_unit_by_id(caster.id)
    assert restored.ability_component.abilities[AbilityType.NEBULA_CATALYST].to_state() == saved_ability
    assert restored.harvester_component is not None
    assert restored.antimatter_component.current_amount == fuel
    restored.remove_component(AntimatterHarvester)
    result = issue(game, restored, 'nebula_catalyst', target_id=body.id, position=(200, 0))
    assert result.accepted, result.errors
    assert restored.antimatter_component.current_amount == fuel - SPECS['nebula_catalyst'].cost
    assert len(deployments(game.galaxy, restored.id, 'nebula_catalyst')) == 1


@pytest.mark.parametrize('flag,label', [('has_sensors', 'Sensors'), ('has_antimatter_storage', 'Antimatter Storage')])
def test_catalyst_designer_prerequisite_controls(pygame_context, tmp_path, flag, label):
    import pygame
    import pygame_gui
    from custom_unit_templates import CustomTemplateManager
    from gui.unit_editor_gui.window import UnitEditorWindow
    from gui.unit_editor_gui.component_state import toggle_ability, update_ability_toggle_labels
    manager = pygame_gui.UIManager((1280, 720))
    editor = UnitEditorWindow(manager, pygame.Vector2(1280, 720),
        CustomTemplateManager(data_file=str(tmp_path / 'designs.json')))
    try:
        editor.show()
        editor._comp.has_ability_component = True
        editor._comp.has_sensors = True
        editor._comp.has_antimatter_storage = True
        editor._comp.has_antimatter_harvester = False
        editor._select_component('has_ability_component')
        button = editor._ability_buttons['nebula_catalyst']
        assert button.is_enabled
        assert button.text == '[ ] Nebula Catalyst (Req: Sensors, Antimatter Storage)'
        toggle_ability(editor, 'nebula_catalyst')
        assert 'nebula_catalyst' in editor._comp.abilities
        assert button.text == '[x] Nebula Catalyst (Req: Sensors, Antimatter Storage)'
        setattr(editor._comp, flag, False)
        update_ability_toggle_labels(editor)
        assert not button.is_enabled
        assert label in button.text
        assert 'Harvester' not in button.text
        assert 'nebula_catalyst' not in editor._comp.abilities
        toggle_ability(editor, 'nebula_catalyst')
        assert 'nebula_catalyst' not in editor._comp.abilities
        setattr(editor._comp, flag, True)
        update_ability_toggle_labels(editor)
        assert button.is_enabled
        assert button.text == '[ ] Nebula Catalyst (Req: Sensors, Antimatter Storage)'
    finally:
        editor.hide()


@pytest.mark.parametrize('kind,cap', [('ghost_fleet', 1), ('fuel_cache', 3)])
def test_persistent_cap_survives_time_save_refit_and_capture(kind, cap):
    game = campaign()
    caster = equipped(game)
    for index in range(cap):
        start_owner_turn(game.galaxy, caster.owner, game.turn_number)
        assert activate(caster, kind, game.galaxy, position=Position(200+index*60, 0))
        game.turn_number += SPECS[kind].cooldown
    start_owner_turn(game.galaxy, caster.owner, game.turn_number+10000)
    assert len(deployments(game.galaxy, caster.id, kind)) == cap
    fuel = caster.antimatter_component.current_amount
    assert not activate(caster, kind, game.galaxy, position=Position(200, 0))
    assert caster.antimatter_component.current_amount == fuel
    state = json.loads(json.dumps(serialize_game_state(game)))
    assert state['version'] == '4.3'
    assert all('lifetime' not in d for s in state['galaxy']['systems'] for h in s['hexes'] for d in h['deployables'])
    restored = campaign()
    assert deserialize_game_state(restored, state)
    caster = restored.galaxy.get_unit_by_id(caster.id)
    caster.owner = restored.players[1]
    caster.add_component(AbilityComponent(caster, [AbilityType(kind)]))
    assert availability(caster, kind, restored.galaxy) == 'deployment_cap_reached'
    objects = deployments(restored.galaxy, caster.id, kind)
    assert all(d.owner == restored.players[0] for d in objects)
    objects[0].destroy()
    assert availability(caster, kind, restored.galaxy) is None
    caster.destroy()
    assert len(deployments(restored.galaxy, caster.id, kind)) == cap-1


def test_fuel_recovery_partial_theft_and_empty_slot():
    game = campaign()
    caster = equipped(game)
    assert activate(caster, 'fuel_cache', game.galaxy, position=Position(220, 0))
    cache = deployments(game.galaxy, caster.id, 'fuel_cache')[0]
    thief = equipped(game, 'thief', owner=1)
    thief.position = Position(250, 0)
    thief.antimatter_component.current_amount = 980
    command = Command(type='recover_fuel_cache', unit_ids=(thief.id,), target_id=cache.id)
    assert CommandGateway(game).apply_batch(thief.owner, CommandBatch((command,))).accepted
    assert thief.antimatter_component.current_amount == 1000
    assert cache.fuel == 30
    thief.antimatter_component.current_amount = 900
    assert CommandGateway(game).apply_batch(thief.owner, CommandBatch((command,))).accepted
    assert thief.antimatter_component.current_amount == 930
    assert not deployments(game.galaxy, caster.id, 'fuel_cache')


@pytest.mark.parametrize('damage,loss,guardian_loss', [(40, 28, 9), (100, 80, 15), (1, 1, 0), (0, 0, 0)])
def test_guardian_reduces_redirected_weapon_damage_only(damage, loss, guardian_loss):
    game = campaign()
    caster, target = equipped(game), ship(game, 'protected')
    target.position = Position(250, 0)
    assert activate(caster, 'guardian_link', game.galaxy, target.id)
    before = (target.current_hit_points, caster.current_hit_points)
    combat_hit(target, damage)
    assert before[0]-target.current_hit_points == loss
    assert before[1]-caster.current_hit_points == guardian_loss
    target.take_damage(10)
    assert before[1]-caster.current_hit_points == guardian_loss
    assert cancel(caster, 'guardian_link')
    assert caster.ability_component.abilities[AbilityType.GUARDIAN_LINK].cooldown_remaining == 7


def test_tractor_pull_cost_single_tick_break_and_order_preservation():
    game = campaign()
    caster, target = equipped(game), ship(game, 'tow', hull=HullSize.SMALL)
    target.add_component(Engines(target, speed=100))
    target.engines_component.current_hit_points = 0
    target.position = Position(450, 0)
    assert activate(caster, 'tractor_tether', game.galaxy, target.id)
    assert caster.engines_component.effective_speed == 50
    am = caster.antimatter_component.current_amount
    process_pulls(game.galaxy, caster.owner, game.turn_number)
    assert target.position.x == pytest.approx(250)
    assert caster.antimatter_component.current_amount == am-5
    process_pulls(game.galaxy, caster.owner, game.turn_number)
    assert caster.antimatter_component.current_amount == am-5
    target.position = Position(1000, 0)
    process_pulls(game.galaxy, caster.owner, game.turn_number+1)
    assert caster.engines_component.effective_speed == 100


def test_sweep_only_known_fields_and_deterministic_budget():
    game = campaign()
    caster = equipped(game)
    sector = game.galaxy.systems['Sol'].hexes[(0, 0)]
    fields = [Minefield(game.players[1], Position(x, 0), (0, 0), 'Sol', mines_remaining=2) for x in (300, 500, 700)]
    sector.minefields.extend(fields)
    fields[1].reveal_to(caster.owner)
    fields[2].reveal_to(caster.owner)
    assert activate(caster, 'mine_clearing_sweep', game.galaxy, position=Position(900, 0))
    assert fields[0].mines_remaining == 2
    assert fields[1] not in sector.minefields
    assert fields[2].mines_remaining == 1


@pytest.mark.parametrize('kind,attribute,friendly_value,enemy_value', [
    ('HYDROGEN', 'fuel_multiplier', 0.25, 0.5), ('NITROGEN', 'cooldown_reduction', 2, 1),
    ('OXYGEN', 'splash_damage_multiplier', 1.15, 1.35), ('DUST', 'sensor_multiplier', 0.7, 0.5)])
def test_catalyst_selective_effects_persist_ownership(kind, attribute, friendly_value, enemy_value):
    from environmental_effects import modifiers_for_unit
    game = campaign()
    caster, enemy = equipped(game), equipped(game, 'enemy', owner=1)
    body = Nebula((0, 0), 'Sol', NebulaType[kind])
    body.position, body.radius = Position(200, 0), 1000
    game.galaxy.systems['Sol'].add_celestial_body(body)
    assert activate(caster, 'nebula_catalyst', game.galaxy, body.id, Position(200, 0))
    assert getattr(modifiers_for_unit(caster), attribute) == friendly_value
    assert getattr(modifiers_for_unit(enemy), attribute) == enemy_value
    caster.owner = enemy.owner
    assert getattr(modifiers_for_unit(caster), attribute) == enemy_value


def test_ghost_radar_has_no_identity_and_inspection_discredits_it():
    from visibility import VisibilityService
    game = campaign()
    caster = equipped(game)
    scout = equipped(game, 'scout', owner=1)
    scout.position = Position(3000, 0)
    assert activate(caster, 'ghost_fleet', game.galaxy, position=Position(200, 0))
    cache = deployments(game.galaxy, caster.id, 'ghost_fleet')[0]
    game.galaxy.systems['Sol'].hexes[(0, 0)].units.remove(caster)
    snapshot = VisibilityService.compute(game.galaxy, scout.owner)
    assert ('Sol', (0, 0)) in snapshot.presence_hexes
    obs = build_observation(game, scout.owner)
    assert not obs['visible_deployables']
    assert cache.id not in snapshot.visible_enemy_unit_ids
    scout.position = Position(250, 0)
    VisibilityService.compute(game.galaxy, scout.owner)
    scout.position = Position(3000, 0)
    assert ('Sol', (0, 0)) not in VisibilityService.compute(game.galaxy, scout.owner).presence_hexes
    assert cache in deployments(game.galaxy, caster.id, 'ghost_fleet')


def test_gateway_duplicate_spending_is_atomic_and_catalog_has_all_six():
    game = campaign()
    caster = equipped(game)
    before = caster.antimatter_component.current_amount
    cmd = Command(type='use_ability', unit_ids=(caster.id,), ability='fuel_cache', position=(200, 0))
    result = CommandGateway(game).apply_batch(caster.owner, CommandBatch((cmd, cmd)))
    assert not result.accepted
    assert caster.antimatter_component.current_amount == before
    assert not deployments(game.galaxy, caster.id, 'fuel_cache')
    assert issue(game, caster, 'fuel_cache', position=(200, 0)).accepted
    observation = build_observation(game, caster.owner)
    assert observation['schema_version'] == 6
    assert set(SPECS) <= set(observation['ability_catalog'])
    assert observation['visible_deployables'][0]['persistent'] is True


def test_invalid_cast_is_mutation_free_and_deadlines_roundtrip():
    game = campaign()
    caster, target = equipped(game), ship(game, 'target')
    am = caster.antimatter_component.current_amount
    assert not activate(caster, 'fuel_cache', game.galaxy, position=caster.position)
    assert caster.antimatter_component.current_amount == am
    target.position = Position(250, 0)
    assert activate(caster, 'guardian_link', game.galaxy, target.id)
    state = json.loads(json.dumps(serialize_game_state(game)))
    restored = campaign()
    assert deserialize_game_state(restored, state)
    caster = restored.galaxy.get_unit_by_id(caster.id)
    inst = caster.ability_component.abilities[AbilityType.GUARDIAN_LINK]
    assert inst.is_active and inst.expires_round == game.turn_number+3
    start_owner_turn(restored.galaxy, caster.owner, game.turn_number+3)
    assert not inst.is_active and inst.cooldown_remaining == 4


def test_recovery_then_cast_projects_fuel_and_frees_source_slot():
    game = campaign()
    caster = equipped(game)
    for index in range(3):
        assert activate(caster, 'fuel_cache', game.galaxy, position=Position(200, 0))
        game.turn_number += 4
        start_owner_turn(game.galaxy, caster.owner, game.turn_number)
    cache = deployments(game.galaxy, caster.id, 'fuel_cache')[0]
    caster.antimatter_component.current_amount = 5
    commands = (Command(type='recover_fuel_cache', unit_ids=(caster.id,), target_id=cache.id),
                Command(type='use_ability', unit_ids=(caster.id,), ability='fuel_cache', position=(200, 0)))
    result = CommandGateway(game).apply_batch(caster.owner, CommandBatch(commands))
    assert result.accepted, result.errors
    assert caster.antimatter_component.current_amount == 0
    assert len(deployments(game.galaxy, caster.id, 'fuel_cache')) == 3
    assert cache.current_hit_points == 0


def test_pending_cast_reserves_fuel_and_replacement_releases_it():
    from unit_orders import MoveOrder
    game = campaign()
    caster = equipped(game)
    caster.antimatter_component.current_amount = 60
    caster.commander_component.add_order(MoveOrder(caster, {'destination_system_name': 'Sol',
        'destination_hex_coord': (0, 0), 'destination_position': Position(1000, 0)}))
    assert issue(game, caster, 'fuel_cache', position=(200, 0), queue=True).accepted
    assert availability(caster, 'ghost_fleet', game.galaxy) == 'insufficient_resources'
    assert not issue(game, caster, 'ghost_fleet', position=(200, 0), queue=True).accepted
    assert issue(game, caster, 'ghost_fleet', position=(200, 0), queue=False).accepted
    assert caster.antimatter_component.current_amount == 35
    assert len(deployments(game.galaxy, caster.id, 'ghost_fleet')) == 1
    assert not deployments(game.galaxy, caster.id, 'fuel_cache')


@pytest.mark.parametrize('reverse', [False, True])
def test_legacy_and_new_abilities_share_batch_fuel_budget(reverse):
    from unit_components.abilities.registry import ABILITY_CLASSES
    game = campaign()
    caster = equipped(game)
    caster.ability_component.abilities[AbilityType.ADAPTIVE_FORCEFIELD] = ABILITY_CLASSES[AbilityType.ADAPTIVE_FORCEFIELD]()
    old = caster.ability_component.abilities[AbilityType.ADAPTIVE_FORCEFIELD]
    caster.antimatter_component.current_amount = 55 + old.definition.antimatter_cost - 1
    before = caster.antimatter_component.current_amount
    commands = [Command(type='use_ability', unit_ids=(caster.id,), ability='fuel_cache', position=(200, 0)),
                Command(type='use_ability', unit_ids=(caster.id,), ability='adaptive_forcefield')]
    if reverse:
        commands.reverse()
    result = CommandGateway(game).apply_batch(caster.owner, CommandBatch(tuple(commands)))
    assert not result.accepted and caster.antimatter_component.current_amount == before
    assert not old.is_active and not deployments(game.galaxy, caster.id, 'fuel_cache')


def test_batch_link_occupancy_cycles_and_cancellation():
    game = campaign()
    first, second, protected = equipped(game), equipped(game, 'second'), equipped(game, 'protected')
    second.position, protected.position = Position(250, 0), Position(400, 0)
    command = Command(type='use_ability', unit_ids=(first.id, second.id), ability='guardian_link', target_id=protected.id)
    assert not CommandGateway(game).apply_batch(first.owner, CommandBatch((command,))).accepted
    commands = (Command(type='use_ability', unit_ids=(first.id,), ability='guardian_link', target_id=second.id),
                Command(type='use_ability', unit_ids=(second.id,), ability='guardian_link', target_id=first.id))
    assert not CommandGateway(game).apply_batch(first.owner, CommandBatch(commands)).accepted
    commands = (commands[0], Command(type='cancel_ability', unit_ids=(first.id,), ability='guardian_link'),
                Command(type='use_ability', unit_ids=(protected.id,), ability='guardian_link', target_id=second.id))
    result = CommandGateway(game).apply_batch(first.owner, CommandBatch(commands))
    assert result.accepted, result.errors
    assert not first.ability_component.abilities[AbilityType.GUARDIAN_LINK].is_active
    assert protected.ability_component.abilities[AbilityType.GUARDIAN_LINK].is_active


@pytest.mark.parametrize('kind,equipment', [('guardian_link', Defenses), ('tractor_tether', Engines)])
def test_required_equipment_removal_releases_link_immediately(kind, equipment):
    game = campaign()
    caster, target = equipped(game), equipped(game, 'target', hull=HullSize.SMALL)
    target.position = Position(250, 0)
    assert activate(caster, kind, game.galaxy, target.id)
    caster.remove_component(equipment)
    assert not caster.ability_component.abilities[AbilityType(kind)].is_active
    assert caster.ability_component.abilities[AbilityType(kind)].cooldown_remaining == SPECS[kind].cooldown


def test_guardian_subsystem_spillover_and_death_do_not_route_again():
    game = campaign()
    guardian, target, outer = equipped(game), equipped(game, 'target'), equipped(game, 'outer')
    target.position, outer.position = Position(250, 0), Position(400, 0)
    assert activate(outer, 'guardian_link', game.galaxy, guardian.id)
    assert activate(guardian, 'guardian_link', game.galaxy, target.id)
    target.engines_component.current_hit_points = 5
    target.damage_reduction = 0.5
    before = target.current_hit_points
    outer_hp = outer.current_hit_points
    guardian.current_hit_points = 3
    combat_hit(target, 40, component_type=Engines)
    assert guardian.current_hit_points == 0
    assert outer.current_hit_points == outer_hp
    assert target.engines_component.current_hit_points == 0
    assert target.current_hit_points == before - 9  # 28 * 0.5 - 5 subsystem HP
    combat_hit(target, 40)
    assert target.current_hit_points == before - 9 - 20


def test_tractor_stops_before_ship_obstacle_and_no_extra_enemy_mine_tick():
    from turn_processor import TurnProcessor
    game = campaign()
    caster, target = equipped(game), equipped(game, 'target', owner=1, hull=HullSize.SMALL)
    target.position = Position(500, 0)
    obstacle = ship(game, 'obstacle')
    obstacle.position = Position(350, 0)
    sector = game.galaxy.systems['Sol'].hexes[(0, 0)]
    field = Minefield(caster.owner, Position(410, 0), (0, 0), 'Sol', mines_remaining=5)
    sector.minefields.append(field)
    assert activate(caster, 'tractor_tether', game.galaxy, target.id)
    process_pulls(game.galaxy, caster.owner, game.turn_number)
    assert 400 <= target.position.x < 401
    TurnProcessor(game)._process_minefield_detonations(caster.owner)
    assert field.mines_remaining == 5
    caster.antimatter_component.current_amount = 0
    sector.units.remove(obstacle)
    process_pulls(game.galaxy, caster.owner, game.turn_number+1)
    assert not caster.ability_component.abilities[AbilityType.TRACTOR_TETHER].is_active


def test_catalyst_opposing_patches_baseline_boundary_and_recipient_splash():
    from environmental_effects import modifiers_for_unit
    game = campaign()
    guardian, target, enemy = equipped(game), equipped(game, 'target'), equipped(game, 'enemy', owner=1)
    body = Nebula((0, 0), 'Sol', NebulaType.OXYGEN)
    body.position, body.radius = Position(200, 0), 300
    game.galaxy.systems['Sol'].add_celestial_body(body)
    target.position = Position(500, 0)
    assert activate(guardian, 'guardian_link', game.galaxy, target.id)
    assert activate(guardian, 'nebula_catalyst', game.galaxy, body.id, Position(200, 0))
    assert activate(enemy, 'nebula_catalyst', game.galaxy, body.id, Position(200, 0))
    # The friendly patch cannot suppress the hostile oxygen enhancement.
    assert modifiers_for_unit(target).splash_damage_multiplier == 1.35
    guardian.position = Position(50, 0)
    before = guardian.current_hit_points, target.current_hit_points
    combat_hit(target, 40, is_splash=True)
    assert guardian.current_hit_points == before[0]-12  # floor(9 * 1.35)
    assert target.current_hit_points == before[1]-37  # floor(28 * 1.35)
    target.position = Position(500.01, 0)
    assert modifiers_for_unit(target).splash_damage_multiplier == 1.0
    enemy.destroy()
    assert modifiers_for_unit(guardian).splash_damage_multiplier == 1.35


@pytest.mark.parametrize('players_count', [2, 3, 6])
def test_owner_start_deadlines_do_not_depend_on_number_of_players(players_count):
    from turn_processor import TurnProcessor
    game = campaign()
    game.players.extend(Player(str(i), (50, 50, 50)) for i in range(players_count-2))
    caster, target = equipped(game), ship(game, 'target')
    target.position = Position(250, 0)
    assert activate(caster, 'guardian_link', game.galaxy, target.id)
    inst = caster.ability_component.abilities[AbilityType.GUARDIAN_LINK]
    processor = TurnProcessor(game)
    processor.process_player_turn = lambda player: None
    processor.process_global_end_of_round = lambda: None
    for _ in range(players_count * 3 - 1):
        processor.end_turn()
        assert inst.is_active
    processor.end_turn()
    assert not inst.is_active and inst.cooldown_remaining == 4


def test_historical_source_allocator_and_legacy_40_migration():
    from domain.identity import GameObject
    from campaign_persistence import prepare_campaign
    game = campaign()
    caster = equipped(game)
    assert activate(caster, 'ghost_fleet', game.galaxy, position=Position(200, 0))
    obj = deployments(game.galaxy, caster.id, 'ghost_fleet')[0]
    with pytest.raises(AttributeError):
        obj.deploying_ship_id = 999999
    caster.destroy()
    state = json.loads(json.dumps(serialize_game_state(game)))
    state['galaxy']['systems'][0]['hexes'][0]['deployables'][0]['deploying_ship_id'] = 999999
    assert deserialize_game_state(game, state)
    assert GameObject.object_counter >= 1000000
    legacy = serialize_game_state(campaign())
    legacy['version'] = '4.0'
    for system in legacy['galaxy']['systems']:
        for sector in system['hexes']:
            sector.pop('deployables')
            sector.pop('catalyst_patches')
    prepared = prepare_campaign(legacy)
    assert all(not s.deployables and not s.catalyst_patches for system in prepared.state.galaxy.systems.values() for s in system.hexes.values())


def test_hidden_cache_and_missing_id_have_same_error_and_no_provenance_leak():
    game = campaign()
    caster, enemy = equipped(game), equipped(game, 'enemy', owner=1)
    enemy.position = Position(3000, 0)
    assert activate(caster, 'fuel_cache', game.galaxy, position=Position(200, 0))
    cache = deployments(game.galaxy, caster.id, 'fuel_cache')[0]
    def recover(target_id):
        return CommandGateway(game).apply_batch(enemy.owner, CommandBatch((Command(type='recover_fuel_cache', unit_ids=(enemy.id,), target_id=target_id),)))
    assert recover(cache.id).errors[0].code == recover(99999999).errors[0].code
    assert not build_observation(game, enemy.owner)['visible_deployables']
    enemy.position = Position(250, 0)
    view = build_observation(game, enemy.owner)['visible_deployables'][0]
    assert 'deploying_ship_id' not in view and 'lifetime' not in view


@pytest.mark.parametrize('kind', [k for k in SPECS if k not in STRIKECRAFT_ABILITIES])
def test_fake_provider_can_issue_each_tactical_ability(kind):
    from game_ai.adapters.fake import FakePlanningProvider
    from game_ai.adapters.base import PlanningRequest
    from game_ai.contracts import TurnPlan
    from game_ai.runtime import get_runtime_config
    from tests.support.ai import EMPTY_PATCH
    game = campaign()
    caster, target = equipped(game), equipped(game, 'target', hull=HullSize.SMALL)
    target.position = Position(250, 0)
    body = Nebula((0, 0), 'Sol', NebulaType.HYDROGEN)
    body.position, body.radius = Position(200, 0), 1000
    game.galaxy.systems['Sol'].add_celestial_body(body)
    field = Minefield(game.players[1], Position(400, 0), (0, 0), 'Sol', mines_remaining=5)
    field.reveal_to(caster.owner)
    game.galaxy.systems['Sol'].hexes[(0, 0)].minefields.append(field)
    kwargs = {'target_id': target.id} if SPECS[kind].target_kind == 'unit' else {'position': (200, 0)}
    if kind == 'nebula_catalyst':
        kwargs['target_id'] = body.id
    command = Command(type='use_ability', unit_ids=(caster.id,), ability=kind, **kwargs)
    plan = TurnPlan.from_dict({'plan': [], 'commands': [command.to_dict()], 'memory_patch': EMPTY_PATCH, 'end_turn': True})
    provider = FakePlanningProvider([plan])
    observation = build_observation(game, caster.owner)
    output = provider.plan_turn(PlanningRequest('test', 'agent', 'One', 7, observation, {}), get_runtime_config('low'))
    result = CommandGateway(game).apply_batch(caster.owner, output.plan.batch)
    assert result.accepted, result.errors
    assert caster.ability_component.abilities[AbilityType(kind)].cooldown_remaining == SPECS[kind].cooldown


def test_custom_design_roundtrip_construction_and_use(tmp_path):
    from custom_unit_templates import CustomUnitTemplate, CustomTemplateManager
    from unit_components.constructor import Constructor
    game = campaign()
    design = CustomUnitTemplate('Tactical Test Design', HullSize.HUGE)
    for flag in {flag for spec in SPECS.values() for flag in spec.equipment}:
        setattr(design.components, flag, True)
    design.components.has_ability_component = True
    design.components.abilities = list(SPECS)
    from custom_unit_templates import TurretConfig
    design.components.turrets = [TurretConfig(turret_type='MASS_DRIVER', damage=1, range=100, cooldown=2, variant='ANTI_STRIKECRAFT')]
    design.components.antimatter_capacity = 300
    manager = CustomTemplateManager(data_file=str(tmp_path / 'designs.json'))
    assert manager.save_design(design) == []
    loaded = CustomTemplateManager(data_file=str(tmp_path / 'designs.json'))
    loaded.load_from_file()
    assert set(loaded.designs[design.display_name].components.abilities) == set(SPECS)
    yard = equipped(game, 'yard')
    yard.add_component(Constructor(yard))
    command = Command(type='construct', unit_ids=(yard.id,), template_name=design.display_name, position=(500, 0))
    result = CommandGateway(game).apply_batch(yard.owner, CommandBatch((command,)))
    assert result.accepted, result.errors
    yard.constructor_component.finish_construction(game.galaxy)
    built = next(u for u in game.galaxy.systems['Sol'].hexes[(0, 0)].units if u.template_name == design.display_name)
    assert set(k.value for k in built.ability_component.abilities) == set(SPECS)
    assert issue(game, built, 'ghost_fleet', position=(700, 0)).accepted


def test_recovery_and_celestial_orders_roundtrip_without_replaying(tmp_path):
    from unit_orders import MoveOrder
    game = campaign()
    caster = equipped(game)
    assert activate(caster, 'fuel_cache', game.galaxy, position=Position(200, 0))
    cache = deployments(game.galaxy, caster.id, 'fuel_cache')[0]
    body = Nebula((0, 0), 'Sol', NebulaType.HYDROGEN)
    body.position, body.radius = Position(200, 0), 1000
    game.galaxy.systems['Sol'].add_celestial_body(body)
    caster.commander_component.add_order(MoveOrder(caster, {'destination_system_name': 'Sol',
        'destination_hex_coord': (0, 0), 'destination_position': Position(1000, 0)}))
    commands = (Command(type='recover_fuel_cache', unit_ids=(caster.id,), target_id=cache.id, queue=True),
                Command(type='use_ability', unit_ids=(caster.id,), ability='nebula_catalyst', target_id=body.id, position=(200, 0), queue=True))
    assert CommandGateway(game).apply_batch(caster.owner, CommandBatch(commands)).accepted
    roots = list(caster.commander_component.orders_queue)
    before = caster.antimatter_component.current_amount
    assert deserialize_game_state(game, json.loads(json.dumps(serialize_game_state(game))))
    restored = game.galaxy.get_unit_by_id(caster.id)
    assert [o.public_id for o in restored.commander_component.orders_queue] == [o.public_id for o in roots]
    assert restored.antimatter_component.current_amount == before
    assert not deployments(game.galaxy, caster.id, 'nebula_catalyst')
    assert len(deployments(game.galaxy, caster.id, 'fuel_cache')) == 1


def test_ghost_concealment_team_identification_and_real_enemy_coexistence():
    from visibility import VisibilityService
    from domain.celestials import AsteroidField
    game = campaign()
    ally = Player('Observer ally', (100, 100, 0), team_id=game.players[1].team_id)
    game.players.append(ally)
    caster = equipped(game)
    scout = equipped(game, 'scout', owner=1)
    scout.position = Position(3000, 0)
    assert activate(caster, 'ghost_fleet', game.galaxy, position=Position(200, 0))
    emitter = deployments(game.galaxy, caster.id, 'ghost_fleet')[0]
    sector = game.galaxy.systems['Sol'].hexes[(0, 0)]
    field = AsteroidField((0, 0), 'Sol')
    field.position, field.radius = Position(200, 0), 700
    game.galaxy.systems['Sol'].add_celestial_body(field)
    assert ('Sol', (0, 0)) not in VisibilityService.compute(game.galaxy, scout.owner).presence_hexes
    sector.celestial_bodies.remove(field)
    scout.position = Position(250, 0)
    VisibilityService.compute(game.galaxy, scout.owner)
    assert {scout.owner.id, ally.id} <= emitter.identified_player_ids
    scout.position = Position(3000, 0)
    assert ('Sol', (0, 0)) in VisibilityService.compute(game.galaxy, scout.owner).presence_hexes
    caster.destroy()
    assert ('Sol', (0, 0)) not in VisibilityService.compute(game.galaxy, scout.owner).presence_hexes


def test_actual_sensor_radius_is_shared_with_ai_and_cooldown_resets():
    from environmental_effects import sensor_radius
    from unit_components.weapons import Weapons, Turret
    from unit_components.enums import TurretType
    game = campaign()
    caster, enemy = equipped(game), equipped(game, 'enemy', owner=1)
    body = Nebula((0, 0), 'Sol', NebulaType.DUST)
    body.position, body.radius = Position(200, 0), 1000
    game.galaxy.systems['Sol'].add_celestial_body(body)
    assert activate(caster, 'nebula_catalyst', game.galaxy, body.id, Position(200, 0))
    assert sensor_radius(enemy) == 500
    obs = build_observation(game, enemy.owner)
    view = next(u for u in obs['units'] if u['id'] == enemy.id)
    assert view['capability_details']['sensors']['effective_short_range_radius'] == 500
    body.nebula_type = NebulaType.NITROGEN
    caster.add_component(Weapons(caster))
    for base, expected in [(0, 0), (1, 1), (3, 1), (6, 4)]:
        turret = Turret(TurretType.BEAM, damage=10, range=500, cooldown=base, parent_unit=caster)
        turret.parent_unit = caster
        turret.current_cooldown = 8
        assert turret.effective_cooldown == expected
        assert turret.current_cooldown == 8
        turret.fire()
        assert turret.current_cooldown == expected


def test_deployable_ordinary_turret_attack_and_subsystem_rejection():
    from unit_components.weapons import Weapons, Turret
    from unit_components.enums import TurretType
    game = campaign()
    caster, attacker = equipped(game), equipped(game, 'attacker', owner=1)
    attacker.position = Position(400, 0)
    assert activate(caster, 'fuel_cache', game.galaxy, position=Position(200, 0))
    cache = deployments(game.galaxy, caster.id, 'fuel_cache')[0]
    weapons = Weapons(attacker)
    attacker.add_component(weapons)
    weapons.add_turret(Turret(TurretType.BEAM, damage=25, range=500, cooldown=1, parent_unit=attacker))
    command = Command(type='attack', unit_ids=(attacker.id,), target_id=cache.id, target_component='Engines')
    assert not CommandGateway(game).apply_batch(attacker.owner, CommandBatch((command,))).accepted
    command = Command(type='attack', unit_ids=(attacker.id,), target_id=cache.id)
    result = CommandGateway(game).apply_batch(attacker.owner, CommandBatch((command,)))
    assert result.accepted, result.errors
    weapons.update(game.galaxy)
    assert cache.current_hit_points == 0


def test_codex_protocol_requires_observation_of_new_cache_before_recovery():
    from game_control_protocol import ControlService, PROTOCOL_VERSION
    from player_controller import PlayerController
    game = campaign()
    caster = equipped(game)
    caster.owner.controller = PlayerController.CODEX
    game.current_player = caster.owner
    service = ControlService(game, port=0)
    try:
        observed = service._dispatch('observe', 'obs', {})
        assert observed['ok'] and observed['protocol_version'] == PROTOCOL_VERSION == 3
        token = observed['data']['turn_token']
        command = Command(type='use_ability', unit_ids=(caster.id,), ability='fuel_cache', position=(200, 0))
        result = service._dispatch('command', 'deploy', {'turn_token': token, 'commands': [command.to_dict()]})
        assert result['ok'], result
        cache = deployments(game.galaxy, caster.id, 'fuel_cache')[0]
        recover = Command(type='recover_fuel_cache', unit_ids=(caster.id,), target_id=cache.id).to_dict()
        result = service._dispatch('command', 'guess', {'turn_token': token, 'commands': [recover]})
        assert not result['ok'] and cache.fuel == 50
        observation = service._dispatch('observe', 'fresh', {})
        assert observation['data']['observation']['visible_deployables'][0]['id'] == cache.id
        result = service._dispatch('command', 'recover', {'turn_token': token, 'commands': [recover]})
        assert result['ok'], result
        assert not deployments(game.galaxy, caster.id, 'fuel_cache')
    finally:
        service.shutdown()


def test_designer_exposes_all_six_and_sidebar_persistent_caps(pygame_context, tmp_path):
    import pygame
    import pygame_gui
    from gui.unit_editor_gui.window import UnitEditorWindow
    from custom_unit_templates import CustomTemplateManager
    from tactical_ui import ability_panel
    manager = pygame_gui.UIManager((1280, 720))
    editor = UnitEditorWindow(manager, pygame.Vector2(1280, 720), CustomTemplateManager(data_file=str(tmp_path / 'designs.json')))
    editor.show()
    editor._comp.has_ability_component = True
    editor._select_component('has_ability_component')
    assert set(SPECS) <= set(editor._ability_buttons)
    for kind in SPECS:
        control = editor._ability_buttons[kind]
        assert control.visible
        assert editor._ability_scroll_container.get_container().get_abs_rect().contains(control.get_abs_rect())
    assert editor._panel.get_abs_rect().contains(editor._ability_scroll_container.get_abs_rect())
    screen = pygame.Surface((1280, 720))
    manager.update(0.1)
    manager.draw_ui(screen)
    pygame.image.save(screen, str(tmp_path / 'designer.png'))
    editor.hide()
    game = campaign()
    caster = equipped(game)
    assert activate(caster, 'ghost_fleet', game.galaxy, position=Position(200, 0))
    labels = [row.get('text', '') for row in ability_panel(caster, game)]
    assert any('1/1 emitters' in text and 'Persistent' in text for text in labels)
