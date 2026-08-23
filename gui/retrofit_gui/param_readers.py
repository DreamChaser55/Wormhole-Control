"""
param_readers.py

Parameter input reading and parsing methods for the Retrofit Customization Options Wizard.
"""

from constants import get_min_antimatter_capacity, DEFAULT_SENSOR_SHORT_RANGE


def read_engine_params(wizard) -> None:
    """Reads engine speed from UI entry and updates config."""
    try:
        speed = float(wizard._engine_speed_entry.get_text()) if getattr(wizard, '_engine_speed_entry', None) else 100.0
        wizard._comp_config["speed"] = max(0.0, speed)
    except ValueError:
        pass


def read_antimatter_params(wizard) -> None:
    """Reads antimatter capacity from UI entry and updates config."""
    try:
        min_cap = get_min_antimatter_capacity(wizard.target_unit.hull_size) if wizard.target_unit else 10.0
        cap = float(wizard._am_capacity_entry.get_text()) if getattr(wizard, '_am_capacity_entry', None) else min_cap
        wizard._comp_config["max_capacity"] = max(min_cap, cap)
    except ValueError:
        pass


def read_hyperdrive_params(wizard) -> None:
    """Reads hyperdrive jump range from UI entry and updates config."""
    try:
        jr = int(wizard._hd_jump_range_entry.get_text()) if getattr(wizard, '_hd_jump_range_entry', None) else 5
        wizard._comp_config["jump_range"] = max(1, jr)
    except ValueError:
        pass


def read_defense_params(wizard) -> None:
    """Reads armor, shields, and point defense from UI entries and updates config."""
    try:
        wizard._comp_config["armor"] = max(0, int(wizard._armor_entry.get_text())) if getattr(wizard, '_armor_entry', None) else 0
    except ValueError:
        pass
    try:
        wizard._comp_config["shields"] = max(0, int(wizard._shields_entry.get_text())) if getattr(wizard, '_shields_entry', None) else 0
    except ValueError:
        pass
    try:
        wizard._comp_config["point_defense"] = max(0, int(wizard._pd_entry.get_text())) if getattr(wizard, '_pd_entry', None) else 0
    except ValueError:
        pass


def read_sensor_params(wizard) -> None:
    """Reads short/long range sensor values from UI entries and updates config."""
    try:
        sr = float(wizard._sensor_short_range_entry.get_text()) if getattr(wizard, '_sensor_short_range_entry', None) else DEFAULT_SENSOR_SHORT_RANGE
        wizard._comp_config["short_range_radius"] = max(0.0, sr)
    except ValueError:
        pass
    try:
        lr = int(wizard._sensor_long_range_entry.get_text()) if getattr(wizard, '_sensor_long_range_entry', None) else 1
        wizard._comp_config["long_range_hexes"] = max(0, lr)
    except ValueError:
        pass


def read_repair_params(wizard) -> None:
    """Reads repair rate and range parameters from UI entries and updates config."""
    try:
        rr = float(wizard._repair_rate_entry.get_text()) if getattr(wizard, '_repair_rate_entry', None) else 10.0
        wizard._comp_config["repair_rate"] = max(0.0, rr)
    except ValueError:
        pass
    try:
        rrange = float(wizard._repair_range_entry.get_text()) if getattr(wizard, '_repair_range_entry', None) else 200.0
        wizard._comp_config["repair_range"] = max(0.0, rrange)
    except ValueError:
        pass


def read_mining_params(wizard) -> None:
    """Reads mining rate, range, and cargo capacity from UI entries and updates config."""
    try:
        mr = float(wizard._mining_rate_entry.get_text()) if getattr(wizard, '_mining_rate_entry', None) else 10.0
        wizard._comp_config["mining_rate"] = max(0.0, mr)
    except ValueError:
        pass
    try:
        mrange = float(wizard._mining_range_entry.get_text()) if getattr(wizard, '_mining_range_entry', None) else 200.0
        wizard._comp_config["mining_range"] = max(0.0, mrange)
    except ValueError:
        pass
    try:
        mcargo = float(wizard._mining_max_cargo_entry.get_text()) if getattr(wizard, '_mining_max_cargo_entry', None) else 100.0
        wizard._comp_config["max_cargo"] = max(0.0, mcargo)
    except ValueError:
        pass


def read_hangar_params(wizard) -> None:
    """Reads hangar slots count from UI entry and updates config."""
    try:
        slots = int(wizard._hangar_slots_entry.get_text()) if getattr(wizard, '_hangar_slots_entry', None) else 2
        wizard._comp_config["max_slots"] = max(1, slots)
    except ValueError:
        pass


def read_strikecraft_bay_params(wizard) -> None:
    """Reads strikecraft bay slots count from UI entry and updates config."""
    try:
        slots = int(wizard._strikecraft_bay_slots_entry.get_text()) if getattr(wizard, '_strikecraft_bay_slots_entry', None) else 2
        wizard._comp_config["max_slots"] = max(1, slots)
    except ValueError:
        pass


def read_inhibitor_params(wizard) -> None:
    """Reads inhibitor radius from UI entry and updates config."""
    try:
        radius = float(wizard._inhibitor_radius_entry.get_text()) if getattr(wizard, '_inhibitor_radius_entry', None) else 100.0
        wizard._comp_config["radius"] = max(0.0, radius)
    except ValueError:
        pass


def read_marines_params(wizard) -> None:
    """Reads marines count from UI entry and updates config."""
    try:
        count = int(wizard._marines_count_entry.get_text()) if getattr(wizard, '_marines_count_entry', None) else 10
        wizard._comp_config["marines_count"] = max(1, count)
    except ValueError:
        pass


def read_cloaking_params(wizard) -> None:
    """Reads cloaking radius from UI entry and updates config."""
    try:
        radius = float(wizard._cloaking_radius_entry.get_text()) if getattr(wizard, '_cloaking_radius_entry', None) else 500.0
        wizard._comp_config["area_radius"] = max(0.0, radius)
    except ValueError:
        pass
