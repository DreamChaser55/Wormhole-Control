import pytest
from constants import HullSize, HYPERDRIVE_HEX_JUMP_COST, HYPERDRIVE_SYSTEM_JUMP_COST
from custom_unit_templates import (
    calc_hangar_hull_cost,
    calc_strikecraft_bay_hull_cost,
    calc_repair_hull_cost,
    calc_mining_hull_cost,
    calc_inhibitor_hull_cost,
    get_hyperdrive_system_jump_cost,
    get_hyperdrive_hex_jump_cost,
    ComponentConfig,
    CustomUnitTemplate,
)
from unit_components import Hyperdrive, HyperdriveType, AntimatterStorage


def test_hyperdrive_jump_cost_by_hull_size():
    # Medium is baseline (1.0x)
    assert get_hyperdrive_system_jump_cost(HullSize.MEDIUM) == pytest.approx(25.0)
    assert get_hyperdrive_hex_jump_cost(HullSize.MEDIUM) == pytest.approx(10.0)

    # Tiny is 0.6x
    assert get_hyperdrive_system_jump_cost(HullSize.TINY) == pytest.approx(15.0)
    assert get_hyperdrive_hex_jump_cost(HullSize.TINY) == pytest.approx(6.0)

    # Small is 0.8x
    assert get_hyperdrive_system_jump_cost(HullSize.SMALL) == pytest.approx(20.0)
    assert get_hyperdrive_hex_jump_cost(HullSize.SMALL) == pytest.approx(8.0)

    # Large is 1.5x
    assert get_hyperdrive_system_jump_cost(HullSize.LARGE) == pytest.approx(37.5)
    assert get_hyperdrive_hex_jump_cost(HullSize.LARGE) == pytest.approx(15.0)

    # Huge is 2.0x
    assert get_hyperdrive_system_jump_cost(HullSize.HUGE) == pytest.approx(50.0)
    assert get_hyperdrive_hex_jump_cost(HullSize.HUGE) == pytest.approx(20.0)


def test_calc_hangar_hull_cost():
    assert calc_hangar_hull_cost(0) == 0.0
    assert calc_hangar_hull_cost(1) == 10.0
    assert calc_hangar_hull_cost(2) == 20.0
    assert calc_hangar_hull_cost(4) == 40.0


def test_calc_strikecraft_bay_hull_cost():
    assert calc_strikecraft_bay_hull_cost(0) == 0.0
    assert calc_strikecraft_bay_hull_cost(1) == 7.5
    assert calc_strikecraft_bay_hull_cost(2) == 15.0
    assert calc_strikecraft_bay_hull_cost(4) == 30.0


def test_calc_repair_hull_cost():
    assert calc_repair_hull_cost(0) == 0.0
    assert calc_repair_hull_cost(10.0) == pytest.approx(14.9925, rel=1e-3)  # 10 / 0.667 ~ 15.0
    assert calc_repair_hull_cost(20.0) == pytest.approx(29.985, rel=1e-3)


def test_calc_mining_hull_cost():
    assert calc_mining_hull_cost(0, 0) == 0.0
    # 10 / 2.0 + 100 / 20.0 = 5.0 + 5.0 = 10.0
    assert calc_mining_hull_cost(10.0, 100.0) == 10.0
    assert calc_mining_hull_cost(20.0, 200.0) == 20.0


def test_calc_inhibitor_hull_cost():
    assert calc_inhibitor_hull_cost(0) == 0.0
    assert calc_inhibitor_hull_cost(100.0) == 20.0
    assert calc_inhibitor_hull_cost(200.0) == 40.0


def test_component_config_dynamic_properties():
    c = ComponentConfig()

    # Hangar
    c.has_hangar = True
    c.hangar_slots = 3
    assert c.hangar_hull_cost == 30.0

    # Strikecraft Bay
    c.has_strikecraft_bay = True
    c.strikecraft_bay_slots = 4
    assert c.strikecraft_bay_hull_cost == 30.0

    # Repair
    c.has_repair_component = True
    c.repair_rate = 20.0
    assert c.repair_hull_cost == pytest.approx(29.985, rel=1e-3)

    # Mining
    c.has_mining_component = True
    c.mining_rate = 20.0
    c.max_mining_cargo = 200.0
    assert c.mining_hull_cost == 20.0

    # Inhibitor
    c.has_inhibitor = True
    c.inhibitor_radius = 150.0
    assert c.inhibitor_hull_cost == 30.0


def test_custom_unit_template_total_hull_cost():
    comp = ComponentConfig(
        has_hangar=True,
        hangar_slots=3,  # 30 hull cost
        has_inhibitor=True,
        inhibitor_radius=100.0,  # 20 hull cost
    )
    tmpl = CustomUnitTemplate(
        display_name="Test Carrier",
        hull_size=HullSize.LARGE,
        components=comp,
    )
    assert tmpl.total_hull_cost == 50.0


def test_unit_editor_summary_hull_size_scaling():
    from unittest.mock import MagicMock
    from gui.unit_editor_gui import UnitEditorWindow
    gui = UnitEditorWindow.__new__(UnitEditorWindow)
    gui._comp = ComponentConfig(has_hyperdrive=True, hyperdrive_type="BASIC", hyperdrive_jump_range=5)
    gui._hull_size = HullSize.HUGE
    gui._turrets = []
    gui._selected_abilities = set()
    gui._current_hull_used = lambda: gui._comp.get_hyperdrive_hull_cost(gui._hull_size)
    gui._summary_box = MagicMock()

    UnitEditorWindow._update_summary(gui)

    gui._summary_box.set_text.assert_called_once()
    html_text = gui._summary_box.set_text.call_args[0][0]
    assert "Hyperdrive (8 hull)" in html_text
