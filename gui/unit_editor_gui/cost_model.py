"""
cost_model.py

Hull capacity calculations, dynamic component cost synchronization,
and capacity bar rendering.
"""

import math
import pygame
from gui.equipment_input import capacity_excess
from constants import HULL_CAPACITIES
from .catalog import COMPONENT_ROWS


def lerp_color(a: pygame.Color, b: pygame.Color, t: float) -> pygame.Color:
    """Linearly interpolates between two Pygame colors.

    Args:
        a (pygame.Color): Starting color at t=0.0.
        b (pygame.Color): Target color at t=1.0.
        t (float): Interpolation factor clamped between 0.0 and 1.0.

    Returns:
        pygame.Color: Resulting interpolated RGBA color.
    """
    return pygame.Color(
        int(a.r + (b.r - a.r) * t),
        int(a.g + (b.g - a.g) * t),
        int(a.b + (b.b - a.b) * t),
    )


def current_hull_used(editor) -> float:
    """Computes total hull points consumed by active/enabled components.

    Args:
        editor: UnitEditorWindow instance.

    Returns:
        float: Sum of static and dynamically computed hull costs across all active components.
    """
    return sum(component_hull_cost(editor, row) for row in COMPONENT_ROWS
               if getattr(editor._comp, row['key'], False))


def component_hull_cost(editor, row):
    """Return an individual cost, or infinity when finite input overflows."""
    try:
        if row['key'] == 'has_engine':
            value = editor._comp.get_engine_hull_cost(editor._hull_size)
        elif row['key'] == 'has_hyperdrive':
            value = editor._comp.get_hyperdrive_hull_cost(editor._hull_size)
        else:
            value = getattr(editor._comp, row['cost_key'], row['default_cost'])
        return value if math.isfinite(value) else math.inf
    except (OverflowError, ValueError):
        return math.inf


def predicted_upkeep(editor) -> float:
    """Computes predicted credit upkeep cost per turn for the current editor design.

    Args:
        editor: UnitEditorWindow instance.

    Returns:
        float: Predicted upkeep cost in credits per turn.
    """
    from economy import calculate_unit_upkeep
    return calculate_unit_upkeep(editor._hull_size, current_hull_used(editor))


def capacity_text(editor) -> str:
    """Generates formatted display string comparing current used hull capacity to total max capacity.

    Args:
        editor: UnitEditorWindow instance.

    Returns:
        str: Capacity summary text (e.g. 'Hull Capacity: 45 / 100').
    """
    capacity = HULL_CAPACITIES[editor._hull_size]
    used = current_hull_used(editor)
    if not math.isfinite(used):
        return "Hull Capacity: unavailable"
    return f"Hull Capacity: {used:g} / {capacity:g}"


def update_capacity_label(editor) -> None:
    """Updates capacity label text."""
    if editor._capacity_label:
        editor._capacity_label.set_text(capacity_text(editor))
    label = getattr(editor, '_capacity_excess_label', None)
    if label:
        used = current_hull_used(editor)
        label.set_text(capacity_excess(used, HULL_CAPACITIES[editor._hull_size])
                       if math.isfinite(used) else 'Correct values to preview')


def sync_dynamic_costs(editor) -> None:
    """Refreshes displayed hull cost labels for dynamic components and updates capacity indicators."""
    for row in COMPONENT_ROWS:
        if not row['is_dynamic']:
            continue
        computed_cost = component_hull_cost(editor, row)
        lbl = editor._comp_cost_labels.get(row['key'])
        if lbl:
            lbl.set_text(f"{computed_cost:g}" if math.isfinite(computed_cost) else 'N/A')

    update_capacity_label(editor)


def draw_capacity_bar(editor, surface: pygame.Surface) -> None:
    """Draw any custom pygame elements (capacity bar)."""
    if not editor.is_visible or not editor._cap_bar_rect:
        return
    capacity = HULL_CAPACITIES[editor._hull_size]
    used = current_hull_used(editor)
    frac = min(1.0, used / max(1, capacity)) if math.isfinite(used) else 1.0
    bar = editor._cap_bar_rect

    # Background
    pygame.draw.rect(surface, (40, 40, 50), bar, border_radius=3)

    # Fill
    fill_w = max(0, int(bar.w * frac))
    if fill_w > 0:
        ok_color = pygame.Color(50, 180, 80)
        warn_color = pygame.Color(220, 170, 30)
        over_color = pygame.Color(220, 50, 50)
        fill_color = (
            lerp_color(ok_color, warn_color, min(1.0, frac / 0.85))
            if frac <= 0.85
            else lerp_color(warn_color, over_color, (frac - 0.85) / 0.15)
        )
        fill_rect = pygame.Rect(bar.x, bar.y, fill_w, bar.h)
        pygame.draw.rect(surface, fill_color, fill_rect, border_radius=3)

    # Border
    pygame.draw.rect(surface, (100, 100, 120), bar, 1, border_radius=3)
