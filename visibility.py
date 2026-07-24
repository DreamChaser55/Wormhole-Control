import dataclasses
import typing
from typing import Set, Tuple, Dict, List, Optional, TYPE_CHECKING
from utils import HexCoord
from geometry import distance
from hexgrid_utils import hexes_within_range

if TYPE_CHECKING:
    from galaxy import Galaxy
    from entities import Player, Unit

@dataclasses.dataclass
class VisibilitySnapshot:
    viewer: 'Player'
    visible_enemy_unit_ids: Set[int] = dataclasses.field(default_factory=set)
    presence_hexes: Set[Tuple[str, HexCoord]] = dataclasses.field(default_factory=set)


class VisibilityService:
    """Computes visibility (DETAILED vs PRESENCE vs HIDDEN) for all enemy units from a viewer's perspective."""

    @staticmethod
    def compute(galaxy: 'Galaxy', viewer: Optional['Player']) -> VisibilitySnapshot:
        if not viewer or not galaxy:
            return VisibilitySnapshot(viewer=viewer)

        snapshot = VisibilitySnapshot(viewer=viewer)

        # short_range_by_hex: (system_name, hex_coord) -> list of (position, radius)
        short_range_by_hex: Dict[Tuple[str, HexCoord], List[Tuple[Any, float]]] = {}
        # long_range_covered: set of (system_name, hex_coord)
        long_range_covered: Set[Tuple[str, HexCoord]] = set()

        all_units: List['Unit'] = []
        for system_name, system in galaxy.systems.items():
            for hex_coord, hex_obj in system.hexes.items():
                for unit in hex_obj.units:
                    all_units.append(unit)
                    if unit.owner == viewer:
                        sensors = unit.sensors_component
                        if sensors and not sensors.is_destroyed:
                            if sensors.has_short_range:
                                key = (system_name, hex_coord)
                                if key not in short_range_by_hex:
                                    short_range_by_hex[key] = []
                                short_range_by_hex[key].append((unit.position, sensors.short_range_radius))
                            if sensors.has_long_range:
                                covered_hexes = hexes_within_range(hex_coord, sensors.long_range_hexes)
                                for h in covered_hexes:
                                    if h in system.hexes:
                                        long_range_covered.add((system_name, h))

        # Evaluate enemy units
        for unit in all_units:
            if unit.owner != viewer:
                unit_key = (unit.in_system, unit.in_hex)
                is_detailed = False
                if unit_key in short_range_by_hex:
                    for pos, radius in short_range_by_hex[unit_key]:
                        if distance(pos, unit.position) <= radius:
                            is_detailed = True
                            break
                if is_detailed:
                    snapshot.visible_enemy_unit_ids.add(unit.id)
                elif unit_key in long_range_covered:
                    snapshot.presence_hexes.add(unit_key)

        return snapshot


def is_unit_visible(snapshot: Optional[VisibilitySnapshot], unit: 'Unit') -> bool:
    """Return True if friendly unit or DETAILED enemy unit."""
    if snapshot is None:
        return True
    if unit.owner == snapshot.viewer:
        return True
    return unit.id in snapshot.visible_enemy_unit_ids


def hex_has_presence(snapshot: Optional[VisibilitySnapshot], system_name: str, hex_coord: HexCoord) -> bool:
    """Return True if hex contains undetailed enemy unit presence."""
    if snapshot is None:
        return False
    return (system_name, hex_coord) in snapshot.presence_hexes
