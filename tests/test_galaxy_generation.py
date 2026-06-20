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
