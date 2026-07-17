import logging

logger = logging.getLogger(__name__)

import pygame
import typing
from pygame import Color

from constants import (
    HEX_SIZE, SECTOR_CIRCLE_CENTER_IN_PX, SECTOR_CIRCLE_RADIUS_IN_PX, SECTOR_CIRCLE_RADIUS_LOGICAL,
    SECTOR_OBJECT_CLICK_RADIUS_MULT, STAR_RADIUS, PLANET_RADIUS, WORMHOLE_RADIUS, HULL_BASE_ICON_SCALES, SECTOR_VIEW_BASE_ICON_SIZE
)
from utils import HexCoord
from geometry import Vector, Position, distance_sq
from hexgrid_utils import pixel_to_hex
from sector_utils import sector_coords_to_pixels, pixels_to_sector_coords
from entities import GameObject, Unit, Star, Planet, Moon, Asteroid, Comet, Wormhole, HullSize, AsteroidField, IceField, DebrisField
from events import (
    CancelOrdersEvent, IssueMoveOrderEvent, IssuePatrolOrderEvent, JumpInterhexEvent, JumpWormholeEvent,
    AttackUnitEvent, ColonizeEvent, LoadColonistsEvent, ConstructEvent, RepairUnitEvent,
    MineEvent, UnloadResourcesEvent, DockEvent, UseAbilityEvent, IssueProtectOrderEvent,
    ContinuousMineEvent
)
from galaxy import StarSystem, Hex
from unit_components import HyperdriveType
from galaxy_utils import logical_to_screen_galaxy

class InputProcessor:
    def __init__(self, game_instance):
        self.game = game_instance
        self.gui = game_instance.gui

    def handle_input(self, time_delta: float = 0.016):
        """Processes user input (keyboard, mouse, UI events)."""
        mouse_pos_tuple = pygame.mouse.get_pos()
        mouse_pos = Position(mouse_pos_tuple[0], mouse_pos_tuple[1])

        # Keyboard camera panning in sector view
        keys = pygame.key.get_pressed()
        if self.game.view_mode == 'sector' and self.game.game_started:
            zoom = self.game.sector_zoom
            if not isinstance(zoom, (int, float)):
                zoom = 1.0
            pan_offset = self.game.sector_pan_offset
            if isinstance(pan_offset, Position):
                pan_amount = 500.0 * time_delta
                def is_pressed(k):
                    try: return keys[k]
                    except (IndexError, KeyError, TypeError): return False
                
                if is_pressed(pygame.K_LEFT):
                    pan_offset.x += pan_amount
                if is_pressed(pygame.K_RIGHT):
                    pan_offset.x -= pan_amount
                if is_pressed(pygame.K_UP):
                    pan_offset.y += pan_amount
                if is_pressed(pygame.K_DOWN):
                    pan_offset.y -= pan_amount

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

            # Similarly, block game-world input when the unit editor is open.
            if self.gui.is_unit_editor_open():
                continue

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if self.gui.is_mouse_over_context_menu((-1,-1)): 
                        self.gui.close_context_menu()
                    elif self.game.pending_ability is not None:
                        # Cancel ability targeting mode
                        logger.debug(f"Ability targeting cancelled via ESC.")
                        self.game.pending_ability = None
                        self.game.sidebar_needs_update = True
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
                elif event.button == 2 and self.game.view_mode == 'sector':
                    self.game.is_dragging_camera = True
                    self.game.camera_drag_last_pos = clicked_point

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
                if event.button == 2 and getattr(self.game, 'is_dragging_camera', False):
                    self.game.is_dragging_camera = False
                elif event.button == 1 and self.game.is_dragging_selection_box:
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
                                    unit_pixel_pos = sector_coords_to_pixels(unit.position, self.game.sector_zoom, self.game.sector_pan_offset)
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

            elif event.type == pygame.MOUSEMOTION:
                if self.game.view_mode == 'sector' and getattr(self.game, 'is_dragging_camera', False):
                    dx = mouse_pos.x - self.game.camera_drag_last_pos.x
                    dy = mouse_pos.y - self.game.camera_drag_last_pos.y
                    self.game.sector_pan_offset.x += dx
                    self.game.sector_pan_offset.y += dy
                    self.game.camera_drag_last_pos = mouse_pos

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
                 screen_pos = logical_to_screen_galaxy(system.position, self.gui.galaxy_generation_rect)
                 if distance_sq(mouse_pos, screen_pos) < hover_dist_sq:
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
                zoom = self.game.sector_zoom
                if not isinstance(zoom, (int, float)):
                    zoom = 1.0
                pan_offset = self.game.sector_pan_offset
                if not isinstance(pan_offset, Position):
                    pan_offset = Position(0, 0)

                min_dist_sq = float('inf')
                hovered_obj = None
                hex_obj = system.hexes[self.game.current_sector_coord]
                if hex_obj:
                    bodies = hex_obj.celestial_bodies
                    units = hex_obj.units
                    for obj in units + bodies:
                        pixel_pos = sector_coords_to_pixels(obj.position, zoom, pan_offset)
                        obj_radius_logical = 0
                        if isinstance(obj, Star): obj_radius_logical = STAR_RADIUS
                        elif isinstance(obj, Planet): obj_radius_logical = PLANET_RADIUS
                        elif isinstance(obj, Wormhole): obj_radius_logical = WORMHOLE_RADIUS
                        elif isinstance(obj, Unit):
                            unit_obj: Unit = obj
                            # Calculate effective icon size dynamically
                            scale_factor = HULL_BASE_ICON_SCALES[unit_obj.hull_size]
                            effective_icon_size = SECTOR_VIEW_BASE_ICON_SIZE * scale_factor
                            obj_radius_logical = effective_icon_size
                        elif isinstance(obj, Moon):
                            obj_radius_logical = 27.78
                        elif isinstance(obj, Asteroid):
                            obj_radius_logical = 16.67
                        elif isinstance(obj, (AsteroidField, IceField, DebrisField)):
                            obj_radius_logical = 100.0
                        elif isinstance(obj, Comet):
                            obj_radius_logical = 16.67
                        else:
                            obj_radius_logical = 13.89
                        
                        obj_radius = obj_radius_logical * (SECTOR_CIRCLE_RADIUS_IN_PX * zoom) / SECTOR_CIRCLE_RADIUS_LOGICAL
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

        # --- Pending Ability Targeting Mode ---
        # If an ability awaiting a target is pending, intercept the next right-click
        if self.game.pending_ability and is_right_click:
            ability_type_str, requires_unit, requires_pos = self.game.pending_ability
            selected_units = [u for u in self.game.selected_objects if isinstance(u, Unit)]

            if self.game.view_mode == 'sector' and selected_units:
                clicked_object = self.game.sector_view_mouse_hover_object
                clicked_sector_coord = pixels_to_sector_coords(position, self.game.sector_zoom, self.game.sector_pan_offset)

                if requires_unit and isinstance(clicked_object, Unit):
                    # Complete unit-targeted ability
                    self.game.event_bus.publish(UseAbilityEvent(
                        units=selected_units,
                        ability_type_str=ability_type_str,
                        target_unit=clicked_object,
                        shift_pressed=shift_pressed,
                    ))
                    logger.debug(f"Ability {ability_type_str} targeted at unit {clicked_object.name}.")
                    self.game.pending_ability = None
                    self.game.sidebar_needs_update = True
                    return  # Consume the click

                elif requires_pos and not isinstance(clicked_object, Unit):
                    # Complete position-targeted ability (clicking on empty space / non-unit)
                    self.game.event_bus.publish(UseAbilityEvent(
                        units=selected_units,
                        ability_type_str=ability_type_str,
                        target_position=clicked_sector_coord,
                        target_system_name=self.game.current_system_name,
                        target_hex_coord=self.game.current_sector_coord,
                        shift_pressed=shift_pressed,
                    ))
                    logger.debug(f"Ability {ability_type_str} targeted at position {clicked_sector_coord}.")
                    self.game.pending_ability = None
                    self.game.sidebar_needs_update = True
                    return  # Consume the click

            # Wrong view or wrong target type — don't consume; let normal handling proceed

        if self.game.view_mode == 'galaxy':
            clicked_system_name = self.game.galaxy_view_mouse_hover_system_name
            system_obj = self.game.galaxy.systems.get(clicked_system_name, None)
            if system_obj:
                if is_left_click:
                    self.game.selected_objects = [system_obj]
                    self.game.sidebar_needs_update = True
                    logger.debug(f"Selected object: System {system_obj.name}")
                elif is_middle_click:
                    self.game.view_mode = 'system'
                    self.game.current_system_name = clicked_system_name
                    self.game.sidebar_needs_update = True
                    logger.debug(f"Entering system view: {system_obj.name}")
                    self.game.update_view_specific_labels()
            else:
                if is_left_click:
                    self.game.selected_objects.clear()
                    self.game.sidebar_needs_update = True
                    logger.debug("Selection cleared")

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
                        logger.debug(f"Selected object: Hex {clicked_hex} in System {system.name}")
                elif is_middle_click:
                    self.game.view_mode = 'sector'
                    self.game.current_sector_coord = clicked_hex
                    self.game.reset_sector_camera()
                    self.game.sidebar_needs_update = True
                    logger.debug(f"Entering sector view: Hex {clicked_hex} in System {self.game.current_system_name}")
                    self.game.update_view_specific_labels()
            else:
                if is_left_click:
                    self.game.selected_objects.clear()
                    self.game.sidebar_needs_update = True
                    logger.debug("Selection cleared")
                elif is_middle_click:
                    self.game.view_mode = 'galaxy'
                    self.game.current_system_name = None
                    self.game.sidebar_needs_update = True
                    logger.debug("Entering galaxy view")
                    self.game.update_view_specific_labels()

        elif self.game.view_mode == 'sector':
            zoom = self.game.sector_zoom
            if not isinstance(zoom, (int, float)):
                zoom = 1.0
            pan_offset = self.game.sector_pan_offset
            if not isinstance(pan_offset, Position):
                pan_offset = Position(0, 0)

            dynamic_center = Position(
                SECTOR_CIRCLE_CENTER_IN_PX.x + pan_offset.x,
                SECTOR_CIRCLE_CENTER_IN_PX.y + pan_offset.y
            )
            dynamic_radius = SECTOR_CIRCLE_RADIUS_IN_PX * zoom
            dist_from_center_sq = distance_sq(position, dynamic_center)
            if dist_from_center_sq <= dynamic_radius**2:
                clicked_object = self.game.sector_view_mouse_hover_object
                clicked_sector_coord = pixels_to_sector_coords(position, zoom, pan_offset)
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
                                options.append(("Patrol Here", "issue_patrol_order"))

                            ability_options = self.get_ability_context_options(actors, target_is_unit=False)
                            if ability_options:
                                options.append(("Use Ability", ability_options))

                            for actor in actors:
                                if actor.constructor_component:
                                    build_options = []
                                    for buildable in actor.constructor_component.buildable_units:
                                        from unit_templates import UNIT_TEMPLATES
                                        template = UNIT_TEMPLATES.get(buildable.unit_template_name, {})
                                        display_name = template.get("name", buildable.unit_template_name)
                                        cost = buildable.cost_credits
                                        build_options.append((f"{display_name} ({cost}c)", f"construct_{buildable.unit_template_name}"))
                                    if build_options:
                                        options.append(("Construct", build_options))
                                    break # Only need to check one constructor unit
                        elif target_object is not None:
                            if isinstance(target_object, Unit):
                                if any(target_object.owner != a.owner for a in actors):
                                    if any(a.weapons_component for a in actors):
                                        options.append(("Attack Hull", "attack_unit"))
                                        if target_object.engines_component:
                                            options.append(("Attack Engines", "attack_unit_Engines"))
                                        if target_object.hyperdrive_component:
                                            options.append(("Attack Hyperdrive", "attack_unit_Hyperdrive"))
                                        if target_object.weapons_component:
                                            options.append(("Attack Weapons", "attack_unit_Weapons"))
                                        if target_object.inhibitor_component:
                                            options.append(("Attack Inhibitor", "attack_unit_HyperspaceInhibitionFieldEmitter"))
                                elif any(target_object.owner == a.owner for a in actors) and target_object not in actors:
                                    options.append(("Protect", "protect_unit"))
                                    target_is_damaged = (
                                        target_object.current_hit_points < target_object.max_hit_points or
                                        any(c.current_hit_points < c.max_hit_points for c in target_object.components.values())
                                    )
                                    if target_is_damaged and any(a.repair_component for a in actors):
                                        options.append(("Repair", "repair_unit"))
                                    
                                    is_metal_refinery = bool(getattr(target_object, 'metal_refinery_component', None))
                                    is_crystal_refinery = bool(getattr(target_object, 'crystal_refinery_component', None))
                                    has_correct_cargo_miners = any(
                                        getattr(a, 'mining_component', None) and (
                                            (is_metal_refinery and a.mining_component.raw_metal_cargo > 0) or
                                            (is_crystal_refinery and a.mining_component.raw_crystal_cargo > 0)
                                        ) for a in actors
                                    )
                                    if (is_metal_refinery or is_crystal_refinery) and has_correct_cargo_miners:
                                        options.append(("Unload Resources", "unload_resources"))

                                    can_dock_at_carrier = (
                                        (target_object.hangar_component and any(target_object.hangar_component.can_dock(a) for a in actors)) or
                                        (target_object.strikecraft_bay_component and any(target_object.strikecraft_bay_component.can_dock(a) for a in actors))
                                    )
                                    if can_dock_at_carrier:
                                        options.append(("Dock at Carrier", "dock_at_carrier"))

                                ability_options = self.get_ability_context_options(actors, target_is_unit=True)
                                if ability_options:
                                    options.append(("Use Ability", ability_options))

                            elif isinstance(target_object, Wormhole):
                                if any(a.hyperdrive_component and a.hyperdrive_component.drive_type == HyperdriveType.ADVANCED and a.in_system == target_object.in_system for a in actors):
                                    options.append(("Jump Wormhole", "jump_wormhole"))
                    
                    if target_object is not None:
                        if isinstance(target_object, (Planet, Moon, Asteroid, AsteroidField)):
                            if isinstance(target_object, Planet):
                                options.append(("View Planet", "view_planet"))
                            if len(self.game.selected_objects) == 1 and isinstance(self.game.selected_objects[0], Unit):
                                unit = self.game.selected_objects[0]
                                if isinstance(target_object, (Planet, Moon, Asteroid)):
                                    if unit.colony_component and unit.colony_component.population_cargo > 0 and not target_object.owner:
                                        options.append(("Colonize", "colonize"))
                                    if unit.colony_component and target_object.owner == unit.owner and hasattr(target_object, 'population') and target_object.population > 0 and unit.colony_component.population_cargo < unit.colony_component.max_cargo:
                                        options.append(("Load Colonists", "load_colonists"))
                            if isinstance(target_object, (Asteroid, AsteroidField, Moon)) and any(getattr(a, 'mining_component', None) for a in actors):
                                options.append(("Mine", "mine"))
                                options.append(("Mine (continuously)", "continuous_mine"))
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
                                    logger.debug(f"Deselected unit: {clicked_object.name}")
                                else:
                                    self.game.selected_objects.append(clicked_object)
                                    logger.debug(f"Added unit to selection: {clicked_object.name}")
                                self.game.sidebar_needs_update = True
                        else:
                            self.game.selected_objects = [clicked_object]
                            obj_type = clicked_object.__class__.__name__
                            obj_name = getattr(clicked_object, 'name', 'Unnamed')
                            self.game.sidebar_needs_update = True
                            logger.debug(f"Selected object: {obj_type} {obj_name}")
                    else:
                        if not shift_pressed:
                            self.game.selected_objects.clear()
                            self.game.sidebar_needs_update = True
                            logger.debug("Selection cleared")

            elif is_middle_click:
                self.game.view_mode = 'system'
                self.game.current_sector_coord = None
                self.game.selected_objects.clear()
                self.game.sidebar_needs_update = True
                if self.game.current_system_name and self.game.galaxy.systems[self.game.current_system_name]:
                    logger.debug(f"Entering system view: {self.game.galaxy.systems[self.game.current_system_name].name}")
                else:
                    logger.debug("Entering system view (current system name unknown or invalid)")
                self.game.update_view_specific_labels()

    def handle_context_menu_action(self, action_id: str, target: typing.Any):
        """Performs the action selected from the context menu."""
        current_player = self.game.players[self.game.current_player_index]
        shift_pressed = pygame.key.get_mods() & pygame.KMOD_SHIFT

        selected_units = [obj for obj in self.game.selected_objects if isinstance(obj, Unit) and obj.owner == current_player]

        logger.debug(f"Context Action: '{action_id}', Target: {target}, Actors: {[u.name for u in selected_units]}, SHIFT: {shift_pressed}")

        # Fix: robustly extract action_id if it is nested (from context menu with sub-options)
        extracted_action_id = action_id
        while isinstance(extracted_action_id, list) and len(extracted_action_id) > 0:
            extracted_action_id = extracted_action_id[0]
        if isinstance(extracted_action_id, tuple) and len(extracted_action_id) > 1:
            extracted_action_id = extracted_action_id[1]
        elif isinstance(extracted_action_id, tuple):
            extracted_action_id = extracted_action_id[0]
        if not isinstance(extracted_action_id, str):
            extracted_action_id = str(extracted_action_id)

        if extracted_action_id == "view_hex": logger.debug("  Action: View Hex Details (Not Implemented)")
        elif extracted_action_id == "view_planet": logger.debug(f"  Action: View Planet {getattr(target, 'name', target)} Info (Not Implemented)")
        elif extracted_action_id == "view_star": logger.debug(f"  Action: View Star {getattr(target, 'name', target)} Info (Not Implemented)")
        elif extracted_action_id == "view_wormhole": logger.debug(f"  Action: View Wormhole {getattr(target, 'name', target)} Info (Not Implemented)")
        elif extracted_action_id == "view_unit": logger.debug(f"  Action: View Unit {getattr(target, 'name', target)} Info (Not Implemented)")
        elif extracted_action_id == "scan_hex": logger.debug("  Action: Scan Hex Contents (Not Implemented)")
        
        elif selected_units:
            if extracted_action_id == "cancel_orders":
                self.game.event_bus.publish(CancelOrdersEvent(selected_units))
            
            elif extracted_action_id == "issue_move_order":
                if isinstance(target, Position):
                    self.game.event_bus.publish(IssueMoveOrderEvent(
                        selected_units,
                        self.game.current_system_name,
                        self.game.current_sector_coord,
                        target,
                        shift_pressed
                    ))

            elif extracted_action_id == "issue_patrol_order":
                if isinstance(target, Position):
                    self.game.event_bus.publish(IssuePatrolOrderEvent(
                        selected_units,
                        self.game.current_system_name,
                        self.game.current_sector_coord,
                        target,
                        shift_pressed
                    ))

            elif extracted_action_id == "jump_interhex":
                if isinstance(target, tuple) and len(target) == 2:
                    self.game.event_bus.publish(JumpInterhexEvent(
                        selected_units,
                        self.game.current_system_name,
                        target,
                        shift_pressed
                    ))

            elif extracted_action_id == "jump_wormhole":
                if isinstance(target, Wormhole):
                    self.game.event_bus.publish(JumpWormholeEvent(
                        selected_units,
                        target,
                        shift_pressed
                    ))

            elif extracted_action_id.startswith("attack_unit"):
                if isinstance(target, Unit):
                    parts = extracted_action_id.split("_", 2)
                    target_component_type_str = parts[2] if len(parts) == 3 else None
                    self.game.event_bus.publish(AttackUnitEvent(
                        selected_units,
                        target,
                        shift_pressed,
                        target_component_type_str
                    ))

            elif extracted_action_id == "colonize":
                if isinstance(target, (Planet, Moon, Asteroid)):
                    self.game.event_bus.publish(ColonizeEvent(
                        selected_units,
                        target,
                        shift_pressed
                    ))

            elif extracted_action_id == "load_colonists":
                if isinstance(target, (Planet, Moon, Asteroid)):
                    amount_to_load = 25
                    self.game.event_bus.publish(LoadColonistsEvent(
                        selected_units,
                        target,
                        amount_to_load,
                        shift_pressed
                    ))

            elif extracted_action_id == "repair_unit":
                if isinstance(target, Unit):
                    self.game.event_bus.publish(RepairUnitEvent(
                        selected_units,
                        target,
                        shift_pressed
                    ))

            elif extracted_action_id == "protect_unit":
                if isinstance(target, Unit):
                    self.game.event_bus.publish(IssueProtectOrderEvent(
                        selected_units,
                        target,
                        shift_pressed
                    ))

            elif extracted_action_id == "dock_at_carrier":
                if isinstance(target, Unit):
                    self.game.event_bus.publish(DockEvent(
                        selected_units,
                        target,
                        shift_pressed
                    ))

            elif extracted_action_id == "mine":
                if isinstance(target, (Asteroid, AsteroidField, Moon)):
                    self.game.event_bus.publish(MineEvent(
                        selected_units,
                        target,
                        shift_pressed
                    ))

            elif extracted_action_id == "continuous_mine":
                if isinstance(target, (Asteroid, AsteroidField, Moon)):
                    self.game.event_bus.publish(ContinuousMineEvent(
                        selected_units,
                        target,
                        shift_pressed
                    ))

            elif extracted_action_id == "unload_resources":
                if isinstance(target, Unit):
                    self.game.event_bus.publish(UnloadResourcesEvent(
                        selected_units,
                        target,
                        shift_pressed
                    ))

            elif extracted_action_id.startswith("construct_"):
                unit_template_name = extracted_action_id.split("construct_")[1]
                if isinstance(target, Position):
                    self.game.event_bus.publish(ConstructEvent(
                        selected_units,
                        unit_template_name,
                        target,
                        shift_pressed
                    ))

            elif extracted_action_id.startswith("use_ability_"):
                ability_type_str = extracted_action_id[len("use_ability_"):]
                target_unit = target if isinstance(target, Unit) else None
                target_position = target if isinstance(target, Position) else None
                self.game.event_bus.publish(UseAbilityEvent(
                    units=selected_units,
                    ability_type_str=ability_type_str,
                    target_unit=target_unit,
                    target_position=target_position,
                    target_system_name=self.game.current_system_name,
                    target_hex_coord=self.game.current_sector_coord,
                    shift_pressed=shift_pressed,
                ))

            else:
                logger.debug(f"  Unknown context action ID or no valid unit selected: {extracted_action_id}")
            
            self.game.sidebar_needs_update = True
        else:
            logger.debug(f"  Unknown context action ID or no valid unit selected: {extracted_action_id}")

    def get_ability_context_options(self, actors: typing.List[Unit], target_is_unit: bool) -> typing.List[typing.Tuple[str, str]]:
        current_player = self.game.players[self.game.current_player_index]
        player_actors = [a for a in actors if a.owner == current_player]
        if not player_actors:
            return []

        ability_map = {}
        for actor in player_actors:
            if not actor.ability_component or actor.ability_component.is_destroyed:
                continue
            for atype, instance in actor.ability_component.abilities.items():
                defn = instance.definition
                is_relevant = defn.requires_target_unit if target_is_unit else defn.requires_target_position

                if is_relevant:
                    ability_map.setdefault(atype, []).append((actor, instance))

        if not ability_map:
            return []

        submenu_options = []
        for atype in sorted(ability_map.keys(), key=lambda t: t.value):
            actor_instances = ability_map[atype]
            defn = actor_instances[0][1].definition
            
            if len(actor_instances) == 1:
                actor, instance = actor_instances[0]
                am_comp = actor.antimatter_component
                has_enough_am = am_comp.current_amount >= defn.antimatter_cost if am_comp else True
                
                if instance.is_active:
                    status = f"Active ({instance.duration_remaining}t)"
                elif instance.cooldown_remaining > 0:
                    status = f"Cooldown: {instance.cooldown_remaining}t"
                elif not has_enough_am:
                    status = f"Low AM ({int(am_comp.current_amount)}/{defn.antimatter_cost})"
                else:
                    status = "Ready"
                
                label = f"{defn.name} ({status})"
            else:
                ready_count = 0
                total_count = len(actor_instances)
                for actor, instance in actor_instances:
                    am_comp = actor.antimatter_component
                    has_enough_am = am_comp.current_amount >= defn.antimatter_cost if am_comp else True
                    if instance.is_ready and has_enough_am:
                        ready_count += 1
                label = f"{defn.name} ({ready_count}/{total_count} Ready)"
            
            action_id = f"use_ability_{atype.value}"
            submenu_options.append((label, action_id))

        return submenu_options
