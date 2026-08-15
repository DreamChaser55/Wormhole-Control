import logging
from typing import TYPE_CHECKING, List, Dict, Optional, Any

from .base import UnitComponent
from constants import (
    DEFAULT_ORBITAL_DEFENSE_RADIUS,
    DEFAULT_ORBITAL_DEFENSE_ATTACK_BONUS,
    DEFAULT_ORBITAL_DEFENSE_DEFENSE_BONUS,
    ORBITAL_DEFENSE_HULL_COST,
    BASE_ORBITAL_DEFENSE_CAPACITY,
    POPULATION_PER_ORBITAL_DEFENSE,
)

if TYPE_CHECKING:
    from entities import Unit, CelestialBody, Planet, Moon, ColonizableAsteroid
    from galaxy import Galaxy
    from game import Game

logger = logging.getLogger(__name__)


class OrbitalDefenseComponent(UnitComponent):
    """A component that provides area of effect enhancements to attack and defense stats
    of friendly ships within its effective radius.
    
    Functions exclusively in a sector with a friendly colonized celestial object
    (Planet, Moon, or ColonizableAsteroid) up to the colony's population-supported capacity limit.
    """
    DISPLAY_NAME: str = "Orbital Defense"
    SIDEBAR_ORDER: int = 10

    def __init__(
        self,
        unit: 'Unit',
        radius: float = DEFAULT_ORBITAL_DEFENSE_RADIUS,
        attack_bonus: float = DEFAULT_ORBITAL_DEFENSE_ATTACK_BONUS,
        defense_bonus: float = DEFAULT_ORBITAL_DEFENSE_DEFENSE_BONUS,
        hull_cost: float = ORBITAL_DEFENSE_HULL_COST
    ):
        super().__init__(unit, hull_cost=hull_cost)
        self.radius: float = float(radius)
        self.attack_bonus: float = float(attack_bonus)
        self.defense_bonus: float = float(defense_bonus)

    @staticmethod
    def calc_hull_cost(hull_cost: float = ORBITAL_DEFENSE_HULL_COST) -> float:
        """Calculates hull cost of the Orbital Defense component."""
        return float(hull_cost)

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

    def get_sector_orbital_defense_status(self, galaxy: Optional['Galaxy'] = None) -> Dict[str, Any]:
        """Calculates detailed status of the orbital defense component, including sector capacity,
        active slot allocation, and whether this orbital defense is actively projecting its aura.
        """
        if self.is_destroyed:
            return {
                'active': False,
                'reason': 'Destroyed',
                'slot': 0,
                'capacity': 0,
                'active_count': 0,
                'total_orbital_defenses': 0
            }

        if not self.unit or not self.unit.owner:
            return {
                'active': False,
                'reason': 'No Owner',
                'slot': 0,
                'capacity': 0,
                'active_count': 0,
                'total_orbital_defenses': 0
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
                'total_orbital_defenses': 0
            }

        system = g.systems.get(self.unit.in_system)
        if not system:
            return {
                'active': False,
                'reason': 'Inactive (No Colonized Sector Object)',
                'slot': 0,
                'capacity': 0,
                'active_count': 0,
                'total_orbital_defenses': 0
            }

        hex_obj = system.hexes.get(self.unit.in_hex)
        if not hex_obj:
            return {
                'active': False,
                'reason': 'Inactive (No Colonized Sector Object)',
                'slot': 0,
                'capacity': 0,
                'active_count': 0,
                'total_orbital_defenses': 0
            }

        sector_capacity = 0
        has_colonized_body = False
        from entities import Planet, Moon, ColonizableAsteroid
        for body in hex_obj.celestial_bodies:
            if isinstance(body, (Planet, Moon, ColonizableAsteroid)):
                if getattr(body, 'owner', None) == self.unit.owner and getattr(body, 'population', 0) > 0:
                    has_colonized_body = True
                    if hasattr(body, 'get_supported_orbital_defense_capacity'):
                        sector_capacity += body.get_supported_orbital_defense_capacity()
                    else:
                        sector_capacity += max(
                            BASE_ORBITAL_DEFENSE_CAPACITY,
                            int(getattr(body, 'population', 0) // POPULATION_PER_ORBITAL_DEFENSE)
                        )

        if not has_colonized_body or sector_capacity <= 0:
            return {
                'active': False,
                'reason': 'Inactive (No Colonized Sector Object)',
                'slot': 0,
                'capacity': 0,
                'active_count': 0,
                'total_orbital_defenses': 0
            }

        od_units = []
        for u in hex_obj.units:
            if u.owner == self.unit.owner:
                comp = getattr(u, 'orbital_defense_component', None)
                if comp and not comp.is_destroyed:
                    od_units.append(u)

        od_units.sort(key=lambda u: u.id)
        total_ods = len(od_units)
        slot = od_units.index(self.unit) + 1 if self.unit in od_units else 0
        active_count = min(total_ods, sector_capacity)

        atk_pct = int(self.attack_bonus * 100)
        def_pct = int(self.defense_bonus * 100)

        if 1 <= slot <= sector_capacity:
            active = True
            reason = f"Active (+{atk_pct}% Atk / +{def_pct}% Def, Radius {int(self.radius)}) [Slot {slot}/{sector_capacity}]"
        else:
            active = False
            reason = f"Inactive (Colony Capacity Reached: {sector_capacity}/{sector_capacity})"

        return {
            'active': active,
            'reason': reason,
            'slot': slot,
            'capacity': sector_capacity,
            'active_count': active_count,
            'total_orbital_defenses': total_ods
        }

    def is_active(self, galaxy: Optional['Galaxy'] = None) -> bool:
        """Returns whether this orbital defense component is currently active and
        projecting its enhancement aura based on sector colony support capacity.
        """
        return self.get_sector_orbital_defense_status(galaxy).get('active', False)

    def get_sidebar_data(self, game_state: 'Game') -> List[Dict]:
        data = super().get_sidebar_data(game_state)
        if self.is_destroyed:
            return data

        galaxy = getattr(game_state, 'galaxy', None)
        status_info = self.get_sector_orbital_defense_status(galaxy)

        data.append({
            'type': 'label',
            'text': f"Orbital Defense: {status_info['reason']}",
            'object_id': '#sidebar_info_label',
            'height': 20
        })
        return data

    def get_basic_sidebar_data(self, game_state: 'Game') -> List[Dict]:
        data = super().get_basic_sidebar_data(game_state)
        if self.is_destroyed:
            return data

        galaxy = getattr(game_state, 'galaxy', None)
        status_info = self.get_sector_orbital_defense_status(galaxy)
        atk_pct = int(self.attack_bonus * 100)
        def_pct = int(self.defense_bonus * 100)

        if status_info['active']:
            text = f"• Orbital Defense: +{atk_pct}% Atk/+{def_pct}% Def (R{int(self.radius)}) [{status_info['slot']}/{status_info['capacity']}]"
            obj_id = '#sidebar_value_label'
        elif status_info['capacity'] > 0:
            text = f"• Orbital Defense: Inactive (Capacity {status_info['capacity']}/{status_info['capacity']} Reached)"
            obj_id = '#sidebar_info_label'
        else:
            text = "• Orbital Defense: Inactive"
            obj_id = '#sidebar_info_label'

        data.append({
            'type': 'label',
            'text': text,
            'object_id': obj_id,
            'height': 18,
            'indent_level': 1
        })
        return data
