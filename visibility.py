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
    def compute(galaxy: 'Galaxy', viewer: Optional['Player'], turn_number: int = 1) -> VisibilitySnapshot:
        if not viewer or not galaxy:
            return VisibilitySnapshot(viewer=viewer)

        snapshot = VisibilitySnapshot(viewer=viewer)

        # short_range_by_hex: (system_name, hex_coord) -> list of (position, radius)
        short_range_by_hex: Dict[Tuple[str, HexCoord], List[Tuple[typing.Any, float]]] = {}
        # long_range_covered: set of (system_name, hex_coord)
        long_range_covered: Set[Tuple[str, HexCoord]] = set()
        # active_area_cloaks: (system_name, hex_coord, owner) -> list of (position, radius)
        active_area_cloaks: Dict[Tuple[str, HexCoord, typing.Any], List[Tuple[typing.Any, float]]] = {}

        all_units: List['Unit'] = []
        for system_name, system in galaxy.systems.items():
            for hex_coord, hex_obj in system.hexes.items():
                for unit in hex_obj.units:
                    all_units.append(unit)
                    is_friendly = (unit.owner == viewer)
                    is_infiltrated = hasattr(unit, 'has_infiltrating_agent_from') and unit.has_infiltrating_agent_from(viewer)
                    
                    if is_infiltrated:
                        snapshot.visible_enemy_unit_ids.add(unit.id)

                    if is_friendly or is_infiltrated:
                        sensors = getattr(unit, 'sensors_component', None)
                        if sensors and not sensors.is_destroyed:
                            sr_radius = getattr(sensors, 'effective_short_range_radius', sensors.short_range_radius)
                            lr_hexes = getattr(sensors, 'effective_long_range_hexes', sensors.long_range_hexes)
                            if sr_radius > 0:
                                key = (system_name, hex_coord)
                                if key not in short_range_by_hex:
                                    short_range_by_hex[key] = []
                                short_range_by_hex[key].append((unit.position, sr_radius))
                            if lr_hexes > 0:
                                covered_hexes = hexes_within_range(hex_coord, lr_hexes)
                                for h in covered_hexes:
                                    if h in system.hexes:
                                        long_range_covered.add((system_name, h))
                    else:
                        # Index enemy active area cloaking emitters
                        cloaking = getattr(unit, 'cloaking_component', None)
                        if cloaking and cloaking.is_active and not cloaking.is_destroyed:
                            from unit_components.enums import CloakingType
                            if getattr(cloaking, 'device_type', None) == CloakingType.ADVANCED or getattr(cloaking, 'area_radius', 0.0) > 0:
                                cloak_key = (system_name, hex_coord, unit.owner)
                                if cloak_key not in active_area_cloaks:
                                    active_area_cloaks[cloak_key] = []
                                active_area_cloaks[cloak_key].append((unit.position, cloaking.area_radius))

                for body in hex_obj.celestial_bodies:
                    if hasattr(body, 'has_infiltrating_agent_from') and body.has_infiltrating_agent_from(viewer):
                        key = (system_name, hex_coord)
                        if key not in short_range_by_hex:
                            short_range_by_hex[key] = []
                        short_range_by_hex[key].append((body.position, 500.0))
                        long_range_covered.add(key)

        current_turn = turn_number
        if current_turn == 1:
            if hasattr(galaxy, 'turn_number'):
                current_turn = getattr(galaxy, 'turn_number', 1)
            elif hasattr(galaxy, 'game') and hasattr(galaxy.game, 'turn_number'):
                current_turn = getattr(galaxy.game, 'turn_number', 1)

        if hasattr(viewer, 'record_sector_intel'):
            for sys_name, h_coord in long_range_covered:
                viewer.record_sector_intel(sys_name, h_coord, current_turn)

        # Evaluate enemy units
        for unit in all_units:
            if unit.owner != viewer:
                unit_key = (unit.in_system, unit.in_hex)

                # Check if this unit is actively cloaked (defeats long-range sensors only)
                # Either personally cloaked or covered by an active friendly Advanced Cloaking field
                cloaking = getattr(unit, 'cloaking_component', None)
                is_cloaked = (
                    cloaking is not None
                    and cloaking.is_active
                    and not cloaking.is_destroyed
                )
                if not is_cloaked:
                    cloak_key = (unit.in_system, unit.in_hex, unit.owner)
                    if cloak_key in active_area_cloaks:
                        for emitter_pos, radius in active_area_cloaks[cloak_key]:
                            if distance(emitter_pos, unit.position) <= radius:
                                is_cloaked = True
                                break

                is_detailed = False
                if unit_key in short_range_by_hex:
                    for pos, radius in short_range_by_hex[unit_key]:
                        if distance(pos, unit.position) <= radius:
                            is_detailed = True
                            break
                if is_detailed:
                    snapshot.visible_enemy_unit_ids.add(unit.id)
                elif unit_key in long_range_covered and not is_cloaked:
                    snapshot.presence_hexes.add(unit_key)

        return snapshot

    @staticmethod
    def update_all_players_intel(galaxy: 'Galaxy', players: List['Player'], turn_number: int) -> None:
        """Updates sector intel for all players based on their current long-range sensor coverage."""
        if not galaxy or not players:
            return
        for player in players:
            VisibilityService.compute(galaxy, player, turn_number=turn_number)


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


def is_minefield_visible(snapshot: Optional[VisibilitySnapshot], minefield: typing.Any) -> bool:
    """Return True if friendly minefield, spectator mode, or revealed to viewer.
    Unrevealed minefields are invisible to enemy players even if inside sensor range.
    """
    if snapshot is None or snapshot.viewer is None:
        return True
    if minefield.owner == snapshot.viewer:
        return True
    if hasattr(minefield, 'is_revealed_to') and minefield.is_revealed_to(snapshot.viewer):
        return True
    return False

