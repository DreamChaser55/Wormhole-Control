"""Validated command gateway from model output to authoritative game orders."""

from __future__ import annotations

from dataclasses import dataclass
import uuid
import logging
from typing import Any, Callable

from .contracts import CommandBatch, ContractError
from .command_spec import COMMAND_SPECS, validate_command, MAX_COMMANDS
from .rules import (
    compatible_docking_component,
    compatible_hangar_component,
    compatible_strikecraft_bay_component,
    has_operational_engines,
    is_colonizable_body,
    is_mining_target,
    is_self_owned,
    is_star,
    is_antimatter_source,
)
from .intelligence import (
    discovered_enemy_agent_hosts,
    find_agent_host,
    host_kind,
    relation as intelligence_relation,
    sabotage_types_for_host,
)


logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class CommandError:
    command_index: int
    code: str
    message: str


@dataclass(frozen=True)
class CommandResult:
    accepted: bool
    applied_count: int = 0
    receipts: tuple[str, ...] = ()
    errors: tuple[CommandError, ...] = ()
    failure_stage: str | None = "preflight"
    retryable: bool = True
    operation_results: tuple[dict[str, Any], ...] = ()
    may_have_partial_effects: bool = False
    requires_observation: bool = False


class _Rejected(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _clear_explicit_orders(commander: Any) -> None:
    method = getattr(commander, "clear_explicit_orders", None)
    if callable(method):
        method()
    else:  # Compatibility for integrations implementing the pre-3.1 surface.
        commander.clear_orders()


def _stop_and_idle(commander: Any) -> None:
    method = getattr(commander, "stop_and_idle", None)
    if callable(method):
        method()
        return
    commander.clear_orders()
    from unit_components import UnitStance
    commander.stance = UnitStance.DO_NOTHING


def _set_stance(commander: Any, stance: Any) -> None:
    method = getattr(commander, "set_stance", None)
    if callable(method):
        method(stance)
    else:
        commander.stance = stance


@dataclass
class _Prepared:
    apply: Callable[[], None]
    receipt: str
    command_index: int = -1
    unit_id: int | None = None
    command_type: str = ""
    order_id: str | None = None


class _BatchProjection:
    """Track guaranteed batch effects without mutating authoritative state."""

    def __init__(self, game: Any, player: Any):
        self.game = game
        self.player = player
        self._order_ledger = {}
        self._ledger_units = {}
        self._refunds = 0.0
        self._settled_cargo = {}
        self._settled_population = {}
        self._settled_docks = {}
        self._unavailable_units = set()
        self._edit_target = None
        self._cargo: dict[int, float] = {}
        self._source_population: dict[int, float] = {}
        self._credits = float(getattr(player, "credits", 0))
        self._docking_slots: dict[int, int] = {}
        self._inhibitor_states: dict[int, bool] = {}
        self._cloaking_states: dict[int, bool] = {}
        self._agent_hosts: dict[int, Any] = {}
        self._agent_objects: dict[int, Any] = {}
        self._agent_sabotage: dict[int, str | None] = {}
        self._ci_credit_spend = 0.0
        self._ci_antimatter: dict[int, float] = {}
        self._ci_cooldowns: dict[int, int] = {}
        self._inhibitor_static_zones: dict[tuple[str, tuple[int, int]], list[Any]] = {}
        self._inhibitor_dynamic_zones: dict[
            tuple[str, tuple[int, int]], dict[int, Any]
        ] = {}

    def _ensure_orders(self, unit):
        if unit.id in self._order_ledger:
            return
        commander = unit.commander_component
        roots = [getattr(commander, "current_order", None), *list(getattr(commander, "orders_queue", []))]
        self._ledger_units[unit.id] = unit
        self._order_ledger[unit.id] = [
            {"id": getattr(o, "public_id", str(id(o))), "type": o.order_type.name.lower(),
             "parameters": dict(getattr(o, "parameters", {})), "order": o,
             "started": o is getattr(commander, "current_order", None),
             "settled": getattr(o.status, "name", "") not in {"PENDING", "IN_PROGRESS"}}
            for o in roots if o is not None]

    def target_order(self, command, unit):
        self._ensure_orders(unit)
        for entry in self._order_ledger[unit.id]:
            if entry["id"] == command.order_id and entry["order"] is not None and not entry.get("settled"):
                return entry
        raise _Rejected("order_unavailable", "The order is unavailable.")

    def before(self, command, units):
        for unit in units:
            if unit.id in self._unavailable_units:
                raise _Rejected("unit_unavailable", "A selected unit is unavailable after preceding operations.")
            self._ensure_orders(unit)
            removed = []
            if command.type == "cancel_order":
                entry = self.target_order(command, unit)
                self._edit_target = entry
                removed = [entry]
                self._order_ledger[unit.id].remove(entry)
            elif command.type in {"cancel_orders", "clear_explicit_orders"} or (COMMAND_SPECS[command.type].queued and not command.queue):
                removed = self._order_ledger[unit.id]
                self._order_ledger[unit.id] = []
            for entry in removed:
                order = entry["order"]
                if order is not None and hasattr(order, "refundable_credits"):
                    self._refunds += order.refundable_credits(self.player.id)
            if command.type == "cancel_order":
                self._settle_front(unit)
        self._rebuild()

    def _rebuild(self):
        self._cargo = {}
        self._source_population = {}
        self._credits = float(getattr(self.player, "credits", 0)) + self._refunds - self._ci_credit_spend
        self._docking_slots = dict(self._settled_docks)
        for unit_id, entries in self._order_ledger.items():
            unit = self._ledger_units[unit_id]
            cargo = self._live_cargo(unit) + self._settled_cargo.get(unit_id, 0)
            for entry in entries:
                if entry.get("settled"):
                    continue
                kind, params, order = entry["type"], entry["parameters"], entry["order"]
                if kind == "load_colonists":
                    amount = float(params.get("amount", 0))
                    cargo += amount
                    source = self.game.galaxy.get_celestial_body_by_id(params.get("target_id"))
                    if source is not None:
                        self._source_population.setdefault(source.id, float(source.population) - self._settled_population.get(source.id, 0))
                        self._source_population[source.id] -= amount
                elif kind == "colonize":
                    cargo = 0
                elif kind == "construct" and (order is None or order.status.name == "PENDING"):
                    build = unit.constructor_component.can_build(params.get("unit_template_name"))
                    if build:
                        self._credits -= build.cost_credits
                elif kind in {"dock", "dock_in_hangar", "dock_in_strikecraft_bay"}:
                    target = self.game.galaxy.get_unit_by_id(params.get("target_carrier_id"))
                    if target is not None:
                        comp = compatible_docking_component(unit, target)
                        if comp:
                            key = id(comp)
                            self._docking_slots.setdefault(key, comp.max_slots - comp.get_used_slots())
                            self._docking_slots[key] -= 1
            self._cargo[unit_id] = cargo

    def cargo_for(self, unit):
        self._ensure_orders(unit)
        if unit.id not in self._cargo:
            self._rebuild()
        return self._cargo.get(unit.id, self._live_cargo(unit))

    def validate_load(self, command: Any, units: list[Any], body: Any) -> None:
        amount = float(command.amount or 0)
        if amount <= 0:
            raise _Rejected("invalid_value", "load_colonists requires a positive amount.")
        for unit in units:
            self.cargo_for(unit)
        available = self._source_population.setdefault(
            body.id, float(getattr(body, "population", 0)) - self._settled_population.get(body.id, 0)
        )
        required = amount * len(units)
        if required > available:
            raise _Rejected(
                "insufficient_population",
                f"Body {body.id} has only {available:g} colonists available; "
                f"this command requires {required:g}.",
            )
        for unit in units:
            colony = unit.colony_component
            capacity = float(getattr(colony, "max_cargo", 0))
            remaining = capacity - self.cargo_for(unit)
            if amount > remaining:
                raise _Rejected(
                    "insufficient_capacity",
                    f"Unit {unit.id} can load at most {max(0, remaining):g} colonists.",
                )

    def validate_construct(self, command: Any, units: list[Any]) -> None:
        if not command.template_name:
            return
        costs = []
        for unit in units:
            constructor = getattr(unit, "constructor_component", None)
            buildable = (
                constructor.can_build(command.template_name) if constructor else None
            )
            if buildable is not None:
                costs.append(float(buildable.cost_credits))
        required = sum(costs)
        if required > self._credits:
            raise _Rejected(
                "insufficient_resources",
                f"Construction requires {required:g} credits but only "
                f"{self._credits:g} remain in this batch.",
            )

    def validate_dock_in_hangar(self, command: Any, units: list[Any], target: Any) -> None:
        components = [compatible_hangar_component(unit, target) for unit in units]
        if any(component is None for component in components):
            raise _Rejected(
                "invalid_target",
                "The target carrier has no compatible free hangar slots.",
            )
        component = components[0]
        key = id(component)
        available = self._docking_slots.setdefault(
            key,
            int(getattr(component, "max_slots", 0))
            - int(component.get_used_slots()),
        )
        if len(units) > available:
            raise _Rejected(
                "insufficient_capacity",
                f"The target carrier has only {available} compatible hangar slots available.",
            )

    def validate_dock_in_strikecraft_bay(self, command: Any, units: list[Any], target: Any) -> None:
        components = [compatible_strikecraft_bay_component(unit, target) for unit in units]
        if any(component is None for component in components):
            raise _Rejected(
                "invalid_target",
                "The target carrier has no compatible free strikecraft bay slots.",
            )
        component = components[0]
        key = id(component)
        available = self._docking_slots.setdefault(
            key,
            int(getattr(component, "max_slots", 0))
            - int(component.get_used_slots()),
        )
        if len(units) > available:
            raise _Rejected(
                "insufficient_capacity",
                f"The target carrier has only {available} compatible strikecraft bay slots available.",
            )

    def validate_dock(self, command: Any, units: list[Any], target: Any) -> None:
        components = [compatible_docking_component(unit, target) for unit in units]
        if any(component is None for component in components):
            raise _Rejected(
                "invalid_target",
                "The docking target has no compatible free carrier slots.",
            )
        component = components[0]
        if any(candidate is not component for candidate in components):
            raise _Rejected(
                "invalid_target", "The selected units require different carrier bays."
            )
        key = id(component)
        available = self._docking_slots.setdefault(
            key,
            int(getattr(component, "max_slots", 0))
            - int(component.get_used_slots()),
        )
        if len(units) > available:
            raise _Rejected(
                "insufficient_capacity",
                f"The docking target has only {available} compatible slots available.",
            )

    def plan_inhibitor_toggles(self, units: list[Any]) -> list[tuple[Any, bool]]:
        """Validate and project a group of immediate inhibitor toggles atomically."""
        for unit in units:
            if getattr(unit, "inhibitor_component", None) is None:
                raise _Rejected(
                    "capability_unavailable", f"Unit {unit.id} has no inhibitor."
                )
            self._ensure_inhibitor_hex(unit)

        projected_states = dict(self._inhibitor_states)
        projected_dynamic = {
            key: dict(zones) for key, zones in self._inhibitor_dynamic_zones.items()
        }
        planned: list[tuple[Any, bool]] = []

        for unit in units:
            component = unit.inhibitor_component

            key = self._inhibitor_key(unit)
            current_active = projected_states.setdefault(
                unit.id, bool(getattr(component, "is_active", False))
            )
            turn_on = not current_active
            existing_zones = (
                self._inhibitor_static_zones[key]
                + list(projected_dynamic[key].values())
            )
            check = component.check_state_change(
                turn_on,
                self.game.galaxy,
                existing_zones=existing_zones,
            )
            if not check.allowed:
                raise _Rejected(
                    check.code or "inhibitor_unavailable",
                    f"Unit {unit.id} cannot toggle its inhibitor: {check.message}",
                )

            if turn_on:
                projected_dynamic[key][unit.id] = check.proposed_field
            else:
                projected_dynamic[key].pop(unit.id, None)
            projected_states[unit.id] = turn_on
            planned.append((unit, turn_on))

        self._inhibitor_states = projected_states
        self._inhibitor_dynamic_zones = projected_dynamic
        return planned

    def owned_agent(self, agent_id: int) -> tuple[Any, Any]:
        if agent_id not in self._agent_objects:
            agent, host = find_agent_host(self.game.galaxy, agent_id)
            if (
                agent is None
                or intelligence_relation(self.player, getattr(agent, "owner", None)) != "self"
            ):
                raise _Rejected("agent_unavailable", "The agent is unavailable.")
            self._agent_objects[agent_id] = agent
            self._agent_hosts[agent_id] = host
            sabotage = getattr(agent, "active_sabotage", None)
            self._agent_sabotage[agent_id] = getattr(sabotage, "value", None)
        return self._agent_objects[agent_id], self._agent_hosts[agent_id]

    def project_sabotage(self, agent_id: int, sabotage_type: str) -> tuple[Any, Any]:
        agent, host = self.owned_agent(agent_id)
        if sabotage_type not in sabotage_types_for_host(host):
            raise _Rejected("invalid_value", "That sabotage type is unavailable for this host.")
        self._agent_sabotage[agent_id] = sabotage_type
        return agent, host

    def project_relocation(self, agent_id: int, target: Any) -> tuple[Any, Any]:
        from geometry import distance
        from unit_orders.intelligence import INTELLIGENCE_OPERATIONAL_RANGE

        agent, host = self.owned_agent(agent_id)
        if target is host or host_kind(target) not in {"unit", "colony"}:
            raise _Rejected("target_unavailable", "The target is unavailable.")
        if intelligence_relation(self.player, getattr(target, "owner", None)) != "enemy":
            raise _Rejected("target_unavailable", "The target is unavailable.")
        if (
            getattr(host, "in_system", None) != getattr(target, "in_system", None)
            or getattr(host, "in_hex", None) != getattr(target, "in_hex", None)
            or distance(host.position, target.position) > INTELLIGENCE_OPERATIONAL_RANGE
        ):
            raise _Rejected("target_unavailable", "The target is unavailable.")
        self._agent_hosts[agent_id] = target
        self._agent_sabotage[agent_id] = None
        return agent, host

    def plan_ci_sweeps(self, units: list[Any]) -> list[Any]:
        from constants import CI_SWEEP_ANTIMATTER_COST, CI_SWEEP_CREDIT_COST, CI_SWEEP_COOLDOWN_TURNS

        planned = []
        for unit in units:
            intelligence = getattr(unit, "intelligence_component", None)
            storage = getattr(unit, "antimatter_component", None)
            cooldown = self._ci_cooldowns.get(
                unit.id, int(getattr(intelligence, "ci_cooldown_remaining", 0))
            )
            amount = self._ci_antimatter.get(
                unit.id, float(getattr(storage, "current_amount", 0)) if storage else 0.0
            )
            if (
                intelligence is None
                or getattr(intelligence, "is_destroyed", False)
                or not getattr(intelligence, "has_counter_intelligence", False)
            ):
                raise _Rejected("capability_unavailable", f"Unit {unit.id} has no functioning Counter-Intelligence suite.")
            if cooldown > 0:
                raise _Rejected("capability_unavailable", f"Unit {unit.id} Counter-Intelligence is on cooldown.")
            if self._credits < CI_SWEEP_CREDIT_COST:
                raise _Rejected("insufficient_resources", "Counter-Intelligence sweep requires more credits than remain in this batch.")
            if storage is None or getattr(storage, "is_destroyed", False) or amount < CI_SWEEP_ANTIMATTER_COST:
                raise _Rejected("insufficient_resources", f"Unit {unit.id} lacks antimatter for a Counter-Intelligence sweep.")
            self._ci_credit_spend += CI_SWEEP_CREDIT_COST
            self._credits -= CI_SWEEP_CREDIT_COST
            self._ci_antimatter[unit.id] = amount - CI_SWEEP_ANTIMATTER_COST
            self._ci_cooldowns[unit.id] = CI_SWEEP_COOLDOWN_TURNS
            planned.append(unit)
        return planned

    def record(self, command, units):
        if command.type == "append_patrol_waypoints":
            entry = self.target_order(command, units[0])
            entry["parameters"]["waypoints"] = [*entry["parameters"].get("waypoints", []), *command.waypoints]
        elif COMMAND_SPECS[command.type].queued:
            params = {"target_id": command.target_id, "agent_id": command.agent_id, "amount": command.amount,
                      "unit_template_name": command.template_name, "target_carrier_id": command.target_id,
                      "waypoints": list(command.waypoints or [])}
            for unit in units:
                self._order_ledger[unit.id].append({"id": uuid.uuid4().hex, "type": command.type, "parameters": params, "order": None, "started": False, "settled": False})
                self._settle_front(unit)
        self._rebuild()

    def _settle_front(self, unit):
        """Retain irreversible synchronous effects when later work replaces a root.

        This projects only facts known now. Travel and future resource acquisition
        remain queued prerequisites; no authoritative orders are constructed here.
        """
        entries = self._order_ledger[unit.id]
        if not entries or entries[0].get("started"):
            return
        entry = entries[0]
        entry["started"] = True
        params, kind = entry["parameters"], entry["type"]
        if kind in {"load_colonists", "colonize"}:
            from unit_orders.colony import within_colony_range
            body = self.game.galaxy.get_celestial_body_by_id(params.get("target_id"))
            if body is not None and within_colony_range(unit, body):
                if kind == "load_colonists":
                    amount = float(params.get("amount", 0))
                    self._settled_cargo[unit.id] = self._settled_cargo.get(unit.id, 0) + amount
                    self._settled_population[body.id] = self._settled_population.get(body.id, 0) + amount
                else:
                    self._settled_cargo[unit.id] = -self._live_cargo(unit)
                entry["settled"] = True
        elif kind in {"dock", "dock_in_hangar", "dock_in_strikecraft_bay"}:
            from geometry import distance
            from unit_orders.hangar import DOCKING_RANGE
            target = self.game.galaxy.get_unit_by_id(params.get("target_carrier_id"))
            if target and unit.in_system == target.in_system and unit.in_hex == target.in_hex and distance(unit.position, target.position) <= DOCKING_RANGE:
                component = compatible_docking_component(unit, target)
                if component:
                    key = id(component)
                    self._settled_docks.setdefault(key, component.max_slots - component.get_used_slots())
                    self._settled_docks[key] -= 1
                    self._unavailable_units.add(unit.id)
                    entry["settled"] = True

    @staticmethod
    def _live_cargo(unit):
        return float(getattr(getattr(unit, "colony_component", None), "population_cargo", 0))

    def _ensure_inhibitor_hex(self, unit: Any) -> None:
        key = self._inhibitor_key(unit)
        if key in self._inhibitor_dynamic_zones:
            return
        system = getattr(self.game.galaxy, "systems", {}).get(key[0])
        hex_obj = getattr(system, "hexes", {}).get(key[1]) if system else None
        if hex_obj is None:
            component = getattr(unit, "inhibitor_component", None)
            check = (
                component.check_state_change(False, self.game.galaxy)
                if component is not None
                else None
            )
            raise _Rejected(
                getattr(check, "code", None) or "inhibitor_unavailable",
                f"Unit {unit.id} cannot toggle its inhibitor: "
                f"{getattr(check, 'message', 'The unit has no valid sector location.')}",
            )
        self._inhibitor_static_zones[key] = list(
            getattr(hex_obj, "static_inhibition_zones", [])
        )
        self._inhibitor_dynamic_zones[key] = dict(
            getattr(hex_obj, "dynamic_inhibition_zones", {})
        )

    @staticmethod
    def _inhibitor_key(unit: Any) -> tuple[str, tuple[int, int]]:
        hex_coord = getattr(unit, "in_hex", None)
        if hex_coord is None:
            return str(getattr(unit, "in_system", "")), ()
        return str(getattr(unit, "in_system", "")), tuple(hex_coord)


class CommandGateway:
    """Preflight a complete batch, then commit it on the game thread."""

    def __init__(self, game: Any):
        self.game = game

    def apply_batch(self, player: Any, batch: CommandBatch) -> CommandResult:
        prepared = []
        errors = []
        if len(batch.commands) > MAX_COMMANDS:
            return CommandResult(False, errors=(CommandError(-1, "invalid_command_contract", "A batch may contain at most 40 commands."),))
        self._viewer = player
        self._selected_units = []
        projection = _BatchProjection(self.game, player)
        # Include existing reservations of other owned ships, not only selected ships.
        for system in getattr(self.game.galaxy, "systems", {}).values():
            for sector in getattr(system, "hexes", {}).values():
                for unit in getattr(sector, "units", []):
                    if getattr(unit, "owner", None) is player and getattr(unit, "commander_component", None):
                        projection._ensure_orders(unit)
        for index, command in enumerate(batch.commands):
            try:
                validate_command(command.to_dict())
                if command.type == "send_message":
                    operations = self._prepare_send_message(player, command)
                    units = []
                elif command.type == "message_developer":
                    operations = self._prepare_message_developer(player, command)
                    units = []
                elif COMMAND_SPECS[command.type].player_level:
                    operations = self._prepare_player_intelligence(player, command, projection)
                    units = []
                else:
                    try:
                        units = self._owned_units(player, command.unit_ids)
                    except _Rejected:
                        if command.type in {"cancel_order", "append_patrol_waypoints"}:
                            raise _Rejected("order_unavailable", "The order is unavailable.")
                        raise
                    self._selected_units = units
                    projection.before(command, units)
                    operations = self._prepare(player, command, units, projection)
                    projection.record(command, units)
                for offset, operation in enumerate(operations):
                    operation.command_index = index
                    operation.command_type = command.type
                    operation.unit_id = units[offset].id if units else None
                    prepared.append(operation)
            except ContractError as exc:
                errors.append(CommandError(index, "invalid_command_contract", str(exc)))
            except _Rejected as exc:
                errors.append(CommandError(index, exc.code, str(exc)))
            except Exception:
                errors.append(CommandError(index, "invalid_command", "The command could not be prepared from the current public state."))
        if errors:
            return CommandResult(False, errors=tuple(errors))

        results, receipts = [], []
        for offset, operation in enumerate(prepared):
            try:
                operation.apply()
            except Exception:
                results.append(self._operation_result(operation, "failed", uncertain=True))
                results.extend(self._operation_result(op, "unattempted") for op in prepared[offset + 1:])
                self._mark_dirty()
                return CommandResult(False, applied_count=len(receipts), receipts=tuple(receipts),
                    errors=(CommandError(operation.command_index, "commit_failed", "Execution failed; earlier operations remain applied and the failing operation may have partial effects. Observe before continuing."),),
                    failure_stage="commit", retryable=False, operation_results=tuple(results),
                    may_have_partial_effects=True, requires_observation=True)
            receipts.append(operation.receipt)
            results.append(self._operation_result(operation, "applied"))
        self._mark_dirty()
        return CommandResult(True, applied_count=len(receipts), receipts=tuple(receipts),
                             failure_stage=None, retryable=False, operation_results=tuple(results))

    @staticmethod
    def _operation_result(operation, status, uncertain=False):
        return {"command_index": operation.command_index, "unit_id": operation.unit_id,
                "type": operation.command_type, "order_id": operation.order_id,
                "status": status, "may_have_partial_effects": uncertain}

    def _mark_dirty(self):
        if hasattr(self.game, "sidebar_needs_update"):
            self.game.sidebar_needs_update = True
        if hasattr(self.game, "visibility_dirty"):
            self.game.visibility_dirty = True

    def _prepare(
        self,
        player: Any,
        command: Any,
        units: list[Any],
        projection: _BatchProjection,
    ) -> list[_Prepared]:
        if command.type == "cancel_orders":
            return [
                _Prepared(
                    apply=lambda unit=unit: _stop_and_idle(unit.commander_component),
                    receipt=f"Stopped {unit.name} and set its stance to Do Nothing.",
                )
                for unit in units
            ]

        if command.type == "clear_explicit_orders":
            return [_Prepared(lambda unit=unit: _clear_explicit_orders(unit.commander_component), f"Cleared explicit orders for unit {unit.id}.") for unit in units]
        if command.type == "cancel_order":
            order = projection._edit_target["order"]
            return [_Prepared(lambda: units[0].commander_component.cancel_order(order.order_id), f"Cancelled order {order.public_id}.", order_id=order.public_id)]
        if command.type == "append_patrol_waypoints":
            entry = projection.target_order(command, units[0])
            if entry["type"] != "patrol":
                raise _Rejected("order_unavailable", "The order is unavailable.")
            if len(entry["parameters"].get("waypoints", [])) + len(command.waypoints) > 16:
                raise _Rejected("invalid_value", "The resulting patrol route exceeds 16 waypoints.")
            waypoints = self._waypoints(command.waypoints)
            order = entry["order"]
            def append():
                for waypoint in waypoints:
                    order.add_waypoint(waypoint["system_name"], waypoint["hex_coord"], waypoint["position"])
            return [_Prepared(append, f"Extended patrol {order.public_id}.", order_id=order.public_id)]

        if command.type == "set_stance":
            return self._prepare_stance(units, command.stance)
        if command.type == "toggle_inhibitor":
            return self._prepare_inhibitor(units, projection)
        if command.type == "toggle_cloaking":
            return self._prepare_cloaking(units, projection)
        if command.type == "ci_sweep":
            return self._prepare_ci_sweep(units, projection)

        order_factory, receipt_action = self._order_factory(player, command)
        if command.type == "load_colonists":
            target_body = self._body(command.target_id)
            projection.validate_load(command, units, target_body)
        elif command.type == "construct":
            projection.validate_construct(command, units)
        elif command.type == "dock_in_hangar":
            projection.validate_dock_in_hangar(
                command, units, self._visible_unit(player, command.target_id)
            )
        elif command.type == "dock_in_strikecraft_bay":
            projection.validate_dock_in_strikecraft_bay(
                command, units, self._visible_unit(player, command.target_id)
            )
        elif command.type == "dock":
            projection.validate_dock(
                command, units, self._visible_unit(player, command.target_id)
            )
        operations = []
        for unit in units:
            self._require_capability(unit, command.type)
            self._validate_unit_command(unit, command, projection)
            public_id = uuid.uuid4().hex

            def apply(unit=unit, factory=order_factory, public_id=public_id, queue=command.queue):
                order = factory(unit)
                order.public_id = public_id
                if not queue:
                    _clear_explicit_orders(unit.commander_component)
                unit.commander_component.add_order(order)

            operations.append(
                _Prepared(apply=apply, receipt=f"{command.type} issued for unit {unit.id}.", order_id=public_id)
            )
        return operations

    def _order_factory(self, player: Any, command: Any):
        from geometry import Position
        from unit_orders import (
            AttackOrder,
            ColonizeOrder,
            ConstructOrder,
            ContinuousMineOrder,
            ContinuousResupplyOrder,
            ContinuousTradeOrder,
            DefendOrder,
            DeployAllWingsOrder,
            DeployUnitOrder,
            DockOrder,
            LayMinefieldOrder,
            LoadColonistsOrder,
            MineOrder,
            MoveOrder,
            PatrolOrder,
            ProtectOrder,
            RepairOrder,
            TradeOrder,
            TransferAntimatterOrder,
            UnloadResourcesOrder,
            UseAbilityOrder,
            InfiltrateUnitOrder,
            InfiltratePlanetOrder,
            ExtractAgentOrder,
            EliminateAgentOrder,
        )
        from unit_orders.combat import resolve_component_type

        target_unit = None
        target_body = None
        if command.type in {
            "attack",
            "protect",
            "repair",
            "unload_resources",
            "dock",
            "dock_in_hangar",
            "dock_in_strikecraft_bay",
            "transfer_antimatter",
            "trade",
        } or (command.type == "use_ability" and command.target_id is not None):
            target_unit = self._visible_unit(player, command.target_id)
        if command.type in {
            "colonize",
            "load_colonists",
            "mine",
            "continuous_mine",
            "continuous_resupply",
        }:
            target_body = self._body(command.target_id)

        if command.type == "infiltrate_unit":
            target_unit = self._visible_unit(player, command.target_id)
            self._require_relation(player, target_unit, "enemy")
            return (
                lambda unit: InfiltrateUnitOrder(unit, {"target_unit_id": target_unit.id}),
                f"Infiltrate {target_unit.name}",
            )
        if command.type == "infiltrate_planet":
            target_body = self._body(command.target_id)
            if not is_colonizable_body(target_body) or intelligence_relation(player, getattr(target_body, "owner", None)) != "enemy":
                raise _Rejected("target_unavailable", "The target is unavailable.")
            return (
                lambda unit: InfiltratePlanetOrder(
                    unit,
                    {
                        "target_body_id": target_body.id,
                        "target_body_name": target_body.name,
                        "system": target_body.in_system,
                        "hex": target_body.in_hex,
                    },
                ),
                f"Infiltrate {target_body.name}",
            )
        if command.type == "extract_agent":
            self._owned_agent(player, command.agent_id)
            return (
                lambda unit: ExtractAgentOrder(unit, {"agent_id": command.agent_id}),
                f"Extract agent {command.agent_id}",
            )
        if command.type == "eliminate_agent":
            self._discovered_enemy_agent(player, command.agent_id)
            return (
                lambda unit: EliminateAgentOrder(unit, {"agent_id": command.agent_id}),
                f"Eliminate discovered agent {command.agent_id}",
            )

        if command.type == "patrol" and command.waypoints is not None:
            waypoints = self._waypoints(command.waypoints)
            return (lambda unit: PatrolOrder(unit, {"waypoints": [dict(wp) for wp in waypoints]}), "Patrol")
        if command.type in {"move", "patrol"}:
            destination = self._destination(command)
            cls = MoveOrder if command.type == "move" else PatrolOrder
            return (
                lambda unit: cls(
                    unit,
                    {
                        "destination_system_name": command.system_name,
                        "destination_hex_coord": command.hex_coord,
                        "destination_position": destination,
                    },
                ),
                command.type.capitalize(),
            )
        if command.type == "attack":
            self._require_relation(player, target_unit, "enemy")
            target_comp_type = None
            receipt_suffix = ""
            if command.target_component is not None:
                from component_visibility import public_target_components, component_is_public
                resolved = resolve_component_type(command.target_component)
                if resolved is None or not component_is_public(resolved, enemy=True) or resolved.__name__ not in public_target_components(target_unit):
                    raise _Rejected("target_unavailable", "The target subsystem is unavailable.")
                target_comp_type = resolved.__name__
                receipt_suffix = f" ({target_comp_type})"
            attack_params = {"target_unit_id": target_unit.id}
            if target_comp_type is not None:
                attack_params["target_component_type"] = target_comp_type
            return (
                lambda unit: AttackOrder(unit, dict(attack_params)),
                f"Attack {target_unit.name}{receipt_suffix}",
            )
        if command.type == "defend":
            if command.target_id is not None:
                body = (
                    self.game.galaxy.get_celestial_body_by_id(command.target_id)
                    if hasattr(self.game.galaxy, "get_celestial_body_by_id")
                    else None
                )
                if body is not None:
                    body = self._body(command.target_id)
                    dest_params = {
                        "destination_system_name": getattr(body, "in_system", None),
                        "destination_hex_coord": getattr(body, "in_hex", None),
                        "destination_position": getattr(body, "position", None),
                        "target_id": body.id,
                    }
                    receipt_dest = getattr(body, "name", f"body {command.target_id}")
                else:
                    target_u = self._visible_unit(player, command.target_id)
                    dest_params = {
                        "destination_system_name": getattr(target_u, "in_system", None),
                        "destination_hex_coord": getattr(target_u, "in_hex", None),
                        "destination_position": getattr(target_u, "position", None),
                        "target_id": target_u.id,
                    }
                    receipt_dest = getattr(target_u, "name", f"unit {command.target_id}")
            elif (
                command.system_name is not None
                and command.hex_coord is not None
                and command.position is not None
            ):
                destination = self._destination(command)
                dest_params = {
                    "destination_system_name": command.system_name,
                    "destination_hex_coord": command.hex_coord,
                    "destination_position": destination,
                }
                receipt_dest = f"{command.system_name} {command.hex_coord}"
            else:
                raise _Rejected(
                    "missing_field",
                    "defend requires system_name, hex_coord, and position, or target_id.",
                )
            return (
                lambda unit: DefendOrder(unit, dict(dest_params)),
                f"Defend {receipt_dest}",
            )
        if command.type == "protect":
            self._require_friendly(player, target_unit)
            return (
                lambda unit: ProtectOrder(unit, {"target_unit_id": target_unit.id}),
                f"Protect {target_unit.name}",
            )
        if command.type == "colonize":
            if not is_colonizable_body(target_body):
                raise _Rejected(
                    "invalid_target", "The colonization target is not a habitable body."
                )
            if getattr(target_body, "owner", None) is not None:
                raise _Rejected("invalid_target", "The colonization target is already owned.")
            return (
                lambda unit: ColonizeOrder(
                    unit,
                    {"target_id": target_body.id, "target_name": target_body.name},
                ),
                f"Colonize {target_body.name}",
            )
        if command.type == "load_colonists":
            if not is_colonizable_body(target_body):
                raise _Rejected(
                    "invalid_target", "Colonists can only be loaded from a colony body."
                )
            if not is_self_owned(player, getattr(target_body, "owner", None)):
                raise _Rejected(
                    "invalid_relation", "Colonists must be loaded from a self-owned body."
                )
            if command.amount is None or command.amount <= 0:
                raise _Rejected("invalid_value", "load_colonists requires a positive amount.")
            return (
                lambda unit: LoadColonistsOrder(
                    unit,
                    {
                        "target_id": target_body.id,
                        "target_name": target_body.name,
                        "amount": command.amount,
                    },
                ),
                f"Load colonists from {target_body.name}",
            )
        if command.type == "construct":
            if not command.template_name or command.position is None:
                raise _Rejected(
                    "missing_field", "construct requires template_name and position."
                )
            position = Position(*command.position)
            return (
                lambda unit: ConstructOrder(
                    unit,
                    {
                        "unit_template_name": command.template_name,
                        "target_position": position,
                    },
                ),
                f"Construct {command.template_name}",
            )
        if command.type == "repair":
            self._require_friendly(player, target_unit)
            return (
                lambda unit: RepairOrder(unit, {"target_unit_id": target_unit.id}),
                f"Repair {target_unit.name}",
            )
        if command.type in {"mine", "continuous_mine"}:
            if not is_mining_target(target_body):
                raise _Rejected("invalid_target", "The mining target is not mineable.")
            cls = MineOrder if command.type == "mine" else ContinuousMineOrder
            return (
                lambda unit: cls(unit, {"target_id": target_body.id}),
                f"Mine {target_body.name}",
            )
        if command.type == "unload_resources":
            self._require_friendly(player, target_unit)
            if not (
                getattr(target_unit, "metal_refinery_component", None)
                or getattr(target_unit, "crystal_refinery_component", None)
            ):
                raise _Rejected("invalid_target", "The unload target is not a refinery.")
            return (
                lambda unit: UnloadResourcesOrder(
                    unit, {"target_unit_id": target_unit.id}
                ),
                f"Unload at {target_unit.name}",
            )
        if command.type == "dock_in_hangar":
            self._require_friendly(player, target_unit)
            if not all(
                compatible_hangar_component(unit, target_unit) is not None
                for unit in self._owned_units(player, command.unit_ids)
            ):
                raise _Rejected(
                    "invalid_target",
                    "The docking target has no compatible free hangar slots.",
                )
            return (
                lambda unit: DockOrder(unit, {"target_carrier_id": target_unit.id}),
                f"Dock in Hangar of {target_unit.name}",
            )
        if command.type == "dock_in_strikecraft_bay":
            self._require_friendly(player, target_unit)
            if not all(
                compatible_strikecraft_bay_component(unit, target_unit) is not None
                for unit in self._owned_units(player, command.unit_ids)
            ):
                raise _Rejected(
                    "invalid_target",
                    "The docking target has no compatible free strikecraft bay slots.",
                )
            return (
                lambda unit: DockOrder(unit, {"target_carrier_id": target_unit.id}),
                f"Dock in Strikecraft Bay of {target_unit.name}",
            )
        if command.type == "dock":
            self._require_friendly(player, target_unit)
            if not all(
                compatible_docking_component(unit, target_unit) is not None
                for unit in self._owned_units(player, command.unit_ids)
            ):
                raise _Rejected(
                    "invalid_target",
                    "The docking target has no compatible free carrier slots.",
                )
            return (
                lambda unit: DockOrder(unit, {"target_carrier_id": target_unit.id}),
                f"Dock with {target_unit.name}",
            )
        if command.type == "deploy_unit":
            if command.target_id is None:
                raise _Rejected("missing_field", "deploy_unit requires target_id.")
            return (
                lambda unit: DeployUnitOrder(
                    unit, {"docked_unit_id": command.target_id}
                ),
                f"Deploy docked unit {command.target_id}",
            )
        if command.type == "deploy_all_wings":
            return (lambda unit: DeployAllWingsOrder(unit), "Deploy all wings")
        if command.type == "transfer_antimatter":
            self._require_friendly(player, target_unit)
            target_storage = getattr(target_unit, "antimatter_component", None)
            if target_storage is None:
                raise _Rejected(
                    "invalid_target", "The transfer target has no antimatter storage."
                )
            if float(getattr(target_storage, "current_amount", 0)) >= float(
                getattr(target_storage, "max_capacity", 0)
            ):
                raise _Rejected(
                    "invalid_target", "The transfer target's antimatter storage is full."
                )
            return (
                lambda unit: TransferAntimatterOrder(
                    unit, {"target_unit_id": target_unit.id}
                ),
                f"Transfer antimatter to {target_unit.name}",
            )
        if command.type == "continuous_resupply":
            if not is_antimatter_source(target_body):
                raise _Rejected("invalid_target", "The resupply target is not a star or gas giant.")
            return (
                lambda unit: ContinuousResupplyOrder(
                    unit,
                    {"target_id": target_body.id, "target_name": target_body.name},
                ),
                f"Resupply from {target_body.name}",
            )
        if command.type == "lay_minefield":
            minefield_type = command.minefield_type or "anti_ship"
            if minefield_type not in {"anti_ship", "anti_strikecraft"}:
                raise _Rejected("invalid_value", "Unknown minefield_type.")
            return (
                lambda unit: LayMinefieldOrder(unit, minefield_type=minefield_type),
                f"Lay {minefield_type} minefield",
            )
        if command.type == "trade":
            self._require_friendly(player, target_unit)
            if getattr(target_unit, "civilian_habitat_component", None) is None:
                raise _Rejected(
                    "invalid_target", "The trade target is not a civilian habitat."
                )
            return (
                lambda unit: TradeOrder(unit, {"target_unit_id": target_unit.id}),
                f"Trade with {target_unit.name}",
            )
        if command.type == "continuous_trade":
            return (lambda unit: ContinuousTradeOrder(unit), "Begin continuous trade")
        if command.type == "use_ability":
            return self._ability_factory(command, target_unit)
        raise _Rejected("unsupported_command", "Unsupported command.")

    def _ability_factory(self, command: Any, target_unit: Any):
        from geometry import Position
        from unit_components import ABILITY_DEFINITIONS, AbilityType
        from unit_orders import UseAbilityOrder

        if not command.ability:
            raise _Rejected("missing_field", "use_ability requires ability.")
        try:
            ability_type = AbilityType(command.ability)
        except ValueError as exc:
            raise _Rejected("invalid_value", "Unknown ability.") from exc
        definition = ABILITY_DEFINITIONS.get(ability_type)
        if definition is None:
            raise _Rejected("invalid_value", "Unknown ability.")
        if definition.requires_target_unit and target_unit is None:
            raise _Rejected("missing_field", "This ability requires target_id.")
        if definition.requires_target_position and command.position is None:
            raise _Rejected("missing_field", "This ability requires position.")
        if not definition.requires_target_unit and command.target_id is not None:
            raise _Rejected("invalid_command_contract", "This ability does not use target_id.")
        if not definition.requires_target_position and command.position is not None:
            raise _Rejected("invalid_command_contract", "This ability does not use position.")
        params = {"ability_type": command.ability}
        if target_unit is not None:
            params["target_unit_id"] = target_unit.id
        if command.position is not None:
            params["target_position"] = Position(*command.position)
        return (
            lambda unit: UseAbilityOrder(unit, dict(params)),
            f"Use {command.ability}",
        )

    def _prepare_stance(self, units: list[Any], stance_value: str | None):
        from unit_components import UnitStance

        try:
            stance = UnitStance(stance_value)
        except (TypeError, ValueError) as exc:
            raise _Rejected("invalid_value", "Unknown stance.") from exc
        operations = []
        for unit in units:
            if stance not in unit.commander_component.get_allowed_stances():
                raise _Rejected(
                    "capability_unavailable",
                    f"Stance {stance.value} is unavailable to unit {unit.id}.",
                )
            operations.append(
                _Prepared(
                    apply=lambda unit=unit, stance=stance: _set_stance(unit.commander_component, stance),
                    receipt=f"Set {unit.name} stance to {stance.value}.",
                )
            )
        return operations

    def _prepare_inhibitor(
        self, units: list[Any], projection: _BatchProjection
    ) -> list[_Prepared]:
        operations = []
        for unit, turn_on in projection.plan_inhibitor_toggles(units):
            component = unit.inhibitor_component

            def apply(component=component, turn_on=turn_on):
                result = component.set_active(turn_on, self.game.galaxy)
                if not result.allowed:
                    raise RuntimeError(result.code or "inhibitor state change failed")

            action = "Activated" if turn_on else "Deactivated"
            operations.append(_Prepared(apply, f"{action} inhibitor on {unit.name}."))
        return operations

    def _prepare_cloaking(self, units: list[Any], projection: _BatchProjection):
        operations = []
        for unit in units:
            component = getattr(unit, "cloaking_component", None)
            if component is None or getattr(component, "is_destroyed", False) is True:
                raise _Rejected(
                    "capability_unavailable", f"Unit {unit.id} has no functioning cloaking device."
                )

            turn_on = not projection._cloaking_states.get(unit.id, bool(component.is_active))
            projection._cloaking_states[unit.id] = turn_on
            def apply(component=component):
                if not component.toggle():
                    raise RuntimeError("cloaking toggle failed")

            operations.append(_Prepared(apply, f"Cloaking {'active' if turn_on else 'inactive'} on unit {unit.id}."))
        return operations

    def _prepare_player_intelligence(
        self, player: Any, command: Any, projection: _BatchProjection
    ) -> list[_Prepared]:
        if command.agent_id is None:
            raise _Rejected("agent_unavailable", "The agent is unavailable.")
        if command.type == "sabotage":
            projection.project_sabotage(command.agent_id, command.sabotage_type)

            def apply():
                agent, host = self._owned_agent(player, command.agent_id)
                if command.sabotage_type not in sabotage_types_for_host(host):
                    raise RuntimeError("sabotage authorization changed")
                if not host.apply_sabotage(agent, command.sabotage_type):
                    raise RuntimeError("sabotage failed")

            return [
                _Prepared(
                    apply,
                    f"Agent {command.agent_id} set to {command.sabotage_type} sabotage.",
                )
            ]
        if command.type == "relocate_agent":
            target = self._public_intelligence_target(player, command.target_id)
            projection.project_relocation(command.agent_id, target)

            def apply():
                from geometry import distance
                from unit_orders.intelligence import INTELLIGENCE_OPERATIONAL_RANGE

                agent, host = self._owned_agent(player, command.agent_id)
                live_target = self._public_intelligence_target(player, command.target_id)
                if (
                    live_target is host
                    or intelligence_relation(player, getattr(live_target, "owner", None)) != "enemy"
                    or getattr(host, "in_system", None) != getattr(live_target, "in_system", None)
                    or getattr(host, "in_hex", None) != getattr(live_target, "in_hex", None)
                    or distance(host.position, live_target.position) > INTELLIGENCE_OPERATIONAL_RANGE
                ):
                    raise RuntimeError("relocation authorization changed")
                if not host.remove_agent(agent):
                    raise RuntimeError("agent host changed")
                live_target.infiltrating_agents.append(agent)
                agent.attached_to = live_target
                agent.target_type = "UNIT" if host_kind(live_target) == "unit" else "CELESTIAL_BODY"
                agent.target_id = live_target.id
                agent.active_sabotage = None
                agent.is_discovered = False

            return [
                _Prepared(
                    apply,
                    f"Relocated agent {command.agent_id} to target {command.target_id}.",
                )
            ]
        raise _Rejected("unsupported_command", "Unsupported player-level command.")

    def _prepare_ci_sweep(
        self, units: list[Any], projection: _BatchProjection
    ) -> list[_Prepared]:
        from unit_orders import CISweepOrder, OrderStatus

        operations = []
        for unit in projection.plan_ci_sweeps(units):
            def apply(unit=unit):
                order = CISweepOrder(unit)
                order.execute(self.game.galaxy)
                if order.status != OrderStatus.COMPLETED:
                    raise RuntimeError("Counter-Intelligence sweep failed")

            operations.append(_Prepared(apply, f"Counter-Intelligence sweep performed by unit {unit.id}."))
        return operations

    def _prepare_send_message(self, player: Any, command: Any) -> list[_Prepared]:
        target_id = command.target_id
        if target_id is None:
            raise _Rejected("missing_target", "send_message requires target_id (recipient player ID).")

        recipient = None
        for p in getattr(self.game, "players", []):
            if getattr(p, "id", None) == target_id:
                recipient = p
                break
        if recipient is None:
            raise _Rejected("invalid_recipient", f"Player {target_id} does not exist.")

        if getattr(player, "id", None) == target_id:
            raise _Rejected("invalid_recipient", "Cannot send message to yourself.")

        message_text = command.message
        if not message_text or not str(message_text).strip():
            raise _Rejected("empty_message", "send_message requires non-empty message text.")

        clean_text = str(message_text).strip()[:500]

        def apply(sender=player, recipient_id=target_id, text=clean_text):
            self.game.send_message(sender, recipient_id, text)

        return [
            _Prepared(
                apply=apply,
                receipt=f"Sent transmission to {recipient.name}: '{clean_text}'.",
            )
        ]

    def _prepare_message_developer(self, player: Any, command: Any) -> list[_Prepared]:
        message_text = command.message
        if not message_text or not str(message_text).strip():
            raise _Rejected("empty_message", "message_developer requires non-empty message text.")

        clean_text = str(message_text).strip()[:2000]

        def apply(sender=player, text=clean_text):
            if hasattr(self.game, "record_developer_feedback"):
                self.game.record_developer_feedback(sender, text)
            else:
                logger.info("[Developer Feedback] %s: %s", getattr(sender, "name", "AI"), text)

        return [
            _Prepared(
                apply=apply,
                receipt=f"Delivered message to game developer: '{clean_text}'.",
            )
        ]

    def _owned_units(self, player: Any, unit_ids: tuple[int, ...]) -> list[Any]:
        units = []
        seen = set()
        for unit_id in unit_ids:
            if unit_id in seen:
                continue
            seen.add(unit_id)
            unit = self.game.galaxy.get_unit_by_id(unit_id)
            if unit is None or getattr(unit, "owner", None) is not player:
                raise _Rejected("unit_unavailable", "A selected unit is unavailable.")
            if getattr(unit, "commander_component", None) is None:
                raise _Rejected("capability_unavailable", "A selected unit has no commander.")
            units.append(unit)
        return units

    def _owned_agent(self, player: Any, agent_id: int | None) -> tuple[Any, Any]:
        if agent_id is None:
            raise _Rejected("agent_unavailable", "The agent is unavailable.")
        agent, host = find_agent_host(self.game.galaxy, agent_id)
        if (
            agent is None
            or intelligence_relation(player, getattr(agent, "owner", None)) != "self"
        ):
            raise _Rejected("agent_unavailable", "The agent is unavailable.")
        return agent, host

    def _discovered_enemy_agent(self, player: Any, agent_id: int | None) -> tuple[Any, Any]:
        if agent_id is None:
            raise _Rejected("agent_unavailable", "The agent is unavailable.")
        for agent, host in discovered_enemy_agent_hosts(self.game.galaxy, player):
            if agent.id == agent_id:
                return agent, host
        raise _Rejected("agent_unavailable", "The agent is unavailable.")

    def _public_intelligence_target(self, player: Any, target_id: int | None) -> Any:
        if target_id is None:
            raise _Rejected("target_unavailable", "The target is unavailable.")
        unit = self.game.galaxy.get_unit_by_id(target_id)
        target = self._visible_unit(player, target_id) if unit is not None else self._body(target_id)
        if host_kind(target) not in {"unit", "colony"}:
            raise _Rejected("target_unavailable", "The target is unavailable.")
        return target

    def _visible_unit(self, player: Any, target_id: int | None):
        if target_id is None:
            raise _Rejected("missing_field", "This command requires target_id.")
        unit = self.game.galaxy.get_unit_by_id(target_id)
        if unit is None:
            raise _Rejected("target_unavailable", "The target is unavailable.")
        if self._relation(player, unit.owner) == "enemy":
            from visibility import VisibilityService

            snapshot = VisibilityService.compute(
                self.game.galaxy,
                player,
                turn_number=getattr(self.game, "turn_number", 1),
            )
            if unit.id not in snapshot.visible_enemy_unit_ids:
                raise _Rejected("target_unavailable", "The target is unavailable.")
        return unit

    def _body(self, target_id: int | None):
        if target_id is None:
            raise _Rejected("missing_field", "This command requires target_id.")
        body = self.game.galaxy.get_celestial_body_by_id(target_id)
        from .rules import body_is_public
        if body is None or not body_is_public(self.game, self._viewer, body, self._selected_units):
            raise _Rejected("target_unavailable", "The target is unavailable.")
        return body

    def _waypoints(self, raw):
        from geometry import Position
        result = []
        for waypoint in raw:
            system = self.game.galaxy.systems.get(waypoint["system_name"])
            coord = tuple(waypoint["hex_coord"])
            if system is None or coord not in system.hexes:
                raise _Rejected("invalid_destination", "The destination hex does not exist.")
            result.append({"system_name": waypoint["system_name"], "hex_coord": coord, "position": Position(*waypoint["position"])})
        return result

    def _destination(self, command: Any):
        from geometry import Position

        if command.system_name is None or command.hex_coord is None or command.position is None:
            raise _Rejected(
                "missing_field", "move/patrol requires system_name, hex_coord, and position."
            )
        system = self.game.galaxy.systems.get(command.system_name)
        if system is None or command.hex_coord not in system.hexes:
            raise _Rejected("invalid_destination", "The destination hex does not exist.")
        return Position(*command.position)

    def _require_capability(self, unit: Any, command_type: str) -> None:
        from .rules import capability_blocker
        if capability_blocker(unit, command_type):
            raise _Rejected("capability_unavailable", f"Unit {unit.id} cannot perform {command_type}.")
        if command_type == "defend":
            if (
                not has_operational_engines(unit)
                or getattr(unit, "weapons_component", None) is None
            ):
                raise _Rejected(
                    "capability_unavailable",
                    f"Unit {unit.id} cannot perform defend (requires engines and weapons).",
                )
        if command_type == "lay_minefield" and not any(
            component.__class__.__name__ == "MinelayerComponent"
            for component in getattr(unit, "components", {}).values()
        ):
            raise _Rejected(
                "capability_unavailable",
                f"Unit {unit.id} cannot perform {command_type}.",
            )

    def _validate_unit_command(
        self, unit: Any, command: Any, projection: _BatchProjection
    ) -> None:
        if command.type == "move":
            from constants import HullSize
            from entities import is_position_in_magnetic_storm
            if getattr(unit, "hull_size", None) == HullSize.STRIKECRAFT_WING:
                dest_pos = self._destination(command)
                if is_position_in_magnetic_storm(self.game.galaxy, command.system_name, tuple(command.hex_coord), dest_pos):
                    raise _Rejected("hazard_blocked", "Strikecraft wings cannot enter magnetic storms.")
        elif command.type == "patrol":
            from constants import HullSize
            from entities import is_position_in_magnetic_storm
            if getattr(unit, "hull_size", None) == HullSize.STRIKECRAFT_WING:
                if command.waypoints:
                    for wp in self._waypoints(command.waypoints):
                        if is_position_in_magnetic_storm(self.game.galaxy, wp["system_name"], wp["hex_coord"], wp["position"]):
                            raise _Rejected("hazard_blocked", "Strikecraft wings cannot enter magnetic storms.")
                elif command.system_name is not None and command.position is not None:
                    dest_pos = self._destination(command)
                    if is_position_in_magnetic_storm(self.game.galaxy, command.system_name, tuple(command.hex_coord), dest_pos):
                        raise _Rejected("hazard_blocked", "Strikecraft wings cannot enter magnetic storms.")
        elif command.type == "defend":
            from constants import HullSize
            from entities import is_position_in_magnetic_storm
            if getattr(unit, "hull_size", None) == HullSize.STRIKECRAFT_WING:
                if command.position is not None and command.system_name is not None and command.hex_coord is not None:
                    from geometry import Position
                    defend_pos = Position(*command.position)
                    if is_position_in_magnetic_storm(self.game.galaxy, command.system_name, tuple(command.hex_coord), defend_pos):
                        raise _Rejected("hazard_blocked", "Strikecraft wings cannot enter magnetic storms.")
        elif command.type == "attack":
            target = self._visible_unit(unit.owner, command.target_id)
            check = getattr(unit.weapons_component, "eligible_turrets_for", None)
            if callable(check) and not check(target):
                raise _Rejected("capability_unavailable", "No eligible weapons for this target.")
        elif command.type == "colonize":
            if projection.cargo_for(unit) <= 0:
                queue_hint = (
                    " Queue a valid load_colonists command before colonize with "
                    "colonize.queue=true, or omit colonize this turn."
                )
                raise _Rejected(
                    "capability_unavailable",
                    f"Unit {unit.id} has no colonists.{queue_hint}",
                )
        elif command.type == "construct":
            constructor = unit.constructor_component
            if not command.template_name or not constructor.can_build(command.template_name):
                raise _Rejected(
                    "invalid_value", f"Unit {unit.id} cannot build that template."
                )
        elif command.type == "dock_in_hangar":
            hull = getattr(getattr(unit, "hull_size", None), "name", "").lower()
            if hull != "tiny":
                raise _Rejected(
                    "capability_unavailable",
                    f"Unit {unit.id} cannot dock in a hangar (only tiny ships supported).",
                )
        elif command.type == "dock_in_strikecraft_bay":
            hull = getattr(getattr(unit, "hull_size", None), "name", "").lower()
            if hull != "strikecraft_wing":
                raise _Rejected(
                    "capability_unavailable",
                    f"Unit {unit.id} cannot dock in a strikecraft bay (only strikecraft wings supported).",
                )
        elif command.type == "dock":
            hull = getattr(getattr(unit, "hull_size", None), "name", "").lower()
            if hull not in {"tiny", "strikecraft_wing"}:
                raise _Rejected(
                    "capability_unavailable", f"Unit {unit.id} is too large to dock."
                )
        elif command.type == "deploy_unit":
            if command.target_id is None:
                raise _Rejected("missing_field", "deploy_unit requires target_id.")
            docked = []
            for component_name in ("hangar_component", "strikecraft_bay_component"):
                component = getattr(unit, component_name, None)
                docked.extend(getattr(component, "docked_units", []) or [])
            docked_unit = next((du for du in docked if du.id == command.target_id), None)
            if not docked_unit:
                raise _Rejected(
                    "target_unavailable", "The docked unit is unavailable."
                )
            from entities import is_position_in_magnetic_storm, HullSize
            if getattr(docked_unit, "hull_size", None) == HullSize.STRIKECRAFT_WING:
                if is_position_in_magnetic_storm(self.game.galaxy, unit.in_system, unit.in_hex, unit.position):
                    raise _Rejected(
                        "hazard_blocked", "Cannot launch strikecraft wings in a magnetic storm."
                    )
        elif command.type == "deploy_all_wings":
            bay = getattr(unit, "strikecraft_bay_component", None)
            if bay is None:
                raise _Rejected(
                    "capability_unavailable",
                    f"Unit {unit.id} has no strikecraft bay.",
                )
            from entities import is_position_in_magnetic_storm
            if is_position_in_magnetic_storm(self.game.galaxy, unit.in_system, unit.in_hex, unit.position):
                raise _Rejected(
                    "hazard_blocked", "Cannot launch strikecraft wings in a magnetic storm."
                )
        elif command.type == "transfer_antimatter":
            storage = getattr(unit, "antimatter_component", None)
            if storage is None or getattr(storage, "current_amount", 0) <= 0:
                raise _Rejected(
                    "capability_unavailable", f"Unit {unit.id} has no antimatter to transfer."
                )
        elif command.type == "continuous_resupply":
            if getattr(unit, "antimatter_component", None) is None:
                raise _Rejected(
                    "capability_unavailable",
                    f"Unit {unit.id} has no antimatter storage for resupply.",
                )
        elif command.type == "use_ability":
            from unit_components import AbilityType

            try:
                ability_type = AbilityType(command.ability)
            except (TypeError, ValueError) as exc:
                raise _Rejected("invalid_value", "Unknown ability.") from exc
            if not unit.ability_component.can_use(ability_type):
                raise _Rejected(
                    "capability_unavailable",
                    f"Ability {command.ability} is unavailable on unit {unit.id}.",
                )
        elif command.type in {"infiltrate_unit", "infiltrate_planet"}:
            intelligence = getattr(unit, "intelligence_component", None)
            if intelligence is None or int(getattr(intelligence, "available_agents", 0)) <= 0:
                raise _Rejected("capability_unavailable", f"Unit {unit.id} has no available agents.")
        elif command.type == "extract_agent":
            intelligence = getattr(unit, "intelligence_component", None)
            if (
                intelligence is None
                or int(getattr(intelligence, "available_agents", 0))
                >= int(getattr(intelligence, "agents_capacity", 0))
            ):
                raise _Rejected("insufficient_capacity", f"Unit {unit.id} has no free agent capacity.")
        elif command.type == "eliminate_agent":
            intelligence = getattr(unit, "intelligence_component", None)
            if not getattr(intelligence, "has_counter_intelligence", False):
                raise _Rejected("capability_unavailable", f"Unit {unit.id} has no Counter-Intelligence suite.")
    def _require_friendly(self, player: Any, target: Any) -> None:
        if target is None or self._relation(player, getattr(target, "owner", target)) == "enemy":
            raise _Rejected("invalid_relation", "The target must be friendly.")

    def _require_relation(self, player: Any, target: Any, relation: str) -> None:
        if self._relation(player, getattr(target, "owner", None)) != relation:
            raise _Rejected("invalid_relation", f"The target must be {relation}.")

    @staticmethod
    def _relation(player: Any, owner: Any) -> str:
        if owner is player or getattr(owner, "id", None) == getattr(player, "id", None):
            return "self"
        if owner is not None and player.is_allied_with(owner):
            return "ally"
        return "enemy"
