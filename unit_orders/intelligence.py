import logging
import typing
from typing import Dict, Optional, Any, List, Tuple, TYPE_CHECKING

from geometry import distance, position_at_distance_from_target
from .base import Order, OrderStatus, OrderType
from .movement import MoveOrder
from unit_components.enums import SabotageType

if TYPE_CHECKING:
    from galaxy import Galaxy
    from entities import Unit, CelestialBody
    from unit_components.intelligence import Agent

logger = logging.getLogger(__name__)

INTELLIGENCE_OPERATIONAL_RANGE = 500.0


class InfiltrateUnitOrder(Order):
    """Order instructing an Intelligence unit to deploy a covert agent onto an enemy unit in range."""
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.INFILTRATE_UNIT, parameters, parent_order)

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        target_unit_id = self.parameters.get("target_unit_id")
        if target_unit_id is None:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] INFILTRATE_UNIT failed: no target_unit_id provided.")
            return

        target_unit = galaxy_ref.get_unit_by_id(target_unit_id)
        if not target_unit:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] INFILTRATE_UNIT failed: target unit {target_unit_id} not found.")
            return

        from entities import are_allies, are_enemies
        if are_allies(self.unit.owner, target_unit.owner):
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] INFILTRATE_UNIT failed: cannot infiltrate friendly or allied unit.")
            return

        intel_comp = getattr(self.unit, 'intelligence_component', None)
        if not intel_comp or intel_comp.is_destroyed:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] INFILTRATE_UNIT failed: unit has no functioning IntelligenceComponent.")
            return

        if intel_comp.available_agents <= 0:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] INFILTRATE_UNIT failed: no available agents remaining.")
            return

        # Check if in same system and hex
        if self.unit.in_system != target_unit.in_system or self.unit.in_hex != target_unit.in_hex:
            if not self.has_active_sub_orders():
                dest_pos = position_at_distance_from_target(target_unit.position, self.unit.position, INTELLIGENCE_OPERATIONAL_RANGE - 50.0)
                move_sub_order = MoveOrder(
                    self.unit,
                    parameters={"system": target_unit.in_system, "hex": target_unit.in_hex, "position": dest_pos},
                    parent_order=self
                )
                self.add_sub_order(move_sub_order)
            return

        # In same sector: check distance
        dist = distance(self.unit.position, target_unit.position)
        if dist > INTELLIGENCE_OPERATIONAL_RANGE:
            if not self.has_active_sub_orders():
                dest_pos = position_at_distance_from_target(target_unit.position, self.unit.position, INTELLIGENCE_OPERATIONAL_RANGE - 50.0)
                move_sub_order = MoveOrder(
                    self.unit,
                    parameters={"system": target_unit.in_system, "hex": target_unit.in_hex, "position": dest_pos},
                    parent_order=self
                )
                self.add_sub_order(move_sub_order)
            return

        # Within operational range: deploy agent
        agent = intel_comp.deploy_agent(target_unit)
        if agent:
            self.status = OrderStatus.COMPLETED
            logger.info(f"[{self.unit.name}] Successfully infiltrated enemy unit {target_unit.name} with Agent {agent.id}!")
        else:
            self.status = OrderStatus.FAILED


class InfiltratePlanetOrder(Order):
    """Order instructing an Intelligence unit to deploy a covert agent onto an enemy colonized celestial body."""
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.INFILTRATE_PLANET, parameters, parent_order)

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        target_body_id = self.parameters.get("target_body_id")
        target_body_name = self.parameters.get("target_body_name")
        target_system = self.parameters.get("system", self.unit.in_system)
        target_hex = self.parameters.get("hex", self.unit.in_hex)

        target_body = None
        sys_obj = galaxy_ref.systems.get(target_system)
        if sys_obj:
            for hex_coord, body in sys_obj.get_all_celestial_bodies():
                if (target_body_id is not None and body.id == target_body_id) or (target_body_name and body.name == target_body_name):
                    target_body = body
                    target_hex = hex_coord
                    break

        if not target_body:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] INFILTRATE_PLANET failed: celestial body not found.")
            return

        body_owner = getattr(target_body, 'owner', None)
        from entities import are_allies
        if not body_owner or are_allies(self.unit.owner, body_owner):
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] INFILTRATE_PLANET failed: celestial body is unowned or friendly/allied.")
            return

        intel_comp = getattr(self.unit, 'intelligence_component', None)
        if not intel_comp or intel_comp.is_destroyed:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] INFILTRATE_PLANET failed: unit has no functioning IntelligenceComponent.")
            return

        if intel_comp.available_agents <= 0:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] INFILTRATE_PLANET failed: no available agents remaining.")
            return

        if self.unit.in_system != target_system or self.unit.in_hex != target_hex:
            if not self.has_active_sub_orders():
                dest_pos = position_at_distance_from_target(target_body.position, self.unit.position, INTELLIGENCE_OPERATIONAL_RANGE - 50.0)
                move_sub_order = MoveOrder(
                    self.unit,
                    parameters={"system": target_system, "hex": target_hex, "position": dest_pos},
                    parent_order=self
                )
                self.add_sub_order(move_sub_order)
            return

        dist = distance(self.unit.position, target_body.position)
        if dist > INTELLIGENCE_OPERATIONAL_RANGE:
            if not self.has_active_sub_orders():
                dest_pos = position_at_distance_from_target(target_body.position, self.unit.position, INTELLIGENCE_OPERATIONAL_RANGE - 50.0)
                move_sub_order = MoveOrder(
                    self.unit,
                    parameters={"system": target_system, "hex": target_hex, "position": dest_pos},
                    parent_order=self
                )
                self.add_sub_order(move_sub_order)
            return

        agent = intel_comp.deploy_agent(target_body)
        if agent:
            self.status = OrderStatus.COMPLETED
            logger.info(f"[{self.unit.name}] Successfully infiltrated colonized body {target_body.name} with Agent {agent.id}!")
        else:
            self.status = OrderStatus.FAILED


class RelocateAgentOrder(Order):
    """Order relocating an agent from one infiltrated host to another within operational range."""
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.RELOCATE_AGENT, parameters, parent_order)

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        agent_id = self.parameters.get("agent_id")
        target_type = self.parameters.get("target_type", "unit")  # "unit" or "planet"
        dest_id = self.parameters.get("destination_id")

        if agent_id is None or dest_id is None:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] RELOCATE_AGENT failed: missing agent_id or destination_id.")
            return

        # Find agent and source target
        agent: Optional['Agent'] = None
        source_target = None
        source_pos = None
        source_sys = None
        source_hex = None

        for sys_name, sys_obj in galaxy_ref.systems.items():
            for unit, u_hex in sys_obj.get_all_units():
                if hasattr(unit, 'infiltrating_agents'):
                    for a in unit.infiltrating_agents:
                        if a.id == agent_id:
                            agent = a
                            source_target = unit
                            source_pos = unit.position
                            source_sys = sys_name
                            source_hex = u_hex
                            break
            if agent:
                break
            for h_coord, body in sys_obj.get_all_celestial_bodies():
                if hasattr(body, 'infiltrating_agents'):
                    for a in body.infiltrating_agents:
                        if a.id == agent_id:
                            agent = a
                            source_target = body
                            source_pos = body.position
                            source_sys = sys_name
                            source_hex = h_coord
                            break
            if agent:
                break

        if not agent or not source_target:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] RELOCATE_AGENT failed: agent {agent_id} not found.")
            return

        # Find destination target
        dest_target = None
        if target_type == "unit":
            dest_target = galaxy_ref.get_unit_by_id(dest_id)
        else:
            sys_obj = galaxy_ref.systems.get(source_sys)
            if sys_obj:
                for h_coord, body in sys_obj.get_all_celestial_bodies():
                    if body.id == dest_id:
                        dest_target = body
                        break

        if not dest_target:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] RELOCATE_AGENT failed: destination target {dest_id} not found.")
            return

        dest_owner = getattr(dest_target, 'owner', None)
        from entities import are_allies
        if not dest_owner or are_allies(self.unit.owner, dest_owner):
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] RELOCATE_AGENT failed: destination target is unowned or friendly/allied.")
            return

        # Check range between source and destination
        if source_sys != dest_target.in_system or source_hex != dest_target.in_hex:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] RELOCATE_AGENT failed: destination is in different sector.")
            return

        if distance(source_pos, dest_target.position) > INTELLIGENCE_OPERATIONAL_RANGE:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] RELOCATE_AGENT failed: destination target out of range (> {INTELLIGENCE_OPERATIONAL_RANGE}).")
            return

        # Transfer agent
        source_target.remove_agent(agent)
        agent.attached_to = dest_target
        agent.active_sabotage = None
        agent.is_discovered = False
        dest_target.infiltrating_agents.append(agent)
        self.status = OrderStatus.COMPLETED
        logger.info(f"Agent {agent.id} successfully relocated from {source_target.name} to {dest_target.name}.")


class SabotageOrder(Order):
    """Order commanding an infiltrated agent to sabotage a specific system or colony function."""
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.SABOTAGE, parameters, parent_order)

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        agent_id = self.parameters.get("agent_id")
        sabotage_type_val = self.parameters.get("sabotage_type")

        if agent_id is None or not sabotage_type_val:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] SABOTAGE order failed: missing agent_id or sabotage_type.")
            return

        sab_type = SabotageType(sabotage_type_val) if isinstance(sabotage_type_val, str) else sabotage_type_val

        # Locate agent
        agent: Optional['Agent'] = None
        target_obj = None

        for sys_name, sys_obj in galaxy_ref.systems.items():
            for u, _ in sys_obj.get_all_units():
                if hasattr(u, 'infiltrating_agents'):
                    for a in u.infiltrating_agents:
                        if a.id == agent_id:
                            agent = a
                            target_obj = u
                            break
            if agent:
                break
            for _, b in sys_obj.get_all_celestial_bodies():
                if hasattr(b, 'infiltrating_agents'):
                    for a in b.infiltrating_agents:
                        if a.id == agent_id:
                            agent = a
                            target_obj = b
                            break
            if agent:
                break

        if not agent or not target_obj:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] SABOTAGE order failed: agent {agent_id} not found.")
            return

        success = target_obj.apply_sabotage(agent, sab_type)
        if success:
            self.status = OrderStatus.COMPLETED
            logger.info(f"Agent {agent.id} commenced sabotage {sab_type.name} on {target_obj.name}.")
        else:
            self.status = OrderStatus.FAILED


class CISweepOrder(Order):
    """Order instructing a Counter-Intelligence vessel to scan the area for enemy agents."""
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.CI_SWEEP, parameters, parent_order)

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        from constants import CI_SWEEP_CREDIT_COST, CI_SWEEP_ANTIMATTER_COST, CI_SWEEP_COOLDOWN_TURNS

        intel_comp = getattr(self.unit, 'intelligence_component', None)
        if not intel_comp or intel_comp.is_destroyed or not intel_comp.has_counter_intelligence:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] CI_SWEEP failed: unit lacks functional Counter-Intelligence suite.")
            return

        if intel_comp.ci_cooldown_remaining > 0:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] CI_SWEEP failed: Counter-Intelligence suite is on cooldown ({intel_comp.ci_cooldown_remaining} turns remaining).")
            return

        if not self.unit.owner or getattr(self.unit.owner, 'credits', 0.0) < CI_SWEEP_CREDIT_COST:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] CI_SWEEP failed: insufficient empire credits (requires {CI_SWEEP_CREDIT_COST}).")
            return

        am_comp = getattr(self.unit, 'antimatter_component', None)
        if not am_comp or am_comp.is_destroyed or am_comp.current_amount < CI_SWEEP_ANTIMATTER_COST:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] CI_SWEEP failed: insufficient antimatter (requires {CI_SWEEP_ANTIMATTER_COST}).")
            return

        sys_obj = galaxy_ref.systems.get(self.unit.in_system)
        if not sys_obj:
            self.status = OrderStatus.FAILED
            return

        hex_obj = sys_obj.hexes.get(self.unit.in_hex)
        if not hex_obj:
            self.status = OrderStatus.FAILED
            return

        # Deduct costs and apply cooldown
        self.unit.owner.credits -= CI_SWEEP_CREDIT_COST
        am_comp.consume(CI_SWEEP_ANTIMATTER_COST)
        intel_comp.ci_cooldown_remaining = CI_SWEEP_COOLDOWN_TURNS

        discovered_count = 0
        from entities import are_allies, are_enemies
        for target_u in hex_obj.units:
            if are_allies(self.unit.owner, target_u.owner) and hasattr(target_u, 'infiltrating_agents'):
                if distance(self.unit.position, target_u.position) <= INTELLIGENCE_OPERATIONAL_RANGE:
                    for agent in target_u.infiltrating_agents:
                        if are_enemies(self.unit.owner, agent.owner):
                            agent.is_discovered = True
                            discovered_count += 1

        for body in hex_obj.celestial_bodies:
            body_owner = getattr(body, 'owner', None)
            if are_allies(self.unit.owner, body_owner) and hasattr(body, 'infiltrating_agents'):
                if distance(self.unit.position, body.position) <= INTELLIGENCE_OPERATIONAL_RANGE:
                    for agent in body.infiltrating_agents:
                        if are_enemies(self.unit.owner, agent.owner):
                            agent.is_discovered = True
                            discovered_count += 1

        self.status = OrderStatus.COMPLETED
        logger.info(f"[{self.unit.name}] CI Sweep complete! Discovered {discovered_count} enemy agent(s). (Cost: {CI_SWEEP_CREDIT_COST}c, {CI_SWEEP_ANTIMATTER_COST}am, Cooldown: {CI_SWEEP_COOLDOWN_TURNS}t)")


class EliminateAgentOrder(Order):
    """Order instructing a Counter-Intelligence vessel to eliminate a discovered enemy agent."""
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.ELIMINATE_AGENT, parameters, parent_order)

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        agent_id = self.parameters.get("agent_id")
        if agent_id is None:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] ELIMINATE_AGENT failed: no agent_id provided.")
            return

        intel_comp = getattr(self.unit, 'intelligence_component', None)
        if not intel_comp or intel_comp.is_destroyed or not intel_comp.has_counter_intelligence:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] ELIMINATE_AGENT failed: unit lacks Counter-Intelligence suite.")
            return

        # Find agent & host
        agent: Optional['Agent'] = None
        host_target = None
        host_pos = None
        host_sys = None
        host_hex = None

        for sys_name, sys_obj in galaxy_ref.systems.items():
            for u, u_hex in sys_obj.get_all_units():
                if hasattr(u, 'infiltrating_agents'):
                    for a in u.infiltrating_agents:
                        if a.id == agent_id:
                            agent = a
                            host_target = u
                            host_pos = u.position
                            host_sys = sys_name
                            host_hex = u_hex
                            break
            if agent:
                break
            for h_coord, b in sys_obj.get_all_celestial_bodies():
                if hasattr(b, 'infiltrating_agents'):
                    for a in b.infiltrating_agents:
                        if a.id == agent_id:
                            agent = a
                            host_target = b
                            host_pos = b.position
                            host_sys = sys_name
                            host_hex = h_coord
                            break
            if agent:
                break

        if not agent or not host_target:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] ELIMINATE_AGENT failed: agent {agent_id} not found.")
            return

        if self.unit.in_system != host_sys or self.unit.in_hex != host_hex:
            if not self.has_active_sub_orders():
                dest_pos = position_at_distance_from_target(host_pos, self.unit.position, INTELLIGENCE_OPERATIONAL_RANGE - 50.0)
                move_sub_order = MoveOrder(
                    self.unit,
                    parameters={"system": host_sys, "hex": host_hex, "position": dest_pos},
                    parent_order=self
                )
                self.add_sub_order(move_sub_order)
            return

        dist = distance(self.unit.position, host_pos)
        if dist > INTELLIGENCE_OPERATIONAL_RANGE:
            if not self.has_active_sub_orders():
                dest_pos = position_at_distance_from_target(host_pos, self.unit.position, INTELLIGENCE_OPERATIONAL_RANGE - 50.0)
                move_sub_order = MoveOrder(
                    self.unit,
                    parameters={"system": host_sys, "hex": host_hex, "position": dest_pos},
                    parent_order=self
                )
                self.add_sub_order(move_sub_order)
            return

        # Eliminate agent
        host_target.remove_agent(agent)
        agent.attached_to = None
        # Notify owner's component if still linked
        owner_unit = agent.source_unit
        if owner_unit and getattr(owner_unit, 'intelligence_component', None):
            owner_unit.intelligence_component.remove_agent_reference(agent)

        self.status = OrderStatus.COMPLETED
        logger.info(f"[{self.unit.name}] Successfully neutralized and eliminated Agent {agent.id} from {host_target.name}!")


class ExtractAgentOrder(Order):
    """Order extracting an agent back into the parent Intelligence unit."""
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.EXTRACT_AGENT, parameters, parent_order)

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        agent_id = self.parameters.get("agent_id")
        if agent_id is None:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] EXTRACT_AGENT failed: no agent_id provided.")
            return

        intel_comp = getattr(self.unit, 'intelligence_component', None)
        if not intel_comp or intel_comp.is_destroyed:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] EXTRACT_AGENT failed: unit lacks functional IntelligenceComponent.")
            return

        # Locate agent
        agent: Optional['Agent'] = None
        host_target = None
        host_pos = None
        host_sys = None
        host_hex = None

        for sys_name, sys_obj in galaxy_ref.systems.items():
            for u, u_hex in sys_obj.get_all_units():
                if hasattr(u, 'infiltrating_agents'):
                    for a in u.infiltrating_agents:
                        if a.id == agent_id:
                            agent = a
                            host_target = u
                            host_pos = u.position
                            host_sys = sys_name
                            host_hex = u_hex
                            break
            if agent:
                break
            for h_coord, b in sys_obj.get_all_celestial_bodies():
                if hasattr(b, 'infiltrating_agents'):
                    for a in b.infiltrating_agents:
                        if a.id == agent_id:
                            agent = a
                            host_target = b
                            host_pos = b.position
                            host_sys = sys_name
                            host_hex = h_coord
                            break
            if agent:
                break

        if not agent or not host_target:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] EXTRACT_AGENT failed: agent {agent_id} not found.")
            return

        if self.unit.in_system != host_sys or self.unit.in_hex != host_hex:
            if not self.has_active_sub_orders():
                dest_pos = position_at_distance_from_target(host_pos, self.unit.position, INTELLIGENCE_OPERATIONAL_RANGE - 50.0)
                move_sub_order = MoveOrder(
                    self.unit,
                    parameters={"system": host_sys, "hex": host_hex, "position": dest_pos},
                    parent_order=self
                )
                self.add_sub_order(move_sub_order)
            return

        dist = distance(self.unit.position, host_pos)
        if dist > INTELLIGENCE_OPERATIONAL_RANGE:
            if not self.has_active_sub_orders():
                dest_pos = position_at_distance_from_target(host_pos, self.unit.position, INTELLIGENCE_OPERATIONAL_RANGE - 50.0)
                move_sub_order = MoveOrder(
                    self.unit,
                    parameters={"system": host_sys, "hex": host_hex, "position": dest_pos},
                    parent_order=self
                )
                self.add_sub_order(move_sub_order)
            return

        success = intel_comp.retrieve_agent(agent)
        if success:
            self.status = OrderStatus.COMPLETED
            logger.info(f"[{self.unit.name}] Successfully extracted Agent {agent.id} back into unit.")
        else:
            self.status = OrderStatus.FAILED
