import pytest
from constants import MIN_DAMAGE_PASS_THROUGH
from unit_components.defenses import Defenses
from unit_components.enums import TurretType

@pytest.mark.parametrize('amount,reduction,damage', [
    (0, .5, 0), (-10, .5, 0), (1, .75, .25), (10, .5, 5),
    (10, 1, 0), (10, 2, 0), (10, -1, 10), (10, 0, 10),
    (0.3, 0, 0.3), (0.001, 0, 0.001),
])
def test_damage_floor(atmosphere, amount, reduction, damage):
    _, _, unit = atmosphere
    unit.damage_reduction = reduction
    hp = unit.current_hit_points
    unit.take_damage(amount)
    assert unit.current_hit_points == pytest.approx(hp - damage)


def test_full_environmental_cover_still_absorbs_everything(atmosphere, monkeypatch):
    _, _, unit = atmosphere
    unit.damage_reduction = .5
    monkeypatch.setattr(unit, 'get_environmental_cover_bonus', lambda kind: 1)
    hp = unit.current_hit_points
    unit.take_damage(25, TurretType.BEAM)
    assert unit.current_hit_points == hp


def test_defenses_can_never_absorb_more_than_all_but_the_pass_through(atmosphere, monkeypatch):
    """Even a mitigation that claims to absorb the whole hit lets the minimum pass through."""
    _, _, unit = atmosphere
    unit.damage_reduction = .5
    defenses = Defenses(unit, shields=100)
    unit.add_component(defenses)
    monkeypatch.setattr(defenses, 'calculate_mitigation', lambda amount, kind: amount)
    hp = unit.current_hit_points
    unit.take_damage(25, TurretType.BEAM)
    assert unit.current_hit_points == pytest.approx(hp - 25 * MIN_DAMAGE_PASS_THROUGH * .5)


@pytest.mark.parametrize('turret', list(TurretType))
def test_overwhelming_defenses_still_pass_the_minimum_damage(atmosphere, monkeypatch, turret):
    _, _, unit = atmosphere
    unit.add_component(Defenses(unit, armor=1000, shields=1000, point_defense=1000))
    monkeypatch.setattr('unit_components.defenses.random.uniform', lambda _low, high: high)
    hp = unit.current_hit_points
    unit.take_damage(4, turret)
    assert unit.current_hit_points == pytest.approx(hp - 4 * MIN_DAMAGE_PASS_THROUGH)


def test_pass_through_applies_to_component_hits_and_returns_float_spillover(atmosphere, monkeypatch):
    _, _, unit = atmosphere
    unit.add_component(Defenses(unit, armor=1000))
    monkeypatch.setattr('unit_components.defenses.random.uniform', lambda _low, high: high)
    defenses = unit.get_component(Defenses)
    before = defenses.current_hit_points
    spill = unit.take_component_damage(Defenses, 5, TurretType.MASS_DRIVER)
    assert spill == 0
    assert defenses.current_hit_points == pytest.approx(before - 5 * MIN_DAMAGE_PASS_THROUGH)
    defenses.current_hit_points = 0.25
    spill = unit.take_component_damage(Defenses, 5, TurretType.MASS_DRIVER)
    assert spill == pytest.approx(5 * MIN_DAMAGE_PASS_THROUGH - 0.25)
    assert defenses.current_hit_points == 0


def test_calculate_mitigation_is_a_float_capped_below_the_incoming_damage(atmosphere, monkeypatch):
    _, _, unit = atmosphere
    defenses = Defenses(unit, armor=1000)
    unit.add_component(defenses)
    monkeypatch.setattr('unit_components.defenses.random.uniform', lambda _low, high: high)
    assert defenses.calculate_mitigation(3.0, TurretType.MASS_DRIVER) == pytest.approx(3.0 * (1 - MIN_DAMAGE_PASS_THROUGH))
    assert defenses.calculate_mitigation(0.0, TurretType.MASS_DRIVER) == 0.0
    assert defenses.calculate_mitigation(3.0, None) == 0.0


def test_many_weak_hits_can_kill_a_heavily_defended_target(atmosphere, monkeypatch):
    """A swarm of shots that were fully absorbed before now accumulates damage."""
    game, _, unit = atmosphere
    unit.add_component(Defenses(unit, armor=90, shields=90, point_defense=90))
    monkeypatch.setattr('unit_components.defenses.random.uniform', lambda _low, high: high)
    hits = 0
    while unit.current_hit_points > 0 and hits < 10000:
        unit.take_damage(3, TurretType.MASS_DRIVER)
        hits += 1
    assert unit.current_hit_points == 0
    assert hits == pytest.approx(unit.max_hit_points / (3 * MIN_DAMAGE_PASS_THROUGH), abs=1)


def test_reduced_lethal_damage_still_destroys(atmosphere):
    game, _, unit = atmosphere
    unit.damage_reduction = .5
    unit.take_damage(unit.current_hit_points * 2)
    assert unit.current_hit_points == 0
    assert unit not in game.galaxy.systems['Sol'].hexes[(0, 0)].units


def test_residual_float_hit_points_are_treated_as_destroyed(atmosphere):
    game, _, unit = atmosphere
    unit.current_hit_points = 1e-12
    unit.take_damage(1e-13)
    assert unit.current_hit_points == 0
    assert unit not in game.galaxy.systems['Sol'].hexes[(0, 0)].units


def test_fractional_and_legacy_integer_hp_round_trip(atmosphere):
    import json
    from save_manager import deserialize_game_state, serialize_game_state
    game, _, unit = atmosphere
    defenses = Defenses(unit, armor=10.0, hull_cost=3.0)
    unit.add_component(defenses)
    unit.current_hit_points = 87.35
    unit.experience_points = 12.75
    defenses.current_hit_points = 15.25

    saved = json.loads(json.dumps(serialize_game_state(game)))
    assert deserialize_game_state(game, saved)
    restored = game.galaxy.get_unit_by_id(unit.id)
    assert restored.current_hit_points == pytest.approx(87.35)
    assert restored.experience_points == pytest.approx(12.75)
    assert restored.get_component(Defenses).current_hit_points == pytest.approx(15.25)

    # Legacy saves with integer HP/XP remain valid.
    for system in saved['galaxy']['systems']:
        hexes = system['hexes'].values() if isinstance(system['hexes'], dict) else system['hexes']
        for hx in hexes:
            for u in hx['units']:
                u['current_hit_points'] = int(u['current_hit_points'])
                u['max_hit_points'] = int(u['max_hit_points'])
                u['experience_points'] = int(u['experience_points'])
                for comp in u['components'].values():
                    comp['current_hit_points'] = int(comp['current_hit_points'])
                    comp['max_hit_points'] = int(comp['max_hit_points'])
    assert deserialize_game_state(game, saved)
    legacy = game.galaxy.get_unit_by_id(unit.id)
    assert legacy.current_hit_points == 87.0
    assert legacy.experience_points == 12.0
