"""
summary_view.py

HTML summary text box formatting and updating for the Unit Designer GUI.
"""

from constants import HULL_CAPACITIES, HIT_POINTS
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

    cap_color = "#FF4444" if over else "#88FF88"
    lines = [
        f"<b>Hull:</b> {editor._hull_size.name}   <b>HP:</b> {hp}",
        f"<b>Hull capacity:</b> <font color='{cap_color}'>{used:g} / {capacity:g}</font>",
        f"<b>Build cost:</b> {build_cost} credits",
        f"<b>Build time:</b> {build_time} turns",
        "",
    ]

    comps = []
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
            comps.append(f"  • {row['label']} ({cost_str} hull)")
    if comps:
        lines.append("<b>Components:</b>")
        lines.extend(comps)

    # Engine speed detail
    if c.has_engine:
        lines.append(f"    speed={c.engine_speed:.0f}")

    # Antimatter capacity detail
    if c.has_antimatter_storage:
        lines.append(f"    antimatter_capacity={c.antimatter_capacity:.0f}")

    # Hyperdrive detail
    if c.has_hyperdrive:
        lines.append(f"    type={c.hyperdrive_type}  jump_range={c.hyperdrive_jump_range}")

    # Defenses detail
    if c.has_defenses:
        lines.append(f"    armor={c.armor}  shields={c.shields}  PD={c.point_defense}")

    # Marines detail
    if c.has_marines_component:
        lines.append(f"    marines_count={c.marines_count}")

    if editor._turrets:
        lines.append("")
        lines.append(f"<b>Turrets ({len(editor._turrets)}):</b>")
        for t in editor._turrets:
            disp_range = t.range * 3.0 if t.variant == "LONG_RANGE" else t.range
            disp_cooldown = t.cooldown * 3 if t.variant == "LONG_RANGE" else t.cooldown
            lines.append(f"  • {t.turret_type} ({t.variant.lower()})  dmg:{t.damage:.0f}  rng:{disp_range:.0f}  cd:{disp_cooldown}")

    if editor._selected_abilities:
        lines.append("")
        lines.append(f"<b>Abilities ({len(editor._selected_abilities)}):</b>")
        for a in sorted(editor._selected_abilities):
            lines.append(f"  • {a}")

    editor._summary_box.set_text("<br>".join(lines))
