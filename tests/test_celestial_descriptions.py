"""Terrain rules agree across execution, observations and real sidebar widgets."""
import json
from types import SimpleNamespace

import pytest

from constants import FieldDensity, HullSize, NebulaType, PlanetType, StarType, StormType
from domain.celestials import (AsteroidField, DebrisField, IceField, Nebula, Planet,
                              Star, Storm, Moon, Comet, MetalAsteroid, ColonizableAsteroid, Wormhole)
from environmental_effects import describe_body, modifiers_for_unit, sublight_speed
from game_ai.observation import _body_view, _capability_details, build_observation
from geometry import Position, distance
from gui.sidebar.panels_world import build_celestial_body_panel
from tests.support.campaigns import campaign, ship
from turn_processor import TurnProcessor
from unit_components.movement import Engines
from unit_orders.base import OrderStatus
from unit_orders.movement import ReachWaypointOrder
from visibility import VisibilityService


def install(game, body):
    game.galaxy.systems[body.in_system].add_celestial_body(body)
    return body


def moving_ship(game, speed, destination, *, hull=HullSize.SMALL):
    unit = ship(game, hull=hull)
    unit.add_component(Engines(unit, speed=speed))
    order = ReachWaypointOrder(unit, {'destination_system_name': 'Sol',
        'destination_hex_coord': (0, 0), 'destination_position': destination})
    order.status = OrderStatus.IN_PROGRESS
    unit.commander_component.current_order = order
    unit.engines_component.set_move_target(destination, order.local_order_id)
    return unit


@pytest.mark.parametrize('cls,attribute,enum', [
    (Star, 'star_type', StarType), (Planet, 'planet_type', PlanetType),
    (Nebula, 'nebula_type', NebulaType), (Storm, 'storm_type', StormType),
])
def test_every_subtype_is_readable_and_rules_reach_both_audiences(cls, attribute, enum):
    game = campaign()
    for kind in enum:
        kwargs = {attribute: kind, 'in_system': 'Sol'}
        if cls is not Star:
            kwargs['in_hex'] = (0, 0)
        body = cls(**kwargs)
        observation = _body_view(body, game.players[0])
        assert observation['subtype'] == kind.name
        assert observation['collision_radius'] == body.collision_radius
        assert observation['inhibition_field_radius'] == body.inhibition_field_radius
        panel = build_celestial_body_panel(game, body, show_rules=True)
        text = [row.get('text') for row in panel]
        assert observation['environmental_rules']
        assert all(rule in text for rule in observation['environmental_rules'])
        assert any(row.get('action_id') == 'select_hex' for row in panel)
        json.dumps(observation, allow_nan=False)


@pytest.mark.parametrize('cls', [Moon, Comet, MetalAsteroid, ColonizableAsteroid, Wormhole])
def test_other_bodies_retain_geometry_and_actions(cls):
    game = campaign()
    body = cls((0, 0), 'Sol') if cls is not Wormhole else cls((0, 0), 'Sol', 'Beta')
    observed = _body_view(body, game.players[0])
    assert observed['collision_radius'] == body.collision_radius
    assert observed['inhibition_field_radius'] == body.inhibition_field_radius
    assert any(row.get('action_id') == 'select_hex' for row in build_celestial_body_panel(game, body))


@pytest.mark.parametrize('cls', [AsteroidField, IceField, DebrisField])
@pytest.mark.parametrize('density,max_hull,drag,cover,damage', [
    (FieldDensity.LOW, 'LARGE', .85, .05, 1),
    (FieldDensity.MEDIUM, 'MEDIUM', .75, .10, 2),
    (FieldDensity.HIGH, 'SMALL', .65, .15, 3),
])
def test_field_density_contract(cls, density, max_hull, drag, cover, damage):
    body = cls((0, 0), 'Sol', density)
    observed = _body_view(body, None)
    assert observed['max_hull_size'] == max_hull
    assert observed['effect_radius'] == (2000 if cls is DebrisField else 3600)
    effects = observed['environmental_effects']
    assert effects['speed_multiplier'] == pytest.approx(drag + (.05 if cls is IceField else 0))
    assert effects['strikecraft_ignores_drag']
    if cls is IceField:
        assert effects['beam_cover'] == cover and effects['cooldown_reduction'] == 1
    elif cls is DebrisField:
        hazard = effects['hazards'][0]
        assert effects['kinetic_missile_cover'] == cover
        assert hazard['amount'] == damage and hazard['speed_threshold'] == 50
        assert hazard['requires_sublight_movement'] and not hazard['affects_strikecraft']
    else:
        assert effects['long_range_concealment']


def test_star_geometry_and_hazard_scope_are_independent():
    black_hole = _body_view(Star('Sol', StarType.BLACK_HOLE), None)
    assert black_hole['collision_radius'] == 750.015
    assert black_hole['inhibition_field_radius'] == 4500
    assert 'effect_radius' not in black_hole
    hazard = black_hole['environmental_effects']['hazards'][0]
    assert (hazard['radius'], hazard['amount'], hazard['scope']) == (750, 15, 'radius')
    pulsar = _body_view(Star('Sol', StarType.PULSAR), None)['environmental_effects']['hazards'][0]
    assert pulsar['scope'] == 'sector' and pulsar['radius'] is None and pulsar['amount'] == .05
    for kind in (StarType.BLUE_GIANT, StarType.RED_GIANT):
        body = Star('Sol', kind)
        assert 'Collision radius: 900 units (solid surface).' in describe_body(body).rules


@pytest.mark.parametrize('amount,remaining', [(0, 0), (.5, 0), (5, 0), (6, 0), (10, 4)])
def test_magnetic_drain_is_capped_to_available_fuel(amount, remaining):
    game = campaign()
    unit = ship(game)
    install(game, Storm((0, 0), 'Sol', StormType.MAGNETIC))
    unit.antimatter_component.current_amount = amount
    unit.owner.is_human = True
    from turn_briefing import begin_window
    begin_window(game, unit.owner)
    notices = []
    processor = TurnProcessor(game, presentation=SimpleNamespace(warn_human=lambda *a, **kw: notices.append(a[1])))
    processor._process_environmental_hazards(game.players[0])
    assert unit.antimatter_component.current_amount == remaining
    if amount:
        assert unit.owner.briefing.pending[0].amount == amount - remaining
        assert unit.owner.briefing.pending[0].category == 'hazard'
    else:
        assert not unit.owner.briefing.pending
    assert not notices
    assert not unit.antimatter_component.consume(remaining + 1)
    assert unit.antimatter_component.current_amount == remaining


def test_magnetic_preserves_destroyed_storage():
    game = campaign()
    unit = ship(game)
    install(game, Storm((0, 0), 'Sol', StormType.MAGNETIC))
    unit.antimatter_component.current_amount = 5
    unit.antimatter_component.current_hit_points = 0
    TurnProcessor(game)._process_environmental_hazards(game.players[0])
    assert unit.antimatter_component.current_amount == 5


@pytest.mark.parametrize('speed,damage', [(60, 0), (50 / .75, 0), (80, 2)])
@pytest.mark.parametrize('destination_x', [101, 1000])
def test_debris_uses_post_drag_movement_including_short_arrivals(speed, damage, destination_x):
    game = campaign()
    install(game, DebrisField((0, 0), 'Sol'))
    unit = moving_ship(game, speed, Position(destination_x, 0))
    processor = TurnProcessor(game)
    hp = unit.current_hit_points
    movements = processor._process_movement(unit.owner)
    assert movements[unit.id] == pytest.approx(speed * .75)
    if destination_x == 101:
        assert unit.engines_component.move_target is None
    processor._process_environmental_hazards(unit.owner, movements)
    assert unit.current_hit_points == hp - damage
    # No receipt from this phase means no abrasion, even with a pending target.
    processor._process_environmental_hazards(unit.owner)
    assert unit.current_hit_points == hp - damage


@pytest.mark.parametrize('blocked', ['stationary', 'no_fuel', 'disabled', 'destroyed_engines'])
def test_debris_requires_successful_movement(blocked):
    game = campaign()
    install(game, DebrisField((0, 0), 'Sol'))
    unit = moving_ship(game, 100, Position(1000, 0))
    if blocked == 'stationary':
        unit.commander_component.clear_explicit_orders()
    elif blocked == 'no_fuel':
        unit.antimatter_component.current_amount = 0
    elif blocked == 'disabled':
        unit.is_disabled = True
    else:
        unit.engines_component.current_hit_points = 0
    processor = TurnProcessor(game)
    hp = unit.current_hit_points
    movements = processor._process_movement(unit.owner)
    assert unit.id not in movements
    processor._process_environmental_hazards(unit.owner, movements)
    assert unit.current_hit_points == hp


def test_debris_crossing_and_final_boundary():
    game = campaign()
    body = install(game, DebrisField((0, 0), 'Sol'))
    body.radius = 10
    body.position = Position(140, 0)
    unit = moving_ship(game, 100, Position(200, 0))
    processor = TurnProcessor(game)
    hp = unit.current_hit_points
    movements = processor._process_movement(unit.owner)
    processor._process_environmental_hazards(unit.owner, movements)
    assert unit.position.x == 200 and unit.current_hit_points == hp
    unit.position = Position(150, 0)
    processor._process_environmental_hazards(unit.owner, movements)
    assert unit.current_hit_points == hp - 2


def test_effective_stats_agree_with_movement_sidebar_and_visibility():
    game = campaign()
    unit = moving_ship(game, 60, Position(1000, 0))
    install(game, DebrisField((0, 0), 'Sol'))
    unit.sensors_component.long_range_hexes = 1
    ship(game, 'enemy', owner=1, sector=(1, 0))
    assert ('Sol', (1, 0)) in VisibilityService.compute(game.galaxy, unit.owner).presence_hexes
    install(game, Storm((0, 0), 'Sol', StormType.MAGNETIC))
    actual = VisibilityService.compute(game.galaxy, unit.owner)
    assert ('Sol', (1, 0)) not in actual.presence_hexes
    details = _capability_details(unit, game)
    assert details['engines']['speed'] == 60 and details['engines']['effective_speed'] == 45
    assert details['sensors']['long_range_hexes'] == 1 and details['sensors']['effective_long_range_hexes'] == 0
    assert any('45.0' in row.get('text', '') for row in unit.engines_component.get_sidebar_data(game))
    assert any('Long Range: 0' in row.get('text', '') for row in unit.sensors_component.get_sidebar_data(game))
    start = unit.position
    TurnProcessor(game)._process_movement(unit.owner)
    assert distance(start, unit.position) == 45


def test_wings_keep_cover_and_ignore_strongest_overlapping_drag():
    game = campaign()
    for cls in (AsteroidField, DebrisField, IceField):
        install(game, cls((0, 0), 'Sol', FieldDensity.HIGH))
    wing = moving_ship(game, 100, Position(1000, 0), hull=HullSize.STRIKECRAFT_WING)
    ordinary = moving_ship(game, 100, Position(1000, 0))
    assert sublight_speed(wing) == 100 and sublight_speed(ordinary) == 65
    modifiers = modifiers_for_unit(wing)
    assert modifiers.beam_cover == .15 and modifiers.kinetic_missile_cover == .15 and modifiers.cooldown_reduction == 1
    hp = wing.current_hit_points
    processor = TurnProcessor(game)
    processor._process_environmental_hazards(wing.owner, processor._process_movement(wing.owner))
    assert wing.current_hit_points == hp


def test_arrival_receipt_reaches_owner_turn_hazards_and_expires():
    game = campaign()
    install(game, DebrisField((0, 0), 'Sol'))
    unit = moving_ship(game, 80, Position(101, 0))
    processor = TurnProcessor(game)
    hp = unit.current_hit_points
    processor.process_player_turn(unit.owner)
    assert unit.position.x == 101 and unit.current_hit_points == hp - 2
    game.turn_number += 1
    processor.process_player_turn(unit.owner)
    assert unit.current_hit_points == hp - 2


def test_tractor_only_displacement_does_not_cause_abrasion():
    from tactical_abilities import activate, process_pulls
    from unit_components.abilities import AbilityComponent
    from unit_components.enums import AbilityType
    game = campaign()
    body = install(game, DebrisField((0, 0), 'Sol', FieldDensity.LOW))
    body.radius, body.position = 200, Position(100, 0)
    caster = ship(game, hull=HullSize.LARGE)
    caster.add_component(Engines(caster, speed=100))
    caster.add_component(AbilityComponent(caster, [AbilityType.TRACTOR_TETHER]))
    target = ship(game, 'tow', hull=HullSize.SMALL)
    target.add_component(Engines(target, speed=100))
    target.position = Position(450, 0)
    assert activate(caster, 'tractor_tether', game.galaxy, target.id)
    hp = target.current_hit_points
    processor = TurnProcessor(game)
    records = processor._process_movement(caster.owner)
    process_pulls(game.galaxy, caster.owner, game.turn_number)
    assert distance(target.position, body.position) <= body.radius
    assert target.position.x < 450 and target.id not in records
    processor._process_environmental_hazards(caster.owner, records)
    assert target.current_hit_points == hp


def test_jump_into_debris_does_not_cause_abrasion():
    from unit_components.movement import Hyperdrive
    from unit_components.enums import HyperdriveType
    game = campaign()
    install(game, DebrisField((1, 0), 'Sol'))
    unit = moving_ship(game, 100, Position(100, 0))
    unit.commander_component.clear_explicit_orders()
    drive = Hyperdrive(unit, drive_type=HyperdriveType.BASIC, jump_range=2)
    unit.add_component(drive)
    order = ReachWaypointOrder(unit, {'destination_system_name': 'Sol',
        'destination_hex_coord': (1, 0), 'destination_position': Position(100, 0)})
    order.status = OrderStatus.IN_PROGRESS
    unit.commander_component.current_order = order
    drive.set_hex_jump_target(((1, 0), Position(100, 0)), order.local_order_id)
    hp = unit.current_hit_points
    processor = TurnProcessor(game)
    records = processor._process_movement(unit.owner)
    assert unit.in_hex == (1, 0) and unit.id not in records
    processor._process_environmental_hazards(unit.owner, records)
    assert unit.current_hit_points == hp


def test_hazards_keep_owner_timing_overlap_and_stored_exclusions():
    game = campaign()
    for _ in range(2):
        install(game, Storm((0, 0), 'Sol', StormType.PLASMA))
    own, enemy = ship(game), ship(game, 'enemy', owner=1)
    hidden, docked = ship(game, 'hidden'), ship(game, 'docked')
    hidden.is_hidden_in_gas_giant = True
    game.galaxy.systems['Sol'].hexes[(0, 0)].units.remove(docked)
    hp = own.current_hit_points
    own.damage_reduction = .5
    processor = TurnProcessor(game)
    processor._process_environmental_hazards(own.owner)
    assert own.current_hit_points == hp - 8
    assert enemy.current_hit_points == hidden.current_hit_points == docked.current_hit_points == hp
    assert modifiers_for_unit(hidden).beam_cover == modifiers_for_unit(docked).beam_cover == 0
    processor._process_environmental_hazards(enemy.owner)
    assert own.current_hit_points == hp - 8 and enemy.current_hit_points == hp - 16


@pytest.mark.parametrize('kind,key,value,relation', [
    (NebulaType.HYDROGEN, 'hydrogen_fuel_multiplier', .25, 'friendly'),
    (NebulaType.NITROGEN, 'nitrogen_cooldown_reduction', 2, 'friendly'),
    (NebulaType.OXYGEN, 'oxygen_splash_multiplier', 1.35, 'enemy'),
    (NebulaType.DUST, 'dust_sensor_multiplier', .5, 'enemy'),
])
def test_catalyst_describes_only_its_nebula(kind, key, value, relation):
    from domain.deployables import CatalystPatch
    from game_ai.tactical import patch_views
    from tactical_ui import patch_panel
    game = campaign()
    body = install(game, Nebula((0, 0), 'Sol', kind))
    patch = CatalystPatch(game.players[0], Position(0, 0), (0, 0), 'Sol', 1, body.id, 10)
    game.galaxy.systems['Sol'].hexes[(0, 0)].catalyst_patches.append(patch)
    view = patch_views(game, game.players[0])[0]
    assert view[f'{relation}_effects'] == {key: value}
    assert view['enemy_effects' if relation == 'friendly' else 'friendly_effects'] == {}
    panel = [row.get('text') for row in patch_panel(game, body, show_rules=True)]
    assert all(rule in panel for rule in view['rules'])


def test_remote_terrain_and_enemy_equipment_stay_private():
    game = campaign()
    own = ship(game)
    enemy = ship(game, 'enemy', owner=1)
    hidden_body = install(game, Storm((1, 0), 'Beta', StormType.RADIATION))
    known_body = install(game, Storm((0, 0), 'Sol', StormType.PLASMA))
    observed = build_observation(game, own.owner)
    assert observed['schema_version'] == 12
    beta = next(s for s in observed['systems'] if s['name'] == 'Beta')
    assert beta['detail_level'] == 'summary'
    assert hidden_body.id not in [b['id'] for b in beta['notable_bodies']]
    sol = next(s for s in observed['systems'] if s['name'] == 'Sol')
    assert next(b for b in sol['celestial_bodies'] if b['id'] == known_body.id)['environmental_effects']['hazards']
    enemy_view = next(u for u in observed['units'] if u['id'] == enemy.id)
    assert 'capability_details' not in enemy_view and 'environmental_modifiers' not in enemy_view


@pytest.mark.filterwarnings('error:Label Rect is too small:UserWarning')
@pytest.mark.parametrize('size', [(1280, 720), (2560, 1440)])
@pytest.mark.parametrize('show_rules', [False, True])
def test_celestial_panels_wrap_scroll_and_keep_actions(game_factory, tmp_path, size, show_rules):
    import pygame
    import pygame_gui
    from display_config import DisplayConfig
    game = game_factory(display_config=DisplayConfig(*size, fullscreen=False))
    assert game.start_new_game()
    system_name = next(iter(game.galaxy.systems))
    bodies = [Star(system_name, StarType.BLUE_GIANT),
              DebrisField((0, 0), system_name, FieldDensity.HIGH),
              Nebula((0, 0), system_name, NebulaType.NITROGEN),
              Storm((0, 0), system_name, StormType.MAGNETIC),
              Planet((0, 0), system_name, PlanetType.GAS_GIANT)]
    # Include a real departure action after the atmospheric-hiding explanation.
    for number in range(16):
        hidden = ship(game, f'Ship {number}', system=system_name)
        game.galaxy.systems[system_name].hexes[(0, 0)].units.remove(hidden)
        hidden.is_hidden_in_gas_giant = True
        bodies[-1].hidden_units.append(hidden)
    for index, body in enumerate(bodies):
        rows = build_celestial_body_panel(game, body, show_rules=show_rules)
        gui = game.gui
        gui.update_side_bar_content(rows)
        gui.manager.update(.1)
        scroll = gui.side_bar_scroll_container
        content = scroll.get_container().get_rect()
        assert scroll.horiz_scroll_bar is None
        assert scroll.vert_scroll_bar.start_percentage == 0
        for element in gui.side_bar_dynamic_elements:
            rect = element.get_relative_rect()
            assert rect.left >= 0 and rect.right <= content.width
            assert rect.top >= 0 and rect.bottom <= content.height
            if isinstance(element, pygame_gui.elements.UILabel):
                assert element.font.get_rect(element.text).width <= rect.width
        game.screen.fill((5, 10, 20))
        gui.manager.draw_ui(game.screen)
        pygame.image.save(game.screen, str(tmp_path / f'body-{index}-top.png'))
        scroll.vert_scroll_bar.set_scroll_from_start_percentage(1)
        gui.manager.update(.1)
        game.screen.fill((5, 10, 20))
        gui.manager.draw_ui(game.screen)
        pygame.image.save(game.screen, str(tmp_path / f'body-{index}-bottom.png'))
        if index == 4 and not show_rules:
            assert scroll.vert_scroll_bar.start_percentage > 0
            button = [b for b, action in gui.dynamic_button_actions.items()
                      if action['action_id'] == 'order_unit_leave_gas_giant'][-1]
            assert game.screen.get_rect().contains(button.get_abs_rect())
        before = scroll.vert_scroll_bar.start_percentage
        gui.update_side_bar_content(rows)
        assert scroll.vert_scroll_bar.start_percentage == pytest.approx(before)
