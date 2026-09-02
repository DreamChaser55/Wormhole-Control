"""
summary_view.py

HTML summary text box formatting and updating for the Unit Designer GUI.
"""

from constants import HULL_CAPACITIES, HIT_POINTS, HullSize
from economy import calculate_unit_upkeep
from custom_unit_templates import (
    HULL_BASE_COST,
    HULL_BASE_BUILD_TIME,
    COMPONENT_COST_PER_HULL_POINT,
)
from .catalog import COMPONENT_ROWS
from .cost_model import current_hull_used


def update_summary(editor) -> None:
    """Refresh the summary text box with current design stats."""
    if not editor._summary_box:
        return
    c = editor._comp
    capacity = HULL_CAPACITIES[editor._hull_size]
    used = current_hull_used(editor)
    over = used > capacity

    hp = HIT_POINTS[editor._hull_size]
    build_cost = HULL_BASE_COST[editor._hull_size] + int(round(used * COMPONENT_COST_PER_HULL_POINT))
    base_bt = HULL_BASE_BUILD_TIME[editor._hull_size]
    extra_bt = max(0, round((used / max(1.0, capacity)) * base_bt))
    build_time = base_bt + extra_bt
    upkeep = calculate_unit_upkeep(editor._hull_size, used)

    cap_color = "#FF4444" if over else "#88FF88"
    upkeep_str = f"{upkeep:.2f} credits/turn"
    if editor._hull_size == HullSize.STRIKECRAFT_WING:
        upkeep_str += " (Exempt)"

    lines = [
        f"<b>Hull:</b> {editor._hull_size.name}   <b>HP:</b> {hp}",
        f"<b>Hull capacity:</b> <font color='{cap_color}'>{used:g} / {capacity:g}</font>",
        f"<b>Build cost:</b> {build_cost} credits",
        f"<b>Build time:</b> {build_time} turns",
        f"<b>Predicted upkeep:</b> {upkeep_str}",
        "",
    ]


    comp_lines = []
    for row in COMPONENT_ROWS:
        key = row["key"]
        if getattr(c, key, False):
            if key == "has_engine":
                cost = c.get_engine_hull_cost(editor._hull_size)
            elif key == "has_hyperdrive":
                cost = c.get_hyperdrive_hull_cost(editor._hull_size)
            else:
                cost = getattr(c, row["cost_key"], row["default_cost"])
            cost_str = f"{cost:g}" if isinstance(cost, float) else str(cost)
            comp_lines.append(f"  • {row['label']} ({cost_str} hull)")

            # Component parameter details
            if key == "has_engine":
                comp_lines.append(f"    speed={c.engine_speed:.0f}")
            elif key == "has_antimatter_storage":
                comp_lines.append(f"    antimatter_capacity={c.antimatter_capacity:.0f}")
            elif key == "has_hyperdrive":
                comp_lines.append(f"    type={c.hyperdrive_type}  jump_range={c.hyperdrive_jump_range}")
            elif key == "has_weapon_bays":
                if editor._turrets:
                    for t in editor._turrets:
                        disp_range = t.range * 3.0 if t.variant == "LONG_RANGE" else t.range
                        disp_cooldown = t.cooldown * 3 if t.variant == "LONG_RANGE" else t.cooldown
                        comp_lines.append(f"    • {t.turret_type} ({t.variant.lower()})  dmg:{t.damage:.0f}  rng:{disp_range:.0f}  cd:{disp_cooldown}")
            elif key == "has_defenses":
                comp_lines.append(f"    armor={c.armor}  shields={c.shields}  PD={c.point_defense}")
            elif key == "has_sensors":
                comp_lines.append(f"    short_range={c.sensor_short_range:.0f}  long_range={c.sensor_long_range_hexes}")
            elif key == "has_strikecraft_bay":
                wing = getattr(c, "wing_type", "FIGHTER")
                comp_lines.append(f"    wing={wing}  slots={c.strikecraft_bay_slots}")
            elif key == "has_repair_component":
                comp_lines.append(f"    rate={c.repair_rate:.0f}  range={c.repair_range:.0f}")
            elif key == "has_mining_component":
                comp_lines.append(f"    rate={c.mining_rate:.0f}  range={c.mining_range:.0f}  cargo={c.max_mining_cargo:.0f}")
            elif key == "has_hangar":
                comp_lines.append(f"    slots={c.hangar_slots}")
            elif key == "has_inhibitor":
                comp_lines.append(f"    radius={c.inhibitor_radius:.0f}")
            elif key == "has_ability_component":
                if editor._selected_abilities:
                    for a in sorted(editor._selected_abilities):
                        comp_lines.append(f"    • {a}")
            elif key == "has_marines_component":
                comp_lines.append(f"    marines_count={c.marines_count}")
            elif key == "has_cloaking_device":
                if getattr(c, "cloaking_type", "BASIC") == "ADVANCED":
                    comp_lines.append(f"    type={c.cloaking_type}  radius={c.cloaking_radius:.0f}")
                else:
                    comp_lines.append(f"    type={c.cloaking_type}")

    if comp_lines:
        lines.append("<b>Components:</b>")
        lines.extend(comp_lines)

    editor._summary_box.set_text("<br>".join(lines))
