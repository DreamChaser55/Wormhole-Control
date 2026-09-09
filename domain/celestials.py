"""Celestials domain objects and ownership rules."""
from __future__ import annotations

import typing
from typing import TYPE_CHECKING, Any, Optional

from constants import (
    ASTEROID_FIELD_DENSITY_SPEED_MOD,
    ASTEROID_FIELD_RADIUS,
    ASTEROID_FIELD_SPEED_MOD,
    ASTEROID_RADIUS,
    BASE_HABITAT_CAPACITY,
    BLACK_HOLE_INHIBITION_RADIUS,
    CELESTIAL_FIELD_RADIUS,
    COMET_RADIUS,
    DEBRIS_FIELD_DEFENSE_BONUS,
    DEBRIS_FIELD_DENSITY_DEFENSE_BONUS,
    DEBRIS_FIELD_DENSITY_HAZARD_DAMAGE,
    DEBRIS_FIELD_DENSITY_SPEED_MOD,
    DEBRIS_FIELD_HAZARD_DAMAGE,
    DEBRIS_FIELD_HAZARD_SPEED_THRESHOLD,
    DEBRIS_FIELD_RADIUS,
    DEBRIS_FIELD_SPEED_MOD,
    FIELD_DENSITY_MAX_HULL,
    GIANT_STAR_INHIBITION_RADIUS,
    GIANT_STAR_RADIUS,
    HYDROGEN_NEBULA_HARVEST_MULTIPLIER,
    ICE_FIELD_BEAM_DEFENSE_BONUS,
    ICE_FIELD_COOLDOWN_REDUCTION,
    ICE_FIELD_DENSITY_BEAM_DEFENSE_BONUS,
    ICE_FIELD_DENSITY_SPEED_MOD,
    ICE_FIELD_RADIUS,
    ICE_FIELD_SPEED_MOD,
    MOON_RADIUS,
    NEBULA_RADIUS,
    PLANET_RADIUS,
    PLANET_TRAITS,
    POPULATION_PER_HABITAT,
    STAR_HARVEST_MULTIPLIERS,
    STAR_RADIUS,
    STORM_RADIUS,
    FieldDensity,
    HullSize,
    NebulaType,
    PlanetType,
    StarType,
    StormType,
)
from domain.coordinates import HexCoord
from domain.identity import GameObject
from domain.players import Player
from geometry import Position, distance
from unit_components.enums import SabotageType
from unit_components.intelligence import Agent

if TYPE_CHECKING:
    from domain.units import Unit

import logging

logger = logging.getLogger(__name__)

def _normalize_sabotage_type(sabotage_type: typing.Union[str, SabotageType]) -> SabotageType:
    """Helper to convert a string or SabotageType enum to a SabotageType instance safely."""
    if isinstance(sabotage_type, SabotageType):
        return sabotage_type
    s_val = str(sabotage_type).strip()
    try:
        return SabotageType(s_val.lower())
    except ValueError:
        pass
    try:
        return SabotageType[s_val.upper()]
    except KeyError:
        pass
    return SabotageType(s_val)


class CelestialBody(GameObject):
    """Base class for fixed celestial objects like planets, stars."""
    collision_radius: float = 0.0
    is_solid: bool = True

    @property
    def effect_radius(self) -> float:
        """Returns the logical radius of effect for non-solid bodies or environmental zones."""
        return getattr(self, 'radius', 0.0)

    def __init__(self, position: Position, in_hex: HexCoord, in_system: str, inhibition_field_radius: float = 0.0):
        super().__init__(position, in_hex, in_system)
        self.inhibition_field_radius = inhibition_field_radius
        self.infiltrating_agents: typing.List[Agent] = []

    def has_infiltrating_agent_from(self, player: Optional['Player']) -> bool:
        """Returns True if this celestial body has an active agent belonging to the player."""
        if not player or not hasattr(self, 'infiltrating_agents'):
            return False
        return any(a.owner == player for a in self.infiltrating_agents)

    def get_infiltrating_agents_for_viewer(self, viewer: Optional['Player']) -> typing.List[Agent]:
        """Returns infiltrating agents visible to the viewer."""
        if not viewer or not hasattr(self, 'infiltrating_agents'):
            return []
        return [a for a in self.infiltrating_agents if a.owner == viewer or (a.is_discovered and getattr(self, 'owner', None) == viewer)]

    def is_sabotaged(self, sabotage_type: typing.Union[str, SabotageType]) -> bool:
        """Returns True if this body currently suffers from the specified sabotage."""
        if not hasattr(self, 'infiltrating_agents'):
            return False
        target_type = _normalize_sabotage_type(sabotage_type)
        return any(a.active_sabotage == target_type for a in self.infiltrating_agents)

    def apply_sabotage(self, agent: Agent, sabotage_type: typing.Union[str, SabotageType]) -> bool:
        """Applies a sabotage operation to this celestial body through an attached agent."""
        target_type = _normalize_sabotage_type(sabotage_type)
        if agent in getattr(self, 'infiltrating_agents', []):
            agent.active_sabotage = target_type
            logger.debug(f"Applied sabotage {target_type.name} to {self.name} via Agent {agent.id}.")
            return True
        return False

    def remove_agent(self, agent: Agent) -> bool:
        """Removes an agent from this celestial body."""
        if hasattr(self, 'infiltrating_agents') and agent in self.infiltrating_agents:
            self.infiltrating_agents.remove(agent)
            return True
        return False

    def get_supported_habitat_capacity(self) -> int:
        """Returns the maximum number of civilian habitat modules this body can support based on population."""
        if not getattr(self, 'owner', None) or getattr(self, 'population', 0.0) <= 0:
            return 0
        return max(BASE_HABITAT_CAPACITY, int(self.population // POPULATION_PER_HABITAT))

    def get_supported_orbital_defense_capacity(self) -> int:
        """Returns the maximum number of orbital defense modules this body can support based on population."""
        if not getattr(self, 'owner', None) or getattr(self, 'population', 0.0) <= 0:
            return 0
        from constants import (
            BASE_ORBITAL_DEFENSE_CAPACITY,
            POPULATION_PER_ORBITAL_DEFENSE,
        )
        return max(BASE_ORBITAL_DEFENSE_CAPACITY, int(self.population // POPULATION_PER_ORBITAL_DEFENSE))


class Wormhole(CelestialBody):
    """Represents a wormhole connecting two systems."""
    def __init__(self, in_hex: HexCoord, in_system: str, exit_system_name: str, stability: int = 100, diameter: HullSize = HullSize.HUGE):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=1875.0)
        self.exit_system_name = exit_system_name
        self.exit_wormhole_id: typing.Optional[int] = None
        self.stability = stability
        self.diameter = diameter
        self.name = f"Wormhole {self.id}"


class Star(CelestialBody):
    """Represents the central star of a system."""
    collision_radius: float = STAR_RADIUS
    def __init__(self, in_system: str, star_type: StarType):
        inhibition_radius = 3375.0
        coll_radius = STAR_RADIUS
        if star_type == StarType.BLACK_HOLE:
            inhibition_radius = BLACK_HOLE_INHIBITION_RADIUS
        elif star_type in (StarType.BLUE_GIANT, StarType.RED_GIANT):
            inhibition_radius = GIANT_STAR_INHIBITION_RADIUS
            coll_radius = GIANT_STAR_RADIUS
        super().__init__(position=Position(0.0, 0.0), in_hex=(0, 0), in_system=in_system, inhibition_field_radius=inhibition_radius)
        self.collision_radius = coll_radius
        self.star_type = star_type
        self.name = f"Star {self.id}"

    @property
    def harvest_multiplier(self) -> float:
        """Returns the antimatter harvest rate multiplier based on star type."""
        return STAR_HARVEST_MULTIPLIERS.get(self.star_type, 1.0)


class Planet(CelestialBody):
    """Represents a planet within a system."""
    collision_radius: float = PLANET_RADIUS
    def __init__(self, in_hex: HexCoord, in_system: str, planet_type: Optional[PlanetType] = None):
        if not isinstance(planet_type, PlanetType):
            pos = planet_type if isinstance(planet_type, Position) else Position(0.0, 0.0)
            actual_type = PlanetType.TERRAN
        else:
            pos = Position(0.0, 0.0)
            actual_type = planet_type
        traits = PLANET_TRAITS.get(actual_type, PLANET_TRAITS[PlanetType.TERRAN])
        inhibition_radius = traits.get("inhibition_radius", 3000.0)
        super().__init__(position=pos, in_hex=in_hex, in_system=in_system, inhibition_field_radius=inhibition_radius)
        self.name = f"Planet {self.id}"
        self.owner: Optional[Player] = None
        self.planet_type = actual_type
        self.is_colonizable: bool = traits.get("is_colonizable", True)
        self.population: float = 0
        self.max_population: float = traits.get("max_population", 100.0)
        self.population_growth_rate: float = traits.get("growth_rate", 0.02)
        self.growth_rate: float = self.population_growth_rate
        self.passive_metal: float = traits.get("passive_metal", 0.0)
        self.passive_crystal: float = traits.get("passive_crystal", 0.0)
        self.harvest_multiplier: float = traits.get("am_harvest_multiplier", 0.0)
        self.collision_radius: float = traits.get("collision_radius", PLANET_RADIUS)
        self.hidden_units: typing.List['Unit'] = []

    def can_hide_unit(self, unit: 'Unit') -> bool:
        """Returns True if this planet is a gas giant and the unit can enter its atmosphere."""
        if self.planet_type != PlanetType.GAS_GIANT:
            return False
        if getattr(unit, 'hull_size', None) == HullSize.STRIKECRAFT_WING:
            return False
        eng = getattr(unit, 'engines_component', None)
        if not eng or not getattr(eng, 'is_operational', False):
            return False
        return True

    def hide_unit(self, unit: 'Unit', galaxy_ref: typing.Any = None) -> bool:
        """Hides the unit in the gas giant's atmosphere, removing it from normal sector presence."""
        if not self.can_hide_unit(unit):
            return False
        if unit in self.hidden_units:
            return True

        g = galaxy_ref or getattr(unit, 'in_galaxy', None) or (getattr(unit.game, 'galaxy', None) if getattr(unit, 'game', None) else None)
        if g and unit.in_system:
            sys_obj = g.systems.get(unit.in_system)
            if sys_obj:
                sys_obj.remove_unit(unit)

        # Deactivate any active external fields or targets
        if getattr(unit, 'inhibitor_component', None) and unit.inhibitor_component.is_active:
            if hasattr(unit.inhibitor_component, 'turn_off'):
                unit.inhibitor_component.turn_off()
            else:
                unit.inhibitor_component.is_active = False
        if getattr(unit, 'cloaking_component', None) and unit.cloaking_component.is_active:
            if hasattr(unit.cloaking_component, 'deactivate'):
                unit.cloaking_component.deactivate()
            else:
                unit.cloaking_component.is_active = False
        if getattr(unit, 'weapons_component', None):
            unit.weapons_component.clear_target()

        unit.in_system = self.in_system
        unit.in_hex = self.in_hex
        unit.position = Position(self.position.x, self.position.y)
        unit.is_hidden_in_gas_giant = True
        unit.hidden_in_gas_giant_id = self.id

        if getattr(unit, 'commander_component', None):
            unit.commander_component.suspend_stance_activity("hidden_in_gas_giant")
        if unit.engines_component:
            unit.engines_component.clear_move_target()
        if unit.hyperdrive_component:
            unit.hyperdrive_component.clear_jump_target()

        self.hidden_units.append(unit)
        logger.debug(f"Unit '{unit.name}' (id:{unit.id}) hidden in gas giant atmosphere '{self.name}' (id:{self.id}).")
        return True

    def release_unit(self, unit: 'Unit', galaxy_ref: typing.Any = None) -> typing.Optional[Position]:
        """Commit a safe departure and return its logical position, or return None.

        Nonmembers and blocked exits leave membership and ship state unchanged.
        A successful placement becomes occupied immediately; subsequent departures
        cannot reuse it. The Leave order owns completion and queue advancement.
        """
        if unit not in self.hidden_units:
            return None

        import math
        import random

        from constants import SECTOR_CIRCLE_RADIUS_LOGICAL
        from geometry import GEOMETRY_TOLERANCE, NAVIGATION_CLEARANCE
        from unit_orders.movement import get_hex_collision_obstacles

        standoff_dist = float(self.collision_radius) + NAVIGATION_CLEARANCE
        g = galaxy_ref or getattr(unit, 'in_galaxy', None) or getattr(getattr(unit, 'game', None), 'galaxy', None)
        sys_obj = g.systems.get(self.in_system) if g else None
        hex_obj = sys_obj.hexes.get(self.in_hex) if sys_obj else None
        if hex_obj is None:
            return None
        obstacles = get_hex_collision_obstacles(g, self.in_system, self.in_hex, unit=unit)

        def safe(candidate):
            if candidate.magnitude() > SECTOR_CIRCLE_RADIUS_LOGICAL - 20.0:
                return False
            if any(distance(candidate, obs.center) < obs.radius + NAVIGATION_CLEARANCE - GEOMETRY_TOLERANCE for obs in obstacles):
                return False
            return all(distance(candidate, other.position) >= NAVIGATION_CLEARANCE
                       for other in hex_obj.units if other is not unit and other.current_hit_points > 0)

        emerge_pos = None
        # Every candidate, including the deterministic fallback, uses the same checks.
        import itertools
        angles = itertools.chain((random.uniform(0.0, 2.0 * math.pi) for _ in range(64)),
                                 (math.radians(degrees) for degrees in range(360)))
        for angle in angles:
            candidate = self.position + Position(math.cos(angle), math.sin(angle)) * standoff_dist
            if safe(candidate):
                emerge_pos = candidate
                break
        if emerge_pos is None:
            return None

        self.hidden_units.remove(unit)
        unit.position = emerge_pos
        unit.in_system = self.in_system
        unit.in_hex = self.in_hex
        unit.is_hidden_in_gas_giant = False
        unit.hidden_in_gas_giant_id = None

        if sys_obj:
            sys_obj.add_unit(unit)

        if unit.engines_component:
            unit.engines_component.clear_move_target()
        if unit.hyperdrive_component:
            unit.hyperdrive_component.clear_jump_target()

        logger.debug(f"Unit '{unit.name}' (id:{unit.id}) emerged from gas giant '{self.name}' at {emerge_pos}.")
        return emerge_pos

    def update_population(self):
        if self.owner and self.is_colonizable:
            self.population = max(0, min(self.population, self.max_population))
        if not self.is_colonizable or self.is_sabotaged(SabotageType.GROWTH):
            return
        if self.owner and self.population < self.max_population:
            self.population += self.population * self.population_growth_rate
            if self.population > self.max_population:
                self.population = self.max_population


class Moon(CelestialBody):
    """Represents a moon, which is colonisable."""
    collision_radius: float = MOON_RADIUS
    def __init__(self, in_hex: HexCoord, in_system: str):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=2250.0)
        self.name = f"Moon {self.id}"
        self.owner: Optional[Player] = None
        self.is_colonizable: bool = True
        self.population: float = 0
        self.max_population: float = 50.0
        self.population_growth_rate: float = 0.01

    def update_population(self):
        if self.is_sabotaged(SabotageType.GROWTH):
            return
        if self.owner and self.population < self.max_population:
            self.population += self.population * self.population_growth_rate
            if self.population > self.max_population:
                self.population = self.max_population


class ColonizableAsteroid(CelestialBody):
    """Represents a colonisable asteroid with population growth."""
    collision_radius: float = ASTEROID_RADIUS
    def __init__(self, in_hex: HexCoord, in_system: str):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=1500.0)
        self.name = f"Colonizable Asteroid {self.id}"
        self.owner: Optional[Player] = None
        self.is_colonizable: bool = True
        self.population: float = 0
        self.max_population: float = 20.0
        self.population_growth_rate: float = 0.005

    def update_population(self):
        if self.is_sabotaged(SabotageType.GROWTH):
            return
        if self.owner and self.population < self.max_population:
            self.population += self.population * self.population_growth_rate
            if self.population > self.max_population:
                self.population = self.max_population


class MetalAsteroid(CelestialBody):
    """Represents a metal asteroid, which is a source of Metal."""
    collision_radius: float = ASTEROID_RADIUS
    def __init__(self, in_hex: HexCoord, in_system: str):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=1500.0)
        self.name = f"Metal Asteroid {self.id}"
        self.metal_yield: float = 10.0


class DebrisField(CelestialBody):
    """Represents a field of debris providing physical cover and high-speed navigation hazard."""
    radius: float = DEBRIS_FIELD_RADIUS
    is_solid: bool = False
    def __init__(self, in_hex: HexCoord, in_system: str, density: FieldDensity = FieldDensity.MEDIUM):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=0.0)
        self.name = f"Debris Field {self.id}"
        self.radius = DEBRIS_FIELD_RADIUS
        self.density = density
        self.speed_multiplier = DEBRIS_FIELD_DENSITY_SPEED_MOD.get(density, DEBRIS_FIELD_SPEED_MOD)
        self.defense_bonus = DEBRIS_FIELD_DENSITY_DEFENSE_BONUS.get(density, DEBRIS_FIELD_DEFENSE_BONUS)
        self.hazard_speed_threshold = DEBRIS_FIELD_HAZARD_SPEED_THRESHOLD
        self.hazard_damage = DEBRIS_FIELD_DENSITY_HAZARD_DAMAGE.get(density, DEBRIS_FIELD_HAZARD_DAMAGE)

    @property
    def max_hull_size(self) -> HullSize:
        return FIELD_DENSITY_MAX_HULL.get(self.density, HullSize.MEDIUM)

    def can_unit_enter(self, unit_or_hull: Any) -> bool:
        hull = getattr(unit_or_hull, 'hull_size', unit_or_hull)
        val = getattr(hull, 'value', 0)
        return val <= self.max_hull_size.value


class AsteroidField(CelestialBody):
    """Represents a field of asteroids providing long-range radar scattering and sublight drag."""
    radius: float = ASTEROID_FIELD_RADIUS
    is_solid: bool = False
    def __init__(self, in_hex: HexCoord, in_system: str, density: FieldDensity = FieldDensity.MEDIUM):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=0.0)
        self.name = f"Asteroid Field {self.id}"
        self.density = density
        self.asteroid_count = 200 if density == FieldDensity.LOW else (350 if density == FieldDensity.MEDIUM else 550)
        self.radius = ASTEROID_FIELD_RADIUS
        self.speed_multiplier = ASTEROID_FIELD_DENSITY_SPEED_MOD.get(density, ASTEROID_FIELD_SPEED_MOD)

    @property
    def max_hull_size(self) -> HullSize:
        return FIELD_DENSITY_MAX_HULL.get(self.density, HullSize.MEDIUM)

    def can_unit_enter(self, unit_or_hull: Any) -> bool:
        hull = getattr(unit_or_hull, 'hull_size', unit_or_hull)
        val = getattr(hull, 'value', 0)
        return val <= self.max_hull_size.value


class IceField(CelestialBody):
    """Represents a field of ice particles providing beam defense cover, weapon cooling, and navigation drag."""
    radius: float = ICE_FIELD_RADIUS
    is_solid: bool = False
    def __init__(self, in_hex: HexCoord, in_system: str, density: FieldDensity = FieldDensity.MEDIUM):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=0.0)
        self.name = f"Ice Field {self.id}"
        self.density = density
        self.radius = ICE_FIELD_RADIUS
        self.speed_multiplier = ICE_FIELD_DENSITY_SPEED_MOD.get(density, ICE_FIELD_SPEED_MOD)
        self.beam_defense_bonus = ICE_FIELD_DENSITY_BEAM_DEFENSE_BONUS.get(density, ICE_FIELD_BEAM_DEFENSE_BONUS)
        self.cooldown_reduction = ICE_FIELD_COOLDOWN_REDUCTION

    @property
    def max_hull_size(self) -> HullSize:
        return FIELD_DENSITY_MAX_HULL.get(self.density, HullSize.MEDIUM)

    def can_unit_enter(self, unit_or_hull: Any) -> bool:
        hull = getattr(unit_or_hull, 'hull_size', unit_or_hull)
        val = getattr(hull, 'value', 0)
        return val <= self.max_hull_size.value


class Nebula(CelestialBody):
    """Represents a nebula."""
    radius: float = NEBULA_RADIUS
    is_solid: bool = False
    def __init__(self, in_hex: HexCoord, in_system: str, nebula_type: NebulaType):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=0.0)
        self.name = f"Nebula {self.id}"
        self.nebula_type = nebula_type
        self.radius = NEBULA_RADIUS

    @property
    def harvest_multiplier(self) -> float:
        """Returns antimatter harvesting multiplier (0.4x for Hydrogen, 0.0 otherwise)."""
        if getattr(self, 'nebula_type', None) == NebulaType.HYDROGEN:
            return HYDROGEN_NEBULA_HARVEST_MULTIPLIER
        return 0.0


class Storm(CelestialBody):
    """Represents an energetic space storm hazard."""
    radius: float = STORM_RADIUS
    is_solid: bool = False
    def __init__(self, in_hex: HexCoord, in_system: str, storm_type: StormType):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=0.0)
        self.name = f"Storm {self.id}"
        self.storm_type = storm_type
        self.radius = STORM_RADIUS


class Comet(CelestialBody):
    """Represents a comet, which is a source of Crystal."""
    collision_radius: float = COMET_RADIUS
    def __init__(self, in_hex: HexCoord, in_system: str):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=1000.0)
        self.name = f"Comet {self.id}"
        self.crystal_yield: float = 10.0


NON_SOLID_CELESTIAL_BODIES = (AsteroidField, IceField, DebrisField, Nebula, Storm)


def is_position_in_magnetic_storm(
    galaxy_ref: Any,
    system_name: Optional[str],
    hex_coord: Optional[HexCoord],
    position: Optional[Position]
) -> bool:
    """Returns True if the given position in system_name and hex_coord is inside a Magnetic Storm."""
    if not galaxy_ref or not system_name or hex_coord is None or position is None:
        return False
    systems = getattr(galaxy_ref, "systems", None)
    if not isinstance(systems, dict):
        return False
    system = systems.get(system_name)
    if not system:
        return False
    hexes = getattr(system, "hexes", None)
    if not isinstance(hexes, dict):
        return False
    hex_obj = hexes.get(hex_coord)
    if not hex_obj:
        return False
    for body in getattr(hex_obj, "celestial_bodies", []):
        if isinstance(body, Storm) and getattr(body, "storm_type", None) == StormType.MAGNETIC:
            radius = getattr(body, "radius", STORM_RADIUS)
            if distance(position, body.position) <= radius:
                return True
    return False


def is_position_blocked_by_celestial_field(
    galaxy_ref: Any,
    system_name: Optional[str],
    hex_coord: Optional[HexCoord],
    position: Optional[Position],
    unit_or_hull: Any
) -> bool:
    """Returns True if position in system_name and hex_coord is within a celestial field that forbids unit_or_hull."""
    if not galaxy_ref or not system_name or hex_coord is None or position is None or unit_or_hull is None:
        return False
    hull = getattr(unit_or_hull, 'hull_size', unit_or_hull)
    if not hasattr(hull, 'value'):
        return False
    systems = getattr(galaxy_ref, "systems", None)
    if not isinstance(systems, dict):
        return False
    system = systems.get(system_name)
    if not system:
        return False
    hexes = getattr(system, "hexes", None)
    if not isinstance(hexes, dict):
        return False
    hex_obj = hexes.get(hex_coord)
    if not hex_obj:
        return False
    for body in getattr(hex_obj, "celestial_bodies", []):
        if isinstance(body, (AsteroidField, DebrisField, IceField)):
            if hasattr(body, 'can_unit_enter') and not body.can_unit_enter(hull):
                radius = getattr(body, "radius", CELESTIAL_FIELD_RADIUS)
                if distance(position, body.position) <= radius:
                    return True
    return False
