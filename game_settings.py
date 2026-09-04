"""Game settings data model populated by the New Game Wizard."""
import typing
from dataclasses import dataclass, field

from enum import Enum

from game_ai.runtime import (
    DEFAULT_REASONING_EFFORT,
    DEFAULT_REPAIR_RETRIES,
    normalize_reasoning_effort,
    normalize_repair_retries,
)
from player_controller import PlayerController


# ---------------------------------------------------------------------------
# Spawn profiles
# ---------------------------------------------------------------------------
class SpawnProfile(str, Enum):
    """Preset spawn profile configuring player homeworlds and starting units."""
    NORMAL = "normal"
    TESTING = "testing"

    @property
    def display_name(self) -> str:
        return {
            SpawnProfile.NORMAL: "Normal",
            SpawnProfile.TESTING: "Testing",
        }[self]


DEFAULT_SPAWN_PROFILE: SpawnProfile = SpawnProfile.NORMAL


def normalize_spawn_profile(value: typing.Union[SpawnProfile, str, None]) -> SpawnProfile:
    """Normalizes a raw string or enum value into a valid SpawnProfile."""
    if value is None:
        return DEFAULT_SPAWN_PROFILE
    if isinstance(value, SpawnProfile):
        return value
    val_str = str(value).strip().lower()
    for member in SpawnProfile:
        if member.value == val_str:
            return member
    return DEFAULT_SPAWN_PROFILE


# ---------------------------------------------------------------------------
# Preset player colour palette (name → RGB tuple)
# ---------------------------------------------------------------------------
PLAYER_COLOR_PALETTE: typing.List[typing.Tuple[str, typing.Tuple[int, int, int]]] = [
    ("Blue",    (30,  120, 255)),
    ("Red",     (220,  40,  40)),
    ("Yellow",  (255, 210,   0)),
    ("Green",   ( 40, 200,  80)),
    ("Purple",  (160,  60, 220)),
    ("Orange",  (255, 140,   0)),
    ("Cyan",    (  0, 210, 220)),
    ("Pink",    (230,  80, 160)),
]

# Convenience mapping: color name → RGB tuple
PLAYER_COLORS_BY_NAME: typing.Dict[str, typing.Tuple[int, int, int]] = {
    name: rgb for name, rgb in PLAYER_COLOR_PALETTE
}


@dataclass
class PlayerConfig:
    """Per-player configuration selected in the New Game Wizard."""
    name: str
    color: typing.Tuple[int, int, int]
    controller: PlayerController = PlayerController.HUMAN
    team_id: int = 1
    ai_reasoning_effort: str = DEFAULT_REASONING_EFFORT
    ai_repair_retries: int = DEFAULT_REPAIR_RETRIES
    home_system_name: typing.Optional[str] = None

    def __post_init__(self) -> None:
        self.controller = PlayerController(self.controller)
        self.ai_reasoning_effort = normalize_reasoning_effort(
            self.ai_reasoning_effort
        )
        self.ai_repair_retries = normalize_repair_retries(
            self.ai_repair_retries
        )
        if self.home_system_name is not None:
            self.home_system_name = str(self.home_system_name).strip() or None


def _default_player_configs() -> typing.List[PlayerConfig]:
    """Returns the three default player configurations."""
    return [
        PlayerConfig("Player 1", PLAYER_COLOR_PALETTE[0][1], controller=PlayerController.HUMAN, team_id=1),
        PlayerConfig("Player 2", PLAYER_COLOR_PALETTE[1][1], controller=PlayerController.OPENAI, team_id=2, ai_reasoning_effort="low"),
        PlayerConfig("Player 3", PLAYER_COLOR_PALETTE[2][1], controller=PlayerController.OPENAI, team_id=3, ai_reasoning_effort="low"),
    ]


@dataclass
class GameSettings:
    """All user-customizable parameters for a new game.

    Flows from the New Game Wizard → ``game_setup.start_new_game`` →
    ``Galaxy.__init__`` so that every subsystem can read its relevant values
    without passing a large parameter list.
    """

    # --- Players ---
    player_configs: typing.List[PlayerConfig] = field(
        default_factory=_default_player_configs
    )

    # --- Galaxy generation ---
    num_systems: int = 15
    min_system_distance: float = 50.0
    max_system_distance: float = 350.0
    wormhole_density: float = 1 / 3          # probability of secondary connections
    system_radius_min: int = 6
    system_radius_max: int = 10

    # --- Economy / starting resources ---
    starting_credits: float = 20_000.0
    starting_metal: float = 10_000.0
    starting_crystal: float = 10_000.0
    starting_population: int = 50

    # --- Spawn profile ---
    spawn_profile: SpawnProfile = SpawnProfile.NORMAL

    # --- Stage 1 & 2 integration ---
    pregenerated_galaxy: typing.Optional[typing.Any] = None
    home_system_assignment_mode: str = "random"  # "random" or "specified"

    @property
    def num_players(self) -> int:
        return len(self.player_configs)

    def validate(self) -> typing.List[str]:
        """Validates logical consistency of game settings parameters.

        Returns:
            List of error strings describing any invalid settings, or empty list if valid.
        """
        errors: typing.List[str] = []
        if self.system_radius_min > self.system_radius_max:
            errors.append(
                f"Min System Radius ({self.system_radius_min}) cannot be greater than Max System Radius ({self.system_radius_max})."
            )
        if self.min_system_distance >= self.max_system_distance:
            errors.append(
                f"Min System Distance ({int(self.min_system_distance)}) must be strictly less than Max System Distance ({int(self.max_system_distance)})."
            )
        if len(self.player_configs) >= 2:
            distinct_teams = {cfg.team_id for cfg in self.player_configs}
            if len(distinct_teams) < 2:
                errors.append("Players must be grouped into at least two different teams.")

        if self.pregenerated_galaxy is not None and hasattr(self.pregenerated_galaxy, "systems"):
            for cfg in self.player_configs:
                if cfg.home_system_name and cfg.home_system_name.lower() != "random":
                    if cfg.home_system_name not in self.pregenerated_galaxy.systems:
                        errors.append(
                            f"Assigned home system '{cfg.home_system_name}' for player '{cfg.name}' does not exist in the generated galaxy."
                        )
        return errors

    def __post_init__(self) -> None:
        """Validates settings upon dataclass instantiation."""
        self.spawn_profile = normalize_spawn_profile(self.spawn_profile)
        errors = self.validate()
        if errors:
            raise ValueError("; ".join(errors))


