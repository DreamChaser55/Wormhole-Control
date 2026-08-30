import logging
import typing
from typing import Optional, Tuple, TYPE_CHECKING
import dataclasses

from .base import UnitComponent
from .enums import HyperdriveType, JumpStatus, SabotageType
from utils import HexCoord
from geometry import Position
from constants import (
    DEFAULT_HYPERDRIVE_RECHARGE_DURATION, DEFAULT_JUMP_RANGE,
    XP_SPEED_BONUS, XP_JUMP_RANGE_BONUS, HullSize
)

if TYPE_CHECKING:
    from entities import Unit, Wormhole
    from game import Game

logger = logging.getLogger(__name__)

SPEED_PER_HULL_POINT: float = 20.0
ENGINE_HULL_SIZE_MULTIPLIERS: typing.Dict[HullSize, float] = {
    HullSize.STRIKECRAFT_WING: 0.4,
    HullSize.TINY: 0.6,
    HullSize.SMALL: 0.8,
    HullSize.MEDIUM: 1.0,
    HullSize.LARGE: 1.5,
    HullSize.HUGE: 2.0,
}

HYPERDRIVE_BASE_COST: typing.Dict[str, int] = {
    "BASIC": 3,
    "ADVANCED": 7,
}
HYPERDRIVE_RANGE_PER_POINT: float = 5.0
HYPERDRIVE_HULL_SIZE_MULTIPLIERS: typing.Dict[HullSize, float] = {
    HullSize.STRIKECRAFT_WING: 0.4,
    HullSize.TINY: 0.6,
    HullSize.SMALL: 0.8,
    HullSize.MEDIUM: 1.0,
    HullSize.LARGE: 1.5,
    HullSize.HUGE: 2.0,
}


class Engines(UnitComponent):
    """Engines for sublight (non-faster-than-light) travel, within a single sector."""

    DISPLAY_NAME: str = "Engines"
    SIDEBAR_ORDER: int = 2
    speed: float = 0.0
    move_target: typing.Optional[Position] = None
    move_target_order_id: typing.Optional[int] = None

    def __init__(self, unit: 'Unit', speed: float = 0.0, hull_cost: float = 5.0):
        super().__init__(unit, hull_cost=hull_cost)
        self.speed = speed
        self.move_target = None
        self.move_target_order_id = None

    def set_move_target(self, target: Position, order_id: int) -> None:
        self.move_target = target
        self.move_target_order_id = order_id

    def clear_move_target(self, order_id: Optional[int] = None) -> bool:
        """Clear the target only when ``order_id`` still owns it, if supplied."""
        if order_id is not None and self.move_target_order_id != order_id:
            return False
        self.move_target = None
        self.move_target_order_id = None
        return True

    @staticmethod
    def calc_hull_cost(speed: float, hull_size: Optional[HullSize] = HullSize.MEDIUM) -> float:
        """Compute the hull cost of an Engines component from its speed and unit hull size."""
        if speed <= 0:
            return 0.0
        multiplier = ENGINE_HULL_SIZE_MULTIPLIERS.get(hull_size, 1.0) if hull_size else 1.0
        return (speed / SPEED_PER_HULL_POINT) * multiplier

    @property
    def effective_speed(self) -> float:
        if self.is_destroyed:
            return 0.0

        spd = self.speed
        if hasattr(self.unit, 'is_sabotaged'):
            from .enums import SabotageType
            if self.unit.is_sabotaged(SabotageType.ENGINES):
                spd *= 0.5
        if hasattr(self.unit, 'experience_points') and self.unit.experience_points > 0:
            spd *= self.unit.xp_multiplier(XP_SPEED_BONUS)
        return spd

    @property
    def is_operational(self) -> bool:
        """Whether these engines can currently provide sub-light movement."""
        return not self.is_destroyed and self.effective_speed > 0.0

    def on_destroyed(self) -> None:
        """Immediately stop any active sub-light movement target."""
        self.clear_move_target()

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        xp = getattr(self.unit, 'experience_points', 0)
        eff_speed = self.effective_speed
        is_sab = hasattr(self.unit, 'is_sabotaged') and self.unit.is_sabotaged(SabotageType.ENGINES)
        
        status_extra = []
        if is_sab:
            status_extra.append("-50% Sabotaged")
        if xp > 0:
            status_extra.append(f"+{int((self.unit.xp_multiplier(XP_SPEED_BONUS) - 1.0) * 100)}% XP")
        
        if status_extra:
            speed_text = f"Speed: {self.speed} ({', '.join(status_extra)} → {eff_speed:.1f})"
        else:
            speed_text = f"Speed: {self.speed}"
        data.append({'type': 'label', 'text': speed_text, 'object_id': '#sidebar_info_label', 'height': 20})
        return data

    def get_basic_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_basic_sidebar_data(game_state)
        if self.is_destroyed:
            return data
        eff_speed = self.effective_speed
        data.append({
            'type': 'label',
            'text': f"• Speed: {eff_speed:.1f}",
            'object_id': '#sidebar_value_label',
            'height': 18,
            'indent_level': 1
        })
        return data

@dataclasses.dataclass
class Hyperdrive(UnitComponent):
    """Hyperdrive for faster-than-light travel - inter-sector (basic) or inter-system through wormholes (advanced). """
    DISPLAY_NAME: str = "Hyperdrive"
    SIDEBAR_ORDER: int = 3
    drive_type: HyperdriveType = HyperdriveType.BASIC
    jump_range: int = DEFAULT_JUMP_RANGE
    hex_jump_target: typing.Optional[Tuple[HexCoord, Position]] = None
    wormhole_jump_target: typing.Optional['Wormhole'] = None
    jump_target_order_id: typing.Optional[int] = None
    jump_status: JumpStatus = JumpStatus.READY
    recharge_time_remaining: int = 0
    RECHARGE_DURATION: int = DEFAULT_HYPERDRIVE_RECHARGE_DURATION

    def __init__(self, unit: 'Unit', drive_type: HyperdriveType = HyperdriveType.BASIC, hull_cost: Optional[float] = None, recharge_duration: int = DEFAULT_HYPERDRIVE_RECHARGE_DURATION, jump_range: int = DEFAULT_JUMP_RANGE):
        if hull_cost is None:
            hull_cost = 5.0 if drive_type == HyperdriveType.BASIC else 10.0
        super().__init__(unit, hull_cost=hull_cost)
        self.drive_type = drive_type
        self.jump_range = jump_range
        self.hex_jump_target = None
        self.wormhole_jump_target = None
        self.jump_target_order_id = None
        self.jump_status = JumpStatus.READY
        self.recharge_time_remaining = 0
        self.RECHARGE_DURATION = recharge_duration

    @property
    def is_functional(self) -> bool:
        """Whether the drive can currently execute a jump."""
        if self.is_destroyed:
            return False
        return not (
            hasattr(self.unit, 'is_sabotaged')
            and self.unit.is_sabotaged(SabotageType.HYPERDRIVE)
        )

    def set_hex_jump_target(self, target: Tuple[HexCoord, Position], order_id: int) -> None:
        self.hex_jump_target = target
        self.wormhole_jump_target = None
        self.jump_target_order_id = order_id

    def set_wormhole_jump_target(self, target: 'Wormhole', order_id: int) -> None:
        self.wormhole_jump_target = target
        self.hex_jump_target = None
        self.jump_target_order_id = order_id

    def clear_jump_target(self, order_id: Optional[int] = None) -> bool:
        """Clear the jump target only when ``order_id`` still owns it, if supplied."""
        if order_id is not None and self.jump_target_order_id != order_id:
            return False
        self.hex_jump_target = None
        self.wormhole_jump_target = None
        self.jump_target_order_id = None
        return True

    def on_destroyed(self) -> None:
        self.clear_jump_target()

    @staticmethod
    def calc_hull_cost(
        drive_type: typing.Any,
        jump_range: int,
        hull_size: Optional[HullSize] = HullSize.MEDIUM,
    ) -> float:
        """Compute the hull cost of a Hyperdrive component."""
        dt_str = drive_type.name if hasattr(drive_type, 'name') else str(drive_type)
        base = HYPERDRIVE_BASE_COST.get(dt_str.upper(), HYPERDRIVE_BASE_COST["BASIC"])
        range_cost = max(0, jump_range) / HYPERDRIVE_RANGE_PER_POINT
        raw_cost = base + range_cost
        multiplier = HYPERDRIVE_HULL_SIZE_MULTIPLIERS.get(hull_size, 1.0) if hull_size else 1.0
        return raw_cost * multiplier

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        drive_type_str = self.drive_type.value if self.drive_type else 'N/A'
        
        status_detail = ""
        if self.jump_status == JumpStatus.CHARGING:
            status_detail = f"Charging: {self.recharge_time_remaining} turns"
        elif self.jump_status == JumpStatus.JUMPING:
            status_detail = "Jumping"
        elif self.jump_status == JumpStatus.READY:
            status_detail = "Ready"
        elif self.jump_status == JumpStatus.ERROR:
            status_detail = "Error"

        data.append({'type': 'label', 'text': f"Type: {drive_type_str}  Status: {status_detail}", 'object_id': '#sidebar_info_label', 'height': 20})

        xp = self.unit.experience_points
        if xp > 0:
            effective_range = int(self.jump_range * self.unit.xp_multiplier(XP_JUMP_RANGE_BONUS))
            bonus_pct = int((effective_range / self.jump_range - 1.0) * 100) if self.jump_range else 0
            range_text = f"Jump Range: {self.jump_range} (+{bonus_pct}% XP → {effective_range})"
        else:
            range_text = f"Jump Range: {self.jump_range}"
        data.append({'type': 'label', 'text': range_text, 'object_id': '#sidebar_info_label', 'height': 20})
        return data

    def get_basic_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_basic_sidebar_data(game_state)
        if self.is_destroyed:
            return data
        status_str = "Ready"
        obj_id = '#sidebar_status_active_label'
        if self.jump_status == JumpStatus.CHARGING:
            status_str = f"Charging ({self.recharge_time_remaining}t)"
            obj_id = '#sidebar_status_charging_label'
        elif self.jump_status == JumpStatus.JUMPING:
            status_str = "Jumping"
            obj_id = '#sidebar_status_active_label'
        effective_range = int(self.jump_range * self.unit.xp_multiplier(XP_JUMP_RANGE_BONUS))
        data.append({
            'type': 'label',
            'text': f"• FTL Jump: {self.drive_type.value} ({status_str}, Rng {effective_range})",
            'object_id': obj_id,
            'height': 18,
            'indent_level': 1
        })
        return data


    def start_recharge(self, order_id: Optional[int] = None) -> None:
        """Initiate recharge and release only the target owned by this jump.

        ``order_id`` is normally supplied by the movement processor.  Keeping
        it optional preserves the component's public API for callers that are
        already operating on the currently bound target.
        """
        # A delayed movement pass may still hold the ID of a waypoint that
        # was cancelled/replaced after its snapshot was taken.  Never let that
        # stale completion put a newer jump into recharge or clear its target.
        if order_id is not None and self.jump_target_order_id != order_id:
            return

        extra_turns = 3 if hasattr(self.unit, 'is_sabotaged') and self.unit.is_sabotaged(SabotageType.HYPERDRIVE) else 0
        self.jump_status = JumpStatus.CHARGING
        self.recharge_time_remaining = self.RECHARGE_DURATION + extra_turns
        owner_id = self.jump_target_order_id if order_id is None else order_id
        self.clear_jump_target(owner_id)
        logger.debug(f"Unit {self.unit.name} (id:{self.unit.id}) hyperdrive starting recharge for {self.recharge_time_remaining} turns. Status: CHARGING.")

    def update_recharge(self) -> None:
        """Updates the recharge status of the hyperdrive. Called each turn."""
        if self.jump_status == JumpStatus.CHARGING and self.recharge_time_remaining > 0:
            self.recharge_time_remaining -= 1
            if self.recharge_time_remaining <= 0:
                self.jump_status = JumpStatus.READY
                self.recharge_time_remaining = 0
                logger.debug(f"Unit {self.unit.name} (id:{self.unit.id}) hyperdrive recharged. Status: READY.")
