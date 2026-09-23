import dataclasses
import typing
from typing import Set, Tuple, Dict, List, Optional, TYPE_CHECKING
from domain.coordinates import HexCoord
from domain.players import are_allies, are_enemies
from geometry import distance
from hexgrid_utils import hexes_within_range
from constants import (
    NEBULA_RADIUS, CELESTIAL_FIELD_RADIUS
)

if TYPE_CHECKING:
    from galaxy import Galaxy
    from domain.players import Player
    from domain.units import Unit

@dataclasses.dataclass
class VisibilitySnapshot:
    viewer: 'Player'
    visible_enemy_unit_ids: Set[int] = dataclasses.field(default_factory=set)
    presence_hexes: Set[Tuple[str, HexCoord]] = dataclasses.field(default_factory=set)
    visible_deployable_ids: Set[int] = dataclasses.field(default_factory=set)
    visible_patch_ids: Set[int] = dataclasses.field(default_factory=set)


class VisibilityService:
    """Computes visibility (DETAILED vs PRESENCE vs HIDDEN) for all enemy units from a viewer's perspective."""

    @staticmethod
    def compute(galaxy: 'Galaxy', viewer: Optional['Player'], turn_number: int = 1, *, record_intel: bool = True) -> VisibilitySnapshot:
        if not viewer or not galaxy:
            return VisibilitySnapshot(viewer=viewer)

        snapshot = VisibilitySnapshot(viewer=viewer)

        # short_range_by_hex: (system_name, hex_coord) -> list of (position, radius)
        short_range_by_hex: Dict[Tuple[str, HexCoord], List[Tuple[typing.Any, float]]] = {}
        # long_range_covered: set of (system_name, hex_coord)
        long_range_covered: Set[Tuple[str, HexCoord]] = set()
        # active_area_cloaks: (system_name, hex_coord) -> list of (emitter_owner, position, radius)
        active_area_cloaks: Dict[Tuple[str, HexCoord], List[Tuple[typing.Any, typing.Any, float]]] = {}
        # nebulae_by_hex: (system_name, hex_coord) -> list of (position, radius)
        nebulae_by_hex: Dict[Tuple[str, HexCoord], List[Tuple[typing.Any, float]]] = {}

        all_units: List['Unit'] = []
        for system_name, system in galaxy.systems.items():
            for hex_coord, hex_obj in system.hexes.items():
                for unit in hex_obj.units:
                    all_units.append(unit)
                    is_friendly = are_allies(unit.owner, viewer)
                    
                    is_infiltrated = False
                    if hasattr(unit, 'infiltrating_agents') and isinstance(unit.infiltrating_agents, list):
                        is_infiltrated = any(ag.owner and are_allies(ag.owner, viewer) for ag in unit.infiltrating_agents)
                    elif hasattr(unit, 'has_infiltrating_agent_from'):
                        is_infiltrated = unit.has_infiltrating_agent_from(viewer)
                    
                    if is_infiltrated and are_enemies(unit.owner, viewer):
                        snapshot.visible_enemy_unit_ids.add(unit.id)

                    if is_friendly or is_infiltrated:
                        sensors = getattr(unit, 'sensors_component', None)
                        from dismantling import offline
                        if sensors and not sensors.is_destroyed and not offline(unit):
                            from environmental_effects import sensor_radius
                            sr_radius = sensor_radius(unit)
                            from environmental_effects import long_range_sensor_hexes
                            lr_hexes = long_range_sensor_hexes(unit)

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
                    from environmental_effects import describe_body
                    description = describe_body(body)
                    if dict(description.effects).get('long_range_concealment', False):
                        hex_key = (system_name, hex_coord)
                        if hex_key not in nebulae_by_hex:
                            nebulae_by_hex[hex_key] = []
                        field_radius = description.effect_radius
                        nebulae_by_hex[hex_key].append((body.position, field_radius))

                    is_infiltrated_body = False
                    if hasattr(body, 'infiltrating_agents') and isinstance(body.infiltrating_agents, list):
                        is_infiltrated_body = any(ag.owner and are_allies(ag.owner, viewer) for ag in body.infiltrating_agents)
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

        if record_intel and hasattr(viewer, 'record_sector_intel'):
            for sys_name, h_coord in long_range_covered:
                viewer.record_sector_intel(sys_name, h_coord, current_turn)

        # Evaluate enemy units
        for unit in all_units:
            if are_enemies(unit.owner, viewer):
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
                            if are_allies(emitter_owner, unit.owner) and distance(emitter_pos, unit.position) <= radius:
                                is_cloaked = True
                                break

                # Check if this unit is inside a nebula (defeats long-range sensors only)
                is_in_nebula = False
                if unit_key in nebulae_by_hex:
                    for neb_pos, neb_rad in nebulae_by_hex[unit_key]:
                        if distance(neb_pos, unit.position) <= neb_rad:
                            is_in_nebula = True
                            break

                is_detailed = False
                if unit_key in short_range_by_hex:
                    for pos, radius in short_range_by_hex[unit_key]:
                        if distance(pos, unit.position) <= radius:
                            is_detailed = True
                            break
                if is_detailed:
                    snapshot.visible_enemy_unit_ids.add(unit.id)
                elif unit_key in long_range_covered and not is_cloaked and not is_in_nebula:
                    snapshot.presence_hexes.add(unit_key)

        for system in galaxy.systems.values():
            for sector in system.hexes.values():
                for patch in getattr(sector, 'catalyst_patches', ()):
                    key = (patch.in_system, patch.in_hex)
                    if are_allies(patch.owner, viewer) or any(distance(patch.position, p) <= r + patch.radius for p, r in short_range_by_hex.get(key, ())):
                        snapshot.visible_patch_ids.add(patch.id)
                for obj in getattr(sector, 'deployables', ()):
                    key = (obj.in_system, obj.in_hex)
                    if are_allies(obj.owner, viewer):
                        snapshot.visible_deployable_ids.add(obj.id)
                        continue
                    detailed = any(distance(obj.position, p) <= r for p, r in short_range_by_hex.get(key, ()))
                    identified = viewer.id in obj.identified_player_ids
                    if detailed:
                        snapshot.visible_deployable_ids.add(obj.id)
                        if obj.kind == 'ghost_fleet' and record_intel:
                            players = getattr(getattr(galaxy, 'game', None), 'players', [viewer])
                            obj.identified_player_ids.update(p.id for p in players if are_allies(p, viewer))
                        identified = True
                    concealed = any(distance(obj.position, p) <= r for p, r in nebulae_by_hex.get(key, ()))
                    concealed = concealed or any(are_allies(owner, obj.owner) and distance(obj.position, p) <= r
                        for owner, p, r in active_area_cloaks.get(key, ()))
                    if obj.kind == 'ghost_fleet' and not identified and not concealed and key in long_range_covered:
                        snapshot.presence_hexes.add(key)
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
    if are_allies(unit.owner, snapshot.viewer):
        return True
    if getattr(unit, 'is_hidden_in_gas_giant', False):
        return False
    from domain.deployables import Deployable
    if isinstance(unit, Deployable):
        return unit.id in snapshot.visible_deployable_ids
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
    if are_allies(minefield.owner, snapshot.viewer):
        return True
    if hasattr(minefield, 'is_revealed_to') and minefield.is_revealed_to(snapshot.viewer):
        return True
    return False


def is_unit_in_nebula(unit: Optional['Unit'], galaxy: Optional['Galaxy'] = None) -> bool:
    """Return True if the unit is currently located within a nebula cloud."""
    if unit is None or not unit.in_system or unit.in_hex is None:
        return False
    if galaxy is None and hasattr(unit, 'game') and unit.game and hasattr(unit.game, 'galaxy'):
        galaxy = unit.game.galaxy
    if galaxy is None:
        return False
    system = galaxy.systems.get(unit.in_system)
    if not system:
        return False
    hex_obj = system.hexes.get(unit.in_hex)
    if not hex_obj:
        return False
    from domain.celestials import Nebula
    for body in hex_obj.celestial_bodies:
        if isinstance(body, Nebula):
            neb_radius = getattr(body, 'radius', NEBULA_RADIUS)
            if distance(body.position, unit.position) <= neb_radius:
                return True
    return False


def is_unit_in_asteroid_field(unit: Optional['Unit'], galaxy: Optional['Galaxy'] = None) -> bool:
    """Return True if the unit is currently located within an asteroid field (radar scattering)."""
    if unit is None or not unit.in_system or unit.in_hex is None:
        return False
    if galaxy is None and hasattr(unit, 'game') and unit.game and hasattr(unit.game, 'galaxy'):
        galaxy = unit.game.galaxy
    if galaxy is None:
        return False
    system = galaxy.systems.get(unit.in_system)
    if not system:
        return False
    hex_obj = system.hexes.get(unit.in_hex)
    if not hex_obj:
        return False
    from domain.celestials import AsteroidField
    for body in hex_obj.celestial_bodies:
        if isinstance(body, AsteroidField):
            field_radius = getattr(body, 'radius', CELESTIAL_FIELD_RADIUS)
            if distance(body.position, unit.position) <= field_radius:
                return True
    return False

