"""Public component disclosure policy shared by UI and AI commands."""


def component_is_public(component_or_type, *, enemy: bool) -> bool:
    from unit_components.intelligence import IntelligenceComponent
    cls = component_or_type if isinstance(component_or_type, type) else type(component_or_type)
    return not (enemy and issubclass(cls, IntelligenceComponent))


def public_components(unit, *, enemy: bool):
    return [c for c in unit.components.values() if component_is_public(c, enemy=enemy)]


def public_target_components(unit):
    return sorted(type(c).__name__ for c in public_components(unit, enemy=True))
