import pytest
from unittest.mock import MagicMock
from geometry import Position
from constants import HullSize
from unit_components import (
    StrikecraftWingComponent, WingType, Weapons, Turret, TurretType, TurretVariant
)
from custom_unit_templates import CustomUnitTemplate, ComponentConfig, TurretConfig
from tests.test_unit_components import MockUnit as BaseMockUnit, MockPlayer

class MockUnit(BaseMockUnit):
    @property
    def strikecraft_wing_component(self):
        return self.get_component(StrikecraftWingComponent)

def test_fighter_wing_targeting():
    # Attacker
    attacker = MockUnit()
    attacker.hull_size = HullSize.STRIKECRAFT_WING
    wing_comp = StrikecraftWingComponent(attacker, wing_type=WingType.FIGHTER)
    attacker.add_component(wing_comp)
    
    weapons = Weapons(attacker)
    turret = Turret(
        turret_type=TurretType.MASS_DRIVER,
        damage=5, range=200, cooldown=1,
        parent_unit=attacker,
        variant=TurretVariant.ANTI_STRIKECRAFT
    )
    weapons.add_turret(turret)
    attacker.add_component(weapons)

    # Strikecraft Target
    target_wing = MockUnit()
    target_wing.hull_size = HullSize.STRIKECRAFT_WING

    # Large Ship Target
    target_large = MockUnit()
    target_large.hull_size = HullSize.LARGE

    # Test targeting wing (Success)
    weapons.set_target(target_wing)
    assert turret.target == target_wing

    # Reset target
    weapons.set_target(None)
    assert turret.target is None

    # Test targeting large ship (Failure)
    weapons.set_target(target_large)
    assert turret.target is None


def test_bomber_wing_targeting():
    # Attacker
    attacker = MockUnit()
    attacker.hull_size = HullSize.STRIKECRAFT_WING
    wing_comp = StrikecraftWingComponent(attacker, wing_type=WingType.BOMBER)
    attacker.add_component(wing_comp)
    
    weapons = Weapons(attacker)
    turret = Turret(
        turret_type=TurretType.MASS_DRIVER,
        damage=5, range=200, cooldown=1,
        parent_unit=attacker,
        variant=TurretVariant.STANDARD
    )
    weapons.add_turret(turret)
    attacker.add_component(weapons)

    # Strikecraft Target
    target_wing = MockUnit()
    target_wing.hull_size = HullSize.STRIKECRAFT_WING

    # Large Ship Target
    target_large = MockUnit()
    target_large.hull_size = HullSize.LARGE

    # Test targeting large ship (Success)
    weapons.set_target(target_large)
    assert turret.target == target_large

    # Reset target
    weapons.set_target(None)
    assert turret.target is None

    # Test targeting wing (Failure)
    weapons.set_target(target_wing)
    assert turret.target is None


def test_strikecraft_design_validation():
    # 1. Fighter design with standard turret (Invalid)
    config_invalid_fighter = ComponentConfig(
        has_engine=True,
        engine_speed=20.0,
        has_weapon_bays=True,
        wing_type="FIGHTER",
        turrets=[
            TurretConfig(
                turret_type="MASS_DRIVER",
                damage=0, range=0, cooldown=2,
                variant="STANDARD"
            )
        ]
    )
    template_invalid_fighter = CustomUnitTemplate(
        design_name="Invalid Fighter",
        display_name="Invalid Fighter Wing",
        hull_size=HullSize.STRIKECRAFT_WING,
        components=config_invalid_fighter
    )
    errors = template_invalid_fighter.validate()
    assert any("must be ANTI_STRIKECRAFT" in e for e in errors)

    # 2. Fighter design with anti-strikecraft turret (Valid)
    config_valid_fighter = ComponentConfig(
        has_engine=True,
        engine_speed=20.0,
        has_weapon_bays=True,
        wing_type="FIGHTER",
        turrets=[
            TurretConfig(
                turret_type="MASS_DRIVER",
                damage=0, range=0, cooldown=2,
                variant="ANTI_STRIKECRAFT"
            )
        ]
    )
    template_valid_fighter = CustomUnitTemplate(
        design_name="Valid Fighter",
        display_name="Valid Fighter Wing",
        hull_size=HullSize.STRIKECRAFT_WING,
        components=config_valid_fighter
    )
    assert template_valid_fighter.validate() == []

    # 3. Bomber design with anti-strikecraft turret (Invalid)
    config_invalid_bomber = ComponentConfig(
        has_engine=True,
        engine_speed=20.0,
        has_weapon_bays=True,
        wing_type="BOMBER",
        turrets=[
            TurretConfig(
                turret_type="MASS_DRIVER",
                damage=0, range=0, cooldown=2,
                variant="ANTI_STRIKECRAFT"
            )
        ]
    )
    template_invalid_bomber = CustomUnitTemplate(
        design_name="Invalid Bomber",
        display_name="Invalid Bomber Wing",
        hull_size=HullSize.STRIKECRAFT_WING,
        components=config_invalid_bomber
    )
    errors = template_invalid_bomber.validate()
    assert any("cannot be ANTI_STRIKECRAFT" in e for e in errors)

    # 4. Bomber design with standard/long range turret (Valid)
    config_valid_bomber = ComponentConfig(
        has_engine=True,
        engine_speed=20.0,
        has_weapon_bays=True,
        wing_type="BOMBER",
        turrets=[
            TurretConfig(
                turret_type="MASS_DRIVER",
                damage=0, range=0, cooldown=2,
                variant="STANDARD"
            )
        ]
    )
    template_valid_bomber = CustomUnitTemplate(
        design_name="Valid Bomber",
        display_name="Valid Bomber Wing",
        hull_size=HullSize.STRIKECRAFT_WING,
        components=config_valid_bomber
    )
    assert template_valid_bomber.validate() == []
