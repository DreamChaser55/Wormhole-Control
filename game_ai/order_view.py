"""Explicit public serializers: never reuse persistence or raw order state."""
from __future__ import annotations

from order_history import public_reason

CONTINUOUS = {"patrol", "protect", "defend", "continuous_mine", "continuous_resupply", "continuous_trade"}
TARGET_KEYS = ("target_unit_id", "target_carrier_id", "docked_unit_id", "target_celestial_id", "target_id")


def enum_name(value):
    return str(getattr(value, "name", value)).lower() if value is not None else None


def point(value):
    if hasattr(value, "x") and hasattr(value, "y"):
        return [round(value.x, 2), round(value.y, 2)]
    return list(value) if isinstance(value, (tuple, list)) and len(value) == 2 else None


def order_layers(unit, relation, visible_ids, body_ids):
    commander = getattr(unit, "commander_component", None)
    if commander is None:
        return {"standing_order": None, "current_order": None, "queued_orders": []}
    rich = relation in {"self", "ally"}
    own = relation == "self"
    budget = [32]

    def serialize(order, origin, depth=0, redacted=False, active=False, root=True):
        if order is None:
            return None
        kind = enum_name(order.order_type)
        data = {"type": kind, "status": enum_name(order.status), "origin": origin}
        if not rich:
            return data
        actionable = enum_name(order.status) in {"pending", "in_progress"}
        params = getattr(order, "parameters", {})
        target_id = next((params[k] for k in TARGET_KEYS if params.get(k) is not None), None)
        hidden = redacted or (target_id is not None and target_id not in visible_ids and target_id not in body_ids)
        data.update(order_id=getattr(order, "public_id", None), active=active and actionable,
                    cancellable=own and origin == "explicit" and root and actionable,
                    editable=own and origin == "explicit" and root and actionable and kind == "patrol",
                    target_id=None if hidden else target_id, target_visibility="unavailable" if hidden else "visible" if target_id is not None else None,
                    failure_reason=public_reason(order.failure_reason) if getattr(order, "failure_reason", None) else None)
        if hidden:
            data["parameters"] = {}
        else:
            public = {}
            for key in ("amount", "unit_template_name", "ability_type", "minefield_type", "standoff_distance", "guard_radius"):
                value = params.get(key)
                if type(value) in (str, int, float, bool):
                    public[key] = value
            component = params.get("target_component_type")
            if component is not None:
                from unit_orders.combat import resolve_component_type
                from component_visibility import component_is_public
                resolved = resolve_component_type(component)
                if resolved and component_is_public(resolved, enemy=True):
                    public["target_component"] = resolved.__name__
            for key, output in (("destination_system_name", "system_name"), ("destination_hex_coord", "hex_coord"), ("destination_position", "position"), ("target_position", "position")):
                value = params.get(key)
                if value is not None:
                    public[output] = value if key == "destination_system_name" else point(value)
            if "waypoints" in params:
                route = params["waypoints"]
                public["waypoints"] = [{"system_name": w.get("system_name"), "hex_coord": point(w.get("hex_coord")), "position": point(w.get("position"))} for w in route[:16]]
                public["omitted_waypoints"] = max(0, len(route) - 16)
            data["parameters"] = public
        progress = {}
        if kind == "patrol":
            progress = {"leg": getattr(order, "current_waypoint_index", 0), "phase": enum_name(getattr(order, "patrol_phase", None)), "returns_to_start": True}
            if not hidden:
                progress["start_position"] = point(getattr(order, "start_position", None))
                progress["start_system_name"] = getattr(order, "start_system_name", None)
                progress["start_hex_coord"] = point(getattr(order, "start_hex_coord", None))
        elif kind in {"construct", "refit_unit"} and active:
            constructor = getattr(unit, "constructor_component", None)
            prefix = "construction" if kind == "construct" else "refit"
            if constructor and getattr(constructor, prefix + "_order_id", None) == order.public_id:
                progress = {"turns_completed": getattr(constructor, prefix + "_progress", 0),
                            "turns_required": getattr(constructor, "time_to_build" if kind == "construct" else "refit_time", 0)}
        data["progress"] = progress
        children = list(getattr(order, "sub_orders", []))
        shown = []
        if depth < 6:
            for index, child in enumerate(children):
                if budget[0] <= 0:
                    break
                budget[0] -= 1
                shown.append(serialize(child, "internal", depth + 1, hidden, active and index == 0, False))
        data["suborders"] = shown
        data["omitted_suborders"] = len(children) - len(shown)
        return data

    current = getattr(commander, "current_order", None)
    queued = list(getattr(commander, "orders_queue", []))
    standing = getattr(commander, "standing_order", None)
    suspended = current is not None or bool(queued)
    stance = getattr(getattr(commander, "stance", None), "value", None)
    current_view = serialize(current, "explicit", active=True)
    engagement = serialize(getattr(standing, "active_attack", None), "stance", active=not suspended)
    queue_views = []
    blocker = current if current and enum_name(current.order_type) in CONTINUOUS else None
    for order in queued:
        entry = serialize(order, "explicit")
        if rich:
            entry["blocked_by_order_id"] = getattr(blocker, "public_id", None)
        queue_views.append(entry)
        if blocker is None and enum_name(order.order_type) in CONTINUOUS:
            blocker = order
    return {"standing_order": {"stance": stance, "suspended": suspended, "engagement": engagement},
            "current_order": current_view, "queued_orders": queue_views}
