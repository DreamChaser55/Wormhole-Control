import dataclasses
import logging
import typing
from typing import Optional, List, ClassVar, TYPE_CHECKING
from geometry import Position
from utils import HexCoord
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


class AbilityInstance:
    """Base runtime state for a single ability on a unit."""
    DEFINITION: ClassVar[AbilityDefinition]

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
