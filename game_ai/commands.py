"""Validated command gateway from model output to authoritative game orders."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .contracts import CommandBatch


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


class _Rejected(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class _Prepared:
    apply: Callable[[], None]
    receipt: str


class CommandGateway:
    """Preflight a complete batch, then commit it on the game thread."""

    def __init__(self, game: Any):
        self.game = game

    def apply_batch(self, player: Any, batch: CommandBatch) -> CommandResult:
        prepared: list[_Prepared] = []
        errors: list[CommandError] = []
        for index, command in enumerate(batch.commands):
            try:
                prepared.extend(self._prepare(player, command))
            except _Rejected as exc:
                errors.append(CommandError(index, exc.code, str(exc)))
            except Exception:
                errors.append(
                    CommandError(
                        index,
                        "invalid_command",
                        "The command could not be prepared from the current public state.",
                    )
                )
        if errors:
            return CommandResult(accepted=False, errors=tuple(errors))

        try:
            for operation in prepared:
                operation.apply()
        except Exception as exc:
            return CommandResult(
                accepted=False,
                errors=(
                    CommandError(
                        -1,
                        "commit_failed",
                        f"The game rejected the prepared command batch: {exc}",
                    ),
                ),
            )
        if hasattr(self.game, "sidebar_needs_update"):
            self.game.sidebar_needs_update = True
        if hasattr(self.game, "visibility_dirty"):
            self.game.visibility_dirty = True
        return CommandResult(
            accepted=True,
            applied_count=len(prepared),
            receipts=tuple(operation.receipt for operation in prepared),
        )

    def _prepare(self, player: Any, command: Any) -> list[_Prepared]:
        units = self._owned_units(player, command.unit_ids)
        if not units:
            raise _Rejected("no_units", "At least one owned unit ID is required.")

        if command.type == "cancel_orders":
            return [
                _Prepared(
                    apply=lambda unit=unit: unit.commander_component.clear_orders(),
                    receipt=f"Cleared orders for {unit.name}.",
                )
                for unit in units
            ]

        if command.type == "set_stance":
            return self._prepare_stance(units, command.stance)
        if command.type == "toggle_inhibitor":
            return self._prepare_inhibitor(units)
        if command.type == "toggle_cloaking":
            return self._prepare_cloaking(units)

        order_factory, receipt_action = self._order_factory(player, command)
        operations = []
        for unit in units:
            self._require_capability(unit, command.type)
            self._validate_unit_command(unit, command)
            order = order_factory(unit)

            def apply(unit=unit, order=order, queue=command.queue):
                if not queue:
                    unit.commander_component.clear_orders()
                unit.commander_component.add_order(order)

            operations.append(
                _Prepared(apply=apply, receipt=f"{receipt_action} for {unit.name}.")
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
        )

        target_unit = None
        target_body = None
        if command.type in {
            "attack",
            "protect",
            "repair",
            "unload_resources",
            "dock",
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
            return (
                lambda unit: AttackOrder(unit, {"target_unit_id": target_unit.id}),
                f"Attack {target_unit.name}",
            )
        if command.type == "protect":
            self._require_friendly(player, target_unit)
            return (
                lambda unit: ProtectOrder(unit, {"target_unit_id": target_unit.id}),
                f"Protect {target_unit.name}",
            )
        if command.type == "colonize":
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
            self._require_friendly(player, getattr(target_body, "owner", None))
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
            cls = MineOrder if command.type == "mine" else ContinuousMineOrder
            return (
                lambda unit: cls(unit, {"target_id": target_body.id}),
                f"Mine {target_body.name}",
            )
        if command.type == "unload_resources":
            self._require_friendly(player, target_unit)
            return (
                lambda unit: UnloadResourcesOrder(
                    unit, {"target_unit_id": target_unit.id}
                ),
                f"Unload at {target_unit.name}",
            )
        if command.type == "dock":
            self._require_friendly(player, target_unit)
            if not (
                getattr(target_unit, "hangar_component", None)
                or getattr(target_unit, "strikecraft_bay_component", None)
            ):
                raise _Rejected("invalid_target", "The docking target is not a carrier.")
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
            return (
                lambda unit: TransferAntimatterOrder(
                    unit, {"target_unit_id": target_unit.id}
                ),
                f"Transfer antimatter to {target_unit.name}",
            )
        if command.type == "continuous_resupply":
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
                    apply=lambda unit=unit, stance=stance: setattr(
                        unit.commander_component, "stance", stance
                    ),
                    receipt=f"Set {unit.name} stance to {stance.value}.",
                )
            )
        return operations

    def _prepare_inhibitor(self, units: list[Any]):
        operations = []
        for unit in units:
            component = getattr(unit, "inhibitor_component", None)
            if component is None:
                raise _Rejected(
                    "capability_unavailable", f"Unit {unit.id} has no inhibitor."
                )

            def apply(component=component):
                if not component.toggle(galaxy_ref=self.game.galaxy):
                    raise RuntimeError("inhibitor toggle failed")

            operations.append(_Prepared(apply, f"Toggled inhibitor on {unit.name}."))
        return operations

    def _prepare_cloaking(self, units: list[Any]):
        operations = []
        for unit in units:
            component = getattr(unit, "cloaking_component", None)
            if component is None:
                raise _Rejected(
                    "capability_unavailable", f"Unit {unit.id} has no cloaking device."
                )

            def apply(component=component):
                if not component.toggle():
                    raise RuntimeError("cloaking toggle failed")

            operations.append(_Prepared(apply, f"Toggled cloaking on {unit.name}."))
        return operations

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
        if body is None:
            raise _Rejected("target_unavailable", "The target is unavailable.")
        return body

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
        requirements = {
            "move": "engines_component",
            "patrol": "engines_component",
            "attack": "weapons_component",
            "colonize": "colony_component",
            "load_colonists": "colony_component",
            "construct": "constructor_component",
            "repair": "repair_component",
            "mine": "mining_component",
            "continuous_mine": "mining_component",
            "unload_resources": "mining_component",
            "continuous_resupply": "harvester_component",
            "trade": "trade_component",
            "continuous_trade": "trade_component",
            "use_ability": "ability_component",
        }
        attribute = requirements.get(command_type)
        if attribute and getattr(unit, attribute, None) is None:
            raise _Rejected(
                "capability_unavailable",
                f"Unit {unit.id} cannot perform {command_type}.",
            )
        if command_type == "lay_minefield" and not any(
            component.__class__.__name__ == "MinelayerComponent"
            for component in getattr(unit, "components", {}).values()
        ):
            raise _Rejected(
                "capability_unavailable",
                f"Unit {unit.id} cannot perform {command_type}.",
            )

    def _validate_unit_command(self, unit: Any, command: Any) -> None:
        if command.type == "colonize":
            colony = unit.colony_component
            if getattr(colony, "population_cargo", 0) <= 0:
                raise _Rejected(
                    "capability_unavailable", f"Unit {unit.id} has no colonists."
                )
        elif command.type == "construct":
            constructor = unit.constructor_component
            if not command.template_name or not constructor.can_build(command.template_name):
                raise _Rejected(
                    "invalid_value", f"Unit {unit.id} cannot build that template."
                )
        elif command.type == "dock":
            hull = getattr(getattr(unit, "hull_size", None), "name", "").lower()
            if hull not in {"tiny", "small"}:
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
            if not any(docked_unit.id == command.target_id for docked_unit in docked):
                raise _Rejected(
                    "target_unavailable", "The docked unit is unavailable."
                )
        elif command.type == "deploy_all_wings":
            bay = getattr(unit, "strikecraft_bay_component", None)
            if bay is None:
                raise _Rejected(
                    "capability_unavailable",
                    f"Unit {unit.id} has no strikecraft bay.",
                )
        elif command.type == "transfer_antimatter":
            storage = getattr(unit, "antimatter_component", None)
            if storage is None or getattr(storage, "current_amount", 0) <= 0:
                raise _Rejected(
                    "capability_unavailable", f"Unit {unit.id} has no antimatter to transfer."
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
