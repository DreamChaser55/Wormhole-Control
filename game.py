import pygame
import sys
import random
import typing
import math
from pygame import Color

# Import from local modules
from constants import (
    SCREEN_RES, STATION_ICON_SIZE, SHIP_ICON_SIZE,
    DEFAULT_SUBLIGHT_SHIP_SPEED, RED, BLUE, YELLOW, SECTOR_CIRCLE_RADIUS_LOGICAL, DEBUG, PROFILE
)
from utils import HexCoord, Timer
from geometry import (
    Position, Vector, distance_sq, distance
)
from hexgrid_utils import hex_to_pixel, pixel_to_hex, get_hex_vertices
from sector_utils import move_towards_position, sector_coords_to_pixels, pixels_to_sector_coords, random_point_in_sector, random_point_in_circle
from entities import Player, GameObject, CelestialBody, Unit, Star, Planet, Wormhole, Moon, Asteroid, HullSize
from unit_components import Engines, Hyperdrive, HyperdriveType, Drawable, Commander, JumpStatus, Turret, TurretType
from entities import Order, AsteroidField, DebrisField, IceField, Nebula, Storm, Comet, Moon
from galaxy import Galaxy, StarSystem, Hex
from gui import GUI_Handler
from renderer import Renderer
from input_processor import InputProcessor
from turn_processor import TurnProcessor

# --- Game Class ---
class Game:
    """Main game class, handles initialization, game loop, drawing, and input."""
    def __init__(self):
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

        # Instantiate the InputProcessor
        self.input_processor = InputProcessor(self)

        # Instantiate the TurnProcessor
        self.turn_manager = TurnProcessor(self)

        # Initialize the main menu UI
        self.gui.show_main_menu()
        self.sidebar_needs_update: bool = True


    def start_new_game(self):
        """Initializes a new game when the New Game button is clicked."""
        print("Starting new game setup...")

        # Set up game UI first to ensure galaxy_generation_rect is defined before galaxy generation
        self.gui.show_game_ui()

        # Generate galaxy using the bounds from the GUI
        try:
            if self.gui.galaxy_generation_rect is None:
                print("Error: galaxy_generation_rect is not set in GUI_Handler before Galaxy creation.")
                # Fallback to default Galaxy generation without GUI-specified bounds
                # This is suboptimal but prevents a complete failure
                self.galaxy = Galaxy()
            else:
                self.galaxy = Galaxy(generation_bounds=self.gui.galaxy_generation_rect)
            
            if not self.galaxy.systems:
                print("Warning: Galaxy generated with no systems.")
                return False
        except Exception as e:
            print(f"Error during Galaxy generation: {e}")
            return False

        # Add Players
        self.players = [
            Player("Player 1", BLUE, is_human=True),
            Player("Player 2", RED, is_human=True),
            Player("Player 3", YELLOW, is_human=True)
        ]
        self.current_player_index = 0

        # Grant starting resources
        for player in self.players:
            player.metal = 1000
            player.crystal = 1000

        # Assign homeworlds
        sol_system = self.galaxy.systems.get('Sol')
        if sol_system:
            all_bodies = [body for hex_coord, body in sol_system.get_all_celestial_bodies()]
            sol_planets = [body for body in all_bodies if isinstance(body, Planet)]
            random.shuffle(sol_planets)
        else:
            sol_planets = []
            print("Warning: Sol system not found for homeworld assignment.")

        for player in self.players:
            if sol_planets:
                homeworld = sol_planets.pop()
                homeworld.owner = player
                homeworld.population = 50  # Starting population
                print(f"Assigned {homeworld.name} in {homeworld.in_system} as homeworld for {player.name}")
            else:
                print(f"Warning: Not enough planets in Sol to assign a homeworld for {player.name}")

        # Set up starting units
        self.spawn_units()

        # Change view mode and set up game UI
        self.view_mode = 'galaxy'
        self.game_started = True
        self.update_side_bar_content() # Update info box for initial state
        self.update_player_turn_display() # Update turn display for Player 1
        print("New game setup complete.\n")
        return True

    def spawn_units(self):
        """Sets up the starting units of all players."""
        print("Spawning units...")
        if not self.galaxy or not self.galaxy.systems:
             print("Cannot set up initial state: No galaxy or systems exist.")
             return

        target_system: typing.Optional[StarSystem] = None
        target_system_name = 'Sol'
        if target_system_name in self.galaxy.systems:
            target_system = self.galaxy.systems[target_system_name]
        else:
            if self.galaxy.systems:
                target_system = self.galaxy.systems.values()[0]
            else:
                print("Error: No systems available to place starting units.")
                return
        print(f"Target system for starting units: {target_system.name}")

        if target_system:
            all_hull_sizes = list(HullSize)

            # Spawn units for all players
            for player in self.players:

                available_hexes = list(target_system.hexes.keys())
                random.shuffle(available_hexes) # Shuffle to get varied starting positions

                current_hex_index = 0

                if not available_hexes:
                    print(f"Warning: Target system {target_system.name} has no grid coordinates for Player {player.name} units!")
                    return

                for hull_size in all_hull_sizes:
                    if current_hex_index >= len(available_hexes):
                        print(f"Warning: Ran out of hexes in {target_system.name} for Player {player.name}'s {hull_size.name} ship.")
                        break
                    
                    # --- Spawn Ship ---
                    # Find a valid hex for the ship (not containing a star, planet, or wormhole)
                    start_hex_ship = None
                    while current_hex_index < len(available_hexes):
                        potential_hex_coord = available_hexes[current_hex_index]
                        potential_hex = target_system.hexes[potential_hex_coord]
                        current_hex_index += 1 # Consume the hex

                        # Check if the hex contains any forbidden celestial bodies
                        if not any(isinstance(body, (Star, Planet, Wormhole)) for body in potential_hex.celestial_bodies):
                            start_hex_ship = potential_hex_coord
                            break # Found a valid hex
                    
                    if start_hex_ship is None:
                        print(f"Warning: Could not find a valid empty hex for Player {player.name}'s {hull_size.name} ship.")
                        continue # Skip spawning this ship
                    
                    ship_pos = random_point_in_circle(SECTOR_CIRCLE_RADIUS_LOGICAL / 4) # Closer to center
                    ship_name = f"{player.name} {hull_size.name.capitalize()} Ship"

                    ship_unit = Unit(owner=player,
                                    position=ship_pos,
                                    in_hex=start_hex_ship,
                                    in_system=target_system.name,
                                    name=ship_name,
                                    hull_size=hull_size,
                                    game=self,
                                    in_galaxy=self.galaxy,
                                    engines_speed=DEFAULT_SUBLIGHT_SHIP_SPEED,
                                    hyperdrive_type=HyperdriveType.ADVANCED,
                                    has_weapons=True)
                    if ship_unit.weapons_component:
                        turret = Turret(
                            turret_type=TurretType.MASS_DRIVER,
                            damage=10,
                            range=300,
                            cooldown=2,
                            parent_unit=ship_unit
                        )
                        ship_unit.weapons_component.add_turret(turret)
                    target_system.add_unit(ship_unit)
                    print(f"Added {ship_unit.name} to {target_system.name} at {start_hex_ship} for {player.name}")

                    # --- Spawn Station ---
                    # Find a valid hex for the station (not containing a star, planet, or wormhole)
                    start_hex_station = None
                    while current_hex_index < len(available_hexes):
                        potential_hex_coord = available_hexes[current_hex_index]
                        potential_hex = target_system.hexes[potential_hex_coord]
                        current_hex_index += 1 # Consume the hex

                        # Check if the hex contains any forbidden celestial bodies
                        if not any(isinstance(body, (Star, Planet, Wormhole)) for body in potential_hex.celestial_bodies):
                            start_hex_station = potential_hex_coord
                            break # Found a valid hex
                    
                    if start_hex_station is None:
                        print(f"Warning: Could not find a valid empty hex for Player {player.name}'s {hull_size.name} station.")
                        continue # Skip spawning this station

                    station_pos = random_point_in_circle(SECTOR_CIRCLE_RADIUS_LOGICAL / 4) # Closer to center
                    station_name = f"{player.name} {hull_size.name.capitalize()} Station"
                    
                    # Add inhibitor to the medium station for testing
                    inhibitor_radius_val = None
                    if hull_size == HullSize.MEDIUM:
                        inhibitor_radius_val = 100.0

                    station_unit = Unit(owner=player,
                                        position=station_pos,
                                        in_hex=start_hex_station,
                                        in_system=target_system.name,
                                        name=station_name,
                                        hull_size=hull_size,
                                        game=self,
                                        in_galaxy=self.galaxy,
                                        engines_speed=None, # No engines
                                        hyperdrive_type=None, # No hyperdrive
                                        has_weapons=True,
                                        inhibitor_radius=inhibitor_radius_val,
                                        has_constructor_component=True if hull_size == HullSize.MEDIUM else False)

                    if station_unit.weapons_component:
                        turret = Turret(
                            turret_type=TurretType.BEAM,
                            damage=15,
                            range=400,
                            cooldown=3,
                            parent_unit=station_unit
                        )
                        station_unit.weapons_component.add_turret(turret)

                    target_system.add_unit(station_unit)
                    print(f"Added {station_unit.name} to {target_system.name} at {start_hex_station} for {player.name}")

                # --- Spawn Colony Ship ---
                start_hex_colony_ship = None
                while current_hex_index < len(available_hexes):
                    potential_hex_coord = available_hexes[current_hex_index]
                    potential_hex = target_system.hexes[potential_hex_coord]
                    current_hex_index += 1

                    if not any(isinstance(body, (Star, Planet, Wormhole)) for body in potential_hex.celestial_bodies):
                        start_hex_colony_ship = potential_hex_coord
                        break
            
                if start_hex_colony_ship:
                    colony_ship_pos = random_point_in_circle(SECTOR_CIRCLE_RADIUS_LOGICAL / 4)
                    colony_ship_name = f"{player.name} Colony Ship"
                    colony_ship = Unit(
                        owner=player,
                        position=colony_ship_pos,
                        in_hex=start_hex_colony_ship,
                        in_system=target_system.name,
                        name=colony_ship_name,
                        hull_size=HullSize.MEDIUM,
                        game=self,
                        in_galaxy=self.galaxy,
                        engines_speed=DEFAULT_SUBLIGHT_SHIP_SPEED,
                        hyperdrive_type=HyperdriveType.ADVANCED,
                        has_colony_component=True
                    )
                    target_system.add_unit(colony_ship)
                    print(f"Added {colony_ship.name} to {target_system.name} at {start_hex_colony_ship} for {player.name}")
                else:
                    print(f"Warning: Could not find a valid empty hex for Player {player.name}'s Colony Ship.")

    def handle_input(self):
        """Delegates input processing to the InputProcessor instance."""
        self.input_processor.handle_input()

    def deselect_object(self, obj_to_deselect: typing.Any):
        """Removes a specific object from the selection."""
        if obj_to_deselect in self.selected_objects:
            self.selected_objects.remove(obj_to_deselect)
            self.sidebar_needs_update = True

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
                print(f"Warning: Context menu action '{action_id}' missing ID or target.")
        elif action_type == 'end_turn':
            self.end_turn()
        elif action_type == 'toggle_ingame_menu':
            self.gui.toggle_ingame_menu()
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
        elif action_type == 'ui_handled':
            pass
        else:
             print(f"Warning: Unhandled GUI action type: {action_type}")

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

    def _generate_order_data_recursive(self, order: Order, current_indent_level: int) -> str:
        """
        Helper to recursively generate an HTML string for an order and its sub-orders.
        """
        html_output_for_this_order_and_children = ""
        indent_html = "&nbsp;" * 4 * current_indent_level
        
        # Get the list of text lines for the current order
        order_info_lines = order.get_info_text() # Now returns List[str]
        
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

            # --- Unit Selection ---
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

                if unit.colony_component:
                    data_for_gui.append({'type': 'label', 'text': f"Population Cargo: {unit.colony_component.population_cargo}", 'object_id': '#sidebar_info_label', 'height': 20})
        
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

                if unit.engines_component is not None:
                    data_for_gui.append({'type': 'label', 'text': f"Speed: {unit.engines_component.speed}", 'object_id': '#sidebar_info_label', 'height': 20})

                if unit.hyperdrive_component is not None:
                    hd_comp = unit.hyperdrive_component
                    drive_type_str = hd_comp.drive_type.value if hd_comp.drive_type else 'N/A'
                
                    status_detail = ""
                    if hd_comp.jump_status == JumpStatus.CHARGING:
                        status_detail = f" (Charging: {hd_comp.recharge_time_remaining} turns)"
                    elif hd_comp.jump_status == JumpStatus.JUMPING:
                        status_detail = " (Jumping)"
                    elif hd_comp.jump_status == JumpStatus.READY:
                        status_detail = " (Ready)"
                    elif hd_comp.jump_status == JumpStatus.ERROR:
                        status_detail = " (Error)"

                    final_hyperdrive_text = f"Hyperdrive: {drive_type_str}{status_detail}"
                
                    data_for_gui.append({
                        'type': 'label',
                        'text': final_hyperdrive_text,
                        'object_id': '#sidebar_info_label', 
                        'height': 20
                    })
                else: # If no hyperdrive component at all
                    data_for_gui.append({
                        'type': 'label',
                        'text': "Hyperdrive: None",
                        'object_id': '#sidebar_info_label',
                        'height': 20
                    })

                if unit.inhibitor_component:
                    data_for_gui.append({
                        'type': 'inhibitor_button',
                        'is_active': unit.inhibitor_component.is_active,
                        'height': 30
                    })

                if unit.constructor_component and unit.constructor_component.current_construction_target:
                    constructor = unit.constructor_component
                    target_name = constructor.current_construction_target[0]
                    progress = constructor.construction_progress
                    total = constructor.time_to_build
                    data_for_gui.append({'type': 'label', 'text': f"Constructing: {target_name}", 'object_id': '#sidebar_info_label', 'height': 25})
                    data_for_gui.append({
                        'type': 'progress_bar',
                        'progress': progress,
                        'total': total,
                        'height': 20
                    })

                if unit.weapons_component:
                    data_for_gui.append({'type': 'label', 'text': "Weapons", 'object_id': '#sidebar_section_header_label', 'height': 28, 'indent_level': 0})
                    for turret in unit.weapons_component.turrets:
                        target = unit.weapons_component.turrets[0].target if unit.weapons_component.turrets else None
                        turret_text = f"- {turret.turret_type.name}: {turret.damage} dmg, {turret.range} range, {turret.cooldown} turns cooldown, Target: {target.name if target else 'N/A'}"
                        data_for_gui.append({'type': 'label', 'text': turret_text, 'object_id': '#sidebar_info_label', 'height': 20, 'indent_level': 1})
        
                # Orders Section
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
            print(f"  [Profile] GUI element recreation took: {gui_update_timer}")

        self.sidebar_needs_update = False # Reset the flag

        if PROFILE:
            sidebar_timer.stop()
            print(f"  [Profile] Sidebar update took: {sidebar_timer}")

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
             print("Game initialization failed. Exiting.")
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
        print("Save game action triggered (not implemented yet).")

    def quit_to_main_menu(self):
        print("Quitting to main menu...")
        self.game_started = False
        self.view_mode = 'main_menu'
        self.gui.clear_and_reset()
        self.gui.show_main_menu()

# Application entry point
if __name__ == '__main__':
    print("Initializing Game...")
    game = Game()
    print("Starting Game Loop...")
    game.run()
