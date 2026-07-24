import os
import tempfile
import pytest
from constants import HullSize, ANTIMATTER_CAPACITY_PER_HULL_POINT
from custom_unit_templates import (
    calc_antimatter_hull_cost,
    ComponentConfig,
    CustomUnitTemplate,
    CustomTemplateManager,
)
from unit_components import AntimatterStorage, Constructor
from geometry import Position
from unit_templates import UNIT_TEMPLATES


def test_calc_antimatter_hull_cost():
    assert calc_antimatter_hull_cost(0) == 0
    assert calc_antimatter_hull_cost(-10) == 0
    assert calc_antimatter_hull_cost(100) == 5
    assert calc_antimatter_hull_cost(200) == 10
    assert calc_antimatter_hull_cost(50) == 5
    assert calc_antimatter_hull_cost(1) == 5


def test_component_config_antimatter_hull_cost():
    comp = ComponentConfig(has_antimatter_storage=True, antimatter_capacity=100.0)
    assert comp.antimatter_hull_cost == 5

    comp.antimatter_capacity = 200.0
    assert comp.antimatter_hull_cost == 10

    comp.has_antimatter_storage = False
    assert comp.antimatter_hull_cost == 0


def test_custom_unit_template_total_hull_cost_and_validation():
    comp = ComponentConfig(
        has_engine=True,
        engine_speed=100.0,  # 5 hull cost
        has_antimatter_storage=True,
        antimatter_capacity=150.0,  # ceil(150/20) = 8 hull cost
    )
    template = CustomUnitTemplate(
        design_name="AM_TEST",
        display_name="AM Test Ship",
        hull_size=HullSize.MEDIUM,  # capacity 50
        components=comp,
    )
    assert template.total_hull_cost == 5 + 8
    assert template.validate() == []

    # Test invalid capacity below 100.0
    comp.antimatter_capacity = 50.0
    errors = template.validate()
    assert any("Antimatter storage capacity must be at least 100.0" in e for e in errors)


def test_custom_template_manager_serialization():
    import custom_unit_templates as ctm
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    tmp.write("{}")
    tmp.close()
    orig_data_file = ctm._DATA_FILE
    ctm._DATA_FILE = tmp.name
    try:
        mgr = CustomTemplateManager()
        comp = ComponentConfig(
            has_engine=True,
            engine_speed=100.0,
            has_antimatter_storage=True,
            antimatter_capacity=300.0,
        )
        template = CustomUnitTemplate(
            design_name="AM_SER_TEST",
            display_name="AM Ser Test",
            hull_size=HullSize.LARGE,
            components=comp,
        )
        errors = mgr.save_design(template)
        assert errors == []

        loaded = mgr.get_design("AM_SER_TEST")
        assert loaded is not None
        assert loaded.components.has_antimatter_storage is True
        assert loaded.components.antimatter_capacity == 300.0
        assert loaded.components.antimatter_hull_cost == 15

        # Check registered dict format
        tdict = UNIT_TEMPLATES["AM_SER_TEST"]
        assert tdict["has_antimatter_storage"] is True
        assert tdict["antimatter_capacity"] == 300.0
        assert tdict["antimatter_hull_cost"] == 15
    finally:
        ctm._DATA_FILE = orig_data_file
        os.unlink(tmp.name)
        # Clean up any test entries injected into the global UNIT_TEMPLATES
        for k in list(UNIT_TEMPLATES.keys()):
            if UNIT_TEMPLATES[k].get("is_custom"):
                del UNIT_TEMPLATES[k]


def test_create_unit_from_template_custom_antimatter():
    import custom_unit_templates as ctm

    class DummyOwner:
        id = 1

    class DummySystem:
        name = "Sol"
        def add_unit(self, unit): pass

    class DummyGalaxy:
        systems = {"Sol": DummySystem()}

    class DummyUnit:
        game = None
        name = "Builder"

    builder_unit = DummyUnit()
    constructor = Constructor(builder_unit, hull_cost=15)
    galaxy = DummyGalaxy()
    owner = DummyOwner()

    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    tmp.write("{}")
    tmp.close()
    orig_data_file = ctm._DATA_FILE
    ctm._DATA_FILE = tmp.name
    try:
        mgr = CustomTemplateManager()
        comp = ComponentConfig(
            has_engine=True,
            engine_speed=100.0,
            has_antimatter_storage=True,
            antimatter_capacity=250.0,
        )
        template = CustomUnitTemplate(
            design_name="AM_BUILD_TEST",
            display_name="AM Build Test",
            hull_size=HullSize.MEDIUM,
            components=comp,
        )
        mgr.save_design(template)

        # Catch added unit
        created_units = []
        galaxy.systems["Sol"].add_unit = lambda u: created_units.append(u)

        constructor.create_unit_from_template(
            galaxy, "AM_BUILD_TEST", owner, "Sol", (0, 0), Position(0, 0)
        )

        assert len(created_units) == 1
        u = created_units[0]
        am_comp = u.antimatter_component
        assert am_comp is not None
        assert am_comp.max_capacity == 250.0
        assert am_comp.hull_cost == 13
    finally:
        ctm._DATA_FILE = orig_data_file
        os.unlink(tmp.name)
        # Clean up any test entries injected into the global UNIT_TEMPLATES
        for k in list(UNIT_TEMPLATES.keys()):
            if UNIT_TEMPLATES[k].get("is_custom"):
                del UNIT_TEMPLATES[k]


def test_create_unit_from_template_disabled_antimatter():
    import custom_unit_templates as ctm

    class DummyOwner:
        id = 1

    class DummySystem:
        name = "Sol"
        def add_unit(self, unit): pass

    class DummyGalaxy:
        systems = {"Sol": DummySystem()}

    class DummyUnit:
        game = None
        name = "Builder"

    builder_unit = DummyUnit()
    constructor = Constructor(builder_unit, hull_cost=15)
    galaxy = DummyGalaxy()
    owner = DummyOwner()

    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    tmp.write("{}")
    tmp.close()
    orig_data_file = ctm._DATA_FILE
    ctm._DATA_FILE = tmp.name
    try:
        mgr = CustomTemplateManager()
        comp = ComponentConfig(
            has_engine=True,
            engine_speed=100.0,
            has_antimatter_storage=False,
        )
        template = CustomUnitTemplate(
            design_name="NO_AM_TEST",
            display_name="No AM Test",
            hull_size=HullSize.MEDIUM,
            components=comp,
        )
        mgr.save_design(template)

        created_units = []
        galaxy.systems["Sol"].add_unit = lambda u: created_units.append(u)

        constructor.create_unit_from_template(
            galaxy, "NO_AM_TEST", owner, "Sol", (0, 0), Position(0, 0)
        )

        assert len(created_units) == 1
        u = created_units[0]
        assert u.antimatter_component is None
    finally:
        ctm._DATA_FILE = orig_data_file
        os.unlink(tmp.name)
        # Clean up any test entries injected into the global UNIT_TEMPLATES
        for k in list(UNIT_TEMPLATES.keys()):
            if UNIT_TEMPLATES[k].get("is_custom"):
                del UNIT_TEMPLATES[k]
