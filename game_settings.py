"""Game settings data model populated by the New Game Wizard."""
import typing
from dataclasses import dataclass, field

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
    is_human: bool = True


def _default_player_configs() -> typing.List[PlayerConfig]:
    """Returns the three default player configurations."""
    return [
        PlayerConfig("Player 1", PLAYER_COLOR_PALETTE[0][1], is_human=True),
        PlayerConfig("Player 2", PLAYER_COLOR_PALETTE[1][1], is_human=True),
        PlayerConfig("Player 3", PLAYER_COLOR_PALETTE[2][1], is_human=True),
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
    system_radius_min: int = 5
    system_radius_max: int = 8

    # --- Economy / starting resources ---
    starting_credits: float = 20_000.0
    starting_metal: float = 10_000.0
    starting_crystal: float = 10_000.0
    starting_population: int = 50

    @property
    def num_players(self) -> int:
        return len(self.player_configs)
