"""Explicit migrations of historical saves; current-format hydration has no defaults."""
from copy import deepcopy
from types import SimpleNamespace
import uuid

CURRENT_VERSION = "4.1"


def raw_units(data):
    def visit(unit):
        yield unit
        for component in unit.get("components", {}).values():
            for child in component.get("docked_units", []):
                yield from visit(child)
    for system in data["galaxy"]["systems"]:
        for sector in system["hexes"]:
            for unit in sector.get("units", []):
                yield from visit(unit)
            for body in sector.get("celestial_bodies", []):
                for unit in body.get("hidden_units", []):
                    yield from visit(unit)


def migrate_3_0_to_3_1(data, warnings):
    for unit in raw_units(data):
        commander = unit.setdefault("commander", {})
        legacy = unit.get("orders") or commander.get("orders") or commander.get("legacy_orders", [])
        if legacy and not commander.get("current_order") and not commander.get("orders_queue"):
            commander["current_order"], *commander["orders_queue"] = legacy
        commander.setdefault("stance", "do_nothing")
        commander.setdefault("current_order", None)
        commander.setdefault("orders_queue", [])
    data["version"] = "3.1"


def migrate_3_1_to_3_2(data, warnings):
    def orders(order, path):
        if not order:
            return
        order.setdefault("public_id", uuid.uuid5(uuid.NAMESPACE_URL, path).hex)
        order.setdefault("runtime_state", {})
        order.setdefault("failure_reason", None)
        order.setdefault("outcome_recorded", False)
        order.setdefault("sub_orders", [])
        for index, child in enumerate(order["sub_orders"]):
            orders(child, f"{path}/{index}")
    for unit in raw_units(data):
        commander = unit.get("commander", {})
        for index, root in enumerate([commander.get("current_order"), *commander.get("orders_queue", [])]):
            orders(root, f"{data.get('game_state', {}).get('campaign_id', 'legacy')}/{unit.get('id')}/{index}")
    for player in data["players"]:
        player.setdefault("order_history", [])
        player.setdefault("order_event_sequence", 0)
    data["version"] = "3.2"


def migrate_3_2_to_4_0(data, warnings):
    import save_manager as sm
    from campaign_graph import iter_units
    from persistence_context import isolated_allocations
    from enum import Enum
    from unit_templates import UNIT_TEMPLATES
    # Normalize transitional 3.x Commander encodings as part of this declared migration.
    migrate_3_0_to_3_1(data, warnings)
    migrate_3_1_to_3_2(data, warnings)
    raw_by_id = {}
    for raw in raw_units(data):
        if raw.get("id") in raw_by_id:
            raise ValueError("Duplicate legacy unit ID")
        raw_by_id[raw.get("id")] = raw
        if "schema_version" in raw:
            raise ValueError("Legacy save contains a current-format unit")
        for name, fields in raw.get("components", {}).items():
            if sm.get_component_class_by_name(name) is None and name not in ("Commander", "StrikecraftWingComponent"):
                raise ValueError(f"Unknown legacy component {name}")
            if name in ("Weapons", "AbilityComponent") and not fields:
                template = UNIT_TEMPLATES.get(raw.get("template_name"), {})
                flag = "has_weapon_bays" if name == "Weapons" else "has_ability_component"
                if not template.get(flag):
                    raise ValueError(f"Legacy unit {raw.get('id')}: {name} configuration was not saved and has no matching template component")
    with isolated_allocations():
        candidate = SimpleNamespace(galaxy=None)
        players = [sm.deserialize_player(p) for p in data["players"]]
        candidate.players = players
        candidate.galaxy = sm.deserialize_galaxy(data["galaxy"], {p.id: p for p in players}, candidate)
        for player in players:
            if player.homeworld_id is None:
                player.homeworld_id = next((body.id for system in candidate.galaxy.systems.values()
                    for sector in system.hexes.values() for body in sector.celestial_bodies
                    if getattr(body, "owner", None) is player), None)
        for unit, _ in iter_units(candidate.galaxy):
            unit.in_galaxy = candidate.galaxy
            for name, old_fields in raw_by_id[unit.id].get("components", {}).items():
                cls = sm.get_component_class_by_name(name)
                component = unit.components.get(cls)
                if component is None:
                    continue
                # Keep every field that the historical writer actually supplied.
                for field in (*component.STATE_CONFIG, *component.STATE_RUNTIME, "hull_cost", "current_hit_points", "max_hit_points"):
                    if field not in old_fields or field in ("current_construction_target", "current_refit_target"):
                        continue
                    value = old_fields[field]
                    default = getattr(component, field)
                    if isinstance(default, Enum):
                        value = type(default).__members__.get(value) or type(default)(value)
                    if field == "last_traded_sector" and value is not None:
                        value = (value[0], tuple(value[1]))
                    setattr(component, field, value)
            # Preserve raw explicit orders, including charges and UUIDs. Do not resume them here.
            saved = unit._saved_commander_data
            commander = unit.commander_component
            commander.stance = saved.get("stance", "do_nothing")
            unit.damage_reduction = unit.damage_amplification = 0.0
            unit.is_disabled = False
            unit.disabled_by_unit_ids.clear()
        upgraded_galaxy = sm.serialize_galaxy(candidate.galaxy)
        # Walk both ownership trees in their stable serialized order.
        def current_units(galaxy):
            def visit(raw):
                yield raw
                for c in raw["components"].values():
                    for child in c["runtime"].get("docked_units", []):
                        yield from visit(child)
            for system in galaxy["systems"]:
                for sector in system["hexes"]:
                    for body in sector["celestial_bodies"]:
                        for unit in body.get("hidden_units", []):
                            yield from visit(unit)
                    for unit in sector["units"]:
                        yield from visit(unit)
        units_by_id = {u.id: u for u, _ in iter_units(candidate.galaxy)}
        for raw in current_units(upgraded_galaxy):
            saved = units_by_id[raw["id"]]._saved_commander_data
            raw["components"]["Commander"]["runtime"] = {
                "current_order": saved.get("current_order"), "orders_queue": saved.get("orders_queue", [])}
        data["players"] = [sm.serialize_player(p) for p in players]
        data["galaxy"] = upgraded_galaxy
    state = data["game_state"]
    for key, value in {"turn_number": 1, "current_player_index": 0, "view_mode": "galaxy",
                       "current_system_name": None, "current_sector_coord": None,
                       "object_counter": 1, "player_counter": 0, "agent_counter": 0,
                       "message_counter": 0, "campaign_id": uuid.uuid4().hex[:8]}.items():
        state.setdefault(key, value)
    data.setdefault("conversations", [])
    data["version"] = "4.0"
    warnings.append("Legacy save upgraded: omitted component state uses template/default values; orphaned timed effects were cleared because their timers were not saved.")


def migrate_4_0_to_4_1(data, warnings):
    for system in data['galaxy']['systems']:
        for sector in system['hexes']:
            sector.setdefault('deployables', [])
            sector.setdefault('catalyst_patches', [])
    data['version'] = '4.1'


MIGRATIONS = {'4.0': migrate_4_0_to_4_1, "3.0": migrate_3_0_to_3_1, "3.1": migrate_3_1_to_3_2, "3.2": migrate_3_2_to_4_0}


def migrate_save(data):
    if not isinstance(data, dict):
        raise ValueError("save: expected object")
    data = deepcopy(data)
    warnings = []
    # The pre-versioned layout is the documented 3.0 legacy layout.
    if "version" not in data:
        if not all(key in data for key in ("game_state", "players", "galaxy")):
            raise ValueError("save.version: missing version and unrecognized legacy layout")
        data["version"] = "3.0"
    while data["version"] != CURRENT_VERSION:
        migration = MIGRATIONS.get(data["version"])
        if migration is None:
            raise ValueError(f"Unsupported save version: {data['version']}")
        migration(data, warnings)
    return data, warnings
