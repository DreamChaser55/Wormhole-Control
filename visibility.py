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


def _are_allies(p1: Optional[typing.Any], p2: Optional[typing.Any]) -> bool:
    if p1 is None or p2 is None:
        return False
    if p1 is p2:
        return True
    from entities import Player
    if isinstance(p1, Player):
        return p1.is_allied_with(p2)
    if isinstance(p2, Player):
        return p2.is_allied_with(p1)
    p1_id = getattr(p1, 'id', None)
    p2_id = getattr(p2, 'id', None)
    if isinstance(p1_id, (int, str)) and isinstance(p2_id, (int, str)) and p1_id == p2_id:
        return True
    team1 = getattr(p1, 'team_id', None)
    team2 = getattr(p2, 'team_id', None)
    if isinstance(team1, (int, str)) and isinstance(team2, (int, str)):
        return team1 == team2
    return p1 == p2


def _are_enemies(p1: Optional[typing.Any], p2: Optional[typing.Any]) -> bool:
    if p1 is None or p2 is None:
        return False
    from entities import Player
    if isinstance(p1, Player):
        return p1.is_enemy_of(p2)
    if isinstance(p2, Player):
        return p2.is_enemy_of(p1)
    return not _are_allies(p1, p2)


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
        # active_area_cloaks: (system_name, hex_coord) -> list of (emitter_owner, position, radius)
        active_area_cloaks: Dict[Tuple[str, HexCoord], List[Tuple[typing.Any, typing.Any, float]]] = {}

        all_units: List['Unit'] = []
        for system_name, system in galaxy.systems.items():
            for hex_coord, hex_obj in system.hexes.items():
                for unit in hex_obj.units:
                    all_units.append(unit)
                    is_friendly = _are_allies(unit.owner, viewer)
                    
                    is_infiltrated = False
                    if hasattr(unit, 'infiltrating_agents') and isinstance(unit.infiltrating_agents, list):
                        is_infiltrated = any(ag.owner and _are_allies(ag.owner, viewer) for ag in unit.infiltrating_agents)
                    elif hasattr(unit, 'has_infiltrating_agent_from'):
                        is_infiltrated = unit.has_infiltrating_agent_from(viewer)
                    
                    if is_infiltrated and _are_enemies(unit.owner, viewer):
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
                                hex_key = (system_name, hex_coord)
                                if hex_key not in active_area_cloaks:
                                    active_area_cloaks[hex_key] = []
                                active_area_cloaks[hex_key].append((unit.owner, unit.position, cloaking.area_radius))

                for body in hex_obj.celestial_bodies:
                    is_infiltrated_body = False
                    if hasattr(body, 'infiltrating_agents') and isinstance(body.infiltrating_agents, list):
                        is_infiltrated_body = any(ag.owner and _are_allies(ag.owner, viewer) for ag in body.infiltrating_agents)
                    elif hasattr(body, 'has_infiltrating_agent_from'):
                        is_infiltrated_body = body.has_infiltrating_agent_from(viewer)

                    if is_infiltrated_body:
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
            if _are_enemies(unit.owner, viewer):
                unit_key = (unit.in_system, unit.in_hex)

                # Check if this unit is actively cloaked (defeats long-range sensors only)
                # Either personally cloaked or covered by an active friendly/allied Advanced Cloaking field
                cloaking = getattr(unit, 'cloaking_component', None)
                is_cloaked = (
                    cloaking is not None
                    and cloaking.is_active
                    and not cloaking.is_destroyed
                )
                if not is_cloaked:
                    hex_key = (unit.in_system, unit.in_hex)
                    if hex_key in active_area_cloaks:
                        for emitter_owner, emitter_pos, radius in active_area_cloaks[hex_key]:
                            if _are_allies(emitter_owner, unit.owner) and distance(emitter_pos, unit.position) <= radius:
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
    """Return True if friendly unit, ally unit, or DETAILED enemy unit."""
    if snapshot is None or snapshot.viewer is None:
        return True
    if _are_allies(unit.owner, snapshot.viewer):
        return True
    return unit.id in snapshot.visible_enemy_unit_ids


def hex_has_presence(snapshot: Optional[VisibilitySnapshot], system_name: str, hex_coord: HexCoord) -> bool:
    """Return True if hex contains undetailed enemy unit presence."""
    if snapshot is None:
        return False
    return (system_name, hex_coord) in snapshot.presence_hexes


def is_minefield_visible(snapshot: Optional[VisibilitySnapshot], minefield: typing.Any) -> bool:
    """Return True if friendly minefield, allied minefield, spectator mode, or revealed to viewer.
    Unrevealed minefields are invisible to enemy players even if inside sensor range.
    """
    if snapshot is None or snapshot.viewer is None:
        return True
    if _are_allies(minefield.owner, snapshot.viewer):
        return True
    if hasattr(minefield, 'is_revealed_to') and minefield.is_revealed_to(snapshot.viewer):
        return True
    return False

