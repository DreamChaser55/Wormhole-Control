import typing
from typing import Dict, Optional, Any, TYPE_CHECKING
from utils import HexCoord
from geometry import Position, distance, Vector
from constants import WHITE, YELLOW, GREEN, PURPLE, HULL_CAPACITIES, HullSize, HIT_POINTS, StarType, PlanetType, NebulaType, StormType, NEBULA_COLORS, STORM_COLORS
import uuid
import dataclasses
from enum import Enum, auto
from collections import deque
from unit_orders import Order, OrderStatus, OrderType
from unit_components import (
    UnitComponent,
    Drawable,
    Engines,
    Hyperdrive, HyperdriveType,
    Commander,
    HyperspaceInhibitionFieldEmitter,
    Weapons,
    ColonyComponent,
    Constructor
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
        self.credits = 2000
        self.metal = 1000
        self.crystal = 1000

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
    def __init__(self, in_hex: HexCoord, in_system: str, exit_system_name: str):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=500.0)
        self.exit_system_name = exit_system_name
        self.exit_wormhole_id: typing.Optional[int] = None
        self.stability = 100
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
                 game: "Game",
                 in_galaxy: Optional['Galaxy'] = None,
                 engines_speed: typing.Optional[float] = None,
                 engines_hull_cost: int = 5,
                 hyperdrive_type: typing.Optional[HyperdriveType] = None,
                 hyperdrive_hull_cost: int = 10,
                 inhibitor_radius: typing.Optional[float] = None,
                 inhibitor_hull_cost: int = 20,
                 has_weapons: bool = False,
                 weapons_hull_cost: int = 10,
                 has_colony_component: bool = False,
                 colony_hull_cost: int = 0,
                 has_constructor_component: bool = False,
                 constructor_hull_cost: int = 0,
                 ):
        super().__init__(position, in_hex, in_system)
        self.owner = owner
        self.name: str = name
        self.game = game
        self.in_galaxy: Optional['Galaxy'] = in_galaxy

        self.hull_size: HullSize = hull_size
        self.hull_capacity: int = HULL_CAPACITIES[self.hull_size] # consumed by components with hull_cost
        self.current_hull_usage: int = 0

        self.max_hit_points: int = HIT_POINTS[self.hull_size]
        self.current_hit_points: int = self.max_hit_points

        if engines_speed is not None:
            self.engines_component: typing.Optional[Engines] = Engines(
                unit=self,
                speed=engines_speed,
                hull_cost=engines_hull_cost
            )
        else:
            self.engines_component: typing.Optional[Engines] = None

        self.drawable_component: Drawable = Drawable(unit=self)

        if hyperdrive_type is not None:
            self.hyperdrive_component: typing.Optional[Hyperdrive] = Hyperdrive(
                unit=self,
                drive_type=hyperdrive_type,
                hull_cost=hyperdrive_hull_cost
            )
        else:
            self.hyperdrive_component: typing.Optional[Hyperdrive] = None

        if inhibitor_radius is not None:
            self.inhibitor_component: typing.Optional[HyperspaceInhibitionFieldEmitter] = HyperspaceInhibitionFieldEmitter(
                unit=self,
                radius=inhibitor_radius,
                hull_cost=inhibitor_hull_cost
            )
        else:
            self.inhibitor_component: typing.Optional[HyperspaceInhibitionFieldEmitter] = None

        if has_weapons:
            self.weapons_component: typing.Optional[Weapons] = Weapons(
                unit=self,
                hull_cost=weapons_hull_cost
            )
        else:
            self.weapons_component: typing.Optional[Weapons] = None
            
        if has_colony_component:
            self.colony_component: typing.Optional[ColonyComponent] = ColonyComponent(
                unit=self,
                hull_cost=colony_hull_cost
            )
        else:
            self.colony_component: typing.Optional[ColonyComponent] = None

        if has_constructor_component:
            self.constructor_component: typing.Optional[Constructor] = Constructor(
                unit=self,
                hull_cost=constructor_hull_cost
            )
        else:
            self.constructor_component: typing.Optional[Constructor] = None
        
        self.commander_component: Commander = Commander(unit=self)
        
        self._update_hull_usage()

        if self.current_hull_usage > self.hull_capacity:
            print(f"Warning: Unit '{self.name}' created exceeding hull capacity! "
                  f"Usage: {self.current_hull_usage}, Capacity: {self.hull_capacity}")

    def take_damage(self, amount: int) -> None:
        """Reduces the unit's current hit points by the given amount."""
        self.current_hit_points -= amount
        if self.current_hit_points < 0:
            self.current_hit_points = 0
        print(f"Unit '{self.name}' takes {amount} damage. Current HP: {self.current_hit_points}/{self.max_hit_points}")

        if self.current_hit_points == 0:
            self.destroy()

    def destroy(self) -> None:
        """Handles the destruction of the unit."""
        print(f"Unit '{self.name}' has been destroyed.")
        # Here you would add logic to remove the unit from the game,
        # e.g., by notifying the galaxy or a unit manager.
        if self.in_galaxy:
            self.in_galaxy.remove_unit(self)
        self.game.deselect_object(self)

    def _update_hull_usage(self) -> None:
        """Recalculates and updates the current hull usage based on installed components."""
        usage = 0
        if self.drawable_component:
            usage += self.drawable_component.hull_cost
        if self.engines_component:
            usage += self.engines_component.hull_cost
        if self.hyperdrive_component:
            usage += self.hyperdrive_component.hull_cost
        if self.inhibitor_component:
            usage += self.inhibitor_component.hull_cost
        if self.commander_component:
            usage += self.commander_component.hull_cost
        if self.weapons_component:
            usage += self.weapons_component.hull_cost
        if self.colony_component:
            usage += self.colony_component.hull_cost
        if self.constructor_component:
            usage += self.constructor_component.hull_cost
        self.current_hull_usage = usage
        
    def update(self) -> None:
        """Update the unit's state, including updating its components (processing orders etc.).
        
        This method should be called on each turn processing cycle.
        """
        # Update hyperdrive recharge status if applicable
        if self.hyperdrive_component:
            self.hyperdrive_component.update_recharge()

        # The inhibitor component currently has no update logic, but this is for consistency.
        # if self.inhibitor_component:
        #     self.inhibitor_component.update()

        if self.weapons_component and self.in_galaxy:
            self.weapons_component.update(self.in_galaxy)

        if self.constructor_component and self.in_galaxy:
            self.constructor_component.update(self.in_galaxy)
            
        self.commander_component.update()
