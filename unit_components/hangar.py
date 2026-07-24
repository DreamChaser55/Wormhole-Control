import logging
import math
import random
from typing import TYPE_CHECKING
import dataclasses

from .base import UnitComponent
from geometry import Position
from constants import HullSize, SECTOR_CIRCLE_RADIUS_LOGICAL

if TYPE_CHECKING:
    from entities import Unit
    from galaxy import Galaxy
    from game import Game

logger = logging.getLogger(__name__)

class HangarComponent(UnitComponent):
    """A component that allows a unit to store and transport smaller units."""
    DISPLAY_NAME: str = "Hangar"
    SIDEBAR_ORDER: int = 11
    max_slots: int = 0
    docked_units: list['Unit'] = dataclasses.field(default_factory=list)

    def __init__(self, unit: 'Unit', max_slots: int = 0, hull_cost: int = 0):
        super().__init__(unit, hull_cost=hull_cost)
        self.max_slots = max_slots
        self.docked_units = []

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        used_slots = self.get_used_slots()
        data.append({'type': 'label', 'text': f"Capacity: {used_slots} / {self.max_slots} slots", 'object_id': '#sidebar_info_label', 'height': 20})
        data.append({'type': 'label', 'text': "Docked Ships:", 'object_id': '#sidebar_section_header_label', 'height': 24})
        if not self.docked_units:
            data.append({'type': 'label', 'text': "  None", 'object_id': '#sidebar_info_label', 'height': 20})
        else:
            for docked_ship in self.docked_units:
                size_slots = 1 if docked_ship.hull_size == HullSize.TINY else 2
                ship_label = f"  - {docked_ship.name} ({size_slots} slot)" if size_slots == 1 else f"  - {docked_ship.name} ({size_slots} slots)"
                data.append({'type': 'label', 'text': ship_label, 'object_id': '#sidebar_info_label', 'height': 20})
                data.append({
                    'type': 'button',
                    'text': f"Deploy {docked_ship.name}",
                    'object_id': '#sidebar_expand_button',
                    'action_id': 'deploy_ship',
                    'target_data': (self.unit.id, docked_ship.id),
                    'height': 25
                })
        return data

    def get_used_slots(self) -> int:
        slots = 0
        for u in self.docked_units:
            if u.hull_size == HullSize.TINY:
                slots += 1
            elif u.hull_size == HullSize.SMALL:
                slots += 2
        return slots

    def can_dock(self, unit: 'Unit') -> bool:
        if unit.hull_size != HullSize.TINY:
            return False
        needed = 1
        return self.get_used_slots() + needed <= self.max_slots

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
        
        self.docked_units.append(unit)
        if unit.commander_component:
            unit.commander_component.clear_orders()
            
        logger.debug(f"Unit {unit.name} docked into carrier {self.unit.name}.")
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
        logger.debug(f"Unit {unit.name} deployed from carrier {self.unit.name}.")
        return True
