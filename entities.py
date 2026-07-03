import logging

logger = logging.getLogger(__name__)

import typing
from typing import Dict, Optional, Any, TYPE_CHECKING
from utils import HexCoord
from geometry import Position, distance, Vector
from constants import WHITE, YELLOW, GREEN, PURPLE, HULL_CAPACITIES, HullSize, HIT_POINTS, StarType, PlanetType, NebulaType, StormType, NEBULA_COLORS, STORM_COLORS
import uuid
import dataclasses
from enum import Enum, auto
from collections import deque
from unit_orders import (
    Order, OrderStatus, OrderType,
    MoveOrder, ReachWaypointOrder, AttackOrder, ColonizeOrder,
    LoadColonistsOrder, ConstructOrder, ToggleInhibitorOrder, PatrolOrder,
    RepairOrder, MineOrder, UnloadResourcesOrder, DockOrder, DeployUnitOrder,
    UseAbilityOrder
)
from unit_components import (
    UnitComponent,
    Engines,
    Hyperdrive, HyperdriveType,
    Commander,
    HyperspaceInhibitionFieldEmitter,
    Weapons,
    Defenses,
    TurretType,
    ColonyComponent,
    Constructor,
    RepairComponent,
    MiningComponent,
    MetalRefineryComponent,
    CrystalRefineryComponent,
    HangarComponent,
    AbilityComponent,
    AbilityType,
    StrikecraftBayComponent,
    StrikecraftWingComponent,
)
if TYPE_CHECKING:
    from galaxy import Galaxy
    from game import Game

# --- Player Class ---
class Player:
    """Represents a player in the game (human or AI)."""
    player_counter = 0

    def __init__(self, name: str, color: tuple, is_human: bool = True):
        self.id = Player.player_counter
        Player.player_counter += 1
        self.name = name if name else f"Player {self.id}"
        self.color = color
        self.is_human = is_human
        self.credits = 20000
        self.metal = 10000
        self.crystal = 10000

    def __repr__(self):
        return f"Player({self.name}, ID:{self.id}, Color:{self.color})"

# --- Game Object Base Class ---
class GameObject:
    """Base class for all objects that can exist in a sector."""
    object_counter = 0

    def __init__(self, position: Position, in_hex: HexCoord, in_system: str):
        self.id = GameObject.object_counter
        GameObject.object_counter += 1
        self.position = position
        self.in_hex = in_hex
        self.in_system = in_system

    def __repr__(self):
        return f"{self.__class__.__name__}(ID:{self.id}, Pos:{self.position}, Hex:{self.in_hex}, System:{self.in_system})"

# --- GameObject-derived Class: CelestialBody ---

class CelestialBody(GameObject):
    """Base class for fixed celestial objects like planets, stars."""
    def __init__(self, position: Position, in_hex: HexCoord, in_system: str, inhibition_field_radius: float = 0.0):
        super().__init__(position, in_hex, in_system)
        self.inhibition_field_radius = inhibition_field_radius

# --- CelestialBody-derived Classes ---

class Wormhole(CelestialBody):
    """Represents a wormhole connecting two systems."""
    def __init__(self, in_hex: HexCoord, in_system: str, exit_system_name: str, stability: int = 100, diameter: HullSize = HullSize.HUGE):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=500.0)
        self.exit_system_name = exit_system_name
        self.exit_wormhole_id: typing.Optional[int] = None
        self.stability = stability
        self.diameter = diameter
        self.name = f"Wormhole {self.id}"

class Star(CelestialBody):
    """Represents the central star of a system."""
    def __init__(self, in_system: str, star_type: StarType):
        super().__init__(position=Position(0.0, 0.0), in_hex=(0, 0), in_system=in_system, inhibition_field_radius=900.0)
        self.star_type = star_type
        self.name = f"Star {self.id}"

class Planet(CelestialBody):
    """Represents a planet within a system."""
    def __init__(self, in_hex: HexCoord, in_system: str, planet_type: PlanetType):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=800.0)
        self.name = f"Planet {self.id}"
        self.owner: Optional[Player] = None
        self.population: float = 0
        self.max_population: float = 100.0
        self.population_growth_rate: float = 0.02
        self.planet_type = planet_type

    def update_population(self):
        if self.owner and self.population < self.max_population:
            self.population += self.population * self.population_growth_rate
            if self.population > self.max_population:
                self.population = self.max_population


class Moon(CelestialBody):
    """Represents a moon, which is colonisable and a source of Crystal."""
    def __init__(self, in_hex: HexCoord, in_system: str):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=600.0)
        self.name = f"Moon {self.id}"
        self.owner: Optional[Player] = None
        self.population: float = 0
        self.max_population: float = 50.0
        self.population_growth_rate: float = 0.01
        self.crystal_yield: float = 10.0

    def update_population(self):
        if self.owner and self.population < self.max_population:
            self.population += self.population * self.population_growth_rate
            if self.population > self.max_population:
                self.population = self.max_population


class Asteroid(CelestialBody):
    """Represents an asteroid, which is colonisable and a source of Metal."""
    def __init__(self, in_hex: HexCoord, in_system: str):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=400.0)
        self.name = f"Asteroid {self.id}"
        self.owner: Optional[Player] = None
        self.population: float = 0
        self.max_population: float = 20.0
        self.population_growth_rate: float = 0.005
        self.metal_yield: float = 10.0

    def update_population(self):
        if self.owner and self.population < self.max_population:
            self.population += self.population * self.population_growth_rate
            if self.population > self.max_population:
                self.population = self.max_population

class DebrisField(CelestialBody):
    """Represents a field of debris."""
    def __init__(self, in_hex: HexCoord, in_system: str):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system)
        self.name = f"Debris Field {self.id}"

class AsteroidField(CelestialBody):
    """Represents a field of asteroids."""
    def __init__(self, in_hex: HexCoord, in_system: str):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=300.0)
        self.name = f"Asteroid Field {self.id}"
        self.asteroid_count = 100 # Example value

class IceField(CelestialBody):
    """Represents a field of ice particles."""
    def __init__(self, in_hex: HexCoord, in_system: str):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=150.0)
        self.name = f"Ice Field {self.id}"

class Nebula(CelestialBody):
    """Represents a nebula."""
    def __init__(self, in_hex: HexCoord, in_system: str, nebula_type: NebulaType):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=0.0)
        self.name = f"Nebula {self.id}"
        self.nebula_type = nebula_type

class Storm(CelestialBody):
    """Represents a storm."""
    def __init__(self, in_hex: HexCoord, in_system: str, storm_type: StormType):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=0.0)
        self.name = f"Storm {self.id}"
        self.storm_type = storm_type

class Comet(CelestialBody):
    """Represents a comet."""
    def __init__(self, in_hex: HexCoord, in_system: str):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=200.0)
        self.name = f"Comet {self.id}"


# --- GameObject-derived Class: Unit ---

class Unit(GameObject):
    """Represents a generic unit in the game, composed of various components."""
    def __init__(self, owner: Player, position: Position, in_hex: HexCoord, in_system: str, name: str,
                 hull_size: HullSize,
                 game: "Game"):
        super().__init__(position, in_hex, in_system)
        self.owner = owner
        self.name: str = name
        self.game = game
        self.in_galaxy: Optional['Galaxy'] = game.galaxy if game else None

        self.hull_size: HullSize = hull_size
        self.hull_capacity: int = HULL_CAPACITIES[self.hull_size] # consumed by components with hull_cost
        self.current_hull_usage: int = 0

        self.max_hit_points: int = HIT_POINTS[self.hull_size]
        self.current_hit_points: int = self.max_hit_points

        self.components: typing.Dict[type, UnitComponent] = {}

        # --- Status effects applied by abilities ---
        # Damage reduction (0.0 = none, 0.75 = 75% reduction). Stacks additively.
        self.damage_reduction: float = 0.0
        # Extra damage taken multiplier from Designate Target. Stacks additively.
        self.damage_amplification: float = 0.0
        # Ion Bolt disable: unit cannot move or attack while True.
        self.is_disabled: bool = False
        # Set of unit IDs that have applied a disable. Disable lifts when the set is empty.
        self.disabled_by_unit_ids: typing.Set[int] = set()
        # Lifetime in turns (None = permanent). Used by temporary units (Missile Platforms).
        self.lifetime: typing.Optional[int] = None
        # Flag to distinguish spawned temporary units from regular units.
        self.is_temporary: bool = False

        # Every unit has a commander component by default
        self.add_component(Commander(unit=self))

    def add_component(self, component: UnitComponent) -> None:
        self.components[type(component)] = component
        self._update_hull_usage()

    def get_component(self, component_type: type) -> typing.Optional[UnitComponent]:
        return self.components.get(component_type)
        
    def remove_component(self, component_type: type) -> None:
        if component_type in self.components:
            del self.components[component_type]
            self._update_hull_usage()

    @property
    def engines_component(self) -> typing.Optional[Engines]:
        return self.get_component(Engines)

    @property
    def hyperdrive_component(self) -> typing.Optional[Hyperdrive]:
        return self.get_component(Hyperdrive)

    @property
    def inhibitor_component(self) -> typing.Optional[HyperspaceInhibitionFieldEmitter]:
        return self.get_component(HyperspaceInhibitionFieldEmitter)

    @property
    def weapons_component(self) -> typing.Optional[Weapons]:
        return self.get_component(Weapons)

    @property
    def colony_component(self) -> typing.Optional[ColonyComponent]:
        return self.get_component(ColonyComponent)

    @property
    def constructor_component(self) -> typing.Optional[Constructor]:
        return self.get_component(Constructor)

    @property
    def repair_component(self) -> typing.Optional[RepairComponent]:
        return self.get_component(RepairComponent)

    @property
    def mining_component(self) -> typing.Optional[MiningComponent]:
        return self.get_component(MiningComponent)

    @property
    def metal_refinery_component(self) -> typing.Optional[MetalRefineryComponent]:
        return self.get_component(MetalRefineryComponent)

    @property
    def crystal_refinery_component(self) -> typing.Optional[CrystalRefineryComponent]:
        return self.get_component(CrystalRefineryComponent)

    @property
    def hangar_component(self) -> typing.Optional[HangarComponent]:
        return self.get_component(HangarComponent)

    @property
    def strikecraft_bay_component(self) -> typing.Optional[StrikecraftBayComponent]:
        return self.get_component(StrikecraftBayComponent)

    @property
    def strikecraft_wing_component(self) -> typing.Optional[StrikecraftWingComponent]:
        return self.get_component(StrikecraftWingComponent)

    @property
    def ability_component(self) -> typing.Optional[AbilityComponent]:
        return self.get_component(AbilityComponent)

    @property
    def commander_component(self) -> Commander:
        return self.get_component(Commander)

    def take_damage(self, amount: int, damage_type: Optional[TurretType] = None) -> None:
        """Reduces the unit's current hit points by the given amount, applying any active damage reduction and defenses mitigation."""
        if damage_type:
            defenses = self.get_component(Defenses)
            if defenses:
                mitigation = defenses.calculate_mitigation(amount, damage_type)
                amount = max(0, amount - mitigation)
                logger.debug(f"Unit '{self.name}' defenses mitigated {mitigation} damage. Remaining damage: {amount}")

        if self.damage_reduction > 0.0:
            amount = max(1, int(amount * (1.0 - self.damage_reduction)))
        self.current_hit_points -= amount
        if self.current_hit_points < 0:
            self.current_hit_points = 0
        logger.debug(f"Unit '{self.name}' takes {amount} damage. Current HP: {self.current_hit_points}/{self.max_hit_points}")

        if self.current_hit_points == 0:
            self.destroy()

    def take_component_damage(self, component_type: type, amount: int, damage_type: Optional[TurretType] = None) -> int:
        """
        Applies damage to a specific component. 
        Returns any excess damage (spillover) if the component is destroyed.
        """
        if damage_type:
            defenses = self.get_component(Defenses)
            if defenses:
                mitigation = defenses.calculate_mitigation(amount, damage_type)
                amount = max(0, amount - mitigation)
                logger.debug(f"Unit '{self.name}' defenses mitigated {mitigation} component damage. Remaining damage: {amount}")

        component = self.get_component(component_type)
        if not component or component.is_destroyed:
            return amount  # All damage spills over if component is missing or already destroyed

        logger.debug(f"Unit '{self.name}' component {component_type.__name__} takes {amount} damage.")
        component.current_hit_points -= amount
        spillover = 0
        
        if component.current_hit_points <= 0:
            spillover = abs(component.current_hit_points)
            component.current_hit_points = 0
            component.on_destroyed()
            logger.debug(f"Unit '{self.name}' component {component_type.__name__} has been destroyed!")

        return spillover

    def heal_hull(self, amount: int) -> int:
        """Heals the unit's hull by the given amount. Returns actual amount healed."""
        if self.current_hit_points >= self.max_hit_points:
            return 0
        healed = min(amount, self.max_hit_points - self.current_hit_points)
        self.current_hit_points += healed
        logger.debug(f"Unit '{self.name}' hull healed by {healed}. HP: {self.current_hit_points}/{self.max_hit_points}")
        return healed

    def heal_components(self, amount: int) -> int:
        """Heals damaged components by the given amount. Returns actual amount healed."""
        healed_total = 0
        for component in self.components.values():
            if amount <= 0:
                break
            if component.current_hit_points < component.max_hit_points:
                needed = component.max_hit_points - component.current_hit_points
                healed = min(amount, needed)
                component.current_hit_points += healed
                healed_total += healed
                amount -= healed
                logger.debug(f"Unit '{self.name}' component {type(component).__name__} healed by {healed}. HP: {component.current_hit_points}/{component.max_hit_points}")
        return healed_total

    def destroy(self) -> None:
        """Handles the destruction of the unit."""
        logger.debug(f"Unit '{self.name}' has been destroyed.")
        if self.hangar_component:
            for docked_unit in list(self.hangar_component.docked_units):
                docked_unit.destroy()
        if self.strikecraft_bay_component:
            for docked_unit in list(self.strikecraft_bay_component.docked_units):
                docked_unit.destroy()
        # Here you would add logic to remove the unit from the game,
        # e.g., by notifying the galaxy or a unit manager.
        if self.in_galaxy:
            self.in_galaxy.remove_unit(self)
        self.game.deselect_object(self)

    def _update_hull_usage(self) -> None:
        """Recalculates and updates the current hull usage based on installed components."""
        usage = sum(c.hull_cost for c in self.components.values())
        self.current_hull_usage = usage
        
        if hasattr(self, 'hull_capacity') and self.current_hull_usage > self.hull_capacity:
            logger.debug(f"Warning: Unit '{self.name}' created exceeding hull capacity! "
                  f"Usage: {self.current_hull_usage}, Capacity: {self.hull_capacity}")
        
    def update(self) -> None:
        """Update the unit's state, including updating its components (processing orders etc.).
        
        This method should be called on each turn processing cycle.
        """
        # --- Lifetime check for temporary units (e.g. Missile Platforms) ---
        if self.lifetime is not None:
            self.lifetime -= 1
            if self.lifetime <= 0:
                self.destroy()
                return

        # Update hyperdrive recharge status if applicable
        if self.hyperdrive_component:
            self.hyperdrive_component.update_recharge()

        # The inhibitor component currently has no update logic, but this is for consistency.
        # if self.inhibitor_component:
        #     self.inhibitor_component.update()

        # Skip weapons updates for disabled units (Ion Bolt)
        if not self.is_disabled:
            if self.weapons_component and self.in_galaxy:
                self.weapons_component.update(self.in_galaxy)

        if self.constructor_component and self.in_galaxy:
            self.constructor_component.update(self.in_galaxy)

        if self.repair_component and self.in_galaxy:
            self.repair_component.update(self.in_galaxy)

        if self.mining_component and self.in_galaxy:
            self.mining_component.update(self.in_galaxy)

        # Tick ability cooldowns and apply ongoing ability effects
        if self.ability_component and self.in_galaxy:
            self.ability_component.update(self.in_galaxy)
            
        if self.strikecraft_bay_component and self.in_galaxy:
            self.strikecraft_bay_component.update(self.in_galaxy)
            
        if self.commander_component:
            self.commander_component.update()
