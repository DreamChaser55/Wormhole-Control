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

BASE_TURRET_COST: float = 1.0          # flat per turret
DMG_PER_POINT: float = 5.0             # hull points per unit of damage
RANGE_PER_POINT: float = 100.0         # hull points per unit of range
COOLDOWN_BONUS: float = 2.0            # hull points granted by short cooldown


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

            # Apply Orbital Defense attack bonus if within active friendly aura
            if hasattr(self.parent_unit, 'get_orbital_defense_buffs'):
                od_atk_bonus, _ = self.parent_unit.get_orbital_defense_buffs()
                if od_atk_bonus > 0.0:
                    effective_damage *= (1.0 + od_atk_bonus)

            # Apply weapons sabotage damage reduction
            if hasattr(self.parent_unit, 'is_sabotaged'):
                from .enums import SabotageType
                if self.parent_unit.is_sabotaged(SabotageType.WEAPONS):
                    effective_damage *= 0.5

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

    def __init__(self, unit: 'Unit', hull_cost: float = 0.0):
        super().__init__(unit, hull_cost=hull_cost)
        self.turrets = []

    @staticmethod
    def calc_turret_hull_cost(turret: typing.Any) -> float:
        """Compute the hull cost of a single turret based on its stats."""
        effective_range = turret.range
        effective_cooldown = max(1, turret.cooldown)

        variant_val = getattr(turret, "variant", "")
        variant_name = variant_val.name if hasattr(variant_val, "name") else str(variant_val)
        if variant_name.upper() == "LONG_RANGE":
            effective_range *= 3.0
            effective_cooldown *= 3

        cost = (
            BASE_TURRET_COST
            + turret.damage / DMG_PER_POINT
            + effective_range / RANGE_PER_POINT
            + COOLDOWN_BONUS / effective_cooldown
        )
        return float(cost)

    @staticmethod
    def calc_hull_cost(turrets: typing.List[typing.Any]) -> float:
        """Compute the total hull cost of a Weapons component from its turrets."""
        if not turrets:
            return 0.0
        return sum(Weapons.calc_turret_hull_cost(t) for t in turrets)

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
            
            galaxy_ref = getattr(game_state, 'galaxy', None) if game_state else None
            od_atk_bonus, _ = self.unit.get_orbital_defense_buffs(galaxy_ref) if hasattr(self.unit, 'get_orbital_defense_buffs') else (0.0, 0.0)
            total_mult = xp_dmg_mult * (1.0 + od_atk_bonus)
            effective_dmg = turret.damage * total_mult
            bonus_parts = []
            if xp > 0:
                bonus_parts.append(f"+{int((xp_dmg_mult - 1.0) * 100)}% XP")
            if od_atk_bonus > 0:
                bonus_parts.append(f"+{int(od_atk_bonus * 100)}% OD")
            if bonus_parts:
                stats_text = f"Damage: {turret.damage} ({', '.join(bonus_parts)} → {effective_dmg:.1f}) | Range: {turret.range} | Cooldown: {turret.cooldown}t"
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

    def get_basic_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_basic_sidebar_data(game_state)
        if self.is_destroyed:
            return data

        if not self.turrets:
            data.append({
                'type': 'label',
                'text': "• Turrets: None",
                'object_id': '#sidebar_status_idle_label',
                'height': 18,
                'indent_level': 1
            })
            return data

        xp_dmg_mult = self.unit.xp_multiplier(XP_WEAPON_DAMAGE_BONUS)
        data.append({
            'type': 'label',
            'text': f"• Turrets ({len(self.turrets)}):",
            'object_id': '#sidebar_component_header_label',
            'height': 18,
            'indent_level': 1
        })
        for i, turret in enumerate(self.turrets, 1):
            variant_str = turret.variant.name.replace('_', ' ').title()
            type_str = turret.turret_type.name.replace('_', ' ').title()
            eff_dmg = turret.damage * xp_dmg_mult
            cd_str = f" [CD: {turret.current_cooldown}t]" if turret.current_cooldown > 0 else ""
            turret_obj_id = '#sidebar_status_charging_label' if turret.current_cooldown > 0 else '#sidebar_value_label'
            data.append({
                'type': 'label',
                'text': f"Turret {i}: {variant_str} {type_str} (Dmg {eff_dmg:.1f}, Rng {int(turret.range)}){cd_str}",
                'object_id': turret_obj_id,
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
        Updates all turrets and fires if a target is set, visible, in the same system, hex, in range and the cooldown is over.
        """
        if self.is_destroyed:
            return

        for turret in self.turrets:
            turret.update()

        visibility_snapshot = None
        if any(t.target for t in self.turrets) and self.unit.owner and galaxy:
            from visibility import VisibilityService
            turn_num = getattr(galaxy, 'turn_number', 1)
            if hasattr(galaxy, 'game') and hasattr(galaxy.game, 'turn_number'):
                turn_num = getattr(galaxy.game, 'turn_number', 1)
            visibility_snapshot = VisibilityService.compute(galaxy, self.unit.owner, turn_number=turn_num)

        for turret in self.turrets:
            if turret.target:
                if turret.target.current_hit_points <= 0:
                    turret.target = None
                    turret.target_component_type = None
                    continue

                if visibility_snapshot is not None:
                    from visibility import is_unit_visible
                    if not is_unit_visible(visibility_snapshot, turret.target):
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
