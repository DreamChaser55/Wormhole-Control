"""Prepare, reconcile, validate, and commit a campaign without live-game callbacks."""
from dataclasses import dataclass, field
from types import SimpleNamespace
import math
import uuid

from campaign_graph import iter_objects, iter_units
from persistence_context import isolated_allocations
from state_codec import number


@dataclass
class PreparedCampaign:
    state: SimpleNamespace
    object_counter: int
    player_counter: int
    agent_counter: int
    order_counter: int
    warnings: list
    testing_templates: dict = field(default_factory=dict)


def validate_json(value, path="save", depth=0):
    if depth > 100:
        raise ValueError(f"{path}: nesting exceeds 100 levels")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path}: non-string key")
            validate_json(item, f"{path}.{key}", depth + 1)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            validate_json(item, f"{path}[{index}]", depth + 1)
    elif type(value) is float:
        if not math.isfinite(value):
            raise ValueError(f"{path}: non-finite number")
    elif value is not None and type(value) not in (str, int, bool):
        raise ValueError(f"{path}: not a JSON value")


def require(data, names, path):
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected object")
    missing = set(names) - data.keys()
    if missing:
        raise ValueError(f"{path}: missing {sorted(missing)}")


def coordinates(value, path, integer=False):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{path}: expected two coordinates")
    for v in value:
        number(v, path, integer=integer)


def validate_document(data):
    """Validate shape before constructors/defaults can mask missing state."""
    from save_manager import ORDER_CLASSES, CELESTIAL_CLASSES
    from unit_orders.base import OrderStatus
    from unit_components.persistence import component_registry
    from unit_components.enums import MinefieldType, SabotageType
    require(data, ("version", "game_state", "players", "galaxy", "conversations"), "save")
    state = data["game_state"]
    require(state, ("turn_number", "current_player_index", "view_mode", "current_system_name",
                    "current_sector_coord", "object_counter", "player_counter", "agent_counter",
                    "message_counter", "campaign_id"), "game_state")
    for name in ("turn_number", "current_player_index", "object_counter", "player_counter", "agent_counter", "message_counter"):
        number(state[name], f"game_state.{name}", 1 if name == "turn_number" else 0, integer=True)
    if state["view_mode"] not in ("galaxy", "system", "sector"):
        raise ValueError("game_state.view_mode: unknown view")
    if not isinstance(state["campaign_id"], str) or not state["campaign_id"]:
        raise ValueError("game_state.campaign_id: expected nonempty string")
    if state["current_sector_coord"] is not None:
        coordinates(state["current_sector_coord"], "game_state.current_sector_coord", True)
    if not isinstance(data["players"], list) or not data["players"]:
        raise ValueError("players: expected nonempty array")
    if state["current_player_index"] >= len(data["players"]):
        raise ValueError("game_state.current_player_index: out of range")
    player_ids = set()
    for p in data["players"]:
        require(p, ("id", "name", "color", "controller", "team_id", "credits", "metal", "crystal",
                    "sector_intel", "order_history", "order_event_sequence", "persistent_id", "agent_id",
                    "ai_memory", "ai_reasoning_effort", "ai_repair_retries", "homeworld_id"), "player")
        number(p["id"], "player.id", 0, integer=True)
        if p["id"] in player_ids:
            raise ValueError("Duplicate player ID")
        player_ids.add(p["id"])
        for name in ("credits", "metal", "crystal", "order_event_sequence"):
            number(p[name], f"player.{name}", 0, integer=name == "order_event_sequence")
        if not isinstance(p["color"], list) or len(p["color"]) != 3:
            raise ValueError("player.color: expected RGB array")
        for channel in p["color"]:
            if number(channel, "player.color", 0, integer=True) > 255:
                raise ValueError("player.color: channel exceeds 255")
        if not isinstance(p["sector_intel"], dict) or not isinstance(p["order_history"], list) or not isinstance(p["ai_memory"], dict):
            raise ValueError("Invalid player history/intel/memory")
        for location, turn in p["sector_intel"].items():
            parts = location.rsplit(":", 2)
            if len(parts) != 3:
                raise ValueError("player.sector_intel: invalid location")
            int(parts[1]), int(parts[2])
            number(turn, "player.sector_intel.turn", 0, integer=True)
    require(data["galaxy"], ("systems", "generation_bounds"), "galaxy")
    if not isinstance(data["galaxy"]["systems"], list) or not data["galaxy"]["systems"]:
        raise ValueError("galaxy.systems: expected nonempty array")
    registry = component_registry()
    public_ids = set()

    def order_values(value, path):
        from save_manager import _decode_known_enum
        from enum import Enum
        if isinstance(value, dict):
            tag = value.get("__type__")
            if tag == "enum":
                if not isinstance(_decode_known_enum(value.get("enum", ""), value.get("value")), Enum):
                    raise ValueError(f"{path}: invalid enum")
            elif tag == "position":
                number(value.get("x"), path)
                number(value.get("y"), path)
            elif tag in ("tuple", "set", "dict"):
                if not isinstance(value.get("items"), list):
                    raise ValueError(f"{path}: invalid tagged collection")
                if tag == "dict" and any(not isinstance(pair, list) or len(pair) != 2 for pair in value["items"]):
                    raise ValueError(f"{path}: invalid tagged dictionary")
            elif tag == "class":
                if value.get("name") not in registry:
                    raise ValueError(f"{path}: unknown component class")
            elif tag is not None:
                raise ValueError(f"{path}: unknown order value tag")
            for key, item in value.items():
                order_values(item, f"{path}.{key}")
        elif isinstance(value, list):
            for item in value:
                order_values(item, path)

    def order(raw, path):
        if raw is None:
            return
        require(raw, ("public_id", "order_type", "status", "parameters", "runtime_state", "sub_orders"), path)
        if raw["order_type"] not in ORDER_CLASSES or raw["status"] not in OrderStatus.__members__:
            raise ValueError(f"{path}: unknown order type/status")
        uid = uuid.UUID(raw["public_id"]).hex
        if uid in public_ids:
            raise ValueError(f"{path}: duplicate order UUID")
        public_ids.add(uid)
        if not isinstance(raw["parameters"], dict) or not isinstance(raw["runtime_state"], dict) or not isinstance(raw["sub_orders"], list):
            raise ValueError(f"{path}: malformed order state")
        order_values(raw["parameters"], f"{path}.parameters")
        order_values(raw["runtime_state"], f"{path}.runtime_state")
        for i, child in enumerate(raw["sub_orders"]):
            order(child, f"{path}.sub_orders[{i}]")

    def located(raw, path):
        require(raw, ("id", "position", "in_system", "in_hex"), path)
        number(raw["id"], f"{path}.id", 0, integer=True)
        coordinates(raw["position"], f"{path}.position")
        coordinates(raw["in_hex"], f"{path}.in_hex", True)
        if "owner_id" in raw and raw["owner_id"] is not None and (type(raw["owner_id"]) is not int or raw["owner_id"] not in player_ids):
            raise ValueError(f"{path}.owner_id: unknown player")
        for agent in raw.get("infiltrating_agents", []):
            require(agent, ("id", "owner_id", "source_unit_id", "target_type", "target_id", "is_discovered", "active_sabotage", "turns_active"), f"{path}.agent")
            for name in ("id", "owner_id", "source_unit_id", "target_id", "turns_active"):
                number(agent[name], f"{path}.agent.{name}", 0, integer=True)
            if agent["owner_id"] not in player_ids or type(agent["is_discovered"]) is not bool:
                raise ValueError(f"{path}.agent: invalid owner/discovery state")
            if agent["active_sabotage"] is not None and agent["active_sabotage"] not in SabotageType.__members__:
                raise ValueError(f"{path}.agent.active_sabotage: unknown enum")

    def unit(raw, path):
        located(raw, path)
        require(raw, ("schema_version", "name", "owner_id", "hull_size", "components", "current_hit_points",
                      "max_hit_points", "experience_points", "is_disabled", "disabled_by_unit_ids", "damage_reduction",
                      "damage_amplification", "lifetime", "is_temporary", "infiltrating_agents"), path)
        if not isinstance(raw["components"], dict):
            raise ValueError(f"{path}.components: expected object")
        if raw["owner_id"] is None:
            raise ValueError(f"{path}.owner_id: unit has no owner")
        for name in ("current_hit_points", "max_hit_points", "experience_points"):
            number(raw[name], f"{path}.{name}", 0, integer=True)
        if raw["max_hit_points"] <= 0 or raw["current_hit_points"] > raw["max_hit_points"]:
            raise ValueError(f"{path}: invalid hull HP")
        for name in ("is_disabled", "is_temporary"):
            if type(raw[name]) is not bool:
                raise ValueError(f"{path}.{name}: expected boolean")
        if raw["lifetime"] is not None:
            number(raw["lifetime"], f"{path}.lifetime", 0, integer=True)
        for name, component in raw["components"].items():
            if name not in registry:
                raise ValueError(f"{path}.components: unknown {name}")
            require(component, ("type", "schema_version", "configuration", "runtime"), f"{path}.{name}")
            runtime = component["runtime"]
            if not isinstance(runtime, dict):
                raise ValueError(f"{path}.{name}.runtime: expected object")
            if name == "Constructor" and runtime.get("current_refit_target") is not None:
                job = runtime["current_refit_target"]
                if not isinstance(job, dict) or type(job.get("payer_id")) is not int or job["payer_id"] not in player_ids:
                    raise ValueError(f"{path}.Constructor.refit: unknown payer")
            for i, child in enumerate(runtime.get("docked_units", [])):
                unit(child, f"{path}.{name}.docked_units[{i}]")
            if name == "Commander":
                order(runtime.get("current_order"), f"{path}.current_order")
                for i, root in enumerate(runtime.get("orders_queue", [])):
                    order(root, f"{path}.orders_queue[{i}]")

    for system in data["galaxy"]["systems"]:
        require(system, ("name", "position", "radius", "hexes"), "system")
        coordinates(system["position"], "system.position")
        number(system["radius"], "system.radius", 0, integer=True)
        for sector in system["hexes"]:
            require(sector, ("q", "r", "in_system", "units", "celestial_bodies", "minefields"), "sector")
            if sector["in_system"] != system["name"]:
                raise ValueError("sector.in_system: inconsistent location")
            number(sector["q"], "sector.q", integer=True)
            number(sector["r"], "sector.r", integer=True)
            for body in sector["celestial_bodies"]:
                located(body, "body")
                if body.get("class_name") not in CELESTIAL_CLASSES:
                    raise ValueError("body.class_name: unknown class")
                body_fields = {
                    "Star": ("star_type",), "Planet": ("planet_type", "owner_id", "population", "max_population", "population_growth_rate"),
                    "Moon": ("owner_id", "population", "max_population", "population_growth_rate"),
                    "ColonizableAsteroid": ("owner_id", "population", "max_population", "population_growth_rate"),
                    "MetalAsteroid": ("metal_yield",), "Comet": ("crystal_yield",),
                    "Wormhole": ("exit_system_name", "exit_wormhole_id", "stability", "diameter"),
                    "Nebula": ("nebula_type",), "Storm": ("storm_type",),
                    "AsteroidField": ("density", "asteroid_count"), "IceField": ("density",), "DebrisField": ("density",)}
                require(body, (*body_fields[body["class_name"]], "infiltrating_agents", "inhibition_field_radius"), "body")
                for name in ("population", "max_population", "population_growth_rate", "metal_yield", "crystal_yield", "inhibition_field_radius"):
                    if name in body:
                        number(body[name], f"body.{name}", 0)
                for u in body.get("hidden_units", []):
                    unit(u, f"body[{body['id']}].hidden_units")
            for raw in sector["units"]:
                unit(raw, f"unit[{raw.get('id')}]")
            from tactical_persistence import validate as validate_tactical
            for collection, patch in (('deployables', False), ('catalyst_patches', True)):
                if not isinstance(sector.get(collection), list):
                    raise ValueError('Missing tactical collection')
                for obj in sector[collection]:
                    located(obj, collection)
                    validate_tactical(obj, player_ids, patch=patch)
            for mf in sector["minefields"]:
                located(mf, "minefield")
                require(mf, ("owner_id", "mines_remaining", "mine_damage", "detonation_radius", "minefield_type", "revealed_to_player_ids"), "minefield")
                for name in ("mines_remaining", "mine_damage", "detonation_radius"):
                    number(mf[name], f"minefield.{name}", 0, integer=name == "mines_remaining")
                MinefieldType(mf["minefield_type"])
                if not isinstance(mf["revealed_to_player_ids"], list) or any(type(pid) is not int or pid not in player_ids for pid in mf["revealed_to_player_ids"]):
                    raise ValueError("minefield.revealed_to_player_ids: unknown player")


def reconcile(candidate):
    """Rebuild derived state only; no turn advancement, commands, or UI callbacks."""
    from domain.units import Unit
    from domain.celestials import Wormhole, Planet
    from galaxy import Hex
    from unit_components.hangar import HangarComponent
    from unit_components.strikecraft import StrikecraftBayComponent
    from geometry import Circle, is_circle_contained, do_circles_intersect
    from constants import PlanetType
    from visibility import VisibilityService
    from timed_effects import refresh
    import save_manager as sm
    galaxy = candidate.galaxy
    owned = list(iter_objects(galaxy))
    objects = {}
    agents = {}
    for obj, container in owned:
        if obj.id in objects:
            raise ValueError(f"Duplicate object ID {obj.id}")
        objects[obj.id] = obj
        location = container.unit if isinstance(container, (HangarComponent, StrikecraftBayComponent)) else container
        expected_hex = (location.q, location.r) if isinstance(location, Hex) else location.in_hex
        if obj.in_system != location.in_system or obj.in_hex != expected_hex:
            raise ValueError(f"Object {obj.id}: inconsistent container location")
        from domain.deployables import Deployable
        if isinstance(obj, Deployable):
            obj.in_galaxy = galaxy
        if isinstance(obj, Unit):
            obj.game = candidate
            obj.in_galaxy = galaxy
            obj.is_hidden_in_gas_giant = isinstance(container, Planet)
            obj.hidden_in_gas_giant_id = container.id if obj.is_hidden_in_gas_giant else None
            if obj.is_hidden_in_gas_giant and container.planet_type != PlanetType.GAS_GIANT:
                raise ValueError("Hidden unit belongs to a non-gas-giant body")
            obj._update_hull_usage()
            obj._ability_effects = {}
            refresh(obj)
            if obj.intelligence_component:
                obj.intelligence_component._deployed_agents = []
            if obj.strikecraft_bay_component:
                obj.strikecraft_bay_component.launched_units = []
        for agent in getattr(obj, "infiltrating_agents", ()):
            if agent.id in agents:
                raise ValueError(f"Duplicate agent ID {agent.id}")
            agents[agent.id] = agent
            expected_type = "UNIT" if isinstance(obj, Unit) else "CELESTIAL_BODY"
            if agent.target_id != obj.id or agent.target_type != expected_type or agent.owner is None:
                raise ValueError(f"Agent {agent.id}: invalid host or owner")
            agent.attached_to = obj
    for obj, container in owned:
        if isinstance(obj, Unit):
            if obj.ability_component:
                for ability in obj.ability_component.abilities.values():
                    target = objects.get(ability.target_unit_id)
                    if target is not None and not isinstance(target, Unit):
                        raise ValueError(f"Unit {obj.id}: ability target is not a unit")
                    for uid in ability.spawned_unit_ids:
                        spawned = objects.get(uid)
                        if spawned is not None and (not isinstance(spawned, Unit) or not spawned.is_temporary):
                            raise ValueError(f"Unit {obj.id}: spawned ability object is not a temporary unit")
            for component in obj.components.values():
                for name, uid in getattr(component, "_saved_refs", {}).items():
                    target = objects.get(uid)
                    if target is not None:
                        expected_unit = name != "mining_target"
                        if isinstance(target, Unit) != expected_unit:
                            raise ValueError(f"Unit {obj.id}.{name}: wrong reference type")
                    if uid is not None and target is None and name == "mother_carrier":
                        raise ValueError(f"Unit {obj.id}: missing mother carrier {uid}")
                component.resolve_state(objects)
            wing = obj.strikecraft_wing_component
            if wing and isinstance(container, StrikecraftBayComponent):
                if wing.mother_carrier not in (None, container.unit):
                    raise ValueError("Inconsistent wing carrier")
                wing.mother_carrier = container.unit
            if wing and wing.mother_carrier:
                bay = wing.mother_carrier.strikecraft_bay_component
                if not bay:
                    raise ValueError("Mother carrier has no strikecraft bay")
                if obj not in bay.docked_units:
                    bay.launched_units.append(obj)
    for agent in agents.values():
        source = objects.get(agent.source_unit_id)
        agent._source_unit = source if isinstance(source, Unit) else None
        if source and isinstance(source, Unit) and source.intelligence_component:
            source.intelligence_component._deployed_agents.append(agent)
    galaxy.wormholes = {}
    for system in galaxy.systems.values():
        system.in_galaxy = galaxy
        system.celestial_bodies_by_id = {}
        for sector in system.hexes.values():
            sector.update_static_inhibition_zones()
            sector.dynamic_inhibition_zones.clear()
            for body in sector.celestial_bodies:
                system.celestial_bodies_by_id[body.id] = body
                if isinstance(body, Wormhole):
                    galaxy.wormholes[body.id] = body
            for unit in sector.units:
                emitter = unit.inhibitor_component
                if emitter and emitter.is_active:
                    if emitter.is_destroyed or unit.current_hit_points <= 0:
                        emitter.is_active = False
                        continue
                    circle = Circle(unit.position, emitter.radius)
                    if not is_circle_contained(circle, sector.boundary_circle) or any(do_circles_intersect(circle, z) for z in sector.get_all_inhibition_zones()):
                        raise ValueError(f"Unit {unit.id}: invalid active inhibition zone")
                    sector.dynamic_inhibition_zones[unit.id] = circle
    for wormhole in galaxy.wormholes.values():
        other = galaxy.wormholes.get(wormhole.exit_wormhole_id)
        if other is None or other.in_system != wormhole.exit_system_name or other.exit_wormhole_id != wormhole.id:
            raise ValueError(f"Wormhole {wormhole.id}: invalid reciprocal exit")
    galaxy._build_system_graph()
    for obj, container in owned:
        if isinstance(obj, Unit):
            if not isinstance(container, Hex) and obj.inhibitor_component:
                obj.inhibitor_component.is_active = False
            if obj.ability_component:
                obj.ability_component.reconcile_effects(galaxy)
            if obj.strikecraft_bay_component:
                bay = obj.strikecraft_bay_component
                if bay.replenishing_unit is not None and bay.replenishing_unit not in bay.docked_units:
                    raise ValueError("Replenishment target is not docked in its bay")
    from domain.deployables import CatalystPatch, Deployable
    from domain.celestials import Nebula
    from tactical_abilities import SPECS, deployments, reconcile_links
    for obj, _ in owned:
        if isinstance(obj, CatalystPatch):
            body = objects.get(obj.nebula_id)
            if not isinstance(body, Nebula) or (body.in_system, body.in_hex) != (obj.in_system, obj.in_hex):
                raise ValueError('Invalid catalyst nebula')
        if isinstance(obj, (Deployable, CatalystPatch)):
            source = objects.get(obj.deploying_ship_id)
            if source is not None and not isinstance(source, Unit):
                raise ValueError('Historical deploying ID resolves to a non-unit')
            kind = obj.kind if isinstance(obj, Deployable) else 'nebula_catalyst'
            if len(deployments(galaxy, obj.deploying_ship_id, kind)) > SPECS[kind].cap:
                raise ValueError('Deployment cap exceeded')
    galaxy.game = candidate
    reconcile_links(galaxy)
    from tactical_abilities import start_owner_turn
    for index, player in enumerate(candidate.players):
        start_owner_turn(galaxy, player, candidate.turn_number - int(index > candidate.current_player_index))
    # Restore explicit order bindings only once, after the entire graph exists.
    for obj, _ in list(iter_units(galaxy)):
        sm._restore_saved_commander(obj, candidate)
    candidate.player_homeworlds = {}
    for player in candidate.players:
        if player.homeworld_id is not None:
            body = galaxy.get_celestial_body_by_id(player.homeworld_id)
            if body is None:
                raise ValueError(f"Player {player.id}: homeworld does not exist")
            candidate.player_homeworlds[player] = (body.in_system, body.in_hex, body.position)
    if candidate.current_system_name is not None and candidate.current_system_name not in galaxy.systems:
        raise ValueError("Current view system does not exist")
    if candidate.current_sector_coord is not None:
        system = galaxy.systems.get(candidate.current_system_name)
        if system is None or candidate.current_sector_coord not in system.hexes:
            raise ValueError("Current view sector does not exist")
    candidate.visibility = VisibilityService.compute(galaxy, candidate.players[candidate.current_player_index],
                                                    turn_number=candidate.turn_number, record_intel=False)
    candidate.visibility_dirty = False
    return objects, agents


def _cancel_testing_construction(candidate, warnings):
    """Settle unavailable jobs on the candidate without promoting queued orders."""
    from unit_templates import TESTING_TEMPLATE_KEYS

    for unit, _ in iter_units(candidate.galaxy):
        constructor = unit.constructor_component
        if not constructor or not constructor.current_construction_target:
            continue
        template_name = constructor.current_construction_target[0]
        if template_name not in TESTING_TEMPLATE_KEYS:
            continue
        commander = unit.commander_component
        if commander and commander.current_order:
            active = next((node for node in commander._active_front_chain()
                           if node.public_id == constructor.construction_order_id), None)
            if active is not None:
                # Historical charge reconstruction is not evidence of a recorded payment.
                if active._legacy_charge:
                    active._charged_credits = 0
                commander.cancel_order(commander.current_order.order_id, promote_next=False)
        # Orphaned component jobs have no recorded order charge to refund.
        constructor.cancel_construction()
        warnings.append(f"Cancelled unavailable Testing construction {template_name} on {unit.name}; "
                        "any recorded payment was refunded.")


def prepare_campaign(data):
    import save_manager as sm
    from save_migrations import migrate_save
    from domain.communications import Conversation
    from unit_orders.base import Order
    validate_json(data)
    with isolated_allocations() as allocations:
        data, warnings = migrate_save(data)
        validate_document(data)
        info = data["game_state"]
        candidate = SimpleNamespace(**{name: info[name] for name in
            ("turn_number", "current_player_index", "view_mode", "current_system_name", "campaign_id", "message_counter")})
        candidate.current_sector_coord = tuple(info["current_sector_coord"]) if info["current_sector_coord"] is not None else None
        candidate.galaxy = None
        candidate.game_started = True
        candidate._loading = True
        candidate.deselect_object = lambda obj: None
        candidate.players = [sm.deserialize_player(p) for p in data["players"]]
        candidate.conversations = {}
        player_ids = {p.id for p in candidate.players}
        message_ids = set()
        for raw in data["conversations"]:
            conv = Conversation.from_dict(raw)
            if conv.participant_ids in candidate.conversations or len(set(conv.participant_ids)) != 2 or not set(conv.participant_ids) <= player_ids:
                raise ValueError("Invalid/duplicate conversation participants")
            for message in conv.messages:
                number(message.id, "message.id", 0, integer=True)
                if message.id in message_ids or {message.sender_id, message.recipient_id} != set(conv.participant_ids):
                    raise ValueError("Invalid/duplicate message ID or participants")
                message_ids.add(message.id)
            candidate.conversations[conv.participant_ids] = conv
        candidate.message_counter = max(info["message_counter"], max(message_ids, default=0))
        candidate.galaxy = sm.deserialize_galaxy(data["galaxy"], {p.id: p for p in candidate.players}, candidate)
        objects, agents = reconcile(candidate)
        _cancel_testing_construction(candidate, warnings)
        return PreparedCampaign(candidate,
            max(info["object_counter"], max(objects, default=0) + 1, max((getattr(obj, "deploying_ship_id", 0) for obj in objects.values()), default=0) + 1),
            max(info["player_counter"], max(player_ids, default=-1) + 1),
            max(info["agent_counter"], max(agents, default=-1) + 1),
            allocations.get((Order, "order_counter"), 0), warnings)


def commit_campaign(game, prepared):
    """One callback-free commit. GUI/AI integration belongs to Game.load_game."""
    from domain.identity import GameObject
    from domain.players import Player
    from unit_components.intelligence import Agent
    from unit_orders.base import Order
    from unit_templates import publish_testing_templates
    candidate = prepared.state
    for unit, _ in iter_units(candidate.galaxy):
        unit.game = game
    fields = {key: value for key, value in vars(candidate).items() if key not in ("_loading", "deselect_object")}
    fields.update(selected_objects=[], hovered_object=None, sector_view_mouse_hover_object=None,
                  galaxy_view_mouse_hover_system_name=None, system_view_mouse_hover_hex=None,
                  selected_component_name=None, selected_unit_tab="basic_info", pending_ai_turn_end_time=0,
                  is_dragging_selection_box=False, selection_box_start_pos=None,
                  pending_ability=None, load_warnings=prepared.warnings)
    game.__dict__.update(fields)
    publish_testing_templates(prepared.testing_templates)
    game.galaxy.game = game
    GameObject.object_counter = prepared.object_counter
    Player.player_counter = prepared.player_counter
    Agent.agent_counter = prepared.agent_counter
    Order.order_counter = max(Order.order_counter, prepared.order_counter)
