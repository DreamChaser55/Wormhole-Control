import dataclasses
import logging
import typing
from typing import Optional, List, ClassVar, TYPE_CHECKING
from geometry import Position
from domain.coordinates import HexCoord
from ..enums import AbilityType

if TYPE_CHECKING:
    from galaxy import Galaxy
    from .component import AbilityComponent

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class AbilityDefinition:
    """Static definition of an ability's properties (shared across all units)."""
    ability_type: AbilityType
    name: str
    description: str
    cooldown: int            # Turns before the ability can be used again
    duration: int            # Turns the effect persists (0 = instant / one-shot)
    range: float             # Max targeting distance in logical units (0 = self only)
    requires_target_unit: bool       # True if the ability needs a unit to be selected
    requires_target_position: bool   # True if the ability needs a position click
    antimatter_cost: int = 0         # Cost in antimatter to activate this ability
    required_components: List[str] = dataclasses.field(default_factory=list)  # Component flags required on the unit design to equip this ability

    @property
    def target_kind(self):
        from tactical_balance import SPECS
        spec = SPECS.get(self.ability_type.value)
        return spec.target_kind if spec else 'unit' if self.requires_target_unit else 'position' if self.requires_target_position else 'self'

    @property
    def allowed_relations(self):
        if self.ability_type.value in ('attack_run', 'tracking_lock'):
            return ['enemy']
        if self.ability_type.value in ('evasive_formation', 'emergency_recovery'):
            return ['self']
        if self.ability_type.value == 'guardian_link':
            return ['self', 'ally']
        if self.ability_type.value == 'tractor_tether':
            return ['self', 'ally', 'enemy']
        return []

    @property
    def automatic_approach(self):
        from tactical_balance import STRIKECRAFT_ABILITIES
        if self.ability_type.value in STRIKECRAFT_ABILITIES:
            return False
        return self.requires_target_unit or (self.ability_type.value == 'cluster_warhead')

    @property
    def local_sector(self):
        from tactical_balance import SPECS
        return self.ability_type.value in SPECS



class AbilityInstance:
    """Base runtime state for a single ability on a unit."""
    DEFINITION: ClassVar[AbilityDefinition]
    SCHEMA_VERSION = 1
    STATE_FIELDS = ("cooldown_remaining", "is_active", "duration_remaining", "target_unit_id",
                    "target_position", "spawned_unit_ids")

    def to_state(self):
        from state_codec import encode
        return {"type": self.definition.ability_type.value, "schema_version": self.SCHEMA_VERSION,
                "definition": {f.name: encode(getattr(self.definition, f.name)) for f in dataclasses.fields(AbilityDefinition)},
                "runtime": {name: encode(getattr(self, name)) for name in self.STATE_FIELDS}}

    @classmethod
    def from_state(cls, state):
        from state_codec import decode, fields, number
        from .registry import ABILITY_CLASSES
        fields(state, ("type", "schema_version", "definition", "runtime"), "ability")
        atype = AbilityType(state["type"])
        ability_cls = ABILITY_CLASSES[atype]
        if type(state["schema_version"]) is not int or state["schema_version"] != ability_cls.SCHEMA_VERSION:
            raise ValueError(f"Unsupported ability schema for {atype.value}")
        fields(state["definition"], (f.name for f in dataclasses.fields(AbilityDefinition)), "ability.definition")
        definition = AbilityDefinition(**{k: decode(v) for k, v in state["definition"].items()})
        if definition.ability_type != atype:
            raise ValueError("Ability definition type mismatch")
        for name in ("cooldown", "duration", "range", "antimatter_cost"):
            number(getattr(definition, name), f"ability.definition.{name}", 0, integer=name in ("cooldown", "duration"))
        for name in ("requires_target_unit", "requires_target_position"):
            if type(getattr(definition, name)) is not bool:
                raise ValueError(f"ability.definition.{name}: expected boolean")
        if any(not isinstance(getattr(definition, name), str) for name in ("name", "description")):
            raise ValueError("Ability name/description must be strings")
        if not isinstance(definition.required_components, list) or any(not isinstance(v, str) for v in definition.required_components):
            raise ValueError("Ability required_components must be an array of strings")
        fields(state["runtime"], ability_cls.STATE_FIELDS, "ability.runtime")
        instance = ability_cls(definition=definition)
        for name in instance.STATE_FIELDS:
            setattr(instance, name, decode(state["runtime"][name]))
        for name in ("cooldown_remaining", "duration_remaining"):
            number(getattr(instance, name), f"ability.{name}", 0, integer=True)
        if type(instance.is_active) is not bool:
            raise ValueError("ability.is_active: expected boolean")
        if instance.target_unit_id is not None:
            number(instance.target_unit_id, "ability.target_unit_id", 0, integer=True)
        if instance.target_position is not None and not isinstance(instance.target_position, Position):
            raise ValueError("ability.target_position: expected position")
        if not isinstance(instance.spawned_unit_ids, list):
            raise ValueError("ability.spawned_unit_ids: expected array")
        for uid in instance.spawned_unit_ids:
            number(uid, "ability.spawned_unit_ids", 0, integer=True)
        if len(set(instance.spawned_unit_ids)) != len(instance.spawned_unit_ids):
            raise ValueError("ability.spawned_unit_ids: duplicate ID")
        if hasattr(instance, "validate_state"):
            instance.validate_state()
        return instance

    def restore_effect(self, component, galaxy):
        """Rebuild this effect's contribution without activation side effects."""
        pass

    definition: AbilityDefinition
    cooldown_remaining: int = 0
    is_active: bool = False
    duration_remaining: int = 0
    target_unit_id: Optional[int] = None
    target_position: Optional[Position] = None
    # For Missile Batteries: track spawned platform unit IDs
    spawned_unit_ids: List[int] = dataclasses.field(default_factory=list)

    def __init__(
        self,
        definition: Optional[AbilityDefinition] = None,
        cooldown_remaining: int = 0,
        is_active: bool = False,
        duration_remaining: int = 0,
        target_unit_id: Optional[int] = None,
        target_position: Optional[Position] = None,
        spawned_unit_ids: Optional[List[int]] = None,
    ):
        if definition is None:
            definition = getattr(self, "DEFINITION", None)
        self.definition = definition
        self.cooldown_remaining = cooldown_remaining
        self.is_active = is_active
        self.duration_remaining = duration_remaining
        self.target_unit_id = target_unit_id
        self.target_position = target_position
        self.spawned_unit_ids = spawned_unit_ids if spawned_unit_ids is not None else []

    @property
    def is_ready(self) -> bool:
        """True if the ability is off cooldown and not currently active."""
        return self.cooldown_remaining <= 0 and not self.is_active

    def on_activate(
        self,
        component: 'AbilityComponent',
        galaxy: 'Galaxy',
        target_unit_id: Optional[int] = None,
        target_position: Optional[Position] = None,
        target_system_name: Optional[str] = None,
        target_hex_coord: Optional[HexCoord] = None,
    ) -> bool:
        """
        Executed when the ability is activated. Returns True if activation succeeded,
        False if activation failed/aborted.
        """
        return True

    def on_turn_update(self, component: 'AbilityComponent', galaxy: 'Galaxy') -> None:
        """Executed each turn while the ability is active."""
        pass

    def on_expire(self, component: 'AbilityComponent', galaxy: 'Galaxy') -> None:
        """Executed when the ability duration expires."""
        pass
