

import pytest
from unit_components import Defenses
from unit_components.enums import TurretType

@pytest.mark.parametrize('amount,reduction,damage', [
    (0, .5, 0), (-10, .5, 0), (1, .75, 0), (10, .5, 5),
    (10, 1, 0), (10, 2, 0), (10, -1, 10), (10, 0, 10),
])
def test_damage_floor(atmosphere, amount, reduction, damage):
    _, _, unit = atmosphere
    unit.damage_reduction = reduction
    hp = unit.current_hit_points
    unit.take_damage(amount)
    assert unit.current_hit_points == hp - damage


@pytest.mark.parametrize('mitigation', ['cover', 'defenses'])
def test_fully_mitigated_damage_stays_zero(atmosphere, monkeypatch, mitigation):
    _, _, unit = atmosphere
    unit.damage_reduction = .5
    if mitigation == 'cover':
        monkeypatch.setattr(unit, 'get_environmental_cover_bonus', lambda kind: 1)
    else:
        defenses = Defenses(unit, shields=100)
        unit.add_component(defenses)
        monkeypatch.setattr(defenses, 'calculate_mitigation', lambda amount, kind: amount)
    hp = unit.current_hit_points
    unit.take_damage(25, TurretType.BEAM)
    assert unit.current_hit_points == hp


def test_reduced_lethal_damage_still_destroys(atmosphere):
    game, _, unit = atmosphere
    unit.damage_reduction = .5
    unit.take_damage(unit.current_hit_points * 2)
    assert unit.current_hit_points == 0
    assert unit not in game.galaxy.systems['Sol'].hexes[(0, 0)].units
