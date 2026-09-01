"""Game state bootstrap and starting fleet setup."""
import logging
import random
import typing
import uuid

from constants import BLUE, RED, YELLOW, PlanetType
from entities import Player, Planet, Star, Wormhole
from galaxy import Galaxy, StarSystem
from geometry import Position
from game_ai.runtime import DEFAULT_REASONING_EFFORT, DEFAULT_REPAIR_RETRIES
from unit_components import instantiate_unit_from_template
from utils import HexCoord, generate_short_id
from game_settings import GameSettings, SpawnProfile, normalize_spawn_profile, _default_player_configs

logger = logging.getLogger(__name__)


def _select_starting_systems(galaxy_systems: typing.Dict[str, StarSystem], count: int) -> typing.List[StarSystem]:
    """Selects `count` well-distributed starting systems across the galaxy."""
    systems_list = list(galaxy_systems.values())
    if len(systems_list) <= count:
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


def start_new_game(game, settings: typing.Optional['GameSettings'] = None) -> bool:
    """Initializes a new game when the New Game button is clicked.

    Args:
        game: Target game instance.
        settings: Optional :class:`GameSettings` produced by the New Game Wizard.
            When *None*, the current defaults are used.

    Returns:
        bool: True if initialization succeeded, False otherwise.
    """
    if settings is None:
        settings = GameSettings()

    game.settings = settings
    logger.debug(f"Starting new game setup with spawn profile: {settings.spawn_profile.value}...")
    if hasattr(game, 'ai_coordinator'):
        game.ai_coordinator.reset()
    game.campaign_id = generate_short_id()

    # Set up game UI first to ensure galaxy_generation_rect is defined before galaxy generation
    game.gui.show_game_ui()

    # Generate galaxy using settings parameters
    try:
        game.galaxy = Galaxy(num_systems=settings.num_systems, settings=settings)
        if not game.galaxy.systems:
            logger.debug("Warning: Galaxy generated with no systems.")
            return False
    except Exception as e:
        logger.debug(f"Error during Galaxy generation: {e}")
        return False

    # Add Players from settings
    game.players = [
        Player(
            cfg.name,
            cfg.color,
            controller=cfg.controller,
            team_id=cfg.team_id,
            ai_reasoning_effort=getattr(
                cfg, "ai_reasoning_effort", DEFAULT_REASONING_EFFORT
            ),
            ai_repair_retries=getattr(
                cfg, "ai_repair_retries", DEFAULT_REPAIR_RETRIES
            ),
        )
        for cfg in settings.player_configs
    ]

    game.current_player_index = 0
    game.turn_number = 1

    # Track homeworld info per player: mapping of Player -> (system_name, hex_coord, position)
    player_homeworlds: typing.Dict[Player, typing.Tuple[str, HexCoord, Position]] = {}

    if settings.spawn_profile == SpawnProfile.NORMAL:
        # Each player receives their own distinct star system
        starting_systems = _select_starting_systems(game.galaxy.systems, len(game.players))
        for i, player in enumerate(game.players):
            target_sys = starting_systems[i % len(starting_systems)]
            all_bodies = [body for _, body in target_sys.get_all_celestial_bodies()]
            planets = [body for body in all_bodies if isinstance(body, Planet)]
            if planets:
                homeworld = random.choice(planets)
            else:
                # Spawn a habitable planet in an available non-star, non-wormhole hex
                candidate_hexes = [
                    coord for coord, h in target_sys.hexes.items()
                    if coord != (0, 0) and not any(isinstance(b, (Star, Wormhole)) for b in h.celestial_bodies)
                ]
                hw_hex = random.choice(candidate_hexes) if candidate_hexes else (1, 0)
                if hw_hex not in target_sys.hexes:
                    hw_hex = next((c for c in target_sys.hexes if c != (0, 0)), (0, 0))
                homeworld = Planet(in_hex=hw_hex, in_system=target_sys.name, planet_type=PlanetType.TERRAN)
                target_sys.add_celestial_body(homeworld)
                if hw_hex in target_sys.hexes:
                    target_sys.hexes[hw_hex].update_static_inhibition_zones()

            homeworld.owner = player
            homeworld.population = settings.starting_population
            player_homeworlds[player] = (target_sys.name, homeworld.in_hex, homeworld.position)
            logger.debug(f"Assigned {homeworld.name} in {homeworld.in_system} at hex {homeworld.in_hex} as homeworld for {player.name}")

    else:
        # Testing profile: All players spawn in the same system (Sol or first available system)
        sol_system = game.galaxy.systems.get('Sol')
        if not sol_system and game.galaxy.systems:
            sol_system = next(iter(game.galaxy.systems.values()))

        if sol_system:
            all_bodies = [body for _, body in sol_system.get_all_celestial_bodies()]
            sol_planets = [body for body in all_bodies if isinstance(body, Planet)]
            random.shuffle(sol_planets)
        else:
            sol_planets = []
            logger.debug("Warning: No systems available for homeworld assignment.")

        for player in game.players:
            if sol_system:
                if sol_planets:
                    homeworld = sol_planets.pop()
                else:
                    candidate_hexes = [
                        coord for coord, h in sol_system.hexes.items()
                        if coord != (0, 0) and not any(isinstance(b, (Star, Wormhole, Planet)) for b in h.celestial_bodies)
                    ]
                    hw_hex = random.choice(candidate_hexes) if candidate_hexes else (1, 0)
                    if hw_hex not in sol_system.hexes:
                        hw_hex = next((c for c in sol_system.hexes if c != (0, 0)), (0, 0))
                    homeworld = Planet(in_hex=hw_hex, in_system=sol_system.name, planet_type=PlanetType.TERRAN)
                    sol_system.add_celestial_body(homeworld)
                    if hw_hex in sol_system.hexes:
                        sol_system.hexes[hw_hex].update_static_inhibition_zones()

                homeworld.owner = player
                homeworld.population = settings.starting_population
                player_homeworlds[player] = (sol_system.name, homeworld.in_hex, homeworld.position)
                logger.debug(f"Assigned {homeworld.name} in {homeworld.in_system} at hex {homeworld.in_hex} as homeworld for {player.name}")

    # Apply starting resources from settings
    for player in game.players:
        player.credits = settings.starting_credits
        player.metal = settings.starting_metal
        player.crystal = settings.starting_crystal

    # Set up starting units
    spawn_units(game, player_homeworlds=player_homeworlds, spawn_profile=settings.spawn_profile)

    # Change view mode and set up game UI
    game.view_mode = 'galaxy'
    game.game_started = True
    game.visibility = None
    game.visibility_dirty = True
    game.recompute_visibility()
    game.update_side_bar_content()  # Update info box for initial state
    game.update_player_turn_display()  # Update turn display for Player 1
    logger.debug(f"--- Turn {game.turn_number} - Start of {game.players[game.current_player_index].name}'s Turn ---")
    if hasattr(game, 'check_and_schedule_ai_turn'):
        game.check_and_schedule_ai_turn()
    logger.debug("New game setup complete.\n")
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

