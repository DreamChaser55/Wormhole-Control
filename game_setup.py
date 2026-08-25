"""Game state bootstrap and starting fleet setup."""
import logging
import random
import typing
import uuid

from constants import BLUE, RED, YELLOW
from entities import Player, Planet, Star, Wormhole
from galaxy import Galaxy, StarSystem
from geometry import Position
from unit_components import instantiate_unit_from_template
from utils import HexCoord
from game_settings import GameSettings, _default_player_configs

logger = logging.getLogger(__name__)


def start_new_game(game, settings: typing.Optional['GameSettings'] = None) -> bool:
    """Initializes a new game when the New Game button is clicked.

    Args:
        game: Target game instance.
        settings: Optional :class:`GameSettings` produced by the New Game Wizard.
            When *None*, default settings are used for backwards compatibility.

    Returns:
        bool: True if initialization succeeded, False otherwise.
    """
    if settings is None:
        settings = GameSettings()

    logger.debug("Starting new game setup...")
    if hasattr(game, 'ai_coordinator'):
        game.ai_coordinator.reset()
    game.campaign_id = str(uuid.uuid4())

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
            is_human=cfg.is_human,
            team_id=cfg.team_id,
            ai_profile=getattr(cfg, "ai_profile", "balanced"),
        )
        for cfg in settings.player_configs
    ]

    game.current_player_index = 0
    game.turn_number = 1

    # Assign homeworlds and track their hex locations
    player_homeworld_hexes: typing.Dict[Player, HexCoord] = {}
    sol_system = game.galaxy.systems.get('Sol')
    if sol_system:
        all_bodies = [body for hex_coord, body in sol_system.get_all_celestial_bodies()]
        sol_planets = [body for body in all_bodies if isinstance(body, Planet)]
        random.shuffle(sol_planets)
    else:
        sol_planets = []
        logger.debug("Warning: Sol system not found for homeworld assignment.")

    for player in game.players:
        if sol_planets:
            homeworld = sol_planets.pop()
            homeworld.owner = player
            homeworld.population = settings.starting_population
            player_homeworld_hexes[player] = homeworld.in_hex
            logger.debug(f"Assigned {homeworld.name} in {homeworld.in_system} at hex {homeworld.in_hex} as homeworld for {player.name}")
        else:
            logger.debug(f"Warning: Not enough planets in Sol to assign a homeworld for {player.name}")

    # Apply starting resources from settings
    for player in game.players:
        player.credits = settings.starting_credits
        player.metal = settings.starting_metal
        player.crystal = settings.starting_crystal

    # Set up starting units
    spawn_units(game, player_homeworld_hexes)

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


def spawn_units(game, player_homeworld_hexes: typing.Optional[typing.Dict[Player, HexCoord]] = None) -> None:
    """Sets up the starting units of all players.

    All units for a given player spawn in the same hex sector as their
    homeworld planet, clustered with fixed offsets for visual spread.
    Units are defined by templates in ``data/unit_templates.json`` with the
    ``SPAWN_`` prefix and instantiated via
    :func:`~unit_components.constructor.instantiate_unit_from_template`.

    Args:
        game: Target game instance.
        player_homeworld_hexes: Optional mapping of Player -> HexCoord indicating
            each player's homeworld hex. Units will spawn in this hex.
    """
    logger.debug("Spawning units...")
    if not game.galaxy or not game.galaxy.systems:
        logger.debug("Cannot set up initial state: No galaxy or systems exist.")
        return

    if player_homeworld_hexes is None:
        player_homeworld_hexes = {}

    target_system: typing.Optional[StarSystem] = None
    target_system_name = 'Sol'
    if target_system_name in game.galaxy.systems:
        target_system = game.galaxy.systems[target_system_name]
    else:
        if game.galaxy.systems:
            target_system = next(iter(game.galaxy.systems.values()))
        else:
            logger.debug("Error: No systems available to place starting units.")
            return
    logger.debug(f"Target system for starting units: {target_system.name}")

    # (template_key, x_offset, y_offset)
    # Ships and stations are paired column-by-column (index 0..4 for TINY..HUGE).
    # The carrier sits in column 5 between the ship and station rows.
    hull_names = ["TINY", "SMALL", "MEDIUM", "LARGE", "HUGE"]
    spawn_entries: typing.List[typing.Tuple[str, float, float]] = []
    for i, hull in enumerate(hull_names):
        x = -500.0 + i * 200.0
        spawn_entries.append((f"SPAWN_SHIP_{hull}", x, -1300.0))
        spawn_entries.append((f"SPAWN_STATION_{hull}", x, -1100.0))
    spawn_entries.append(("SPAWN_CARRIER", -500.0 + 5 * 200.0, -1200.0))

    for player in game.players:
        # Determine spawn hex: use homeworld hex if available, otherwise fallback
        spawn_hex = player_homeworld_hexes.get(player)
        if spawn_hex is None or spawn_hex not in target_system.hexes:
            fallback_hexes = [
                coord for coord, h in target_system.hexes.items()
                if not any(isinstance(body, (Star, Wormhole)) for body in h.celestial_bodies)
            ]
            if fallback_hexes:
                spawn_hex = random.choice(fallback_hexes)
                logger.debug(f"Warning: No homeworld hex for {player.name}, using fallback hex {spawn_hex}")
            else:
                logger.debug(f"Warning: No valid hex found for {player.name}'s units in {target_system.name}!")
                continue

        logger.debug(f"Spawning all units for {player.name} in hex {spawn_hex} of {target_system.name}")

        for template_key, x_off, y_off in spawn_entries:
            instantiate_unit_from_template(
                template_name=template_key,
                owner=player,
                system_name=target_system.name,
                hex_coord=spawn_hex,
                position=Position(x_off, y_off),
                galaxy=game.galaxy,
                game=game,
            )
            # Personalise the unit name to include the owning player's name.
            # The unit was just appended as the last entry in the hex.
            hex_obj = target_system.hexes.get(spawn_hex)
            if hex_obj and hex_obj.units:
                spawned = hex_obj.units[-1]
                spawned.name = f"{player.name} {spawned.name}"
                logger.debug(f"Added {spawned.name} to {target_system.name} at {spawn_hex} for {player.name}")
