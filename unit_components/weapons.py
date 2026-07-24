import logging
import typing
from typing import Optional, TYPE_CHECKING
import dataclasses

from .base import UnitComponent
from .enums import TurretType, TurretVariant, WingType
from geometry import distance
from constants import (
    HullSize, XP_WEAPON_DAMAGE_BONUS
)

if TYPE_CHECKING:
    from entities import Unit
    from galaxy import Galaxy
    from game import Game

logger = logging.getLogger(__name__)

@dataclasses.dataclass
class Turret:
    """
    A dataclass representing a single turret on a unit.
    This is not a component, but a data structure used by the Weapons component.
    """
    turret_type: TurretType
    damage: float
    range: float
    cooldown: int
    parent_unit: 'Unit'
    variant: TurretVariant = TurretVariant.STANDARD
    current_cooldown: int = 0
    target: Optional['Unit'] = None
    target_component_type: Optional[type] = None

    def __post_init__(self) -> None:
        if self.variant == TurretVariant.LONG_RANGE:
            self.range *= 3.0
            self.cooldown *= 3

    def fire(self) -> None:
        """
        Fires at the turret's current target and resets the cooldown.
        Damage is amplified if the target is marked by Designate Target.
        The parent unit earns XP equal to the actual damage dealt.
        """
        if self.target:
            # Apply damage amplification from Designate Target (stacks additively)
            effective_damage = self.damage
            if self.target.damage_amplification > 0.0:
                effective_damage = self.damage * (1.0 + self.target.damage_amplification)

            # Apply XP weapon damage bonus from the firing unit
            effective_damage *= self.parent_unit.xp_multiplier(XP_WEAPON_DAMAGE_BONUS)

            # Anti-strikecraft damage reduced to 25% against other targets
            if self.variant == TurretVariant.ANTI_STRIKECRAFT and self.target.hull_size != HullSize.STRIKECRAFT_WING:
                effective_damage *= 0.25

            # Record target HP before damage to compute actual damage dealt for XP
            hp_before = self.target.current_hit_points

            if self.target_component_type:
                logger.debug(f"Turret {self.turret_type.name} from {self.parent_unit.name} firing at {self.target.name}'s {self.target_component_type.__name__}! (effective dmg: {effective_damage:.1f})")
                spillover = self.target.take_component_damage(self.target_component_type, int(effective_damage), damage_type=self.turret_type)
                if spillover > 0:
                    self.target.take_damage(spillover)
            else:
                logger.debug(f"Turret {self.turret_type.name} from {self.parent_unit.name} firing at {self.target.name}! (effective dmg: {effective_damage:.1f})")
                self.target.take_damage(int(effective_damage), damage_type=self.turret_type)

            # Award XP based on actual HP lost (overkill damage does not grant bonus XP)
            xp_earned = max(0, hp_before - self.target.current_hit_points)
            if xp_earned > 0:
                self.parent_unit.gain_experience(xp_earned)

        self.current_cooldown = self.cooldown

    def update(self) -> None:
        """
        Updates the turret's state, primarily its cooldown.
        """
        if self.current_cooldown > 0:
            self.current_cooldown -= 1


class Weapons(UnitComponent):
    """
    Manages all weapon systems for a unit.
    """
    DISPLAY_NAME: str = "Weapons"
    SIDEBAR_ORDER: int = 1
    turrets: list[Turret] = dataclasses.field(default_factory=list)

    def __init__(self, unit: 'Unit', hull_cost: int = 0):
        super().__init__(unit, hull_cost=hull_cost)
        self.turrets = []

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        xp = self.unit.experience_points
        xp_dmg_mult = self.unit.xp_multiplier(XP_WEAPON_DAMAGE_BONUS)
        for i, turret in enumerate(self.turrets):
            if i > 0:
                # Add a small vertical space between turrets
                data.append({
                    'type': 'label',
                    'text': '',
                    'object_id': '#sidebar_info_label',
                    'height': 5,
                    'indent_level': 1
                })
            
            variant_str = turret.variant.name.replace('_', ' ').title()
            type_str = turret.turret_type.name.replace('_', ' ').title()
            
            header_text = f"• Turret {i + 1}: {variant_str} {type_str}"
            data.append({
                'type': 'label',
                'text': header_text,
                'object_id': '#sidebar_info_label',
                'height': 20,
                'indent_level': 1
            })
            
            if xp > 0:
                effective_dmg = turret.damage * xp_dmg_mult
                bonus_pct = int((xp_dmg_mult - 1.0) * 100)
                stats_text = f"Damage: {turret.damage} (+{bonus_pct}% XP → {effective_dmg:.1f}) | Range: {turret.range} | Cooldown: {turret.cooldown}t"
            else:
                stats_text = f"Damage: {turret.damage} | Range: {turret.range} | Cooldown: {turret.cooldown}t"
            data.append({
                'type': 'label',
                'text': stats_text,
                'object_id': '#sidebar_info_label',
                'height': 18,
                'indent_level': 2
            })
            
            cooldown_status = f"On Cooldown ({turret.current_cooldown}t)" if turret.current_cooldown > 0 else "Ready"
            
            target_str = "None"
            if turret.target:
                if turret.target_component_type:
                    comp_name = getattr(turret.target_component_type, 'DISPLAY_NAME', turret.target_component_type.__name__)
                    target_str = f"{turret.target.name} ({comp_name})"
                else:
                    target_str = f"{turret.target.name} (Hull)"
                    
            status_text = f"Status: {cooldown_status} | Target: {target_str}"
            data.append({
                'type': 'label',
                'text': status_text,
                'object_id': '#sidebar_info_label',
                'height': 18,
                'indent_level': 2
            })
        return data

    def add_turret(self, turret: Turret) -> None:
        """
        Adds a pre-configured turret to the unit.
        """
        self.turrets.append(turret)

    def update(self, galaxy: 'Galaxy') -> None:
        """
        Updates all turrets and fires if a target is set and is in the same system, hex, in range and the cooldown is over.
        """
        if self.is_destroyed:
            return

        for turret in self.turrets:
            turret.update()

        for turret in self.turrets:
            if turret.target:
                if turret.target.current_hit_points <= 0:
                    turret.target = None
                    turret.target_component_type = None
                    continue

                target_in_same_system = self.unit.in_system == turret.target.in_system
                target_in_same_hex = self.unit.in_hex == turret.target.in_hex
                target_in_range = distance(self.unit.position, turret.target.position) < turret.range

                if target_in_same_system and target_in_same_hex and target_in_range:
                    if turret.current_cooldown <= 0:
                        turret.fire()

    def set_target(self, target_unit: 'Unit', target_component_type: Optional[type] = None) -> None:
        """Sets the target of the turrets to the specified unit and optionally a specific component."""
        for turret in self.turrets:
            if target_unit:
                # Standard and Long Range turrets cannot target strikecraft (strikecraft wings)
                if target_unit.hull_size == HullSize.STRIKECRAFT_WING and turret.variant != TurretVariant.ANTI_STRIKECRAFT:
                    continue

                # Attacker is a strikecraft wing:
                if self.unit.hull_size == HullSize.STRIKECRAFT_WING:
                    wing_comp = self.unit.strikecraft_wing_component
                    if wing_comp:
                        if wing_comp.wing_type == WingType.FIGHTER:
                            # Fighters can only attack strikecraft wings
                            if target_unit.hull_size != HullSize.STRIKECRAFT_WING:
                                continue
                        elif wing_comp.wing_type == WingType.BOMBER:
                            # Bombers can only attack non-strikecraft units
                            if target_unit.hull_size == HullSize.STRIKECRAFT_WING:
                                continue
            turret.target = target_unit
            turret.target_component_type = target_component_type
    
    def clear_target(self) -> None:
        """Clears the target of the turrets."""
        for turret in self.turrets:
            turret.target = None
            turret.target_component_type = None
