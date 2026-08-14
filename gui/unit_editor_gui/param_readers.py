"""
param_readers.py

Parameter input parsing methods for dynamic component fields.
"""

from constants import get_min_antimatter_capacity, DEFAULT_SENSOR_SHORT_RANGE


def read_engine_params(editor) -> None:
    """Reads engine speed from UI input field and updates component configuration."""
    try:
        speed = float(editor._engine_speed_entry.get_text()) if editor._engine_speed_entry else 100.0
        editor._comp.engine_speed = max(0.0, speed)
    except ValueError:
        pass


def read_antimatter_params(editor) -> None:
    """Reads antimatter capacity from UI input field and updates component configuration."""
    try:
        min_cap = get_min_antimatter_capacity(editor._hull_size)
        cap = float(editor._am_capacity_entry.get_text()) if editor._am_capacity_entry else min_cap
        editor._comp.antimatter_capacity = max(min_cap, cap)
    except ValueError:
        pass


def read_hyperdrive_params(editor) -> None:
    """Reads hyperdrive jump range from UI input field and updates component configuration."""
    try:
        jr = int(editor._hd_jump_range_entry.get_text()) if editor._hd_jump_range_entry else 5
        editor._comp.hyperdrive_jump_range = max(1, jr)
    except ValueError:
        pass


def read_defense_params(editor) -> None:
    """Reads armor, shields, and point defense from UI input fields and updates component configuration."""
    try:
        editor._comp.armor = max(0, int(editor._armor_entry.get_text())) if editor._armor_entry else 0
    except ValueError:
        pass
    try:
        editor._comp.shields = max(0, int(editor._shields_entry.get_text())) if editor._shields_entry else 0
    except ValueError:
        pass
    try:
        editor._comp.point_defense = max(0, int(editor._pd_entry.get_text())) if editor._pd_entry else 0
    except ValueError:
        pass


def read_sensor_params(editor) -> None:
    """Reads short/long range sensor values from UI input fields and updates component configuration."""
    try:
        sr = float(editor._sensor_short_range_entry.get_text()) if getattr(editor, '_sensor_short_range_entry', None) else DEFAULT_SENSOR_SHORT_RANGE
        editor._comp.sensor_short_range = max(0.0, sr)
    except ValueError:
        pass
    try:
        lr = int(editor._sensor_long_range_entry.get_text()) if getattr(editor, '_sensor_long_range_entry', None) else 0
        editor._comp.sensor_long_range_hexes = max(0, lr)
    except ValueError:
        pass


def read_repair_params(editor) -> None:
    """Reads repair rate and range parameters from UI input fields and updates component configuration."""
    try:
        rr = float(editor._repair_rate_entry.get_text()) if getattr(editor, '_repair_rate_entry', None) else 10.0
        editor._comp.repair_rate = max(0.0, rr)
    except ValueError:
        pass
    try:
        rrange = float(editor._repair_range_entry.get_text()) if getattr(editor, '_repair_range_entry', None) else 200.0
        editor._comp.repair_range = max(0.0, rrange)
    except ValueError:
        pass


def read_mining_params(editor) -> None:
    """Reads mining rate, range, and cargo capacity from UI input fields and updates component configuration."""
    try:
        mr = float(editor._mining_rate_entry.get_text()) if getattr(editor, '_mining_rate_entry', None) else 10.0
        editor._comp.mining_rate = max(0.0, mr)
    except ValueError:
        pass
    try:
        mrange = float(editor._mining_range_entry.get_text()) if getattr(editor, '_mining_range_entry', None) else 200.0
        editor._comp.mining_range = max(0.0, mrange)
    except ValueError:
        pass
    try:
        mcargo = float(editor._mining_max_cargo_entry.get_text()) if getattr(editor, '_mining_max_cargo_entry', None) else 100.0
        editor._comp.max_mining_cargo = max(0.0, mcargo)
    except ValueError:
        pass


def read_hangar_params(editor) -> None:
    """Reads hangar slots count from UI input field and updates component configuration."""
    try:
        slots = int(editor._hangar_slots_entry.get_text()) if getattr(editor, '_hangar_slots_entry', None) else 2
        editor._comp.hangar_slots = max(1, slots)
    except ValueError:
        pass


def read_strikecraft_bay_params(editor) -> None:
    """Reads strikecraft bay slots count from UI input field and updates component configuration."""
    try:
        slots = int(editor._strikecraft_bay_slots_entry.get_text()) if getattr(editor, '_strikecraft_bay_slots_entry', None) else 2
        editor._comp.strikecraft_bay_slots = max(1, slots)
    except ValueError:
        pass


def read_inhibitor_params(editor) -> None:
    """Reads inhibitor radius from UI input field and updates component configuration."""
    try:
        radius = float(editor._inhibitor_radius_entry.get_text()) if getattr(editor, '_inhibitor_radius_entry', None) else 100.0
        editor._comp.inhibitor_radius = max(0.0, radius)
    except ValueError:
        pass


def read_marines_params(editor) -> None:
    """Reads marines count from UI input field and updates component configuration."""
    try:
        count = int(editor._marines_count_entry.get_text()) if getattr(editor, '_marines_count_entry', None) else 10
        editor._comp.marines_count = max(1, count)
    except ValueError:
        pass


def read_cloaking_params(editor) -> None:
    """Reads cloaking radius from UI input field and updates component configuration."""
    try:
        radius = float(editor._cloaking_radius_entry.get_text()) if getattr(editor, '_cloaking_radius_entry', None) else 500.0
        editor._comp.cloaking_radius = max(0.0, radius)
    except ValueError:
        pass

