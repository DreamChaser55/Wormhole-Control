"""
gui/unit_editor_gui sub-package

Provides the in-game Unit Designer GUI component split into focused sub-modules.
"""

from .window import UnitEditorWindow
from .catalog import (
    COMPONENT_ROWS,
    HULL_SIZE_NAMES,
    TURRET_TYPES,
    TURRET_VARIANTS,
    ABILITY_NAMES,
    HYPERDRIVE_TYPES,
    WING_TYPES,
)

__all__ = [
    "UnitEditorWindow",
    "COMPONENT_ROWS",
    "HULL_SIZE_NAMES",
    "TURRET_TYPES",
    "TURRET_VARIANTS",
    "ABILITY_NAMES",
    "HYPERDRIVE_TYPES",
    "WING_TYPES",
]
