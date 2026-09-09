from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.units import Unit
    from game import Game

class UnitComponent:
    """Base class for all components that make up a Unit."""
    DISPLAY_NAME: str = "Component"
    SIDEBAR_ORDER: int = 100
    SCHEMA_VERSION = 1
    STATE_CONFIG = ()
    STATE_RUNTIME = ()
    STATE_REFS = ()
    STATE_CHILDREN = ()
    STATE_EXTRA = ()
    STATE_OPTIONAL_TYPES = {}
    STATE_REAL_FIELDS = ()

    def to_state(self):
        from state_codec import encode
        from save_manager import serialize_unit
        runtime = {name: encode(getattr(self, name)) for name in self.STATE_RUNTIME}
        runtime.update({name: getattr(self, name).id if getattr(self, name) is not None else None
                        for name in self.STATE_REFS})
        runtime.update({name: [serialize_unit(u) for u in getattr(self, name)]
                        for name in self.STATE_CHILDREN})
        runtime.update(self._extra_state())
        return {"type": type(self).__name__, "schema_version": self.SCHEMA_VERSION,
                "hull_cost": self.hull_cost, "current_hit_points": self.current_hit_points,
                "max_hit_points": self.max_hit_points,
                "configuration": {name: encode(getattr(self, name)) for name in self.STATE_CONFIG},
                "runtime": runtime}

    def restore_state(self, state, players_by_id=None, game=None):
        from state_codec import decode, fields, number
        from save_manager import deserialize_unit
        fields(state, ("type", "schema_version", "hull_cost", "current_hit_points",
                       "max_hit_points", "configuration", "runtime"), type(self).__name__)
        if state["type"] != type(self).__name__ or type(state["schema_version"]) is not int or state["schema_version"] != self.SCHEMA_VERSION:
            raise ValueError(f"Unsupported {type(self).__name__} schema")
        self.hull_cost = number(state["hull_cost"], "hull_cost", 0)
        self.max_hit_points = number(state["max_hit_points"], "max_hit_points", 1, integer=True)
        self.current_hit_points = number(state["current_hit_points"], "current_hit_points", 0, integer=True)
        if self.current_hit_points > self.max_hit_points:
            raise ValueError("Component HP exceeds maximum")
        fields(state["configuration"], self.STATE_CONFIG, "configuration")
        fields(state["runtime"], (*self.STATE_RUNTIME, *self.STATE_REFS, *self.STATE_CHILDREN, *self.STATE_EXTRA), "runtime")
        for section, names in (("configuration", self.STATE_CONFIG), ("runtime", self.STATE_RUNTIME)):
            for name in names:
                value = decode(state[section][name])
                default = getattr(self, name)
                if isinstance(default, bool):
                    if type(value) is not bool:
                        raise ValueError(f"{name}: expected boolean")
                elif isinstance(default, (int, float)):
                    number(value, name, 0, integer=type(default) is int and name not in self.STATE_REAL_FIELDS)
                elif name in self.STATE_OPTIONAL_TYPES:
                    if value is not None and not isinstance(value, self.STATE_OPTIONAL_TYPES[name]):
                        raise ValueError(f"{name}: unexpected value type")
                elif default is not None and not isinstance(value, type(default)):
                    raise ValueError(f"{name}: unexpected value type")
                setattr(self, name, value)
        self._saved_refs = {}
        for name in self.STATE_REFS:
            uid = state["runtime"][name]
            if uid is not None:
                number(uid, name, 0, integer=True)
            self._saved_refs[name] = uid
        for name in self.STATE_CHILDREN:
            children = state["runtime"][name]
            if not isinstance(children, list):
                raise ValueError(f"{name}: expected units array")
            setattr(self, name, [deserialize_unit(u, players_by_id or {}, game) for u in children])
        self._restore_extra_state(state["runtime"])
        self.validate_state()

    def validate_state(self):
        """Subtype invariants beyond envelope and field types."""
        pass

    def resolve_state(self, objects):
        for name, uid in getattr(self, "_saved_refs", {}).items():
            setattr(self, name, objects.get(uid) if uid is not None else None)
        self.__dict__.pop("_saved_refs", None)

    def _extra_state(self):
        return {}

    def _restore_extra_state(self, runtime):
        pass

    def __init__(self, unit: 'Unit', hull_cost: float = 0.0):
        self.unit: 'Unit' = unit
        self.hull_cost: float = float(hull_cost)
        self.max_hit_points: int = max(10, int(round(float(hull_cost) * 10)))
        self.current_hit_points: int = self.max_hit_points

    @property
    def is_destroyed(self) -> bool:
        return self.current_hit_points <= 0

    def on_destroyed(self) -> None:
        """Called when the component's hit points reach 0."""
        pass

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        """
        Returns a list of UI element definitions (labels, progress bars, buttons)
        to render in the sidebar when this component is selected in Components panel.
        """
        status = "DESTROYED" if self.is_destroyed else f"HP: {self.current_hit_points}/{self.max_hit_points}"
        return [
            {
                'type': 'label',
                'text': f"{self.DISPLAY_NAME} [{status}]",
                'object_id': '#sidebar_section_header_label',
                'height': 28
            }
        ]

    def get_basic_sidebar_data(self, game_state: 'Game') -> list[dict]:
        """
        Returns a list of concise UI element definitions for the Basic Info panel.
        Can be overridden by subclasses to highlight key component stats.
        """
        if self.is_destroyed:
            return [{
                'type': 'label',
                'text': f"• Destroyed Component: {self.DISPLAY_NAME}",
                'object_id': '#sidebar_hit_points_critical_damage_label',
                'height': 18,
                'indent_level': 1
            }]
        return []

    @staticmethod
    def calc_hull_cost(*args, **kwargs) -> float:
        """Compute the dynamic hull cost of the component from its design parameters."""
        return 0.0
