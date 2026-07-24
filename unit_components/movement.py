import logging
import typing
from typing import Optional, Tuple, TYPE_CHECKING
import dataclasses

from .base import UnitComponent
from .enums import HyperdriveType, JumpStatus
from utils import HexCoord
from geometry import Position
from constants import (
    DEFAULT_HYPERDRIVE_RECHARGE_DURATION, DEFAULT_JUMP_RANGE,
    XP_SPEED_BONUS, XP_JUMP_RANGE_BONUS
)

if TYPE_CHECKING:
    from entities import Unit, Wormhole
    from game import Game

logger = logging.getLogger(__name__)

class Engines(UnitComponent):
    """Engines for sublight (non-faster-than-light) travel, within a single sector."""

    DISPLAY_NAME: str = "Engines"
    SIDEBAR_ORDER: int = 2
    speed: float = 0.0
    move_target: typing.Optional[Position] = None

    def __init__(self, unit: 'Unit', speed: float = 0.0, hull_cost: int = 5):
        super().__init__(unit, hull_cost=hull_cost)
        self.speed = speed
        self.move_target = None

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        xp = self.unit.experience_points
        if xp > 0:
            effective_speed = self.speed * self.unit.xp_multiplier(XP_SPEED_BONUS)
            bonus_pct = int((effective_speed / self.speed - 1.0) * 100) if self.speed else 0
            speed_text = f"Speed: {self.speed} (+{bonus_pct}% XP → {effective_speed:.1f})"
        else:
            speed_text = f"Speed: {self.speed}"
        data.append({'type': 'label', 'text': speed_text, 'object_id': '#sidebar_info_label', 'height': 20})
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
    jump_status: JumpStatus = JumpStatus.READY
    recharge_time_remaining: int = 0
    RECHARGE_DURATION: int = DEFAULT_HYPERDRIVE_RECHARGE_DURATION

    def __init__(self, unit: 'Unit', drive_type: HyperdriveType = HyperdriveType.BASIC, hull_cost: Optional[int] = None, recharge_duration: int = DEFAULT_HYPERDRIVE_RECHARGE_DURATION, jump_range: int = DEFAULT_JUMP_RANGE):
        if hull_cost is None:
            hull_cost = 5 if drive_type == HyperdriveType.BASIC else 10
        super().__init__(unit, hull_cost=hull_cost)
        self.drive_type = drive_type
        self.jump_range = jump_range
        self.hex_jump_target = None
        self.wormhole_jump_target = None
        self.jump_status = JumpStatus.READY
        self.recharge_time_remaining = 0
        self.RECHARGE_DURATION = recharge_duration

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

    def start_recharge(self) -> None:
        """Initiates the hyperdrive recharge sequence."""
        self.jump_status = JumpStatus.CHARGING
        self.recharge_time_remaining = self.RECHARGE_DURATION
        self.hex_jump_target = None
        self.wormhole_jump_target = None
        logger.debug(f"Unit {self.unit.name} (id:{self.unit.id}) hyperdrive starting recharge for {self.RECHARGE_DURATION} turns. Status: CHARGING.")

    def update_recharge(self) -> None:
        """Updates the recharge status of the hyperdrive. Called each turn."""
        if self.jump_status == JumpStatus.CHARGING and self.recharge_time_remaining > 0:
            self.recharge_time_remaining -= 1
            if self.recharge_time_remaining <= 0:
                self.jump_status = JumpStatus.READY
                self.recharge_time_remaining = 0
                logger.debug(f"Unit {self.unit.name} (id:{self.unit.id}) hyperdrive recharged. Status: READY.")
