"""Domain representation of an active construction job marker."""
from typing import Optional, Any
from geometry import Position
from constants import HullSize, HULL_BASE_ICON_SCALES, SECTOR_VIEW_BASE_ICON_SIZE
from unit_templates import UNIT_TEMPLATES, get_all_templates_for_player
from unit_naming import initial_unit_name


class ConstructionJob:
    """Represents an active construction site being built by a constructor unit."""

    def __init__(self, constructor_unit: Any):
        self.constructor_unit = constructor_unit
        self.constructor = getattr(constructor_unit, "constructor_component", None)
        self._target = self.constructor.current_construction_target if self.constructor else None

        # Fixed site coordinates
        self.position: Position = self._target.get("position") if self._target else constructor_unit.position
        self.in_hex = self._target.get("hex_coord") if self._target else constructor_unit.in_hex
        self.in_system: str = self._target.get("system_name") if self._target else constructor_unit.in_system

        self.owner = constructor_unit.owner
        self.template_name: str = self._target.get("template_name", "") if self._target else ""

        # Lookup template details
        templates = get_all_templates_for_player(self.owner, base_templates=UNIT_TEMPLATES)
        self.template = templates.get(self.template_name)
        if not self.template:
            for key, tmpl in templates.items():
                if key.lower() == self.template_name.lower() or tmpl.get("name", "").lower() == self.template_name.lower():
                    self.template = tmpl
                    break
        if not self.template:
            self.template = {}

        self.display_name = initial_unit_name(self.template) if self.template else self.template_name
        self.hull_size: HullSize = self.template.get("hull_size", HullSize.MEDIUM) if self.template else HullSize.MEDIUM
        self.is_station: bool = not bool(self.template.get("has_engine", False) or self.template.get("engines", False))

        # Interactive / GameObject-like properties for UI and selection
        self.id = f"const_{constructor_unit.id}"
        self.name = f"Construction: {self.display_name}"
        self.is_solid = True
        self.current_hit_points = 0
        self.max_hit_points = 0

    @property
    def progress(self) -> int:
        return getattr(self.constructor, "construction_progress", 0) if self.constructor else 0

    @property
    def time_to_build(self) -> int:
        return getattr(self.constructor, "time_to_build", 0) if self.constructor else 0

    @property
    def percent(self) -> int:
        total = self.time_to_build
        if total <= 0:
            return 100
        return int((self.progress / total) * 100)

    @property
    def is_valid(self) -> bool:
        return bool(
            self.constructor_unit
            and not getattr(self.constructor_unit, "is_destroyed", False)
            and self.constructor
            and not self.constructor.is_destroyed
            and self.constructor.current_construction_target is not None
            and self.constructor.current_construction_target == self._target
        )

    @property
    def logical_radius(self) -> float:
        scale_factor = HULL_BASE_ICON_SCALES.get(self.hull_size, 1.0)
        return SECTOR_VIEW_BASE_ICON_SIZE * scale_factor

    def get_display_name(self, viewer=None) -> str:
        """Returns the appropriate display name respecting the viewer's visibility permissions."""
        if viewer is not None:
            from component_visibility import unit_details_are_public
            if not unit_details_are_public(self.constructor_unit, viewer):
                if self.template and "default_unit_name" in self.template:
                    return initial_unit_name(self.template)
                hull_label = self.hull_size.name.replace("_", " ").title() if hasattr(self.hull_size, "name") else "Unit"
                return f"Construction Site ({hull_label})"
        return self.display_name

    def __eq__(self, other):
        if not isinstance(other, ConstructionJob):
            return False
        return getattr(self.constructor_unit, "id", None) == getattr(other.constructor_unit, "id", None)

    def __hash__(self):
        return hash(self.id)

    def __repr__(self):
        return f"<ConstructionJob {self.display_name} at ({self.position.x:.0f}, {self.position.y:.0f}) by {self.constructor_unit.name}>"


def get_sector_construction_jobs(hex_obj, viewer=None) -> list[ConstructionJob]:
    """Finds all active construction jobs located in this sector hex, filtered by viewer visibility."""
    if not hex_obj:
        return []
    coord = hex_obj.coordinates() if hasattr(hex_obj, "coordinates") else (getattr(hex_obj, "q", 0), getattr(hex_obj, "r", 0))
    system_name = getattr(hex_obj, "in_system", None)

    jobs = []
    for unit in getattr(hex_obj, "units", ()):
        constructor = getattr(unit, "constructor_component", None)
        if (
            constructor
            and not getattr(constructor, "is_destroyed", False)
            and getattr(constructor, "current_construction_target", None)
        ):
            target = constructor.current_construction_target
            if target.get("system_name") == system_name and tuple(target.get("hex_coord", ())) == coord:
                if viewer is not None:
                    from domain.players import are_allies
                    if not are_allies(unit.owner, viewer):
                        game = getattr(unit, "game", None)
                        if game and hasattr(game, "is_unit_visible") and not game.is_unit_visible(unit):
                            continue
                jobs.append(ConstructionJob(unit))
    return jobs
