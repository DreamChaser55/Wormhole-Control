import pygame
import typing
from pygame import Color

from constants import (
    HEX_SIZE, SECTOR_CIRCLE_CENTER_IN_PX, SECTOR_CIRCLE_RADIUS_IN_PX,
    SECTOR_OBJECT_CLICK_RADIUS_MULT, STAR_RADIUS, PLANET_RADIUS, WORMHOLE_RADIUS, HULL_BASE_ICON_SCALES, SECTOR_VIEW_BASE_ICON_SIZE
)
from utils import HexCoord
from geometry import Vector, Position, distance_sq
from hexgrid_utils import pixel_to_hex
from sector_utils import sector_coords_to_pixels, pixels_to_sector_coords, random_point_in_sector
from entities import GameObject, Unit, Star, Planet, Moon, Asteroid, Wormhole, Order, OrderType, HullSize
from galaxy import StarSystem, Hex
from unit_components import HyperdriveType

class InputProcessor:
    def __init__(self, game_instance):
        self.game = game_instance
        self.gui = game_instance.gui

    def handle_input(self):
        """Processes user input (keyboard, mouse, UI events)."""
        mouse_pos_tuple = pygame.mouse.get_pos()
        mouse_pos = Position(mouse_pos_tuple[0], mouse_pos_tuple[1])

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.game.is_running = False
                return

            gui_action = self.gui.process_event(event)

            if gui_action:
                self.game.handle_gui_action(gui_action)
                if event.type in [pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION]:
                    continue

            # If the in-game menu is open, block all further game-world input processing for this event.
            # This allows the menu to be interactive while disabling the background.
            if self.gui.is_ingame_menu_open():
                continue

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if self.gui.is_mouse_over_context_menu((-1,-1)): 
                        self.gui.close_context_menu()
                    elif self.game.view_mode == 'about':
                        self.game.view_mode = 'main_menu'
                        self.gui.show_main_menu()
                    elif self.game.view_mode in ['galaxy', 'system', 'sector']:
                        self.game.view_mode = 'main_menu'
                        self.game.game_started = False
                        self.gui.show_main_menu()
                elif event.key == pygame.K_g and self.game.game_started:
                    self.game.view_mode = 'galaxy'
                    self.game.update_view_specific_labels()
                elif event.key == pygame.K_s and self.game.game_started and self.game.current_system_name:
                    self.game.view_mode = 'system'
                    self.game.selected_objects.clear()
                    self.game.update_view_specific_labels()
                elif event.key == pygame.K_e and self.game.game_started:
                    self.game.end_turn()
            
            elif event.type == pygame.MOUSEBUTTONDOWN:
                clicked_point = mouse_pos
                if event.button == 1 and self.game.view_mode == 'sector' and not gui_action:
                    self.game.is_dragging_selection_box = True
                    self.game.selection_box_start_pos = clicked_point

                if not gui_action:
                    if not self.gui.is_mouse_over_context_menu(clicked_point):
                        self.handle_mouse_click(event.button, clicked_point)
                        if event.button == 1:
                            self.gui.close_context_menu()
                else:
                    if event.button == 1: 
                        action_type = gui_action['action']
                        
                        if action_type not in ['ui_handled', 'context_menu_select'] and \
                           not self.gui.is_mouse_over_context_menu(clicked_point):
                            self.gui.close_context_menu()

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1 and self.game.is_dragging_selection_box:
                    self.game.is_dragging_selection_box = False
                    start_pos = self.game.selection_box_start_pos
                    end_pos = mouse_pos
                    
                    is_a_click = distance_sq(start_pos, end_pos) < 5**2
                    
                    if not is_a_click:
                        # It's a drag. Perform box selection.
                        selection_rect = pygame.Rect(start_pos.to_tuple(), (end_pos.x - start_pos.x, end_pos.y - start_pos.y))
                        selection_rect.normalize()

                        shift_pressed = pygame.key.get_mods() & pygame.KMOD_SHIFT
                        selected_units_in_box = []
                        current_system = self.game.galaxy.systems[self.game.current_system_name]
                        if current_system:
                            hex_obj = current_system.hexes[self.game.current_sector_coord]
                            if hex_obj:
                                for unit in hex_obj.units:
                                    unit_pixel_pos = sector_coords_to_pixels(unit.position)
                                    if selection_rect.collidepoint(unit_pixel_pos.to_tuple()):
                                        selected_units_in_box.append(unit)
                        
                        if shift_pressed:
                            # If shift is pressed, we either add to selection or deselect if all are already selected.
                            all_in_box_are_selected = all(unit in self.game.selected_objects for unit in selected_units_in_box) if selected_units_in_box else False

                            if all_in_box_are_selected:
                                # Deselect all units in the box
                                for unit in selected_units_in_box:
                                    if unit in self.game.selected_objects:
                                        self.game.selected_objects.remove(unit)
                            else:
                                # Add all units in the box to the selection
                                for unit in selected_units_in_box:
                                    if unit not in self.game.selected_objects:
                                        self.game.selected_objects.append(unit)
                        else:
                            # No shift, so just select the units in the box
                            self.game.selected_objects.clear()
                            self.game.selected_objects.extend(selected_units_in_box)
                        
                        self.game.sidebar_needs_update = True

            elif event.type == pygame.MOUSEWHEEL:
                self.game.handle_mouse_wheel(event.y)
            
        self.update_hover_states(mouse_pos)


    def update_hover_states(self, mouse_pos: 'Position'):
        """Update hover status based on current view mode and mouse position."""
        self.game.galaxy_view_mouse_hover_system_name = None
        self.game.system_view_mouse_hover_hex = None
        self.game.sector_view_mouse_hover_object = None

        context_menu_hover = self.gui.is_mouse_over_context_menu(mouse_pos)
        if context_menu_hover:
            return

        if self.game.view_mode == 'galaxy':
             if not self.game.galaxy or not self.game.galaxy.systems: return
             hover_dist_sq = 15**2
             for sys_name, system in self.game.galaxy.systems.items():
                 if distance_sq(mouse_pos, system.position) < hover_dist_sq:
                     self.game.galaxy_view_mouse_hover_system_name = sys_name
                     break

        elif self.game.view_mode == 'system':
             if not self.game.current_system_name: return
             system = self.game.galaxy.systems[self.game.current_system_name]
             if system:
                 hover_hex = pixel_to_hex(mouse_pos.x, mouse_pos.y)
                 if hover_hex in system.hexes:
                     self.game.system_view_mouse_hover_hex = hover_hex

        elif self.game.view_mode == 'sector':
            if not self.game.current_system_name or self.game.current_sector_coord is None: return
            system = self.game.galaxy.systems[self.game.current_system_name]
            if system:
                min_dist_sq = float('inf')
                hovered_obj = None
                hex_obj = system.hexes[self.game.current_sector_coord]
                if hex_obj:
                    bodies = hex_obj.celestial_bodies
                    units = hex_obj.units
                    for obj in units + bodies:
                        pixel_pos = sector_coords_to_pixels(obj.position)
                        obj_radius = 0
                        if isinstance(obj, Star): obj_radius = STAR_RADIUS
                        elif isinstance(obj, Planet): obj_radius = PLANET_RADIUS
                        elif isinstance(obj, Wormhole): obj_radius = WORMHOLE_RADIUS
                        elif isinstance(obj, Unit):
                            unit_obj: Unit = obj
                            # Calculate effective icon size dynamically
                            scale_factor = HULL_BASE_ICON_SCALES[unit_obj.hull_size]
                            effective_icon_size = SECTOR_VIEW_BASE_ICON_SIZE * scale_factor
                            obj_radius = effective_icon_size
                        
                        actual_click_radius = obj_radius * SECTOR_OBJECT_CLICK_RADIUS_MULT
                        click_radius_sq = (max(actual_click_radius, 5.0))**2
                        if click_radius_sq < 5**2: click_radius_sq = 5**2
                        dist_sq_val = distance_sq(mouse_pos, pixel_pos)

                        if dist_sq_val < click_radius_sq and dist_sq_val < min_dist_sq:
                            min_dist_sq = dist_sq_val
                            hovered_obj = obj
                self.game.sector_view_mouse_hover_object = hovered_obj

    def handle_mouse_click(self, button: int, position: 'Position'):
        """Handles mouse clicks that are not on UI elements."""
        is_left_click = (button == 1)
        is_right_click = (button == 3)
        is_middle_click = (button == 2)
        shift_pressed = pygame.key.get_mods() & pygame.KMOD_SHIFT

        if self.game.view_mode == 'galaxy':
            clicked_system_name = self.game.galaxy_view_mouse_hover_system_name
            system_obj = self.game.galaxy.systems.get(clicked_system_name, None)
            if system_obj:
                if is_left_click:
                    self.game.selected_objects = [system_obj]
                    self.game.sidebar_needs_update = True
                    print(f"Selected object: System {system_obj.name}")
                elif is_middle_click:
                    self.game.view_mode = 'system'
                    self.game.current_system_name = clicked_system_name
                    self.game.sidebar_needs_update = True
                    print(f"Entering system view: {system_obj.name}")
                    self.game.update_view_specific_labels()
            else:
                if is_left_click:
                    self.game.selected_objects.clear()
                    self.game.sidebar_needs_update = True
                    print("Selection cleared")

        elif self.game.view_mode == 'system':
            if not self.game.current_system_name: return
            system = self.game.galaxy.systems[self.game.current_system_name]
            clicked_hex = self.game.system_view_mouse_hover_hex
            if clicked_hex:
                if is_right_click:
                    options = []
                    target = clicked_hex
                    if isinstance(target, tuple) and len(target) == 2: # HexCoord
                        target_hex_coord: HexCoord = target
                        current_system = self.game.galaxy.systems[self.game.current_system_name]
                        if not current_system: return

                        options.append(("View Hex Details", "view_hex"))
                        hex_obj = current_system.hexes[target_hex_coord]
                        if hex_obj:
                            if hex_obj.celestial_bodies or hex_obj.units:
                                options.append(("Scan Hex Contents", "scan_hex"))
                            planet = next((b for b in hex_obj.celestial_bodies if isinstance(b, Planet)), None)
                            if planet: options.append(("View Planet", "view_planet"))
                            wormhole = next((b for b in hex_obj.celestial_bodies if isinstance(b, Wormhole)), None)
                            if wormhole: options.append(("View Wormhole Info", "view_wormhole"))
                        
                        actors = self.game.selected_objects
                        if any(isinstance(actor, Unit) for actor in actors):
                            for actor in actors:
                                if isinstance(actor, Unit) and actor.hyperdrive_component is not None:
                                    if target_hex_coord in current_system.hexes and actor.in_hex != target_hex_coord:
                                        options.append(("Jump Into This Sector", "jump_interhex"))
                                        break
                    self.gui.open_context_menu(position, options, target)
                elif is_left_click:
                    if clicked_hex in system.hexes:
                        hex_obj = system.hexes[clicked_hex]
                        self.game.selected_objects = [hex_obj]
                        self.game.sidebar_needs_update = True
                        print(f"Selected object: Hex {clicked_hex} in System {system.name}")
                elif is_middle_click:
                    self.game.view_mode = 'sector'
                    self.game.current_sector_coord = clicked_hex
                    self.game.sidebar_needs_update = True
                    print(f"Entering sector view: Hex {clicked_hex} in System {self.game.current_system_name}")
                    self.game.update_view_specific_labels()
            else:
                if is_left_click:
                    self.game.selected_objects.clear()
                    self.game.sidebar_needs_update = True
                    print("Selection cleared")
                elif is_middle_click:
                    self.game.view_mode = 'galaxy'
                    self.game.current_system_name = None
                    self.game.sidebar_needs_update = True
                    print("Entering galaxy view")
                    self.game.update_view_specific_labels()

        elif self.game.view_mode == 'sector':
            dist_from_center_sq = distance_sq(position, SECTOR_CIRCLE_CENTER_IN_PX)
            if dist_from_center_sq <= SECTOR_CIRCLE_RADIUS_IN_PX**2:
                clicked_object = self.game.sector_view_mouse_hover_object
                clicked_sector_coord = pixels_to_sector_coords(position)
                if is_right_click:
                    target = clicked_object if clicked_object else clicked_sector_coord
                    options = []
                    target_object = target if isinstance(target, GameObject) else None
                    target_coords = target if isinstance(target, Position) else None
                    
                    actors = self.game.selected_objects
                    actors = [a for a in actors if isinstance(a, Unit)]

                    if any(actors):
                        if target_coords is not None:
                            if any(a.engines_component and a.engines_component.speed > 0 for a in actors):
                                options.append(("Move Here", "issue_move_order"))

                            for actor in actors:
                                if actor.constructor_component:
                                    build_options = []
                                    for buildable in actor.constructor_component.buildable_units:
                                        build_options.append((f"{buildable.unit_template_name}", f"construct_{buildable.unit_template_name}"))
                                    if build_options:
                                        options.append(("Construct", build_options))
                                    break # Only need to check one constructor unit
                        elif target_object is not None:
                            if isinstance(target_object, Unit) and any(target_object.owner != a.owner for a in actors):
                                if any(a.weapons_component for a in actors):
                                    options.append(("Attack Unit", "attack_unit"))
                            elif isinstance(target_object, Wormhole):
                                if any(a.hyperdrive_component and a.hyperdrive_component.drive_type == HyperdriveType.ADVANCED and a.in_system == target_object.in_system for a in actors):
                                    options.append(("Jump Wormhole", "jump_wormhole"))
                    
                    if target_object is not None:
                        if isinstance(target_object, (Planet, Moon, Asteroid)):
                            if isinstance(target_object, Planet):
                                options.append(("View Planet", "view_planet"))
                            if len(self.game.selected_objects) == 1 and isinstance(self.game.selected_objects[0], Unit):
                                unit = self.game.selected_objects[0]
                                if unit.colony_component and unit.colony_component.population_cargo > 0 and not target_object.owner:
                                    options.append(("Colonize", "colonize"))
                                if unit.colony_component and target_object.owner == unit.owner and hasattr(target_object, 'population') and target_object.population > 0 and unit.colony_component.population_cargo < unit.colony_component.max_cargo:
                                    options.append(("Load Colonists", "load_colonists"))
                        elif isinstance(target_object, Wormhole): options.append(("View Wormhole Info", "view_wormhole"))
                        elif isinstance(target_object, Unit): options.append(("View Unit Info", "view_unit"))
                        elif isinstance(target_object, Star): options.append(("View Star", "view_star"))
                    self.gui.open_context_menu(position, options, target)

                elif is_left_click:
                    if clicked_object:
                        if shift_pressed:
                            if isinstance(clicked_object, Unit):
                                if clicked_object in self.game.selected_objects:
                                    self.game.selected_objects.remove(clicked_object)
                                    print(f"Deselected unit: {clicked_object.name}")
                                else:
                                    self.game.selected_objects.append(clicked_object)
                                    print(f"Added unit to selection: {clicked_object.name}")
                                self.game.sidebar_needs_update = True
                        else:
                            self.game.selected_objects = [clicked_object]
                            obj_type = clicked_object.__class__.__name__
                            obj_name = getattr(clicked_object, 'name', 'Unnamed')
                            self.game.sidebar_needs_update = True
                            print(f"Selected object: {obj_type} {obj_name}")
                    else:
                        if not shift_pressed:
                            self.game.selected_objects.clear()
                            self.game.sidebar_needs_update = True
                            print("Selection cleared")

            elif is_middle_click:
                self.game.view_mode = 'system'
                self.game.current_sector_coord = None
                self.game.selected_objects.clear()
                self.game.sidebar_needs_update = True
                if self.game.current_system_name and self.game.galaxy.systems[self.game.current_system_name]:
                    print(f"Entering system view: {self.game.galaxy.systems[self.game.current_system_name].name}")
                else:
                    print("Entering system view (current system name unknown or invalid)")
                self.game.update_view_specific_labels()

    def handle_context_menu_action(self, action_id: str, target: typing.Any):
        """Performs the action selected from the context menu."""
        current_player = self.game.players[self.game.current_player_index]
        shift_pressed = pygame.key.get_mods() & pygame.KMOD_SHIFT

        selected_units = [obj for obj in self.game.selected_objects if isinstance(obj, Unit) and obj.owner == current_player]

        print(f"Context Action: '{action_id}', Target: {target}, Actors: {[u.name for u in selected_units]}, SHIFT: {shift_pressed}")

        if action_id == "view_hex": print("  Action: View Hex Details (Not Implemented)")
        elif action_id == "view_planet": print(f"  Action: View Planet {getattr(target, 'name', target)} Info (Not Implemented)")
        elif action_id == "view_star": print(f"  Action: View Star {getattr(target, 'name', target)} Info (Not Implemented)")
        elif action_id == "view_wormhole": print(f"  Action: View Wormhole {getattr(target, 'name', target)} Info (Not Implemented)")
        elif action_id == "view_unit": print(f"  Action: View Unit {getattr(target, 'name', target)} Info (Not Implemented)")
        
        elif selected_units:
            for unit in selected_units:
                if action_id == "cancel_orders":
                    if unit.commander_component:
                        unit.commander_component.clear_orders()
                        print(f"  Unit {unit.name} orders cancelled.")
                
                elif action_id == "issue_move_order":
                    if isinstance(target, Position) and unit.engines_component:
                        target_pos_in_sector: 'Position' = target
                        move_params = {
                            "destination_system_name": self.game.current_system_name,
                            "destination_hex_coord": self.game.current_sector_coord,
                            "destination_position": target_pos_in_sector
                        }
                        move_order = Order(unit, OrderType.MOVE, move_params)
                        if not shift_pressed:
                            unit.commander_component.clear_orders()
                            print(f"  Unit {unit.name} orders cancelled.")
                        unit.commander_component.add_order(move_order)
                        print(f"  Unit {unit.name} ordered to move to {self.game.current_system_name}:{self.game.current_sector_coord}:{target_pos_in_sector}")

                elif action_id == "jump_interhex":
                    if isinstance(target, tuple) and len(target) == 2 and unit.hyperdrive_component:
                        target_hex_coord: HexCoord = target
                        if target_hex_coord != unit.in_hex:
                            move_params = {
                                "destination_system_name": self.game.current_system_name,
                                "destination_hex_coord": target_hex_coord,
                                "destination_position": random_point_in_sector()
                            }
                            move_order = Order(unit, OrderType.MOVE, move_params)
                            if not shift_pressed:
                                unit.commander_component.clear_orders()
                                print(f"  Unit {unit.name} orders cancelled.")
                            unit.commander_component.add_order(move_order)
                            print(f"  Unit {unit.name} ordered to move to {self.game.current_system_name}:{target_hex_coord}:{move_params['destination_position']}")

                elif action_id == "jump_wormhole":
                    if isinstance(target, Wormhole) and unit.hyperdrive_component:
                        target_wormhole: Wormhole = target
                        exit_wh_id = target_wormhole.exit_wormhole_id
                        exit_system_name = target_wormhole.exit_system_name
                        if not self.game.galaxy: continue
                        exit_wormhole = self.game.galaxy.wormholes.get(exit_wh_id, None)

                        if (unit.in_system == target_wormhole.in_system and
                                target_wormhole.stability > 0 and
                                exit_system_name and
                                exit_wormhole and 
                                exit_wormhole.in_system == exit_system_name):
                            move_params = {
                                "destination_system_name": exit_system_name,
                                "destination_hex_coord": exit_wormhole.in_hex,
                                "destination_position": exit_wormhole.position 
                            }
                            move_order = Order(unit, OrderType.MOVE, move_params)
                            if not shift_pressed:
                                unit.commander_component.clear_orders()
                                print(f"  Unit {unit.name} orders cancelled.")
                            unit.commander_component.add_order(move_order)
                            print(f"  Unit {unit.name} ordered to move via wormhole {target_wormhole.name} to {exit_system_name}:{exit_wormhole.in_hex}:{exit_wormhole.position}")

                elif action_id == "scan_hex": print("  Action: Scan Hex Contents (Not Implemented)")
                elif action_id == "attack_unit":
                    if isinstance(target, Unit):
                        attack_params = {"target_unit_id": target.id}
                        attack_order = Order(unit, OrderType.ATTACK, attack_params)
                        if not shift_pressed:
                            unit.commander_component.clear_orders()
                        unit.commander_component.add_order(attack_order)
                elif action_id == "colonize":
                    if isinstance(target, (Planet, Moon, Asteroid)):
                        colonize_params = {
                            "target_id": target.id,
                            "target_name": target.name
                        }
                        colonize_order = Order(unit, OrderType.COLONIZE, colonize_params)
                        if not shift_pressed:
                            unit.commander_component.clear_orders()
                        unit.commander_component.add_order(colonize_order)
                        print(f"  Unit {unit.name} ordered to colonize {target.name}")
                elif action_id == "load_colonists":
                    if isinstance(target, (Planet, Moon, Asteroid)):
                        # For now, load a fixed amount. Could be a dialog later.
                        amount_to_load = 25
                        load_params = {
                            "target_id": target.id,
                            "target_name": target.name,
                            "amount": amount_to_load
                        }
                        load_order = Order(unit, OrderType.LOAD_COLONISTS, load_params)
                        if not shift_pressed:
                            unit.commander_component.clear_orders()
                        unit.commander_component.add_order(load_order)
                        print(f"  Unit {unit.name} ordered to load {amount_to_load} colonists from planet {target.name}")

                # Fix: robustly extract action_id if it is nested (from context menu with sub-options)
                while isinstance(action_id, list) and len(action_id) > 0:
                    # Flatten nested lists (e.g., [[('STATION_MK1', 'construct_STATION_MK1')]])
                    action_id = action_id[0]
                if isinstance(action_id, tuple) and len(action_id) > 1:
                    action_id = action_id[1]
                elif isinstance(action_id, tuple):
                    action_id = action_id[0]
                if not isinstance(action_id, str):
                    action_id = str(action_id)

                elif action_id.startswith("construct_"):
                    unit_template_name = action_id.split("construct_")[1]
                    if isinstance(target, Position):
                        construct_params = {
                            "unit_template_name": unit_template_name,
                            "target_position": target
                        }
                        construct_order = Order(unit, OrderType.CONSTRUCT, construct_params)
                        if not shift_pressed:
                            unit.commander_component.clear_orders()
                        unit.commander_component.add_order(construct_order)
                        print(f"  Unit {unit.name} ordered to construct {unit_template_name} at {target}")

                else:
                    print(f"  Unknown context action ID for selected unit: {action_id}")
            
            self.game.sidebar_needs_update = True
        else:
            print(f"  Unknown context action ID or no valid unit selected: {action_id}")
