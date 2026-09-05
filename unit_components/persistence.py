"""Canonical persistence registry. Refit aliases are accepted only by migrations."""


def component_registry():
    from .constructor import COMPONENT_NAME_MAP
    from .commander import Commander
    from .strikecraft import StrikecraftWingComponent
    classes = {*COMPONENT_NAME_MAP.values(), Commander, StrikecraftWingComponent}
    return {cls.__name__: cls for cls in classes}


def restore_component(state, unit, players_by_id, game):
    registry = component_registry()
    name = state.get("type") if isinstance(state, dict) else None
    if name not in registry:
        raise ValueError(f"Unknown component type: {name}")
    component = registry[name](unit)
    component.restore_state(state, players_by_id, game)
    return component
