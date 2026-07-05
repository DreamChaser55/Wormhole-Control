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
import pygame
import sys
import random
import typing
import math
from pygame import Color

# Import from local modules
from constants import (
    SCREEN_RES, STATION_ICON_SIZE, SHIP_ICON_SIZE,
    DEFAULT_SUBLIGHT_SHIP_SPEED, RED, BLUE, YELLOW, DEBUG, PROFILE,
    FULLSCREEN, UPKEEP_COST_PER_HULL_POINT, MAX_UNIT_XP
)
from utils import HexCoord, Timer
from geometry import (
    Position, Vector, distance_sq, distance
)
from hexgrid_utils import hex_to_pixel, pixel_to_hex, get_hex_vertices
from sector_utils import move_towards_position, sector_coords_to_pixels, pixels_to_sector_coords, random_point_in_sector
from entities import Player, GameObject, CelestialBody, Unit, Star, Planet, Wormhole, Moon, Asteroid, HullSize
from unit_components import Engines, Hyperdrive, HyperdriveType, Commander, JumpStatus, Turret, TurretType, Weapons, HyperspaceInhibitionFieldEmitter, Constructor, ColonyComponent, RepairComponent, HangarComponent, StrikecraftBayComponent, StrikecraftWingComponent
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
        pygame.init()
        pygame.display.set_caption("Wormhole Control")
        if FULLSCREEN:
            self.screen = pygame.display.set_mode(SCREEN_RES.to_tuple(), pygame.FULLSCREEN | pygame.DOUBLEBUF)
        else:
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
            carrier_unit.add_component(StrikecraftBayComponent(carrier_unit, max_slots=4, hull_cost=20))
            
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
            if carrier and (carrier.hangar_component or carrier.strikecraft_bay_component):
                if carrier.owner == self.players[self.current_player_index]:
                    from unit_orders import DeployUnitOrder
                    deploy_order = DeployUnitOrder(carrier, {"docked_unit_id": docked_unit_id})
                    if carrier.commander_component:
                        carrier.commander_component.add_order(deploy_order)
                        logger.debug(f"Issued DEPLOY_UNIT order for carrier {carrier.name} (docked unit ID: {docked_unit_id}).")
            self.sidebar_needs_update = True
        elif action_type == 'launch_all_wings':
            carrier_id = action.get('carrier_id')
            carrier = self.galaxy.get_unit_by_id(carrier_id)
            if carrier and carrier.strikecraft_bay_component:
                if carrier.owner == self.players[self.current_player_index]:
                    from unit_orders import DeployAllWingsOrder
                    deploy_order = DeployAllWingsOrder(carrier)
                    if carrier.commander_component:
                        carrier.commander_component.add_order(deploy_order)
                        logger.debug(f"Issued DEPLOY_ALL_WINGS order for carrier {carrier.name}.")
            self.sidebar_needs_update = True
        elif action_type == 'recall_ship':
            carrier_id = action.get('carrier_id')
            launched_unit_id = action.get('launched_unit_id')
            carrier = self.galaxy.get_unit_by_id(carrier_id)
            launched_unit = self.galaxy.get_unit_by_id(launched_unit_id)
            if carrier and launched_unit and carrier.strikecraft_bay_component:
                if carrier.owner == self.players[self.current_player_index]:
                    from unit_orders import DockOrder
                    dock_order = DockOrder(launched_unit, {"target_carrier_id": carrier.id})
                    if launched_unit.commander_component:
                        launched_unit.commander_component.add_order(dock_order)
                        logger.debug(f"Issued DOCK order for launched wing {launched_unit.name} to dock to carrier {carrier.name}.")
            self.sidebar_needs_update = True
        elif action_type == 'toggle_build_wing_type':
            carrier_id = action.get('carrier_id')
            carrier = self.galaxy.get_unit_by_id(carrier_id)
            if carrier and carrier.strikecraft_bay_component:
                if carrier.owner == self.players[self.current_player_index]:
                    from unit_components import WingType
                    bay = carrier.strikecraft_bay_component
                    if bay.build_wing_type == WingType.FIGHTER:
                        bay.build_wing_type = WingType.BOMBER
                    else:
                        bay.build_wing_type = WingType.FIGHTER
                    logger.debug(f"Carrier {carrier.name} build wing type toggled to {bay.build_wing_type.name}.")
            self.sidebar_needs_update = True
        elif action_type == 'unload_resources_nearest':
            unit_id = action.get('unit_id')
            shift_pressed = action.get('shift_pressed', False)
            unit = self.galaxy.get_unit_by_id(unit_id)
            if unit and getattr(unit, 'mining_component', None) is not None:
                mining_comp = unit.mining_component
                from geometry import distance, hex_distance
                from pathfinding import find_intersystem_path
                from unit_orders import UnloadResourcesOrder

                friendly_refineries = []
                for system in self.galaxy.systems.values():
                    for hex_obj in system.hexes.values():
                        for u in hex_obj.units:
                            if u.owner == unit.owner:
                                if getattr(u, 'metal_refinery_component', None) is not None or \
                                   getattr(u, 'crystal_refinery_component', None) is not None:
                                    friendly_refineries.append(u)

                def get_dist_to_refinery(refinery):
                    if unit.in_system == refinery.in_system:
                        if unit.in_hex == refinery.in_hex:
                            return distance(unit.position, refinery.position)
                        else:
                            return hex_distance(unit.in_hex, refinery.in_hex) * 10000.0
                    else:
                        path = find_intersystem_path(self.galaxy.system_graph, unit.in_system, refinery.in_system, unit.hull_size)
                        if path is None:
                            return float('inf')
                        return (len(path) - 1) * 1000000.0 + hex_distance(unit.in_hex, refinery.in_hex) * 10000.0

                nearest_metal = None
                min_metal_dist = float('inf')
                nearest_crystal = None
                min_crystal_dist = float('inf')

                for r in friendly_refineries:
                    dist = get_dist_to_refinery(r)
                    if dist == float('inf'):
                        continue
                    if getattr(r, 'metal_refinery_component', None) is not None:
                        if dist < min_metal_dist:
                            min_metal_dist = dist
                            nearest_metal = r
                    if getattr(r, 'crystal_refinery_component', None) is not None:
                        if dist < min_crystal_dist:
                            min_crystal_dist = dist
                            nearest_crystal = r

                orders_to_add = []
                if mining_comp.raw_metal_cargo > 0 and nearest_metal is not None:
                    orders_to_add.append(UnloadResourcesOrder(unit, {"target_unit_id": nearest_metal.id}))
                if mining_comp.raw_crystal_cargo > 0 and nearest_crystal is not None:
                    orders_to_add.append(UnloadResourcesOrder(unit, {"target_unit_id": nearest_crystal.id}))

                if orders_to_add:
                    if not shift_pressed:
                        unit.commander_component.clear_orders()
                    for order in orders_to_add:
                        unit.commander_component.add_order(order)
                        logger.debug(f"Added UnloadResourcesOrder to unit {unit.name} queue targeting refinery ID {order.parameters['target_unit_id']}.")
            self.sidebar_needs_update = True
        elif action_type == 'rename_unit':
            new_name = action.get('new_name', '').strip()
            selected_units = [obj for obj in self.selected_objects if isinstance(obj, Unit)]
            current_player = self.players[self.current_player_index]
            if selected_units and isinstance(selected_units[0], Unit) and selected_units[0].owner == current_player:
                unit_to_rename = selected_units[0]
                if new_name and len(new_name) <= 30:
                    logger.debug(f"Renaming unit '{unit_to_rename.name}' -> '{new_name}'")
                    unit_to_rename.name = new_name
                else:
                    logger.debug(f"Rename rejected (empty or too long: '{new_name}'). Keeping '{unit_to_rename.name}'.")
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
        CONSTRUCT_COLOR = "#FF8C00"  # Dark Orange for Construct order type
        REPAIR_COLOR = "#00FF7F"     # Spring Green for Repair order type
        DOCK_COLOR = "#EE82EE"       # Violet for Dock order type
        DEPLOY_COLOR = "#00FFFF"     # Cyan for Deploy order type
        ABILITY_COLOR = "#FF69B4"    # Hot Pink for Use Ability order type
        MINE_COLOR = "#FFA500"       # Orange for Mine
        UNLOAD_COLOR = "#00FFFF"     # Cyan for Unload Resources

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
            mine_type_styled = f"<font color='{MINE_COLOR}'><b>Mine:</b></font>"
            target_styled = f"<font color='{INFO_COLOR}'><i>Target ID: {target_id}</i></font>"
            return [f"{mine_type_styled} {target_styled}"]

        elif order_type == "UNLOAD_RESOURCES":
            target_unit_id = parameters.get("target_unit_id", "Unknown")
            unload_type_styled = f"<font color='{UNLOAD_COLOR}'><b>Unload:</b></font>"
            target_styled = f"<font color='{INFO_COLOR}'><i>Target ID: {target_unit_id}</i></font>"
            return [f"{unload_type_styled} {target_styled}"]

        elif order_type == "CONSTRUCT":
            unit_template_name = parameters.get("unit_template_name", "Unknown Unit")
            target_pos = parameters.get("target_position")
            pos_str = f"({target_pos.x:.1f}, {target_pos.y:.1f})" if isinstance(target_pos, Position) else "N/A"
            
            construct_type_styled = f"<font color='{CONSTRUCT_COLOR}'><b>Construct:</b></font>"
            template_styled = f"<font color='{INFO_COLOR}'><i>{unit_template_name}</i></font>"
            pos_styled = f"<font color='{INFO_COLOR}'>{pos_str}</font>"
            return [
                f"{construct_type_styled} {template_styled}",
                f"  Pos: {pos_styled}"
            ]

        elif order_type == "REPAIR":
            target_name = state_data.get("target_name")
            target_unit_id = state_data.get("target_unit_id")
            lookup_success = state_data.get("lookup_success", False)

            if lookup_success:
                target_unit_name_styled = f"<font color='{INFO_COLOR}'><i>{target_name}</i></font>"
            elif target_unit_id:
                target_unit_name_styled = f"<font color='{INFO_COLOR}'><i>Target ID: {target_unit_id}</i></font>"
            else:
                target_unit_name_styled = f"<font color='{INFO_COLOR}'><i>Unknown Target</i></font>"

            repair_type_styled = f"<font color='{REPAIR_COLOR}'><b>Repair:</b></font>"
            return [f"{repair_type_styled} {target_unit_name_styled}"]

        elif order_type == "PROTECT":
            target_name = state_data.get("target_name")
            target_unit_id = state_data.get("target_unit_id")
            lookup_success = state_data.get("lookup_success", False)

            if lookup_success:
                target_unit_name_styled = f"<font color='{INFO_COLOR}'><i>{target_name}</i></font>"
            elif target_unit_id:
                target_unit_name_styled = f"<font color='{INFO_COLOR}'><i>Target ID: {target_unit_id}</i></font>"
            else:
                target_unit_name_styled = f"<font color='{INFO_COLOR}'><i>Unknown Target</i></font>"

            protect_type_styled = f"<font color='#FF69B4'><b>Protect:</b></font>"
            return [f"{protect_type_styled} {target_unit_name_styled}"]

        elif order_type == "DOCK":
            target_name = state_data.get("target_name")
            target_carrier_id = state_data.get("target_carrier_id")

            if target_name:
                carrier_name_styled = f"<font color='{INFO_COLOR}'><i>{target_name}</i></font>"
            elif target_carrier_id:
                carrier_name_styled = f"<font color='{INFO_COLOR}'><i>Carrier ID: {target_carrier_id}</i></font>"
            else:
                carrier_name_styled = f"<font color='{INFO_COLOR}'><i>Unknown Carrier</i></font>"

            dock_type_styled = f"<font color='{DOCK_COLOR}'><b>Dock:</b></font>"
            return [f"{dock_type_styled} {carrier_name_styled}"]

        elif order_type == "DEPLOY_UNIT":
            docked_name = state_data.get("docked_name")
            docked_unit_id = state_data.get("docked_unit_id")

            if docked_name:
                unit_name_styled = f"<font color='{INFO_COLOR}'><i>{docked_name}</i></font>"
            elif docked_unit_id:
                unit_name_styled = f"<font color='{INFO_COLOR}'><i>Unit ID: {docked_unit_id}</i></font>"
            else:
                unit_name_styled = f"<font color='{INFO_COLOR}'><i>Unknown Unit</i></font>"

            deploy_type_styled = f"<font color='{DEPLOY_COLOR}'><b>Deploy:</b></font>"
            return [f"{deploy_type_styled} {unit_name_styled}"]

        elif order_type == "DEPLOY_ALL_WINGS":
            deploy_all_type_styled = f"<font color='{DEPLOY_COLOR}'><b>Deploy All Wings</b></font>"
            return [deploy_all_type_styled]

        elif order_type == "USE_ABILITY":
            ability_type_str = parameters.get("ability_type", "Unknown")
            target_unit_id = parameters.get("target_unit_id")
            target_position = parameters.get("target_position")

            target_name = None
            if target_unit_id and self.galaxy:
                target_unit = self.galaxy.get_unit_by_id(target_unit_id)
                if target_unit:
                    target_name = target_unit.name

            ability_type_styled = f"<font color='{ABILITY_COLOR}'><b>Ability: {ability_type_str}</b></font>"

            lines = [ability_type_styled]
            if target_name:
                lines.append(f"  Target: <font color='{INFO_COLOR}'><i>{target_name}</i></font>")
            elif target_unit_id:
                lines.append(f"  Target: <font color='{INFO_COLOR}'><i>ID: {target_unit_id}</i></font>")

            if target_position:
                pos_str = f"({target_position.x:.1f}, {target_position.y:.1f})" if isinstance(target_position, Position) else "N/A"
                lines.append(f"  Pos: <font color='{INFO_COLOR}'>{pos_str}</font>")

            return lines

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
                data_for_gui.append({'type': 'label', 'text': f"Hex Radius: {sys_obj.radius}", 'object_id': '#sidebar_info_label', 'height': 25})
                connected_systems = sorted(set(
                    wh.exit_system_name
                    for wh in self.galaxy.wormholes.values()
                    if wh.in_system == sys_obj.name
                ))
                wormhole_text = ", ".join(connected_systems) if connected_systems else "None"
                data_for_gui.append({'type': 'label', 'text': f"Wormholes: {wormhole_text}", 'object_id': '#sidebar_info_label', 'height': 25})

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
                        data_for_gui.append({'type': 'label', 'text': "Bodies:", 'object_id': '#sidebar_info_label', 'height': 20})
                        for b in hex_obj.celestial_bodies:
                            owner = getattr(b, 'owner', None)
                            style = f'#player_{owner.name.lower().replace(" ", "_")}_label' if owner else '#sidebar_info_label'
                            data_for_gui.append({'type': 'label', 'text': b.name, 'object_id': style, 'height': 20, 'indent_level': 1})
                    if hex_obj.units:
                        data_for_gui.append({'type': 'label', 'text': "Units:", 'object_id': '#sidebar_info_label', 'height': 20})
                        for u in hex_obj.units:
                            style = f'#player_{u.owner.name.lower().replace(" ", "_")}_label'
                            data_for_gui.append({'type': 'label', 'text': u.name, 'object_id': style, 'height': 20, 'indent_level': 1})

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
                    data_for_gui.append({'type': 'label', 'text': "Can interfere with long-range sensors.", 'object_id': '#sidebar_info_label', 'height': 20})

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
                current_player = self.players[self.current_player_index]
                is_owned = (unit.owner == current_player)

                if is_owned:
                    # Editable text entry for the unit name
                    data_for_gui.append({
                        'type': 'text_entry_line',
                        'initial_text': unit.name,
                        'object_id': '#unit_name_entry',
                        'max_length': 30,
                        'height': 30
                    })
                else:
                    # Static label for enemy units
                    data_for_gui.append({'type': 'label', 'text': f"Unit: {unit.name}", 'object_id': '#sidebar_title_label', 'height': 30})
                data_for_gui.append({'type': 'label', 'text': f"Type: {unit.__class__.__name__}", 'object_id': '#sidebar_info_label', 'height': 20})
                data_for_gui.append({'type': 'label', 'text': f"Hull Size: {unit.hull_size.name.capitalize()}", 'object_id': '#sidebar_info_label', 'height': 20})
                if getattr(unit, 'template_name', None):
                    data_for_gui.append({'type': 'label', 'text': f"Template: {unit.template_name}", 'object_id': '#sidebar_info_label', 'height': 20})
            
                owner_name_style_id = f'#player_{unit.owner.name.lower().replace(" ", "_")}_label' # e.g. #player_player_1_label
                data_for_gui.append({'type': 'label', 'text': f"Owner: {unit.owner.name}", 'object_id': owner_name_style_id, 'height': 25})
            
                data_for_gui.append({'type': 'label', 'text': f"System: {unit.in_system or 'None'}", 'object_id': '#sidebar_info_label', 'height': 20})
                hex_pos_str = "N/A"
                if unit.in_system and unit.in_system in self.galaxy.systems:
                    hex_pos_str = str(unit.in_hex)
                data_for_gui.append({'type': 'label', 'text': f"Hex: {hex_pos_str}", 'object_id': '#sidebar_info_label', 'height': 20})
                data_for_gui.append({'type': 'label', 'text': f"Sector Pos: ({unit.position.x:.2f}, {unit.position.y:.2f})", 'object_id': '#sidebar_info_label', 'height': 20})
        
                data_for_gui.append({'type': 'label', 'text': f"Hull Capacity: {unit.current_hull_usage}/{unit.hull_capacity}", 'object_id': '#sidebar_info_label', 'height': 25})
                upkeep_per_turn = unit.current_hull_usage * UPKEEP_COST_PER_HULL_POINT
                data_for_gui.append({'type': 'label', 'text': f"Upkeep: {upkeep_per_turn:.2f} cr/turn", 'object_id': '#sidebar_info_label', 'height': 20})
                
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

                # XP display row
                xp = unit.experience_points
                xp_text = f"Experience: {xp} / {MAX_UNIT_XP}"
                if xp >= MAX_UNIT_XP:
                    xp_text += " [Veteran]"
                data_for_gui.append({'type': 'label', 'text': xp_text, 'object_id': '#sidebar_info_label', 'height': 20})

                # Gather available components dynamically
                installed_components = list(unit.components.values())
                installed_components.sort(key=lambda c: getattr(c, 'SIDEBAR_ORDER', 100))

                components_map = {c.DISPLAY_NAME: c for c in installed_components}
                dropdown_options = list(components_map.keys())

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

                # Render detailed info for the selected component dynamically
                selected_comp = components_map.get(self.selected_component_name)
                if selected_comp:
                    data_for_gui.extend(selected_comp.get_sidebar_data(self))

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

    def get_player_income(self, player: Player) -> float:
        """Calculates total credit income per turn for the player."""
        from entities import Planet, Moon, Asteroid
        from constants import TAX_RATE
        total_income = 0.0
        if self.galaxy:
            for system in self.galaxy.systems.values():
                for hexcoord, body in system.get_all_celestial_bodies():
                    if isinstance(body, (Planet, Moon, Asteroid)) and body.owner == player:
                        total_income += body.population * TAX_RATE
        return total_income

    def get_player_upkeep(self, player: Player) -> float:
        """Calculates total unit upkeep cost per turn for the player."""
        from constants import UPKEEP_COST_PER_HULL_POINT, HullSize
        total_upkeep = 0.0
        if self.galaxy:
            for system_obj in self.galaxy.systems.values():
                for unit, _ in system_obj.get_all_units():
                    if unit.owner != player:
                        continue
                    if unit.is_temporary:
                        continue
                    if unit.hull_size == HullSize.STRIKECRAFT_WING:
                        continue
                    total_upkeep += unit.current_hull_usage * UPKEEP_COST_PER_HULL_POINT
        return total_upkeep

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
