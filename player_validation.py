"""Player value checks shared by new-game input and strict save restoration."""
import unicodedata

from game_ai.runtime import SUPPORTED_REASONING_EFFORTS, MIN_REPAIR_RETRIES, MAX_REPAIR_RETRIES
from persistence_paths import validate_identity
from player_controller import PlayerController


def is_integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def player_value_issues(values, *, require_trimmed=False):
    """Return field/code/message triples without coercion or mutation.

    Setup may trim names after validation; saved names must already be canonical.
    Campaign-wide uniqueness, map and spawn rules belong to their callers.
    """
    issues = []
    name = values.get('name')
    if (not isinstance(name, str) or not 1 <= len(name.strip()) <= 80
            or any(unicodedata.category(c).startswith('C') for c in name)
            or (require_trimmed and name != name.strip())):
        message = 'Player name must contain 1-80 characters without control characters.'
        if require_trimmed:
            message += ' Saved names must already be trimmed.'
        issues.append(('name', 'invalid_player_name', message))
    color = values.get('color')
    if (not isinstance(color, (tuple, list)) or len(color) != 3
            or any(not is_integer(c) or not 0 <= c <= 255 for c in color)):
        issues.append(('color', 'invalid_color', 'Player color must be three integers from 0 to 255.'))
    team = values.get('team_id')
    if not is_integer(team) or team < 1:
        issues.append(('team_id', 'invalid_team', 'Player team_id must be a positive integer.'))
    controller = values.get('controller')
    if not isinstance(controller, str) or controller not in tuple(c.value for c in PlayerController):
        issues.append(('controller', 'invalid_controller', 'Player controller must be human, openai, or codex.'))
    if values.get('ai_reasoning_effort') not in SUPPORTED_REASONING_EFFORTS:
        issues.append(('ai_reasoning_effort', 'invalid_reasoning_effort', 'AI reasoning effort must be low, medium, or high.'))
    retries = values.get('ai_repair_retries')
    if not is_integer(retries) or not MIN_REPAIR_RETRIES <= retries <= MAX_REPAIR_RETRIES:
        issues.append(('ai_repair_retries', 'invalid_repair_retries', f'AI repair retries must be between {MIN_REPAIR_RETRIES} and {MAX_REPAIR_RETRIES}.'))
    return issues


def validate_saved_player_values(data, path='player'):
    """Reject malformed identity/configuration before constructors can default it."""
    for field, _code, message in player_value_issues(data, require_trimmed=True):
        raise ValueError(f'{path}.{field}: {message}')
    for field in ('persistent_id', 'agent_id'):
        validate_identity(data.get(field), f'{path}.{field}')
    for field in ('id', 'homeworld_id'):
        value = data.get(field)
        if field == 'homeworld_id' and value is None:
            continue
        if not is_integer(value) or value < 0:
            raise ValueError(f'{path}.{field}: expected a non-negative integer')
