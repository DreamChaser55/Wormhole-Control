import pygame
import typing

from constants import PROFILE
from utils import HexCoord, Timer
from geometry import Vector, Position, distance, hex_distance, Circle, is_point_in_circle
from sector_utils import move_towards_position
from entities import Unit, Wormhole, Planet, Moon, Asteroid
from unit_components import JumpStatus

TAX_RATE = 0.1  # 10% tax rate

class TurnProcessor:
    def __init__(self, game_instance):
        self.game = game_instance

    def end_turn(self):
        """Processes the end of the current player's turn."""
        print(f"--- End of {self.game.players[self.game.current_player_index].name}'s Turn ---")
        self.process_turn()

        self.game.current_player_index = (self.game.current_player_index + 1) % len(self.game.players)
        current_player_name = self.game.players[self.game.current_player_index].name
        print(f"\n--- Start of {current_player_name}'s Turn ---")

        self.game.update_player_turn_display()
        self.game.update_side_bar_content() # Update info box after changing turn

        if not self.game.players[self.game.current_player_index].is_human:
             print(f"AI Turn for {current_player_name} (Not Implemented) - Ending Turn Automatically")
             pygame.time.wait(500) # Pause briefly for effect
             self.end_turn()

    def process_turn(self):
        """Processes actions that occur at the end of a turn (movement, jumps) and calls update() for all units in the current player's turn."""
        if PROFILE:
            total_timer = Timer()
            total_timer.start()

        current_player = self.game.players[self.game.current_player_index]
        print(f"Processing turn for {current_player.name}...")
        
        if not self.game.galaxy or not self.game.galaxy.systems:
            print("Warning: Galaxy or systems not initialized in process_turn.")
            return

        # --- 1. Movement Planning & Execution ---
        if PROFILE:
            movement_timer = Timer()
            movement_timer.start()

        for system_name, system in self.game.galaxy.systems.items():
            units_to_move: typing.List[typing.Tuple['Unit', typing.Tuple[str, typing.Union['HexCoord', str, typing.Tuple['HexCoord', 'Position']]]]] = []

            all_units_in_system = system.get_all_units()[:]
            for unit, current_hex in all_units_in_system:
                if unit.owner != current_player:
                    continue
                
                if unit.hyperdrive_component and unit.hyperdrive_component.wormhole_jump_target:
                    target_wormhole_obj = unit.hyperdrive_component.wormhole_jump_target
                    target_sys_name_for_jump = target_wormhole_obj.exit_system_name
                    exit_wh_id_for_jump = target_wormhole_obj.exit_wormhole_id
                    if target_sys_name_for_jump and exit_wh_id_for_jump and target_sys_name_for_jump in self.game.galaxy.systems:
                        units_to_move.append((unit, ("system_jump", target_sys_name_for_jump)))
                    else:
                        print(f"  Wormhole Jump Failed (Queuing): Invalid target system ({target_sys_name_for_jump}) or incomplete exit wormhole data ({exit_wh_id_for_jump}) for {unit.name}")

                elif unit.hyperdrive_component and unit.hyperdrive_component.hex_jump_target:
                    target_hex_for_jump, target_position_for_jump = unit.hyperdrive_component.hex_jump_target
                    if target_hex_for_jump != current_hex and target_hex_for_jump in system.hexes:
                        units_to_move.append((unit, ("hex_jump", (target_hex_for_jump, target_position_for_jump))))

                elif unit.engines_component and unit.engines_component.move_target:
                    target_pos_in_sector = unit.engines_component.move_target
                    unit.position = move_towards_position(unit.position, target_pos_in_sector, unit.engines_component.speed)
                    print(f"   {unit.name} moved to {unit.position} (sub-light)")
                    
                    # If unit has an active inhibitor, update its position in the hex
                    if unit.inhibitor_component and unit.inhibitor_component.is_active:
                        current_hex_obj = system.hexes[unit.in_hex]
                        if current_hex_obj:
                            current_hex_obj.dynamic_inhibition_zones[unit.id] = Circle(
                                center=unit.position,
                                radius=unit.inhibitor_component.radius
                            )

                    dist_after_move = distance(unit.position, target_pos_in_sector)
                    if dist_after_move < 0.01:
                        print(f"   {unit.name} arrived at destination {target_pos_in_sector}")
                        unit.position = target_pos_in_sector
                        if unit.engines_component:
                            unit.engines_component.move_target = None

            for unit, movement_details in units_to_move:
                movement_type, movement_data = movement_details
                origin_system = self.game.galaxy.systems[unit.in_system]
                if not origin_system:
                    print(f"   FATAL Error: Could not find origin system {unit.in_system} for unit {unit.id}. Skipping move.")
                    continue

                if not unit.hyperdrive_component:
                    print(f"   LOGIC ERROR: Unit {unit.name} in units_to_move for jump but has no hyperdrive_component. Skipping.")
                    continue
                hd_comp = unit.hyperdrive_component

                if movement_type == "system_jump":
                    if hd_comp.jump_status == JumpStatus.CHARGING:
                        print(f"   {unit.name} system jump delayed: Hyperdrive charging ({hd_comp.recharge_time_remaining} turns left).")
                        continue 
                    
                    if hd_comp.jump_status == JumpStatus.JUMPING: 
                        print(f"   Warning: {unit.name} attempting system jump while already JUMPING. Resetting to READY.")
                        hd_comp.jump_status = JumpStatus.READY 
                    
                    if hd_comp.jump_status == JumpStatus.ERROR:
                        print(f"   {unit.name} cannot system jump: Hyperdrive in ERROR state. Order should re-evaluate or clear target.")
                        continue

                    if hd_comp.jump_status != JumpStatus.READY:
                        print(f"   Error: {unit.name} unexpected jump status {hd_comp.jump_status} for system jump. Skipping.")
                        continue
                        
                    hd_comp.jump_status = JumpStatus.JUMPING

                    target_sys_name = typing.cast(str, movement_data)
                    target_system = self.game.galaxy.systems[target_sys_name]
                    arrival_hex: typing.Optional[HexCoord] = None
                    exit_wormhole_obj_for_exec: typing.Optional[Wormhole] = None
                    can_jump = False

                    # Validation starts here, hd_comp.jump_status is JUMPING
                    if not hd_comp.wormhole_jump_target: # Target might have been cleared by another process
                        print(f"   Error: Unit {unit.name} lost its wormhole_jump_target before system_jump execution. Aborting jump.")
                        hd_comp.jump_status = JumpStatus.ERROR 
                    elif not target_system:
                        print(f"   Error: Wormhole destination system {target_sys_name} not found. Jump aborted for {unit.name}.")
                        hd_comp.jump_status = JumpStatus.ERROR
                        hd_comp.wormhole_jump_target = None
                    else:
                        entry_wormhole = hd_comp.wormhole_jump_target
                        exit_wh_id = entry_wormhole.exit_wormhole_id
                        if not exit_wh_id:
                            print(f"   Error: Entry wormhole {entry_wormhole.id} for unit {unit.name} has no exit_wormhole_id. Aborting jump.")
                            hd_comp.jump_status = JumpStatus.ERROR
                            hd_comp.wormhole_jump_target = None
                        else:
                            exit_wormhole_obj_for_exec = self.game.galaxy.wormholes[exit_wh_id]
                            if not exit_wormhole_obj_for_exec:
                                print(f"   Error: Exit wormhole object with ID {exit_wh_id} not found in galaxy. Aborting jump for {unit.name}.")
                                hd_comp.jump_status = JumpStatus.ERROR
                                hd_comp.wormhole_jump_target = None
                            elif exit_wormhole_obj_for_exec.in_system != target_sys_name:
                                print(f"   Error: Exit wormhole {exit_wormhole_obj_for_exec.id} (in system {exit_wormhole_obj_for_exec.in_system}) does not actually lead to target system {target_sys_name}. Aborting jump for {unit.name}.")
                                hd_comp.jump_status = JumpStatus.ERROR
                                hd_comp.wormhole_jump_target = None
                            else:
                                arrival_hex = exit_wormhole_obj_for_exec.in_hex
                                can_jump = True
                    
                    if can_jump and arrival_hex and target_system and exit_wormhole_obj_for_exec:
                        unit.position = exit_wormhole_obj_for_exec.position 
                        moved = self.game.galaxy.move_unit_between_systems(
                            unit=unit,
                            origin_system_name=origin_system.name, 
                            destination_system_name=target_sys_name,
                            destination_hex=arrival_hex 
                        )
                        if moved:
                            print(f"   {unit.name} completed wormhole jump from {origin_system.name} to {target_sys_name}, into hex {arrival_hex}")
                            hd_comp.start_recharge() # Clears targets and sets status to CHARGING
                        else:
                            print(f"   Error during final wormhole jump execution for {unit.name}. Jump aborted.")
                            hd_comp.jump_status = JumpStatus.ERROR
                            if hd_comp.wormhole_jump_target: # Ensure target is cleared on failure
                                 hd_comp.wormhole_jump_target = None
                    elif hd_comp.jump_status == JumpStatus.JUMPING: # If can_jump became false after setting to JUMPING
                        hd_comp.jump_status = JumpStatus.ERROR 
                        if hd_comp.wormhole_jump_target: # Ensure target is cleared
                             hd_comp.wormhole_jump_target = None
                
                elif movement_type == "hex_jump":
                    if hd_comp.jump_status == JumpStatus.CHARGING:
                        print(f"   {unit.name} hex jump delayed: Hyperdrive charging ({hd_comp.recharge_time_remaining} turns left).")
                        continue
            
                    if hd_comp.jump_status == JumpStatus.JUMPING:
                        print(f"   Warning: {unit.name} attempting hex jump while already JUMPING. Resetting to READY.")
                        hd_comp.jump_status = JumpStatus.READY
            
                    if hd_comp.jump_status == JumpStatus.ERROR:
                        print(f"   {unit.name} cannot hex jump: Hyperdrive in ERROR state.")
                        continue

                    if hd_comp.jump_status != JumpStatus.READY:
                        print(f"   Error: {unit.name} unexpected jump status {hd_comp.jump_status} for hex jump. Skipping.")
                        continue
                        
                    hd_comp.jump_status = JumpStatus.JUMPING

                    target_hex, target_pos = typing.cast(typing.Tuple[HexCoord, "Position"], movement_data)
                    
                    # Validation starts here, hd_comp.jump_status is JUMPING
                    if not hd_comp.hex_jump_target: # Target might have been cleared
                        print(f"   Error: Unit {unit.name} lost its hex_jump_target before hex_jump execution. Aborting jump.")
                        hd_comp.jump_status = JumpStatus.ERROR
                        continue

                    if target_hex not in origin_system.hexes: # Validate target hex
                        print(f"   Error: Unit {unit.name} hex_jump_target {target_hex} is invalid for system {origin_system.name}. Aborting.")
                        hd_comp.jump_status = JumpStatus.ERROR
                        hd_comp.hex_jump_target = None
                        continue

                    # Validate jump range
                    if unit.in_hex and hex_distance(unit.in_hex, target_hex) > hd_comp.jump_range:
                        print(f"   Error: Unit {unit.name} hex_jump to {target_hex} exceeds jump range of {hd_comp.jump_range}. Aborting.")
                        hd_comp.jump_status = JumpStatus.ERROR
                        hd_comp.hex_jump_target = None
                        continue

                    # Validate inhibition fields
                    jump_inhibited = False
                    origin_hex_obj = origin_system.hexes[unit.in_hex]
                    if origin_hex_obj:
                        for zone in origin_hex_obj.get_all_inhibition_zones():
                            if is_point_in_circle(unit.position, zone):
                                print(f"   Error: Unit {unit.name} cannot jump; origin position is inside an inhibition field.")
                                jump_inhibited = True
                                break
                    if jump_inhibited:
                        hd_comp.jump_status = JumpStatus.ERROR
                        hd_comp.hex_jump_target = None
                        continue

                    destination_hex_obj = origin_system.hexes[target_hex]
                    if destination_hex_obj:
                        for zone in destination_hex_obj.get_all_inhibition_zones():
                            if is_point_in_circle(target_pos, zone):
                                print(f"   Error: Unit {unit.name} cannot jump; destination position is inside an inhibition field.")
                                jump_inhibited = True
                                break
                    if jump_inhibited:
                        hd_comp.jump_status = JumpStatus.ERROR
                        hd_comp.hex_jump_target = None
                        continue
                        
                    unit.position = target_pos
                    moved = origin_system.move_unit_between_hexes(unit=unit, destination_hex=target_hex)
                    if moved:
                        print(f"   {unit.name}(id:{unit.id}) completed hex jump to {target_hex}:{target_pos} in {origin_system.name} system.")
                        hd_comp.start_recharge() # Clears targets and sets status to CHARGING
                    else:
                        print(f"   Error during hex jump processing for {unit.name} to {target_hex}. Jump aborted.")
                        hd_comp.jump_status = JumpStatus.ERROR
                        if hd_comp.hex_jump_target: # Ensure target is cleared on failure
                             hd_comp.hex_jump_target = None
        
        if PROFILE:
            movement_timer.stop()
            print(f"  [Profile] Movement processing took: {movement_timer}")

        # --- 2. Population Growth ---
        if PROFILE:
            population_timer = Timer()
            population_timer.start()

        for system in self.game.galaxy.systems.values():
            for hexcoord, body in system.get_all_celestial_bodies():
                if isinstance(body, (Planet, Moon, Asteroid)):
                    body.update_population()

        if PROFILE:
            population_timer.stop()
            print(f"  [Profile] Population growth took: {population_timer}")

        # --- 3. Resource Generation ---
        if PROFILE:
            resource_timer = Timer()
            resource_timer.start()

        total_credits_generated = 0
        for system in self.game.galaxy.systems.values():
            for hexcoord, body in system.get_all_celestial_bodies():
                if isinstance(body, (Planet, Moon, Asteroid)) and body.owner == current_player:
                    credits_generated = body.population * TAX_RATE
                    current_player.credits += credits_generated
                    total_credits_generated += credits_generated

        if total_credits_generated > 0:
            print(f"  {current_player.name} generated {total_credits_generated:.2f} credits from taxes.")

        if PROFILE:
            resource_timer.stop()
            print(f"  [Profile] Resource generation took: {resource_timer}")

        # --- 4. Unit Updates ---
        if PROFILE:
            unit_update_timer = Timer()
            unit_update_timer.start()

        if current_player:
            for system_name, system_obj in self.game.galaxy.systems.items():
                all_units_in_system_for_final_update = system_obj.get_all_units()[:]
                for unit, _ in all_units_in_system_for_final_update:
                    if unit.owner == current_player:
                        unit.update()
        
        if PROFILE:
            unit_update_timer.stop()
            print(f"  [Profile] Unit updates took: {unit_update_timer}")

        if PROFILE:
            total_timer.stop()
            print(f"Finished turn processing for {current_player.name}. Total time: {total_timer}")
        else:
            print(f"Finished turn processing for {current_player.name}.")
