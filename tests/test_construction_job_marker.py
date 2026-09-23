"""Tests for the visible construction job marker domain, visibility, UI and rendering."""
import pygame
from unittest.mock import MagicMock
from display_config import DisplayConfig
from constants import HullSize
from geometry import Position
from domain.construction_job import ConstructionJob, get_sector_construction_jobs
from unit_components.constructor import Constructor
from tests.support.units import ComponentUnit, ComponentPlayer
from gui.sidebar.panels_world import build_construction_job_panel
from gui.sidebar.builder import build_sidebar_data
from gui.dynamic_actions import build_button_payload
from game_actions.unit_actions import handle_select_constructor_unit, handle_cancel_construction_job
from input_processor.context_menu_builder import build_sector_context_menu_options
from rendering.drawing_utils import draw_wireframe_shape, draw_scaffold_brackets


def _create_constructing_unit(template_name="Missile Frigate", pos=Position(150, 250), progress=3, time_to_build=10):
    unit = ComponentUnit()
    constructor = Constructor(unit, hull_cost=10)
    unit.add_component(constructor)
    constructor.current_construction_target = {
        "template_name": template_name,
        "system_name": unit.in_system,
        "hex_coord": unit.in_hex,
        "position": pos,
    }
    constructor.construction_progress = progress
    constructor.time_to_build = time_to_build
    return unit, constructor


def test_construction_job_properties():
    unit, constructor = _create_constructing_unit("Missile Frigate", Position(100, 200), progress=3, time_to_build=10)
    job = ConstructionJob(unit)

    assert job.position == Position(100, 200)
    assert job.in_system == "Sol"
    assert job.in_hex == (0, 0)
    assert job.owner == unit.owner
    assert job.template_name == "Missile Frigate"
    assert job.display_name == "Missile Frigate"
    assert job.hull_size == HullSize.MEDIUM
    assert job.is_station is False
    assert job.progress == 3
    assert job.time_to_build == 10
    assert job.percent == 30
    assert job.is_valid is True
    assert job.is_solid is True
    assert job.logical_radius > 0
    assert "Missile Frigate" in job.name
    assert repr(job).startswith("<ConstructionJob")


def test_construction_job_station():
    unit, constructor = _create_constructing_unit("Shipyard", Position(50, 50), progress=1, time_to_build=5)
    job = ConstructionJob(unit)

    assert job.is_station is True
    assert job.hull_size == HullSize.SMALL


def test_construction_job_validity_on_cancel_or_destruction():
    unit, constructor = _create_constructing_unit()
    job = ConstructionJob(unit)
    assert job.is_valid is True

    # Cancel construction
    constructor.current_construction_target = None
    assert job.is_valid is False

    # Destroy unit
    constructor.current_construction_target = {"template_name": "Missile Frigate", "system_name": "Sol", "hex_coord": (0, 0), "position": Position(0, 0)}
    unit.is_destroyed = True
    assert job.is_valid is False


def test_construction_job_display_name_enemy_covert_vs_regular():
    p1 = ComponentPlayer("Player 1", player_id=1, team_id=1)
    p2 = ComponentPlayer("Player 2", player_id=2, team_id=2)

    unit, constructor = _create_constructing_unit("Missile Frigate")
    unit.owner = p1
    job = ConstructionJob(unit)

    # For owner or ally: returns template name
    assert job.get_display_name(p1) == "Missile Frigate"

    # For enemy: returns generic hull class
    assert job.get_display_name(p2) == "Construction Site (Medium)"

    # For covert ship: returns cover name "Patrol Escort"
    unit_covert, constructor_covert = _create_constructing_unit("Covert Intelligence Ship")
    unit_covert.owner = p1
    job_covert = ConstructionJob(unit_covert)
    assert job_covert.get_display_name(p2) == "Patrol Escort"


def test_get_sector_construction_jobs():
    unit1, constructor1 = _create_constructing_unit("Missile Frigate", Position(100, 100))
    unit2 = ComponentUnit()  # Idle unit, no construction

    hex_obj = MagicMock()
    hex_obj.coordinates.return_value = (0, 0)
    hex_obj.in_system = "Sol"
    hex_obj.units = [unit1, unit2]

    # Query for owner
    jobs = get_sector_construction_jobs(hex_obj, viewer=unit1.owner)
    assert len(jobs) == 1
    assert jobs[0].template_name == "Missile Frigate"

    # Job in a different hex should not be returned
    constructor1.current_construction_target["hex_coord"] = (1, 1)
    assert len(get_sector_construction_jobs(hex_obj, viewer=unit1.owner)) == 0
    constructor1.current_construction_target["hex_coord"] = (0, 0)

    # Query for enemy
    enemy = ComponentPlayer("Enemy", player_id=2, team_id=2)
    mock_game = MagicMock()
    mock_game.is_unit_visible.return_value = False
    unit1.game = mock_game

    # When unit is invisible to enemy, job is not returned
    assert len(get_sector_construction_jobs(hex_obj, viewer=enemy)) == 0

    # When unit is visible to enemy, job is returned
    mock_game.is_unit_visible.return_value = True
    assert len(get_sector_construction_jobs(hex_obj, viewer=enemy)) == 1


def test_sidebar_construction_job_panel():
    unit, constructor = _create_constructing_unit("Missile Frigate", Position(100, 200), progress=4, time_to_build=10)
    job = ConstructionJob(unit)

    mock_game = MagicMock()
    mock_game.players = [unit.owner]
    mock_game.current_player_index = 0

    panel = build_construction_job_panel(mock_game, job)
    labels = [e for e in panel if e.get("type") == "label"]
    progress_bars = [e for e in panel if e.get("type") == "progress_bar"]
    buttons = [e for e in panel if e.get("type") == "button"]

    assert any("Missile Frigate" in l["text"] for l in labels)
    assert any("Progress: 4 / 10 turns (40%)" in l["text"] for l in labels)
    assert len(progress_bars) == 1
    assert progress_bars[0]["progress"] == 4
    assert progress_bars[0]["total"] == 10

    focus_btn = next((b for b in buttons if b["action_id"] == "select_constructor_unit"), None)
    assert focus_btn is not None
    assert focus_btn["target_data"] == unit.id

    cancel_btn = next((b for b in buttons if b["action_id"] == "cancel_construction_job"), None)
    assert cancel_btn is not None
    assert cancel_btn["target_data"] == unit.id

    # Enemy viewer should not see cancel button
    enemy = ComponentPlayer("Enemy", player_id=2, team_id=2)
    mock_game.players = [enemy]
    enemy_panel = build_construction_job_panel(mock_game, job)
    enemy_cancel_btn = next((b for b in enemy_panel if b.get("action_id") == "cancel_construction_job"), None)
    assert enemy_cancel_btn is None


def test_sidebar_builder_dispatch_construction_job():
    unit, constructor = _create_constructing_unit("Missile Frigate")
    job = ConstructionJob(unit)

    mock_game = MagicMock()
    mock_game.selected_objects = [job]
    mock_game.players = [unit.owner]
    mock_game.current_player_index = 0

    data = build_sidebar_data(mock_game)
    assert any("Missile Frigate" in d.get("text", "") for d in data)


def test_dynamic_actions_and_handlers():
    unit, constructor = _create_constructing_unit("Missile Frigate")

    # Payload builder
    payload_select = build_button_payload(MagicMock(), "select_constructor_unit", unit.id)
    assert payload_select == {"action": "select_constructor_unit", "unit_id": unit.id}

    payload_cancel = build_button_payload(MagicMock(), "cancel_construction_job", unit.id)
    assert payload_cancel == {"action": "cancel_construction_job", "unit_id": unit.id}

    mock_game = MagicMock()
    mock_game.galaxy.get_unit_by_id.return_value = unit
    mock_game.selected_objects = []

    # Handle select
    handle_select_constructor_unit(mock_game, payload_select)
    assert mock_game.selected_objects == [unit]
    assert mock_game.sidebar_needs_update is True

    # Handle cancel
    handle_cancel_construction_job(mock_game, payload_cancel)
    assert constructor.current_construction_target is None


def test_context_menu_for_construction_job():
    unit, constructor = _create_constructing_unit("Missile Frigate")
    job = ConstructionJob(unit)

    mock_game = MagicMock()
    mock_game.players = [unit.owner]
    mock_game.current_player_index = 0
    mock_game.selected_objects = [unit]

    options, target = build_sector_context_menu_options(mock_game, job, job.position)
    assert target == job
    opt_dict = dict(options)
    assert "Select Builder" in opt_dict
    assert "Cancel Construction" in opt_dict


def test_drawing_utils_wireframe_and_scaffold():
    pygame.init()
    surface = pygame.Surface((200, 200))

    # Should execute without errors
    draw_wireframe_shape(surface, 'triangle', (255, 255, 255), Position(50, 50), 20)
    draw_wireframe_shape(surface, 'square', (255, 255, 255), Position(100, 50), 20)
    draw_wireframe_shape(surface, 'strikecraft_wing', (255, 255, 255), Position(150, 50), 20)
    draw_wireframe_shape(surface, 'circle', (255, 255, 255), Position(50, 100), 20)
    draw_scaffold_brackets(surface, (255, 200, 50), Position(100, 100), 20)


def test_sector_entity_renderer_methods():
    pygame.init()
    surface = pygame.Surface((400, 400))

    mock_parent = MagicMock()
    mock_parent.screen = surface
    mock_parent._font_cache = {}
    mock_parent.grid_renderer.coords_to_pixels.side_effect = lambda pos: pos

    from rendering.sector_renderer.sector_entity_renderer import SectorEntityRenderer
    unit, constructor = _create_constructing_unit("Missile Frigate", Position(100, 100), progress=2, time_to_build=8)
    mock_parent.game = MagicMock(display_config=DisplayConfig(), players=[unit.owner], current_player_index=0)
    renderer = SectorEntityRenderer(mock_parent)

    job = ConstructionJob(unit)

    # Test draw_construction_job
    radius = renderer.draw_construction_job(job, Position(100, 100), dynamic_radius=500.0)
    assert radius > 0

    # Test draw_construction_beam
    renderer.draw_construction_beam(job, dynamic_radius=500.0)

