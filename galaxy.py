import typing
import math
import random
from dataclasses import dataclass, field
import pygame
from constants import SCREEN_RES, SECTOR_CIRCLE_RADIUS_LOGICAL, StarType, PlanetType, NebulaType, StormType
from utils import HexCoord
from geometry import distance_sq, Vector, Position, Circle
from entities import Player, GameObject, Unit, Star, Planet, Wormhole, Moon, Asteroid, HullSize, Order, OrderType, CelestialBody, Nebula, Storm, Comet, DebrisField, AsteroidField, IceField

# Galaxy generation parameters
NUM_SYSTEMS = 15
GALAXY_PADDING = 50 # Pixels from edge for system placement
MIN_SYSTEM_DISTANCE = 50
MAX_SYSTEM_DISTANCE = 350
SECOND_NEAREST_WORMHOLE_PROB = 1/3 # Probability of connecting a system to the second nearest system

# --- Hex Class ---
@dataclass
class Hex:
    """Represents a single cell in a star system's hex grid, which corresponds to a sector map."""
    q: int
    r: int
    in_system: str
    celestial_bodies: typing.List['CelestialBody'] = field(default_factory=list)
    units: typing.List['Unit'] = field(default_factory=list)
    
    # Inhibition field attributes
    boundary_circle: Circle = field(init=False)
    static_inhibition_zones: typing.List[Circle] = field(init=False, default_factory=list)
    dynamic_inhibition_zones: typing.Dict[int, Circle] = field(init=False, default_factory=dict)

    def __post_init__(self):
        """Initializes fields that depend on other attributes."""
        self.boundary_circle = Circle(
            center=Position(0, 0),
            radius=SECTOR_CIRCLE_RADIUS_LOGICAL
        )

    def get_all_inhibition_zones(self) -> typing.List[Circle]:
        """Returns a combined list of static and dynamic inhibition zones."""
        return self.static_inhibition_zones + list(self.dynamic_inhibition_zones.values())

    def update_static_inhibition_zones(self):
        """
        Calculates and populates the static inhibition zones based on the
        celestial bodies currently in this hex.
        """
        self.static_inhibition_zones.clear()
        for body in self.celestial_bodies:
            if hasattr(body, 'inhibition_field_radius') and body.inhibition_field_radius > 0:
                self.static_inhibition_zones.append(Circle(body.position, body.inhibition_field_radius))

    def coordinates(self) -> HexCoord:
        return (self.q, self.r)

    def add_celestial_body(self, body: 'CelestialBody'):
        self.celestial_bodies.append(body)

    def remove_celestial_body(self, body: 'CelestialBody'):
        if body in self.celestial_bodies:
            self.celestial_bodies.remove(body)

    def add_unit(self, unit: 'Unit'):
        self.units.append(unit)

    def remove_unit(self, unit: 'Unit'):
        if unit in self.units:
            self.units.remove(unit)

    def is_empty(self) -> bool:
        """Check if the hex contains any celestial bodies or units."""
        return not self.celestial_bodies and not self.units

# --- Star System Class ---
class StarSystem:
    """Represents a single star system with a hex grid and contents."""
    def __init__(self, name: str, position: Position, radius: int = 3):
        """Initializes a StarSystem.

        Args:
            name: Unique name for the system (e.g., 'Sol'), also used as the identifier.
            position: Position object representing the system's position in the galaxy view (pixel coords).
            radius: The radius of the hexagonal grid within the system.
        """
        self.name = name
        self.position = position
        self.radius = radius
        self.hexes: typing.Dict[HexCoord, Hex] = {}
        self.celestial_bodies_by_id: typing.Dict[int, 'CelestialBody'] = {}
        self.generate_grid()
        self.spawn_celestial_bodies()

    def generate_grid(self):
        """Generates the hexagonal grid coordinates for the system."""
        for q in range(-self.radius, self.radius + 1):
            r1 = max(-self.radius, -q - self.radius)
            r2 = min(self.radius, -q + self.radius)
            for r in range(r1, r2 + 1):
                self.hexes[(q, r)] = Hex(q, r, in_system=self.name)

    def spawn_celestial_bodies(self):
        """Adds the central star and randomly spawns other celestial bodies in the system."""
        # Add central star of a random type
        star_type = random.choice(list(StarType))
        star = Star(in_system=self.name, star_type=star_type)
        self.add_celestial_body(star)

        # Get a list of all hexes except the center one (where the star is)
        available_hexes = [h for h in self.hexes.values() if h.coordinates() != (0, 0)]
        random.shuffle(available_hexes)

        # Define probabilities for spawning different celestial bodies
        body_types_to_spawn = [Planet, Moon, Asteroid, AsteroidField, IceField, Nebula, Storm, Comet, DebrisField]
        weights = [0.4, 0.15, 0.15, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05]

        # Decide how many bodies to spawn in this system
        num_bodies_to_spawn = random.randint(4, len(available_hexes) // 2)

        for i in range(min(num_bodies_to_spawn, len(available_hexes))):
            hex_to_spawn_in = available_hexes[i]

            # Choose a body type based on weights
            chosen_body_class = random.choices(body_types_to_spawn, weights=weights, k=1)[0]

            body = None
            if chosen_body_class == Planet:
                planet_type = random.choice(list(PlanetType))
                body = Planet(in_hex=hex_to_spawn_in.coordinates(), in_system=self.name, planet_type=planet_type)
            elif chosen_body_class == Nebula:
                nebula_type = random.choice(list(NebulaType))
                body = Nebula(in_hex=hex_to_spawn_in.coordinates(), in_system=self.name, nebula_type=nebula_type)
            elif chosen_body_class == Storm:
                storm_type = random.choice(list(StormType))
                body = Storm(in_hex=hex_to_spawn_in.coordinates(), in_system=self.name, storm_type=storm_type)
            else:  # For Moon, Asteroid, Fields, Comet
                body = chosen_body_class(in_hex=hex_to_spawn_in.coordinates(), in_system=self.name)

            if body:
                self.add_celestial_body(body)

        # After all bodies are placed, calculate the inhibition zones
        for hex_obj in self.hexes.values():
            hex_obj.update_static_inhibition_zones()

    def add_celestial_body(self, body_to_add: CelestialBody):
        """Adds a celestial body to the specified system's hex and the system's dictionary."""
        if body_to_add.in_hex in self.hexes:
            self.hexes[body_to_add.in_hex].add_celestial_body(body_to_add)
            self.celestial_bodies_by_id[body_to_add.id] = body_to_add
        else:
            print(f"Error: Hex {body_to_add.in_hex} not found in system {self.name}")

    def remove_celestial_body(self, body_to_remove: CelestialBody):
        """Removes a celestial body from the system."""
        if body_to_remove.in_hex in self.hexes:
            self.hexes[body_to_remove.in_hex].remove_celestial_body(body_to_remove)
            if body_to_remove.id in self.celestial_bodies_by_id:
                del self.celestial_bodies_by_id[body_to_remove.id]
        else:
            print(f"Error: Hex {body_to_remove.in_hex} not found in system {self.name}")

    def add_unit(self, unit_to_add: Unit):
        """Adds a unit to the specified system's hex."""
        hex_coord = unit_to_add.in_hex
        if hex_coord in self.hexes:
            self.hexes[hex_coord].add_unit(unit_to_add)
            unit_to_add.in_system = self.name
        else:
             print(f"Warning: Attempted to add unit to invalid hex {hex_coord} in system {self.name}")

    def remove_unit(self, unit_to_remove: Unit) -> bool:
         """Removes a specific unit object from the system's hex. Returns True if successful."""
         hex_coord = unit_to_remove.in_hex
         if hex_coord in self.hexes:
              if unit_to_remove in self.hexes[hex_coord].units:
                   self.hexes[hex_coord].remove_unit(unit_to_remove)
                   unit_to_remove.in_system = None
                   return True
         return False

    def get_units_in_hex(self, hex_coord: HexCoord) -> typing.List[Unit]:
        """Returns a list of units in the specified hex."""
        return self.hexes.get(hex_coord, []).units

    def get_celestial_bodies_in_hex(self, hex_coord: HexCoord) -> typing.List[CelestialBody]:
        """Returns a list of celestial bodies in the specified hex."""
        return self.hexes.get(hex_coord, []).celestial_bodies

    def get_all_units(self) -> typing.List[typing.Tuple[Unit, HexCoord]]:
        """Returns a list of all units in the system and their hex coordinates."""
        all_units = []
        for coord, hex in self.hexes.items():
            for unit in hex.units:
                 all_units.append((unit, coord))
        return all_units

    def get_all_celestial_bodies(self) -> typing.List[typing.Tuple[HexCoord, CelestialBody]]:
        """Returns a list of all celestial bodies and their hex coordinates."""
        return [(body.in_hex, body) for body in self.celestial_bodies_by_id.values()]

    def move_unit_between_hexes(self, unit: Unit, destination_hex: HexCoord) -> bool:
        """Moves a unit from its current hex to a destination hex within this system.

        Args:
            unit: The unit object to move.
            destination_hex: The target hex coordinate.

        Returns:
            True if the move was successful, False otherwise.
        """
        origin_hex = unit.in_hex
        if origin_hex == destination_hex:
            print(f"Warning: Attempted to move unit {unit.id} ({unit.name}) to its current hex {origin_hex}.")
            return False # Or True, arguably it's 'moved'

        if destination_hex not in self.hexes:
            print(f"Error: Cannot move unit {unit.id} ({unit.name}) to invalid destination hex {destination_hex} in system {self.name}")
            return False

        # 1. Remove from origin
        removed = self.remove_unit(unit)
        if not removed:
            print(f"Error: Failed to remove unit {unit.id} ({unit.name}) from origin hex {origin_hex} during move.")
            # Attempt to find where the unit actually is, if anywhere
            actual_hex = unit.in_hex
            print(f"Unit {unit.id} ({unit.name}) is not in hex {origin_hex} but in {actual_hex}")
            return False

        # 2. Update unit's internal hex
        unit.in_hex = destination_hex

        # 3. Add to destination
        self.add_unit(unit)
        print(f"System {self.name}: Moved unit {unit.id} ({unit.name}) from {origin_hex} to {destination_hex}")
        return True

# --- Galaxy Class ---
class Galaxy:
    """Represents the entire game galaxy, containing systems and wormholes."""
    def __init__(self, num_systems: int = NUM_SYSTEMS, generation_bounds: typing.Optional[pygame.Rect] = None):
        self.systems: typing.Dict[str, StarSystem] = {}
        self.wormholes: typing.Dict[int, Wormhole] = {}
        self.system_graph: typing.Dict[str, typing.List[str]] = {}
        
        if generation_bounds:
            self.generation_x_min = generation_bounds.left + GALAXY_PADDING
            self.generation_y_min = generation_bounds.top + GALAXY_PADDING
            self.generation_x_max = generation_bounds.right - GALAXY_PADDING
            self.generation_y_max = generation_bounds.bottom - GALAXY_PADDING
        else:
            self.generation_x_min = GALAXY_PADDING
            self.generation_y_min = GALAXY_PADDING
            self.generation_x_max = SCREEN_RES.x - GALAXY_PADDING
            self.generation_y_max = SCREEN_RES.y - GALAXY_PADDING

        # Ensure max is greater than min (e.g., if padding is too large for bounds)
        self.generation_x_max = max(self.generation_x_min, self.generation_x_max)
        self.generation_y_max = max(self.generation_y_min, self.generation_y_max)

        self.generate_galaxy(num_systems)

    def get_unit_by_id(self, unit_id: int) -> typing.Optional[Unit]:
        """Finds a unit anywhere in the galaxy by its ID."""
        for system in self.systems.values():
            for hex_obj in system.hexes.values():
                for unit in hex_obj.units:
                    if unit.id == unit_id:
                        return unit
        return None

    def remove_unit(self, unit: Unit):
        """Removes a unit from the galaxy."""
        if unit.in_system and unit.in_system in self.systems:
            system = self.systems[unit.in_system]
            system.remove_unit(unit)
        else:
            print(f"Warning: Could not remove unit {unit.id} - system '{unit.in_system}' not found.")

    # --- Incremental Galaxy Generation Method  ---
    def generate_galaxy(self, num_systems: int):
        """Generates systems and wormholes incrementally."""
        if num_systems <= 0:
            print("Cannot generate 0 or negative systems.")
            return

        # --- Generate unique system names ---
        names = ["Sol", "Alpha Centauri", "Sirius", "Proxima Centauri", "Barnard's Star",
                 "Tau Ceti", "Epsilon Eridani", "Kepler-186", "Gliese 581", "Vega",
                 "Arcturus", "Capella", "Rigel", "Betelgeuse", "Procyon"]
        random.shuffle(names)
        base_len = len(names)
        if num_systems > base_len:
            names.extend([f"System-{i+1}" for i in range(num_systems - base_len)])

        system_names = []
        used_names = set()
        for i in range(num_systems):
            base_name = names[i]
            system_name = base_name
            count = 1
            while system_name in used_names:
                system_name = f"{base_name}-{count}"
                count += 1
            used_names.add(system_name)
            system_names.append(system_name)

        # --- Place First System ---
        first_sys_name = system_names[0]
        first_x = random.randint(self.generation_x_min, self.generation_x_max)
        first_y = random.randint(self.generation_y_min, self.generation_y_max)
        radius = random.randint(5, 8)
        self.systems[first_sys_name] = StarSystem(first_sys_name, Vector(first_x, first_y), radius)
        print(f"Placed first system: {first_sys_name} at {self.systems[first_sys_name].position}")

        # --- Place Remaining Systems Incrementally ---
        max_placement_attempts = 100 # Avoid infinite loops
        for i in range(1, num_systems):
            current_sys_name = system_names[i]
            found_position = False
            attempts = 0

            while not found_position and attempts < max_placement_attempts:
                attempts += 1
                # Generate random coordinates within the defined generation area
                x = random.randint(self.generation_x_min, self.generation_x_max)
                y = random.randint(self.generation_y_min, self.generation_y_max)

                # Determine closest existing systems
                distances = [] # get squared distances
                for existing_name, existing_sys in self.systems.items():
                    d_sq = distance_sq(Vector(x, y), existing_sys.position)
                    distances.append((d_sq, existing_name))

                if not distances: # Should only happen for the very first system, handled above
                    break

                distances.sort()
                nearest_dist_sq, nearest_sys_name = distances[0]
                second_nearest_sys_name = distances[1][1] if len(distances) > 1 else None

                # Check distance constraints
                min_dist_sq = MIN_SYSTEM_DISTANCE ** 2
                max_dist_sq = MAX_SYSTEM_DISTANCE ** 2

                if min_dist_sq <= nearest_dist_sq <= max_dist_sq:
                    # Coords' distance constraints OK - Spawn system
                    radius = random.randint(5, 8)
                    new_system_position = Vector(x,y)
                    self.systems[current_sys_name] = StarSystem(current_sys_name, new_system_position, radius)
                    print(f"Placed system {current_sys_name} at {new_system_position} near {nearest_sys_name}")

                    # Connect to closest
                    self.add_wormhole_pair(current_sys_name, nearest_sys_name)
                    print(f"  Added wormhole: {current_sys_name} <-> {nearest_sys_name}")

                    # Connect to second closest (probabilistically)
                    if second_nearest_sys_name and random.random() < SECOND_NEAREST_WORMHOLE_PROB:
                        # Check if already connected to avoid duplicate wormholes
                        already_connected = False
                        origin_system = self.systems[current_sys_name]
                        for _, hex in origin_system.hexes.items():
                             for body in hex.celestial_bodies:
                                 if isinstance(body, Wormhole) and body.exit_system_name == second_nearest_sys_name:
                                     already_connected = True
                                     break
                             if already_connected: break

                        if not already_connected:
                            self.add_wormhole_pair(current_sys_name, second_nearest_sys_name)
                            print(f"  Added 2nd wormhole: {current_sys_name} <-> {second_nearest_sys_name}")

                    found_position = True
                # else: Coords NOT OK - Loop continues to try new random coords

            if not found_position:
                print(f"Warning: Could not place system {current_sys_name} after {max_placement_attempts} attempts. Constraints might be too tight.")

        print(f"Finished galaxy generation.")
        print(f"Generated {len(self.systems)} systems.")
        # The number of wormhole connections is half the number of wormhole objects
        print(f"Created {len(self.wormholes) // 2} wormhole connections.\n")

        self._build_system_graph()


    def _build_system_graph(self):
        """
        Builds the system graph and stores it in self.system_graph.
        This should be called once after galaxy generation is complete.
        """
        graph: typing.Dict[str, typing.List[str]] = {name: [] for name in self.systems}
        for system_name, system_obj in self.systems.items():
            for _coord, hex_obj in system_obj.hexes.items():
                for body in hex_obj.celestial_bodies:
                    if isinstance(body, Wormhole) and body.exit_system_name:
                        if body.exit_system_name in graph:
                            if body.exit_system_name not in graph[system_name]:
                                graph[system_name].append(body.exit_system_name)
                        else:
                            print(f"Warning: Wormhole in {system_name} points to non-existent system {body.exit_system_name}")
        self.system_graph = graph

    # --- Wormhole Helper Methods ---

    def find_empty_hex(self, system: StarSystem) -> typing.Optional[HexCoord]:
        """Finds a random empty hex (no celestial bodies or units)."""
        potential_hexes = [h for h in system.hexes if system.hexes[h].is_empty()]
        return random.choice(potential_hexes) if potential_hexes else None

    def add_wormhole_pair(self, sys_name_a: str, sys_name_b: str):
        """Creates a pair of linked wormholes between two systems."""
        system_a = self.systems[sys_name_a]
        system_b = self.systems[sys_name_b]

        if not system_a or not system_b:
            print(f"Error creating wormhole: System not found ({sys_name_a} or {sys_name_b})")
            return

        hex_a = self.find_empty_hex(system_a)
        hex_b = self.find_empty_hex(system_b)

        if hex_a is None or hex_b is None:
            print(f"Error creating wormhole: Could not find empty hex in {sys_name_a} or {sys_name_b}")
            return

        # Create wormholes
        wh_a = Wormhole(in_hex=hex_a, in_system=sys_name_a, exit_system_name=sys_name_b)
        wh_b = Wormhole(in_hex=hex_b, in_system=sys_name_b, exit_system_name=sys_name_a)

        # Link them
        wh_a.exit_wormhole_id = wh_b.id
        wh_b.exit_wormhole_id = wh_a.id

        # Add to systems and global list
        system_a.add_celestial_body(wh_a)
        system_b.add_celestial_body(wh_b)
        self.wormholes[wh_a.id] = wh_a
        self.wormholes[wh_b.id] = wh_b

        # Update inhibition zones for the hexes that received the wormholes
        if hex_a in system_a.hexes:
            system_a.hexes[hex_a].update_static_inhibition_zones()
        if hex_b in system_b.hexes:
            system_b.hexes[hex_b].update_static_inhibition_zones()

    def move_unit_between_systems(self, unit: Unit, origin_system_name: str, destination_system_name: str, destination_hex: HexCoord) -> bool:
        """Moves a unit between two star systems.

        Args:
            unit: The unit object to move.
            origin_system_name: The name of the system the unit is starting in.
            destination_system_name: The name of the system the unit is moving to.
            destination_hex: The hex coordinate the unit should arrive at in the destination system.

        Returns:
            True if the move was successful, False otherwise.
        """
        origin_system = self.systems[origin_system_name]
        destination_system = self.systems[destination_system_name]

        if not origin_system:
            print(f"Error: Origin system '{origin_system_name}' not found for unit transfer.")
            return False
        if not destination_system:
            print(f"Error: Destination system '{destination_system_name}' not found for unit transfer.")
            return False

        # Validate destination hex exists in the destination system
        if destination_hex not in destination_system.hexes:
             print(f"Error: Cannot move unit {unit.id} ({unit.name}) to invalid destination hex {destination_hex} in system {destination_system_name}")
             return False

        # 1. Remove from origin system
        removed = origin_system.remove_unit(unit)
        if not removed:
            print(f"Error: Failed to remove unit {unit.id} ({unit.name}) from origin system {origin_system_name} during transfer.")
            return False

        # 2. Update unit's system ID and hex
        unit.in_system = destination_system_name
        unit.in_hex = destination_hex

        # 3. Add to destination system
        destination_system.add_unit(unit)
        print(f"Galaxy: Transferred unit {unit.id} ({unit.name}) from system {origin_system_name} to system {destination_system_name}, into hex {destination_hex}")
        return True

    def get_celestial_body_by_id(self, body_id: int) -> typing.Optional['CelestialBody']:
        """Finds and returns a celestial body by its unique ID."""
        for system in self.systems.values():
            if body_id in system.celestial_bodies_by_id:
                return system.celestial_bodies_by_id[body_id]
        return None
