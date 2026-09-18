"""tests/test_sector_context_menu.py

Tests for right-click context menu options in sector view:
- Verifies placeholder options ('View Planet', 'View Star', 'View Wormhole Info', 'View Unit Info', 'View Nebula') are not present.
- Verifies celestial bodies and units without actionable orders yield empty option lists.
- Verifies valid orders (Colonize, Resupply, Jump Wormhole, Attack, Protect) appear without placeholders when compatible units are selected.
"""
import pytest
from unittest.mock import MagicMock
from geometry import Position
from constants import HullSize, PlanetType, NebulaType, StarType
from domain.players import Player
from domain.units import Unit
from domain.celestials import Planet, Star, Wormhole, Nebula
from galaxy import Galaxy, StarSystem
from unit_components.movement import Hyperdrive, Engines
from unit_components.commander import Commander
from unit_components.weapons import Weapons, Turret
from unit_components.colony import ColonyComponent
from unit_components.antimatter import AntimatterHarvester, AntimatterStorage
from unit_components.enums import HyperdriveType, TurretType
from input_processor.context_menu_builder import build_sector_context_menu_options


@pytest.fixture
def sector_setup():
    p1 = Player("Player 1", (0, 0, 255))
    p2 = Player("Player 2", (255, 0, 0))
    p1.team_id = 1
    p2.team_id = 2

    galaxy = Galaxy()
    system = StarSystem(name="Sol", position=Position(0, 0), radius=3)
    galaxy.systems = {"Sol": system}

    game = MagicMock()
    game.galaxy = galaxy
    game.players = [p1, p2]
    game.current_player_index = 0
    game.current_system_name = "Sol"
    game.current_sector_coord = (0, 0)
    game.selected_objects = []
    game.event_bus = MagicMock()
    return p1, p2, galaxy, system, game


def test_sector_context_menu_planet_no_view_planet_placeholder(sector_setup):
    p1, p2, galaxy, system, game = sector_setup
    planet = Planet(in_hex=(0, 0), in_system="Sol", planet_type=PlanetType.TERRAN)
    planet.name = "Earth"

    # 1. No units selected -> empty options, no "View Planet"
    options, _ = build_sector_context_menu_options(game, planet, Position(0, 0))
    labels = [opt[0] for opt in options if isinstance(opt[0], str)]
    action_ids = [opt[1] for opt in options if isinstance(opt[1], str)]
    assert "View Planet" not in labels
    assert "view_planet" not in action_ids
    assert options == []

    # 2. Colonizer unit selected -> offers "Colonize", but no "View Planet"
    colonizer = Unit(p1, Position(10, 10), (0, 0), "Sol", "Colonizer", HullSize.MEDIUM, game)
    colonizer.add_component(Commander(colonizer))
    col_comp = ColonyComponent(colonizer)
    col_comp.population_cargo = 50
    colonizer.add_component(col_comp)
    game.selected_objects = [colonizer]

    options, _ = build_sector_context_menu_options(game, planet, Position(0, 0))
    labels = [opt[0] for opt in options if isinstance(opt[0], str)]
    action_ids = [opt[1] for opt in options if isinstance(opt[1], str)]
    assert "View Planet" not in labels
    assert "view_planet" not in action_ids
    assert "Colonize" in labels
    assert "colonize" in action_ids


def test_sector_context_menu_star_no_view_star_placeholder(sector_setup):
    p1, p2, galaxy, system, game = sector_setup
    star = Star(in_system="Sol", star_type=StarType.G_TYPE)
    star.name = "Sun"

    # 1. No units selected -> empty options, no "View Star"
    options, _ = build_sector_context_menu_options(game, star, Position(0, 0))
    labels = [opt[0] for opt in options if isinstance(opt[0], str)]
    action_ids = [opt[1] for opt in options if isinstance(opt[1], str)]
    assert "View Star" not in labels
    assert "view_star" not in action_ids
    assert options == []

    # 2. Harvester unit selected -> offers "Resupply (continuously)...", but no "View Star"
    harvester = Unit(p1, Position(10, 10), (0, 0), "Sol", "Harvester", HullSize.MEDIUM, game)
    harvester.add_component(Commander(harvester))
    harvester.add_component(AntimatterHarvester(harvester))
    storage = AntimatterStorage(harvester, max_capacity=100.0)
    storage.current_amount = 50.0
    harvester.add_component(storage)
    game.selected_objects = [harvester]

    options, _ = build_sector_context_menu_options(game, star, Position(0, 0))
    labels = [opt[0] for opt in options if isinstance(opt[0], str)]
    action_ids = [opt[1] for opt in options if isinstance(opt[1], str)]
    assert "View Star" not in labels
    assert "view_star" not in action_ids
    assert "Resupply (continuously)..." in labels
    assert "continuous_resupply" in action_ids


def test_sector_context_menu_wormhole_no_view_wormhole_placeholder(sector_setup):
    p1, p2, galaxy, system, game = sector_setup
    wormhole = Wormhole(in_hex=(0, 0), in_system="Sol", exit_system_name="Alpha Centauri")
    wormhole.name = "Alpha Centauri Wormhole"

    # 1. No units selected -> empty options, no "View Wormhole Info"
    options, _ = build_sector_context_menu_options(game, wormhole, Position(0, 0))
    labels = [opt[0] for opt in options if isinstance(opt[0], str)]
    action_ids = [opt[1] for opt in options if isinstance(opt[1], str)]
    assert "View Wormhole Info" not in labels
    assert "view_wormhole" not in action_ids
    assert options == []

    # 2. Advanced Hyperdrive unit selected -> offers "Jump Wormhole", but no "View Wormhole Info"
    adv_ship = Unit(p1, Position(10, 10), (0, 0), "Sol", "Explorer", HullSize.SMALL, game)
    adv_ship.add_component(Commander(adv_ship))
    adv_ship.add_component(Hyperdrive(adv_ship, drive_type=HyperdriveType.ADVANCED))
    game.selected_objects = [adv_ship]

    options, _ = build_sector_context_menu_options(game, wormhole, Position(0, 0))
    labels = [opt[0] for opt in options if isinstance(opt[0], str)]
    action_ids = [opt[1] for opt in options if isinstance(opt[1], str)]
    assert "View Wormhole Info" not in labels
    assert "view_wormhole" not in action_ids
    assert "Jump Wormhole" in labels
    assert "jump_wormhole" in action_ids


def test_sector_context_menu_units_no_view_unit_placeholder(sector_setup):
    p1, p2, galaxy, system, game = sector_setup

    friendly_target = Unit(p1, Position(100, 100), (0, 0), "Sol", "Friendly Frigate", HullSize.MEDIUM, game)
    friendly_target.add_component(Commander(friendly_target))

    enemy_target = Unit(p2, Position(200, 200), (0, 0), "Sol", "Enemy Frigate", HullSize.MEDIUM, game)
    enemy_target.add_component(Commander(enemy_target))

    # 1. No units selected -> right-clicking friendly or enemy unit yields empty options, no "View Unit Info"
    options_f, _ = build_sector_context_menu_options(game, friendly_target, Position(100, 100))
    assert "View Unit Info" not in [opt[0] for opt in options_f if isinstance(opt[0], str)]
    assert "view_unit" not in [opt[1] for opt in options_f if isinstance(opt[1], str)]
    assert options_f == []

    options_e, _ = build_sector_context_menu_options(game, enemy_target, Position(200, 200))
    assert "View Unit Info" not in [opt[0] for opt in options_e if isinstance(opt[0], str)]
    assert "view_unit" not in [opt[1] for opt in options_e if isinstance(opt[1], str)]
    assert options_e == []

    # 2. Combat unit selected -> offers "Protect" on friendly, "Attack Hull" on enemy; no "View Unit Info"
    active_unit = Unit(p1, Position(50, 50), (0, 0), "Sol", "My Battleship", HullSize.LARGE, game)
    active_unit.add_component(Commander(active_unit))
    weapons = Weapons(active_unit)
    weapons.turrets.append(Turret(turret_type=TurretType.BEAM, damage=10.0, range=500.0, cooldown=1, parent_unit=active_unit))
    active_unit.add_component(weapons)
    game.selected_objects = [active_unit]

    options_f, _ = build_sector_context_menu_options(game, friendly_target, Position(100, 100))
    labels_f = [opt[0] for opt in options_f if isinstance(opt[0], str)]
    action_ids_f = [opt[1] for opt in options_f if isinstance(opt[1], str)]
    assert "View Unit Info" not in labels_f
    assert "view_unit" not in action_ids_f
    assert "Protect" in labels_f
    assert "protect_unit" in action_ids_f

    options_e, _ = build_sector_context_menu_options(game, enemy_target, Position(200, 200))
    labels_e = [opt[0] for opt in options_e if isinstance(opt[0], str)]
    action_ids_e = [opt[1] for opt in options_e if isinstance(opt[1], str)]
    assert "View Unit Info" not in labels_e
    assert "view_unit" not in action_ids_e
    assert "Attack Hull" in labels_e
    assert "attack_unit" in action_ids_e


def test_sector_context_menu_nebula_no_view_nebula_placeholder(sector_setup):
    p1, p2, galaxy, system, game = sector_setup
    h_nebula = Nebula(in_hex=(0, 0), in_system="Sol", nebula_type=NebulaType.HYDROGEN)
    h_nebula.name = "Hydrogen Cloud"

    # 1. No units selected -> empty options, no "View Nebula"
    options, _ = build_sector_context_menu_options(game, h_nebula, Position(0, 0))
    labels = [opt[0] for opt in options if isinstance(opt[0], str)]
    action_ids = [opt[1] for opt in options if isinstance(opt[1], str)]
    assert "View Nebula" not in labels
    assert "view_nebula" not in action_ids
    assert options == []

    # 2. Harvester unit selected -> offers "Resupply (continuously)...", but no "View Nebula"
    harvester = Unit(p1, Position(10, 10), (0, 0), "Sol", "Harvester", HullSize.MEDIUM, game)
    harvester.add_component(Commander(harvester))
    harvester.add_component(AntimatterHarvester(harvester))
    game.selected_objects = [harvester]

    options, _ = build_sector_context_menu_options(game, h_nebula, Position(0, 0))
    labels = [opt[0] for opt in options if isinstance(opt[0], str)]
    action_ids = [opt[1] for opt in options if isinstance(opt[1], str)]
    assert "View Nebula" not in labels
    assert "view_nebula" not in action_ids
    assert "Resupply (continuously)..." in labels
    assert "continuous_resupply" in action_ids


def test_sector_context_menu_empty_coords_behavior(sector_setup):
    p1, p2, galaxy, system, game = sector_setup

    # 1. No units selected -> empty space returns no options
    options, target = build_sector_context_menu_options(game, None, Position(500, 500))
    assert options == []
    assert target == Position(500, 500)

    # 2. Unit with engines selected -> offers Move Here and Patrol Here
    scout = Unit(p1, Position(0, 0), (0, 0), "Sol", "Scout", HullSize.SMALL, game)
    scout.add_component(Commander(scout))
    scout.add_component(Engines(scout, speed=100.0))
    game.selected_objects = [scout]

    options, target = build_sector_context_menu_options(game, None, Position(500, 500))
    labels = [opt[0] for opt in options if isinstance(opt[0], str)]
    action_ids = [opt[1] for opt in options if isinstance(opt[1], str)]
    assert "Move Here" in labels
    assert "issue_move_order" in action_ids
    assert "Patrol Here" in labels
    assert "issue_patrol_order" in action_ids
