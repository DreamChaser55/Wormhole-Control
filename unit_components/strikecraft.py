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
from constants import HullSize, SECTOR_CIRCLE_RADIUS_LOGICAL, STRIKECRAFT_BAY_HULL_COST_PER_SLOT

if TYPE_CHECKING:
    from domain.units import Unit
    from galaxy import Galaxy
    from game import Game

logger = logging.getLogger(__name__)

class StrikecraftWingComponent(UnitComponent):
    """A component specifically for STRIKECRAFT_WING (strikecraft wings) to track individual fighter counts."""
    STATE_CONFIG = ('wing_type',)
    STATE_RUNTIME = ('recovery_ready_round', 'last_flak_round', 'last_flak_owner_id')
    STATE_REFS = ('mother_carrier',)
    DISPLAY_NAME: str = "Strikecraft Wing"
    SIDEBAR_ORDER: int = 13
    mother_carrier: typing.Optional['Unit'] = None

    def __init__(self, unit: 'Unit', wing_type: WingType = WingType.FIGHTER, hull_cost: float = 0.0):
        super().__init__(unit, hull_cost=hull_cost)
        self.mother_carrier = None
        self.wing_type: WingType = wing_type
        self.recovery_ready_round = 0
        self.last_flak_round = 0
        self.last_flak_owner_id = None

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
        from strikecraft_abilities import wing_order, evasion, round_now
        root = wing_order(self.unit)
        if root:
            data.append({'type': 'label', 'text': f"{root.order_type.name.replace('_', ' ').title()}: {root.phase}", 'object_id': '#sidebar_info_label', 'height': 20})
        if evasion(self.unit):
            data.append({'type': 'label', 'text': 'Evasive: incoming damage 50%; outgoing 75%', 'object_id': '#sidebar_info_label', 'height': 20})
        if self.recovery_ready_round > round_now(game_state.galaxy):
            data.append({'type': 'label', 'text': 'Recovering: launch available next owner turn', 'object_id': '#sidebar_info_label', 'height': 20})
        return data

    def validate_state(self):
        from state_codec import number
        if self.last_flak_owner_id is not None:
            number(self.last_flak_owner_id, 'last_flak_owner_id', 0, integer=True)

    def get_basic_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_basic_sidebar_data(game_state)
        if self.is_destroyed:
            return data
        role_str = "Fighter" if self.wing_type == WingType.FIGHTER else "Bomber"
        obj_id = '#sidebar_status_active_label' if self.active_fighters > 0 else '#sidebar_status_idle_label'
        data.append({
            'type': 'label',
            'text': f"• Strikecraft ({role_str}): {self.active_fighters}/4 active",
            'object_id': obj_id,
            'height': 18,
            'indent_level': 1
        })
        return data


class StrikecraftBayComponent(UnitComponent):
    """A component that allows a unit to store, transport, and automatically construct/replenish strikecraft wings."""
    STATE_CONFIG = ('max_slots',)
    STATE_RUNTIME = ('constructing', 'construction_progress', 'replenish_progress', 'build_wing_type')
    STATE_REFS = ('replenishing_unit',)
    STATE_CHILDREN = ("docked_units",)

    def on_destroyed(self) -> None:
        from campaign_graph import iter_units
        galaxy = self.unit.in_galaxy or getattr(self.unit.game, "galaxy", None)
        for unit, _ in iter_units(galaxy):
            wing = unit.strikecraft_wing_component
            if wing and wing.mother_carrier is self.unit and unit not in self.docked_units:
                wing.mother_carrier = None
        self.launched_units.clear()

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

    def __init__(self, unit: 'Unit', max_slots: int = 0, hull_cost: float = 0.0):
        super().__init__(unit, hull_cost=hull_cost)
        self.max_slots = max_slots
        self.docked_units = []
        self.launched_units = []
        self.constructing = False
        self.construction_progress = 0
        self.replenishing_unit = None
        self.replenish_progress = 0
        self.build_wing_type = WingType.FIGHTER

    @property
    def production_template_name(self):
        return "FIGHTER_WING" if self.build_wing_type == WingType.FIGHTER else "BOMBER_WING"

    @property
    def production_template(self):
        from unit_templates import UNIT_TEMPLATES
        return UNIT_TEMPLATES[self.production_template_name]

    def can_set_production(self, template_name):
        return not self.is_destroyed and not self.constructing and template_name in ("FIGHTER_WING", "BOMBER_WING")

    def set_production(self, template_name):
        if not self.can_set_production(template_name):
            return False
        self.build_wing_type = WingType.FIGHTER if template_name == "FIGHTER_WING" else WingType.BOMBER
        return True

    @staticmethod
    def calc_hull_cost(slots: int) -> float:
        """Compute the hull cost of a Strikecraft Bay component from strikecraft_bay_slots."""
        if slots <= 0:
            return 0.0
        return float(slots * STRIKECRAFT_BAY_HULL_COST_PER_SLOT)

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        used_slots = self.get_used_slots()
        data.append({'type': 'label', 'text': f"Capacity: {used_slots} / {self.max_slots} wings", 'object_id': '#sidebar_info_label', 'height': 20})
        if self.constructing:
            role_text = "Fighter" if self.build_wing_type == WingType.FIGHTER else "Bomber"
            data.append({'type': 'label', 'text': f"Constructing {role_text} Wing ({self.construction_progress + 1}/{self.production_template['build_time']} turns)", 'object_id': '#sidebar_info_label', 'height': 20})
        elif self.replenishing_unit:
            data.append({'type': 'label', 'text': f"Replenishing Wing: {self.replenishing_unit.name}", 'object_id': '#sidebar_info_label', 'height': 20})
        
        is_owner = self.unit.owner == game_state.players[game_state.current_player_index]

        if is_owner and not self.constructing and not self.is_destroyed:
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

        from domain.celestials import is_position_in_magnetic_storm
        galaxy_ref = getattr(self.unit.game, 'galaxy', None) if getattr(self.unit, 'game', None) else None
        in_magnetic_storm = is_position_in_magnetic_storm(galaxy_ref, self.unit.in_system, self.unit.in_hex, self.unit.position)
        if in_magnetic_storm:
            data.append({'type': 'label', 'text': "  ⚠ Magnetic Storm: Wings cannot launch", 'object_id': '#sidebar_status_charging_label', 'height': 20})

        if self.docked_units and is_owner and not in_magnetic_storm:
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
                if is_owner and not in_magnetic_storm and self.can_deploy(docked_ship, galaxy_ref):
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

    def get_basic_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_basic_sidebar_data(game_state)
        if self.is_destroyed:
            return data
        used_slots = self.get_used_slots()
        docked_cnt = len(self.docked_units)
        launched_cnt = len(self.launched_units)
        data.append({
            'type': 'label',
            'text': f"• Strikecraft Wings: {used_slots}/{self.max_slots} ({docked_cnt} docked, {launched_cnt} launched)",
            'object_id': '#sidebar_value_label',
            'height': 18,
            'indent_level': 1
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
            unit.commander_component.clear_explicit_orders()
            unit.commander_component.suspend_stance_activity("docked")
            
        logger.debug(f"Strikecraft wing {unit.name} docked into carrier {self.unit.name}.")
        return True

    def can_deploy(self, unit: 'Unit', galaxy_ref: 'Galaxy') -> bool:
        if unit not in self.docked_units:
            return False
        from strikecraft_abilities import round_now
        wing = unit.strikecraft_wing_component
        if wing and wing.recovery_ready_round > round_now(galaxy_ref):
            return False
        from domain.celestials import is_position_in_magnetic_storm
        if is_position_in_magnetic_storm(galaxy_ref, self.unit.in_system, self.unit.in_hex, self.unit.position):
            return False
        return True

    def deploy(self, unit: 'Unit', galaxy_ref: 'Galaxy') -> bool:
        if not self.can_deploy(unit, galaxy_ref):
            return False
        
        unit.in_system = self.unit.in_system
        unit.in_hex = self.unit.in_hex
        
        from domain.celestials import is_position_in_magnetic_storm
        attempts = 0
        while attempts < 100:
            attempts += 1
            angle = random.uniform(0, 2 * math.pi)
            offset_dist = random.uniform(20.0, 50.0)
            candidate_x = self.unit.position.x + math.cos(angle) * offset_dist
            candidate_y = self.unit.position.y + math.sin(angle) * offset_dist
            candidate_pos = Position(candidate_x, candidate_y)
            
            if self.unit.in_system is None:
                if math.hypot(candidate_x, candidate_y) > SECTOR_CIRCLE_RADIUS_LOGICAL:
                    continue
            if is_position_in_magnetic_storm(galaxy_ref, unit.in_system, unit.in_hex, candidate_pos):
                continue
            unit.position = candidate_pos
            break
        else:
            logger.debug(f"Strikecraft wing {unit.name} cannot deploy: Launch zone obstructed by magnetic storm.")
            return False
        
        system = galaxy_ref.systems.get(unit.in_system)
        if system:
            system.add_unit(unit)
            
        self.docked_units.remove(unit)
        self.launched_units.append(unit)
        logger.debug(f"Strikecraft wing {unit.name} deployed from carrier {self.unit.name}.")
        return True

    def finish_auto_construction(self, galaxy: 'Galaxy'):
        """Creates the new Strikecraft Wing and docks it."""
        from unit_templates import UNIT_TEMPLATES
        
        template_name = "FIGHTER_WING" if self.build_wing_type == WingType.FIGHTER else "BOMBER_WING"
        template = UNIT_TEMPLATES.get(template_name)
        if not template:
            logger.debug(f"Error: Unit template '{template_name}' not found for auto-construction.")
            return
 
        from .constructor import assemble_unit_from_template
        new_unit = assemble_unit_from_template(
            template_name, template, self.unit.owner, self.unit.in_system,
            self.unit.in_hex, Position(self.unit.position.x, self.unit.position.y), self.unit.game)

        new_unit.strikecraft_wing_component.mother_carrier = self.unit

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
            if self.construction_progress >= self.production_template['build_time']:
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
            cost = self.production_template["build_cost"]
            if owner.credits >= cost:
                owner.credits -= cost
                self.constructing = True
                self.construction_progress = 0
                role_text = "Fighter" if self.build_wing_type == WingType.FIGHTER else "Bomber"
                logger.debug(f"Strikecraft bay on {self.unit.name} started constructing new {role_text} Wing for {cost} credits.")
                return
