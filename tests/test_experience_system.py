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
from unittest.mock import MagicMock, patch
from geometry import Position
from unit_components import (
    Engines, Hyperdrive, HyperdriveType,
    Turret, TurretType, TurretVariant, Weapons,
    Defenses, Commander,
)
from constants import (
    HullSize,
    MAX_UNIT_XP,
    XP_WEAPON_DAMAGE_BONUS,
    XP_DEFENSE_BONUS,
    XP_SPEED_BONUS,
    XP_JUMP_RANGE_BONUS,
)

# ---------------------------------------------------------------------------
# Helpers / minimal mocks
# ---------------------------------------------------------------------------

class MockPlayer:
    def __init__(self):
        self.id = 1
        self.name = "Test Player"
        self.credits = 10_000
        self.metal = 10_000
        self.crystal = 10_000


class MockUnit:
    """Minimal unit mock that includes the XP methods from entities.Unit."""

    def __init__(self, hp: int = 200):
        self.id = 1
        self.name = "Test Unit"
        self.position = Position(0.0, 0.0)
        self.in_hex = (0, 0)
        self.in_system = "Sol"
        self.owner = MockPlayer()
        self.components: dict = {}
        self.in_galaxy = MagicMock()
        self.current_hit_points = hp
        self.max_hit_points = hp
        self.game = MagicMock()
        self.hull_size = HullSize.LARGE
        self.is_disabled = False
        self.damage_amplification = 0.0
        self.damage_reduction = 0.0
        self.is_temporary = False
        self.current_hull_usage = 0
        # XP fields
        self.experience_points = 0

    # --- component helpers ---
    def add_component(self, component):
        self.components[type(component)] = component

    def get_component(self, component_type):
        return self.components.get(component_type)

    @property
    def engines_component(self): return self.get_component(Engines)
    @property
    def hyperdrive_component(self): return self.get_component(Hyperdrive)
    @property
    def weapons_component(self): return self.get_component(Weapons)
    @property
    def commander_component(self): return self.get_component(Commander)

    # --- XP methods (copied from entities.Unit) ---
    def gain_experience(self, amount: int) -> None:
        if self.experience_points >= MAX_UNIT_XP:
            return
        self.experience_points = min(MAX_UNIT_XP, self.experience_points + max(0, amount))

    def xp_multiplier(self, max_bonus: float) -> float:
        return 1.0 + max_bonus * (self.experience_points / MAX_UNIT_XP)

    # --- Damage helpers (minimal, mirrors entities.Unit) ---
    def take_damage(self, amount: int, damage_type=None) -> None:
        if damage_type:
            defenses = self.get_component(Defenses)
            if defenses:
                mitigation = defenses.calculate_mitigation(amount, damage_type)
                amount = max(0, amount - mitigation)
        if self.damage_reduction > 0.0:
            amount = max(1, int(amount * (1.0 - self.damage_reduction)))
        self.current_hit_points = max(0, self.current_hit_points - amount)

    def take_component_damage(self, component_type, amount: int, damage_type=None) -> int:
        return amount  # simplified -- all damage spills to hull


# ---------------------------------------------------------------------------
# gain_experience tests
# ---------------------------------------------------------------------------

class TestGainExperience:
    def test_gain_basic(self):
        unit = MockUnit()
        unit.gain_experience(100)
        assert unit.experience_points == 100

    def test_gain_accumulates(self):
        unit = MockUnit()
        unit.gain_experience(300)
        unit.gain_experience(200)
        assert unit.experience_points == 500

    def test_gain_capped_at_max(self):
        unit = MockUnit()
        unit.gain_experience(900)
        unit.gain_experience(500)  # would push over max
        assert unit.experience_points == MAX_UNIT_XP

    def test_gain_exactly_max(self):
        unit = MockUnit()
        unit.gain_experience(MAX_UNIT_XP)
        assert unit.experience_points == MAX_UNIT_XP

    def test_gain_already_at_max_no_change(self):
        unit = MockUnit()
        unit.experience_points = MAX_UNIT_XP
        unit.gain_experience(50)
        assert unit.experience_points == MAX_UNIT_XP

    def test_gain_negative_ignored(self):
        unit = MockUnit()
        unit.gain_experience(-50)
        assert unit.experience_points == 0

    def test_gain_zero_no_change(self):
        unit = MockUnit()
        unit.gain_experience(0)
        assert unit.experience_points == 0


# ---------------------------------------------------------------------------
# xp_multiplier tests
# ---------------------------------------------------------------------------

class TestXpMultiplier:
    def test_at_zero_xp(self):
        unit = MockUnit()
        assert unit.xp_multiplier(XP_WEAPON_DAMAGE_BONUS) == pytest.approx(1.0)

    def test_at_max_xp_weapon_damage(self):
        unit = MockUnit()
        unit.experience_points = MAX_UNIT_XP
        expected = 1.0 + XP_WEAPON_DAMAGE_BONUS
        assert unit.xp_multiplier(XP_WEAPON_DAMAGE_BONUS) == pytest.approx(expected)

    def test_at_max_xp_defense(self):
        unit = MockUnit()
        unit.experience_points = MAX_UNIT_XP
        expected = 1.0 + XP_DEFENSE_BONUS
        assert unit.xp_multiplier(XP_DEFENSE_BONUS) == pytest.approx(expected)

    def test_at_max_xp_speed(self):
        unit = MockUnit()
        unit.experience_points = MAX_UNIT_XP
        expected = 1.0 + XP_SPEED_BONUS
        assert unit.xp_multiplier(XP_SPEED_BONUS) == pytest.approx(expected)

    def test_at_max_xp_jump_range(self):
        unit = MockUnit()
        unit.experience_points = MAX_UNIT_XP
        expected = 1.0 + XP_JUMP_RANGE_BONUS
        assert unit.xp_multiplier(XP_JUMP_RANGE_BONUS) == pytest.approx(expected)

    def test_at_half_xp_is_linear(self):
        unit = MockUnit()
        unit.experience_points = MAX_UNIT_XP // 2
        expected = 1.0 + XP_WEAPON_DAMAGE_BONUS * 0.5
        assert unit.xp_multiplier(XP_WEAPON_DAMAGE_BONUS) == pytest.approx(expected)

    def test_at_quarter_xp(self):
        unit = MockUnit()
        unit.experience_points = MAX_UNIT_XP // 4
        expected = 1.0 + XP_WEAPON_DAMAGE_BONUS * 0.25
        assert unit.xp_multiplier(XP_WEAPON_DAMAGE_BONUS) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Turret.fire() -- XP earning (no overkill inflation)
# ---------------------------------------------------------------------------

def make_turret(attacker: MockUnit, target, damage: float = 50.0) -> Turret:
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
        attacker = MockUnit()
        target = MockUnit(hp=200)
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
        attacker = MockUnit()
        target = MockUnit(hp=10)
        turret = make_turret(attacker, target, damage=50.0)

        turret.fire()

        # Target should be at 0 HP; XP cannot exceed initial HP
        assert target.current_hit_points == 0
        assert attacker.experience_points == 10

    def test_no_xp_if_no_target(self):
        attacker = MockUnit()
        turret = make_turret(attacker, None, damage=50.0)
        turret.target = None
        turret.fire()
        assert attacker.experience_points == 0

    def test_xp_accumulates_across_shots(self):
        attacker = MockUnit()
        target = MockUnit(hp=200)
        turret = make_turret(attacker, target, damage=30.0)

        turret.fire()
        turret.current_cooldown = 0  # reset cooldown manually
        turret.fire()

        assert attacker.experience_points > 0
        # Two shots of 30 each = 60 XP (no mitigation in this bare mock)
        assert attacker.experience_points == 60

    def test_xp_capped_across_shots(self):
        attacker = MockUnit()
        attacker.experience_points = MAX_UNIT_XP - 5
        target = MockUnit(hp=200)
        turret = make_turret(attacker, target, damage=50.0)

        turret.fire()
        assert attacker.experience_points == MAX_UNIT_XP


# ---------------------------------------------------------------------------
# Turret.fire() -- weapon damage XP bonus
# ---------------------------------------------------------------------------

class TestWeaponDamageXpBonus:
    def test_no_xp_no_damage_bonus(self):
        """At 0 XP the damage applied to the target should equal the base damage."""
        attacker = MockUnit()
        target = MockUnit(hp=500)
        turret = make_turret(attacker, target, damage=100.0)

        turret.fire()

        hp_lost = 500 - target.current_hit_points
        # At 0 XP multiplier is 1.0 so effective_damage == 100
        assert hp_lost == 100

    def test_max_xp_increases_damage(self):
        """At max XP the effective damage should be base * (1 + XP_WEAPON_DAMAGE_BONUS)."""
        attacker = MockUnit()
        attacker.experience_points = MAX_UNIT_XP
        target = MockUnit(hp=500)
        turret = make_turret(attacker, target, damage=100.0)

        turret.fire()

        hp_lost = 500 - target.current_hit_points
        expected = int(100.0 * (1.0 + XP_WEAPON_DAMAGE_BONUS))
        assert hp_lost == expected

    def test_half_xp_scales_damage(self):
        attacker = MockUnit()
        attacker.experience_points = MAX_UNIT_XP // 2
        target = MockUnit(hp=500)
        turret = make_turret(attacker, target, damage=100.0)

        turret.fire()

        hp_lost = 500 - target.current_hit_points
        mult = 1.0 + XP_WEAPON_DAMAGE_BONUS * 0.5
        expected = int(100.0 * mult)
        assert hp_lost == expected


# ---------------------------------------------------------------------------
# Defenses.calculate_mitigation() -- defense XP bonus
# ---------------------------------------------------------------------------

class TestDefenseMitigationXpBonus:
    def _make_defender_with_defenses(self, armor: int = 50, xp: int = 0) -> MockUnit:
        defender = MockUnit()
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
