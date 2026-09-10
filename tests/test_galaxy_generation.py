import random

import pytest
from constants import PlanetType
from domain.celestials import MetalAsteroid, Moon, Planet, Star
from galaxy import Galaxy
from types import SimpleNamespace
from galaxy import StarSystem
from geometry import Vector, hex_distance
from tests.support.commands import world


@pytest.fixture
def controlled_system(monkeypatch):
    """Control body draws and initial hex order while using real generation."""
    def generate(body_types, first_hexes=(), planet_type=PlanetType.TERRAN):
        draws = iter(body_types)

        def body_count(low, high):
            assert low <= len(body_types) <= high
            return len(body_types)

        def order_hexes(hexes):
            priorities = {coord: i for i, coord in enumerate(first_hexes)}
            hexes.sort(key=lambda h: priorities.get(h.coordinates(), len(priorities)))

        monkeypatch.setattr('galaxy.random.randint', body_count)
        monkeypatch.setattr('galaxy.random.shuffle', order_hexes)
        monkeypatch.setattr('galaxy.random.choices', lambda population, weights, k: [next(draws)])
        monkeypatch.setattr(
            'galaxy.random.choice',
            lambda values: planet_type if isinstance(values[0], PlanetType) else values[0],
        )
        return StarSystem('Moon test', Vector(0, 0), radius=3)

    return generate


@pytest.mark.parametrize('planet_type', list(PlanetType))
def test_deferred_moon_spawns_beside_every_planet_type(controlled_system, planet_type):
    system = controlled_system(
        [Moon, Planet, MetalAsteroid, MetalAsteroid],
        [(1, 0), (-3, 0), (-3, 1)], planet_type,
    )
    bodies = list(system.celestial_bodies_by_id.values())
    planet, = [body for body in bodies if isinstance(body, Planet)]
    moon, = [body for body in bodies if isinstance(body, Moon)]
    assert planet.planet_type == planet_type
    assert planet.in_hex == (1, 0)
    assert hex_distance(moon.in_hex, planet.in_hex) == 1
    assert moon.in_system == system.name
    assert system.hexes[moon.in_hex].celestial_bodies == [moon]
    zone, = system.hexes[moon.in_hex].static_inhibition_zones
    assert zone.center == moon.position
    assert zone.radius == moon.inhibition_field_radius
    assert len(bodies) == 5  # Central star plus all four requested bodies.


@pytest.mark.parametrize('body_types', [
    [Moon, Moon, Moon, Moon],
    [Moon, MetalAsteroid, MetalAsteroid, MetalAsteroid],
])
def test_moons_without_planets_are_skipped(controlled_system, body_types):
    system = controlled_system(body_types)
    bodies = list(system.celestial_bodies_by_id.values())
    assert not any(isinstance(body, (Moon, Planet)) for body in bodies)
    assert len(bodies) == 1 + body_types.count(MetalAsteroid)


def test_moons_with_all_planet_neighbors_occupied_are_skipped(controlled_system):
    system = controlled_system(
        [Moon, Planet, MetalAsteroid, MetalAsteroid, MetalAsteroid],
        [(3, 0), (2, 0), (2, 1), (3, -1)],
    )
    assert not any(isinstance(body, Moon) for body in system.celestial_bodies_by_id.values())
    assert len(system.celestial_bodies_by_id) == 5


@pytest.mark.parametrize('planet_hexes', [
    [(1, 0)],  # The central star occupies one neighbor.
    [(3, 0)],  # Some neighbors fall outside the system.
    [(1, 0), (0, 1)],  # Two planets share eligible neighbors.
])
def test_excess_moons_fill_unique_available_neighbors(controlled_system, planet_hexes):
    occupied_hex = (2, 0)
    system = controlled_system(
        [Planet] * len(planet_hexes) + [MetalAsteroid] + [Moon] * 14,
        planet_hexes + [occupied_hex],
    )
    expected = {
        coord for coord in system.hexes
        if coord not in [(0, 0), occupied_hex, *planet_hexes]
        and any(hex_distance(coord, planet) == 1 for planet in planet_hexes)
    }
    moons = [body for body in system.celestial_bodies_by_id.values() if isinstance(body, Moon)]
    assert 1 < len(moons) == len(expected) < 14
    assert {moon.in_hex for moon in moons} == expected
    assert len(system.celestial_bodies_by_id) == 2 + len(planet_hexes) + len(moons)
    assert isinstance(system.hexes[(0, 0)].celestial_bodies[0], Star)
    assert all(len(sector.celestial_bodies) <= 1 for sector in system.hexes.values())


@pytest.mark.parametrize('radius', [3, 12])
def test_seeded_generation_moon_adjacency(radius):
    moon_count = 0
    for seed in range(10):
        random.seed(seed)
        system = StarSystem(f'Seed {seed}', Vector(0, 0), radius=radius)
        planets = [body for body in system.celestial_bodies_by_id.values() if isinstance(body, Planet)]
        for coord, body in system.get_all_celestial_bodies():
            if isinstance(body, Moon):
                moon_count += 1
                assert any(hex_distance(coord, planet.in_hex) == 1 for planet in planets)
                assert coord != (0, 0)
                assert system.hexes[coord].celestial_bodies == [body]
                assert system.celestial_bodies_by_id[body.id] is body
    assert moon_count > 0

def test_wormhole_stability_generation():
    # Test stability values over 5 galaxy generations to ensure we get a mix
    has_stable = False
    has_unstable = False

    for _ in range(5):
        galaxy = Galaxy(num_systems=15)
        assert len(galaxy.wormholes) > 0

        for wh_id, wh in galaxy.wormholes.items():
            # Check stability is in valid range [50, 100]
            assert 50 <= wh.stability <= 100

            # Check that stability is symmetric for the linked wormhole pair
            exit_wh = galaxy.wormholes.get(wh.exit_wormhole_id)
            assert exit_wh is not None
            assert wh.stability == exit_wh.stability

            if wh.stability == 100:
                has_stable = True
            else:
                has_unstable = True

    # Check that we generated at least one stable and one unstable wormhole across the runs
    assert has_stable, "Expected to generate at least one stable wormhole (100% stability) across runs"
    assert has_unstable, "Expected to generate at least one unstable wormhole (<100% stability) across runs"

def test_wormhole_diameter_generation():
    from constants import HullSize
    
    diameters = {HullSize.HUGE: 0, HullSize.LARGE: 0, HullSize.MEDIUM: 0}
    total_wormholes = 0

    for _ in range(20):
        galaxy = Galaxy(num_systems=15)
        for wh in galaxy.wormholes.values():
            assert wh.diameter in [HullSize.HUGE, HullSize.LARGE, HullSize.MEDIUM]
            
            # Check symmetry
            exit_wh = galaxy.wormholes.get(wh.exit_wormhole_id)
            assert exit_wh is not None
            assert wh.diameter == exit_wh.diameter
            
            diameters[wh.diameter] += 1
            total_wormholes += 1

    assert total_wormholes > 0
    # Verify we get at least one of each to make sure they all can generate
    assert diameters[HullSize.HUGE] > 0
    assert diameters[HullSize.LARGE] > 0
    assert diameters[HullSize.MEDIUM] > 0


def test_wormhole_directional_outskirt_placement():
    from geometry import Vector, hex_distance
    from constants import SQRT3

    # Create a galaxy instance
    galaxy = Galaxy(num_systems=0)

    # Create two star systems: System A and System B
    # System A is to the left of System B
    from galaxy import StarSystem
    system_a = StarSystem("System-A", Vector(100.0, 100.0), radius=5)
    system_b = StarSystem("System-B", Vector(500.0, 100.0), radius=5)

    galaxy.systems["System-A"] = system_a
    galaxy.systems["System-B"] = system_b

    # Find wormhole hex in System-A pointing to System-B (directly right, angle = 0)
    hex_a = galaxy.find_wormhole_hex(system_a, system_b)
    assert hex_a is not None

    # Verify hex_a is in the outskirts (distance from center >= 4)
    dist_a = hex_distance(hex_a, (0, 0))
    assert dist_a >= 4

    # Verify hex_a is on the right side of the central star
    q_a, r_a = hex_a
    hex_x_a = SQRT3 * q_a + (SQRT3 / 2.0) * r_a
    assert hex_x_a > 0, f"Expected hex on the right side, got {hex_a} with x={hex_x_a}"

    # Find wormhole hex in System-B pointing to System-A (directly left, angle = pi)
    hex_b = galaxy.find_wormhole_hex(system_b, system_a)
    assert hex_b is not None

    # Verify hex_b is in the outskirts (distance from center >= 4)
    dist_b = hex_distance(hex_b, (0, 0))
    assert dist_b >= 4

    # Verify hex_b is on the left side of the central star
    q_b, r_b = hex_b
    hex_x_b = SQRT3 * q_b + (SQRT3 / 2.0) * r_b
    assert hex_x_b < 0, f"Expected hex on the left side, got {hex_b} with x={hex_x_b}"


def test_comet_outskirt_spawning_distribution():
    from domain.celestials import Comet
    from geometry import hex_distance
    import math

    outskirt_count = 0
    total_comets = 0

    # Generate multiple galaxies/systems to sample comet positions
    for _ in range(30):
        galaxy = Galaxy(num_systems=10)
        for system in galaxy.systems.values():
            outskirts_threshold = max(2, math.ceil(system.radius * 0.65))
            for hex_coord, body in system.get_all_celestial_bodies():
                if isinstance(body, Comet):
                    dist = hex_distance(hex_coord, (0, 0))
                    total_comets += 1
                    if dist >= outskirts_threshold:
                        outskirt_count += 1

    assert total_comets > 0, "Expected at least some comets to be generated across 300 star systems"
    outskirt_ratio = outskirt_count / total_comets
    # Verify that at least 75% of comets spawn on system outskirts
    assert outskirt_ratio >= 0.75, f"Expected high comet outskirt ratio, got {outskirt_ratio:.2f} ({outskirt_count}/{total_comets})"


def test_missing_and_valid_hex_lookups():
    system = object.__new__(StarSystem)
    sector = SimpleNamespace(units=[object()], celestial_bodies=[object()])
    system.hexes = {(0, 0): sector}
    assert system.get_units_in_hex((9, 9)) == []
    assert system.get_celestial_bodies_in_hex((9, 9)) == []
    assert system.get_units_in_hex((0, 0)) is sector.units
    assert system.get_celestial_bodies_in_hex((0, 0)) is sector.celestial_bodies


@pytest.mark.parametrize('origin,destination,coord,success', [
    ('missing', 'Sol', (0, 0), False), ('Sol', 'missing', (0, 0), False),
    ('Sol', 'Other', (99, 99), False), ('Sol', 'Other', (0, 0), True),
])
def test_transfer_validation_preserves_membership(origin, destination, coord, success):
    game, player, _, unit = world()
    galaxy = game.galaxy
    galaxy.systems['Other'] = StarSystem('Other', Vector(500, 0), radius=2)
    before = (unit.in_system, unit.in_hex)
    result = galaxy.move_unit_between_systems(unit, origin, destination, coord)
    assert result is success
    if success:
        assert unit in galaxy.systems['Other'].get_units_in_hex((0, 0))
        assert unit not in galaxy.systems['Sol'].get_units_in_hex(before[1])
    else:
        assert (unit.in_system, unit.in_hex) == before
        assert unit in galaxy.systems['Sol'].get_units_in_hex(before[1])
        assert unit not in galaxy.systems['Other'].get_units_in_hex((0, 0))
