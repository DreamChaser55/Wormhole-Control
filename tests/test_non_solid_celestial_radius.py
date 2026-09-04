"""Unit and integration tests for non-solid celestial body effect radii and turquoise circles."""

import pytest
from unittest.mock import MagicMock, patch

from constants import (
    ASTEROID_FIELD_RADIUS, ICE_FIELD_RADIUS, DEBRIS_FIELD_RADIUS,
    NEBULA_RADIUS, STORM_RADIUS, TURQUOISE, SECTOR_CIRCLE_RADIUS_LOGICAL,
    SECTOR_CIRCLE_RADIUS_IN_PX, PlanetType, NebulaType, StormType, StarType,
    FieldDensity, HYDROGEN_NEBULA_HARVEST_MULTIPLIER
)
from entities import (
    AsteroidField, IceField, DebrisField, Nebula, Storm,
    Planet, Star, Moon, ColonizableAsteroid, MetalAsteroid, Comet, Wormhole,
    NON_SOLID_CELESTIAL_BODIES
)
from geometry import Position
from utils import HexCoord
from game_ai.observation import _body_view
from game_ai.rules import is_antimatter_source
from rendering.sector_renderer.sector_celestial_renderer import SectorCelestialRenderer


def test_effect_radius_attribute_on_non_solid_celestial_bodies():
    """Verify effect_radius matches the exact logical radius on all non-solid bodies."""
    af = AsteroidField(in_hex=HexCoord(0, 0), in_system="Sol")
    assert af.effect_radius == ASTEROID_FIELD_RADIUS == 3600.0
    assert af.is_solid is False

    ice = IceField(in_hex=HexCoord(0, 0), in_system="Sol")
    assert ice.effect_radius == ICE_FIELD_RADIUS == 3600.0
    assert ice.is_solid is False

    df = DebrisField(in_hex=HexCoord(0, 0), in_system="Sol")
    assert df.effect_radius == DEBRIS_FIELD_RADIUS == 2000.0
    assert df.is_solid is False

    nebula = Nebula(in_hex=HexCoord(0, 0), in_system="Sol", nebula_type=NebulaType.HYDROGEN)
    assert nebula.effect_radius == NEBULA_RADIUS == 3600.0
    assert nebula.is_solid is False

    storm = Storm(in_hex=HexCoord(0, 0), in_system="Sol", storm_type=StormType.PLASMA)
    assert storm.effect_radius == STORM_RADIUS == 3600.0
    assert storm.is_solid is False


def test_solid_bodies_effect_radius_default():
    """Solid bodies default to effect_radius 0.0 and is_solid True."""
    star = Star(in_system="Sol", star_type=StarType.G_TYPE)
    assert star.is_solid is True
    assert star.effect_radius == 0.0

    planet = Planet(in_hex=HexCoord(1, 0), in_system="Sol", planet_type=PlanetType.TERRAN)
    assert planet.is_solid is True
    assert planet.effect_radius == 0.0


def test_hydrogen_nebula_harvest_multiplier_and_antimatter_source():
    """Verify Hydrogen nebulae have harvest_multiplier and are recognized by rules."""
    h_nebula = Nebula(in_hex=HexCoord(0, 0), in_system="Sol", nebula_type=NebulaType.HYDROGEN)
    assert h_nebula.harvest_multiplier == HYDROGEN_NEBULA_HARVEST_MULTIPLIER == 0.4
    assert is_antimatter_source(h_nebula) is True

    n_nebula = Nebula(in_hex=HexCoord(0, 0), in_system="Sol", nebula_type=NebulaType.NITROGEN)
    assert n_nebula.harvest_multiplier == 0.0
    assert is_antimatter_source(n_nebula) is False


def test_ai_observation_includes_effect_radius_for_non_solid_bodies():
    """Verify _body_view includes is_solid: false and effect_radius for non-solid bodies."""
    df = DebrisField(in_hex=HexCoord(0, 0), in_system="Sol", density=FieldDensity.MEDIUM)
    view_df = _body_view(df, None)
    assert view_df["is_solid"] is False
    assert view_df["effect_radius"] == 2000.0

    af = AsteroidField(in_hex=HexCoord(0, 0), in_system="Sol", density=FieldDensity.HIGH)
    view_af = _body_view(af, None)
    assert view_af["is_solid"] is False
    assert view_af["effect_radius"] == 3600.0

    nebula = Nebula(in_hex=HexCoord(0, 0), in_system="Sol", nebula_type=NebulaType.HYDROGEN)
    view_neb = _body_view(nebula, None)
    assert view_neb["is_solid"] is False
    assert view_neb["effect_radius"] == 3600.0
    assert view_neb["harvest_multiplier"] == 0.4

    storm = Storm(in_hex=HexCoord(0, 0), in_system="Sol", storm_type=StormType.PLASMA)
    view_storm = _body_view(storm, None)
    assert view_storm["is_solid"] is False
    assert view_storm["effect_radius"] == 3600.0

    # Solid bodies should report is_solid: True and not have effect_radius
    planet = Planet(in_hex=HexCoord(0, 0), in_system="Sol", planet_type=PlanetType.TERRAN)
    view_planet = _body_view(planet, None)
    assert view_planet["is_solid"] is True
    assert "effect_radius" not in view_planet


def test_sector_celestial_renderer_draws_turquoise_circle():
    """Verify SectorCelestialRenderer draws a turquoise circle for non-solid celestial bodies."""
    parent_mock = MagicMock()
    parent_mock.game = MagicMock()
    parent_mock.game.sector_zoom = 1.0
    parent_mock.screen = MagicMock()
    parent_mock._is_circle_off_screen.return_value = False
    parent_mock._font_cache = {}

    renderer = SectorCelestialRenderer(parent_mock)

    df = DebrisField(in_hex=HexCoord(0, 0), in_system="Sol")
    df.id = 55
    obj_pixel_pos = Position(500.0, 400.0)
    dynamic_radius = SECTOR_CIRCLE_RADIUS_IN_PX * 1.0

    with patch("rendering.sector_renderer.sector_celestial_renderer._sr") as mock_sr:
        mock_sr.return_value = mock_sr
        mock_sr.pygame = MagicMock()
        mock_sr.pygame.time.get_ticks.return_value = 1000

        renderer.draw_celestial_object(df, obj_pixel_pos, dynamic_radius)

        # Expected pixel radius for debris field
        expected_px_radius = int(DEBRIS_FIELD_RADIUS * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)

        # Verify pygame.draw.circle was called with screen, TURQUOISE, pos, expected_px_radius, 1
        found_turquoise_call = False
        for call in mock_sr.pygame.draw.circle.call_args_list:
            args = call[0]
            if len(args) >= 5 and args[1] == TURQUOISE:
                assert args[2] == (int(obj_pixel_pos.x), int(obj_pixel_pos.y))
                assert args[3] == expected_px_radius
                assert args[4] == 1
                found_turquoise_call = True
                break
        assert found_turquoise_call, f"Expected turquoise circle call with radius {expected_px_radius}, calls: {mock_sr.pygame.draw.circle.call_args_list}"
