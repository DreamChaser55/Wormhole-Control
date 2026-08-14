import logging
from typing import Optional, TYPE_CHECKING
from geometry import Position, distance
from utils import HexCoord
from ..enums import AbilityType
from .base import AbilityDefinition, AbilityInstance

if TYPE_CHECKING:
    from galaxy import Galaxy
    from .component import AbilityComponent

logger = logging.getLogger(__name__)


class ScanForMinefieldsAbility(AbilityInstance):
    DEFINITION = AbilityDefinition(
        ability_type=AbilityType.SCAN_FOR_MINEFIELDS,
        name="Scan for Minefields",
        description="Emits a high-frequency sensor sweep that permanently reveals all enemy minefields within range in the sector.",
        cooldown=6,
        duration=0,
        range=1500.0,
        requires_target_unit=False,
        requires_target_position=False,
        antimatter_cost=35,
        required_components=["has_sensors"],
    )

    def on_activate(
        self,
        component: 'AbilityComponent',
        galaxy: 'Galaxy',
        target_unit_id: Optional[int] = None,
        target_position: Optional[Position] = None,
        target_system_name: Optional[str] = None,
        target_hex_coord: Optional[HexCoord] = None,
    ) -> bool:
        unit = component.unit
        sys_name = target_system_name if target_system_name is not None else unit.in_system
        hex_coord = target_hex_coord if target_hex_coord is not None else unit.in_hex

        system = galaxy.systems.get(sys_name) if galaxy else None
        hex_obj = system.hexes.get(hex_coord) if system else None

        revealed_count = 0
        if hex_obj:
            for mf in getattr(hex_obj, 'minefields', []):
                if mf.owner != unit.owner:
                    if distance(unit.position, mf.position) <= self.DEFINITION.range:
                        mf.reveal_to(unit.owner)
                        revealed_count += 1
                        logger.debug(f"[{unit.name}] Scan for Minefields revealed {mf.name} at {mf.position}.")

        logger.debug(f"[{unit.name}] Scan for Minefields executed. {revealed_count} enemy minefield(s) revealed.")

        game = getattr(unit, 'game', None)
        if game:
            if hasattr(game, 'visibility_dirty'):
                game.visibility_dirty = True
            if hasattr(game, 'sidebar_needs_update'):
                game.sidebar_needs_update = True

        return True
