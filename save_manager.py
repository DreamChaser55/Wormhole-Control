"""
save_manager.py

Handles saving and loading of game states and galaxy maps for Wormhole-Control.
Provides JSON serialization and deserialization for Players, Galaxy, StarSystems,
Hex grids, CelestialBodies, Units, UnitComponents, and Orders.
"""

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

from geometry import Position, Vector
from constants import (
    HullSize, StarType, PlanetType, NebulaType, StormType, HULL_CAPACITIES, HIT_POINTS
)
from entities import (
    Player, GameObject, CelestialBody, Star, Planet, Moon, ColonizableAsteroid,
    MetalAsteroid, AsteroidField, IceField, DebrisField, Nebula, Storm, Comet, Wormhole, Unit, Minefield
)
from galaxy import Galaxy, StarSystem, Hex
from unit_components import (
    AntimatterStorage, AntimatterHarvester, Engines, Hyperdrive, HyperdriveType,
    Commander, HyperspaceInhibitionFieldEmitter, Weapons, Defenses, Turret,
    ColonyComponent, CivilianHabitatComponent, OrbitalDefenseComponent, TradeComponent, Constructor, RepairComponent, MiningComponent,
    MetalRefineryComponent, CrystalRefineryComponent, HangarComponent,
    StrikecraftBayComponent, StrikecraftWingComponent, Sensors, AbilityComponent,
    MinelayerComponent, MarinesComponent, CloakingDevice, IntelligenceComponent,
    instantiate_unit_from_template, instantiate_component_for_unit, get_component_class_by_name
)
from unit_orders import (
    Order, OrderStatus, OrderType,
    MoveOrder, ReachWaypointOrder, AttackOrder, ColonizeOrder,
    LoadColonistsOrder, ConstructOrder, ToggleInhibitorOrder, PatrolOrder,
    RepairOrder, MineOrder, UnloadResourcesOrder, DockOrder, DeployUnitOrder,
    UseAbilityOrder, ProtectOrder, ContinuousMineOrder, TransferAntimatterOrder,
    ContinuousResupplyOrder, LayMinefieldOrder, RefitOrder, TradeOrder, ContinuousTradeOrder,
    InfiltrateUnitOrder, InfiltratePlanetOrder, RelocateAgentOrder, SabotageOrder,
    CISweepOrder, EliminateAgentOrder, ExtractAgentOrder
)

logger = logging.getLogger(__name__)


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

# Map of OrderType string names to Order classes
ORDER_CLASSES = {
    "MOVE": MoveOrder,
    "REACH_WAYPOINT": ReachWaypointOrder,
    "ATTACK": AttackOrder,
    "COLONIZE": ColonizeOrder,
    "LOAD_COLONISTS": LoadColonistsOrder,
    "CONSTRUCT": ConstructOrder,
    "TOGGLE_INHIBITOR": ToggleInhibitorOrder,
    "PATROL": PatrolOrder,
    "REPAIR": RepairOrder,
    "MINE": MineOrder,
    "UNLOAD_RESOURCES": UnloadResourcesOrder,
    "DOCK": DockOrder,
    "DEPLOY_UNIT": DeployUnitOrder,
    "USE_ABILITY": UseAbilityOrder,
    "PROTECT": ProtectOrder,
    "CONTINUOUS_MINE": ContinuousMineOrder,
    "TRANSFER_ANTIMATTER": TransferAntimatterOrder,
    "CONTINUOUS_RESUPPLY": ContinuousResupplyOrder,
    "REFIT_UNIT": RefitOrder,
    "TRADE": TradeOrder,
    "CONTINUOUS_TRADE": ContinuousTradeOrder,
    "INFILTRATE_UNIT": InfiltrateUnitOrder,
    "INFILTRATE_PLANET": InfiltratePlanetOrder,
    "RELOCATE_AGENT": RelocateAgentOrder,
    "SABOTAGE": SabotageOrder,
    "CI_SWEEP": CISweepOrder,
    "ELIMINATE_AGENT": EliminateAgentOrder,
    "EXTRACT_AGENT": ExtractAgentOrder,
}



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
        "is_human": player.is_human,
        "team_id": getattr(player, "team_id", player.id + 1),
        "persistent_id": getattr(player, "persistent_id", None) or str(uuid.uuid4()),
        "agent_id": getattr(player, "agent_id", None) or str(uuid.uuid4()),
        "ai_profile": getattr(player, "ai_profile", "balanced"),
        "ai_memory": getattr(player, "ai_memory", {}),
        "credits": player.credits,
        "metal": player.metal,
        "crystal": player.crystal,
        "sector_intel": sector_intel_data,
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
    elif isinstance(body, Moon) or isinstance(body, ColonizableAsteroid):
        data["owner_id"] = body.owner.id if body.owner else None
        data["population"] = body.population
        data["max_population"] = body.max_population
        data["population_growth_rate"] = body.population_growth_rate
    elif isinstance(body, MetalAsteroid):
        data["metal_yield"] = body.metal_yield
    elif isinstance(body, Comet):
        data["crystal_yield"] = body.crystal_yield
    elif isinstance(body, AsteroidField):
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

    data["infiltrating_agents"] = [a.to_dict() for a in getattr(body, 'infiltrating_agents', [])]
    return data


def serialize_order(order: Order) -> dict:
    params = {}
    if hasattr(order, "parameters") and isinstance(order.parameters, dict):
        for k, v in order.parameters.items():
            if isinstance(v, Position) or isinstance(v, Vector):
                params[k] = [v.x, v.y]
            elif isinstance(v, (tuple, list)):
                params[k] = list(v)
            else:
                params[k] = v

    order_type_str = order.order_type.name if hasattr(order, "order_type") and order.order_type else "UNKNOWN"
    status_str = order.status.name if hasattr(order, "status") and order.status else "PENDING"

    sub_orders = [serialize_order(so) for so in getattr(order, "sub_orders", [])]

    return {
        "order_type": order_type_str,
        "status": status_str,
        "parameters": params,
        "sub_orders": sub_orders
    }


def serialize_components(unit: Unit) -> dict:
    comps = {}
    for comp_type, comp in unit.components.items():
        comp_name = comp_type.__name__
        comp_data = {}

        if isinstance(comp, AntimatterStorage):
            comp_data["current_amount"] = comp.current_amount
            comp_data["max_capacity"] = comp.max_capacity
        elif isinstance(comp, ColonyComponent):
            comp_data["population_cargo"] = comp.population_cargo
            comp_data["max_cargo"] = comp.max_cargo
        elif isinstance(comp, MiningComponent):
            comp_data["mining_rate"] = comp.mining_rate
            comp_data["mining_range"] = comp.mining_range
            comp_data["raw_metal_cargo"] = comp.raw_metal_cargo
            comp_data["raw_crystal_cargo"] = comp.raw_crystal_cargo
            comp_data["max_cargo"] = comp.max_cargo
            comp_data["hull_cost"] = comp.hull_cost
        elif isinstance(comp, Hyperdrive):
            comp_data["recharge_time_remaining"] = comp.recharge_time_remaining
            comp_data["jump_status"] = comp.jump_status.name
        elif isinstance(comp, HyperspaceInhibitionFieldEmitter):
            comp_data["is_active"] = comp.is_active
        elif isinstance(comp, CloakingDevice):
            comp_data["is_active"] = comp.is_active
            comp_data["device_type"] = comp.device_type.name
            comp_data["area_radius"] = comp.area_radius
        elif isinstance(comp, HangarComponent):
            comp_data["docked_units"] = [serialize_unit(u) for u in comp.docked_units]
        elif isinstance(comp, StrikecraftBayComponent):
            comp_data["docked_units"] = [serialize_unit(u) for u in comp.docked_units]
            comp_data["constructing"] = comp.constructing
            comp_data["construction_progress"] = comp.construction_progress
            comp_data["build_wing_type"] = comp.build_wing_type.name
        elif isinstance(comp, StrikecraftWingComponent):
            comp_data["wing_type"] = comp.wing_type.name
        elif isinstance(comp, Constructor):
            if comp.current_construction_target:
                comp_data["current_construction_target"] = [
                    comp.current_construction_target[0],
                    [comp.current_construction_target[1].x, comp.current_construction_target[1].y]
                ]
                comp_data["construction_progress"] = comp.construction_progress
                comp_data["time_to_build"] = comp.time_to_build
            if comp.current_refit_target:
                comp_data["current_refit_target"] = dict(comp.current_refit_target)
                comp_data["refit_progress"] = comp.refit_progress
                comp_data["refit_time"] = comp.refit_time
        elif isinstance(comp, Defenses):
            comp_data["armor"] = comp.armor
            comp_data["shields"] = comp.shields
            comp_data["point_defense"] = comp.point_defense
            comp_data["hull_cost"] = comp.hull_cost
        elif isinstance(comp, Engines):
            comp_data["speed"] = comp.speed
            comp_data["hull_cost"] = comp.hull_cost
        elif isinstance(comp, RepairComponent):
            comp_data["repair_rate"] = comp.repair_rate
            comp_data["repair_range"] = comp.repair_range
            comp_data["credit_cost_per_hp"] = comp.credit_cost_per_hp
            comp_data["hull_cost"] = comp.hull_cost
        elif isinstance(comp, Sensors):
            comp_data["short_range_radius"] = comp.short_range_radius
            comp_data["long_range_hexes"] = comp.long_range_hexes
            comp_data["hull_cost"] = comp.hull_cost
        elif isinstance(comp, OrbitalDefenseComponent):
            comp_data["radius"] = comp.radius
            comp_data["attack_bonus"] = comp.attack_bonus
            comp_data["defense_bonus"] = comp.defense_bonus
            comp_data["hull_cost"] = comp.hull_cost
        elif isinstance(comp, TradeComponent):
            comp_data["last_traded_sector"] = list(comp.last_traded_sector) if comp.last_traded_sector else None
            comp_data["last_traded_unit_id"] = comp.last_traded_unit_id
            comp_data["last_trade_income"] = comp.last_trade_income
            comp_data["total_trade_income"] = comp.total_trade_income
            comp_data["trades_completed"] = comp.trades_completed
            comp_data["trade_revenue_multiplier"] = comp.trade_revenue_multiplier
            comp_data["hull_cost"] = comp.hull_cost
        elif isinstance(comp, IntelligenceComponent):
            comp_data["agents_count"] = comp.agents_count
            comp_data["agents_capacity"] = comp.agents_capacity
            comp_data["has_counter_intelligence"] = comp.has_counter_intelligence
            comp_data["ci_cooldown_remaining"] = comp.ci_cooldown_remaining
            comp_data["hull_cost"] = comp.hull_cost

        comps[comp_name] = comp_data

    return comps


def serialize_unit(unit: Unit) -> dict:
    orders_data = []
    if unit.commander_component and hasattr(unit.commander_component, "orders"):
        orders_data = [serialize_order(o) for o in unit.commander_component.orders]

    return {
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
        "damage_reduction": unit.damage_reduction,
        "damage_amplification": unit.damage_amplification,
        "lifetime": unit.lifetime,
        "is_temporary": unit.is_temporary,
        "infiltrating_agents": [a.to_dict() for a in getattr(unit, 'infiltrating_agents', [])],
        "components": serialize_components(unit),
        "orders": orders_data
    }


def serialize_minefield(minefield: Minefield) -> dict:
    return {
        "id": minefield.id,
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
    return {
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
    object_counter = GameObject.object_counter
    player_counter = Player.player_counter

    players_data = [serialize_player(p) for p in game.players]
    galaxy_data = serialize_galaxy(game.galaxy) if game.galaxy else None

    return {
        "version": "2.0",
        "timestamp": datetime.now().isoformat(),
        "game_state": {
            "turn_number": game.turn_number,
            "current_player_index": game.current_player_index,
            "view_mode": game.view_mode,
            "current_system_name": game.current_system_name,
            "current_sector_coord": list(game.current_sector_coord) if game.current_sector_coord else None,
            "object_counter": object_counter,
            "player_counter": player_counter,
            "campaign_id": getattr(game, "campaign_id", str(uuid.uuid4())),
        },
        "players": players_data,
        "galaxy": galaxy_data
    }


# --- Deserialization Functions ---

def deserialize_player(data: dict) -> Player:
    player = Player(
        name=data.get("name", "Player"),
        color=tuple(data.get("color", (255, 255, 255))),
        is_human=data.get("is_human", True),
        team_id=data.get("team_id", None),
        persistent_id=data.get("persistent_id"),
        agent_id=data.get("agent_id"),
        ai_profile=data.get("ai_profile", "balanced"),
        ai_memory=data.get("ai_memory", {}),
    )
    player.id = data.get("id", player.id)
    if "team_id" in data:
        player.team_id = data["team_id"]
    player.credits = data.get("credits", 20000.0)
    player.metal = data.get("metal", 10000.0)
    player.crystal = data.get("crystal", 10000.0)

    raw_intel = data.get("sector_intel", {})
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


def deserialize_celestial_body(data: dict, players_by_id: Dict[int, Player]) -> CelestialBody:
    class_name = data.get("class_name")
    cls = CELESTIAL_CLASSES.get(class_name)
    if not cls:
        raise ValueError(f"Unknown CelestialBody class_name: {class_name}")

    in_hex = tuple(data.get("in_hex", (0, 0)))
    in_system = data.get("in_system", "")
    position = Position(data["position"][0], data["position"][1])

    if cls == Star:
        star_type = StarType[data.get("star_type", "YELLOW_MAIN_SEQUENCE")]
        body = Star(in_system=in_system, star_type=star_type)
    elif cls == Planet:
        planet_type = PlanetType[data.get("planet_type", "TERRAN")]
        body = Planet(in_hex=in_hex, in_system=in_system, planet_type=planet_type)
        owner_id = data.get("owner_id")
        body.owner = players_by_id.get(owner_id) if owner_id is not None else None
        body.population = data.get("population", 0.0)
        body.max_population = data.get("max_population", 100.0)
        body.population_growth_rate = data.get("population_growth_rate", 0.02)
    elif cls in (Moon, ColonizableAsteroid):
        body = cls(in_hex=in_hex, in_system=in_system)
        owner_id = data.get("owner_id")
        body.owner = players_by_id.get(owner_id) if owner_id is not None else None
        body.population = data.get("population", 0.0)
        body.max_population = data.get("max_population", 50.0)
        body.population_growth_rate = data.get("population_growth_rate", 0.01)
    elif cls == MetalAsteroid:
        body = MetalAsteroid(in_hex=in_hex, in_system=in_system)
        body.metal_yield = data.get("metal_yield", 10.0)
    elif cls == Comet:
        body = Comet(in_hex=in_hex, in_system=in_system)
        body.crystal_yield = data.get("crystal_yield", 10.0)
    elif cls == AsteroidField:
        body = AsteroidField(in_hex=in_hex, in_system=in_system)
        body.asteroid_count = data.get("asteroid_count", 100)
    elif cls == Nebula:
        nebula_type = NebulaType[data.get("nebula_type", "EMISSION")]
        body = Nebula(in_hex=in_hex, in_system=in_system, nebula_type=nebula_type)
    elif cls == Storm:
        storm_type = StormType[data.get("storm_type", "ION")]
        body = Storm(in_hex=in_hex, in_system=in_system, storm_type=storm_type)
    elif cls == Wormhole:
        diameter = HullSize[data.get("diameter", "HUGE")]
        exit_sys = data.get("exit_system_name", "")
        stability = data.get("stability", 100)
        body = Wormhole(in_hex=in_hex, in_system=in_system, exit_system_name=exit_sys, stability=stability, diameter=diameter)
        body.exit_wormhole_id = data.get("exit_wormhole_id")
    else:
        body = cls(in_hex=in_hex, in_system=in_system)

    body.id = data.get("id", body.id)
    body.position = position
    if "name" in data and data["name"]:
        body.name = data["name"]
    if "inhibition_field_radius" in data:
        body.inhibition_field_radius = data["inhibition_field_radius"]

    if "infiltrating_agents" in data:
        from unit_components import Agent
        body.infiltrating_agents = [Agent.from_dict(ad, players_by_id, body) for ad in data["infiltrating_agents"]]

    return body


def deserialize_order(data: dict, unit: Unit, game: Any) -> Optional[Order]:
    order_type_str = data.get("order_type")
    order_cls = ORDER_CLASSES.get(order_type_str)
    if not order_cls:
        logger.warning(f"Unknown Order class for order_type: {order_type_str}")
        return None

    params = dict(data.get("parameters", {}))
    # Convert list positions back to Position objects if present
    for k, v in list(params.items()):
        if isinstance(v, list) and len(v) == 2 and isinstance(v[0], (int, float)) and isinstance(v[1], (int, float)):
            if k in ("destination_position", "target_position", "waypoint"):
                params[k] = Position(v[0], v[1])
            elif k in ("destination_hex", "target_hex"):
                params[k] = tuple(v)

    order = order_cls(unit=unit, parameters=params)
    status_str = data.get("status", "PENDING")
    if hasattr(OrderStatus, status_str):
        order.status = OrderStatus[status_str]

    for sub_data in data.get("sub_orders", []):
        sub_order = deserialize_order(sub_data, unit, game)
        if sub_order:
            sub_order.parent_order = order
            order.sub_orders.append(sub_order)

    return order


def _build_unit_from_template(template_name: str, owner: Player, position: Position, in_hex: Tuple[int, int], in_system: str, game: Any, custom_name: str) -> Unit:
    from unit_templates import UNIT_TEMPLATES
    from unit_components import TurretVariant, TurretType
    template = UNIT_TEMPLATES.get(template_name)
    if not template:
        return Unit(owner=owner, position=position, in_hex=in_hex, in_system=in_system, name=custom_name, hull_size=HullSize.MEDIUM, game=game, template_name=template_name)

    hull_size_val = template["hull_size"]
    if isinstance(hull_size_val, str):
        hull_size_val = HullSize[hull_size_val.upper()]

    new_unit = Unit(
        owner=owner,
        name=custom_name,
        hull_size=hull_size_val,
        game=game,
        in_system=in_system,
        in_hex=in_hex,
        position=position,
        template_name=template_name
    )

    if template.get("has_antimatter_storage", True):
        from custom_unit_templates import calc_antimatter_hull_cost
        cap = float(template.get("antimatter_capacity", 100.0))
        cost = template.get("antimatter_hull_cost")
        if cost is None:
            cost = calc_antimatter_hull_cost(cap)
        new_unit.add_component(AntimatterStorage(new_unit, max_capacity=cap, hull_cost=cost))
    elif template.get("has_antimatter_storage") is False:
        new_unit.remove_component(AntimatterStorage)

    if template.get("has_antimatter_harvester"):
        new_unit.add_component(AntimatterHarvester(new_unit, harvest_rate=template.get("antimatter_harvest_rate", 1.0)))

    if template.get("has_engine"):
        speed = template.get("engine_speed", 0)
        new_unit.add_component(Engines(new_unit, speed=speed, hull_cost=template.get("engine_hull_cost", 0)))

    if template.get("has_hyperdrive"):
        htype_raw = template.get("hyperdrive_type", HyperdriveType.BASIC)
        htype = HyperdriveType.ADVANCED if str(htype_raw).upper() == "ADVANCED" else HyperdriveType.BASIC
        cost = template.get("hyperdrive_hull_cost", 5.0)
        jump_range = template.get("hyperdrive_jump_range", 5)
        new_unit.add_component(Hyperdrive(new_unit, drive_type=htype, hull_cost=cost, jump_range=jump_range))

    if template.get("has_weapon_bays"):
        weapons_comp = Weapons(new_unit, hull_cost=template.get("weapon_bays_hull_cost", 0))
        for turret_def in template.get("turrets", []):
            variant_str = turret_def.get("variant", "STANDARD")
            variant = TurretVariant[variant_str.upper()] if hasattr(TurretVariant, variant_str.upper()) else TurretVariant.STANDARD
            turret = Turret(
                turret_type=TurretType[turret_def["type"]],
                damage=turret_def["damage"],
                range=turret_def["range"],
                cooldown=turret_def["cooldown"],
                parent_unit=new_unit,
                variant=variant
            )
            weapons_comp.add_turret(turret)
        new_unit.add_component(weapons_comp)

    if template.get("has_defenses"):
        new_unit.add_component(Defenses(new_unit, armor=template.get("armor", 0), shields=template.get("shields", 0), point_defense=template.get("point_defense", 0), hull_cost=template.get("defenses_hull_cost", 0)))

    if template.get("has_constructor_component"):
        new_unit.add_component(Constructor(new_unit, hull_cost=template.get("constructor_hull_cost", 0)))

    if template.get("has_repair_component"):
        new_unit.add_component(RepairComponent(new_unit, repair_rate=template.get("repair_rate", 10.0), repair_range=template.get("repair_range", 200.0)))

    if template.get("has_mining_component"):
        new_unit.add_component(MiningComponent(new_unit, mining_rate=template.get("mining_rate", 10.0), mining_range=template.get("mining_range", 200.0), max_cargo=template.get("max_mining_cargo", 100.0)))

    if template.get("has_metal_refinery_component"):
        new_unit.add_component(MetalRefineryComponent(new_unit, unload_range=template.get("unload_range", 300.0)))

    if template.get("has_crystal_refinery_component"):
        new_unit.add_component(CrystalRefineryComponent(new_unit, unload_range=template.get("unload_range", 300.0)))

    if template.get("has_hangar"):
        new_unit.add_component(HangarComponent(new_unit, max_slots=template.get("hangar_slots", 0)))

    if template.get("has_strikecraft_bay"):
        new_unit.add_component(StrikecraftBayComponent(new_unit, max_slots=template.get("strikecraft_bay_slots", 0)))

    if new_unit.hull_size == HullSize.STRIKECRAFT_WING:
        from unit_components import WingType
        wing_type_str = template.get("wing_type", "FIGHTER")
        wing_type = WingType[wing_type_str.upper()] if hasattr(WingType, wing_type_str.upper()) else WingType.FIGHTER
        new_unit.add_component(StrikecraftWingComponent(new_unit, wing_type=wing_type))

    if template.get("has_colony_component"):
        new_unit.add_component(ColonyComponent(new_unit))

    if template.get("has_civilian_habitat_component"):
        new_unit.add_component(CivilianHabitatComponent(
            new_unit,
            economic_bonus=template.get("civilian_habitat_bonus", 50.0),
            hull_cost=template.get("civilian_habitat_hull_cost", 15.0)
        ))

    if template.get("has_orbital_defense_component"):
        new_unit.add_component(OrbitalDefenseComponent(
            new_unit,
            radius=template.get("orbital_defense_radius", 500.0),
            attack_bonus=template.get("orbital_defense_attack_bonus", 0.20),
            defense_bonus=template.get("orbital_defense_defense_bonus", 0.20),
            hull_cost=template.get("orbital_defense_hull_cost", 20.0)
        ))

    if template.get("has_trade_component"):
        new_unit.add_component(TradeComponent(
            new_unit,
            hull_cost=template.get("trade_hull_cost", 10.0),
            trade_revenue_multiplier=template.get("trade_revenue_multiplier", 1.0)
        ))

    if template.get("has_marines_component"):
        new_unit.add_component(MarinesComponent(
            new_unit,
            marines_count=template.get("marines_count", 10),
            hull_cost=template.get("marines_hull_cost", 0.0)
        ))

    if template.get("has_cloaking_device"):
        from unit_components.cloaking import CloakingDevice
        from unit_components.enums import CloakingType
        from constants import DEFAULT_ADVANCED_CLOAKING_RADIUS
        c_type_raw = template.get("cloaking_type", "BASIC")
        c_type = CloakingType.ADVANCED if str(c_type_raw).upper() == "ADVANCED" else CloakingType.BASIC
        c_radius = float(template.get("cloaking_radius", DEFAULT_ADVANCED_CLOAKING_RADIUS)) if c_type == CloakingType.ADVANCED else 0.0
        c_cost = float(template.get("cloaking_hull_cost", CloakingDevice.calc_hull_cost(c_type, c_radius)))
        new_unit.add_component(CloakingDevice(new_unit, device_type=c_type, area_radius=c_radius, hull_cost=c_cost))

    if template.get("has_intelligence_component"):
        from unit_components import IntelligenceComponent
        i_count = int(template.get("intelligence_agents_count", 1))
        i_ci = bool(template.get("has_counter_intelligence", False))
        i_cost = template.get("intelligence_hull_cost")
        if i_cost is None:
            i_cost = IntelligenceComponent.calc_hull_cost(i_count, i_ci)
        new_unit.add_component(IntelligenceComponent(
            new_unit,
            agents_count=i_count,
            agents_capacity=i_count,
            has_counter_intelligence=i_ci,
            hull_cost=i_cost
        ))

    return new_unit


def deserialize_unit(data: dict, players_by_id: Dict[int, Player], game: Any) -> Unit:
    hull_size = HullSize[data.get("hull_size", "MEDIUM")]
    owner_id = data.get("owner_id")
    owner = players_by_id.get(owner_id) if owner_id is not None else players_by_id.get(0)

    in_hex = tuple(data["in_hex"]) if data.get("in_hex") else (0, 0)
    in_system = data.get("in_system", "")
    position = Position(data["position"][0], data["position"][1])
    name = data.get("name", "Unit")
    template_name = data.get("template_name")

    if template_name:
        unit = _build_unit_from_template(
            template_name=template_name,
            owner=owner,
            position=position,
            in_hex=in_hex,
            in_system=in_system,
            game=game,
            custom_name=name
        )
    else:
        unit = Unit(
            owner=owner,
            position=position,
            in_hex=in_hex,
            in_system=in_system,
            name=name,
            hull_size=hull_size,
            game=game
        )

    unit.id = data.get("id", unit.id)
    unit.current_hit_points = data.get("current_hit_points", unit.current_hit_points)
    unit.max_hit_points = data.get("max_hit_points", unit.max_hit_points)
    unit.experience_points = data.get("experience_points", 0)
    unit.is_disabled = data.get("is_disabled", False)
    unit.disabled_by_unit_ids = set(data.get("disabled_by_unit_ids", []))
    unit.damage_reduction = data.get("damage_reduction", 0.0)
    unit.damage_amplification = data.get("damage_amplification", 0.0)
    unit.lifetime = data.get("lifetime")
    unit.is_temporary = data.get("is_temporary", False)

    # Restore component dynamic state
    comps_data = data.get("components", {})

    # First, restore dynamically added components that weren't in base template
    for comp_name, comp_fields in comps_data.items():
        comp_cls = get_component_class_by_name(comp_name)
        if comp_cls and comp_cls not in unit.components:
            inst = instantiate_component_for_unit(comp_name, unit, comp_fields)
            if inst:
                unit.add_component(inst)

    for comp_name, comp_fields in comps_data.items():
        if comp_name == "AntimatterStorage" and unit.antimatter_component:
            unit.antimatter_component.current_amount = comp_fields.get("current_amount", unit.antimatter_component.current_amount)
            unit.antimatter_component.max_capacity = comp_fields.get("max_capacity", unit.antimatter_component.max_capacity)
        elif comp_name == "ColonyComponent" and unit.colony_component:
            unit.colony_component.population_cargo = comp_fields.get("population_cargo", unit.colony_component.population_cargo)
            unit.colony_component.max_cargo = comp_fields.get("max_cargo", unit.colony_component.max_cargo)
        elif comp_name == "MiningComponent" and unit.mining_component:
            unit.mining_component.mining_rate = comp_fields.get("mining_rate", unit.mining_component.mining_rate)
            unit.mining_component.mining_range = comp_fields.get("mining_range", unit.mining_component.mining_range)
            unit.mining_component.raw_metal_cargo = comp_fields.get("raw_metal_cargo", unit.mining_component.raw_metal_cargo)
            unit.mining_component.raw_crystal_cargo = comp_fields.get("raw_crystal_cargo", unit.mining_component.raw_crystal_cargo)
            unit.mining_component.max_cargo = comp_fields.get("max_cargo", unit.mining_component.max_cargo)
        elif comp_name == "Hyperdrive" and unit.hyperdrive_component:
            from unit_components import JumpStatus
            unit.hyperdrive_component.recharge_time_remaining = comp_fields.get("recharge_time_remaining", 0)
            status_str = comp_fields.get("jump_status", "READY")
            if hasattr(JumpStatus, status_str):
                unit.hyperdrive_component.jump_status = JumpStatus[status_str]
        elif comp_name == "CivilianHabitatComponent" and unit.civilian_habitat_component:
            unit.civilian_habitat_component.economic_bonus = comp_fields.get("economic_bonus", unit.civilian_habitat_component.economic_bonus)
        elif comp_name in ("IntelligenceComponent", "Intelligence") and getattr(unit, "intelligence_component", None):
            unit.intelligence_component.agents_count = comp_fields.get("agents_count", unit.intelligence_component.agents_count)
            unit.intelligence_component.agents_capacity = comp_fields.get("agents_capacity", unit.intelligence_component.agents_capacity)
            unit.intelligence_component.has_counter_intelligence = comp_fields.get("has_counter_intelligence", unit.intelligence_component.has_counter_intelligence)
            unit.intelligence_component.ci_cooldown_remaining = comp_fields.get("ci_cooldown_remaining", 0)
        elif comp_name == "OrbitalDefenseComponent" and unit.orbital_defense_component:
            unit.orbital_defense_component.radius = comp_fields.get("radius", unit.orbital_defense_component.radius)
            unit.orbital_defense_component.attack_bonus = comp_fields.get("attack_bonus", unit.orbital_defense_component.attack_bonus)
            unit.orbital_defense_component.defense_bonus = comp_fields.get("defense_bonus", unit.orbital_defense_component.defense_bonus)
        elif comp_name == "TradeComponent" and unit.trade_component:
            raw_sec = comp_fields.get("last_traded_sector")
            if raw_sec and len(raw_sec) == 2:
                unit.trade_component.last_traded_sector = (raw_sec[0], tuple(raw_sec[1]))
            else:
                unit.trade_component.last_traded_sector = None
            unit.trade_component.last_traded_unit_id = comp_fields.get("last_traded_unit_id")
            unit.trade_component.last_trade_income = comp_fields.get("last_trade_income", 0.0)
            unit.trade_component.total_trade_income = comp_fields.get("total_trade_income", 0.0)
            unit.trade_component.trades_completed = comp_fields.get("trades_completed", 0)
            unit.trade_component.trade_revenue_multiplier = comp_fields.get("trade_revenue_multiplier", 1.0)
        elif comp_name == "HyperspaceInhibitionFieldEmitter" and unit.inhibitor_component:
            unit.inhibitor_component.is_active = comp_fields.get("is_active", unit.inhibitor_component.is_active)
        elif comp_name == "CloakingDevice":
            from unit_components.enums import CloakingType
            from unit_components.cloaking import CloakingDevice
            type_str = comp_fields.get("device_type", "BASIC")
            c_type = CloakingType.ADVANCED if str(type_str).upper() == "ADVANCED" else CloakingType.BASIC
            c_radius = float(comp_fields.get("area_radius", 0.0))
            if not unit.cloaking_component:
                unit.add_component(CloakingDevice(unit, device_type=c_type, area_radius=c_radius))
            else:
                unit.cloaking_component.device_type = c_type
                unit.cloaking_component.area_radius = c_radius
            unit.cloaking_component.is_active = comp_fields.get("is_active", False)
        elif comp_name == "HangarComponent" and unit.hangar_component:
            unit.hangar_component.docked_units.clear()
            for docked_data in comp_fields.get("docked_units", []):
                docked_u = deserialize_unit(docked_data, players_by_id, game)
                unit.hangar_component.docked_units.append(docked_u)
        elif comp_name == "StrikecraftBayComponent" and unit.strikecraft_bay_component:
            from unit_components import WingType
            unit.strikecraft_bay_component.docked_units.clear()
            for docked_data in comp_fields.get("docked_units", []):
                docked_u = deserialize_unit(docked_data, players_by_id, game)
                if docked_u.strikecraft_wing_component:
                    docked_u.strikecraft_wing_component.mother_carrier = unit
                unit.strikecraft_bay_component.docked_units.append(docked_u)
            unit.strikecraft_bay_component.constructing = comp_fields.get("constructing", False)
            unit.strikecraft_bay_component.construction_progress = comp_fields.get("construction_progress", 0)
            wing_type_str = comp_fields.get("build_wing_type", "FIGHTER")
            if hasattr(WingType, wing_type_str):
                unit.strikecraft_bay_component.build_wing_type = WingType[wing_type_str]
        elif comp_name == "StrikecraftWingComponent" and unit.strikecraft_wing_component:
            from unit_components import WingType
            wing_type_str = comp_fields.get("wing_type", "FIGHTER")
            if hasattr(WingType, wing_type_str):
                unit.strikecraft_wing_component.wing_type = WingType[wing_type_str]
        elif comp_name == "MarinesComponent":
            marines_comp = unit.get_component(MarinesComponent)
            if marines_comp:
                marines_comp.marines_count = comp_fields.get("marines_count", marines_comp.marines_count)
        elif comp_name == "Constructor" and unit.constructor_component:
            if "current_construction_target" in comp_fields:
                tgt_raw = comp_fields["current_construction_target"]
                unit.constructor_component.current_construction_target = (tgt_raw[0], Position(tgt_raw[1][0], tgt_raw[1][1]))
                unit.constructor_component.construction_progress = comp_fields.get("construction_progress", 0)
                unit.constructor_component.time_to_build = comp_fields.get("time_to_build", 0)
            if "current_refit_target" in comp_fields:
                unit.constructor_component.current_refit_target = comp_fields["current_refit_target"]
                unit.constructor_component.refit_progress = comp_fields.get("refit_progress", 0)
                unit.constructor_component.refit_time = comp_fields.get("refit_time", 0)

    # Remove components that were removed via refit
    for comp_cls in list(unit.components.keys()):
        if comp_cls == Commander:
            continue
        if comp_cls.__name__ not in comps_data and (comp_cls != HyperspaceInhibitionFieldEmitter or "Inhibitor" not in comps_data):
            unit.remove_component(comp_cls)

    # Restore infiltrating agents if present
    if "infiltrating_agents" in data:
        from unit_components import Agent
        unit.infiltrating_agents = [Agent.from_dict(ad, players_by_id, unit) for ad in data["infiltrating_agents"]]

    # Note: Commander orders will be restored after all units are in place so references can be mapped.
    unit._saved_orders_data = data.get("orders", [])

    return unit


def deserialize_minefield(data: dict, players_by_id: Dict[int, Player]) -> Minefield:
    owner_id = data.get("owner_id")
    owner = players_by_id.get(owner_id) if owner_id is not None else players_by_id.get(0)
    in_hex = tuple(data.get("in_hex", (0, 0)))
    in_system = data.get("in_system", "")
    position = Position(data["position"][0], data["position"][1])
    minefield_type = data.get("minefield_type", "anti_ship")

    minefield = Minefield(
        owner=owner,
        position=position,
        in_hex=in_hex,
        in_system=in_system,
        mines_remaining=data.get("mines_remaining", 5),
        mine_damage=data.get("mine_damage", 40.0),
        detonation_radius=data.get("detonation_radius", 250.0),
        minefield_type=minefield_type
    )
    minefield.id = data.get("id", minefield.id)
    minefield.revealed_to_player_ids = set(data.get("revealed_to_player_ids", []))
    return minefield


def deserialize_hex(data: dict, players_by_id: Dict[int, Player], game: Any) -> Hex:
    q = data["q"]
    r = data["r"]
    in_system = data["in_system"]
    hex_obj = Hex(q, r, in_system=in_system)

    for cb_data in data.get("celestial_bodies", []):
        body = deserialize_celestial_body(cb_data, players_by_id)
        hex_obj.add_celestial_body(body)

    for unit_data in data.get("units", []):
        unit = deserialize_unit(unit_data, players_by_id, game)
        hex_obj.add_unit(unit)

    for mf_data in data.get("minefields", []):
        mf = deserialize_minefield(mf_data, players_by_id)
        hex_obj.add_minefield(mf)

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

    for hex_data in data.get("hexes", []):
        hex_obj = deserialize_hex(hex_data, players_by_id, game)
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

    bounds = data.get("generation_bounds", {})
    galaxy.generation_x_min = bounds.get("x_min", 50)
    galaxy.generation_x_max = bounds.get("x_max", 1870)
    galaxy.generation_y_min = bounds.get("y_min", 50)
    galaxy.generation_y_max = bounds.get("y_max", 1030)

    for sys_data in data.get("systems", []):
        sys_obj = deserialize_star_system(sys_data, players_by_id, game)
        galaxy.systems[sys_obj.name] = sys_obj

        # Collect wormholes
        for hex_obj in sys_obj.hexes.values():
            for body in hex_obj.celestial_bodies:
                if isinstance(body, Wormhole):
                    galaxy.wormholes[body.id] = body

    galaxy._build_system_graph()
    return galaxy


def deserialize_game_state(game: Any, data: dict) -> bool:
    """Restores the active game state from serialized JSON dictionary."""
    try:
        state_info = data["game_state"]
        game.turn_number = state_info.get("turn_number", 1)
        game.current_player_index = state_info.get("current_player_index", 0)
        game.view_mode = state_info.get("view_mode", "galaxy")
        game.current_system_name = state_info.get("current_system_name")
        game.campaign_id = state_info.get("campaign_id") or str(uuid.uuid4())

        sec_coord = state_info.get("current_sector_coord")
        game.current_sector_coord = tuple(sec_coord) if sec_coord else None

        # Clear active selections
        game.selected_objects = []
        game.hovered_object = None

        # Reconstruct Players
        game.players = [deserialize_player(p_data) for p_data in data.get("players", [])]
        players_by_id = {p.id: p for p in game.players}

        # Reconstruct Galaxy
        game.galaxy = deserialize_galaxy(data["galaxy"], players_by_id, game)

        # Second Pass: Restore orders on all units now that galaxy objects exist
        max_object_id = 0
        for sys_obj in game.galaxy.systems.values():
            for hex_obj in sys_obj.hexes.values():
                for body in hex_obj.celestial_bodies:
                    if body.id > max_object_id:
                        max_object_id = body.id
                for unit in hex_obj.units:
                    if unit.id > max_object_id:
                        max_object_id = unit.id

                    if hasattr(unit, "_saved_orders_data") and unit.commander_component:
                        unit.commander_component.clear_orders()
                        for order_data in unit._saved_orders_data:
                            order = deserialize_order(order_data, unit, game)
                            if order:
                                unit.commander_component.add_order(order)
                        delattr(unit, "_saved_orders_data")

        # Update global object and player counters to prevent ID collisions
        max_player_id = max([p.id for p in game.players]) if game.players else 0
        Player.player_counter = max_player_id + 1
        GameObject.object_counter = max_object_id + 1

        game.game_started = True
        game.visibility = None
        game.visibility_dirty = True
        game.recompute_visibility()
        game.update_side_bar_content()
        game.update_player_turn_display()
        if hasattr(game, 'check_and_schedule_ai_turn'):
            game.check_and_schedule_ai_turn()

        logger.debug(f"Game state successfully loaded. Turn: {game.turn_number}, Systems: {len(game.galaxy.systems)}")
        return True
    except Exception as e:
        logger.error(f"Failed to deserialize game state: {e}", exc_info=True)
        return False


# --- I/O Helper Functions ---

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
        json.dump(state_dict, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary_path, filepath)

    try:
        from pathlib import Path
        from game_ai.memory import AgentMemory, write_memory_sidecar

        for player in game.players:
            if not getattr(player, "is_human", True):
                write_memory_sidecar(
                    Path(SAVES_DIR),
                    campaign_id=str(game.campaign_id),
                    agent_id=str(player.agent_id),
                    player_name=str(player.name),
                    memory=AgentMemory.from_dict(getattr(player, "ai_memory", None)),
                )
    except Exception:
        logger.warning("Could not write AI memory sidecars.", exc_info=True)

    logger.debug(f"Game saved successfully to {filepath}")
    return filepath


def load_game_from_file(game: Any, filepath: str) -> bool:
    """Loads a game state from a JSON file into the game instance."""
    if not os.path.isabs(filepath):
        filepath = os.path.join(SAVES_DIR, filepath)

    if not os.path.exists(filepath):
        logger.error(f"Save file not found: {filepath}")
        return False

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        return deserialize_game_state(game, data)
    except Exception as e:
        logger.error(f"Error loading save file {filepath}: {e}", exc_info=True)
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
