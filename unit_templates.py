import json
import os
from constants import HullSize

def _load_templates(filename: str = "unit_templates.json") -> dict:
    file_path = os.path.join(os.path.dirname(__file__), "data", filename)
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for key, template in data.items():
        if "hull_size" in template:
            template["hull_size"] = HullSize[template["hull_size"]]
    return data

UNIT_TEMPLATES = _load_templates()

# Membership is independent of the active catalogue, including during save loading.
TESTING_TEMPLATE_KEYS = frozenset(
    [f"SPAWN_{kind}_{hull}" for kind in ("SHIP", "STATION")
     for hull in ("TINY", "SMALL", "MEDIUM", "LARGE", "HUGE")]
    + ["SPAWN_CARRIER"]
)


def load_testing_templates() -> dict:
    """Read the Testing catalogue without making its designs buildable."""
    templates = _load_templates("test_unit_templates.json")
    if templates.keys() != TESTING_TEMPLATE_KEYS:
        raise ValueError("Testing catalogue must contain exactly the Testing starter templates.")
    return templates


def builtin_template_names() -> set[str]:
    """Reserve built-in keys and display names even when Testing is inactive."""
    templates = _load_templates() | load_testing_templates()
    return {name.lower() for key, value in templates.items()
            for name in (key, value.get("name", key))}


def lookup_legacy_template(name: str) -> dict:
    """Resolve historical save definitions without publishing Testing designs."""
    if name in TESTING_TEMPLATE_KEYS:
        return load_testing_templates().get(name, {})
    return UNIT_TEMPLATES.get(name, {})


def publish_testing_templates(templates: dict) -> None:
    """Replace the active Testing subset, preserving the shared dictionary."""
    for key in TESTING_TEMPLATE_KEYS:
        UNIT_TEMPLATES.pop(key, None)
    UNIT_TEMPLATES.update(templates)


def register_template(name: str, template: dict) -> None:
    """Insert or overwrite a template in UNIT_TEMPLATES at runtime.

    The template dict must already have its ``hull_size`` value as a
    :class:`~constants.HullSize` enum member (matching the convention used
    by :func:`_load_templates`).
    """
    UNIT_TEMPLATES[name] = template


def unregister_template(name: str) -> bool:
    """Remove a template from UNIT_TEMPLATES.  Returns True if it existed."""
    if name in UNIT_TEMPLATES:
        del UNIT_TEMPLATES[name]
        return True
    return False


# Private player-designed templates loaded from custom_unit_templates.json.
# Kept strictly separate from UNIT_TEMPLATES so built-in and private categories are disjoint.
PRIVATE_TEMPLATES: dict = {}


def get_template(name: str, player=None, base_templates: dict = None) -> dict:
    """Retrieve a template by name, respecting player privacy restrictions.

    Built-in templates are accessible to all players.
    Private templates are available to human players (and default callers without AI controller).
    Automated AI and Codex players receive strictly built-in templates.
    """
    builtins = base_templates if base_templates is not None else UNIT_TEMPLATES
    if name in builtins:
        return builtins[name]
    from player_controller import PlayerController
    if name in PRIVATE_TEMPLATES:
        controller = getattr(player, "controller", None) if player is not None else None
        if controller not in (PlayerController.OPENAI, PlayerController.CODEX):
            return PRIVATE_TEMPLATES[name]
    return None


def get_all_templates_for_player(player=None, base_templates: dict = None) -> dict:
    """Return all templates accessible to a given player.

    All players receive the built-in templates.
    Human players (and default callers) additionally receive private player-designed templates.
    Automated AI and Codex players receive strictly the built-in catalogue.
    """
    templates = dict(base_templates if base_templates is not None else UNIT_TEMPLATES)
    from player_controller import PlayerController
    controller = getattr(player, "controller", None) if player is not None else None
    if controller not in (PlayerController.OPENAI, PlayerController.CODEX):
        templates.update(PRIVATE_TEMPLATES)
    return templates
