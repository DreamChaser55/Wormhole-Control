"""Owner-only fuel and mineral outlook from current work and disclosed history."""
from constants import CONSTRUCTION_AM_PER_OWNER_TURN
from antimatter_logistics import storage_ready


def _fuel_need(unit, view, previous):
    if view['disabled'] or view.get('is_hidden_in_gas_giant'):
        return None
    storage = storage_ready(unit)
    current = unit.antimatter_component.current_amount if storage else 0.0
    order = view.get('current_order') or {}
    if order.get('active'):
        kind = order['type']
        progress = order.get('progress', {})
        if kind == 'construct' and progress.get('phase') in {'building', 'stalled'}:
            remaining = progress.get('turns_required', 0) - progress.get('turns_completed', 0)
            cost = CONSTRUCTION_AM_PER_OWNER_TURN
            horizon = int(current // cost)
            if horizon >= min(remaining, 3):
                return None
        else:
            journey = progress.get('journey', {})
            cost = journey.get('next_step_antimatter', 0)
            if not journey.get('waiting_reason') or cost <= 0:
                return None
            horizon = 0
    else:
        failure = previous.get('jump_fuel_failure')
        if not failure or view.get('queued_orders'):
            return None
        kind, cost = previous['type'], failure['required_antimatter']
        if current >= cost:
            return None
        horizon = 0
    return {'unit_id': unit.id, 'order_type': kind, 'current_antimatter': round(current, 2),
            'next_required_antimatter': cost, 'next_shortfall': round(max(0.0, cost - current), 2),
            'owner_turns_before_stall': horizon,
            'reason': 'storage_unavailable' if not storage else 'low_fuel' if horizon else 'insufficient_antimatter'}


def logistics_view(unit_views, history, templates, available, economy):
    latest = {event.get('unit_id'): event for event in history['events']}
    fuel_needs = []
    for unit, view in unit_views:
        if view['relation'] == 'self':
            need = _fuel_need(unit, view, latest.get(unit.id, {}))
            if need is not None:
                fuel_needs.append(need)
    fuel_needs.sort(key=lambda row: (row['owner_turns_before_stall'], row['unit_id']))
    minerals = {
        name: {'available_after_reservations': available[name],
               'passive_per_owner_turn': round(sum(colony[name] for colony in economy['income_breakdown']['colonies']), 2),
               'construction_designs_short': sum(entry['resource_shortfall'][name] > 0 for entry in templates)}
        for name in ('metal', 'crystal')
    }
    return {'fuel_needs': fuel_needs[:16], 'omitted_fuel_needs': max(0, len(fuel_needs) - 16),
            'minerals': minerals}
