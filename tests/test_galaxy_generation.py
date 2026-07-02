import pytest
from galaxy import Galaxy

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
    import math

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

