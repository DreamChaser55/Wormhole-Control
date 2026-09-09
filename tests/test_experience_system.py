"""
tests/test_experience_system.py

Unit tests for the XP (experience points) system added to Wormhole Control.

Coverage:
  - Unit.gain_experience() -- increments and caps correctly.
  - Unit.xp_multiplier() -- linear scaling at 0 XP, max XP, and midpoints.
  - Turret.fire() -- grants XP equal to actual HP lost (not overkill).
  - Turret.fire() -- weapon damage is scaled by attacker XP.
  - Defenses.calculate_mitigation() -- mitigation is scaled by defender XP.
"""

import pytest
from unittest.mock import patch
from unit_components import (
    Turret, TurretType, TurretVariant, Defenses,
)
from constants import (
    HullSize,
    MAX_UNIT_XP,
    XP_WEAPON_DAMAGE_BONUS,
    XP_DEFENSE_BONUS,
    XP_SPEED_BONUS,
    XP_JUMP_RANGE_BONUS,
)
from entities import Unit
from tests.support.campaigns import campaign, ship


def make_unit(hp=200):
    unit = ship(campaign(), hull=HullSize.LARGE)
    unit.current_hit_points = unit.max_hit_points = hp
    return unit


@pytest.mark.parametrize("start,awards,expected", [
    (0, (300, 200), 500), (900, (500,), MAX_UNIT_XP),
    (0, (MAX_UNIT_XP,), MAX_UNIT_XP), (MAX_UNIT_XP, (50,), MAX_UNIT_XP),
    (100, (-50, 0), 100),
])
def test_gain_experience_accumulates_and_clamps(start, awards, expected):
    unit = make_unit()
    unit.experience_points = start
    for amount in awards:
        unit.gain_experience(amount)
    assert unit.experience_points == expected


@pytest.mark.parametrize("fraction", [0, 0.5, 1])
def test_xp_multiplier_scales_bonuses(fraction):
    unit = make_unit()
    unit.experience_points = int(MAX_UNIT_XP * fraction)
    for bonus in (XP_WEAPON_DAMAGE_BONUS, XP_DEFENSE_BONUS, XP_SPEED_BONUS, XP_JUMP_RANGE_BONUS):
        assert unit.xp_multiplier(bonus) == pytest.approx(1 + fraction * bonus)


def make_turret(attacker: Unit, target, damage: float = 50.0) -> Turret:
    return Turret(
        turret_type=TurretType.BEAM,
        damage=damage,
        range=500.0,
        cooldown=1,
        parent_unit=attacker,
        variant=TurretVariant.STANDARD,
        target=target,
    )


class TestTurretFireXpEarning:
    def test_xp_earned_equals_damage_dealt(self):
        attacker = make_unit()
        target = make_unit(hp=200)
        turret = make_turret(attacker, target, damage=50.0)

        hp_before = target.current_hit_points
        turret.fire()

        xp_earned = attacker.experience_points
        actual_damage = hp_before - target.current_hit_points
        # XP should match actual HP lost (no overkill, target had plenty of HP)
        assert xp_earned == actual_damage
        assert xp_earned > 0

    def test_overkill_does_not_inflate_xp(self):
        """If target has only 10 HP but turret does 50 damage, XP should be 10."""
        attacker = make_unit()
        target = make_unit(hp=10)
        turret = make_turret(attacker, target, damage=50.0)

        turret.fire()

        # Target should be at 0 HP; XP cannot exceed initial HP
        assert target.current_hit_points == 0
        assert attacker.experience_points == 10

    def test_no_xp_if_no_target(self):
        attacker = make_unit()
        turret = make_turret(attacker, None, damage=50.0)
        turret.target = None
        turret.fire()
        assert attacker.experience_points == 0

    def test_xp_accumulates_across_shots(self):
        attacker = make_unit()
        target = make_unit(hp=200)
        turret = make_turret(attacker, target, damage=30.0)

        turret.fire()
        turret.current_cooldown = 0  # reset cooldown manually
        turret.fire()

        assert attacker.experience_points > 0
        # Two shots of 30 each = 60 XP (no mitigation in this bare mock)
        assert attacker.experience_points == 60

    def test_xp_capped_across_shots(self):
        attacker = make_unit()
        attacker.experience_points = MAX_UNIT_XP - 5
        target = make_unit(hp=200)
        turret = make_turret(attacker, target, damage=50.0)

        turret.fire()
        assert attacker.experience_points == MAX_UNIT_XP


class TestWeaponDamageXpBonus:
    def test_no_xp_no_damage_bonus(self):
        """At 0 XP the damage applied to the target should equal the base damage."""
        attacker = make_unit()
        target = make_unit(hp=500)
        turret = make_turret(attacker, target, damage=100.0)

        turret.fire()

        hp_lost = 500 - target.current_hit_points
        # At 0 XP multiplier is 1.0 so effective_damage == 100
        assert hp_lost == 100

    def test_max_xp_increases_damage(self):
        """At max XP the effective damage should be base * (1 + XP_WEAPON_DAMAGE_BONUS)."""
        attacker = make_unit()
        attacker.experience_points = MAX_UNIT_XP
        target = make_unit(hp=500)
        turret = make_turret(attacker, target, damage=100.0)

        turret.fire()

        hp_lost = 500 - target.current_hit_points
        expected = int(100.0 * (1.0 + XP_WEAPON_DAMAGE_BONUS))
        assert hp_lost == expected

    def test_half_xp_scales_damage(self):
        attacker = make_unit()
        attacker.experience_points = MAX_UNIT_XP // 2
        target = make_unit(hp=500)
        turret = make_turret(attacker, target, damage=100.0)

        turret.fire()

        hp_lost = 500 - target.current_hit_points
        mult = 1.0 + XP_WEAPON_DAMAGE_BONUS * 0.5
        expected = int(100.0 * mult)
        assert hp_lost == expected


class TestDefenseMitigationXpBonus:
    def _make_defender_with_defenses(self, armor: int = 50, xp: int = 0) -> Unit:
        defender = make_unit()
        defender.experience_points = xp
        defenses = Defenses(unit=defender, armor=armor, shields=0, point_defense=0, hull_cost=10)
        defender.add_component(defenses)
        return defender

    def test_no_xp_mitigation_at_most_armor(self):
        """Without XP the mitigation from armor is bounded by [0, armor]."""
        defender = self._make_defender_with_defenses(armor=100, xp=0)
        defenses = defender.get_component(Defenses)
        for _ in range(20):
            m = defenses.calculate_mitigation(200, TurretType.MASS_DRIVER)
            assert 0 <= m <= 100

    def test_max_xp_increases_max_mitigation(self):
        """At max XP the mitigation should be scaled up by XP_DEFENSE_BONUS."""
        with patch("unit_components.random.randint", return_value=50):
            defender = self._make_defender_with_defenses(armor=50, xp=0)
            defenses = defender.get_component(Defenses)
            baseline = defenses.calculate_mitigation(200, TurretType.MASS_DRIVER)

            defender.experience_points = MAX_UNIT_XP
            boosted = defenses.calculate_mitigation(200, TurretType.MASS_DRIVER)

        expected_boosted = int(baseline * (1.0 + XP_DEFENSE_BONUS))
        assert boosted == expected_boosted
        assert boosted > baseline

    def test_destroyed_defenses_return_zero_mitigation(self):
        defender = self._make_defender_with_defenses(armor=100, xp=MAX_UNIT_XP)
        defenses = defender.get_component(Defenses)
        defenses.current_hit_points = 0  # destroy component
        assert defenses.calculate_mitigation(100, TurretType.MASS_DRIVER) == 0

    def test_mitigation_never_exceeds_incoming_damage(self):
        """Regardless of XP, mitigation must not exceed the incoming damage."""
        defender = self._make_defender_with_defenses(armor=1000, xp=MAX_UNIT_XP)
        defenses = defender.get_component(Defenses)
        for _ in range(20):
            incoming = 10
            m = defenses.calculate_mitigation(incoming, TurretType.MASS_DRIVER)
            assert m <= incoming
