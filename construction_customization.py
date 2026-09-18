"""Pure construction-only equipment overrides; never publish modified designs."""
from copy import deepcopy

TURRET_TYPES = ("mass_driver", "beam", "missile")
DEFENSE_TYPES = ("armor", "shields", "point_defense")
OVERRIDE_FIELDS = ("turret_type_override", "defense_type_override")


def validate_override_values(turret_type_override=None, defense_type_override=None):
    for name, value, choices in zip(OVERRIDE_FIELDS,
                                    (turret_type_override, defense_type_override),
                                    (TURRET_TYPES, DEFENSE_TYPES)):
        if value is not None and (not isinstance(value, str) or value not in choices):
            raise ValueError(f"{name} must be null or one of {', '.join(choices)}.")


def validate_template_overrides(template, turret_type_override=None, defense_type_override=None):
    validate_override_values(turret_type_override, defense_type_override)
    if turret_type_override is not None and (
            not template or not template.get("has_weapon_bays") or not template.get("turrets")):
        raise ValueError("turret_type_override requires a template with installed turrets.")
    if defense_type_override is not None and (
            not template or not template.get("has_defenses")
            or sum(template.get(field, 0) for field in DEFENSE_TYPES) <= 0):
        raise ValueError("defense_type_override requires a template with positive defense strength.")


def customize_template(template, turret_type_override=None, defense_type_override=None):
    """Keep authored stats/costs intact, including unscaled Long Range turret stats."""
    validate_template_overrides(template, turret_type_override, defense_type_override)
    result = deepcopy(template)
    if turret_type_override is not None:
        for turret in result["turrets"]:
            turret["type"] = turret_type_override.upper()
    if defense_type_override is not None:
        total = sum(result.get(field, 0) for field in DEFENSE_TYPES)
        for field in DEFENSE_TYPES:
            result[field] = total if field == defense_type_override else 0
    return result
