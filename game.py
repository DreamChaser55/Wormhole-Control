import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler("game.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

import os
import ctypes
import pygame
import sys
import random
import typing
import math
from pygame import Color

# Import from local modules
from constants import (
    SCREEN_RES, STATION_ICON_SIZE, SHIP_ICON_SIZE,
    DEFAULT_SUBLIGHT_SHIP_SPEED, RED, BLUE, YELLOW, DEBUG, PROFILE
)
from utils import HexCoord, Timer
from geometry import (
    Position, Vector, distance_sq, distance
)
from hexgrid_utils import hex_to_pixel, pixel_to_hex, get_hex_vertices
from sector_utils import move_towards_position, sector_coords_to_pixels, pixels_to_sector_coords, random_point_in_sector
from entities import Player, GameObject, CelestialBody, Unit, Star, Planet, Wormhole, Moon, Asteroid, HullSize
from unit_components import Engines, Hyperdrive, HyperdriveType, Commander, JumpStatus, Turret, TurretType, Weapons, HyperspaceInhibitionFieldEmitter, Constructor, ColonyComponent, RepairComponent, HangarComponent, FighterBayComponent, FighterWingComponent
from events import (
    CancelOrdersEvent, IssueMoveOrderEvent, IssuePatrolOrderEvent, JumpInterhexEvent, JumpWormholeEvent,
    AttackUnitEvent, ColonizeEvent, LoadColonistsEvent, ConstructEvent, RepairUnitEvent,
    MineEvent, UnloadResourcesEvent, DockEvent, UseAbilityEvent
)
from entities import Order, AsteroidField, DebrisField, IceField, Nebula, Storm, Comet, Moon
from galaxy import Galaxy, StarSystem, Hex
from gui import GUI_Handler
from renderer import Renderer
from input_processor import InputProcessor
from turn_processor import TurnProcessor
from events import EventBus
from order_system import OrderSystem
from custom_unit_templates import CustomTemplateManager

# --- Game Class ---
class Game:
    """Main game class, handles initialization, game loop, drawing, and input."""
    def __init__(self):
        # Disable Windows OS window scaling to ensure 1:1 pixel perfect resolution
        if os.name == 'nt':
            try:
                # Windows 8.1 and later
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                try:
                    # Windows Vista and later
                    ctypes.windll.user32.SetProcessDPIAware()
                except Exception:
                    pass

        pygame.init()
        pygame.display.set_caption("Wormhole Control")
        self.screen = pygame.display.set_mode(SCREEN_RES.to_tuple())
        self.clock = pygame.time.Clock()
        
        # Instantiate the GUI Handler
        self.gui = GUI_Handler(SCREEN_RES, self)

        # Game State - Controls the current game status and view context
        self.is_running = True  # Controls the main game loop
        self.view_mode = 'main_menu'  # Valid modes: 'main_menu', 'galaxy', 'system', 'sector'
        self.game_started = False  # Set to True after starting a new game
        self.current_system_name: typing.Optional[str] = None  # Name of currently viewed star system
        self.current_sector_coord: typing.Optional[HexCoord] = None  # Hex coordinates of the sector being viewed

        # UI State / Selections - Tracks current user interactions with game objects
        self.selected_objects: typing.List[typing.Any] = [] # List of all selected game objects
        self.hovered_object: typing.Optional[typing.Any] = None  # Object directly under mouse cursor
        self.is_dragging_selection_box = False
        self.selection_box_start_pos = None
        
        # View-specific hover tracking
        self.galaxy_view_mouse_hover_system_name: typing.Optional[str] = None
        self.system_view_mouse_hover_hex: typing.Optional[HexCoord] = None
        self.sector_view_mouse_hover_object: typing.Any = None

        # Initialize empty galaxy and players - will be created after New Game is clicked
        self.galaxy = None
        self.players: typing.List[Player] = []
        self.current_player_index = 0

        # Alpha Surface for drawing overlays (highlights and order lines)
        self.overlay_surface = pygame.Surface(SCREEN_RES.to_tuple(), pygame.SRCALPHA)

        # Instantiate the Renderer
        self.renderer = Renderer(self)

        # Initialize Event Bus and Order System
        self.event_bus = EventBus()
        self.order_system = OrderSystem(self, self.event_bus)

        # Instantiate the InputProcessor
        self.input_processor = InputProcessor(self)

        # Instantiate the TurnProcessor
        self.turn_manager = TurnProcessor(self)

        # Initialize the main menu UI
        self.gui.show_main_menu()
        self.sidebar_needs_update: bool = True
        self.pending_ai_turn_end_time: int = 0
        self.selected_component_name: typing.Optional[str] = None

        # Pending ability activation state (when targeting mode is active)
        # Holds (ability_type_str, requires_target_unit, requires_target_position)
        self.pending_ability: typing.Optional[typing.Tuple[str, bool, bool]] = None

        # Custom unit template manager (persists designs across sessions)
        self.custom_template_manager = CustomTemplateManager()
        self.custom_template_manager.load_from_file()

    def start_new_game(self):
        """Initializes a new game when the New Game button is clicked."""
        logger.debug("Starting new game setup...")

        # Set up game UI first to ensure galaxy_generation_rect is defined before galaxy generation
        self.gui.show_game_ui()

        # Generate galaxy using logical coordinates
        try:
            self.galaxy = Galaxy()
            if not self.galaxy.systems:
                logger.debug("Warning: Galaxy generated with no systems.")
                return False
        except Exception as e:
            logger.debug(f"Error during Galaxy generation: {e}")
            return False

        # Add Players
        self.players = [
            Player("Player 1", BLUE, is_human=True),
            Player("Player 2", RED, is_human=True),
            Player("Player 3", YELLOW, is_human=True)
        ]

        self.current_player_index = 0

        # Assign homeworlds and track their hex locations
        player_homeworld_hexes: typing.Dict[Player, HexCoord] = {}
        sol_system = self.galaxy.systems.get('Sol')
        if sol_system:
            all_bodies = [body for hex_coord, body in sol_system.get_all_celestial_bodies()]
            sol_planets = [body for body in all_bodies if isinstance(body, Planet)]
            random.shuffle(sol_planets)
        else:
            sol_planets = []
            logger.debug("Warning: Sol system not found for homeworld assignment.")

        for player in self.players:
            if sol_planets:
                homeworld = sol_planets.pop()
                homeworld.owner = player
                homeworld.population = 50  # Starting population
                player_homeworld_hexes[player] = homeworld.in_hex
                logger.debug(f"Assigned {homeworld.name} in {homeworld.in_system} at hex {homeworld.in_hex} as homeworld for {player.name}")
            else:
                logger.debug(f"Warning: Not enough planets in Sol to assign a homeworld for {player.name}")

        # Set up starting units
        self.spawn_units(player_homeworld_hexes)

        # Change view mode and set up game UI
        self.view_mode = 'galaxy'
        self.game_started = True
        self.update_side_bar_content() # Update info box for initial state
        self.update_player_turn_display() # Update turn display for Player 1
        logger.debug("New game setup complete.\n")
        return True

    def spawn_units(self, player_homeworld_hexes: typing.Dict[Player, HexCoord] = None):
        """Sets up the starting units of all players.

        All units for a given player spawn in the same hex sector as their
        homeworld planet, clustered with random positions for visual spread.

        Each player receives the following units in the 'Sol' system:
        - One ship per hull size (TINY–LARGE): Engines + Hyperdrive + Weapons
        - One station per hull size (TINY–LARGE): Weapons (MEDIUM also gets Inhibitor)
        - One Huge Ship (HUGE): Engines + Hyperdrive + Weapons + Constructor
            (builds STATION_MK1, REPAIR_STATION_SMALL, SHIPYARD_MK1)
            + ColonyComponent + RepairComponent
        - One Huge Station (HUGE): Weapons + Constructor
            (builds CONSTRUCTOR_MK1, BATTLESHIP_TINY, BATTLESHIP_SMALL,
             BATTLESHIP_MEDIUM, REPAIR_SHIP_SMALL, METAL_REFINERY_STATION,
             CRYSTAL_REFINERY_STATION)
            + RepairComponent

        Args:
            player_homeworld_hexes: Optional mapping of Player -> HexCoord indicating
                each player's homeworld hex. Units will spawn in this hex.
        """
        logger.debug("Spawning units...")
        if not self.galaxy or not self.galaxy.systems:
             logger.debug("Cannot set up initial state: No galaxy or systems exist.")
             return

        if player_homeworld_hexes is None:
            player_homeworld_hexes = {}

        target_system: typing.Optional[StarSystem] = None
        target_system_name = 'Sol'
        if target_system_name in self.galaxy.systems:
            target_system = self.galaxy.systems[target_system_name]
        else:
            if self.galaxy.systems:
                target_system = next(iter(self.galaxy.systems.values()))
            else:
                logger.debug("Error: No systems available to place starting units.")
                return
        logger.debug(f"Target system for starting units: {target_system.name}")

        all_hull_sizes = [h for h in HullSize if h != HullSize.STRIKECRAFT_WING]

        # Spawn units for all players
        for player in self.players:
            # Determine spawn hex: use homeworld hex if available, otherwise fallback
            spawn_hex = player_homeworld_hexes.get(player)
            if spawn_hex is None or spawn_hex not in target_system.hexes:
                # Fallback: pick a random hex that doesn't contain a Star or Wormhole
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

            # --- Spawn Ship & Station for every hull size ---
            for i, hull_size in enumerate(all_hull_sizes):

                # -- Ship --
                ship_pos = Position(-500.0 + i * 200.0, -100.0)
                ship_name = f"{player.name} {hull_size.name.capitalize()} Ship"
                ship_unit = Unit(
                    owner=player,
                    position=ship_pos,
                    in_hex=spawn_hex,
                    in_system=target_system.name,
                    name=ship_name,
                    hull_size=hull_size,
                    game=self
                )
                ship_unit.add_component(Engines(ship_unit, speed=DEFAULT_SUBLIGHT_SHIP_SPEED, hull_cost=5))
                if hull_size == HullSize.TINY:
                    ship_unit.add_component(Hyperdrive(ship_unit, drive_type=HyperdriveType.BASIC, hull_cost=5))
                else:
                    ship_unit.add_component(Hyperdrive(ship_unit, drive_type=HyperdriveType.ADVANCED, hull_cost=10))
                weapons = Weapons(ship_unit, hull_cost=10)
                weapons.add_turret(Turret(
                    turret_type=TurretType.MASS_DRIVER,
                    damage=10, range=300, cooldown=2,
                    parent_unit=ship_unit
                ))
                ship_unit.add_component(weapons)

                # Huge Ships are multi-role flagships
                if hull_size == HullSize.HUGE:
                    ship_unit.add_component(Constructor(
                        ship_unit, hull_cost=15
                    ))
                    ship_unit.add_component(ColonyComponent(ship_unit, hull_cost=0))
                    ship_unit.add_component(RepairComponent(
                        ship_unit,
                        repair_rate=15.0, repair_range=200.0,
                        credit_cost_per_hp=1.0, hull_cost=10
                    ))

                target_system.add_unit(ship_unit)
                logger.debug(f"Added {ship_unit.name} to {target_system.name} at {spawn_hex} for {player.name}")

                # -- Station --
                station_pos = Position(-500.0 + i * 200.0, 100.0)
                station_name = f"{player.name} {hull_size.name.capitalize()} Station"
                station_unit = Unit(
                    owner=player,
                    position=station_pos,
                    in_hex=spawn_hex,
                    in_system=target_system.name,
                    name=station_name,
                    hull_size=hull_size,
                    game=self
                )
                # MEDIUM stations get a hyperspace inhibition field emitter
                if hull_size == HullSize.MEDIUM:
                    station_unit.add_component(HyperspaceInhibitionFieldEmitter(station_unit, radius=100.0, hull_cost=20))
                weapons = Weapons(station_unit, hull_cost=10)
                weapons.add_turret(Turret(
                    turret_type=TurretType.BEAM,
                    damage=15, range=400, cooldown=3,
                    parent_unit=station_unit
                ))
                station_unit.add_component(weapons)

                # Huge Stations are capital shipyard/repair facilities
                if hull_size == HullSize.HUGE:
                    station_unit.add_component(Constructor(
                        station_unit, hull_cost=30
                    ))
                    station_unit.add_component(RepairComponent(
                        station_unit,
                        repair_rate=30.0, repair_range=350.0,
                        credit_cost_per_hp=1.0, hull_cost=20
                    ))

                target_system.add_unit(station_unit)
                logger.debug(f"Added {station_unit.name} to {target_system.name} at {spawn_hex} for {player.name}")

            # -- Carrier Ship --
            carrier_pos = Position(-500.0 + 5 * 200.0, 0.0)
            carrier_name = f"{player.name} Carrier"
            carrier_unit = Unit(
                owner=player,
                position=carrier_pos,
                in_hex=spawn_hex,
                in_system=target_system.name,
                name=carrier_name,
                hull_size=HullSize.LARGE,
                game=self
            )
            carrier_unit.add_component(Engines(carrier_unit, speed=DEFAULT_SUBLIGHT_SHIP_SPEED, hull_cost=5))
            carrier_unit.add_component(Hyperdrive(carrier_unit, drive_type=HyperdriveType.ADVANCED, hull_cost=10))
            carrier_unit.add_component(FighterBayComponent(carrier_unit, max_slots=4, hull_cost=20))
            
            weapons = Weapons(carrier_unit, hull_cost=10)
            weapons.add_turret(Turret(
                turret_type=TurretType.BEAM,
                damage=10, range=300, cooldown=2,
                parent_unit=carrier_unit
            ))
            carrier_unit.add_component(weapons)
            
            target_system.add_unit(carrier_unit)
            logger.debug(f"Added {carrier_unit.name} to {target_system.name} at {spawn_hex} for {player.name}")

    def handle_input(self):
        """Delegates input processing to the InputProcessor instance."""
        self.input_processor.handle_input()

    def deselect_object(self, obj_to_deselect: typing.Any):
        """Removes a specific object from the selection."""
        if obj_to_deselect in self.selected_objects:
            self.selected_objects.remove(obj_to_deselect)
            self.sidebar_needs_update = True
            if not any(isinstance(obj, Unit) for obj in self.selected_objects):
                self.selected_component_name = None

    # --- GUI Action Handling ---
    def handle_gui_action(self, action: typing.Dict[str, typing.Any]):
        """Handles actions triggered by GUI interactions."""
        action_type = action['action']
        action_id = action.get('action_id')
        target = action.get('target')

        if action_type == 'new_game':
            self.start_new_game()
        elif action_type == 'show_about':
            self.gui.show_about_screen()
        elif action_type == 'quit':
            self.is_running = False
        elif action_type == 'show_main_menu':
            self.view_mode = 'main_menu'
            self.game_started = False
            self.gui.show_main_menu()
        elif action_type == 'context_menu_select':
            if action_id and target is not None:
                self.input_processor.handle_context_menu_action(action_id, target)
            else:
                logger.debug(f"Warning: Context menu action '{action_id}' missing ID or target.")
        elif action_type == 'end_turn':
            self.end_turn()
        elif action_type == 'toggle_ingame_menu':
            self.gui.toggle_ingame_menu()
        elif action_type == 'toggle_unit_editor':
            if self.gui.is_unit_editor_open():
                self.gui.close_unit_editor()
            else:
                self.gui.open_unit_editor(self.custom_template_manager)
        elif action_type == 'unit_editor_design_saved':
            # Refresh SHIPYARD_MK1 constructors so they can build the new design
            if self.galaxy:
                all_units = [
                    u for system in self.galaxy.systems.values()
                    for h in system.hexes.values()
                    for u in h.units
                ]
                count = self.custom_template_manager.refresh_shipyard_buildables(all_units)
                if count:
                    logger.debug(f"[Game] Refreshed constructors on {count} shipyard unit(s) with custom designs.")
        elif action_type == 'unit_editor_design_deleted':
            pass  # No constructor refresh needed on delete
        elif action_type == 'save_game':
            self.save_game()
        elif action_type == 'quit_to_main_menu':
            self.quit_to_main_menu()
        elif action_type == 'navigate_back':
            if self.view_mode == 'sector':
                self.view_mode = 'system'
                self.current_sector_coord = None
                self.update_view_specific_labels()
                self.gui.update_back_button_visibility()
                self.update_side_bar_content()
            elif self.view_mode == 'system':
                self.view_mode = 'galaxy'
                self.current_system_name = None
                self.current_sector_coord = None
                self.update_view_specific_labels()
                self.gui.update_back_button_visibility()
                self.update_side_bar_content()
        elif action_type == 'deploy_ship':
            carrier_id = action.get('carrier_id')
            docked_unit_id = action.get('docked_unit_id')
            carrier = self.galaxy.get_unit_by_id(carrier_id)
            if carrier and (carrier.hangar_component or carrier.fighter_bay_component):
                if carrier.owner == self.players[self.current_player_index]:
                    from unit_orders import DeployUnitOrder
                    deploy_order = DeployUnitOrder(carrier, {"docked_unit_id": docked_unit_id})
                    if carrier.commander_component:
                        carrier.commander_component.add_order(deploy_order)
                        logger.debug(f"Issued DEPLOY_UNIT order for carrier {carrier.name} (docked unit ID: {docked_unit_id}).")
            self.sidebar_needs_update = True
        elif action_type == 'recall_ship':
            carrier_id = action.get('carrier_id')
            launched_unit_id = action.get('launched_unit_id')
            carrier = self.galaxy.get_unit_by_id(carrier_id)
            launched_unit = self.galaxy.get_unit_by_id(launched_unit_id)
            if carrier and launched_unit and carrier.fighter_bay_component:
                if carrier.owner == self.players[self.current_player_index]:
                    from unit_orders import DockOrder
                    dock_order = DockOrder(launched_unit, {"target_carrier_id": carrier.id})
                    if launched_unit.commander_component:
                        launched_unit.commander_component.add_order(dock_order)
                        logger.debug(f"Issued DOCK order for launched wing {launched_unit.name} to dock to carrier {carrier.name}.")
            self.sidebar_needs_update = True
        elif action_type == 'component_selected':
            self.selected_component_name = action.get('component_name')
            self.sidebar_needs_update = True
        elif action_type == 'use_ability':
            # A sidebar ability button was clicked
            ability_type_str = action.get('ability_type_str')
            requires_unit = action.get('requires_target_unit', False)
            requires_pos = action.get('requires_target_position', False)
            selected_units = [u for u in self.selected_objects if isinstance(u, Unit)]
            if selected_units and ability_type_str:
                if requires_unit or requires_pos:
                    # Enter targeting mode — next click will complete the activation
                    self.pending_ability = (ability_type_str, requires_unit, requires_pos)
                    logger.debug(f"Ability {ability_type_str} awaiting target (unit={requires_unit}, pos={requires_pos}).")
                else:
                    # Self-targeted / no-target ability: fire immediately
                    self.event_bus.publish(UseAbilityEvent(
                        units=selected_units,
                        ability_type_str=ability_type_str,
                    ))
                    logger.debug(f"Fired self-targeted ability {ability_type_str} for {len(selected_units)} unit(s).")
            self.sidebar_needs_update = True
        elif action_type == 'ui_handled':
            pass
        else:
             logger.debug(f"Warning: Unhandled GUI action type: {action_type}")

    def update(self, time_delta: float):
        """Called every frame. Updates the UI. Game logic updates are done in TurnProcessor.process_turn(), which is called at the end of each turn."""
        # Update the GUI Handler
        self.gui.update(time_delta)

        # Update view-specific labels if game is running
        if self.game_started:
            self.update_view_specific_labels()
        
        # Update info box based on selection only if needed
        if self.sidebar_needs_update:
            self.update_side_bar_content()
        
        # Update turn display
        if self.game_started and self.players:
            self.update_player_turn_display()

        # Handle pending non-blocking AI turn progression
        if self.game_started and self.pending_ai_turn_end_time > 0:
            if pygame.time.get_ticks() >= self.pending_ai_turn_end_time:
                self.pending_ai_turn_end_time = 0
                self.end_turn()


    def end_turn(self):
        """Delegates end_turn processing to the TurnProcessor instance."""
        self.turn_manager.end_turn()
        self.sidebar_needs_update = True # Ensure sidebar refreshes after turn processing

    def update_view_specific_labels(self):
        """Updates UI labels that depend on the current view mode."""
        if self.view_mode == 'system' and self.current_system_name:
            self.gui.update_view_mode_label(f"{self.current_system_name} system")
        elif self.view_mode == 'sector' and self.current_sector_coord:
            self.gui.update_view_mode_label(f"{self.current_sector_coord} sector in {self.current_system_name} system")
        elif self.view_mode == 'galaxy':
            self.gui.update_view_mode_label("Galaxy map")
        else:
            self.gui.update_view_mode_label(f"View: {self.view_mode.capitalize()}")

    def _format_order_state_data(self, state_data: dict) -> list:
        """Formats the raw order state data into a list of HTML-styled strings for display."""
        order_type = state_data.get("order_type")
        status = state_data.get("status")
        parameters = state_data.get("parameters", {})

        # Define colors for styling
        MOVE_TYPE_COLOR = "#87CEEB"    # Cyan for Move order type
        WAYPOINT_TYPE_COLOR = "#98FB98" # Green for Waypoint order type
        ATTACK_TYPE_COLOR = "#FF0000"   # Red for Attack order type
        TOGGLE_INHIBITOR_TYPE_COLOR = "#A020F0" # Purple for Toggle Inhibitor type
        TOGGLE_INHIBITOR_ON_COLOR = "#90EE90" # Light Green for Inhibitor Activate
        TOGGLE_INHIBITOR_OFF_COLOR = "#F08080" # Light Red for Inhibitor Deactivate
        PATROL_TYPE_COLOR = "#DAA520" # Goldenrod for Patrol (example)
        COLONIZE_COLOR = "#FFD700" # Gold for Colonize
        LOAD_COLONISTS_COLOR = "#ADD8E6" # Light Blue for Load Colonists
        INFO_COLOR = "#D3D3D3"       # Light Gray for general info (destinations, targets, hex/pos)

        if order_type == "MOVE":
            dsys = parameters.get("destination_system_name", "N/A")
            dhex = parameters.get("destination_hex_coord", "N/A")
            dpos_param = parameters.get("destination_position", None)
            dpos_str = f"({dpos_param.x:.1f}, {dpos_param.y:.1f})" if isinstance(dpos_param, Position) else "N/A"

            move_type_styled = f"<font color='{MOVE_TYPE_COLOR}'><b>Move:</b></font>"
            dsys_styled = f"<font color='{INFO_COLOR}'><i>{dsys}</i></font>" if dsys != "N/A" else f"<font color='{INFO_COLOR}'>N/A</font>"
            dhex_styled = f"<font color='{INFO_COLOR}'>{dhex}</font>"
            dpos_styled = f"<font color='{INFO_COLOR}'>{dpos_str}</font>"
            return [
                move_type_styled,
                f"  Sys: {dsys_styled}",
                f"  Hex: {dhex_styled}",
                f"  Pos: {dpos_styled}"
            ]

        elif order_type == "REACH_WAYPOINT":
            dsys = parameters.get("destination_system_name", "N/A")
            dhex = parameters.get("destination_hex_coord", "N/A")
            dpos_param = parameters.get("destination_position", None)
            dpos_str = f"({dpos_param.x:.1f}, {dpos_param.y:.1f})" if isinstance(dpos_param, Position) else "N/A"

            waypoint_type_styled = f"<font color='{WAYPOINT_TYPE_COLOR}'><b>Waypoint:</b></font>"
            dsys_styled = f"<font color='{INFO_COLOR}'><i>{dsys}</i></font>" if dsys != "N/A" else f"<font color='{INFO_COLOR}'>N/A</font>"
            dhex_styled = f"<font color='{INFO_COLOR}'>{dhex}</font>"
            dpos_styled = f"<font color='{INFO_COLOR}'>{dpos_str}</font>"
            return [
                waypoint_type_styled,
                f"  Sys: {dsys_styled}",
                f"  Hex: {dhex_styled}",
                f"  Pos: {dpos_styled}"
            ]

        elif order_type == "TOGGLE_INHIBITOR":
            turn_on = parameters.get("turn_on", False)
            action = "Activate" if turn_on else "Deactivate"
            status_color = TOGGLE_INHIBITOR_ON_COLOR if turn_on else TOGGLE_INHIBITOR_OFF_COLOR
            action_styled = f"<font color='{status_color}'>{action}</font>"
            toggle_inhibitor_type_styled = f"<font color='{TOGGLE_INHIBITOR_TYPE_COLOR}'><b>Toggle Inhibitor:</b></font>"
            return [f"{toggle_inhibitor_type_styled} {action_styled}"]

        elif order_type == "PATROL":
            dsys = parameters.get("destination_system_name", "N/A")
            dhex = parameters.get("destination_hex_coord", "N/A")
            dpos_param = parameters.get("destination_position", None)
            dpos_str = f"({dpos_param.x:.1f}, {dpos_param.y:.1f})" if isinstance(dpos_param, Position) else "N/A"

            patrol_type_styled = f"<font color='{PATROL_TYPE_COLOR}'><b>🔄 Patrol:</b></font>"
            dsys_styled = f"<font color='{INFO_COLOR}'><i>{dsys}</i></font>" if dsys != "N/A" else f"<font color='{INFO_COLOR}'>N/A</font>"
            dhex_styled = f"<font color='{INFO_COLOR}'>{dhex}</font>"
            dpos_styled = f"<font color='{INFO_COLOR}'>{dpos_str}</font>"
            return [
                patrol_type_styled,
                f"  Sys: {dsys_styled}",
                f"  Hex: {dhex_styled}",
                f"  Pos: {dpos_styled}"
            ]

        elif order_type == "ATTACK":
            target_unit_id = state_data.get("target_unit_id")
            target_name = state_data.get("target_name")
            lookup_attempted = state_data.get("lookup_attempted", False)
            lookup_success = state_data.get("lookup_success", False)

            if lookup_success:
                target_unit_name_styled = f"<font color='{INFO_COLOR}'><i>{target_name}</i></font>"
            elif target_unit_id:
                if lookup_attempted:
                    target_unit_name_styled = f"<font color='{INFO_COLOR}'><i>Target ID: {target_unit_id} (Not found)</i></font>"
                else:
                    target_unit_name_styled = f"<font color='{INFO_COLOR}'><i>Target ID: {target_unit_id}</i></font>"
            else:
                target_unit_name_styled = f"<font color='{INFO_COLOR}'><i>Unknown Target</i></font>"

            attack_type_styled = f"<font color='{ATTACK_TYPE_COLOR}'><b>Attack:</b></font>"
            return [f"{attack_type_styled} {target_unit_name_styled}"]

        elif order_type == "COLONIZE":
            target_name = parameters.get("target_name", "Unknown Target")
            colonize_type_styled = f"<font color='{COLONIZE_COLOR}'><b>Colonize:</b></font>"
            target_styled = f"<font color='{INFO_COLOR}'><i>{target_name}</i></font>"
            return [f"{colonize_type_styled} {target_styled}"]

        elif order_type == "LOAD_COLONISTS":
            target_name = parameters.get("target_name", "Unknown Target")
            load_type_styled = f"<font color='{LOAD_COLONISTS_COLOR}'><b>Load Colonists:</b></font>"
            target_styled = f"<font color='{INFO_COLOR}'><i>{target_name}</i></font>"
            return [f"{load_type_styled} {target_styled}"]

        elif order_type == "MINE":
            target_id = parameters.get("target_id", "Unknown")
            mine_type_styled = f"<font color='#FFA500'><b>Mine:</b></font>"
            target_styled = f"<font color='{INFO_COLOR}'><i>Target ID: {target_id}</i></font>"
            return [f"{mine_type_styled} {target_styled}"]

        elif order_type == "UNLOAD_RESOURCES":
            target_unit_id = parameters.get("target_unit_id", "Unknown")
            unload_type_styled = f"<font color='#00FFFF'><b>Unload:</b></font>"
            target_styled = f"<font color='{INFO_COLOR}'><i>Target ID: {target_unit_id}</i></font>"
            return [f"{unload_type_styled} {target_styled}"]

        else:
            # Default styling for other order types
            return [f"<font color='{INFO_COLOR}'>{order_type} ({status})</font>"]

    def _generate_order_data_recursive(self, order: Order, current_indent_level: int) -> str:
        """
        Helper method to recursively generate an HTML-formatted string representing
        an order and its entire hierarchy of sub-orders for GUI display.

        This function traverses the given order and its sub-orders, formatting each
        level with appropriate HTML indentation and styling. It utilizes
        `_format_order_state_data` to get the styled text representation of individual
        order components and appends visual cues (like a prefix character) for nested
        sub-orders.

        Args:
            order (Order): The base or current order in the hierarchy to be processed.
            current_indent_level (int): The current depth of recursion, used to calculate
                                        the amount of indentation (non-breaking spaces)
                                        for the generated HTML lines.

        Returns:
            str: A continuous HTML string representing the formatted order and all its
                 sub-orders, ready to be rendered by a UI text box component.
        """
        html_output_for_this_order_and_children = ""
        indent_html = "&nbsp;" * 4 * current_indent_level
        
        # Get the list of text lines for the current order
        state_data = order.get_state_data()
        order_info_lines = self._format_order_state_data(state_data)
        
        sub_order_first_line_prefix_char = "> " 

        # Process and indent each line of the current order's text
        for i, line_text in enumerate(order_info_lines):
            line_prefix_html = indent_html
            # Add a visual cue (prefix char) if this is a sub-order and it's the first line of its text block
            if current_indent_level > 0 and i == 0:
                line_prefix_html += sub_order_first_line_prefix_char
        
            html_output_for_this_order_and_children += f"{line_prefix_html}{line_text}<br>"

        # Recursively process sub-orders of *this* order
        if order.sub_orders:
            for sub_order in order.sub_orders:
                html_output_for_this_order_and_children += self._generate_order_data_recursive(sub_order, current_indent_level + 1)
    
        return html_output_for_this_order_and_children

    def update_side_bar_content(self):
        """Updates the side bar info panel by constructing a list of data dictionaries."""
        
        if not self.sidebar_needs_update:
            return

        if not self.selected_objects or len(self.selected_objects) > 1 or not isinstance(self.selected_objects[0], Unit):
            self.selected_component_name = None

        if PROFILE:
            sidebar_timer = Timer()
            sidebar_timer.start()

        data_for_gui = []

        if not self.selected_objects:
            data_for_gui.append({
                'type': 'label',
                'text': 'Nothing Selected',
                'object_id': '#sidebar_title_label',
                'height': 30
            })
        elif len(self.selected_objects) > 1:
            data_for_gui.append({
                'type': 'label',
                'text': f"{len(self.selected_objects)} units selected",
                'object_id': '#sidebar_title_label',
                'height': 30
            })
            for obj in self.selected_objects:
                if isinstance(obj, Unit):
                    data_for_gui.append({
                        'type': 'label',
                        'text': f"- {obj.name}",
                        'object_id': '#sidebar_info_label',
                        'height': 20
                    })

        elif len(self.selected_objects) == 1:
            selected_obj = self.selected_objects[0]

            # --- System Selection ---
            if isinstance(selected_obj, StarSystem):
                sys_obj: StarSystem = selected_obj
                data_for_gui.append({'type': 'label', 'text': f"System: {sys_obj.name}", 'object_id': '#sidebar_title_label', 'height': 30})
                data_for_gui.append({'type': 'label', 'text': f"Position: {sys_obj.position}", 'object_id': '#sidebar_info_label', 'height': 25})
                num_units = sum(len(hex_data.units) for hex_data in sys_obj.hexes.values())
                num_bodies = sum(len(hex_data.celestial_bodies) for hex_data in sys_obj.hexes.values())
                data_for_gui.append({'type': 'label', 'text': f"Objects: {num_bodies} Bodies, {num_units} Units", 'object_id': '#sidebar_info_label', 'height': 25})

            # --- Hex Selection ---
            elif isinstance(selected_obj, Hex):
                hex_obj: Hex = selected_obj
                coords = hex_obj.coordinates()
                system_name = self.galaxy.systems[hex_obj.in_system].name
                data_for_gui.append({'type': 'label', 'text': f"Hex ({coords[0]}, {coords[1]}) in {system_name}", 'object_id': '#sidebar_title_label', 'height': 30})
                if not hex_obj.celestial_bodies and not hex_obj.units:
                    data_for_gui.append({'type': 'label', 'text': "Contains: Nothing", 'object_id': '#sidebar_info_label', 'height': 25})
                else:
                    if hex_obj.celestial_bodies:
                        data_for_gui.append({'type': 'label', 'text': "Bodies: " + ", ".join([b.name for b in hex_obj.celestial_bodies]), 'object_id': '#sidebar_info_label', 'height': 25})
                    if hex_obj.units:
                        data_for_gui.append({'type': 'label', 'text': "Units: " + ", ".join([u.name for u in hex_obj.units]), 'object_id': '#sidebar_info_label', 'height': 25})

            # --- Celestial Body Selection ---
            elif isinstance(selected_obj, CelestialBody):
                body: CelestialBody = selected_obj
                data_for_gui.append({'type': 'label', 'text': f"{body.__class__.__name__}: {body.name}", 'object_id': '#sidebar_title_label', 'height': 30})
                
                # Common info
                data_for_gui.append({'type': 'label', 'text': f"System: {body.in_system or 'None'}", 'object_id': '#sidebar_info_label', 'height': 25})
                hex_pos_str = "N/A"
                if body.in_system and body.in_system in self.galaxy.systems:
                    hex_pos_str = str(body.in_hex)
                data_for_gui.append({'type': 'label', 'text': f"Hex: {hex_pos_str}", 'object_id': '#sidebar_info_label', 'height': 25})
                data_for_gui.append({'type': 'label', 'text': f"Sector Pos: ({body.position.x:.2f}, {body.position.y:.2f})", 'object_id': '#sidebar_info_label', 'height': 25})

                # Type-specific info
                if isinstance(body, Star):
                    data_for_gui.append({'type': 'label', 'text': f"Type: {body.star_type.name.capitalize()}", 'object_id': '#sidebar_info_label', 'height': 20})
                
                elif isinstance(body, Planet):
                    data_for_gui.append({'type': 'label', 'text': f"Type: {body.planet_type.name.capitalize()}", 'object_id': '#sidebar_info_label', 'height': 20})
                    owner_name = body.owner.name if body.owner else "Uninhabited"
                    data_for_gui.append({'type': 'label', 'text': f"Owner: {owner_name}", 'object_id': '#sidebar_info_label', 'height': 25})
                    data_for_gui.append({'type': 'label', 'text': f"Population: {body.population:.2f} / {body.max_population:.2f}", 'object_id': '#sidebar_info_label', 'height': 25})

                elif isinstance(body, Moon):
                    owner_name = body.owner.name if body.owner else "Uninhabited"
                    data_for_gui.append({'type': 'label', 'text': f"Owner: {owner_name}", 'object_id': '#sidebar_info_label', 'height': 25})
                    data_for_gui.append({'type': 'label', 'text': f"Population: {body.population:.2f} / {body.max_population:.2f}", 'object_id': '#sidebar_info_label', 'height': 25})
                    data_for_gui.append({'type': 'label', 'text': f"Crystal Yield: {body.crystal_yield}", 'object_id': '#sidebar_info_label', 'height': 25})

                elif isinstance(body, Asteroid):
                    owner_name = body.owner.name if body.owner else "Uninhabited"
                    data_for_gui.append({'type': 'label', 'text': f"Owner: {owner_name}", 'object_id': '#sidebar_info_label', 'height': 25})
                    data_for_gui.append({'type': 'label', 'text': f"Population: {body.population:.2f} / {body.max_population:.2f}", 'object_id': '#sidebar_info_label', 'height': 25})
                    data_for_gui.append({'type': 'label', 'text': f"Metal Yield: {body.metal_yield}", 'object_id': '#sidebar_info_label', 'height': 25})

                elif isinstance(body, Wormhole):
                    data_for_gui.append({'type': 'label', 'text': f"Exit System: {body.exit_system_name or 'None'}", 'object_id': '#sidebar_info_label', 'height': 25})
                    data_for_gui.append({'type': 'label', 'text': f"Exit Wormhole: {body.exit_wormhole_id or 'None'}", 'object_id': '#sidebar_info_label', 'height': 25})
                    data_for_gui.append({'type': 'label', 'text': f"Stability: {body.stability}", 'object_id': '#sidebar_info_label', 'height': 25})
                    data_for_gui.append({'type': 'label', 'text': f"Diameter: {body.diameter.name.capitalize()}", 'object_id': '#sidebar_info_label', 'height': 25})

                elif isinstance(body, DebrisField):
                    data_for_gui.append({'type': 'label', 'text': "A field of space debris.", 'object_id': '#sidebar_info_label', 'height': 20})
                    data_for_gui.append({'type': 'label', 'text': "Hazardous to navigation.", 'object_id': '#sidebar_info_label', 'height': 20})

                elif isinstance(body, AsteroidField):
                    data_for_gui.append({'type': 'label', 'text': f"Asteroid Count: {body.asteroid_count}", 'object_id': '#sidebar_info_label', 'height': 20})
                    data_for_gui.append({'type': 'label', 'text': "Rich in metals.", 'object_id': '#sidebar_info_label', 'height': 20})

                elif isinstance(body, IceField):
                    data_for_gui.append({'type': 'label', 'text': "A field of frozen particles.", 'object_id': '#sidebar_info_label', 'height': 20})
                    data_for_gui.append({'type': 'label', 'text': "May contain valuable resources.", 'object_id': '#sidebar_info_label', 'height': 20})

                elif isinstance(body, Nebula):
                    data_for_gui.append({'type': 'label', 'text': f"Type: {body.nebula_type.name.capitalize()}", 'object_id': '#sidebar_info_label', 'height': 20})
                    data_for_gui.append({'type': 'label', 'text': "Affects sensors and shields.", 'object_id': '#sidebar_info_label', 'height': 20})

                elif isinstance(body, Storm):
                    data_for_gui.append({'type': 'label', 'text': f"Type: {body.storm_type.name.capitalize()}", 'object_id': '#sidebar_info_label', 'height': 20})
                    data_for_gui.append({'type': 'label', 'text': "Damages ships over time.", 'object_id': '#sidebar_info_label', 'height': 20})

                elif isinstance(body, Comet):
                    data_for_gui.append({'type': 'label', 'text': "A celestial body of ice and rock.", 'object_id': '#sidebar_info_label', 'height': 20})
            elif isinstance(selected_obj, Unit):
                unit: Unit = selected_obj
                data_for_gui.append({'type': 'label', 'text': f"Unit: {unit.name}", 'object_id': '#sidebar_title_label', 'height': 30})
                data_for_gui.append({'type': 'label', 'text': f"Type: {unit.__class__.__name__}", 'object_id': '#sidebar_info_label', 'height': 20})
                data_for_gui.append({'type': 'label', 'text': f"Hull Size: {unit.hull_size.name.capitalize()}", 'object_id': '#sidebar_info_label', 'height': 20})
            
                owner_name_style_id = f'#player_{unit.owner.name.lower().replace(" ", "_")}_label' # e.g. #player_player_1_label
                data_for_gui.append({'type': 'label', 'text': f"Owner: {unit.owner.name}", 'object_id': owner_name_style_id, 'height': 25})
            
                data_for_gui.append({'type': 'label', 'text': f"System: {unit.in_system or 'None'}", 'object_id': '#sidebar_info_label', 'height': 20})
                hex_pos_str = "N/A"
                if unit.in_system and unit.in_system in self.galaxy.systems:
                    hex_pos_str = str(unit.in_hex)
                data_for_gui.append({'type': 'label', 'text': f"Hex: {hex_pos_str}", 'object_id': '#sidebar_info_label', 'height': 20})
                data_for_gui.append({'type': 'label', 'text': f"Sector Pos: ({unit.position.x:.2f}, {unit.position.y:.2f})", 'object_id': '#sidebar_info_label', 'height': 20})
        
                data_for_gui.append({'type': 'label', 'text': f"Hull Capacity: {unit.current_hull_usage}/{unit.hull_capacity}", 'object_id': '#sidebar_info_label', 'height': 25})
                
                # Determine HP label color style based on damage
                hp_percentage = unit.current_hit_points / unit.max_hit_points
                if hp_percentage > 0.75:
                    hp_style_id = '#sidebar_hit_points_ok_label'
                elif hp_percentage > 0.40:
                    hp_style_id = '#sidebar_hit_points_light_damage_label'
                elif hp_percentage > 0.15:
                    hp_style_id = '#sidebar_hit_points_heavy_damage_label'
                else:
                    hp_style_id = '#sidebar_hit_points_critical_damage_label'

                data_for_gui.append({'type': 'label', 'text': f"Hit Points: {unit.current_hit_points}/{unit.max_hit_points}", 'object_id': hp_style_id, 'height': 25})

                # Gather available components
                components_map = {}
                if unit.commander_component:
                    components_map["Commander"] = unit.commander_component
                if unit.weapons_component:
                    components_map["Weapons"] = unit.weapons_component
                if unit.engines_component:
                    components_map["Engines"] = unit.engines_component
                if unit.hyperdrive_component:
                    components_map["Hyperdrive"] = unit.hyperdrive_component
                if unit.inhibitor_component:
                    components_map["Inhibitor"] = unit.inhibitor_component
                if unit.constructor_component:
                    components_map["Constructor"] = unit.constructor_component
                if unit.colony_component:
                    components_map["Colony"] = unit.colony_component
                if unit.mining_component:
                    components_map["Mining"] = unit.mining_component
                if unit.metal_refinery_component:
                    components_map["Metal Refinery"] = unit.metal_refinery_component
                if unit.crystal_refinery_component:
                    components_map["Crystal Refinery"] = unit.crystal_refinery_component
                if unit.repair_component:
                    components_map["Repair"] = unit.repair_component
                if unit.hangar_component:
                    components_map["Hangar"] = unit.hangar_component
                if unit.fighter_bay_component:
                    components_map["Fighter Bay"] = unit.fighter_bay_component
                if unit.ability_component:
                    components_map["Abilities"] = unit.ability_component

                component_order = ["Commander", "Weapons", "Engines", "Hyperdrive", "Inhibitor", "Constructor", "Colony", "Mining", "Metal Refinery", "Crystal Refinery", "Repair", "Hangar", "Fighter Bay", "Abilities"]
                dropdown_options = [c for c in component_order if c in components_map]
                for c in components_map:
                    if c not in dropdown_options:
                        dropdown_options.append(c)

                if dropdown_options:
                    if self.selected_component_name not in dropdown_options:
                        if "Commander" in dropdown_options:
                            self.selected_component_name = "Commander"
                        else:
                            self.selected_component_name = dropdown_options[0]
                    starting_option = self.selected_component_name
                else:
                    self.selected_component_name = None
                    starting_option = None

                if dropdown_options and starting_option:
                    data_for_gui.append({
                        'type': 'drop_down_menu',
                        'options_list': dropdown_options,
                        'starting_option': starting_option,
                        'height': 30
                    })

                # Render detailed info for the selected component only
                if self.selected_component_name == "Commander":
                    if unit.commander_component:
                        # Display Current Order (always visible if exists)
                        current_order = unit.commander_component.current_order
                        if current_order:
                            data_for_gui.append({
                                'type': 'label', 
                                'text': "Current Order:", 
                                'object_id': '#sidebar_section_header_label', 
                                'height': 25,
                                'indent_level': 0
                            })

                            current_order_html = self._generate_order_data_recursive(current_order, 0)
                            data_for_gui.append({
                                'type': 'text_box',
                                'html_text': current_order_html,
                                'height': 120,
                                'object_id': '#order_text_box'
                            })
                        else:
                            data_for_gui.append({'type': 'label', 'text': "Current Order: None", 'object_id': '#sidebar_info_label', 'height': 20, 'indent_level': 0})

                        # Queued Orders Section Header
                        data_for_gui.append({'type': 'label', 'text': "Queued Orders", 'object_id': '#sidebar_section_header_label', 'height': 28, 'indent_level': 0})
                    
                        queued_order_count = len(unit.commander_component.orders_queue)
                        section_key = f"{unit.id}_orders_queue" 
                        is_queue_expanded = self.gui.is_section_expanded(section_key)
                        button_text = "[-] Queued" if is_queue_expanded else "[+] Queued"
                    
                        data_for_gui.append({
                            'type': 'button', 
                            'text': f"{button_text} ({queued_order_count})", 
                            'object_id': '#sidebar_expand_button',
                            'action_id': 'toggle_orders_queue', 
                            'target_data': unit.id, 
                            'height': 25,
                            'indent_level': 0 
                        })

                        if is_queue_expanded:
                            queued_orders_html = ""
                            if queued_order_count == 0:
                                queued_orders_html = "No queued orders"
                            else:
                                for i, queued_top_order in enumerate(unit.commander_component.orders_queue):
                                    queued_orders_html += f"<b>{i+1}.</b> "
                                    queued_orders_html += self._generate_order_data_recursive(queued_top_order, 0)
                            
                            data_for_gui.append({
                                'type': 'text_box',
                                'html_text': queued_orders_html,
                                'height': 150,
                                'object_id': '#order_text_box',
                                'indent_level': 1
                            })
                    else:
                        data_for_gui.append({'type': 'label', 'text': "Orders: N/A (No Commander)", 'object_id': '#sidebar_info_label', 'height': 20})

                elif self.selected_component_name == "Weapons":
                    if unit.weapons_component:
                        comp = unit.weapons_component
                        status = "DESTROYED" if comp.is_destroyed else f"HP: {comp.current_hit_points}/{comp.max_hit_points}"
                        data_for_gui.append({'type': 'label', 'text': f"Weapons [{status}]", 'object_id': '#sidebar_section_header_label', 'height': 28, 'indent_level': 0})
                        for turret in comp.turrets:
                            target = turret.target
                            turret_text = f"- {turret.turret_type.name}: {turret.damage} dmg, {turret.range} range, {turret.cooldown} turns cooldown, Target: {target.name if target else 'N/A'}"
                            data_for_gui.append({'type': 'label', 'text': turret_text, 'object_id': '#sidebar_info_label', 'height': 20, 'indent_level': 1})

                elif self.selected_component_name == "Engines":
                    if unit.engines_component is not None:
                        comp = unit.engines_component
                        status = "DESTROYED" if comp.is_destroyed else f"HP: {comp.current_hit_points}/{comp.max_hit_points}"
                        data_for_gui.append({'type': 'label', 'text': f"Engines [{status}]", 'object_id': '#sidebar_section_header_label', 'height': 28})
                        data_for_gui.append({'type': 'label', 'text': f"Speed: {comp.speed}", 'object_id': '#sidebar_info_label', 'height': 20})

                elif self.selected_component_name == "Hyperdrive":
                    if unit.hyperdrive_component is not None:
                        comp = unit.hyperdrive_component
                        status = "DESTROYED" if comp.is_destroyed else f"HP: {comp.current_hit_points}/{comp.max_hit_points}"
                        drive_type_str = comp.drive_type.value if comp.drive_type else 'N/A'
                    
                        status_detail = ""
                        if comp.jump_status == JumpStatus.CHARGING:
                            status_detail = f" (Charging: {comp.recharge_time_remaining} turns)"
                        elif comp.jump_status == JumpStatus.JUMPING:
                            status_detail = " (Jumping)"
                        elif comp.jump_status == JumpStatus.READY:
                            status_detail = " (Ready)"
                        elif comp.jump_status == JumpStatus.ERROR:
                            status_detail = " (Error)"
     
                        final_hyperdrive_text = f"Hyperdrive [{status}]: {drive_type_str}{status_detail}"
                    
                        data_for_gui.append({
                            'type': 'label',
                            'text': final_hyperdrive_text,
                            'object_id': '#sidebar_info_label', 
                            'height': 20
                        })

                elif self.selected_component_name == "Inhibitor":
                    if unit.inhibitor_component:
                        comp = unit.inhibitor_component
                        status = "DESTROYED" if comp.is_destroyed else f"HP: {comp.current_hit_points}/{comp.max_hit_points}"
                        data_for_gui.append({'type': 'label', 'text': f"Inhibitor [{status}]", 'object_id': '#sidebar_section_header_label', 'height': 28})
                        data_for_gui.append({
                            'type': 'inhibitor_button',
                            'is_active': comp.is_active,
                            'height': 30
                        })

                elif self.selected_component_name == "Constructor":
                    if unit.constructor_component:
                        comp = unit.constructor_component
                        status = "DESTROYED" if comp.is_destroyed else f"HP: {comp.current_hit_points}/{comp.max_hit_points}"
                        data_for_gui.append({'type': 'label', 'text': f"Constructor [{status}]", 'object_id': '#sidebar_section_header_label', 'height': 28})
                        if comp.current_construction_target:
                            target_name = comp.current_construction_target[0]
                            progress = comp.construction_progress
                            total = comp.time_to_build
                            data_for_gui.append({'type': 'label', 'text': f"Constructing: {target_name}", 'object_id': '#sidebar_info_label', 'height': 25})
                            data_for_gui.append({
                                'type': 'progress_bar',
                                'progress': progress,
                                'total': total,
                                'height': 25
                            })
                        else:
                            data_for_gui.append({'type': 'label', 'text': "Status: Idle", 'object_id': '#sidebar_info_label', 'height': 20})

                elif self.selected_component_name == "Colony":
                    if unit.colony_component:
                        comp = unit.colony_component
                        status = "DESTROYED" if comp.is_destroyed else f"HP: {comp.current_hit_points}/{comp.max_hit_points}"
                        data_for_gui.append({'type': 'label', 'text': f"Colony Component [{status}]", 'object_id': '#sidebar_section_header_label', 'height': 28})
                        data_for_gui.append({'type': 'label', 'text': f"Population Cargo: {comp.population_cargo} / {comp.max_cargo}", 'object_id': '#sidebar_info_label', 'height': 20})

                elif self.selected_component_name == "Mining":
                    if unit.mining_component:
                        comp = unit.mining_component
                        status = "DESTROYED" if comp.is_destroyed else f"HP: {comp.current_hit_points}/{comp.max_hit_points}"
                        metal = int(comp.raw_metal_cargo)
                        crystal = int(comp.raw_crystal_cargo)
                        max_c = int(comp.max_cargo)
                        data_for_gui.append({'type': 'label', 'text': f"Mining Component [{status}]", 'object_id': '#sidebar_section_header_label', 'height': 28})
                        data_for_gui.append({'type': 'label', 'text': f"Raw Cargo: {metal} Metal, {crystal} Crystal / {max_c}", 'object_id': '#sidebar_info_label', 'height': 20})
                        if comp.mining_target:
                            data_for_gui.append({'type': 'label', 'text': f"Mining Target: {comp.mining_target.name}", 'object_id': '#sidebar_info_label', 'height': 20})

                elif self.selected_component_name == "Metal Refinery":
                    if unit.metal_refinery_component:
                        comp = unit.metal_refinery_component
                        status = "DESTROYED" if comp.is_destroyed else f"HP: {comp.current_hit_points}/{comp.max_hit_points}"
                        data_for_gui.append({'type': 'label', 'text': f"Metal Refinery [{status}]", 'object_id': '#sidebar_section_header_label', 'height': 28})
                        data_for_gui.append({'type': 'label', 'text': "Metal Refinery Active", 'object_id': '#sidebar_info_label', 'height': 20})

                elif self.selected_component_name == "Crystal Refinery":
                    if unit.crystal_refinery_component:
                        comp = unit.crystal_refinery_component
                        status = "DESTROYED" if comp.is_destroyed else f"HP: {comp.current_hit_points}/{comp.max_hit_points}"
                        data_for_gui.append({'type': 'label', 'text': f"Crystal Refinery [{status}]", 'object_id': '#sidebar_section_header_label', 'height': 28})
                        data_for_gui.append({'type': 'label', 'text': "Crystal Refinery Active", 'object_id': '#sidebar_info_label', 'height': 20})

                elif self.selected_component_name == "Repair":
                    if unit.repair_component:
                        comp = unit.repair_component
                        status = "DESTROYED" if comp.is_destroyed else f"HP: {comp.current_hit_points}/{comp.max_hit_points}"
                        data_for_gui.append({'type': 'label', 'text': f"Repair Component [{status}]", 'object_id': '#sidebar_section_header_label', 'height': 28})
                        data_for_gui.append({'type': 'label', 'text': f"Repair Rate: {comp.repair_rate} HP/turn", 'object_id': '#sidebar_info_label', 'height': 20})
                        data_for_gui.append({'type': 'label', 'text': f"Repair Range: {comp.repair_range}", 'object_id': '#sidebar_info_label', 'height': 20})
                        target_name = comp.target.name if comp.target else "None"
                        data_for_gui.append({'type': 'label', 'text': f"Repair Target: {target_name}", 'object_id': '#sidebar_info_label', 'height': 20})

                elif self.selected_component_name == "Hangar":
                    if unit.hangar_component:
                        comp = unit.hangar_component
                        status = "DESTROYED" if comp.is_destroyed else f"HP: {comp.current_hit_points}/{comp.max_hit_points}"
                        data_for_gui.append({'type': 'label', 'text': f"Hangar Component [{status}]", 'object_id': '#sidebar_section_header_label', 'height': 28})
                        used_slots = comp.get_used_slots()
                        data_for_gui.append({'type': 'label', 'text': f"Capacity: {used_slots} / {comp.max_slots} slots", 'object_id': '#sidebar_info_label', 'height': 20})
                        data_for_gui.append({'type': 'label', 'text': "Docked Ships:", 'object_id': '#sidebar_section_header_label', 'height': 24})
                        if not comp.docked_units:
                            data_for_gui.append({'type': 'label', 'text': "  None", 'object_id': '#sidebar_info_label', 'height': 20})
                        else:
                            for docked_ship in comp.docked_units:
                                size_slots = 1 if docked_ship.hull_size == HullSize.TINY else 2
                                ship_label = f"  - {docked_ship.name} ({size_slots} slot)" if size_slots == 1 else f"  - {docked_ship.name} ({size_slots} slots)"
                                data_for_gui.append({'type': 'label', 'text': ship_label, 'object_id': '#sidebar_info_label', 'height': 20})
                                data_for_gui.append({
                                    'type': 'button',
                                    'text': f"Deploy {docked_ship.name}",
                                    'object_id': '#sidebar_expand_button',
                                    'action_id': 'deploy_ship',
                                    'target_data': (unit.id, docked_ship.id),
                                    'height': 25
                                })

                elif self.selected_component_name == "Fighter Bay":
                    if unit.fighter_bay_component:
                        comp = unit.fighter_bay_component
                        status = "DESTROYED" if comp.is_destroyed else f"HP: {comp.current_hit_points}/{comp.max_hit_points}"
                        data_for_gui.append({'type': 'label', 'text': f"Fighter Bay [{status}]", 'object_id': '#sidebar_section_header_label', 'height': 28})
                        used_slots = comp.get_used_slots()
                        data_for_gui.append({'type': 'label', 'text': f"Capacity: {used_slots} / {comp.max_slots} wings", 'object_id': '#sidebar_info_label', 'height': 20})
                        if comp.constructing:
                            data_for_gui.append({'type': 'label', 'text': f"Constructing Fighter Wing ({comp.construction_progress + 1}/2 turns)", 'object_id': '#sidebar_info_label', 'height': 20})
                        elif comp.replenishing_unit:
                            data_for_gui.append({'type': 'label', 'text': f"Replenishing Wing: {comp.replenishing_unit.name}", 'object_id': '#sidebar_info_label', 'height': 20})
                        
                        is_owner = unit.owner == self.players[self.current_player_index]

                        # Docked Wings
                        data_for_gui.append({'type': 'label', 'text': "Docked Fighter Wings:", 'object_id': '#sidebar_section_header_label', 'height': 24})
                        if not comp.docked_units:
                            data_for_gui.append({'type': 'label', 'text': "  None", 'object_id': '#sidebar_info_label', 'height': 20})
                        else:
                            for docked_ship in comp.docked_units:
                                f_count = docked_ship.fighter_wing_component.active_fighters if docked_ship.fighter_wing_component else 4
                                wing_label = f"  - {docked_ship.name} ({f_count}/4 fighters, HP: {docked_ship.current_hit_points}/{docked_ship.max_hit_points})"
                                data_for_gui.append({'type': 'label', 'text': wing_label, 'object_id': '#sidebar_info_label', 'height': 20})
                                if is_owner:
                                    data_for_gui.append({
                                        'type': 'button',
                                        'text': f"Deploy {docked_ship.name}",
                                        'object_id': '#sidebar_expand_button',
                                        'action_id': 'deploy_ship',
                                        'target_data': (unit.id, docked_ship.id),
                                        'height': 25
                                    })

                        # Launched Wings
                        data_for_gui.append({'type': 'label', 'text': "Launched Fighter Wings:", 'object_id': '#sidebar_section_header_label', 'height': 24})
                        if not comp.launched_units:
                            data_for_gui.append({'type': 'label', 'text': "  None", 'object_id': '#sidebar_info_label', 'height': 20})
                        else:
                            for launched_ship in comp.launched_units:
                                f_count = launched_ship.fighter_wing_component.active_fighters if launched_ship.fighter_wing_component else 4
                                wing_label = f"  - {launched_ship.name} ({f_count}/4 fighters, HP: {launched_ship.current_hit_points}/{launched_ship.max_hit_points})"
                                data_for_gui.append({'type': 'label', 'text': wing_label, 'object_id': '#sidebar_info_label', 'height': 20})
                                if is_owner:
                                    data_for_gui.append({
                                        'type': 'button',
                                        'text': f"Recall {launched_ship.name}",
                                        'object_id': '#sidebar_expand_button',
                                        'action_id': 'recall_ship',
                                        'target_data': (unit.id, launched_ship.id),
                                        'height': 25
                                    })

                elif self.selected_component_name == "Abilities":
                    if unit.ability_component:
                        comp = unit.ability_component
                        status = "DESTROYED" if comp.is_destroyed else f"HP: {comp.current_hit_points}/{comp.max_hit_points}"
                        data_for_gui.append({
                            'type': 'label',
                            'text': f"Ability System [{status}]",
                            'object_id': '#sidebar_section_header_label',
                            'height': 28,
                        })

                        # Show Ion Bolt / Designate Target targeting-mode indicator
                        if self.pending_ability:
                            pending_name = self.pending_ability[0].replace('_', ' ').title()
                            data_for_gui.append({
                                'type': 'label',
                                'text': f"\u25b6 Select target for: {pending_name}",
                                'object_id': '#sidebar_hit_points_light_damage_label',
                                'height': 22,
                            })

                        from unit_components import ABILITY_DEFINITIONS, AbilityType
                        for ability_type, instance in comp.abilities.items():
                            defn = instance.definition
                            if instance.is_active:
                                cd_str = f"Active ({instance.duration_remaining} turns)"
                                btn_obj_id = '#sidebar_section_header_label'
                            elif instance.cooldown_remaining > 0:
                                cd_str = f"Cooldown: {instance.cooldown_remaining} turns"
                                btn_obj_id = '#sidebar_info_label'
                            else:
                                cd_str = "Ready"
                                btn_obj_id = '#sidebar_expand_button'

                            btn_text = f"{defn.name}  [{cd_str}]"
                            data_for_gui.append({
                                'type': 'button',
                                'text': btn_text,
                                'object_id': btn_obj_id,
                                'action_id': 'use_ability',
                                'target_data': {
                                    'ability_type_str': ability_type.value,
                                    'requires_target_unit': defn.requires_target_unit,
                                    'requires_target_position': defn.requires_target_position,
                                },
                                'height': 28,
                                'enabled': instance.is_ready and not comp.is_destroyed,
                            })
                            data_for_gui.append({
                                'type': 'label',
                                'text': f"  {defn.description}",
                                'object_id': '#sidebar_info_label',
                                'height': 18,
                            })


        # --- Default / Unknown ---
        else:
                data_for_gui.append({
                    'type': 'label',
                    'text': f"Selected: {type(selected_obj).__name__}",
                    'object_id': '#sidebar_title_label',
                    'height': 30
                })
                data_for_gui.append({
                    'type': 'label',
                    'text': f"ID: {getattr(selected_obj, 'id', 'N/A')}",
                    'object_id': '#sidebar_info_label',
                    'height': 25
                })

        if PROFILE:
            gui_update_timer = Timer()
            gui_update_timer.start()
        
        self.gui.update_side_bar_content(data_for_gui)

        if PROFILE:
            gui_update_timer.stop()
            logger.debug(f"  [Profile] GUI element recreation took: {gui_update_timer}")

        self.sidebar_needs_update = False # Reset the flag

        if PROFILE:
            sidebar_timer.stop()
            logger.debug(f"  [Profile] Sidebar update took: {sidebar_timer}")

    def update_player_turn_display(self):
        """Updates the turn label and player color indicator."""
        if not self.players:
            return
        current_player = self.players[self.current_player_index]
        self.gui.update_turn_label(f"{current_player.name}'s Turn")
        # Update color indicator panel's background
        self.gui.update_player_color_indicator(Color(current_player.color)) # Convert tuple to pygame.Color
        self.gui.update_resource_display(current_player)

    def draw(self):
        """Delegates rendering to the Renderer instance."""
        self.renderer.draw()

    def handle_mouse_wheel(self, scroll_y: int):
        """Handles mouse wheel."""
        pass

    def run(self):
        """Main game loop."""
        if not self.is_running: # Check if init failed
             logger.debug("Game initialization failed. Exiting.")
             pygame.quit()
             sys.exit()

        while self.is_running:
            time_delta = self.clock.tick(60) / 1000.0

            self.handle_input()
            self.update(time_delta)
            self.draw()

        pygame.quit()
        sys.exit()

    def save_game(self):
        logger.debug("Save game action triggered (not implemented yet).")

    def quit_to_main_menu(self):
        logger.debug("Quitting to main menu...")
        self.game_started = False
        self.view_mode = 'main_menu'
        self.gui.clear_and_reset()
        self.gui.show_main_menu()

# Application entry point
if __name__ == '__main__':
    logger.debug("Initializing Game...")
    game = Game()
    logger.debug("Starting Game Loop...")
    game.run()
