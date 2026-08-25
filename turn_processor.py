import logging

logger = logging.getLogger(__name__)

import pygame
import random
import typing

from utils import HexCoord, ProfileTimer
from geometry import Vector, Position, distance, hex_distance, Circle, is_point_in_circle
from sector_utils import move_towards_position
from entities import Unit, Wormhole, Planet, Moon, ColonizableAsteroid
from unit_components import JumpStatus, Commander
from visibility import VisibilityService
from constants import (
    UPKEEP_COST_PER_HULL_POINT, HullSize, TAX_RATE, XP_SPEED_BONUS, XP_JUMP_RANGE_BONUS,
    ENGINE_ANTIMATTER_COST_PER_TURN, HYPERDRIVE_SYSTEM_JUMP_COST, HYPERDRIVE_HEX_JUMP_COST
)


class TurnProcessor:
    def __init__(self, game_instance):
        self.game = game_instance

    def end_turn(self):
        """Processes the end of the current player's turn and advances turn/round state."""
        turn_num = getattr(self.game, 'turn_number', 1)
        current_player = self.game.players[self.game.current_player_index]
        logger.debug(f"--- Turn {turn_num} - End of {current_player.name}'s Turn ---")
        self.process_player_turn(current_player)

        is_last_player = (self.game.current_player_index == len(self.game.players) - 1)
        if is_last_player:
            self.process_global_end_of_round()
            if hasattr(self.game, 'turn_number'):
                self.game.turn_number += 1
            self.game.current_player_index = 0
        else:
            self.game.current_player_index += 1

        new_turn_num = getattr(self.game, 'turn_number', 1)
        next_player = self.game.players[self.game.current_player_index]
        logger.debug(f"\n--- Turn {new_turn_num} - Start of {next_player.name}'s Turn ---")

        self.game.update_player_turn_display()
        self.game.update_side_bar_content() # Update info box after changing turn
        self.check_and_schedule_ai_turn()

    def check_and_schedule_ai_turn(self):
        """Schedule the active AI after a short delay so the UI can show the turn."""
        if not getattr(self.game, 'players', None) or not (0 <= getattr(self.game, 'current_player_index', 0) < len(self.game.players)):
            return
        current_player = self.game.players[self.game.current_player_index]
        if not getattr(current_player, 'is_human', True):
            logger.debug(f"Scheduling agentic AI turn for {current_player.name}")
            self.game.pending_ai_turn_end_time = pygame.time.get_ticks() + 500
        else:
            self.game.pending_ai_turn_end_time = 0

    def process_turn(self, player=None):
        """Processes actions that occur at the end of a player's turn (movement, jumps, economy, unit updates)."""
        target_player = player if player is not None else self.game.players[self.game.current_player_index]
        self.process_player_turn(target_player)


    def process_player_turn(self, current_player):
        """Processes player-specific actions that occur at the end of their turn (movement, economy, unit updates)."""
        with ProfileTimer("Total player turn processing"):
            turn_num = getattr(self.game, 'turn_number', 1)
            logger.debug(f"Processing Turn {turn_num} for {current_player.name}...")
            
            if not self.game.galaxy or not self.game.galaxy.systems:
                logger.debug("Warning: Galaxy or systems not initialized in process_turn.")
                return

            # The execution order is critical for game state consistency:
            # 1. Resolve unit movement first so positions are updated.
            # 2. Minefield detonations from movement.
            # 3. Generate resource credits for the active player based on population and habitats.
            # 4. Deduct upkeep for the active player's units.
            # 5. Run unit state updates (engines, weapons, order resolution) with updated context.
            with ProfileTimer("Movement processing"):
                self._process_movement(current_player)

            with ProfileTimer("Minefield detonations"):
                self._process_minefield_detonations()
                self._cleanup_dead_units()

            with ProfileTimer("Resource generation"):
                self._process_resource_generation(current_player)

            with ProfileTimer("Unit upkeep"):
                self._process_unit_upkeep(current_player)

            with ProfileTimer("Unit updates"):
                self._process_unit_updates(current_player)
                self._cleanup_dead_units()

            logger.debug(f"Finished Turn {turn_num} processing for {current_player.name}.")


    def process_global_end_of_round(self):
        """Processes galaxy-wide actions at the end of a full round (after all players have acted)."""
        with ProfileTimer("Total global end of round processing"):
            turn_num = getattr(self.game, 'turn_number', 1)
            logger.debug(f"Processing End of Round {turn_num} (Global)...")

            if not self.game.galaxy or not self.game.galaxy.systems:
                return

            with ProfileTimer("Population growth"):
                self._process_population_growth()

            with ProfileTimer("Sector intel update"):
                VisibilityService.update_all_players_intel(self.game.galaxy, self.game.players, turn_num)

            logger.debug(f"Finished End of Round {turn_num} processing.")

    def _process_movement(self, current_player):
        for system_name, system in self.game.galaxy.systems.items():
            units_to_move: typing.List[typing.Tuple['Unit', typing.Tuple[str, typing.Union['HexCoord', str, typing.Tuple['HexCoord', 'Position']]]]] = []

            all_units_in_system = system.get_all_units()[:]
            for unit, current_hex in all_units_in_system:
                if unit.owner != current_player:
                    continue

                # Units disabled by Ion Bolt cannot move
                if unit.is_disabled:
                    logger.debug(f"   {unit.name} is disabled (Ion Bolt) — movement skipped.")
                    continue
                
                if unit.hyperdrive_component and unit.hyperdrive_component.wormhole_jump_target:
                    target_wormhole_obj = unit.hyperdrive_component.wormhole_jump_target
                    target_sys_name_for_jump = target_wormhole_obj.exit_system_name
                    exit_wh_id_for_jump = target_wormhole_obj.exit_wormhole_id
                    if target_sys_name_for_jump and exit_wh_id_for_jump and target_sys_name_for_jump in self.game.galaxy.systems:
                        units_to_move.append((unit, ("system_jump", target_sys_name_for_jump)))
                    else:
                        logger.debug(f"  Wormhole Jump Failed (Queuing): Invalid target system ({target_sys_name_for_jump}) or incomplete exit wormhole data ({exit_wh_id_for_jump}) for {unit.name}")

                elif unit.hyperdrive_component and unit.hyperdrive_component.hex_jump_target:
                    target_hex_for_jump, target_position_for_jump = unit.hyperdrive_component.hex_jump_target
                    if target_hex_for_jump != current_hex and target_hex_for_jump in system.hexes:
                        units_to_move.append((unit, ("hex_jump", (target_hex_for_jump, target_position_for_jump))))

                elif unit.engines_component and unit.engines_component.move_target:
                    from custom_unit_templates import get_sublight_antimatter_cost_per_turn
                    raw_eff = getattr(unit.engines_component, 'effective_speed', None)
                    if isinstance(raw_eff, (int, float)):
                        effective_speed = float(raw_eff)
                    else:
                        effective_speed = float(getattr(unit.engines_component, 'speed', 100.0))
                    sublight_cost = get_sublight_antimatter_cost_per_turn(unit.hull_size, effective_speed)

                    # Engines consume antimatter per turn while moving
                    am_comp = unit.antimatter_component
                    if am_comp and am_comp.current_amount < sublight_cost:
                        logger.debug(f"   {unit.name} cannot move sub-light: Insufficient antimatter ({am_comp.current_amount:.1f}/{sublight_cost:.1f}).")
                        continue

                    if am_comp:
                        am_comp.consume(sublight_cost)

                    target_pos_in_sector = unit.engines_component.move_target
                    unit.position = move_towards_position(unit.position, target_pos_in_sector, effective_speed)
                    logger.debug(f"   {unit.name} moved to {unit.position} (sub-light, speed={effective_speed:.1f})")
                    
                    # Sync the active inhibitor field's location with the unit's new sub-light position.
                    if unit.inhibitor_component and unit.inhibitor_component.is_active:
                        current_hex_obj = system.hexes[unit.in_hex]
                        if current_hex_obj:
                            current_hex_obj.dynamic_inhibition_zones[unit.id] = Circle(
                                center=unit.position,
                                radius=unit.inhibitor_component.radius
                            )

                    dist_after_move = distance(unit.position, target_pos_in_sector)
                    if dist_after_move < 0.01:
                        logger.debug(f"   {unit.name} arrived at destination {target_pos_in_sector}")
                        unit.position = target_pos_in_sector
                        if unit.engines_component:
                            unit.engines_component.move_target = None

            for unit, movement_details in units_to_move:
                movement_type, movement_data = movement_details
                origin_system = self.game.galaxy.systems[unit.in_system]
                if not origin_system:
                    logger.debug(f"   FATAL Error: Could not find origin system {unit.in_system} for unit {unit.id}. Skipping move.")
                    continue

                if not unit.hyperdrive_component:
                    logger.debug(f"   LOGIC ERROR: Unit {unit.name} in units_to_move for jump but has no hyperdrive_component. Skipping.")
                    continue
                hd_comp = unit.hyperdrive_component

                if movement_type == "system_jump":
                    if hd_comp.jump_status == JumpStatus.CHARGING:
                        logger.debug(f"   {unit.name} system jump delayed: Hyperdrive charging ({hd_comp.recharge_time_remaining} turns left).")
                        continue 
                    
                    if hd_comp.jump_status == JumpStatus.JUMPING: 
                        logger.debug(f"   Warning: {unit.name} attempting system jump while already JUMPING. Resetting to READY.")
                        hd_comp.jump_status = JumpStatus.READY 
                    
                    if hd_comp.jump_status == JumpStatus.ERROR:
                        logger.debug(f"   {unit.name} cannot system jump: Hyperdrive in ERROR state. Order should re-evaluate or clear target.")
                        continue

                    if hd_comp.jump_status != JumpStatus.READY:
                        logger.debug(f"   Error: {unit.name} unexpected jump status {hd_comp.jump_status} for system jump. Skipping.")
                        continue
                        
                    hd_comp.jump_status = JumpStatus.JUMPING

                    target_sys_name = typing.cast(str, movement_data)
                    target_system = self.game.galaxy.systems[target_sys_name]
                    arrival_hex: typing.Optional[HexCoord] = None
                    exit_wormhole_obj_for_exec: typing.Optional[Wormhole] = None
                    can_jump = False

                    # Verify wormhole jump parameters are still valid at the moment of execution,
                    # as targets could have been cleared or altered since planning.
                    if not hd_comp.wormhole_jump_target:
                        logger.debug(f"   Error: Unit {unit.name} lost its wormhole_jump_target before system_jump execution. Aborting jump.")
                        hd_comp.jump_status = JumpStatus.ERROR 
                    elif not target_system:
                        logger.debug(f"   Error: Wormhole destination system {target_sys_name} not found. Jump aborted for {unit.name}.")
                        hd_comp.jump_status = JumpStatus.ERROR
                        hd_comp.wormhole_jump_target = None
                    else:
                        entry_wormhole = hd_comp.wormhole_jump_target
                        exit_wh_id = entry_wormhole.exit_wormhole_id
                        if not exit_wh_id:
                            logger.debug(f"   Error: Entry wormhole {entry_wormhole.id} for unit {unit.name} has no exit_wormhole_id. Aborting jump.")
                            hd_comp.jump_status = JumpStatus.ERROR
                            hd_comp.wormhole_jump_target = None
                        else:
                            exit_wormhole_obj_for_exec = self.game.galaxy.wormholes[exit_wh_id]
                            if not exit_wormhole_obj_for_exec:
                                logger.debug(f"   Error: Exit wormhole object with ID {exit_wh_id} not found in galaxy. Aborting jump for {unit.name}.")
                                hd_comp.jump_status = JumpStatus.ERROR
                                hd_comp.wormhole_jump_target = None
                            elif exit_wormhole_obj_for_exec.in_system != target_sys_name:
                                logger.debug(f"   Error: Exit wormhole {exit_wormhole_obj_for_exec.id} (in system {exit_wormhole_obj_for_exec.in_system}) does not actually lead to target system {target_sys_name}. Aborting jump for {unit.name}.")
                                hd_comp.jump_status = JumpStatus.ERROR
                                hd_comp.wormhole_jump_target = None
                            else:
                                arrival_hex = exit_wormhole_obj_for_exec.in_hex
                                can_jump = True
                    
                    if can_jump and arrival_hex and target_system and exit_wormhole_obj_for_exec:
                        # Check/consume antimatter for system jump
                        from custom_unit_templates import get_hyperdrive_system_jump_cost
                        sys_jump_cost = get_hyperdrive_system_jump_cost(unit.hull_size)
                        am_comp = unit.antimatter_component
                        if am_comp and am_comp.current_amount < sys_jump_cost:
                            logger.debug(f"   {unit.name} system jump failed: Insufficient antimatter ({am_comp.current_amount:.1f}/{sys_jump_cost:.1f}).")
                            hd_comp.jump_status = JumpStatus.ERROR
                            hd_comp.wormhole_jump_target = None
                            continue

                        moved = self.game.galaxy.move_unit_between_systems(
                            unit=unit,
                            origin_system_name=origin_system.name, 
                            destination_system_name=target_sys_name,
                            destination_hex=arrival_hex 
                        )
                        if moved:
                            unit.position = exit_wormhole_obj_for_exec.position 
                            if am_comp:
                                am_comp.consume(sys_jump_cost)
                            logger.debug(f"   {unit.name} completed wormhole jump from {origin_system.name} to {target_sys_name}, into hex {arrival_hex}")
                            
                            # Apply probabilistic damage for unstable wormholes (< 100 stability)
                            stability = entry_wormhole.stability
                            if stability < 100:
                                damage_chance = (100 - stability) / 100.0
                                if random.random() < damage_chance:
                                    # Calculate damage amount (10% to 25% of max hit points)
                                    damage_percentage = random.uniform(0.10, 0.25)
                                    damage_amount = int(unit.max_hit_points * damage_percentage)
                                    damage_amount = max(1, damage_amount)
                                    
                                    # 50% chance of component damage
                                    component_damaged = False
                                    if random.random() < 0.5:
                                        # Get eligible components (excluding Commander, and not destroyed)
                                        eligible_components = [
                                            comp_type for comp_type, comp in unit.components.items()
                                            if comp_type != Commander and not comp.is_destroyed
                                        ]
                                        if eligible_components:
                                            target_comp_type = random.choice(eligible_components)
                                            logger.debug(f"   Wormhole instability damages {unit.name}'s {target_comp_type.__name__} component for {damage_amount} damage.")
                                            spillover = unit.take_component_damage(target_comp_type, damage_amount)
                                            if spillover > 0:
                                                logger.debug(f"   {spillover} damage spilled over to {unit.name}'s hull.")
                                                unit.take_damage(spillover)
                                            component_damaged = True
                                            
                                    if not component_damaged:
                                        logger.debug(f"   Wormhole instability damages {unit.name}'s hull for {damage_amount} damage.")
                                        unit.take_damage(damage_amount)

                                    if getattr(self.game, 'gui', None) and getattr(unit.owner, 'is_human', False):
                                        self.game.gui.show_warning_dialog(
                                            f"Unit <b>{unit.name}</b> sustained structural damage jumping through unstable wormhole <b>{entry_wormhole.name}</b> ({damage_amount} damage)!",
                                            title="Wormhole Damage"
                                        )

                            hd_comp.start_recharge() # Clears targets and sets status to CHARGING
                        else:
                            logger.debug(f"   Error during final wormhole jump execution for {unit.name}. Jump aborted.")
                            hd_comp.jump_status = JumpStatus.ERROR
                            if hd_comp.wormhole_jump_target: # Ensure target is cleared on failure
                                 hd_comp.wormhole_jump_target = None
                    elif hd_comp.jump_status == JumpStatus.JUMPING: # If can_jump became false after setting to JUMPING
                        hd_comp.jump_status = JumpStatus.ERROR 
                        if hd_comp.wormhole_jump_target: # Ensure target is cleared
                             hd_comp.wormhole_jump_target = None
                
                elif movement_type == "hex_jump":
                    if hd_comp.jump_status == JumpStatus.CHARGING:
                        logger.debug(f"   {unit.name} hex jump delayed: Hyperdrive charging ({hd_comp.recharge_time_remaining} turns left).")
                        continue
            
                    if hd_comp.jump_status == JumpStatus.JUMPING:
                        logger.debug(f"   Warning: {unit.name} attempting hex jump while already JUMPING. Resetting to READY.")
                        hd_comp.jump_status = JumpStatus.READY
            
                    if hd_comp.jump_status == JumpStatus.ERROR:
                        logger.debug(f"   {unit.name} cannot hex jump: Hyperdrive in ERROR state.")
                        continue

                    if hd_comp.jump_status != JumpStatus.READY:
                        logger.debug(f"   Error: {unit.name} unexpected jump status {hd_comp.jump_status} for hex jump. Skipping.")
                        continue
                        
                    hd_comp.jump_status = JumpStatus.JUMPING

                    target_hex, target_pos = typing.cast(typing.Tuple[HexCoord, "Position"], movement_data)
                    
                    # Validate the hex jump parameters. The destination must be within the same system,
                    # within jump range, and not blocked by active inhibitor fields at the source or target.
                    if not hd_comp.hex_jump_target:
                        logger.debug(f"   Error: Unit {unit.name} lost its hex_jump_target before hex_jump execution. Aborting jump.")
                        hd_comp.jump_status = JumpStatus.ERROR
                        continue

                    if target_hex not in origin_system.hexes:
                        logger.debug(f"   Error: Unit {unit.name} hex_jump_target {target_hex} is invalid for system {origin_system.name}. Aborting.")
                        hd_comp.jump_status = JumpStatus.ERROR
                        hd_comp.hex_jump_target = None
                        continue

                    effective_jump_range = int(hd_comp.jump_range * unit.xp_multiplier(XP_JUMP_RANGE_BONUS))
                    if unit.in_hex and hex_distance(unit.in_hex, target_hex) > effective_jump_range:
                        logger.debug(f"   Error: Unit {unit.name} hex_jump to {target_hex} exceeds jump range of {effective_jump_range}. Aborting.")
                        hd_comp.jump_status = JumpStatus.ERROR
                        hd_comp.hex_jump_target = None
                        continue

                    jump_inhibited = False
                    origin_hex_obj = origin_system.hexes[unit.in_hex]
                    if origin_hex_obj:
                        for zone in origin_hex_obj.get_all_inhibition_zones():
                            if is_point_in_circle(unit.position, zone):
                                logger.debug(f"   Error: Unit {unit.name} cannot jump; origin position is inside an inhibition field.")
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
                                logger.debug(f"   Error: Unit {unit.name} cannot jump; destination position is inside an inhibition field.")
                                jump_inhibited = True
                                break
                    if jump_inhibited:
                        hd_comp.jump_status = JumpStatus.ERROR
                        hd_comp.hex_jump_target = None
                        continue
                        
                    # Check/consume antimatter for hex jump
                    from custom_unit_templates import get_hyperdrive_hex_jump_cost
                    hex_jump_cost = get_hyperdrive_hex_jump_cost(unit.hull_size)
                    am_comp = unit.antimatter_component
                    if am_comp and am_comp.current_amount < hex_jump_cost:
                        logger.debug(f"   {unit.name} hex jump failed: Insufficient antimatter ({am_comp.current_amount:.1f}/{hex_jump_cost:.1f}).")
                        hd_comp.jump_status = JumpStatus.ERROR
                        hd_comp.hex_jump_target = None
                        continue

                    moved = origin_system.move_unit_between_hexes(unit=unit, destination_hex=target_hex)
                    if moved:
                        unit.position = target_pos
                        if am_comp:
                            am_comp.consume(hex_jump_cost)
                        logger.debug(f"   {unit.name}(id:{unit.id}) completed hex jump to {target_hex}:{target_pos} in {origin_system.name} system.")
                        hd_comp.start_recharge() # Clears targets and sets status to CHARGING
                    else:
                        logger.debug(f"   Error during hex jump processing for {unit.name} to {target_hex}. Jump aborted.")
                        hd_comp.jump_status = JumpStatus.ERROR
                        if hd_comp.hex_jump_target: # Ensure target is cleared on failure
                             hd_comp.hex_jump_target = None

    def _process_population_growth(self):
        for system in self.game.galaxy.systems.values():
            for hexcoord, body in system.get_all_celestial_bodies():
                if isinstance(body, (Planet, Moon, ColonizableAsteroid)):
                    body.update_population()

    def _process_resource_generation(self, current_player):
        total_credits_generated = 0
        habitat_credits_generated = 0
        siphon_credits_generated = 0
        from unit_components.enums import SabotageType
        for system in self.game.galaxy.systems.values():
            for hexcoord, body in system.get_all_celestial_bodies():
                if isinstance(body, (Planet, Moon, ColonizableAsteroid)):
                    base_tax = body.population * TAX_RATE
                    if body.owner == current_player:
                        is_sab = False
                        if getattr(body, 'infiltrating_agents', None) and isinstance(body.infiltrating_agents, list) and len(body.infiltrating_agents) > 0:
                            if hasattr(body, 'is_sabotaged') and callable(body.is_sabotaged):
                                is_sab = bool(body.is_sabotaged(SabotageType.ECONOMY))
                        if is_sab:
                            credits_generated = base_tax * 0.5
                        else:
                            credits_generated = base_tax
                        current_player.credits += credits_generated
                        total_credits_generated += credits_generated
                    else:
                        from entities import are_enemies
                        if body.owner and are_enemies(current_player, body.owner) and getattr(body, 'infiltrating_agents', None) and isinstance(body.infiltrating_agents, list):
                            if any(getattr(a, 'owner', None) == current_player and getattr(a, 'active_sabotage', None) == SabotageType.ECONOMY for a in body.infiltrating_agents):
                                siphoned = base_tax * 0.25
                                current_player.credits += siphoned
                                siphon_credits_generated += siphoned

            for unit, _ in system.get_all_units():
                if unit.owner == current_player:
                    hab_comp = getattr(unit, 'civilian_habitat_component', None)
                    if hab_comp and not hab_comp.is_destroyed:
                        if hab_comp.is_active(self.game.galaxy):
                            bonus = hab_comp.economic_bonus
                            current_player.credits += bonus
                            habitat_credits_generated += bonus

        if total_credits_generated > 0:
            logger.debug(f"  {current_player.name} generated {total_credits_generated:.2f} credits from taxes.")
        if siphon_credits_generated > 0:
            logger.debug(f"  {current_player.name} siphoned {siphon_credits_generated:.2f} credits from infiltrated colonies.")
        if habitat_credits_generated > 0:
            logger.debug(f"  {current_player.name} generated {habitat_credits_generated:.2f} credits from civilian habitat bonuses.")

    def _process_unit_upkeep(self, current_player):
        """Deducts upkeep costs from the current player's credits for every owned unit.

        Upkeep = unit.current_hull_usage * UPKEEP_COST_PER_HULL_POINT per turn.
        Temporary units and strikecraft wings are excluded.
        Credits are clamped to zero (no negative balance).
        """
        total_upkeep = 0.0
        for system_obj in self.game.galaxy.systems.values():
            for unit, _ in system_obj.get_all_units():
                if unit.owner != current_player:
                    continue
                if unit.is_temporary:
                    continue
                if unit.hull_size == HullSize.STRIKECRAFT_WING:
                    continue
                total_upkeep += unit.current_hull_usage * UPKEEP_COST_PER_HULL_POINT

        if total_upkeep > 0:
            if current_player.credits < total_upkeep and getattr(self.game, 'gui', None) and getattr(current_player, 'is_human', False):
                self.game.gui.show_warning_dialog(
                    f"Treasury depleted! Unable to fully pay total unit upkeep of <b>{total_upkeep:.0f}</b> credits.",
                    title="Upkeep Shortage"
                )
            current_player.credits = max(0.0, current_player.credits - total_upkeep)
            logger.debug(f"  {current_player.name} paid {total_upkeep:.2f} credits in unit upkeep.")

    def _process_unit_updates(self, current_player):
        if current_player:
            for system_name, system_obj in self.game.galaxy.systems.items():
                all_units_in_system_for_final_update = system_obj.get_all_units()[:]
                for unit, u_hex in all_units_in_system_for_final_update:
                    if unit.owner == current_player:
                        unit.update()

    def _process_minefield_detonations(self):
        """Checks all units across all systems for contact with enemy minefields."""
        if not self.game.galaxy:
            return

        for system_name, system in self.game.galaxy.systems.items():
            for hex_coord, hex_obj in system.hexes.items():
                minefields = getattr(hex_obj, 'minefields', None)
                units = getattr(hex_obj, 'units', None)
                if not minefields or not units:
                    continue

                minefields_to_remove = []
                for minefield in list(minefields):
                    if minefield.mines_remaining <= 0:
                        minefields_to_remove.append(minefield)
                        continue

                    for unit in list(units):
                        if not minefield.can_target(unit):
                            continue

                        if distance(unit.position, minefield.position) <= minefield.detonation_radius:
                            minefield.detonate_against(unit)
                            if getattr(self.game, 'gui', None) and getattr(unit.owner, 'is_human', False):
                                self.game.gui.show_warning_dialog(
                                    f"Unit <b>{unit.name}</b> triggered an enemy minefield in sector <b>{hex_coord}</b>!",
                                    title="Minefield Detonation"
                                )
                            if minefield.mines_remaining <= 0:
                                minefields_to_remove.append(minefield)
                                break

                for mf in minefields_to_remove:
                    if hasattr(hex_obj, 'remove_minefield'):
                        hex_obj.remove_minefield(mf)
                    elif isinstance(minefields, list) and mf in minefields:
                        minefields.remove(mf)

    def _cleanup_dead_units(self):
        """Sweeps all systems and destroys any units with 0 or less hit points."""
        if not self.game.galaxy:
            return
        for system in self.game.galaxy.systems.values():
            for unit, _ in system.get_all_units():
                if unit.current_hit_points <= 0:
                    unit.destroy()



