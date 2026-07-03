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
        """Default speed 100 should yield hull cost 5 (matching old default)."""
        assert calc_engine_hull_cost(100.0) == 5

    def test_speed_200_gives_10(self):
        assert calc_engine_hull_cost(200.0) == 10

    def test_speed_50_gives_3(self):
        # ceil(50 / 20) = ceil(2.5) = 3
        assert calc_engine_hull_cost(50.0) == 3

    def test_speed_1_gives_minimum_1(self):
        assert calc_engine_hull_cost(1.0) == 1

    def test_speed_0_gives_0(self):
        """Zero speed = no thrust = no hull cost."""
        assert calc_engine_hull_cost(0.0) == 0

    def test_speed_negative_gives_0(self):
        assert calc_engine_hull_cost(-10.0) == 0

    def test_speed_exactly_on_boundary(self):
        """Speed exactly divisible by SPEED_PER_HULL_POINT."""
        assert calc_engine_hull_cost(SPEED_PER_HULL_POINT) == 1

    def test_result_always_int(self):
        assert isinstance(calc_engine_hull_cost(137.5), int)


# ---------------------------------------------------------------------------
# calc_turret_hull_cost
# ---------------------------------------------------------------------------

class TestCalcTurretHullCost:
    def _standard(self, dmg, rng, cd, variant="STANDARD"):
        return TurretConfig(turret_type="MASS_DRIVER", damage=dmg, range=rng, cooldown=cd, variant=variant)

    def test_typical_mass_driver_standard(self):
        """Mass driver: dmg=10, rng=300, cd=2, STANDARD → ceil(1 + 2 + 3 + 1) = 7."""
        t = self._standard(10, 300, 2)
        assert calc_turret_hull_cost(t) == 7

    def test_minimum_is_1(self):
        """Even a trivially weak turret costs at least 1."""
        t = self._standard(0.01, 0.01, 99)
        assert calc_turret_hull_cost(t) >= 1

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

    def test_result_always_int(self):
        assert isinstance(calc_turret_hull_cost(self._standard(10, 300, 2)), int)


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
        assert calc_defenses_hull_cost(0, 0, 0) == 0

    def test_equal_spread_5_5_5(self):
        """armor=5 + shields=5 + pd=5 = 15 total → ceil(15 / 3) = 5."""
        assert calc_defenses_hull_cost(5, 5, 5) == 5

    def test_equal_spread_10_10_10(self):
        """30 total → ceil(30 / 3) = 10."""
        assert calc_defenses_hull_cost(10, 10, 10) == 10

    def test_minimum_is_1_when_any_nonzero(self):
        assert calc_defenses_hull_cost(1, 0, 0) == 1

    def test_more_total_higher_cost(self):
        low = calc_defenses_hull_cost(2, 2, 2)
        high = calc_defenses_hull_cost(20, 20, 20)
        assert high > low

    def test_result_always_int(self):
        assert isinstance(calc_defenses_hull_cost(7, 3, 5), int)


# ---------------------------------------------------------------------------
# calc_hyperdrive_hull_cost
# ---------------------------------------------------------------------------

class TestCalcHyperdriveCost:
    def test_basic_range5(self):
        """BASIC + range 5 → 3 + ceil(5/5) = 3 + 1 = 4."""
        assert calc_hyperdrive_hull_cost("BASIC", 5) == 4

    def test_advanced_range5(self):
        """ADVANCED + range 5 → 7 + 1 = 8."""
        assert calc_hyperdrive_hull_cost("ADVANCED", 5) == 8

    def test_basic_range10(self):
        """BASIC + range 10 → 3 + ceil(10/5) = 3 + 2 = 5."""
        assert calc_hyperdrive_hull_cost("BASIC", 10) == 5

    def test_advanced_range10(self):
        """ADVANCED + range 10 → 7 + 2 = 9."""
        assert calc_hyperdrive_hull_cost("ADVANCED", 10) == 9

    def test_longer_range_costs_more(self):
        assert calc_hyperdrive_hull_cost("BASIC", 20) > calc_hyperdrive_hull_cost("BASIC", 5)

    def test_advanced_costs_more_than_basic_same_range(self):
        assert calc_hyperdrive_hull_cost("ADVANCED", 5) > calc_hyperdrive_hull_cost("BASIC", 5)

    def test_case_insensitive(self):
        assert calc_hyperdrive_hull_cost("basic", 5) == calc_hyperdrive_hull_cost("BASIC", 5)

    def test_minimum_is_1(self):
        assert calc_hyperdrive_hull_cost("BASIC", 0) >= 1

    def test_result_always_int(self):
        assert isinstance(calc_hyperdrive_hull_cost("ADVANCED", 7), int)


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

    def test_result_always_int(self):
        assert isinstance(calc_ability_hull_cost(["ion_bolt"]), int)


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
        assert t.total_hull_cost == calc_engine_hull_cost(100.0)

    def test_hyperdrive_only(self):
        t = self._make(has_hyperdrive=True, hyperdrive_type="BASIC", hyperdrive_jump_range=5)
        assert t.total_hull_cost == calc_hyperdrive_hull_cost("BASIC", 5)

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
