"""Unit tests verifying that sector object click radius corresponds directly to
real object radius, without the former 1.5x multiplier.
"""
from display_config import DisplayConfig
from unittest.mock import MagicMock
import pytest
from constants import (
    HullSize, PlanetType, StarType, HULL_BASE_ICON_SCALES,
    SECTOR_VIEW_BASE_ICON_SIZE, STAR_RADIUS, PLANET_RADIUS
)
import constants
from geometry import Position
from domain.units import Unit
from domain.celestials import Planet, Star
from domain.construction_job import ConstructionJob
from domain.minefields import Minefield
from unit_components.enums import MinefieldType
from domain.players import Player
from galaxy import Galaxy, StarSystem, Hex
from input_processor import InputProcessor, get_units_under_mouse
from sector_utils import (
    sector_coords_to_pixels,
    sector_radius_to_pixels,
    get_minefield_dot_pixel_positions,
    get_minefield_dot_radius_px,
)


def _setup_mock_game_in_sector():
    game = MagicMock()
    game.display_config = DisplayConfig()
    game.view_mode = 'sector'
    game.current_system_name = 'Sol'
    game.current_sector_coord = (0, 0)
    game.sector_zoom = 1.0
    game.sector_pan_offset = Position(0, 0)
    game.selected_objects = []
    game.sector_view_mouse_hover_object = None
    game.is_unit_visible = MagicMock(return_value=True)
    game.is_minefield_visible = MagicMock(return_value=True)
    game.pending_ability = None

    galaxy = Galaxy(num_systems=0)
    system = StarSystem("Sol", Position(0, 0))
    hex_obj = Hex(0, 0, "Sol")
    system.hexes[(0, 0)] = hex_obj
    galaxy.systems["Sol"] = system
    game.galaxy = galaxy

    p1 = Player(name="Player 1", color=(0, 100, 255))
    game.players = [p1]
    game.current_player_index = 0
    game.current_player = p1

    gui = MagicMock()
    gui.display_config = DisplayConfig()
    gui.is_mouse_over_context_menu = MagicMock(return_value=False)
    gui.is_mouse_over_gui_panels = MagicMock(return_value=False)
    game.gui = gui

    return game, hex_obj, p1


def test_sector_object_click_radius_mult_constant_removed():
    """Verify SECTOR_OBJECT_CLICK_RADIUS_MULT is no longer in constants."""
    assert not hasattr(constants, "SECTOR_OBJECT_CLICK_RADIUS_MULT")


def test_unit_click_radius_matches_real_radius():
    """Verify unit hover and selection bounds match real icon radius, not 1.5x."""
    game, hex_obj, p1 = _setup_mock_game_in_sector()
    game.sector_zoom = 3.0  # Sufficient zoom so obj_radius > 5px floor

    unit = Unit(
        owner=p1,
        position=Position(100, 100),
        in_hex=(0, 0),
        in_system="Sol",
        name="Test Cruiser",
        hull_size=HullSize.LARGE,
        game=game,
    )
    hex_obj.units = [unit]

    scale_factor = HULL_BASE_ICON_SCALES[unit.hull_size]
    effective_icon_size = SECTOR_VIEW_BASE_ICON_SIZE * scale_factor
    obj_radius = sector_radius_to_pixels(effective_icon_size, game.sector_zoom, display_config=game.display_config)
    assert obj_radius > 5.0  # Ensure we test the real radius boundary, not the 5px floor
    unit_pixel_pos = sector_coords_to_pixels(unit.position, game.sector_zoom, game.sector_pan_offset, display_config=game.display_config)

    ip = InputProcessor(game)

    # 1. Point strictly inside real radius
    inside_pos = Position(unit_pixel_pos.x + obj_radius - 2.0, unit_pixel_pos.y)
    ip.update_hover_states(inside_pos)
    assert game.sector_view_mouse_hover_object == unit
    assert get_units_under_mouse(game, inside_pos) == [unit]

    # 2. Point strictly outside real radius, but inside the former 1.5x multiplier zone (e.g., 1.2x)
    former_mult_pos = Position(unit_pixel_pos.x + obj_radius * 1.2, unit_pixel_pos.y)
    ip.update_hover_states(former_mult_pos)
    assert game.sector_view_mouse_hover_object is None
    assert get_units_under_mouse(game, former_mult_pos) == []

    # 3. Point just outside real radius
    outside_pos = Position(unit_pixel_pos.x + obj_radius + 2.0, unit_pixel_pos.y)
    ip.update_hover_states(outside_pos)
    assert game.sector_view_mouse_hover_object is None
    assert get_units_under_mouse(game, outside_pos) == []


def test_solid_celestial_click_radius_matches_real_radius():
    """Verify solid celestial bodies match collision radius, rejecting former 1.5x zone."""
    game, hex_obj, p1 = _setup_mock_game_in_sector()

    planet = Planet(in_hex=(0, 0), in_system="Sol", planet_type=PlanetType.TERRAN)
    planet.id = 201
    planet.position = Position(0, 0)
    planet.collision_radius = PLANET_RADIUS
    hex_obj.celestial_bodies = [planet]

    obj_radius = sector_radius_to_pixels(PLANET_RADIUS, game.sector_zoom, display_config=game.display_config)
    assert obj_radius > 5.0
    planet_pixel_pos = sector_coords_to_pixels(planet.position, game.sector_zoom, game.sector_pan_offset, display_config=game.display_config)

    ip = InputProcessor(game)

    # Inside real radius
    inside_pos = Position(planet_pixel_pos.x + obj_radius - 3.0, planet_pixel_pos.y)
    ip.update_hover_states(inside_pos)
    assert game.sector_view_mouse_hover_object == planet

    # Inside former 1.5x zone (1.25x real radius)
    former_mult_pos = Position(planet_pixel_pos.x + obj_radius * 1.25, planet_pixel_pos.y)
    ip.update_hover_states(former_mult_pos)
    assert game.sector_view_mouse_hover_object is None


def test_construction_job_click_radius_matches_real_radius():
    """Verify construction jobs match real icon radius without multiplier."""
    game, hex_obj, p1 = _setup_mock_game_in_sector()
    game.sector_zoom = 3.0

    builder = Unit(
        owner=p1,
        position=Position(50, 50),
        in_hex=(0, 0),
        in_system="Sol",
        name="Constructor",
        hull_size=HullSize.MEDIUM,
        game=game,
    )
    job = ConstructionJob(builder)
    job.hull_size = HullSize.LARGE
    job.position = Position(50, 50)

    scale_factor = HULL_BASE_ICON_SCALES[job.hull_size]
    effective_icon_size = SECTOR_VIEW_BASE_ICON_SIZE * scale_factor
    obj_radius = sector_radius_to_pixels(effective_icon_size, game.sector_zoom, display_config=game.display_config)
    assert obj_radius > 5.0
    job_pixel_pos = sector_coords_to_pixels(job.position, game.sector_zoom, game.sector_pan_offset, display_config=game.display_config)

    ip = InputProcessor(game)

    from unittest.mock import patch
    with patch("domain.construction_job.get_sector_construction_jobs", return_value=[job]):
        inside_pos = Position(job_pixel_pos.x + obj_radius - 2.0, job_pixel_pos.y)
        ip.update_hover_states(inside_pos)
        assert game.sector_view_mouse_hover_object == job

        outside_pos = Position(job_pixel_pos.x + obj_radius * 1.25, job_pixel_pos.y)
        ip.update_hover_states(outside_pos)
        assert game.sector_view_mouse_hover_object is None


def test_minefield_dot_click_radius_matches_real_radius():
    """Verify minefield dots hover when within dot radius, rejecting outside."""
    game, hex_obj, p1 = _setup_mock_game_in_sector()

    mf = Minefield(
        owner=p1,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        minefield_type=MinefieldType.ANTI_SHIP,
        mines_remaining=3,
    )
    hex_obj.add_minefield(mf)

    dot_positions = get_minefield_dot_pixel_positions(
        mf.position, mf.mines_remaining, game.sector_zoom, game.sector_pan_offset, display_config=game.display_config
    )
    first_dot_pos = Position(dot_positions[0][0], dot_positions[0][1])
    dot_radius = max(get_minefield_dot_radius_px(game.sector_zoom, display_config=game.display_config), 5.0)

    ip = InputProcessor(game)

    # Center of first dot
    ip.update_hover_states(first_dot_pos)
    assert game.sector_view_mouse_hover_object == mf

    # Outside the dot radius in Y direction (avoiding adjacent dots in X)
    outside_pos = Position(first_dot_pos.x, first_dot_pos.y + dot_radius + 4.0)
    ip.update_hover_states(outside_pos)
    assert game.sector_view_mouse_hover_object is None


def test_minimum_floor_for_heavily_zoomed_out_objects():
    """Verify heavily zoomed-out objects retain a 5px minimum floor so they remain clickable."""
    game, hex_obj, p1 = _setup_mock_game_in_sector()
    game.sector_zoom = 0.05  # extremely zoomed out

    unit = Unit(
        owner=p1,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Tiny Scout",
        hull_size=HullSize.TINY,
        game=game,
    )
    hex_obj.units = [unit]

    scale_factor = HULL_BASE_ICON_SCALES[unit.hull_size]
    effective_icon_size = SECTOR_VIEW_BASE_ICON_SIZE * scale_factor
    obj_radius = sector_radius_to_pixels(effective_icon_size, game.sector_zoom, display_config=game.display_config)
    assert obj_radius < 5.0  # confirm that the natural pixel radius is tiny (< 5px)

    unit_pixel_pos = sector_coords_to_pixels(unit.position, game.sector_zoom, game.sector_pan_offset, display_config=game.display_config)
    ip = InputProcessor(game)

    # Within 5px floor (e.g. 3px)
    within_floor_pos = Position(unit_pixel_pos.x + 3.0, unit_pixel_pos.y)
    ip.update_hover_states(within_floor_pos)
    assert game.sector_view_mouse_hover_object == unit
    assert get_units_under_mouse(game, within_floor_pos) == [unit]

    # Beyond 5px floor (e.g. 7px)
    beyond_floor_pos = Position(unit_pixel_pos.x + 7.0, unit_pixel_pos.y)
    ip.update_hover_states(beyond_floor_pos)
    assert game.sector_view_mouse_hover_object is None
    assert get_units_under_mouse(game, beyond_floor_pos) == []


pytestmark = pytest.mark.usefixtures("pygame_context")
