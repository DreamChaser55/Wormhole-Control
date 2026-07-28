"""
tests/test_dynamic_component_costs.py

Unit tests for the dynamic hull-cost calculation functions in
custom_unit_templates.py.
"""

import pytest
import math

from custom_unit_templates import (
    TurretConfig,
    calc_engine_hull_cost,
    calc_turret_hull_cost,
    calc_weapons_hull_cost,
    calc_defenses_hull_cost,
    calc_hyperdrive_hull_cost,
    calc_ability_hull_cost,
    ComponentConfig,
    CustomUnitTemplate,
    SPEED_PER_HULL_POINT,
    BASE_TURRET_COST,
    DMG_PER_POINT,
    RANGE_PER_POINT,
    COOLDOWN_BONUS,
    DEFENSE_PER_HULL_POINT,
    HYPERDRIVE_BASE_COST,
    HYPERDRIVE_RANGE_PER_POINT,
    ABILITY_BASE_COST,
    ABILITY_COST_PER_ABILITY,
)
from constants import HullSize


# ---------------------------------------------------------------------------
# calc_engine_hull_cost
# ---------------------------------------------------------------------------

class TestCalcEngineHullCost:
    def test_speed_100_gives_5(self):
        """Default speed 100 should yield hull cost 5 on MEDIUM baseline hull."""
        assert calc_engine_hull_cost(100.0, HullSize.MEDIUM) == 5

    def test_speed_200_gives_10(self):
        assert calc_engine_hull_cost(200.0, HullSize.MEDIUM) == 10

    def test_speed_50_gives_2_point_5(self):
        assert calc_engine_hull_cost(50.0, HullSize.MEDIUM) == 2.5

    def test_speed_1_gives_fractional(self):
        assert calc_engine_hull_cost(1.0, HullSize.MEDIUM) == 0.05

    def test_speed_0_gives_0(self):
        """Zero speed = no thrust = no hull cost."""
        assert calc_engine_hull_cost(0.0, HullSize.MEDIUM) == 0.0

    def test_speed_negative_gives_0(self):
        assert calc_engine_hull_cost(-10.0, HullSize.MEDIUM) == 0.0

    def test_speed_exactly_on_boundary(self):
        """Speed exactly divisible by SPEED_PER_HULL_POINT."""
        assert calc_engine_hull_cost(SPEED_PER_HULL_POINT, HullSize.MEDIUM) == 1.0

    def test_result_always_float(self):
        assert isinstance(calc_engine_hull_cost(137.5, HullSize.MEDIUM), float)

    def test_hull_size_multipliers_for_speed_100(self):
        """Verify speed 100 scales according to hull size multipliers."""
        assert calc_engine_hull_cost(100.0, HullSize.STRIKECRAFT_WING) == 2.0  # 5 * 0.4 = 2.0
        assert calc_engine_hull_cost(100.0, HullSize.TINY) == 3.0             # 5 * 0.6 = 3.0
        assert calc_engine_hull_cost(100.0, HullSize.SMALL) == 4.0            # 5 * 0.8 = 4.0
        assert calc_engine_hull_cost(100.0, HullSize.MEDIUM) == 5.0           # 5 * 1.0 = 5.0
        assert calc_engine_hull_cost(100.0, HullSize.LARGE) == 7.5            # 5 * 1.5 = 7.5
        assert calc_engine_hull_cost(100.0, HullSize.HUGE) == 10.0           # 5 * 2.0 = 10.0


# ---------------------------------------------------------------------------
# calc_turret_hull_cost
# ---------------------------------------------------------------------------

class TestCalcTurretHullCost:
    def _standard(self, dmg, rng, cd, variant="STANDARD"):
        return TurretConfig(turret_type="MASS_DRIVER", damage=dmg, range=rng, cooldown=cd, variant=variant)

    def test_typical_mass_driver_standard(self):
        """Mass driver: dmg=10, rng=300, cd=2, STANDARD → 1 + 2 + 3 + 1 = 7.0."""
        t = self._standard(10, 300, 2)
        assert calc_turret_hull_cost(t) == 7.0

    def test_minimum_is_positive(self):
        t = self._standard(0.01, 0.01, 99)
        assert calc_turret_hull_cost(t) > 0.0

    def test_high_damage_increases_cost(self):
        t_low = self._standard(10, 300, 2)
        t_high = self._standard(50, 300, 2)
        assert calc_turret_hull_cost(t_high) > calc_turret_hull_cost(t_low)

    def test_high_range_increases_cost(self):
        t_low = self._standard(10, 100, 2)
        t_high = self._standard(10, 600, 2)
        assert calc_turret_hull_cost(t_high) > calc_turret_hull_cost(t_low)

    def test_low_cooldown_increases_cost(self):
        """Lower cooldown = fires faster = more expensive."""
        t_slow = self._standard(10, 300, 5)
        t_fast = self._standard(10, 300, 1)
        assert calc_turret_hull_cost(t_fast) > calc_turret_hull_cost(t_slow)

    def test_long_range_variant_costs_more_than_standard(self):
        """LONG_RANGE variant triples effective range and cooldown in pricing."""
        t_std = self._standard(10, 300, 2, "STANDARD")
        t_lr = self._standard(10, 300, 2, "LONG_RANGE")
        assert calc_turret_hull_cost(t_lr) > calc_turret_hull_cost(t_std)

    def test_result_always_float(self):
        assert isinstance(calc_turret_hull_cost(self._standard(10, 300, 2)), float)


# ---------------------------------------------------------------------------
# calc_weapons_hull_cost
# ---------------------------------------------------------------------------

class TestCalcWeaponsHullCost:
    def _t(self):
        return TurretConfig(turret_type="BEAM", damage=15, range=400, cooldown=3, variant="STANDARD")

    def test_no_turrets_returns_0(self):
        assert calc_weapons_hull_cost([]) == 0

    def test_single_turret(self):
        t = self._t()
        assert calc_weapons_hull_cost([t]) == calc_turret_hull_cost(t)

    def test_multiple_turrets_sum(self):
        t = self._t()
        assert calc_weapons_hull_cost([t, t]) == calc_turret_hull_cost(t) * 2

    def test_two_different_turrets(self):
        t1 = TurretConfig("MASS_DRIVER", 10, 300, 2, "STANDARD")
        t2 = TurretConfig("MISSILE", 20, 350, 2, "STANDARD")
        expected = calc_turret_hull_cost(t1) + calc_turret_hull_cost(t2)
        assert calc_weapons_hull_cost([t1, t2]) == expected


# ---------------------------------------------------------------------------
# calc_defenses_hull_cost
# ---------------------------------------------------------------------------

class TestCalcDefensesHullCost:
    def test_all_zeros_returns_0(self):
        assert calc_defenses_hull_cost(0, 0, 0) == 0.0

    def test_equal_spread_5_5_5(self):
        """armor=5 + shields=5 + pd=5 = 15 total → 15 / 3 = 5.0."""
        assert calc_defenses_hull_cost(5, 5, 5) == 5.0

    def test_equal_spread_10_10_10(self):
        """30 total → 30 / 3 = 10.0."""
        assert calc_defenses_hull_cost(10, 10, 10) == 10.0

    def test_nonzero_when_any_nonzero(self):
        assert calc_defenses_hull_cost(1, 0, 0) == 1 / 3.0

    def test_more_total_higher_cost(self):
        low = calc_defenses_hull_cost(2, 2, 2)
        high = calc_defenses_hull_cost(20, 20, 20)
        assert high > low

    def test_result_always_float(self):
        assert isinstance(calc_defenses_hull_cost(7, 3, 5), float)


# ---------------------------------------------------------------------------
# calc_hyperdrive_hull_cost
# ---------------------------------------------------------------------------

class TestCalcHyperdriveCost:
    def test_basic_range5(self):
        """BASIC + range 5 → 3 + 5/5 = 3 + 1 = 4.0."""
        assert calc_hyperdrive_hull_cost("BASIC", 5) == 4.0

    def test_advanced_range5(self):
        """ADVANCED + range 5 → 7 + 1 = 8.0."""
        assert calc_hyperdrive_hull_cost("ADVANCED", 5) == 8.0

    def test_basic_range10(self):
        """BASIC + range 10 → 3 + 10/5 = 3 + 2 = 5.0."""
        assert calc_hyperdrive_hull_cost("BASIC", 10) == 5.0

    def test_advanced_range10(self):
        """ADVANCED + range 10 → 7 + 2 = 9.0."""
        assert calc_hyperdrive_hull_cost("ADVANCED", 10) == 9.0

    def test_longer_range_costs_more(self):
        assert calc_hyperdrive_hull_cost("BASIC", 20) > calc_hyperdrive_hull_cost("BASIC", 5)

    def test_advanced_costs_more_than_basic_same_range(self):
        assert calc_hyperdrive_hull_cost("ADVANCED", 5) > calc_hyperdrive_hull_cost("BASIC", 5)

    def test_case_insensitive(self):
        assert calc_hyperdrive_hull_cost("basic", 5) == calc_hyperdrive_hull_cost("BASIC", 5)

    def test_minimum_is_1(self):
        assert calc_hyperdrive_hull_cost("BASIC", 0) >= 1.0

    def test_result_always_float(self):
        assert isinstance(calc_hyperdrive_hull_cost("ADVANCED", 7), float)

    def test_hyperdrive_hull_cost_scales_with_hull_size(self):
        # BASIC, range 5 has base raw cost of 3 + (5/5) = 4.0
        assert calc_hyperdrive_hull_cost("BASIC", 5, HullSize.STRIKECRAFT_WING) == 1.6  # 4 * 0.4 = 1.6
        assert calc_hyperdrive_hull_cost("BASIC", 5, HullSize.TINY) == 2.4             # 4 * 0.6 = 2.4
        assert calc_hyperdrive_hull_cost("BASIC", 5, HullSize.SMALL) == 3.2            # 4 * 0.8 = 3.2
        assert calc_hyperdrive_hull_cost("BASIC", 5, HullSize.MEDIUM) == 4.0           # 4 * 1.0 = 4.0
        assert calc_hyperdrive_hull_cost("BASIC", 5, HullSize.LARGE) == 6.0            # 4 * 1.5 = 6.0
        assert calc_hyperdrive_hull_cost("BASIC", 5, HullSize.HUGE) == 8.0             # 4 * 2.0 = 8.0


# ---------------------------------------------------------------------------
# calc_ability_hull_cost
# ---------------------------------------------------------------------------

class TestCalcAbilityCost:
    def test_no_abilities_gives_base_cost(self):
        assert calc_ability_hull_cost([]) == ABILITY_BASE_COST

    def test_one_ability(self):
        assert calc_ability_hull_cost(["ion_bolt"]) == ABILITY_BASE_COST + ABILITY_COST_PER_ABILITY

    def test_multiple_abilities(self):
        assert calc_ability_hull_cost(["ion_bolt", "cluster_warhead", "repair_cloud"]) == \
               ABILITY_BASE_COST + 3 * ABILITY_COST_PER_ABILITY

    def test_result_always_float(self):
        assert isinstance(calc_ability_hull_cost(["ion_bolt"]), float)


# ---------------------------------------------------------------------------
# ComponentConfig computed properties
# ---------------------------------------------------------------------------

class TestComponentConfigProperties:
    def test_engine_hull_cost_property_uses_calc(self):
        c = ComponentConfig(has_engine=True, engine_speed=100.0)
        assert c.engine_hull_cost == calc_engine_hull_cost(100.0)

    def test_engine_hull_cost_zero_when_disabled(self):
        c = ComponentConfig(has_engine=False, engine_speed=100.0)
        assert c.engine_hull_cost == 0

    def test_hyperdrive_hull_cost_property(self):
        c = ComponentConfig(has_hyperdrive=True, hyperdrive_type="ADVANCED", hyperdrive_jump_range=10)
        assert c.hyperdrive_hull_cost == calc_hyperdrive_hull_cost("ADVANCED", 10)

    def test_hyperdrive_hull_cost_zero_when_disabled(self):
        c = ComponentConfig(has_hyperdrive=False)
        assert c.hyperdrive_hull_cost == 0

    def test_weapons_hull_cost_property(self):
        turrets = [TurretConfig("BEAM", 15, 400, 3, "STANDARD")]
        c = ComponentConfig(has_weapon_bays=True, turrets=turrets)
        assert c.weapon_bays_hull_cost == calc_weapons_hull_cost(turrets)

    def test_weapons_hull_cost_zero_when_disabled(self):
        c = ComponentConfig(has_weapon_bays=False, turrets=[TurretConfig("BEAM", 15, 400, 3)])
        assert c.weapon_bays_hull_cost == 0

    def test_defenses_hull_cost_property(self):
        c = ComponentConfig(has_defenses=True, armor=5, shields=5, point_defense=5)
        assert c.defenses_hull_cost == calc_defenses_hull_cost(5, 5, 5)

    def test_defenses_hull_cost_zero_when_disabled(self):
        c = ComponentConfig(has_defenses=False, armor=10, shields=10, point_defense=10)
        assert c.defenses_hull_cost == 0

    def test_ability_hull_cost_property_uses_calc(self):
        c = ComponentConfig(has_ability_component=True, abilities=["ion_bolt", "cluster_warhead"])
        assert c.ability_hull_cost == calc_ability_hull_cost(["ion_bolt", "cluster_warhead"])

    def test_ability_hull_cost_zero_when_disabled(self):
        c = ComponentConfig(has_ability_component=False, abilities=["ion_bolt", "cluster_warhead"])
        assert c.ability_hull_cost == 0


# ---------------------------------------------------------------------------
# CustomUnitTemplate.total_hull_cost
# ---------------------------------------------------------------------------

class TestCustomUnitTemplateHullCost:
    def _make(self, **comp_kwargs):
        comp = ComponentConfig(**comp_kwargs)
        return CustomUnitTemplate(
            design_name="TEST",
            display_name="Test Ship",
            hull_size=HullSize.MEDIUM,
            components=comp,
        )

    def test_no_components_costs_zero(self):
        t = self._make()
        assert t.total_hull_cost == 0

    def test_engine_only(self):
        t = self._make(has_engine=True, engine_speed=100.0)
        assert t.total_hull_cost == calc_engine_hull_cost(100.0, HullSize.MEDIUM)

    def test_engine_hull_cost_scales_with_template_hull_size(self):
        comp = ComponentConfig(has_engine=True, engine_speed=100.0)
        t_small = CustomUnitTemplate("S", "Small", HullSize.SMALL, comp)
        t_huge = CustomUnitTemplate("H", "Huge", HullSize.HUGE, comp)
        assert t_small.engine_hull_cost == 4.0
        assert t_huge.engine_hull_cost == 10.0
        assert t_huge.total_hull_cost > t_small.total_hull_cost

    def test_hyperdrive_only(self):
        t = self._make(has_hyperdrive=True, hyperdrive_type="BASIC", hyperdrive_jump_range=5)
        assert t.total_hull_cost == calc_hyperdrive_hull_cost("BASIC", 5, HullSize.MEDIUM)

    def test_hyperdrive_hull_cost_scales_with_template_hull_size(self):
        comp = ComponentConfig(has_hyperdrive=True, hyperdrive_type="BASIC", hyperdrive_jump_range=5)
        t_small = CustomUnitTemplate("S", "Small", HullSize.SMALL, comp)
        t_huge = CustomUnitTemplate("H", "Huge", HullSize.HUGE, comp)
        assert t_small.hyperdrive_hull_cost == 3.2
        assert t_huge.hyperdrive_hull_cost == 8.0
        assert t_huge.total_hull_cost > t_small.total_hull_cost

    def test_ability_only(self):
        t = self._make(has_ability_component=True, abilities=["ion_bolt"])
        assert t.total_hull_cost == calc_ability_hull_cost(["ion_bolt"])

    def test_engine_plus_hyperdrive(self):
        t = self._make(has_engine=True, engine_speed=100.0,
                       has_hyperdrive=True, hyperdrive_type="BASIC", hyperdrive_jump_range=5)
        expected = calc_engine_hull_cost(100.0) + calc_hyperdrive_hull_cost("BASIC", 5)
        assert t.total_hull_cost == expected

    def test_over_capacity_detected(self):
        """MEDIUM hull has capacity 50. Stuffing many components should trip is_over_capacity."""
        turrets = [TurretConfig("BEAM", 50, 600, 1, "STANDARD")] * 10
        t = self._make(
            has_engine=True, engine_speed=300.0,
            has_hyperdrive=True, hyperdrive_type="ADVANCED", hyperdrive_jump_range=20,
            has_weapon_bays=True, turrets=turrets,
            has_defenses=True, armor=20, shields=20, point_defense=20,
        )
        assert t.is_over_capacity

    def test_build_cost_scales_with_hull_usage(self):
        t_cheap = self._make(has_engine=True, engine_speed=50.0)
        t_expensive = self._make(has_engine=True, engine_speed=300.0)
        assert t_expensive.build_cost > t_cheap.build_cost


# ---------------------------------------------------------------------------
# validate() checks jump_range
# ---------------------------------------------------------------------------

class TestValidation:
    def test_jump_range_zero_fails(self):
        comp = ComponentConfig(
            has_hyperdrive=True,
            hyperdrive_type="BASIC",
            hyperdrive_jump_range=0,
            has_engine=True,
            engine_speed=100.0,
        )
        t = CustomUnitTemplate("X", "X", HullSize.SMALL, comp)
        errors = t.validate()
        assert any("jump range" in e.lower() for e in errors)

    def test_jump_range_1_passes(self):
        comp = ComponentConfig(
            has_hyperdrive=True,
            hyperdrive_type="BASIC",
            hyperdrive_jump_range=1,
            has_engine=True,
            engine_speed=100.0,
        )
        t = CustomUnitTemplate("X", "X", HullSize.SMALL, comp)
        errors = t.validate()
        assert not any("jump range" in e.lower() for e in errors)
