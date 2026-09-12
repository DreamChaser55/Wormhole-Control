"""Unit display names shared by construction, human controls and AI commands."""
import unicodedata


MAX_UNIT_NAME_LENGTH = 30


def normalize_unit_name(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Unit name must be a string.")
    if any(unicodedata.category(char) == "Cc" for char in value):
        raise ValueError("Unit name must not contain control characters.")
    name = value.strip()
    if not 1 <= len(name) <= MAX_UNIT_NAME_LENGTH:
        raise ValueError("Unit name must contain 1–30 characters after trimming.")
    return name


def rename_unit(unit, new_name: str) -> None:
    """Assign a validated name; callers authorize ownership before calling."""
    unit.name = normalize_unit_name(new_name)


def initial_unit_name(template) -> str:
    if "default_unit_name" in template:
        return normalize_unit_name(template["default_unit_name"])
    return template["name"]
