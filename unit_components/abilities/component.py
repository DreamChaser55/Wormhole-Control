import dataclasses
import logging
from typing import Dict, List, Optional, TYPE_CHECKING
from geometry import Position
from utils import HexCoord
from ..base import UnitComponent
from ..enums import AbilityType
from .base import AbilityInstance, AbilityDefinition
from .registry import ABILITY_CLASSES, ABILITY_DEFINITIONS

if TYPE_CHECKING:
    from entities import Unit
    from galaxy import Galaxy
    from game import Game

logger = logging.getLogger(__name__)


class AbilityComponent(UnitComponent):
    """
    Manages the set of special abilities available to a unit.

    Each ability has its own cooldown and active-duration tracking. This component
    is responsible for ticking cooldowns, applying ongoing effects each turn
    (e.g. Repair Cloud healing, Designate Target marking), and cleaning up expired
    effects. If this component is destroyed the unit cannot use any abilities.
    """
    DISPLAY_NAME: str = "Abilities"
    SIDEBAR_ORDER: int = 14
    abilities: Dict[AbilityType, AbilityInstance] = dataclasses.field(default_factory=dict)

    def __init__(self, unit: 'Unit', ability_types: List[AbilityType], hull_cost: int = 10):
        super().__init__(unit, hull_cost=hull_cost)
        self.abilities: Dict[AbilityType, AbilityInstance] = {}
        for atype in ability_types:
            cls = ABILITY_CLASSES.get(atype)
            if cls:
                self.abilities[atype] = cls()
            else:
                logger.warning(f"[AbilityComponent] Unknown ability type: {atype}")

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        status = "DESTROYED" if self.is_destroyed else f"HP: {self.current_hit_points}/{self.max_hit_points}"
        data = [{
            'type': 'label',
            'text': f"Ability System [{status}]",
            'object_id': '#sidebar_section_header_label',
            'height': 28,
        }]

        # Show Ion Bolt / Designate Target targeting-mode indicator
        if game_state.pending_ability:
            pending_name = game_state.pending_ability[0].replace('_', ' ').title()
            data.append({
                'type': 'label',
                'text': f"\u25b6 Select target for: {pending_name}",
                'object_id': '#sidebar_hit_points_light_damage_label',
                'height': 22,
            })

        for ability_type, instance in self.abilities.items():
            defn = instance.definition
            if instance.is_active:
                cd_str = f"Active ({instance.duration_remaining} turns)"
                btn_obj_id = '#sidebar_section_header_label'
            elif instance.cooldown_remaining > 0:
                cd_str = f"Cooldown: {instance.cooldown_remaining} turns"
                btn_obj_id = '#sidebar_info_label'
            else:
                cd_str = "Ready"
                btn_obj_id = '#sidebar_expand_button'

            # Check if there is enough antimatter
            am_comp = self.unit.antimatter_component
            has_enough_am = True
            if am_comp and am_comp.current_amount < defn.antimatter_cost:
                has_enough_am = False

            btn_text = f"{defn.name} ({defn.antimatter_cost} AM) [{cd_str}]"
            data.append({
                'type': 'button',
                'text': btn_text,
                'object_id': btn_obj_id,
                'action_id': 'use_ability',
                'target_data': {
                    'ability_type_str': ability_type.value,
                    'requires_target_unit': defn.requires_target_unit,
                    'requires_target_position': defn.requires_target_position,
                },
                'height': 28,
                'enabled': instance.is_ready and not self.is_destroyed and has_enough_am,
            })
            data.append({
                'type': 'label',
                'text': f"  {defn.description}",
                'object_id': '#sidebar_info_label',
                'height': 18,
            })
        return data

    def can_use(self, ability_type: AbilityType) -> bool:
        """Returns True if the ability exists, the component is intact, it is off cooldown, and has enough antimatter."""
        if self.is_destroyed:
            return False
        instance = self.abilities.get(ability_type)
        if not instance:
            return False
        if not instance.is_ready:
            return False
        am_comp = self.unit.antimatter_component
        if am_comp and am_comp.current_amount < instance.definition.antimatter_cost:
            return False
        return True

    def activate(
        self,
        ability_type: AbilityType,
        galaxy: 'Galaxy',
        target_unit_id: Optional[int] = None,
        target_position: Optional[Position] = None,
        target_system_name: Optional[str] = None,
        target_hex_coord: Optional[HexCoord] = None,
    ) -> bool:
        """
        Activates the specified ability.

        Performs validation, applies immediate effects, and sets the active
        state. Returns True on success, False on failure.
        """
        if not self.can_use(ability_type):
            logger.debug(f"[{self.unit.name}] Cannot use {ability_type.name}: not ready, component destroyed, or low antimatter.")
            return False

        instance = self.abilities[ability_type]
        defn = instance.definition

        # --- Immediate activation effects ---
        success = instance.on_activate(
            component=self,
            galaxy=galaxy,
            target_unit_id=target_unit_id,
            target_position=target_position,
            target_system_name=target_system_name,
            target_hex_coord=target_hex_coord,
        )
        if not success:
            return False

        # --- Consume antimatter ---
        am_comp = self.unit.antimatter_component
        if am_comp:
            consumed = am_comp.consume(defn.antimatter_cost)
            if not consumed:
                logger.debug(f"[{self.unit.name}] Consume failed during activation (insufficient antimatter).")
                return False

        # --- Mark as active and set cooldown ---
        instance.is_active = (defn.duration > 0)
        instance.duration_remaining = defn.duration
        instance.target_position = target_position
        instance.cooldown_remaining = defn.cooldown
        return True

    def _expire_ability(self, ability_type: AbilityType, galaxy: 'Galaxy') -> None:
        """Cleans up lingering effects when an ability's duration expires."""
        instance = self.abilities[ability_type]
        instance.on_expire(self, galaxy)
        instance.is_active = False
        instance.duration_remaining = 0
        instance.target_position = None

    def update(self, galaxy: 'Galaxy') -> None:
        """
        Called once per turn. Ticks cooldowns, applies ongoing ability effects,
        and expires abilities whose duration has elapsed.
        """
        if self.is_destroyed:
            return

        for ability_type, instance in self.abilities.items():
            # --- Tick cooldown ---
            if instance.cooldown_remaining > 0:
                instance.cooldown_remaining -= 1

            # --- Apply ongoing effects for active abilities ---
            if instance.is_active:
                instance.on_turn_update(self, galaxy)

                # --- Tick duration ---
                if instance.duration_remaining > 0:
                    instance.duration_remaining -= 1

                # --- Check expiry ---
                if instance.duration_remaining <= 0:
                    self._expire_ability(ability_type, galaxy)
