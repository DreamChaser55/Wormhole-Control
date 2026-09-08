"""Game settings data model populated by the New Game Wizard."""
import typing
import math
import unicodedata
from dataclasses import InitVar, dataclass, field

from enum import Enum

from game_ai.runtime import (
    DEFAULT_REASONING_EFFORT,
    DEFAULT_REPAIR_RETRIES,
    SUPPORTED_REASONING_EFFORTS,
    MIN_REPAIR_RETRIES,
    MAX_REPAIR_RETRIES,
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
MIN_PLAYERS, MAX_PLAYERS = 2, 6
MIN_SYSTEMS, MAX_SYSTEMS = 5, 30
MIN_SYSTEM_RADIUS, MAX_SYSTEM_RADIUS = 3, 12


@dataclass(frozen=True)
class ValidationIssue:
    """A stable field/code plus human-readable explanation of invalid new-game input."""
    field: str
    code: str
    message: str


class SettingsValidationError(ValueError):
    def __init__(self, issues):
        self.issues = tuple(issues)
        super().__init__('; '.join(issue.message for issue in self.issues))


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def player_config_issues(config, prefix='player'):
    """Validate without coercing malformed input or mutating a player configuration."""
    issues = []
    def add(field, code, message):
        issues.append(ValidationIssue(f'{prefix}.{field}', code, message))
    name = config.name
    if (not isinstance(name, str) or not 1 <= len(name.strip()) <= 80
            or any(unicodedata.category(c).startswith('C') for c in name)):
        add('name', 'invalid_player_name', 'Player name must contain 1-80 characters without control characters.')
    if (not isinstance(config.color, (tuple, list)) or len(config.color) != 3
            or any(not _integer(c) or not 0 <= c <= 255 for c in config.color)):
        add('color', 'invalid_color', 'Player color must be three integers from 0 to 255.')
    if not _integer(config.team_id) or config.team_id < 1:
        add('team_id', 'invalid_team', 'Player team_id must be a positive integer.')
    try:
        PlayerController(config.controller)
    except (TypeError, ValueError):
        add('controller', 'invalid_controller', 'Player controller must be human, openai, or codex.')
    if config.ai_reasoning_effort not in SUPPORTED_REASONING_EFFORTS:
        add('ai_reasoning_effort', 'invalid_reasoning_effort', 'AI reasoning effort must be low, medium, or high.')
    if not _integer(config.ai_repair_retries) or not MIN_REPAIR_RETRIES <= config.ai_repair_retries <= MAX_REPAIR_RETRIES:
        add('ai_repair_retries', 'invalid_repair_retries', f'AI repair retries must be between {MIN_REPAIR_RETRIES} and {MAX_REPAIR_RETRIES}.')
    if config.home_system_name is not None and not isinstance(config.home_system_name, str):
        add('home_system_name', 'invalid_settings', 'Home system name must be a string or None.')
    return issues


def normalize_spawn_profile(value: typing.Union[SpawnProfile, str, None]) -> SpawnProfile:
    """Normalizes a raw string or enum value into a valid SpawnProfile."""
    if value is None:
        return DEFAULT_SPAWN_PROFILE
    if isinstance(value, SpawnProfile):
        return value
    if not isinstance(value, str):
        raise ValueError('spawn_profile must be a string or None.')
    val_str = value.strip().lower()
    for member in SpawnProfile:
        if member.value == val_str:
            return member
    raise ValueError("Invalid spawn_profile: must be 'normal' or 'testing'.")


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
        issues = player_config_issues(self)
        if issues:
            raise SettingsValidationError(issues)
        self.name = self.name.strip()
        self.color = tuple(self.color)
        self.controller = PlayerController(self.controller)
        if self.home_system_name is not None:
            self.home_system_name = self.home_system_name.strip() or None
            if self.home_system_name and self.home_system_name.lower() == 'random':
                self.home_system_name = None


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
    preview_only: InitVar[bool] = False

    @property
    def num_players(self) -> int:
        return len(self.player_configs)

    def validation_issues(self, *, for_preview=False):
        """Validate current values; preview mode never exempts a subsequent campaign start."""
        issues = []
        def add(field, message, code='invalid_settings'):
            issues.append(ValidationIssue(field, code, message))
        bounds = {'num_systems': (MIN_SYSTEMS, MAX_SYSTEMS),
                  'system_radius_min': (MIN_SYSTEM_RADIUS, MAX_SYSTEM_RADIUS),
                  'system_radius_max': (MIN_SYSTEM_RADIUS, MAX_SYSTEM_RADIUS)}
        for name, (lo, hi) in bounds.items():
            value = getattr(self, name)
            if not _integer(value) or not lo <= value <= hi:
                add(name, f'{name} must be an integer between {lo} and {hi}.')
        for name in ('min_system_distance', 'max_system_distance'):
            value = getattr(self, name)
            if not _finite(value) or value <= 0:
                add(name, f'{name} must be a finite positive number.')
        if not _finite(self.wormhole_density) or not 0 <= self.wormhole_density <= 1:
            add('wormhole_density', 'wormhole_density must be a finite number between 0 and 1.')
        invalid = {issue.field for issue in issues}
        if not invalid.intersection(('system_radius_min', 'system_radius_max')) and self.system_radius_min > self.system_radius_max:
            add('system_radius_min', f'Min System Radius ({self.system_radius_min}) cannot be greater than Max System Radius ({self.system_radius_max}).')
        if not invalid.intersection(('min_system_distance', 'max_system_distance')) and self.min_system_distance >= self.max_system_distance:
            add('min_system_distance', f'Min System Distance ({self.min_system_distance:g}) must be strictly less than Max System Distance ({self.max_system_distance:g}).')
        if for_preview:
            return issues
        for name in ('starting_credits', 'starting_metal', 'starting_crystal'):
            value = getattr(self, name)
            if not _finite(value) or value < 0:
                add(name, f'{name} must be a finite non-negative number.')
        if not _integer(self.starting_population) or self.starting_population < 0:
            add('starting_population', 'Starting population must be a non-negative integer.')
        try:
            normalize_spawn_profile(self.spawn_profile)
        except ValueError as exc:
            add('spawn_profile', str(exc))
        mode = self.home_system_assignment_mode
        if not isinstance(mode, str) or mode.strip().lower() not in ('random', 'specified'):
            add('home_system_assignment_mode', "Home assignment mode must be 'random' or 'specified'.")
        if not isinstance(self.player_configs, list) or not MIN_PLAYERS <= len(self.player_configs) <= MAX_PLAYERS:
            add('player_configs', f'A campaign must contain {MIN_PLAYERS}-{MAX_PLAYERS} players.', 'invalid_players')
        if isinstance(self.player_configs, list):
            names = set()
            valid_players = True
            for i, cfg in enumerate(self.player_configs):
                if not isinstance(cfg, PlayerConfig):
                    add(f'player_configs[{i}]', 'Expected a PlayerConfig.', 'invalid_player')
                    valid_players = False
                    continue
                player_issues = player_config_issues(cfg, f'player_configs[{i}]')
                issues.extend(player_issues)
                valid_players &= not player_issues
                if isinstance(cfg.name, str):
                    key = cfg.name.strip().casefold()
                    if key in names:
                        add(f'player_configs[{i}].name', 'Player names must be unique ignoring case.', 'invalid_player_name')
                    names.add(key)
            if valid_players and len(self.player_configs) >= MIN_PLAYERS and len({p.team_id for p in self.player_configs}) < 2:
                add('player_configs', 'Players must be grouped into at least two different teams.', 'invalid_teams')
        if not issues:
            issues.extend(ValidationIssue('start_conditions', 'invalid_settings', message)
                          for message in validate_start_conditions(self, self.pregenerated_galaxy))
        return issues

    def validate(self, *, for_preview=False) -> typing.List[str]:
        """Return errors without mutation; by default validate a complete campaign."""
        return [issue.message for issue in self.validation_issues(for_preview=for_preview)]

    def __post_init__(self, preview_only=False) -> None:
        issues = self.validation_issues(for_preview=preview_only)
        if issues:
            raise SettingsValidationError(issues)
        if not preview_only:
            self.spawn_profile = normalize_spawn_profile(self.spawn_profile)
            self.home_system_assignment_mode = self.home_system_assignment_mode.strip().lower()


def validate_start_conditions(settings, galaxy=None) -> typing.List[str]:
    """Shared, side-effect-free population and home-system rules for new games.

    Map previews pass no players; topology and faction checks are then independent.
    Existing saves do not pass through new-game validation.
    """
    errors = []
    if settings.starting_population < 0:
        errors.append("Starting population must be non-negative.")
    if settings.num_systems <= 0:
        errors.append("At least one star system is required.")
    homes = [(cfg, cfg.home_system_name.strip() if cfg.home_system_name else '')
             for cfg in settings.player_configs]
    assigned = [name for _, name in homes if name and name.lower() != 'random']
    if normalize_spawn_profile(settings.spawn_profile) == SpawnProfile.NORMAL:
        if settings.num_systems < settings.num_players:
            errors.append("Normal requires at least one distinct star system per player.")
        if len(assigned) != len(set(assigned)):
            errors.append("Normal requires distinct specified home systems.")
        if galaxy is not None and len(galaxy.systems) < settings.num_players:
            errors.append("The generated galaxy has too few systems for distinct Normal starts.")
    if galaxy is not None:
        if len(galaxy.systems) != settings.num_systems:
            errors.append(f"Requested {settings.num_systems} systems but the map contains {len(galaxy.systems)}. Regenerate the map or relax its distance constraints.")
        for cfg, name in homes:
            if name and name.lower() != "random":
                if name not in galaxy.systems:
                    errors.append(f"Assigned home system '{name}' for player '{cfg.name}' does not exist in the galaxy.")
    return errors
