"""Pure, per-application display geometry. Importing this module touches no OS APIs."""
from dataclasses import dataclass
from typing import Any

from geometry import Position, Vector


@dataclass(frozen=True)
class DisplayConfig:
    """Physical pixel dimensions and derived metrics; never persisted in campaigns."""

    width: int = 2560
    height: int = 1440
    fullscreen: bool = True

    def __post_init__(self) -> None:
        if type(self.width) is not int or type(self.height) is not int or min(self.width, self.height) <= 0:
            raise ValueError("Display dimensions must be positive integers")

    @property
    def resolution(self) -> Vector:
        return Vector(self.width, self.height)

    @property
    def center(self) -> Position:
        return Position(self.width // 2, self.height // 2)

    @property
    def text_scale(self) -> float:
        return float((self.height / 720.0) ** 1.15)

    @property
    def hex_size(self) -> int:
        return int(25 * self.height / 720.0)

    @property
    def sector_radius(self) -> int:
        return self.height // 2

    @property
    def info_box_width(self) -> int:
        return int(self.width * 250 / 1280.0)

    @property
    def top_bar_height(self) -> int:
        return int(self.height * 35 / 720.0)

    @property
    def context_menu_width(self) -> int:
        return int(self.width * 180 / 1280.0)

    @property
    def context_menu_item_height(self) -> int:
        return int(self.height * 25 / 720.0)


DEFAULT_DISPLAY_CONFIG = DisplayConfig()


def display_config_for(owner: Any) -> DisplayConfig:
    """Read an adapter's configuration, accepting legacy resolution-only adapters.

    Lightweight collaborators without a configuration keep the fixed historical
    default. No display discovery or global mutation occurs here.
    """
    if isinstance(owner, DisplayConfig):
        return owner
    config = getattr(owner, "display_config", None)
    if isinstance(config, DisplayConfig):
        return config
    resolution = getattr(owner, "screen_res", owner)
    width, height = getattr(resolution, "x", None), getattr(resolution, "y", None)
    if isinstance(width, (int, float)) and isinstance(height, (int, float)):
        return DisplayConfig(int(width), int(height))
    return DEFAULT_DISPLAY_CONFIG
