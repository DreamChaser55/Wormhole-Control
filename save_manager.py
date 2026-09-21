"""
save_manager.py

Handles saving and loading of game states and galaxy maps for Wormhole-Control.
Provides JSON serialization and deserialization for Players, Galaxy, StarSystems,
Hex grids, CelestialBodies, Units, UnitComponents, and Orders.
"""

from order_history import bounded_history

import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from enum import Enum

from utils import generate_short_id
from player_controller import PlayerController

from geometry import Position, Vector
from game_ai.runtime import (
    DEFAULT_REASONING_EFFORT,
    DEFAULT_REPAIR_RETRIES,
    normalize_reasoning_effort,
    normalize_repair_retries,
)
from constants import (
    HullSize, StarType, PlanetType, NebulaType, StormType, FieldDensity
)
from domain.players import Player
from domain.identity import GameObject
from domain.celestials import CelestialBody, Star, Planet, Moon, ColonizableAsteroid, MetalAsteroid, AsteroidField, IceField, DebrisField, Nebula, Storm, Comet, Wormhole
from domain.units import Unit
from domain.minefields import Minefield
from domain.communications import Conversation, Message
from galaxy import Galaxy, StarSystem, Hex
from unit_components.enums import UnitStance
from unit_orders.base import Order, OrderStatus, OrderType
from unit_orders.registry import ORDER_CLASS_REGISTRY

logger = logging.getLogger(__name__)


CURRENT_SAVE_VERSION = "4.15"

SAVES_DIR = os.path.join(os.path.dirname(__file__), "saves")

# Map of CelestialBody class names for deserialization
CELESTIAL_CLASSES = {
    "Star": Star,
    "Planet": Planet,
    "Moon": Moon,
    "ColonizableAsteroid": ColonizableAsteroid,
    "MetalAsteroid": MetalAsteroid,
    "AsteroidField": AsteroidField,
    "IceField": IceField,
    "DebrisField": DebrisField,
    "Nebula": Nebula,
    "Storm": Storm,
    "Comet": Comet,
    "Wormhole": Wormhole,
}

ORDER_CLASSES = {order_type.name: order_cls for order_type, order_cls in ORDER_CLASS_REGISTRY.items()}


def _ensure_saves_dir():
    if not os.path.exists(SAVES_DIR):
        os.makedirs(SAVES_DIR)


# --- Serialization Functions ---

def serialize_player(player: Player) -> dict:
    sector_intel_data = {
        f"{sys}:{q}:{r}": turn
        for (sys, (q, r)), turn in getattr(player, 'sector_intel', {}).items()
    }
    return {
        "id": player.id,
        "name": player.name,
        "color": list(player.color),
        "controller": player.controller.value,
        "team_id": getattr(player, "team_id", player.id + 1),
        "persistent_id": getattr(player, "persistent_id", None) or generate_short_id(),
        "agent_id": getattr(player, "agent_id", None) or generate_short_id(),
        "ai_reasoning_effort": normalize_reasoning_effort(
            getattr(player, "ai_reasoning_effort", DEFAULT_REASONING_EFFORT)
        ),
        "ai_repair_retries": normalize_repair_retries(
            getattr(player, "ai_repair_retries", DEFAULT_REPAIR_RETRIES)
        ),
        "ai_memory": getattr(player, "ai_memory", {}),
        "order_history": bounded_history(getattr(player, "order_history", [])),
        "order_event_sequence": getattr(player, "order_event_sequence", 0),
        "briefing": player.briefing.to_dict(),
        "credits": player.credits,
        "metal": player.metal,
        "crystal": player.crystal,
        "sector_intel": sector_intel_data,
        "homeworld_id": getattr(player, "homeworld_id", None),
    }


def serialize_celestial_body(body: CelestialBody) -> dict:
    data = {
        "class_name": body.__class__.__name__,
        "id": body.id,
        "name": getattr(body, "name", ""),
        "position": [body.position.x, body.position.y],
        "in_hex": list(body.in_hex),
        "in_system": body.in_system,
        "inhibition_field_radius": getattr(body, "inhibition_field_radius", 0.0),
    }

    if isinstance(body, Star):
        data["star_type"] = body.star_type.name
    elif isinstance(body, Planet):
        data["planet_type"] = body.planet_type.name
        data["owner_id"] = body.owner.id if body.owner else None
        data["population"] = body.population
        data["max_population"] = body.max_population
        data["population_growth_rate"] = body.population_growth_rate
        if body.planet_type == PlanetType.GAS_GIANT and getattr(body, 'hidden_units', None):
            data["hidden_units"] = [serialize_unit(u) for u in body.hidden_units]
    elif isinstance(body, Moon) or isinstance(body, ColonizableAsteroid):
        data["owner_id"] = body.owner.id if body.owner else None
        data["population"] = body.population
        data["max_population"] = body.max_population
        data["population_growth_rate"] = body.population_growth_rate
    elif isinstance(body, MetalAsteroid):
        data["metal_yield"] = body.metal_yield
    elif isinstance(body, Comet):
        data["crystal_yield"] = body.crystal_yield
    elif isinstance(body, (AsteroidField, DebrisField, IceField)):
        if hasattr(body, 'density') and body.density is not None:
            data["density"] = body.density.name
        if isinstance(body, AsteroidField):
            data["asteroid_count"] = body.asteroid_count
    elif isinstance(body, Nebula):
        data["nebula_type"] = body.nebula_type.name
    elif isinstance(body, Storm):
        data["storm_type"] = body.storm_type.name
    elif isinstance(body, Wormhole):
        data["exit_system_name"] = body.exit_system_name
        data["exit_wormhole_id"] = body.exit_wormhole_id
        data["stability"] = body.stability
        data["diameter"] = body.diameter.name

    if isinstance(body, (Planet, Moon, ColonizableAsteroid)):
        from planetary_warfare import BODY_FIELDS
        data.update({field: getattr(body, field) for field in BODY_FIELDS})
    data["infiltrating_agents"] = [a.to_dict() for a in getattr(body, 'infiltrating_agents', [])]
    return data


def _encode_order_value(value: Any) -> Any:
    """Recursively encode order parameters without losing container types."""
    if isinstance(value, Vector):
        return {"__type__": "position", "x": value.x, "y": value.y}
    if isinstance(value, Enum):
        return {"__type__": "enum", "enum": value.__class__.__name__, "value": value.value}
    if isinstance(value, type):
        return {"__type__": "class", "name": value.__name__}
    if isinstance(value, tuple):
        return {"__type__": "tuple", "items": [_encode_order_value(item) for item in value]}
    if isinstance(value, list):
        return [_encode_order_value(item) for item in value]
    if isinstance(value, dict):
        if all(isinstance(key, str) for key in value):
            return {key: _encode_order_value(item) for key, item in value.items()}
        return {
            "__type__": "dict",
            "items": [
                [_encode_order_value(key), _encode_order_value(item)]
                for key, item in value.items()
            ],
        }
    if isinstance(value, set):
        return {"__type__": "set", "items": [_encode_order_value(item) for item in value]}
    return value


def _decode_known_enum(enum_name: str, value: Any) -> Any:
    import constants as constants_module
    import unit_components.enums as component_enums
    import unit_orders.base as order_enums
    import player_controller as controller_enums
    for module in (constants_module, component_enums, order_enums, controller_enums):
        enum_cls = getattr(module, enum_name, None)
        if isinstance(enum_cls, type) and issubclass(enum_cls, Enum):
            try:
                return enum_cls(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid {enum_name} value: {value!r}") from exc
    raise ValueError(f"Unknown enum: {enum_name}")


def _decode_order_value(value: Any) -> Any:
    """Decode explicitly tagged order values."""
    if isinstance(value, dict):
        type_tag = value.get("__type__")
        if type_tag == "position":
            return Position(value["x"], value["y"])
        if type_tag == "enum":
            return _decode_known_enum(value["enum"], value["value"])
        if type_tag == "class":
            return value["name"]
        if type_tag == "tuple":
            return tuple(_decode_order_value(item) for item in value["items"])
        if type_tag == "set":
            return set(_decode_order_value(item) for item in value["items"])
        if type_tag == "dict":
            return {
                _decode_order_value(pair[0]): _decode_order_value(pair[1])
                for pair in value["items"]
            }
        if type_tag is not None:
            raise ValueError(f"Unknown order value tag: {type_tag}")
        return {key: _decode_order_value(item) for key, item in value.items()}
    if isinstance(value, list):
        decoded = [_decode_order_value(item) for item in value]
        return decoded
    return value


def serialize_order(order: Order) -> dict:
    params = _encode_order_value(getattr(order, "parameters", {}))

    order_type_str = order.order_type.name if hasattr(order, "order_type") and order.order_type else "UNKNOWN"
    status_str = order.status.name if hasattr(order, "status") and order.status else "PENDING"

    # A standing stance is a persistent policy; its Attack/Move descendants
    # are transient and must be reacquired after loading rather than persisted.
    sub_orders = (
        []
        if order_type_str == OrderType.STANCE.name
        else [serialize_order(so) for so in getattr(order, "sub_orders", [])]
    )

    return {
        "public_id": order.public_id,
        "failure_reason": order.failure_reason,
        "outcome_recorded": order._outcome_recorded,
        "order_type": order_type_str,
        "status": status_str,
        "parameters": params,
        "runtime_state": _encode_order_value(order.get_persistence_state()),
        "sub_orders": sub_orders
    }


def serialize_components(unit: Unit) -> dict:
    from unit_components.persistence import component_registry
    registry = component_registry()
    result = {}
    for cls, component in unit.components.items():
        if registry.get(cls.__name__) is not cls:
            raise ValueError(f"Unregistered component {cls.__name__}")
        result[cls.__name__] = component.to_state()
    return result


def serialize_unit(unit: Unit) -> dict:
    return {
        "schema_version": 3,
        "id": unit.id,
        "name": unit.name,
        "owner_id": unit.owner.id if unit.owner else None,
        "hull_size": unit.hull_size.name,
        "template_name": unit.template_name,
        "in_system": unit.in_system,
        "in_hex": list(unit.in_hex) if unit.in_hex else None,
        "position": [unit.position.x, unit.position.y] if unit.position else [0.0, 0.0],
        "current_hit_points": unit.current_hit_points,
        "max_hit_points": unit.max_hit_points,
        "experience_points": unit.experience_points,
        "is_disabled": unit.is_disabled,
        "disabled_by_unit_ids": list(unit.disabled_by_unit_ids),
        "last_planetary_action_round": unit.last_planetary_action_round,
        "multiply_cast_ready_round": unit.multiply_cast_ready_round,
        "multiply_receive_ready_round": unit.multiply_receive_ready_round,
        "damage_reduction": unit.damage_reduction,
        "damage_amplification": unit.damage_amplification,
        "lifetime": unit.lifetime,
        "is_temporary": unit.is_temporary,
        "infiltrating_agents": [a.to_dict() for a in getattr(unit, 'infiltrating_agents', [])],
        "components": serialize_components(unit),
    }


def serialize_minefield(minefield: Minefield) -> dict:
    return {
        "id": minefield.id,
        "name": minefield.name,
        "owner_id": minefield.owner.id if minefield.owner else None,
        "in_hex": list(minefield.in_hex),
        "in_system": minefield.in_system,
        "position": [minefield.position.x, minefield.position.y],
        "mines_remaining": minefield.mines_remaining,
        "mine_damage": minefield.mine_damage,
        "detonation_radius": minefield.detonation_radius,
        "minefield_type": minefield.minefield_type.value,
        "revealed_to_player_ids": list(getattr(minefield, "revealed_to_player_ids", set())),
    }


def serialize_hex(hex_obj: Hex) -> dict:
    from tactical_persistence import serialize as serialize_tactical
    return {
        "deployables": [serialize_tactical(d) for d in hex_obj.deployables],
        "catalyst_patches": [serialize_tactical(p) for p in hex_obj.catalyst_patches],
        "q": hex_obj.q,
        "r": hex_obj.r,
        "in_system": hex_obj.in_system,
        "celestial_bodies": [serialize_celestial_body(b) for b in hex_obj.celestial_bodies],
        "units": [serialize_unit(u) for u in hex_obj.units],
        "minefields": [serialize_minefield(mf) for mf in getattr(hex_obj, "minefields", [])]
    }


def serialize_star_system(system: StarSystem) -> dict:
    hexes_list = [serialize_hex(h) for h in system.hexes.values()]
    return {
        "name": system.name,
        "position": [system.position.x, system.position.y],
        "radius": system.radius,
        "hexes": hexes_list
    }


def serialize_galaxy(galaxy: Galaxy) -> dict:
    systems_data = [serialize_star_system(sys) for sys in galaxy.systems.values()]
    return {
        "generation_bounds": {
            "x_min": galaxy.generation_x_min,
            "x_max": galaxy.generation_x_max,
            "y_min": galaxy.generation_y_min,
            "y_max": galaxy.generation_y_max,
        },
        "systems": systems_data
    }


def serialize_game_state(game: Any) -> dict:
    """Serializes the entire Game instance into a JSON-compatible dictionary."""
    from unit_components.intelligence import Agent
    from planetary_warfare import invasion_rng
    from state_codec import encode
    object_counter = GameObject.object_counter
    player_counter = Player.player_counter

    players_data = [serialize_player(p) for p in game.players]
    galaxy_data = serialize_galaxy(game.galaxy) if game.galaxy else None
    conversations_data = [
        conv.to_dict() for conv in getattr(game, "conversations", {}).values()
    ]

    return {
        "version": CURRENT_SAVE_VERSION,
        "timestamp": datetime.now().isoformat(),
        "game_state": {
            "invasion_rng_state": encode(invasion_rng(game).getstate()),
            "turn_number": game.turn_number,
            "current_player_index": game.current_player_index,
            "view_mode": game.view_mode,
            "current_system_name": game.current_system_name,
            "current_sector_coord": list(game.current_sector_coord) if game.current_sector_coord else None,
            "object_counter": object_counter,
            "player_counter": player_counter,
            "agent_counter": Agent.agent_counter,
            "message_counter": getattr(game, "message_counter", 0),
            "campaign_id": getattr(game, "campaign_id", None) or generate_short_id(),
        },
        "players": players_data,
        "galaxy": galaxy_data,
        "conversations": conversations_data,
    }


# --- Deserialization Functions ---

def deserialize_player(data: dict) -> Player:
    ai_reasoning_effort = normalize_reasoning_effort(
        data['ai_reasoning_effort']
    )
    player = Player(
        name=data['name'],
        color=tuple(data['color']),
        controller=PlayerController(data["controller"]),
        team_id=data['team_id'],
        persistent_id=data['persistent_id'],
        agent_id=data['agent_id'],
        ai_reasoning_effort=ai_reasoning_effort,
        ai_repair_retries=normalize_repair_retries(
            data['ai_repair_retries']
        ),
        ai_memory=data['ai_memory'],
        homeworld_id=data['homeworld_id'],
    )
    player.order_history = bounded_history(data['order_history'])
    player.order_event_sequence = max(int(data['order_event_sequence']), max((e["event_id"] for e in player.order_history), default=0))
    player.id = data['id']
    from turn_briefing import state_from_dict
    player.briefing = state_from_dict(data['briefing'])
    if "team_id" in data:
        player.team_id = data["team_id"]
    player.credits = data['credits']
    player.metal = data['metal']
    player.crystal = data['crystal']

    raw_intel = data['sector_intel']
    if isinstance(raw_intel, dict):
        for key_str, turn in raw_intel.items():
            parts = key_str.split(":")
            if len(parts) == 3:
                sys_name, q_str, r_str = parts
                try:
                    player.sector_intel[(sys_name, (int(q_str), int(r_str)))] = int(turn)
                except ValueError:
                    pass
    return player


def deserialize_celestial_body(data: dict, players_by_id: Dict[int, Player], game: Any = None) -> CelestialBody:
    class_name = data['class_name']
    cls = CELESTIAL_CLASSES.get(class_name)
    if not cls:
        raise ValueError(f"Unknown CelestialBody class_name: {class_name}")

    in_hex = tuple(data['in_hex'])
    in_system = data['in_system']
    position = Position(data["position"][0], data["position"][1])

    if cls == Star:
        star_type = StarType[data['star_type']]
        body = Star(in_system=in_system, star_type=star_type)
    elif cls == Planet:
        planet_type = PlanetType[data['planet_type']]
        body = Planet(in_hex=in_hex, in_system=in_system, planet_type=planet_type)
        owner_id = data['owner_id']
        body.owner = players_by_id.get(owner_id) if owner_id is not None else None
        body.population = data['population']
        body.max_population = data['max_population']
        body.population_growth_rate = data['population_growth_rate']
    elif cls in (Moon, ColonizableAsteroid):
        body = cls(in_hex=in_hex, in_system=in_system)
        owner_id = data['owner_id']
        body.owner = players_by_id.get(owner_id) if owner_id is not None else None
        body.population = data['population']
        body.max_population = data['max_population']
        body.population_growth_rate = data['population_growth_rate']
    elif cls == MetalAsteroid:
        body = MetalAsteroid(in_hex=in_hex, in_system=in_system)
        body.metal_yield = data['metal_yield']
    elif cls == Comet:
        body = Comet(in_hex=in_hex, in_system=in_system)
        body.crystal_yield = data['crystal_yield']
    elif cls in (AsteroidField, DebrisField, IceField):
        density = FieldDensity[data['density']]
        body = cls(in_hex=in_hex, in_system=in_system, density=density)
        if cls == AsteroidField:
            body.asteroid_count = data['asteroid_count']
    elif cls == Nebula:
        nebula_type = NebulaType[data['nebula_type']]
        body = Nebula(in_hex=in_hex, in_system=in_system, nebula_type=nebula_type)
    elif cls == Storm:
        storm_type = StormType[data['storm_type']]
        body = Storm(in_hex=in_hex, in_system=in_system, storm_type=storm_type)
    elif cls == Wormhole:
        diameter = HullSize[data['diameter']]
        exit_sys = data['exit_system_name']
        stability = data['stability']
        body = Wormhole(in_hex=in_hex, in_system=in_system, exit_system_name=exit_sys, stability=stability, diameter=diameter)
        body.exit_wormhole_id = data['exit_wormhole_id']
    else:
        body = cls(in_hex=in_hex, in_system=in_system)

    if isinstance(body, (Planet, Moon, ColonizableAsteroid)):
        from planetary_warfare import BODY_FIELDS
        for field in BODY_FIELDS:
            setattr(body, field, data[field])
    body.id = data['id']
    body.position = position
    if "name" in data and data["name"]:
        body.name = data["name"]
    if cls in (AsteroidField, DebrisField, IceField):
        body.inhibition_field_radius = 0.0
    elif "inhibition_field_radius" in data:
        body.inhibition_field_radius = data["inhibition_field_radius"]

    if "infiltrating_agents" in data:
        from unit_components.intelligence import Agent
        body.infiltrating_agents = [Agent.from_dict(ad, players_by_id, body) for ad in data["infiltrating_agents"]]

    if "hidden_units" in data and game is not None:
        body.hidden_units = [deserialize_unit(ud, players_by_id, game) for ud in data["hidden_units"]]
        for u in body.hidden_units:
            u.is_hidden_in_gas_giant = True
            u.hidden_in_gas_giant_id = body.id

    return body


def deserialize_order(data: dict, unit: Unit, game: Any) -> Order:
    order_type_str = data['order_type']
    order_cls = ORDER_CLASSES.get(order_type_str)
    if not order_cls:
        raise ValueError(f"Unknown order type: {order_type_str}")

    params = _decode_order_value(data['parameters'])
    if not isinstance(params, dict):
        raise ValueError(f"Invalid parameters for order type {order_type_str}")

    from location_validation import order_locations
    params = order_locations(order_type_str, params, getattr(game, "galaxy", None))
    if order_type_str == "CONSTRUCT":
        from construction_customization import validate_override_values, OVERRIDE_FIELDS
        if any(field not in params for field in OVERRIDE_FIELDS):
            raise ValueError("Missing construction overrides")
        validate_override_values(*(params[field] for field in OVERRIDE_FIELDS))
    order = order_cls(unit=unit, parameters=params)
    import uuid
    order.public_id = uuid.UUID(data["public_id"]).hex
    order.failure_reason = data['failure_reason']
    order._outcome_recorded = bool(data['outcome_recorded'])
    order.status = OrderStatus[data['status']]
    runtime_state = _decode_order_value(data['runtime_state'])
    from state_codec import fields
    fields(runtime_state, order.get_persistence_state().keys(), "order.runtime_state")
    order.restore_persistence_state(runtime_state)

    if order_type_str == OrderType.STANCE.name and data["sub_orders"]:
        raise ValueError("Standing-order descendants must not be persisted")
    serialized_sub_orders = data["sub_orders"]
    for sub_data in serialized_sub_orders:
        sub_order = deserialize_order(sub_data, unit, game)
        if sub_order:
            sub_order.parent_order = order
            order.sub_orders.append(sub_order)

    return order


def _iter_unit_tree(root: Unit):
    """Yield a deployed or docked unit and every recursively docked child."""
    yield root
    for component in (root.hangar_component, root.strikecraft_bay_component):
        if component:
            for docked in component.docked_units:
                yield from _iter_unit_tree(docked)


def _restore_saved_commander(unit: Unit, game: Any) -> None:
    if not hasattr(unit, "_saved_commander_data"):
        return
    data = unit._saved_commander_data
    commander = unit.commander_component
    commander.set_stance(UnitStance(data["stance"]))
    current = deserialize_order(data["current_order"], unit, game) if data["current_order"] is not None else None
    queued = [deserialize_order(raw, unit, game) for raw in data["orders_queue"]]
    commander.restore_explicit_orders(current, queued, game.galaxy)
    del unit._saved_commander_data


def deserialize_unit(data: dict, players_by_id: Dict[int, Player], game: Any) -> Unit:
    from unit_components.persistence import restore_component
    if type(data["schema_version"]) is not int or data["schema_version"] != 3:
        raise ValueError("Unsupported unit schema")
    owner = players_by_id.get(data["owner_id"])
    if data["owner_id"] is not None and owner is None:
        raise ValueError(f"unit {data['id']}: unknown owner")
    unit = Unit(owner, Position(*data["position"]), tuple(data["in_hex"]), data["in_system"],
                data["name"], HullSize[data["hull_size"]], game, data['template_name'])
    unit.id = data["id"]
    for name in ("current_hit_points", "max_hit_points", "experience_points", "is_disabled",
                 "damage_reduction", "damage_amplification", "lifetime", "is_temporary",
                 "multiply_cast_ready_round", "multiply_receive_ready_round", "last_planetary_action_round"):
        setattr(unit, name, data[name])
    unit.disabled_by_unit_ids = set(data["disabled_by_unit_ids"])
    # A new shell has no installed equipment to decommission.
    unit.components.clear()
    for name, state in data["components"].items():
        if name != state.get("type"):
            raise ValueError(f"unit {unit.id}: component key/type mismatch")
        try:
            component = restore_component(state, unit, players_by_id, game)
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(f"unit {unit.id}.components.{name}: {exc}") from exc
        unit.add_component(component)
    if not unit.commander_component:
        raise ValueError(f"unit {unit.id}: missing Commander")
    from unit_components.intelligence import Agent
    unit.infiltrating_agents = [Agent.from_dict(a, players_by_id, unit) for a in data["infiltrating_agents"]]
    return unit


def deserialize_minefield(data: dict, players_by_id: Dict[int, Player]) -> Minefield:
    owner_id = data['owner_id']
    owner = players_by_id[owner_id] if owner_id is not None else None
    in_hex = tuple(data['in_hex'])
    in_system = data['in_system']
    position = Position(data["position"][0], data["position"][1])
    minefield_type = data['minefield_type']

    minefield = Minefield(
        owner=owner,
        position=position,
        in_hex=in_hex,
        in_system=in_system,
        mines_remaining=data['mines_remaining'],
        mine_damage=data['mine_damage'],
        detonation_radius=data['detonation_radius'],
        minefield_type=minefield_type
    )
    minefield.id = data['id']
    minefield.name = data['name']
    minefield.revealed_to_player_ids = set(data['revealed_to_player_ids'])
    return minefield


def deserialize_hex(data: dict, players_by_id: Dict[int, Player], game: Any) -> Hex:
    q = data["q"]
    r = data["r"]
    in_system = data["in_system"]
    hex_obj = Hex(q, r, in_system=in_system)

    for cb_data in data['celestial_bodies']:
        body = deserialize_celestial_body(cb_data, players_by_id, game)
        hex_obj.add_celestial_body(body)

    for unit_data in data['units']:
        unit = deserialize_unit(unit_data, players_by_id, game)
        hex_obj.add_unit(unit)

    for mf_data in data['minefields']:
        mf = deserialize_minefield(mf_data, players_by_id)
        if not hex_obj.add_minefield(mf):
            raise ValueError("Too many minefields in sector")

    from tactical_persistence import deserialize as deserialize_tactical
    hex_obj.deployables = [deserialize_tactical(d, players_by_id) for d in data['deployables']]
    hex_obj.catalyst_patches = [deserialize_tactical(p, players_by_id, patch=True) for p in data['catalyst_patches']]
    return hex_obj


def deserialize_star_system(data: dict, players_by_id: Dict[int, Player], game: Any) -> StarSystem:
    name = data["name"]
    position = Vector(data["position"][0], data["position"][1])
    radius = data["radius"]

    system = StarSystem.__new__(StarSystem)
    system.name = name
    system.position = position
    system.radius = radius
    system.hexes = {}
    system.celestial_bodies_by_id = {}

    for hex_data in data['hexes']:
        hex_obj = deserialize_hex(hex_data, players_by_id, game)
        if (hex_obj.q, hex_obj.r) in system.hexes:
            raise ValueError("Duplicate sector coordinates")
        system.hexes[(hex_obj.q, hex_obj.r)] = hex_obj
        for body in hex_obj.celestial_bodies:
            system.celestial_bodies_by_id[body.id] = body

    for hex_obj in system.hexes.values():
        hex_obj.update_static_inhibition_zones()

    return system


def deserialize_galaxy(data: dict, players_by_id: Dict[int, Player], game: Any) -> Galaxy:
    galaxy = Galaxy.__new__(Galaxy)
    galaxy.systems = {}
    galaxy.wormholes = {}
    galaxy.system_graph = {}

    bounds = data['generation_bounds']
    galaxy.generation_x_min = bounds['x_min']
    galaxy.generation_x_max = bounds['x_max']
    galaxy.generation_y_min = bounds['y_min']
    galaxy.generation_y_max = bounds['y_max']

    for sys_data in data['systems']:
        sys_obj = deserialize_star_system(sys_data, players_by_id, game)
        sys_obj.in_galaxy = galaxy
        if sys_obj.name in galaxy.systems:
            raise ValueError(f"Duplicate system {sys_obj.name}")
        galaxy.systems[sys_obj.name] = sys_obj

        # Collect wormholes
        for hex_obj in sys_obj.hexes.values():
            for body in hex_obj.celestial_bodies:
                if isinstance(body, Wormhole):
                    galaxy.wormholes[body.id] = body

    galaxy._build_system_graph()
    return galaxy


def deserialize_game_state(game: Any, data: dict, *, on_error=None) -> bool:
    """Prepare in isolation; an invalid save never changes the running campaign."""
    from campaign_persistence import prepare_campaign, commit_campaign
    try:
        prepared = prepare_campaign(data)
    except Exception as exc:
        logger.error("Failed to prepare save: %s", exc, exc_info=True)
        if on_error is not None:
            on_error(str(exc))
        return False
    commit_campaign(game, prepared)
    return True


def save_game_to_file(game: Any, filename: Optional[str] = None) -> str:
    """Saves the current game state to a JSON file in the saves directory."""
    _ensure_saves_dir()

    if not filename:
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        sys_name = game.current_system_name or "Galaxy"
        filename = f"save_turn_{game.turn_number}_{sys_name}_{timestamp_str}.json"

    if not filename.endswith(".json"):
        filename += ".json"

    filepath = os.path.join(SAVES_DIR, filename)

    state_dict = serialize_game_state(game)
    temporary_path = filepath + ".tmp"
    with open(temporary_path, "w", encoding="utf-8") as f:
        json.dump(state_dict, f, indent=2, allow_nan=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary_path, filepath)

    try:
        from pathlib import Path
        from game_ai.memory import AgentMemory, write_memory_sidecar

        for player in game.players:
            if player.controller == PlayerController.OPENAI:
                write_memory_sidecar(
                    Path(SAVES_DIR),
                    campaign_id=str(game.campaign_id),
                    agent_id=str(player.agent_id),
                    player_name=str(player.name),
                    memory=AgentMemory.from_dict(getattr(player, "ai_memory", None)),
                )

        # Write campaign communications sidecar
        conv_list = list(getattr(game, "conversations", {}).values())
        write_comms_sidecar(
            Path(SAVES_DIR),
            campaign_id=str(getattr(game, "campaign_id", "unknown")),
            conversations=conv_list,
            players=getattr(game, "players", []),
        )
    except Exception:
        logger.warning("Could not write sidecars.", exc_info=True)

    logger.debug(f"Game saved successfully to {filepath}")
    return filepath


def write_comms_sidecar(
    root: Any,
    *,
    campaign_id: str,
    conversations: List[Conversation],
    players: List[Player],
) -> Any:
    """Atomically write the campaign comms.md sidecar below the save directory."""
    from pathlib import Path
    root_path = Path(root)
    target_dir = root_path / "comms" / campaign_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "comms.md"
    temporary = target.with_suffix(".md.tmp")

    players_by_id = {p.id: p for p in players}
    all_messages: List[Message] = []
    for conv in conversations:
        all_messages.extend(conv.messages)
    all_messages.sort(key=lambda m: (m.turn_sent, m.id))

    lines = [
        "# Inter-Player Communications Log",
        "",
        "> Canonical log of in-game transmissions between players.",
        "",
        f"- **Campaign**: `{campaign_id}`",
        f"- **Generated**: `{datetime.now(timezone.utc).isoformat()}`",
        f"- **Total Transmissions**: {len(all_messages)}",
        "",
        "---",
        "",
    ]

    if not all_messages:
        lines.append("*No in-game transmissions recorded.*")
    else:
        current_turn = None
        for msg in all_messages:
            if current_turn != msg.turn_sent:
                current_turn = msg.turn_sent
                lines.extend([f"## Turn {current_turn}", ""])
            sender = players_by_id.get(msg.sender_id)
            recipient = players_by_id.get(msg.recipient_id)
            lines.append(msg.to_markdown(sender, recipient))
            lines.append("")

    temporary.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    temporary.replace(target)
    return target


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def load_game_from_file(game: Any, filepath: str, *, on_error=None) -> bool:
    """Loads a game state from a JSON file into the game instance."""
    if not os.path.isabs(filepath):
        filepath = os.path.join(SAVES_DIR, filepath)

    if not os.path.exists(filepath):
        logger.error(f"Save file not found: {filepath}")
        if on_error is not None:
            on_error("Save file not found")
        return False

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f, object_pairs_hook=_unique_json_object)

        return deserialize_game_state(game, data, on_error=on_error)
    except Exception as e:
        logger.error(f"Error loading save file {filepath}: {e}", exc_info=True)
        if on_error is not None:
            on_error(str(e))
        return False


def list_save_files() -> List[dict]:
    """Returns a list of dictionaries with summary details for all saved games in saves/."""
    _ensure_saves_dir()
    saves = []

    for fname in os.listdir(SAVES_DIR):
        if fname.endswith(".json"):
            filepath = os.path.join(SAVES_DIR, fname)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    game_state = data.get("game_state", {})
                    saves.append({
                        "filename": fname,
                        "filepath": filepath,
                        "turn_number": game_state.get("turn_number", 1),
                        "timestamp": data.get("timestamp", ""),
                        "current_system": game_state.get("current_system_name", "Galaxy")
                    })
            except Exception:
                continue

    saves.sort(key=lambda s: s["filename"], reverse=True)
    return saves
