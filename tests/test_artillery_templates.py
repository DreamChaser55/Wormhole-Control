"""Tests for dedicated long-range (artillery) unit designs."""
from constants import HullSize
from geometry import Position
from unit_components.enums import TurretVariant
from unit_templates import UNIT_TEMPLATES
from unit_components.constructor import instantiate_unit_from_template
from tests.support.commands import world


ARTILLERY_KEYS = [
    "ARTILLERY_FRIGATE",
    "RAILGUN_CRUISER",
    "LANCE_CRUISER",
    "ARTILLERY_BATTERY",
    "ARTILLERY_DREADNOUGHT",
]


def test_artillery_templates_exist_and_have_long_range_turrets():
    """All 5 dedicated artillery templates must be registered and contain LONG_RANGE turrets."""
    for key in ARTILLERY_KEYS:
        assert key in UNIT_TEMPLATES, f"Template {key} not found in UNIT_TEMPLATES"
        template = UNIT_TEMPLATES[key]
        assert template.get("has_weapon_bays") is True
        turrets = template.get("turrets", [])
        long_range_turrets = [t for t in turrets if t.get("variant") == "LONG_RANGE"]
        assert len(long_range_turrets) >= 1, f"{key} must have at least one LONG_RANGE turret"


def test_artillery_dreadnought_tri_weapon_composition():
    """Artillery Dreadnought must feature all 3 turret types with LONG_RANGE variant."""
    template = UNIT_TEMPLATES["ARTILLERY_DREADNOUGHT"]
    assert template["hull_size"] == HullSize.HUGE
    turrets = template.get("turrets", [])
    lr_types = {t["type"] for t in turrets if t.get("variant") == "LONG_RANGE"}
    assert "MISSILE" in lr_types, "Artillery Dreadnought must feature long-range missiles"
    assert "MASS_DRIVER" in lr_types, "Artillery Dreadnought must feature long-range mass drivers"
    assert "BEAM" in lr_types, "Artillery Dreadnought must feature long-range beams"

    # Also verify anti-strikecraft point defense
    as_turrets = [t for t in turrets if t.get("variant") == "ANTI_STRIKECRAFT"]
    assert len(as_turrets) >= 2, "Artillery Dreadnought must feature anti-strikecraft screen"


def test_railgun_cruiser_kinetic_focus():
    """Railgun Cruiser must feature long-range kinetic (MASS_DRIVER) weaponry."""
    template = UNIT_TEMPLATES["RAILGUN_CRUISER"]
    assert template["hull_size"] == HullSize.LARGE
    turrets = template.get("turrets", [])
    lr_types = {t["type"] for t in turrets if t.get("variant") == "LONG_RANGE"}
    assert lr_types == {"MASS_DRIVER"}
    assert template["roles"] == ["ranged kinetic fire support"]


def test_lance_cruiser_energy_focus():
    """Lance Cruiser must feature long-range energy (BEAM) weaponry."""
    template = UNIT_TEMPLATES["LANCE_CRUISER"]
    assert template["hull_size"] == HullSize.LARGE
    turrets = template.get("turrets", [])
    lr_types = {t["type"] for t in turrets if t.get("variant") == "LONG_RANGE"}
    assert lr_types == {"BEAM"}
    assert template["roles"] == ["ranged energy fire support"]


def test_artillery_battery_station_attributes():
    """Artillery Battery must be a stationary installation without engines or hyperdrive."""
    template = UNIT_TEMPLATES["ARTILLERY_BATTERY"]
    assert template["hull_size"] == HullSize.MEDIUM
    assert template.get("has_engine") is False
    assert template.get("has_hyperdrive") is False
    assert template["roles"] == ["stationary fire support"]
    assert "Stationary installation" in template["description"]


def test_artillery_frigate_mobile_fire_support():
    """Artillery Frigate must be a mobile medium warship with long-range missile capability."""
    template = UNIT_TEMPLATES["ARTILLERY_FRIGATE"]
    assert template["hull_size"] == HullSize.MEDIUM
    assert template.get("has_engine") is True
    assert template.get("has_hyperdrive") is True
    turrets = template.get("turrets", [])
    lr_types = {t["type"] for t in turrets if t.get("variant") == "LONG_RANGE"}
    assert "MISSILE" in lr_types


def test_instantiate_and_long_range_capabilities():
    """Units instantiated in a live game must initialize turrets with 3x effective range."""
    game, player, _, _ = world()
    for key in ARTILLERY_KEYS:
        unit = instantiate_unit_from_template(
            key, player, "Sol", (0, 0), Position(100, 100), game.galaxy, game
        )
        assert unit is not None
        assert unit.weapons_component is not None
        lr_turrets = [t for t in unit.weapons_component.turrets if t.variant == TurretVariant.LONG_RANGE]
        assert len(lr_turrets) >= 1
        for t in lr_turrets:
            # Effective range of long-range turrets is 3x base range (base 400 -> 1200)
            assert t.range == 1200.0
            # Effective cooldown is 3x base cooldown (base 3 -> 9)
            assert t.cooldown == 9
