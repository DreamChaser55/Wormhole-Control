from collections import Counter
import json
import math
import random

import pytest
from constants import PlanetType, StarType, SQRT3
from domain.celestials import Comet, MetalAsteroid, Moon, Planet, Star
from galaxy import Galaxy
from types import SimpleNamespace
from galaxy import StarSystem
from geometry import Vector, hex_distance
from tests.support.commands import world


def empty_system(radius=3, name='Generation test'):
    system = StarSystem.__new__(StarSystem)
    system.name, system.position, system.radius = name, Vector(0, 0), radius
    system.hexes, system.celestial_bodies_by_id = {}, {}
    system.generate_grid()
    system.add_celestial_body(Star(in_system=name, star_type=StarType.G_TYPE))
    return system


@pytest.fixture
def controlled_system(monkeypatch):
    """Exercise secondary placement with explicitly placed planets and body draws."""
    def generate(body_types, first_hexes=(), planet_type=PlanetType.TERRAN):
        system = empty_system()
        available = [h for coord, h in system.hexes.items() if coord != (0, 0)]
        priorities = {coord: i for i, coord in enumerate(first_hexes)}
        available.sort(key=lambda h: priorities.get(h.coordinates(), len(priorities)))
        for _ in range(body_types.count(Planet)):
            coord = available.pop(0).coordinates()
            system.add_celestial_body(Planet(coord, system.name, planet_type))
        secondary = [body_type for body_type in body_types if body_type != Planet]
        draws = iter(secondary)

        def choose_body(population, weights, k):
            # A depleted moon neighborhood must draw a nonmoon replacement.
            return [next(draws) if Moon in population else MetalAsteroid]

        monkeypatch.setattr('galaxy.random.choices', choose_body)
        system._spawn_secondary_bodies(available, len(secondary))
        for sector in system.hexes.values():
            sector.update_static_inhibition_zones()
        return system

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
def test_moons_without_planets_are_replaced(controlled_system, body_types):
    system = controlled_system(body_types)
    bodies = list(system.celestial_bodies_by_id.values())
    assert not any(isinstance(body, (Moon, Planet)) for body in bodies)
    assert len(bodies) == 1 + len(body_types)
    assert sum(isinstance(body, MetalAsteroid) for body in bodies) == len(body_types)


def test_moons_with_all_planet_neighbors_occupied_are_replaced(controlled_system):
    system = controlled_system(
        [Moon, Planet, MetalAsteroid, MetalAsteroid, MetalAsteroid],
        [(3, 0), (2, 0), (2, 1), (3, -1)],
    )
    assert not any(isinstance(body, Moon) for body in system.celestial_bodies_by_id.values())
    assert len(system.celestial_bodies_by_id) == 6


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
    assert len(system.celestial_bodies_by_id) == 2 + len(planet_hexes) + 14
    assert isinstance(system.hexes[(0, 0)].celestial_bodies[0], Star)
    assert all(len(sector.celestial_bodies) <= 1 for sector in system.hexes.values())


@pytest.mark.parametrize('radius', range(3, 13))
def test_seeded_system_budgets_rings_and_integrity(radius):
    moon_count = 0
    for seed in range(100):
        random.seed(seed)
        system = StarSystem(f'Seed {seed}', Vector(0, 0), radius=radius)
        bodies = list(system.celestial_bodies_by_id.values())
        planets = [body for body in bodies if isinstance(body, Planet)]
        assert math.ceil(0.7 * radius) <= len(planets) <= math.floor(1.3 * radius)
        assert 2 * radius <= len(bodies) - len(planets) - 1 <= 3 * radius
        rings = Counter(hex_distance(planet.in_hex, (0, 0)) for planet in planets)
        assert len(rings) == min(len(planets), radius)
        assert max(rings.values()) <= 2
        stars = [body for body in bodies if isinstance(body, Star)]
        assert len(stars) == 1 and stars[0].in_hex == (0, 0)
        assert sum(len(sector.celestial_bodies) for sector in system.hexes.values()) == len(bodies)
        for sector in system.hexes.values():
            assert len(sector.celestial_bodies) <= 1
            expected_zones = [(b.position, b.inhibition_field_radius) for b in sector.celestial_bodies
                              if b.inhibition_field_radius > 0]
            assert [(zone.center, zone.radius) for zone in sector.static_inhibition_zones] == expected_zones
        for coord, body in system.get_all_celestial_bodies():
            assert body.in_system == system.name and body.in_hex == coord
            assert system.hexes[coord].celestial_bodies == [body]
            assert system.celestial_bodies_by_id[body.id] is body
            if isinstance(body, Moon):
                moon_count += 1
                assert any(hex_distance(coord, planet.in_hex) == 1 for planet in planets)
                assert coord != (0, 0)
    assert moon_count > 0


def test_planet_types_follow_distance_with_rare_exceptions():
    zones = [Counter(), Counter(), Counter()]
    for seed in range(600):
        random.seed(seed)
        system = StarSystem('Climate', Vector(0, 0), radius=12)
        for body in system.celestial_bodies_by_id.values():
            if isinstance(body, Planet):
                distance = hex_distance(body.in_hex, (0, 0))
                zones[0 if distance <= 4 else 1 if distance <= 8 else 2][body.planet_type] += 1
    hot = (PlanetType.VOLCANIC, PlanetType.GREENHOUSE, PlanetType.FERROUS)
    temperate = (PlanetType.TERRAN, PlanetType.OCEANIC)
    cold = (PlanetType.ICE, PlanetType.GAS_GIANT)

    def share(zone, types):
        return sum(zones[zone][kind] for kind in types) / sum(zones[zone].values())

    assert share(0, hot) > 3 * share(2, hot)
    assert share(1, temperate) > 3 * max(share(0, temperate), share(2, temperate))
    assert share(2, cold) > 3 * share(0, cold)
    assert all(set(zone) == set(PlanetType) for zone in zones)


def test_climate_third_boundaries(monkeypatch):
    system = empty_system(radius=6)
    available = [h for coord, h in system.hexes.items() if coord != (0, 0)]
    monkeypatch.setattr('galaxy.random.choices',
                        lambda population, weights, k: [population[weights.index(max(weights))]])
    system._spawn_planets(available, 6)
    types_by_ring = {hex_distance(body.in_hex, (0, 0)): body.planet_type
                     for body in system.celestial_bodies_by_id.values() if isinstance(body, Planet)}
    assert types_by_ring == {
        1: PlanetType.VOLCANIC, 2: PlanetType.VOLCANIC,
        3: PlanetType.TERRAN, 4: PlanetType.TERRAN,
        5: PlanetType.GAS_GIANT, 6: PlanetType.GAS_GIANT,
    }


@pytest.mark.parametrize('radius', [2, 3, 8, 12])
def test_seeded_generation_is_repeatable(radius):
    def generate():
        random.seed(71)
        system = StarSystem('Repeatable', Vector(0, 0), radius=radius)
        return [(coord, type(body), getattr(body, 'planet_type', None), getattr(body, 'star_type', None),
                 getattr(body, 'nebula_type', None), getattr(body, 'storm_type', None), getattr(body, 'density', None))
                for coord, body in system.get_all_celestial_bodies()]

    assert generate() == generate()


@pytest.mark.parametrize('radius', [3, 12])
def test_planet_generation_does_not_depend_on_star_type(monkeypatch, radius):
    original_choice = random.choice
    planets_by_star = []
    for star_type in StarType:
        def choose(values):
            chosen = original_choice(values)
            return star_type if isinstance(chosen, StarType) else chosen

        monkeypatch.setattr('galaxy.random.choice', choose)
        random.seed(23)
        system = StarSystem('Stellar independence', Vector(0, 0), radius=radius)
        planets_by_star.append([(coord, body.planet_type) for coord, body in system.get_all_celestial_bodies()
                                if isinstance(body, Planet)])
    assert all(planets == planets_by_star[0] for planets in planets_by_star)


@pytest.mark.parametrize('available_coords,expected', [
    ([(1, 0), (0, 1), (-1, 0)], (-1, 0)),  # The only nonadjacent location.
    ([(1, 0), (0, 1)], (0, 1)),  # Adjacency must not reduce the budget.
])
def test_planet_spacing_and_crowded_ring_fallback(monkeypatch, available_coords, expected):
    system = empty_system(radius=1)
    available = [system.hexes[coord] for coord in available_coords]
    monkeypatch.setattr('galaxy.random.choice', lambda values: values[0])
    system._spawn_planets(available, 2)
    planets = [body for body in system.celestial_bodies_by_id.values() if isinstance(body, Planet)]
    assert [planet.in_hex for planet in planets] == [(1, 0), expected]


@pytest.mark.parametrize('coords,roll,expected', [
    ([(1, 0), (3, 0)], 0.84, (3, 0)),
    ([(1, 0), (3, 0)], 0.85, (1, 0)),
    ([(1, 0)], 0.0, (1, 0)),
])
def test_comet_bias_and_fallback(monkeypatch, coords, roll, expected):
    system = empty_system()
    available = [system.hexes[coord] for coord in coords]
    monkeypatch.setattr('galaxy.random.random', lambda: roll)
    system._spawn_secondary_body(Comet, available)
    comet, = [body for body in system.celestial_bodies_by_id.values() if isinstance(body, Comet)]
    assert comet.in_hex == expected
    assert len(available) == len(coords) - 1

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


@pytest.mark.parametrize('radius', [3, 5, 12])
@pytest.mark.parametrize('angle', [0, math.pi / 3, 2 * math.pi / 3, math.pi,
                                  -2 * math.pi / 3, -math.pi / 3, -0.01, math.pi - 0.01])
def test_wormhole_directional_outskirt_placement(radius, angle):
    galaxy = Galaxy(num_systems=0)
    system_a = StarSystem('System-A', Vector(0, 0), radius=radius)
    system_b = StarSystem('System-B', Vector(500 * math.cos(angle), 500 * math.sin(angle)), radius=radius)
    galaxy.systems = {system_a.name: system_a, system_b.name: system_b}

    for origin, destination in [(system_a, system_b), (system_b, system_a)]:
        direction = (destination.position.x - origin.position.x, destination.position.y - origin.position.y)

        def alignment(coord):
            q, r = coord
            x, y = SQRT3 * (q + r / 2), 1.5 * r
            return (x * direction[0] + y * direction[1]) / math.hypot(x, y)

        # Occupy the preferred hex and verify a second, equally well-directed
        # available endpoint is selected without replacing the existing body.
        for _ in range(2):
            coord = galaxy.find_wormhole_hex(origin, destination)
            assert coord is not None and origin.hexes[coord].is_empty()
            assert hex_distance(coord, (0, 0)) >= radius - 1
            candidates = [h for h, sector in origin.hexes.items()
                          if sector.is_empty() and hex_distance(h, (0, 0)) >= radius - 1]
            assert alignment(coord) == pytest.approx(max(map(alignment, candidates)))
            assert alignment(coord) > 0
            origin.add_celestial_body(MetalAsteroid(coord, origin.name))


@pytest.mark.parametrize('radius', [3, 12])
@pytest.mark.parametrize('density', [0.0, 1.0])
def test_maximum_galaxy_remains_connected_with_outlying_paired_endpoints(radius, density):
    from game_settings import GameSettings

    settings = GameSettings(num_systems=30, system_radius_min=radius,
                            system_radius_max=radius, wormhole_density=density)
    galaxy = Galaxy(num_systems=30, settings=settings)
    visited = set()
    pending = [next(iter(galaxy.systems))]
    while pending:
        name = pending.pop()
        if name not in visited:
            visited.add(name)
            pending.extend(galaxy.system_graph[name])
    assert visited == set(galaxy.systems)
    for wormhole in galaxy.wormholes.values():
        partner = galaxy.wormholes[wormhole.exit_wormhole_id]
        assert partner.exit_wormhole_id == wormhole.id
        assert partner.in_system == wormhole.exit_system_name
        assert partner.exit_system_name == wormhole.in_system
        assert hex_distance(wormhole.in_hex, (0, 0)) >= radius - 1
        assert galaxy.systems[wormhole.in_system].hexes[wormhole.in_hex].celestial_bodies == [wormhole]


@pytest.mark.parametrize('extra_planets', [0, 20])
def test_save_load_preserves_generated_and_overbudget_systems(monkeypatch, extra_planets):
    from campaign_persistence import prepare_campaign
    from save_manager import serialize_game_state
    from tests.support.campaigns import campaign

    game = campaign()
    game.galaxy = Galaxy(num_systems=2)
    game.view_mode, game.current_system_name, game.current_sector_coord = 'galaxy', None, None
    first_system = next(iter(game.galaxy.systems.values()))
    empty_coords = [coord for coord, sector in first_system.hexes.items() if sector.is_empty()]
    for coord in empty_coords[:extra_planets]:
        first_system.add_celestial_body(Planet(coord, first_system.name, PlanetType.ICE))
    assert len(empty_coords) >= extra_planets

    def fingerprint(galaxy):
        return {body.id: (name, coord, type(body), getattr(body, 'planet_type', None),
                          getattr(body, 'star_type', None), getattr(body, 'nebula_type', None),
                          getattr(body, 'storm_type', None), getattr(body, 'density', None),
                          getattr(body, 'exit_wormhole_id', None))
                for name, system in galaxy.systems.items() for coord, body in system.get_all_celestial_bodies()}

    expected = fingerprint(game.galaxy)
    payload = json.loads(json.dumps(serialize_game_state(game)))

    def forbidden(*args):
        pytest.fail('Loading must not run generation')

    monkeypatch.setattr(StarSystem, 'spawn_celestial_bodies', forbidden)
    monkeypatch.setattr(Galaxy, 'generate_galaxy', forbidden)
    restored = prepare_campaign(payload).state.galaxy
    assert restored is not game.galaxy
    assert fingerprint(restored) == expected


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
