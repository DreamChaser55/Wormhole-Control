"""Persistent standing stance order and its transient engagement subtree."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, TYPE_CHECKING

from constants import XP_JUMP_RANGE_BONUS
from geometry import distance, hex_distance
from .base import Order, OrderStatus, OrderType
from .combat import AttackOrder

if TYPE_CHECKING:
    from entities import Unit
    from galaxy import Galaxy
    from unit_components.enums import UnitStance

logger = logging.getLogger(__name__)


class StanceOrder(Order):
    """A persistent policy which owns at most one transient Attack order."""

    def __init__(
        self,
        unit: 'Unit',
        parameters: Optional[Dict[str, Any]] = None,
        parent_order: Optional[Order] = None,
    ):
        params = dict(parameters or {})
        stance = params.get("stance", "do_nothing")
        from unit_components.enums import UnitStance
        if hasattr(stance, "value"):
            stance = stance.value
        else:
            try:
                stance = UnitStance(stance).value
            except (TypeError, ValueError):
                raw_name = str(stance)
                if raw_name.startswith("UnitStance."):
                    raw_name = raw_name.rsplit(".", 1)[-1]
                try:
                    stance = UnitStance[raw_name.upper()].value
                except (KeyError, TypeError):
                    stance = "do_nothing"
        params["stance"] = stance
        super().__init__(unit, OrderType.STANCE, params, parent_order)
        self.status = OrderStatus.IN_PROGRESS

    @property
    def stance(self) -> 'UnitStance':
        from unit_components.enums import UnitStance
        try:
            return UnitStance(self.parameters.get("stance", UnitStance.DO_NOTHING.value))
        except (TypeError, ValueError):
            return UnitStance.DO_NOTHING

    @property
    def active_attack(self) -> Optional[AttackOrder]:
        if not self.sub_orders:
            return None
        child = self.sub_orders[0]
        if child.order_type != OrderType.ATTACK:
            return None
        return child  # type: ignore[return-value]

    @property
    def has_engagement(self) -> bool:
        attack = self.active_attack
        return bool(attack and attack.status in {OrderStatus.PENDING, OrderStatus.IN_PROGRESS})

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        self.status = OrderStatus.IN_PROGRESS

    def target_invalid_reason(
        self,
        target: Optional['Unit'],
        galaxy_ref: 'Galaxy',
        visibility_snapshot: Any = None,
    ) -> Optional[str]:
        from unit_components.enums import UnitStance
        commander = self.unit.commander_component
        if self.stance not in commander.get_allowed_stances():
            return "stance capability unavailable"
        if target is None or target.current_hit_points <= 0:
            return "target missing or destroyed"

        from entities import are_enemies
        if not are_enemies(self.unit.owner, target.owner):
            return "target is no longer an enemy"
        if target.in_system != self.unit.in_system:
            return "target left the system"

        weapons = self.unit.weapons_component
        if not weapons or not weapons.eligible_turrets_for(target):
            return "no eligible turret"

        if visibility_snapshot is None and self.unit.owner:
            from visibility import VisibilityService
            turn_num = getattr(getattr(self.unit, "game", None), "turn_number", None)
            if turn_num is None:
                turn_num = getattr(
                    getattr(galaxy_ref, "game", None),
                    "turn_number",
                    getattr(galaxy_ref, "turn_number", 1),
                )
            visibility_snapshot = VisibilityService.compute(galaxy_ref, self.unit.owner, turn_number=turn_num)
        if visibility_snapshot is not None:
            from visibility import is_unit_visible
            if not is_unit_visible(visibility_snapshot, target):
                return "target is no longer visible"

        if self.stance == UnitStance.ATTACK_WEAPON_RANGE:
            if target.in_hex != self.unit.in_hex:
                return "target left weapon-range sector"
            target_distance = distance(self.unit.position, target.position)
            if not any(target_distance <= turret.range for turret in weapons.eligible_turrets_for(target)):
                return "target left weapon range"
        elif self.stance == UnitStance.ATTACK_SAME_SECTOR:
            if target.in_hex != self.unit.in_hex:
                return "target left the sector"
        elif self.stance == UnitStance.ATTACK_INTRA_SYSTEM_JUMP_RANGE:
            drive = self.unit.hyperdrive_component
            if not drive or not drive.is_functional:
                return "functional hyperdrive unavailable"
            effective_range = int(drive.jump_range * self.unit.xp_multiplier(XP_JUMP_RANGE_BONUS))
            if hex_distance(self.unit.in_hex, target.in_hex) > effective_range:
                return "target left jump vigilance range"
        elif self.stance == UnitStance.ATTACK_SAME_SYSTEM:
            drive = self.unit.hyperdrive_component
            if not drive or not drive.is_functional:
                return "functional hyperdrive unavailable"
        elif self.stance == UnitStance.DO_NOTHING:
            return "stance is Do Nothing"
        return None

    def is_target_valid(
        self,
        target: Optional['Unit'],
        galaxy_ref: 'Galaxy',
        visibility_snapshot: Any = None,
    ) -> bool:
        return self.target_invalid_reason(target, galaxy_ref, visibility_snapshot) is None

    def find_target(self, galaxy_ref: 'Galaxy', visibility_snapshot: Any = None) -> Optional['Unit']:
        from unit_components.enums import UnitStance
        system = galaxy_ref.systems.get(self.unit.in_system)
        if not system:
            return None
        if visibility_snapshot is None and self.unit.owner:
            from visibility import VisibilityService
            turn_num = getattr(getattr(self.unit, "game", None), "turn_number", None)
            if turn_num is None:
                turn_num = getattr(
                    getattr(galaxy_ref, "game", None),
                    "turn_number",
                    getattr(galaxy_ref, "turn_number", 1),
                )
            visibility_snapshot = VisibilityService.compute(
                galaxy_ref, self.unit.owner, turn_number=turn_num
            )
        if self.stance in {UnitStance.ATTACK_WEAPON_RANGE, UnitStance.ATTACK_SAME_SECTOR}:
            sector = system.hexes.get(self.unit.in_hex)
            candidates = list(sector.units) if sector else []
        else:
            candidates = [unit for sector in system.hexes.values() for unit in sector.units]

        ranked = []
        for candidate in candidates:
            if self.is_target_valid(candidate, galaxy_ref, visibility_snapshot):
                score = (
                    hex_distance(self.unit.in_hex, candidate.in_hex) * 1_000_000.0
                    + distance(self.unit.position, candidate.position)
                )
                ranked.append((score, candidate.id, candidate))
        return min(ranked, default=(None, None, None), key=lambda item: (item[0], item[1]))[2]

    def cancel_engagement(self, reason: str = "suspended") -> None:
        attack = self.active_attack
        if not attack:
            return
        logger.debug(
            "[%s (id:%s)] STANCE(id:%s): invalidating target %s (%s).",
            self.unit.name,
            self.unit.id,
            self.order_id,
            attack.parameters.get("target_unit_id"),
            reason,
        )
        attack.cancel()
        self.sub_orders.popleft()

    def validate_engagement(self, galaxy_ref: 'Galaxy') -> bool:
        attack = self.active_attack
        if not attack:
            return True
        target_id = attack.parameters.get("target_unit_id")
        target = galaxy_ref.get_unit_by_id(target_id) if target_id is not None else None
        reason = self.target_invalid_reason(target, galaxy_ref)
        if reason:
            self.cancel_engagement(reason)
            return False
        return True

    def update(self, galaxy_ref: 'Galaxy') -> None:
        from unit_components.enums import UnitStance
        self.status = OrderStatus.IN_PROGRESS
        if self.stance not in self.unit.commander_component.get_allowed_stances():
            self.unit.commander_component.set_stance(UnitStance.DO_NOTHING)
            return
        if self.stance == UnitStance.DO_NOTHING or self.unit.is_disabled:
            self.cancel_engagement("stance inactive")
            return

        attack = self.active_attack
        if attack and not self.validate_engagement(galaxy_ref):
            attack = None
        if attack:
            if attack.status == OrderStatus.PENDING:
                attack.execute(galaxy_ref)
            if attack.status == OrderStatus.IN_PROGRESS:
                attack.update(galaxy_ref)
            if attack.status in {OrderStatus.COMPLETED, OrderStatus.FAILED, OrderStatus.CANCELLED}:
                self.sub_orders.popleft()
            return

        target = self.find_target(galaxy_ref)
        if target:
            logger.debug(
                "[%s (id:%s)] STANCE(id:%s): acquired target %s (id:%s).",
                self.unit.name,
                self.unit.id,
                self.order_id,
                target.name,
                target.id,
            )
            attack = AttackOrder(self.unit, {"target_unit_id": target.id}, parent_order=self)
            self.add_sub_order(attack)
            attack.execute(galaxy_ref)
            if attack.status == OrderStatus.IN_PROGRESS:
                attack.update(galaxy_ref)

    def cancel(self) -> None:
        self.cancel_engagement("standing order replaced")
        self.status = OrderStatus.CANCELLED

    def check_completion_conditions(self) -> None:
        return
