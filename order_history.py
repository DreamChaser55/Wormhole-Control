"""Bounded, save-authoritative explicit-order outcomes (no live target lookups)."""
import json

MAX_EVENTS = 128
MAX_CHARACTERS = 32_000
PUBLIC_REASONS = frozenset({"completed", "failed", "cancelled", "execution_failed", "suborder_failed",
    "unit_destroyed", "ownership_lost", "target_unavailable", "capability_unavailable",
    "insufficient_resources", "insufficient_population", "insufficient_capacity", "invalid_parameters",
    "path_unavailable", "construction_unavailable", "refit_unavailable", "ability_unavailable"})


def public_reason(reason, fallback="execution_failed"):
    return reason if isinstance(reason, str) and reason in PUBLIC_REASONS else fallback



def bounded_history(events):
    allowed = {"event_id", "turn", "player_id", "unit_id", "order_id", "type", "outcome", "reason"}
    cleaned = []
    for event in events if isinstance(events, list) else []:
        if not isinstance(event, dict) or type(event.get("event_id")) is not int:
            continue
        item = {key: value for key, value in event.items() if key in allowed and type(value) in (str, int)}
        for key, value in list(item.items()):
            if isinstance(value, str):
                item[key] = value[:200]
        if "reason" in item:
            item["reason"] = public_reason(item["reason"])
        cleaned.append(item)
    cleaned = sorted(cleaned, key=lambda e: e["event_id"])[-MAX_EVENTS:]
    while cleaned and len(json.dumps(cleaned, ensure_ascii=False)) > MAX_CHARACTERS:
        cleaned.pop(0)
    return cleaned


def record_outcome(order, outcome=None, reason=None):
    if not getattr(order, "_journal_root", False) or getattr(order, "_outcome_recorded", False):
        return
    owner = getattr(order, "_issuing_player", None)
    if owner is None:
        return
    outcome = outcome or order.status.name.lower()
    if outcome not in {"completed", "failed", "cancelled"}:
        return
    order._outcome_recorded = True
    sequence = getattr(owner, "order_event_sequence", 0)
    sequence = (sequence if type(sequence) is int else 0) + 1
    owner.order_event_sequence = sequence
    event = {"event_id": sequence, "turn": int(getattr(getattr(order.unit, "game", None), "turn_number", 1)),
             "player_id": owner.id, "unit_id": order.unit.id, "order_id": order.public_id,
             "type": order.order_type.name.lower(), "outcome": outcome,
             "reason": public_reason(reason or getattr(order, "failure_reason", None) or outcome)}
    owner.order_history = bounded_history([*getattr(owner, "order_history", []), event])


def interrupt_unit_orders(unit, reason):
    commander = getattr(unit, "commander_component", None)
    if commander:
        for root in [commander.current_order, *commander.orders_queue]:
            if root is not None:
                record_outcome(root, "cancelled", reason)


def history_view(player):
    events = bounded_history(getattr(player, "order_history", []))
    sequence = getattr(player, "order_event_sequence", 0)
    return {"events": events, "latest_event_id": sequence,
            "oldest_event_id": events[0]["event_id"] if events else None,
            "omitted_count": max(0, sequence - len(events)),
            "max_events": MAX_EVENTS, "max_serialized_characters": MAX_CHARACTERS}
