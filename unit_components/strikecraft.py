import logging
import typing
from typing import Optional, TYPE_CHECKING
import dataclasses
import math
import random

from .base import UnitComponent
from .enums import WingType, TurretType, TurretVariant
from .movement import Engines
from .weapons import Weapons, Turret
from geometry import Position
from constants import HullSize, SECTOR_CIRCLE_RADIUS_LOGICAL

if TYPE_CHECKING:
    from entities import Unit
    from galaxy import Galaxy
    from game import Game

logger = logging.getLogger(__name__)

class StrikecraftWingComponent(UnitComponent):
    """A component specifically for STRIKECRAFT_WING (strikecraft wings) to track individual fighter counts."""
    DISPLAY_NAME: str = "Strikecraft Wing"
    SIDEBAR_ORDER: int = 13
    mother_carrier: typing.Optional['Unit'] = None

    def __init__(self, unit: 'Unit', wing_type: WingType = WingType.FIGHTER, hull_cost: int = 0):
        super().__init__(unit, hull_cost=hull_cost)
        self.mother_carrier = None
        self.wing_type: WingType = wing_type

    @property
    def active_fighters(self) -> int:
        if self.unit.current_hit_points <= 0:
            return 0
        return math.ceil((self.unit.current_hit_points / self.unit.max_hit_points) * 4)

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        role_str = "Fighter" if self.wing_type == WingType.FIGHTER else "Bomber"
        data.append({'type': 'label', 'text': f"Role: {role_str}", 'object_id': '#sidebar_info_label', 'height': 20})
        data.append({'type': 'label', 'text': f"Active Craft: {self.active_fighters} / 4", 'object_id': '#sidebar_info_label', 'height': 20})
        mother_name = self.mother_carrier.name if self.mother_carrier else "None"
        data.append({'type': 'label', 'text': f"Mother Carrier: {mother_name}", 'object_id': '#sidebar_info_label', 'height': 20})
        return data


class StrikecraftBayComponent(UnitComponent):
    """A component that allows a unit to store, transport, and automatically construct/replenish strikecraft wings."""
    DISPLAY_NAME: str = "Strikecraft Bay"
    SIDEBAR_ORDER: int = 12
    max_slots: int = 0
    docked_units: list['Unit'] = dataclasses.field(default_factory=list)
    launched_units: list['Unit'] = dataclasses.field(default_factory=list)
    
    # Auto-construction and replenishment state
    constructing: bool = False
    construction_progress: int = 0
    replenishing_unit: typing.Optional['Unit'] = None
    replenish_progress: int = 0
    build_wing_type: WingType = WingType.FIGHTER

    def __init__(self, unit: 'Unit', max_slots: int = 0, hull_cost: int = 0):
        super().__init__(unit, hull_cost=hull_cost)
        self.max_slots = max_slots
        self.docked_units = []
        self.launched_units = []
        self.constructing = False
        self.construction_progress = 0
        self.replenishing_unit = None
        self.replenish_progress = 0
        self.build_wing_type = WingType.FIGHTER

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        used_slots = self.get_used_slots()
        data.append({'type': 'label', 'text': f"Capacity: {used_slots} / {self.max_slots} wings", 'object_id': '#sidebar_info_label', 'height': 20})
        if self.constructing:
            role_text = "Fighter" if self.build_wing_type == WingType.FIGHTER else "Bomber"
            data.append({'type': 'label', 'text': f"Constructing {role_text} Wing ({self.construction_progress + 1}/2 turns)", 'object_id': '#sidebar_info_label', 'height': 20})
        elif self.replenishing_unit:
            data.append({'type': 'label', 'text': f"Replenishing Wing: {self.replenishing_unit.name}", 'object_id': '#sidebar_info_label', 'height': 20})
        
        is_owner = self.unit.owner == game_state.players[game_state.current_player_index]

        if is_owner:
            role_text = "Fighter" if self.build_wing_type == WingType.FIGHTER else "Bomber"
            data.append({
                'type': 'button',
                'text': f"Target Wing Build: {role_text}",
                'object_id': '#sidebar_expand_button',
                'action_id': 'toggle_build_wing_type',
                'target_data': self.unit.id,
                'height': 25
            })

        # Docked Wings
        data.append({'type': 'label', 'text': "Docked Strikecraft Wings:", 'object_id': '#sidebar_section_header_label', 'height': 24})
        if self.docked_units and is_owner:
            data.append({
                'type': 'button',
                'text': "Launch All Wings",
                'object_id': '#sidebar_expand_button',
                'action_id': 'launch_all_wings',
                'target_data': self.unit.id,
                'height': 25
            })
        if not self.docked_units:
            data.append({'type': 'label', 'text': "  None", 'object_id': '#sidebar_info_label', 'height': 20})
        else:
            for docked_ship in self.docked_units:
                f_comp = docked_ship.strikecraft_wing_component
                f_count = f_comp.active_fighters if f_comp else 4
                role_str = f_comp.wing_type.value.capitalize() if f_comp else "Fighter"
                wing_label = f"  - {docked_ship.name} ({role_str}, {f_count}/4 craft, HP: {docked_ship.current_hit_points}/{docked_ship.max_hit_points})"
                data.append({'type': 'label', 'text': wing_label, 'object_id': '#sidebar_info_label', 'height': 20})
                if is_owner:
                    data.append({
                        'type': 'button',
                        'text': f"Deploy {docked_ship.name}",
                        'object_id': '#sidebar_expand_button',
                        'action_id': 'deploy_ship',
                        'target_data': (self.unit.id, docked_ship.id),
                        'height': 25
                    })

        # Launched Wings
        data.append({'type': 'label', 'text': "Launched Strikecraft Wings:", 'object_id': '#sidebar_section_header_label', 'height': 24})
        if not self.launched_units:
            data.append({'type': 'label', 'text': "  None", 'object_id': '#sidebar_info_label', 'height': 20})
        else:
            for launched_ship in self.launched_units:
                f_comp = launched_ship.strikecraft_wing_component
                f_count = f_comp.active_fighters if f_comp else 4
                role_str = f_comp.wing_type.value.capitalize() if f_comp else "Fighter"
                wing_label = f"  - {launched_ship.name} ({role_str}, {f_count}/4 craft, HP: {launched_ship.current_hit_points}/{launched_ship.max_hit_points})"
                data.append({'type': 'label', 'text': wing_label, 'object_id': '#sidebar_info_label', 'height': 20})
                if is_owner:
                    data.append({
                        'type': 'button',
                        'text': f"Recall {launched_ship.name}",
                        'object_id': '#sidebar_expand_button',
                        'action_id': 'recall_ship',
                        'target_data': (self.unit.id, launched_ship.id),
                        'height': 25
                    })
        return data

    def get_used_slots(self) -> int:
        return len(self.docked_units) + len(self.launched_units)

    def can_dock(self, unit: 'Unit') -> bool:
        if unit.hull_size != HullSize.STRIKECRAFT_WING:
            return False
        if unit in self.launched_units:
            return True
        return self.get_used_slots() < self.max_slots

    def dock(self, unit: 'Unit', galaxy_ref: 'Galaxy') -> bool:
        if not self.can_dock(unit):
            return False
        
        # Remove from system
        if unit.in_system and unit.in_hex is not None:
            system = galaxy_ref.systems.get(unit.in_system)
            if system:
                system.remove_unit(unit)
        
        unit.in_system = self.unit.in_system
        unit.in_hex = self.unit.in_hex
        unit.position = Position(self.unit.position.x, self.unit.position.y)
        
        if unit in self.launched_units:
            self.launched_units.remove(unit)
        
        # Orphaned wings are adopted
        if unit.strikecraft_wing_component:
            unit.strikecraft_wing_component.mother_carrier = self.unit
        
        self.docked_units.append(unit)
        if unit.commander_component:
            unit.commander_component.clear_orders()
            
        logger.debug(f"Strikecraft wing {unit.name} docked into carrier {self.unit.name}.")
        return True

    def deploy(self, unit: 'Unit', galaxy_ref: 'Galaxy') -> bool:
        if unit not in self.docked_units:
            return False
        
        unit.in_system = self.unit.in_system
        unit.in_hex = self.unit.in_hex
        
        while True:
            angle = random.uniform(0, 2 * math.pi)
            offset_dist = random.uniform(20.0, 50.0)
            candidate_x = self.unit.position.x + math.cos(angle) * offset_dist
            candidate_y = self.unit.position.y + math.sin(angle) * offset_dist
            
            if self.unit.in_system is None:
                if math.hypot(candidate_x, candidate_y) <= SECTOR_CIRCLE_RADIUS_LOGICAL:
                    unit.position = Position(candidate_x, candidate_y)
                    break
            else:
                unit.position = Position(candidate_x, candidate_y)
                break
        
        system = galaxy_ref.systems.get(unit.in_system)
        if system:
            system.add_unit(unit)
            
        self.docked_units.remove(unit)
        self.launched_units.append(unit)
        logger.debug(f"Strikecraft wing {unit.name} deployed from carrier {self.unit.name}.")
        return True

    def finish_auto_construction(self, galaxy: 'Galaxy'):
        """Creates the new Strikecraft Wing and docks it."""
        from entities import Unit # Avoid circular import
        from unit_templates import UNIT_TEMPLATES
        
        template_name = "FIGHTER_WING" if self.build_wing_type == WingType.FIGHTER else "BOMBER_WING"
        template = UNIT_TEMPLATES.get(template_name)
        if not template:
            logger.debug(f"Error: Unit template '{template_name}' not found for auto-construction.")
            return
 
        new_unit = Unit(
            owner=self.unit.owner,
            name=template["name"],
            hull_size=template["hull_size"],
            game=self.unit.game,
            in_system=self.unit.in_system,
            in_hex=self.unit.in_hex,
            position=Position(self.unit.position.x, self.unit.position.y),
            template_name=template.get("name", template_name)
        )

        if template.get("has_engine"):
            new_unit.add_component(Engines(new_unit, speed=template.get("engine_speed", 0), hull_cost=template.get("engine_hull_cost", 0)))
        
        if template.get("has_weapon_bays"):
            weapons_comp = Weapons(new_unit, hull_cost=template.get("weapon_bays_hull_cost", 0))
            for turret_def in template.get("turrets", []):
                variant_str = turret_def.get("variant", "STANDARD")
                try:
                    variant = TurretVariant[variant_str.upper()]
                except (KeyError, ValueError, AttributeError):
                    variant = TurretVariant.STANDARD

                turret = Turret(
                    turret_type=TurretType[turret_def["type"]],
                    damage=turret_def["damage"],
                    range=turret_def["range"],
                    cooldown=turret_def["cooldown"],
                    parent_unit=new_unit,
                    variant=variant
                )
                weapons_comp.add_turret(turret)
            new_unit.add_component(weapons_comp)

        wing_comp = StrikecraftWingComponent(new_unit, wing_type=self.build_wing_type)
        wing_comp.mother_carrier = self.unit
        new_unit.add_component(wing_comp)

        # Direct dock
        self.docked_units.append(new_unit)
        logger.debug(f"Auto-constructed and docked new strikecraft wing {new_unit.name} ({new_unit.id}) for carrier {self.unit.name}.")

    def update(self, galaxy: 'Galaxy'):
        """Automatically constructs or replenishes wings. Called each turn."""
        if self.is_destroyed:
            return

        # Prune destroyed launched units
        self.launched_units = [u for u in self.launched_units if u.current_hit_points > 0]

        owner = self.unit.owner
        if not owner:
            return

        # 1. Update ongoing replenishment
        if self.replenishing_unit:
            # If the unit was deployed or destroyed in the meantime, cancel replenishment
            if self.replenishing_unit not in self.docked_units or self.replenishing_unit.current_hit_points <= 0:
                self.replenishing_unit = None
                self.replenish_progress = 0
            else:
                self.replenish_progress += 1
                if self.replenish_progress >= 1: # 1 turn to replenish 1 fighter (10 HP)
                    self.replenishing_unit.heal_hull(10)
                    logger.debug(f"Strikecraft bay on {self.unit.name} replenished 1 craft in wing {self.replenishing_unit.name}. HP: {self.replenishing_unit.current_hit_points}/{self.replenishing_unit.max_hit_points}")
                    # If fully healed, clear. Otherwise keep replenishing on next turn
                    if self.replenishing_unit.current_hit_points >= self.replenishing_unit.max_hit_points:
                        self.replenishing_unit = None
                        self.replenish_progress = 0
                    else:
                        # Start next replenishment step immediately if we have credits
                        cost = 35
                        if owner.credits >= cost:
                            owner.credits -= cost
                            self.replenish_progress = 0
                        else:
                            self.replenishing_unit = None
                            self.replenish_progress = 0
                return

        # 2. Update ongoing construction
        if self.constructing:
            self.construction_progress += 1
            if self.construction_progress >= 2: # 2 turns to construct a new wing
                self.finish_auto_construction(galaxy)
                self.constructing = False
                self.construction_progress = 0
            return

        # 3. If not busy, check if we need to replenish a damaged wing
        damaged_wing = None
        for wing in self.docked_units:
            if wing.current_hit_points < wing.max_hit_points:
                damaged_wing = wing
                break

        if damaged_wing:
            cost = 35
            if owner.credits >= cost:
                owner.credits -= cost
                self.replenishing_unit = damaged_wing
                self.replenish_progress = 0
                logger.debug(f"Strikecraft bay on {self.unit.name} started replenishing wing {damaged_wing.name} for {cost} credits.")
                return

        # 4. If not busy and we have free slots, start constructing a new wing
        if self.get_used_slots() < self.max_slots:
            cost = 150
            if owner.credits >= cost:
                owner.credits -= cost
                self.constructing = True
                self.construction_progress = 0
                role_text = "Fighter" if self.build_wing_type == WingType.FIGHTER else "Bomber"
                logger.debug(f"Strikecraft bay on {self.unit.name} started constructing new {role_text} Wing for {cost} credits.")
                return
