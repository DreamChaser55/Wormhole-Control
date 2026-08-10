import logging
from typing import TYPE_CHECKING, List, Dict, Optional

from .base import UnitComponent

if TYPE_CHECKING:
    from entities import Unit, CelestialBody, Planet, Moon, ColonizableAsteroid
    from galaxy import Galaxy
    from game import Game

logger = logging.getLogger(__name__)


class CivilianHabitatComponent(UnitComponent):
    """A component that provides economic credit bonuses per turn if stationed

    in a sector with a colonized celestial object (Planet, Moon, or ColonizableAsteroid).
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

    def get_sidebar_data(self, game_state: 'Game') -> List[Dict]:
        data = super().get_sidebar_data(game_state)
        if self.is_destroyed:
            return data

        galaxy = getattr(game_state, 'galaxy', None)
        active = self.has_colonized_celestial_object_in_sector(galaxy)
        if active:
            status_str = f"Active (+{int(self.economic_bonus)} Credits/Turn)"
        else:
            status_str = "Inactive (No Colonized Sector Object)"

        data.append({
            'type': 'label',
            'text': f"Habitat Bonus: {status_str}",
            'object_id': '#sidebar_info_label',
            'height': 20
        })
        return data

    def get_basic_sidebar_data(self, game_state: 'Game') -> List[Dict]:
        data = super().get_basic_sidebar_data(game_state)
        if self.is_destroyed:
            return data

        galaxy = getattr(game_state, 'galaxy', None)
        active = self.has_colonized_celestial_object_in_sector(galaxy)
        text = f"• Civilian Habitat: +{int(self.economic_bonus)} Credits/Turn" if active else "• Civilian Habitat: Inactive"
        data.append({
            'type': 'label',
            'text': text,
            'object_id': '#sidebar_value_label' if active else '#sidebar_info_label',
            'height': 18,
            'indent_level': 1
        })
        return data
