"""
tests/test_cloaking.py

Comprehensive test suite for Basic and Advanced Cloaking Devices:
- Component initialization, dynamic hull costs, and fuel drain rates
- Antimatter per-turn consumption and auto-deactivation
- Long-range vs short-range sensor visibility interactions
- Area cloaking fleet coverage
- Custom unit template validation, build cost calculations, and serialization
- Save/load game state persistence
"""

import pytest
from unittest.mock import MagicMock
from geometry import Position
from constants import (
    DEFAULT_SENSOR_SHORT_RANGE,
    HullSize,
    CLOAKING_BASIC_HULL_COST,
    CLOAKING_ADVANCED_HULL_COST,
    CLOAKING_BASIC_ANTIMATTER_COST_PER_TURN,
    CLOAKING_ADVANCED_ANTIMATTER_COST_PER_TURN,
    DEFAULT_ADVANCED_CLOAKING_RADIUS,
)
from entities import Player, Unit
from unit_components import (
    Sensors,
    AntimatterStorage,
    CloakingDevice,
    CloakingType,
)
from visibility import VisibilityService, is_unit_visible, hex_has_presence
from galaxy import Galaxy, StarSystem
from custom_unit_templates import (
    CustomUnitTemplate,
    ComponentConfig,
    calc_cloaking_hull_cost,
)


@pytest.fixture
def galaxy_setup():
    p1 = Player("Player 1", (0, 0, 255))
    p2 = Player("Player 2", (255, 0, 0))

    galaxy = Galaxy()
    system = StarSystem(name="Alpha", position=Position(0, 0), radius=3)
    galaxy.systems = {"Alpha": system}

    mock_game = MagicMock()
    mock_game.galaxy = galaxy
    mock_game.turn_number = 1

    return p1, p2, galaxy, system, mock_game


# --------------------------------------------------------------------------
# 1. Component initialization and cost calculations
# --------------------------------------------------------------------------

def test_basic_cloaking_initialization(galaxy_setup):
    p1, p2, galaxy, system, mock_game = galaxy_setup
    unit = Unit(p1, Position(0, 0), in_hex=(0, 0), in_system="Alpha", name="StealthScout", hull_size=HullSize.SMALL, game=mock_game)
    cloak = CloakingDevice(unit, device_type=CloakingType.BASIC)

    assert cloak.device_type == CloakingType.BASIC
    assert cloak.area_radius == 0.0
    assert cloak.hull_cost == CLOAKING_BASIC_HULL_COST
    assert cloak.get_antimatter_cost_per_turn() == CLOAKING_BASIC_ANTIMATTER_COST_PER_TURN
    assert cloak.is_active is False


def test_advanced_cloaking_initialization(galaxy_setup):
    p1, p2, galaxy, system, mock_game = galaxy_setup
    unit = Unit(p1, Position(0, 0), in_hex=(0, 0), in_system="Alpha", name="CloakCruiser", hull_size=HullSize.MEDIUM, game=mock_game)
    cloak = CloakingDevice(unit, device_type=CloakingType.ADVANCED, area_radius=600.0)

    assert cloak.device_type == CloakingType.ADVANCED
    assert cloak.area_radius == 600.0
    # Radius 600.0: hull cost = (600 / 500) * 30.0 = 36.0
    assert cloak.hull_cost == 36.0
    # Radius 600.0: AM cost = (600 / 500) * 20.0 = 24.0
    assert cloak.get_antimatter_cost_per_turn() == 24.0
    assert cloak.is_active is False


def test_calc_hull_cost_helper():
    assert CloakingDevice.calc_hull_cost(CloakingType.BASIC) == CLOAKING_BASIC_HULL_COST
    assert CloakingDevice.calc_hull_cost("basic") == CLOAKING_BASIC_HULL_COST
    assert CloakingDevice.calc_hull_cost(CloakingType.ADVANCED) == CLOAKING_ADVANCED_HULL_COST
    assert CloakingDevice.calc_hull_cost("ADVANCED") == CLOAKING_ADVANCED_HULL_COST
    assert CloakingDevice.calc_hull_cost("ADVANCED", area_radius=250.0) == 15.0
    assert CloakingDevice.calc_hull_cost(CloakingType.ADVANCED, area_radius=1000.0) == 60.0
    assert CloakingDevice.calc_hull_cost(CloakingType.ADVANCED, area_radius=0.0) == 0.0


# --------------------------------------------------------------------------
# 2. Antimatter consumption and auto-deactivation
# --------------------------------------------------------------------------

def test_antimatter_consumption_basic_cloak(galaxy_setup):
    p1, p2, galaxy, system, mock_game = galaxy_setup
    unit = Unit(p1, Position(0, 0), in_hex=(0, 0), in_system="Alpha", name="Infiltrator", hull_size=HullSize.SMALL, game=mock_game)
    am = AntimatterStorage(unit, max_capacity=100.0)
    am.current_amount = 10.0
    unit.add_component(am)
    cloak = CloakingDevice(unit, device_type=CloakingType.BASIC)
    unit.add_component(cloak)

    cloak.activate()
    assert cloak.is_active is True

    # 1st update consumes 5.0 AM (10.0 -> 5.0)
    cloak.update()
    assert am.current_amount == 5.0
    assert cloak.is_active is True

    # 2nd update consumes 5.0 AM (5.0 -> 0.0)
    cloak.update()
    assert am.current_amount == 0.0
    assert cloak.is_active is True

    # 3rd update attempts to consume 5.0 AM with 0 available -> auto-deactivates
    cloak.update()
    assert cloak.is_active is False


def test_antimatter_consumption_advanced_cloak(galaxy_setup):
    p1, p2, galaxy, system, mock_game = galaxy_setup
    unit = Unit(p1, Position(0, 0), in_hex=(0, 0), in_system="Alpha", name="FleetCloaker", hull_size=HullSize.MEDIUM, game=mock_game)
    am = AntimatterStorage(unit, max_capacity=100.0)
    am.current_amount = 30.0
    unit.add_component(am)
    cloak = CloakingDevice(unit, device_type=CloakingType.ADVANCED)
    unit.add_component(cloak)

    cloak.activate()
    assert cloak.is_active is True

    # 1st update consumes 20.0 AM (30.0 -> 10.0)
    cloak.update()
    assert am.current_amount == 10.0
    assert cloak.is_active is True

    # 2nd update needs 20.0 AM but only 10.0 left -> auto-deactivates
    cloak.update()
    assert cloak.is_active is False


def test_toggle_and_destroyed_handling(galaxy_setup):
    p1, p2, galaxy, system, mock_game = galaxy_setup
    unit = Unit(p1, Position(0, 0), in_hex=(0, 0), in_system="Alpha", name="StealthFrigate", hull_size=HullSize.SMALL, game=mock_game)
    cloak = CloakingDevice(unit, device_type=CloakingType.BASIC)
    unit.add_component(cloak)

    assert cloak.toggle() is True
    assert cloak.is_active is True
    assert cloak.toggle() is True
    assert cloak.is_active is False

    cloak.activate()
    cloak.current_hit_points = 0
    assert cloak.is_destroyed is True
    cloak.on_destroyed()
    assert cloak.is_active is False
    assert cloak.toggle() is False




# --------------------------------------------------------------------------
# 3. VisibilityService Sensor Interaction (Basic & Advanced Area Cloaking)
# --------------------------------------------------------------------------

def test_basic_cloaking_defeats_long_range_sensors(galaxy_setup):
    p1, p2, galaxy, system, mock_game = galaxy_setup

    # P1 sensor ship with long-range sensor hex coverage
    sensor_ship = Unit(p1, Position(0, 0), in_hex=(0, 0), in_system="Alpha", name="RadarBase", hull_size=HullSize.MEDIUM, game=mock_game)
    sensor_ship.remove_component(Sensors)
    sensor_ship.add_component(Sensors(sensor_ship, short_range_radius=2000.0, long_range_hexes=1, hull_cost=5))

    # P2 enemy stealth ship far away in same hex (3500 > short range 2000)
    enemy_stealth = Unit(p2, Position(3500, 0), in_hex=(0, 0), in_system="Alpha", name="EnemySpy", hull_size=HullSize.SMALL, game=mock_game)
    cloak = CloakingDevice(enemy_stealth, device_type=CloakingType.BASIC)
    enemy_stealth.add_component(cloak)

    system.hexes[(0, 0)].units.extend([sensor_ship, enemy_stealth])

    # Case A: Cloak inactive -> P1 detects enemy presence in (0, 0)
    cloak.deactivate()
    snapshot = VisibilityService.compute(galaxy, p1)
    assert hex_has_presence(snapshot, "Alpha", (0, 0)) is True
    assert is_unit_visible(snapshot, enemy_stealth) is False

    # Case B: Cloak active -> P1 does NOT detect presence in (0, 0)
    cloak.activate()
    snapshot = VisibilityService.compute(galaxy, p1)
    assert hex_has_presence(snapshot, "Alpha", (0, 0)) is False
    assert is_unit_visible(snapshot, enemy_stealth) is False

    # Case C: P1 moves within short range (1000 px) -> DETAILED visibility overrides cloak
    enemy_stealth.position = Position(1000, 0)
    snapshot = VisibilityService.compute(galaxy, p1)
    assert is_unit_visible(snapshot, enemy_stealth) is True


def test_advanced_area_cloaking_hides_fleet(galaxy_setup):
    p1, p2, galaxy, system, mock_game = galaxy_setup

    # P1 sensor platform with long-range coverage in (0, 0)
    sensor_ship = Unit(p1, Position(0, 0), in_hex=(0, 0), in_system="Alpha", name="Watcher", hull_size=HullSize.MEDIUM, game=mock_game)
    sensor_ship.remove_component(Sensors)
    sensor_ship.add_component(Sensors(sensor_ship, short_range_radius=1000.0, long_range_hexes=1, hull_cost=5))

    # P2 Fleet: 1 Cloak Carrier (Advanced) + 2 Escorts with NO cloaking devices
    # All stationed at (3500, 0), outside P1's 1000 px short range
    emitter_ship = Unit(p2, Position(3500, 0), in_hex=(0, 0), in_system="Alpha", name="CloakFlagship", hull_size=HullSize.LARGE, game=mock_game)
    adv_cloak = CloakingDevice(emitter_ship, device_type=CloakingType.ADVANCED, area_radius=DEFAULT_ADVANCED_CLOAKING_RADIUS)
    emitter_ship.add_component(adv_cloak)

    escort_in_radius = Unit(p2, Position(3700, 0), in_hex=(0, 0), in_system="Alpha", name="EscortA", hull_size=HullSize.SMALL, game=mock_game) # 200 px away <= 500
    escort_out_of_radius = Unit(p2, Position(4500, 0), in_hex=(0, 0), in_system="Alpha", name="EscortB", hull_size=HullSize.SMALL, game=mock_game) # 1000 px away > 500

    system.hexes[(0, 0)].units.extend([sensor_ship, emitter_ship, escort_in_radius, escort_out_of_radius])

    # Case 1: Advanced cloak active, but EscortB is outside 500 radius -> presence still reported
    adv_cloak.activate()
    snapshot = VisibilityService.compute(galaxy, p1)
    assert hex_has_presence(snapshot, "Alpha", (0, 0)) is True

    # Case 2: EscortB moves inside the 500 radius (Position 3600, 0) -> entire fleet is cloaked!
    escort_out_of_radius.position = Position(3600, 0)
    snapshot = VisibilityService.compute(galaxy, p1)
    assert hex_has_presence(snapshot, "Alpha", (0, 0)) is False

    # Case 3: Flagship deactivates cloak -> presence returns
    adv_cloak.deactivate()
    snapshot = VisibilityService.compute(galaxy, p1)
    assert hex_has_presence(snapshot, "Alpha", (0, 0)) is True


def test_area_cloak_does_not_cloak_hostile_units(galaxy_setup):
    p1, p2, galaxy, system, mock_game = galaxy_setup

    # P1 sensor ship
    sensor_ship = Unit(p1, Position(0, 0), in_hex=(0, 0), in_system="Alpha", name="SensorShip", hull_size=HullSize.MEDIUM, game=mock_game)
    sensor_ship.remove_component(Sensors)
    sensor_ship.add_component(Sensors(sensor_ship, short_range_radius=1000.0, long_range_hexes=1, hull_cost=5))

    # P1 neutral/hostile picket ship near P2's cloaker
    p1_scout = Unit(p1, Position(3550, 0), in_hex=(0, 0), in_system="Alpha", name="P1Scout", hull_size=HullSize.TINY, game=mock_game)

    # P2 emitter with active Advanced cloak
    p2_emitter = Unit(p2, Position(3500, 0), in_hex=(0, 0), in_system="Alpha", name="P2Emitter", hull_size=HullSize.LARGE, game=mock_game)
    adv_cloak = CloakingDevice(p2_emitter, device_type=CloakingType.ADVANCED, area_radius=500.0)
    p2_emitter.add_component(adv_cloak)
    adv_cloak.activate()

    system.hexes[(0, 0)].units.extend([sensor_ship, p1_scout, p2_emitter])

    # From P1's perspective: P2 emitter is cloaked, but P1 sees own scout
    snapshot_p1 = VisibilityService.compute(galaxy, p1)
    assert hex_has_presence(snapshot_p1, "Alpha", (0, 0)) is False
    assert is_unit_visible(snapshot_p1, p1_scout) is True


# --------------------------------------------------------------------------
# 4. Custom Unit Templates & Designer
# --------------------------------------------------------------------------

def test_template_cloaking_costs_and_validation():
    # Basic Cloak template
    t_basic = CustomUnitTemplate("Basic Stealth", HullSize.SMALL)
    t_basic.components.has_engine = True
    t_basic.components.has_cloaking_device = True
    t_basic.components.cloaking_type = "BASIC"

    assert t_basic.components.cloaking_device_hull_cost == CLOAKING_BASIC_HULL_COST
    assert t_basic.validate() == []
    # Build cost: SMALL base 250 + (engine 4.0 + cloak 10.0) * 30 = 250 + 420 = 670
    assert t_basic.build_cost == 670

    # Advanced Cloak template on MEDIUM hull
    t_adv = CustomUnitTemplate("Fleet Stealth Cruiser", HullSize.MEDIUM)
    t_adv.components.has_engine = True
    t_adv.components.has_cloaking_device = True
    t_adv.components.cloaking_type = "ADVANCED"

    assert t_adv.components.cloaking_device_hull_cost == CLOAKING_ADVANCED_HULL_COST
    assert t_adv.validate() == []
    # Build cost: MEDIUM base 500 + (engine 5.0 + cloak 30.0) * 30 = 500 + 1050 = 1550
    assert t_adv.build_cost == 1550

    # Advanced Cloak forbidden on TINY hull
    t_tiny_adv = CustomUnitTemplate("Tiny Adv Cloak", HullSize.TINY)
    t_tiny_adv.components.has_engine = True
    t_tiny_adv.components.has_cloaking_device = True
    t_tiny_adv.components.cloaking_type = "ADVANCED"

    errors = t_tiny_adv.validate()
    assert any("ADVANCED cloaking device requires at least" in e for e in errors)


def test_template_dict_roundtrip():
    from custom_unit_templates import CustomTemplateManager
    mgr = CustomTemplateManager()

    t = CustomUnitTemplate("Phantom Cruiser", HullSize.MEDIUM)
    t.components.has_engine = True
    t.components.has_cloaking_device = True
    t.components.cloaking_type = "ADVANCED"
    t.components.cloaking_radius = 650.0

    d = mgr._template_to_dict(t)
    assert d["has_cloaking_device"] is True
    assert d["cloaking_type"] == "ADVANCED"
    assert d["cloaking_radius"] == 650.0
    # (650 / 500) * 30.0 = 39.0
    assert d["cloaking_hull_cost"] == 39.0

    rebuilt = mgr._dict_to_template("Phantom Cruiser", d)
    assert rebuilt.components.has_cloaking_device is True
    assert rebuilt.components.cloaking_type == "ADVANCED"
    assert rebuilt.components.cloaking_radius == 650.0
    assert rebuilt.components.cloaking_device_hull_cost == 39.0


def test_advanced_cloaking_radius_scaling_hull_credits_antimatter(galaxy_setup):
    p1, p2, galaxy, system, mock_game = galaxy_setup
    for radius, expected_hull, expected_am, expected_cloak_credit_contrib in [
        (250.0, 15.0, 10.0, 450),
        (500.0, 30.0, 20.0, 900),
        (750.0, 45.0, 30.0, 1350),
        (1000.0, 60.0, 40.0, 1800),
    ]:
        unit = Unit(p1, Position(0, 0), in_hex=(0, 0), in_system="Alpha", name="ScalingCloaker", hull_size=HullSize.MEDIUM, game=mock_game)
        cloak = CloakingDevice(unit, device_type=CloakingType.ADVANCED, area_radius=radius)
        assert cloak.area_radius == radius
        assert cloak.hull_cost == expected_hull
        assert cloak.get_antimatter_cost_per_turn() == expected_am

        # Template cost calculation
        t = CustomUnitTemplate("Test Cloak Ship", HullSize.MEDIUM)
        t.components.has_engine = True  # MEDIUM engine = 5.0 hull
        t.components.has_cloaking_device = True
        t.components.cloaking_type = "ADVANCED"
        t.components.cloaking_radius = radius

        assert t.components.cloaking_device_hull_cost == expected_hull
        # Base hull cost for MEDIUM = 500; engine = 5.0 * 30 = 150; cloak = expected_cloak_credit_contrib
        assert t.build_cost == 500 + 150 + expected_cloak_credit_contrib


def test_basic_cloaking_unaffected_by_radius(galaxy_setup):
    p1, p2, galaxy, system, mock_game = galaxy_setup
    unit = Unit(p1, Position(0, 0), in_hex=(0, 0), in_system="Alpha", name="BasicShip", hull_size=HullSize.SMALL, game=mock_game)
    cloak = CloakingDevice(unit, device_type=CloakingType.BASIC, area_radius=800.0)

    assert cloak.area_radius == 0.0
    assert cloak.hull_cost == CLOAKING_BASIC_HULL_COST
    assert cloak.get_antimatter_cost_per_turn() == CLOAKING_BASIC_ANTIMATTER_COST_PER_TURN

    t = CustomUnitTemplate("Basic Cloak Ship", HullSize.SMALL)
    t.components.has_engine = True  # SMALL engine = 4.0 hull
    t.components.has_cloaking_device = True
    t.components.cloaking_type = "BASIC"
    t.components.cloaking_radius = 800.0  # Should be ignored for BASIC

    assert t.components.cloaking_device_hull_cost == CLOAKING_BASIC_HULL_COST
    # Base SMALL = 250 + (4.0 + 10.0) * 30 = 250 + 420 = 670
    assert t.build_cost == 670


# --------------------------------------------------------------------------
# 5. Save / Load Serialization
# --------------------------------------------------------------------------

def test_save_manager_cloaking_serialization(galaxy_setup):
    p1, p2, galaxy, system, mock_game = galaxy_setup
    from save_manager import serialize_unit, deserialize_unit

    unit = Unit(p1, Position(100, 200), in_hex=(0, 0), in_system="Alpha", name="ShadowVessel", hull_size=HullSize.MEDIUM, game=mock_game)
    cloak = CloakingDevice(unit, device_type=CloakingType.ADVANCED, area_radius=750.0)
    cloak.activate()
    unit.add_component(cloak)

    serialized = serialize_unit(unit)
    assert "CloakingDevice" in serialized["components"]
    comp_data = serialized["components"]["CloakingDevice"]
    assert comp_data["is_active"] is True
    assert comp_data["device_type"] == "ADVANCED"
    assert comp_data["area_radius"] == 750.0

    players_by_id = {p1.id: p1}
    restored = deserialize_unit(serialized, players_by_id, mock_game)
    assert restored.cloaking_component is not None
    assert restored.cloaking_component.is_active is True
    assert restored.cloaking_component.device_type == CloakingType.ADVANCED
    assert restored.cloaking_component.area_radius == 750.0
