import logging
from typing import Optional, TYPE_CHECKING
from geometry import Position, is_point_in_circle, clamp_point_to_circle, Circle
from constants import SECTOR_CIRCLE_RADIUS_LOGICAL
from utils import HexCoord
from ..enums import AbilityType
from .base import AbilityDefinition, AbilityInstance

if TYPE_CHECKING:
    from galaxy import Galaxy
    from .component import AbilityComponent

logger = logging.getLogger(__name__)


class MicrojumpAbility(AbilityInstance):
    DEFINITION = AbilityDefinition(
        ability_type=AbilityType.MICROJUMP,
        name="Microjump",
        description="Performs a tactical hyperspace jump to any target position in the same sector.",
        cooldown=5,
        duration=0,
        range=0.0,
        requires_target_unit=False,
        requires_target_position=True,
        antimatter_cost=25,
        required_components=["has_hyperdrive"],
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
        if target_position is None:
            logger.debug(f"[{component.unit.name}] Microjump requires a target position.")
            return False

        unit = component.unit
        sys_name = target_system_name if target_system_name is not None else unit.in_system
        hex_coord = target_hex_coord if target_hex_coord is not None else unit.in_hex

        # Microjump is strictly intra-sector (same system and hex)
        if sys_name != unit.in_system or hex_coord != unit.in_hex:
            logger.debug(f"[{unit.name}] Microjump failed: Target position is in a different sector.")
            gui = getattr(getattr(unit, 'game', None), 'gui', None)
            if gui:
                gui.show_warning_dialog(
                    f"Cannot microjump unit <b>{unit.name}</b>: Target position is in a different sector. Microjumps are restricted to the local sector.",
                    title="Microjump Failed"
                )
            return False

        # Fetch system and hex object for inhibition checks
        system = galaxy.systems.get(sys_name) if galaxy else None
        hex_obj = system.hexes.get(hex_coord) if system else None

        if hex_obj:
            inhibition_zones = hex_obj.get_all_inhibition_zones()
            # 1. Check origin position
            for zone in inhibition_zones:
                if is_point_in_circle(unit.position, zone):
                    logger.debug(f"[{unit.name}] Microjump failed: Origin position is inside an inhibition field.")
                    gui = getattr(getattr(unit, 'game', None), 'gui', None)
                    if gui:
                        gui.show_warning_dialog(
                            f"Cannot microjump unit <b>{unit.name}</b>: Origin position is inside a hyperspace inhibition field.",
                            title="Microjump Failed"
                        )
                    return False

            # 2. Check destination position
            for zone in inhibition_zones:
                if is_point_in_circle(target_position, zone):
                    logger.debug(f"[{unit.name}] Microjump failed: Destination position is inside an inhibition field.")
                    gui = getattr(getattr(unit, 'game', None), 'gui', None)
                    if gui:
                        gui.show_warning_dialog(
                            f"Cannot microjump unit <b>{unit.name}</b>: Destination position is inside a hyperspace inhibition field.",
                            title="Microjump Failed"
                        )
                    return False

        from entities import is_position_blocked_by_celestial_field
        if is_position_blocked_by_celestial_field(galaxy, unit.in_system, unit.in_hex, target_position, unit):
            logger.debug(f"[{unit.name}] Microjump failed: Destination position is inside an impassable dense celestial field.")
            gui = getattr(getattr(unit, 'game', None), 'gui', None)
            if gui:
                gui.show_warning_dialog(
                    f"Cannot microjump unit <b>{unit.name}</b>: Destination is inside an impassable celestial field.",
                    title="Microjump Failed"
                )
            return False

        # Clamp position to sector boundary if needed
        clamped_pos = clamp_point_to_circle(target_position, Circle(Position(0, 0), SECTOR_CIRCLE_RADIUS_LOGICAL))

        # Perform the jump
        unit.position = clamped_pos
        logger.debug(f"[{unit.name}] Microjump executed successfully to position {clamped_pos}.")
        return True
