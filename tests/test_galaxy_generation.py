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
