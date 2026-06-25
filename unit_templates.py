import json
import os
from constants import HullSize

def _load_templates() -> dict:
    file_path = os.path.join(os.path.dirname(__file__), "data", "unit_templates.json")
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for key, template in data.items():
        if "hull_size" in template:
            template["hull_size"] = HullSize[template["hull_size"]]
    return data

UNIT_TEMPLATES = _load_templates()


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
