"""Game state bootstrap and starting fleet setup."""
import logging
import random
import typing
import copy
from types import SimpleNamespace

from constants import PlanetType
from domain.players import Player
from domain.celestials import Planet, Star, Wormhole
from galaxy import Galaxy, StarSystem
from geometry import Position
from unit_components.constructor import instantiate_unit_from_template
from domain.coordinates import HexCoord
from utils import generate_short_id
from game_settings import GameSettings, SpawnProfile, normalize_spawn_profile, validate_start_conditions

logger = logging.getLogger(__name__)


def _select_starting_systems(galaxy_systems: typing.Dict[str, StarSystem], count: int) -> typing.List[StarSystem]:
    """Selects `count` well-distributed starting systems across the galaxy."""
    systems_list = list(galaxy_systems.values())
    if count < 0 or count > len(systems_list):
        raise ValueError("Not enough unclaimed systems for distinct Normal starts")
    if count == 0:
        return []
    if len(systems_list) == count:
        return systems_list

    # Farthest-point sampling to distribute player starting positions across the galaxy
    selected = [random.choice(systems_list)]
    while len(selected) < count:
        best_sys = None
        best_min_dist = -1.0
        for candidate in systems_list:
            if candidate in selected:
                continue
            min_dist = min(
                (candidate.position.x - s.position.x) ** 2 + (candidate.position.y - s.position.y) ** 2
                for s in selected
            )
            if min_dist > best_min_dist:
                best_min_dist = min_dist
                best_sys = candidate
        if best_sys:
            selected.append(best_sys)
        else:
            break
    return selected


def _homeworld(system, player, population):
    """Select a usable world or create a Terran world in an empty sector."""
    planets = [body for _, body in system.get_all_celestial_bodies()
               if isinstance(body, Planet) and body.owner is None and body.is_colonizable]
    if planets:
        world = random.choice(planets)
    else:
        available = [coord for coord, sector in system.hexes.items()
                     if coord != (0, 0) and not sector.celestial_bodies and not sector.units]
        if not available:
            raise ValueError(f"No valid homeworld placement is available in {system.name}.")
        world = Planet(random.choice(available), system.name, PlanetType.TERRAN)
        system.add_celestial_body(world)
        system.hexes[world.in_hex].update_static_inhibition_zones()
    world.owner = player
    world.population = min(population, world.max_population)
    player.homeworld_id = world.id
    return world


def prepare_new_campaign(settings):
    """Build and validate an isolated campaign; never invoke live GUI or AI code."""
    from campaign_graph import iter_objects, iter_units
    from campaign_persistence import PreparedCampaign, reconcile
    from persistence_context import isolated_allocations
    from domain.identity import GameObject
    from unit_components.intelligence import Agent
    from unit_orders.base import Order

    errors = settings.validate()
    if errors:
        raise ValueError("; ".join(errors))
    settings = copy.copy(settings)
    settings.player_configs = copy.deepcopy(settings.player_configs)
    for config in settings.player_configs:
        config.__post_init__()
    settings.spawn_profile = normalize_spawn_profile(settings.spawn_profile)
    with isolated_allocations() as allocations:
        allocations[(GameObject, 'object_counter')] = 1
        galaxy = (copy.deepcopy(settings.pregenerated_galaxy) if settings.pregenerated_galaxy is not None
                  else Galaxy(num_systems=settings.num_systems, settings=settings))
        errors = validate_start_conditions(settings, galaxy)
        if errors:
            raise ValueError("; ".join(errors))
        allocations[(GameObject, 'object_counter')] = max(
            allocations[(GameObject, 'object_counter')],
            max((obj.id for obj, _ in iter_objects(galaxy)), default=0) + 1)
        settings.pregenerated_galaxy = None
        candidate = SimpleNamespace(
            settings=settings, galaxy=galaxy, players=[], campaign_id=generate_short_id(),
            current_player_index=0, turn_number=1, view_mode='galaxy', game_started=True,
            current_system_name=None, current_sector_coord=None, conversations={}, message_counter=0,
            visibility=None, visibility_dirty=True, selected_objects=[], _loading=True,
            deselect_object=lambda obj: None)
        candidate.players = [Player(cfg.name, cfg.color, controller=cfg.controller, team_id=cfg.team_id,
                                    ai_reasoning_effort=cfg.ai_reasoning_effort,
                                    ai_repair_retries=cfg.ai_repair_retries) for cfg in settings.player_configs]
        if not candidate.players:
            raise ValueError("A campaign requires players.")
        specified = {i: galaxy.systems[cfg.home_system_name] for i, cfg in enumerate(settings.player_configs)
                     if cfg.home_system_name and cfg.home_system_name.lower() != 'random'}
        if settings.spawn_profile == SpawnProfile.NORMAL:
            unclaimed = {name: system for name, system in galaxy.systems.items() if system not in specified.values()}
            random_systems = iter(_select_starting_systems(unclaimed, len(candidate.players) - len(specified)))
        else:
            shared = galaxy.systems.get('Sol') or next(iter(galaxy.systems.values()))
        homes = {}
        for i, player in enumerate(candidate.players):
            system = specified.get(i)
            if system is None:
                system = next(random_systems) if settings.spawn_profile == SpawnProfile.NORMAL else shared
            world = _homeworld(system, player, settings.starting_population)
            homes[player] = (system.name, world.in_hex, world.position)
            player.credits, player.metal, player.crystal = settings.starting_credits, settings.starting_metal, settings.starting_crystal
        candidate.player_homeworlds = homes
        spawn_units(candidate, player_homeworlds=homes, spawn_profile=settings.spawn_profile)
        expected_units = 4 if settings.spawn_profile == SpawnProfile.NORMAL else 11
        for player in candidate.players:
            world = galaxy.get_celestial_body_by_id(player.homeworld_id)
            if world is None or world.owner is not player or not world.is_colonizable or not 0 <= world.population <= world.max_population:
                raise ValueError(f"Invalid homeworld for {player.name}.")
            if sum(unit.owner is player for unit, _ in iter_units(galaxy)) != expected_units:
                raise ValueError(f"Could not create the complete starter fleet for {player.name}.")
        objects, agents = reconcile(candidate)
        return PreparedCampaign(candidate,
            max(objects, default=0) + 1,
            allocations.get((Player, 'player_counter'), 0),
            max(allocations.get((Agent, 'agent_counter'), 0), max(agents, default=-1) + 1),
            allocations.get((Order, 'order_counter'), 0), [])


def start_new_game(game, settings: typing.Optional['GameSettings'] = None) -> bool:
    """Prepare a complete campaign before committing; failed setup preserves live play."""
    from campaign_persistence import commit_campaign
    try:
        prepared = prepare_new_campaign(settings if settings is not None else GameSettings())
    except Exception as exc:
        logger.exception("Could not prepare new campaign")
        game.last_setup_error = str(exc)
        return False
    commit_campaign(game, prepared)
    game.last_setup_error = None
    # As with loading, a presentation failure cannot reject an already committed campaign.
    try:
        if hasattr(game, 'ai_coordinator'):
            game.ai_coordinator.reset()
    except Exception:
        logger.exception("Campaign started, but AI reset failed")
    try:
        game.gui.show_game_ui()
        game.recompute_visibility()
        game.update_side_bar_content()
        game.update_player_turn_display()
    except Exception:
        logger.exception("Campaign started, but presentation refresh failed")
    try:
        if hasattr(game, 'check_and_schedule_ai_turn'):
            game.check_and_schedule_ai_turn()
    except Exception:
        logger.exception("Campaign started, but AI scheduling failed")
    return True


def spawn_units(
    game,
    player_homeworlds: typing.Optional[typing.Any] = None,
    spawn_profile: typing.Optional[SpawnProfile] = None,
) -> None:
    """Sets up the starting units of all players.

    Args:
        game: Target game instance.
        player_homeworlds: Mapping of Player -> homeworld information. Accepts
            dict of Player -> HexCoord (legacy), Player -> (system_name, hex_coord, position),
            or Player -> Planet.
        spawn_profile: The spawn profile to use (NORMAL or TESTING). When *None*,
            inferred from game settings or defaults to NORMAL.
    """
    logger.debug("Spawning units...")
    if not game.galaxy or not game.galaxy.systems:
        logger.debug("Cannot set up initial state: No galaxy or systems exist.")
        return

    if spawn_profile is None:
        if hasattr(game, 'settings') and game.settings and hasattr(game.settings, 'spawn_profile'):
            spawn_profile = normalize_spawn_profile(game.settings.spawn_profile)
        else:
            spawn_profile = SpawnProfile.NORMAL
    else:
        spawn_profile = normalize_spawn_profile(spawn_profile)

    if player_homeworlds is None:
        player_homeworlds = {}

    default_system_name = 'Sol' if 'Sol' in game.galaxy.systems else next(iter(game.galaxy.systems.keys()))

    for player in game.players:
        hw_info = player_homeworlds.get(player)
        target_system_name = default_system_name
        spawn_hex = None
        planet_pos = Position(0.0, 0.0)

        if isinstance(hw_info, tuple):
            if len(hw_info) == 3:
                target_system_name, spawn_hex, planet_pos = hw_info
            elif len(hw_info) == 2:
                if isinstance(hw_info[0], str):
                    target_system_name, spawn_hex = hw_info
                else:
                    # Legacy (q, r) HexCoord tuple
                    spawn_hex = hw_info
            elif len(hw_info) == 1:
                spawn_hex = hw_info[0]
        elif isinstance(hw_info, Planet):
            target_system_name = hw_info.in_system
            spawn_hex = hw_info.in_hex
            planet_pos = hw_info.position

        target_system = game.galaxy.systems.get(target_system_name)
        if not target_system:
            target_system = next(iter(game.galaxy.systems.values()))

        # Determine spawn hex if not valid
        if spawn_hex is None or spawn_hex not in target_system.hexes:
            fallback_hexes = [
                coord for coord, h in target_system.hexes.items()
                if not any(isinstance(body, (Star, Wormhole)) for body in h.celestial_bodies)
            ]
            if fallback_hexes:
                spawn_hex = random.choice(fallback_hexes)
            else:
                spawn_hex = next((c for c in target_system.hexes if c != (0, 0)), (0, 0))

        logger.debug(f"Spawning units for {player.name} in hex {spawn_hex} of {target_system.name} (profile: {spawn_profile.value})")

        if spawn_profile == SpawnProfile.NORMAL:
            # Normal profile starter units:
            # 1. Starting Constructor Station in orbit around homeworld
            # 2. Constructor Ship
            # 3. Colonizer Ship
            # 4. Antimatter Harvester Ship
            normal_spawn_entries = [
                ("SHIPYARD_MK1", planet_pos.x, planet_pos.y - 650.0),
                ("CONSTRUCTOR_MK1", planet_pos.x - 250.0, planet_pos.y - 750.0),
                ("COLONIZER_MK1", planet_pos.x + 250.0, planet_pos.y - 750.0),
                ("ANTIMATTER_HARVESTER", planet_pos.x, planet_pos.y - 900.0),
            ]

            for template_key, x_pos, y_pos in normal_spawn_entries:
                instantiate_unit_from_template(
                    template_name=template_key,
                    owner=player,
                    system_name=target_system.name,
                    hex_coord=spawn_hex,
                    position=Position(x_pos, y_pos),
                    galaxy=game.galaxy,
                    game=game,
                )
                hex_obj = target_system.hexes.get(spawn_hex)
                if hex_obj and hex_obj.units:
                    spawned = hex_obj.units[-1]
                    spawned.name = f"{player.name} {spawned.name}"
                    logger.debug(f"Added {spawned.name} to {target_system.name} at {spawn_hex} for {player.name}")

        else:
            # Testing profile: Full complement of ships, stations, and carrier
            hull_names = ["TINY", "SMALL", "MEDIUM", "LARGE", "HUGE"]
            testing_spawn_entries: typing.List[typing.Tuple[str, float, float]] = []
            for i, hull in enumerate(hull_names):
                x = -500.0 + i * 200.0
                testing_spawn_entries.append((f"SPAWN_SHIP_{hull}", x, -1300.0))
                testing_spawn_entries.append((f"SPAWN_STATION_{hull}", x, -1100.0))
            testing_spawn_entries.append(("SPAWN_CARRIER", -500.0 + 5 * 200.0, -1200.0))

            for template_key, x_off, y_off in testing_spawn_entries:
                instantiate_unit_from_template(
                    template_name=template_key,
                    owner=player,
                    system_name=target_system.name,
                    hex_coord=spawn_hex,
                    position=Position(x_off, y_off),
                    galaxy=game.galaxy,
                    game=game,
                )
                hex_obj = target_system.hexes.get(spawn_hex)
                if hex_obj and hex_obj.units:
                    spawned = hex_obj.units[-1]
                    spawned.name = f"{player.name} {spawned.name}"
                    logger.debug(f"Added {spawned.name} to {target_system.name} at {spawn_hex} for {player.name}")

