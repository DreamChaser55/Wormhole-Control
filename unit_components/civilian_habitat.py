import logging
from typing import TYPE_CHECKING, List, Dict, Optional, Any

from .base import UnitComponent

if TYPE_CHECKING:
    from entities import Unit, CelestialBody, Planet, Moon, ColonizableAsteroid
    from galaxy import Galaxy
    from game import Game

logger = logging.getLogger(__name__)


class CivilianHabitatComponent(UnitComponent):
    """A component that provides economic credit bonuses per turn if stationed
    in a sector with a colonized celestial object (Planet, Moon, or ColonizableAsteroid)
    up to the colony's population-supported capacity limit.
    """
    DISPLAY_NAME: str = "Civilian Habitat"
    SIDEBAR_ORDER: int = 10

    def __init__(self, unit: 'Unit', economic_bonus: float = 50.0, hull_cost: float = 15.0):
        super().__init__(unit, hull_cost=hull_cost)
        self.economic_bonus: float = float(economic_bonus)

    @staticmethod
    def calc_hull_cost(economic_bonus: float = 50.0) -> float:
        """Calculates hull cost based on economic bonus rate."""
        # 15.0 base hull cost for baseline 50 credits/turn bonus
        if economic_bonus <= 0:
            return 0.0
        return float(max(5.0, (economic_bonus / 50.0) * 15.0))

    def has_colonized_celestial_object_in_sector(self, galaxy: Optional['Galaxy'] = None) -> bool:
        """Checks if the unit's current sector contains a colonized celestial body
        (Planet, Moon, ColonizableAsteroid with population > 0) owned by the unit's owner.
        """
        if self.is_destroyed:
            return False

        if not self.unit or not self.unit.owner:
            return False

        g = galaxy or getattr(self.unit, 'in_galaxy', None)
        if not g and getattr(self.unit, 'game', None):
            g = getattr(self.unit.game, 'galaxy', None)

        if not g or not self.unit.in_system or not self.unit.in_hex:
            return False

        system = g.systems.get(self.unit.in_system)
        if not system:
            return False

        hex_obj = system.hexes.get(self.unit.in_hex)
        if not hex_obj:
            return False

        from entities import Planet, Moon, ColonizableAsteroid
        for body in hex_obj.celestial_bodies:
            if isinstance(body, (Planet, Moon, ColonizableAsteroid)):
                if getattr(body, 'owner', None) == self.unit.owner and getattr(body, 'population', 0) > 0:
                    return True

        return False

    def get_sector_habitat_status(self, galaxy: Optional['Galaxy'] = None) -> Dict[str, Any]:
        """Calculates detailed status of the habitat component, including sector capacity,
        active slot allocation, and whether this habitat is actively generating credits.
        """
        if self.is_destroyed:
            return {
                'active': False,
                'reason': 'Destroyed',
                'slot': 0,
                'capacity': 0,
                'active_count': 0,
                'total_habitats': 0
            }

        if not self.unit or not self.unit.owner:
            return {
                'active': False,
                'reason': 'No Owner',
                'slot': 0,
                'capacity': 0,
                'active_count': 0,
                'total_habitats': 0
            }

        g = galaxy or getattr(self.unit, 'in_galaxy', None)
        if not g and getattr(self.unit, 'game', None):
            g = getattr(self.unit.game, 'galaxy', None)

        if not g or not self.unit.in_system or not self.unit.in_hex:
            return {
                'active': False,
                'reason': 'Inactive (No Colonized Sector Object)',
                'slot': 0,
                'capacity': 0,
                'active_count': 0,
                'total_habitats': 0
            }

        system = g.systems.get(self.unit.in_system)
        if not system:
            return {
                'active': False,
                'reason': 'Inactive (No Colonized Sector Object)',
                'slot': 0,
                'capacity': 0,
                'active_count': 0,
                'total_habitats': 0
            }

        hex_obj = system.hexes.get(self.unit.in_hex)
        if not hex_obj:
            return {
                'active': False,
                'reason': 'Inactive (No Colonized Sector Object)',
                'slot': 0,
                'capacity': 0,
                'active_count': 0,
                'total_habitats': 0
            }

        sector_capacity = 0
        has_colonized_body = False
        from entities import Planet, Moon, ColonizableAsteroid
        for body in hex_obj.celestial_bodies:
            if isinstance(body, (Planet, Moon, ColonizableAsteroid)):
                if getattr(body, 'owner', None) == self.unit.owner and getattr(body, 'population', 0) > 0:
                    has_colonized_body = True
                    if hasattr(body, 'get_supported_habitat_capacity'):
                        sector_capacity += body.get_supported_habitat_capacity()
                    else:
                        from constants import BASE_HABITAT_CAPACITY, POPULATION_PER_HABITAT
                        sector_capacity += max(BASE_HABITAT_CAPACITY, int(getattr(body, 'population', 0) // POPULATION_PER_HABITAT))

        if not has_colonized_body or sector_capacity <= 0:
            return {
                'active': False,
                'reason': 'Inactive (No Colonized Sector Object)',
                'slot': 0,
                'capacity': 0,
                'active_count': 0,
                'total_habitats': 0
            }

        habitat_units = []
        for u in hex_obj.units:
            if u.owner == self.unit.owner:
                comp = getattr(u, 'civilian_habitat_component', None)
                if comp and not comp.is_destroyed:
                    habitat_units.append(u)

        habitat_units.sort(key=lambda u: u.id)
        total_habitats = len(habitat_units)
        slot = habitat_units.index(self.unit) + 1 if self.unit in habitat_units else 0
        active_count = min(total_habitats, sector_capacity)

        if 1 <= slot <= sector_capacity:
            active = True
            reason = f"Active (+{int(self.economic_bonus)} Credits/Turn [Slot {slot}/{sector_capacity}])"
        else:
            active = False
            reason = f"Inactive (Colony Capacity Reached: {sector_capacity}/{sector_capacity})"

        return {
            'active': active,
            'reason': reason,
            'slot': slot,
            'capacity': sector_capacity,
            'active_count': active_count,
            'total_habitats': total_habitats
        }

    def is_active(self, galaxy: Optional['Galaxy'] = None) -> bool:
        """Returns whether this civilian habitat component is currently active and
        generating credits based on sector colony support capacity.
        """
        return self.get_sector_habitat_status(galaxy).get('active', False)

    def get_sidebar_data(self, game_state: 'Game') -> List[Dict]:
        data = super().get_sidebar_data(game_state)
        if self.is_destroyed:
            return data

        galaxy = getattr(game_state, 'galaxy', None)
        status_info = self.get_sector_habitat_status(galaxy)

        data.append({
            'type': 'label',
            'text': f"Habitat Bonus: {status_info['reason']}",
            'object_id': '#sidebar_info_label',
            'height': 20
        })
        return data

    def get_basic_sidebar_data(self, game_state: 'Game') -> List[Dict]:
        data = super().get_basic_sidebar_data(game_state)
        if self.is_destroyed:
            return data

        galaxy = getattr(game_state, 'galaxy', None)
        status_info = self.get_sector_habitat_status(galaxy)
        if status_info['active']:
            text = f"• Civilian Habitat: +{int(self.economic_bonus)} Credits/Turn [{status_info['slot']}/{status_info['capacity']}]"
            obj_id = '#sidebar_value_label'
        elif status_info['capacity'] > 0:
            text = f"• Civilian Habitat: Inactive (Capacity {status_info['capacity']}/{status_info['capacity']} Reached)"
            obj_id = '#sidebar_info_label'
        else:
            text = "• Civilian Habitat: Inactive"
            obj_id = '#sidebar_info_label'

        data.append({
            'type': 'label',
            'text': text,
            'object_id': obj_id,
            'height': 18,
            'indent_level': 1
        })
        return data

