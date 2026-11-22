"""Tests for hex selection sidebar sectioning, Ships/Stations split, and disclosure rules."""
import pytest

from constants import FieldDensity, HullSize, NebulaType, PlanetType, StarType, StormType
from display_config import DisplayConfig
from domain.celestials import (
    AsteroidField,
    ColonizableAsteroid,
    Comet,
    DebrisField,
    IceField,
    MetalAsteroid,
    Moon,
    Nebula,
    Planet,
    Star,
    Storm,
    Wormhole,
)
from domain.construction_job import ConstructionJob
from domain.deployables import Deployable
from domain.minefields import Minefield
from domain.units import Unit
from game import Game
from game_actions import handle_gui_action
from geometry import Position
from gui.dynamic_actions import build_button_payload
from gui.sidebar.panels_world import build_hex_panel
from tests.support.campaigns import campaign, ship
from unit_components.constructor import Constructor
from unit_components.movement import Engines


def _sections(payload):
    """Groups hex panel items by top-level section header text."""
    grouped = {}
    current = None
    for item in payload:
        if item.get('type') == 'label' and item.get('object_id') == '#sidebar_component_header_label':
            current = item['text']
            assert current not in grouped
            grouped[current] = []
        elif current is not None:
            grouped[current].append(item)
    return grouped


def test_hex_sidebar_splits_units_into_ships_and_stations():
    game = campaign()
    game.is_unit_visible = lambda _u: True
    game.is_minefield_visible = lambda _mf: True
    game.hex_has_presence = lambda *_args: False

    sector = game.galaxy.systems['Sol'].hexes[(0, 0)]
    sector.celestial_bodies.clear()

    frigate = ship(game, 'Kinetic Frigate', hull=HullSize.MEDIUM)
    frigate.add_component(Engines(frigate, speed=120))

    wing = ship(game, 'Fighter Wing', hull=HullSize.STRIKECRAFT_WING)
    wing.add_component(Engines(wing, speed=300))

    disabled_ship = ship(game, 'Crippled Scout', hull=HullSize.SMALL)
    broken_engines = Engines(disabled_ship, speed=150)
    broken_engines.current_hit_points = 0
    disabled_ship.add_component(broken_engines)

    shipyard = ship(game, 'Shipyard', hull=HullSize.SMALL)
    platform = ship(game, 'Missile Platform', hull=HullSize.TINY)
    platform.is_temporary = True

    payload = build_hex_panel(game, sector)
    sections = _sections(payload)
    assert list(sections) == ['Units:']

    unit_rows = sections['Units:']
    assert [(row['type'], row['text'], row.get('indent_level', 0)) for row in unit_rows] == [
        ('label', 'Ships (3):', 1),
        ('button', 'Kinetic Frigate', 2),
        ('button', 'Fighter Wing', 2),
        ('button', 'Crippled Scout', 2),
        ('label', 'Stations (2):', 1),
        ('button', 'Shipyard', 2),
        ('button', 'Missile Platform', 2),
    ]
    assert all(row['action_id'] == 'select_individual_unit' for row in unit_rows if row['type'] == 'button')


def test_hex_sidebar_omits_empty_unit_subsection():
    game = campaign()
    game.is_unit_visible = lambda _u: True
    game.is_minefield_visible = lambda _mf: True
    game.hex_has_presence = lambda *_args: False

    sector = game.galaxy.systems['Sol'].hexes[(0, 0)]
    sector.celestial_bodies.clear()

    frigate = ship(game, 'Solo Frigate', hull=HullSize.MEDIUM)
    frigate.add_component(Engines(frigate, speed=120))

    only_ships = _sections(build_hex_panel(game, sector))['Units:']
    assert [row['text'] for row in only_ships] == ['Ships (1):', 'Solo Frigate']

    sector.units.clear()
    ship(game, 'Solo Station', hull=HullSize.SMALL)

    only_stations = _sections(build_hex_panel(game, sector))['Units:']
    assert [row['text'] for row in only_stations] == ['Stations (1):', 'Solo Station']


def test_hex_sidebar_groups_all_object_types_clearly():
    game = campaign()
    game.is_unit_visible = lambda _u: True
    game.is_minefield_visible = lambda _mf: True
    game.hex_has_presence = lambda *_args: False

    p1 = game.players[0]
    sector = game.galaxy.systems['Sol'].hexes[(0, 0)]
    sector.celestial_bodies.clear()

    wh = Wormhole((0, 0), 'Sol', 'Beta')
    wh.name = 'Wormhole 1'
    star = Star('Sol', StarType.G_TYPE)
    star.name = 'Sol Star'
    planet = Planet((0, 0), 'Sol', PlanetType.GAS_GIANT)
    planet.name = 'Gas Giant 1'
    moon = Moon((0, 0), 'Sol')
    moon.name = 'Moon 1'
    col_ast = ColonizableAsteroid((0, 0), 'Sol')
    col_ast.name = 'Col Asteroid 1'
    metal = MetalAsteroid((0, 0), 'Sol')
    metal.name = 'Metal Asteroid 1'
    comet = Comet((0, 0), 'Sol')
    comet.name = 'Comet 1'
    ast_field = AsteroidField((0, 0), 'Sol', FieldDensity.LOW)
    ast_field.name = 'Asteroid Field 1'
    ice_field = IceField((0, 0), 'Sol', FieldDensity.MEDIUM)
    ice_field.name = 'Ice Field 1'
    debris = DebrisField((0, 0), 'Sol', FieldDensity.HIGH)
    debris.name = 'Debris Field 1'
    nebula = Nebula((0, 0), 'Sol', NebulaType.HYDROGEN)
    nebula.name = 'Hydrogen Nebula 1'
    storm = Storm((0, 0), 'Sol', StormType.PLASMA)
    storm.name = 'Plasma Storm 1'

    for body in (wh, star, planet, moon, col_ast, metal, comet, ast_field, ice_field, debris, nebula, storm):
        game.galaxy.systems['Sol'].add_celestial_body(body)

    cruiser = ship(game, 'Cruiser', hull=HullSize.MEDIUM)
    cruiser.add_component(Engines(cruiser, speed=100))

    builder = ship(game, 'Shipyard', hull=HullSize.SMALL)
    constructor = Constructor(builder)
    constructor.current_construction_target = {
        'template_name': 'Missile Frigate',
        'system_name': 'Sol',
        'hex_coord': (0, 0),
        'position': Position(150, 0),
    }
    constructor.construction_progress = 3
    constructor.time_to_build = 10
    builder.add_component(constructor)

    hidden_ship = Unit(p1, Position(0, 0), (0, 0), 'Sol', 'Submerged Raider', HullSize.SMALL, game)
    hidden_ship.add_component(Engines(hidden_ship, speed=150))
    assert planet.hide_unit(hidden_ship, game.galaxy)

    emitter = Deployable(p1, Position(200, 0), (0, 0), 'Sol', 'ghost_fleet', cruiser.id, game.galaxy)
    sector.deployables.append(emitter)

    mf = Minefield(p1, Position(-200, 0), (0, 0), 'Sol', mines_remaining=4)
    mf.name = 'Anti-Ship Minefield 9'
    sector.add_minefield(mf)

    payload = build_hex_panel(game, sector)
    sections = _sections(payload)

    assert list(sections) == [
        'Wormholes:',
        'Celestial Bodies:',
        'Resource Bodies:',
        'Environment:',
        'Units:',
        'Submerged Ships:',
        'Construction Sites:',
        'Deployables:',
        'Minefields:',
    ]
    assert [row['text'] for row in sections['Wormholes:']] == ['Wormhole 1 → Beta']
    assert [row['text'] for row in sections['Celestial Bodies:']] == [
        'Sol Star', 'Gas Giant 1', 'Moon 1', 'Col Asteroid 1',
    ]
    assert [row['text'] for row in sections['Resource Bodies:']] == ['Metal Asteroid 1', 'Comet 1']
    assert [row['text'] for row in sections['Environment:']] == [
        'Asteroid Field 1', 'Ice Field 1', 'Debris Field 1', 'Hydrogen Nebula 1', 'Plasma Storm 1',
    ]
    assert [row['text'] for row in sections['Units:']] == [
        'Ships (1):', 'Cruiser', 'Stations (1):', 'Shipyard',
    ]
    assert [row['text'] for row in sections['Submerged Ships:']] == ['Submerged Raider']
    assert [row['text'] for row in sections['Construction Sites:']] == ['Missile Frigate (3/10t)']
    assert [row['text'] for row in sections['Deployables:']] == ['Ghost Emitter (Persistent)']
    assert [row['text'] for row in sections['Minefields:']] == ['Anti-Ship Minefield 9 (4 mines)']

    # Clicking the construction site button selects the ConstructionJob
    site_button = sections['Construction Sites:'][0]
    action = build_button_payload(None, site_button['action_id'], site_button['target_data'])
    assert action == {'action': 'select_construction_job', 'constructor_unit_id': builder.id}
    handle_gui_action(game, action)
    assert len(game.selected_objects) == 1
    assert isinstance(game.selected_objects[0], ConstructionJob)
    assert game.selected_objects[0].constructor_unit is builder


def test_hex_sidebar_deployable_only_is_not_reported_empty():
    game = campaign()
    game.is_unit_visible = lambda _u: True
    game.is_minefield_visible = lambda _mf: True
    game.hex_has_presence = lambda *_args: False

    sector = game.galaxy.systems['Sol'].hexes[(0, 0)]
    sector.celestial_bodies.clear()
    emitter = Deployable(game.players[0], Position(0, 0), (0, 0), 'Sol', 'ghost_fleet', 999, game.galaxy)
    sector.deployables.append(emitter)

    payload = build_hex_panel(game, sector)
    assert not any(row.get('text') == 'Contains: Nothing' for row in payload)
    sections = _sections(payload)
    assert list(sections) == ['Deployables:']
    assert sections['Deployables:'][0]['action_id'] == 'select_deployable'
    assert sections['Deployables:'][0]['target_data'] == emitter.id


def test_hex_sidebar_respects_disclosure_for_submerged_sites_and_allied_presence():
    game = campaign()
    p1, p2 = game.players[0], game.players[1]
    sector = game.galaxy.systems['Sol'].hexes[(0, 0)]
    sector.celestial_bodies.clear()

    gas_giant = Planet((0, 0), 'Sol', PlanetType.GAS_GIANT)
    game.galaxy.systems['Sol'].add_celestial_body(gas_giant)

    enemy_hidden = Unit(p2, Position(0, 0), (0, 0), 'Sol', 'Enemy Sub', HullSize.SMALL, game)
    enemy_hidden.add_component(Engines(enemy_hidden, speed=150))
    assert gas_giant.hide_unit(enemy_hidden, game.galaxy)

    enemy_builder = ship(game, 'Enemy Yard', owner=1, hull=HullSize.SMALL)
    constructor = Constructor(enemy_builder)
    constructor.current_construction_target = {
        'template_name': 'Covert Intelligence Ship',
        'system_name': 'Sol',
        'hex_coord': (0, 0),
        'position': Position(100, 0),
    }
    constructor.construction_progress = 2
    constructor.time_to_build = 8
    enemy_builder.add_component(constructor)

    # Enemy builder invisible to P1 -> no Construction Sites, no enemy Submerged Ships
    game.current_player_index = 0
    game.is_unit_visible = lambda u: u.owner == p1
    game.is_minefield_visible = lambda _mf: False
    game.hex_has_presence = lambda *_args: True

    # Add an allied unit to confirm allied visibility doesn't suppress enemy radar warning
    p1.team_id = 1
    ally = ship(game, 'Ally Scout', owner=0, hull=HullSize.SMALL)
    ally.add_component(Engines(ally, speed=120))
    from domain.players import Player
    p3 = Player('Player 3', (0, 255, 0), team_id=1)
    game.players.append(p3)
    ally.owner = p3
    game.is_unit_visible = lambda u: u.owner in (p1, p3)

    payload = build_hex_panel(game, sector)
    sections = _sections(payload)
    assert 'Submerged Ships:' not in sections
    assert 'Construction Sites:' not in sections
    assert any(row.get('text') == '⚠ Enemy presence detected' for row in payload)

    # Clicking a forged select_construction_job for invisible enemy builder does nothing
    game.selected_objects = []
    handle_gui_action(game, {'action': 'select_construction_job', 'constructor_unit_id': enemy_builder.id})
    assert game.selected_objects == []

    # When enemy builder becomes visible, covert ship uses its cover name and radar banner hides
    game.is_unit_visible = lambda _u: True
    payload_visible = build_hex_panel(game, sector)
    sections_visible = _sections(payload_visible)
    assert sections_visible['Construction Sites:'][0]['text'] == 'Patrol Escort (2/8t)'
    assert not any(row.get('text') == '⚠ Enemy presence detected' for row in payload_visible)


@pytest.mark.filterwarnings('error:Label Rect is too small:UserWarning')
def test_hex_sidebar_renders_in_hud_without_warnings(pygame_context):
    from gui.handler import GUI_Handler

    size = (1280, 720)
    pygame_context.display.set_mode(size)
    game = campaign()
    game.display_config = DisplayConfig(*size, fullscreen=False)
    game.is_unit_visible = lambda _u: True
    game.is_minefield_visible = lambda _mf: True
    game.hex_has_presence = lambda *_args: False

    sector = game.galaxy.systems['Sol'].hexes[(0, 0)]
    sector.celestial_bodies.clear()
    game.galaxy.systems['Sol'].add_celestial_body(Wormhole((0, 0), 'Sol', 'Alpha Centauri'))
    game.galaxy.systems['Sol'].add_celestial_body(Planet((0, 0), 'Sol', PlanetType.TERRAN))
    game.galaxy.systems['Sol'].add_celestial_body(MetalAsteroid((0, 0), 'Sol'))
    game.galaxy.systems['Sol'].add_celestial_body(Nebula((0, 0), 'Sol', NebulaType.HYDROGEN))

    frigate = ship(game, 'Kinetic Frigate', hull=HullSize.MEDIUM)
    frigate.add_component(Engines(frigate, speed=120))
    ship(game, 'Shipyard', hull=HullSize.SMALL)

    game.gui = gui = GUI_Handler(game.display_config, game)
    try:
        gui.show_game_ui()
        game.selected_objects = [sector]
        game.sidebar_needs_update = True
        Game.update_side_bar_content(game)
        gui.manager.update(0.1)
        assert gui.side_bar_dynamic_elements
    finally:
        gui.clear_and_reset()
