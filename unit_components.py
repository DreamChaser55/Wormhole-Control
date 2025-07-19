import typing
from typing import Optional, Tuple, TYPE_CHECKING, Deque
import dataclasses
from collections import deque
from enum import Enum, auto

from utils import HexCoord
from geometry import Vector, Position, distance
from unit_orders import Order, OrderStatus
from constants import DEFAULT_HYPERDRIVE_RECHARGE_DURATION, DEFAULT_JUMP_RANGE
from unit_templates import UNIT_TEMPLATES

if TYPE_CHECKING:
    from entities import Unit, Wormhole, Planet
    from galaxy import Galaxy

# --- Enums for Hyperdrive Component ---

class HyperdriveType(Enum):
    BASIC = "basic"  # Inter-sector travel only
    ADVANCED = "advanced" # Wormhole travel capable

class JumpStatus(Enum):
    CHARGING = "charging"
    READY = "ready"
    JUMPING = "jumping"
    ERROR = "error"

# --- Unit Component Class ---

class UnitComponent:
    """Base class for all components that make up a Unit."""
    def __init__(self, unit: 'Unit', hull_cost: int = 0):
        self.unit: 'Unit' = unit
        self.hull_cost: int = hull_cost

# --- UnitComponent-derived Classes (Components) ---

@dataclasses.dataclass
class Drawable(UnitComponent):
    # No explicit fields needed here anymore beyond what UnitComponent provides. Consider removing the Drawable component in the future?
    def __init__(self, unit: 'Unit'):
        super().__init__(unit, hull_cost=0)

@dataclasses.dataclass
class Engines(UnitComponent):
    """Engines for sublight (non-faster-than-light) travel, within a single sector."""
    speed: float = 0.0
    move_target: typing.Optional[Position] = None

    def __init__(self, unit: 'Unit', speed: float = 0.0, hull_cost: int = 5):
        super().__init__(unit, hull_cost=hull_cost)
        self.speed = speed
        self.move_target = None

@dataclasses.dataclass
class Hyperdrive(UnitComponent):
    """Hyperdrive for faster-than-light travel - inter-sector (basic) or inter-system through wormholes (advanced). """
    drive_type: HyperdriveType = HyperdriveType.BASIC
    jump_range: int = DEFAULT_JUMP_RANGE
    hex_jump_target: typing.Optional[Tuple[HexCoord, Position]] = None
    wormhole_jump_target: typing.Optional['Wormhole'] = None
    jump_status: JumpStatus = JumpStatus.READY
    recharge_time_remaining: int = 0
    RECHARGE_DURATION: int = DEFAULT_HYPERDRIVE_RECHARGE_DURATION

    def __init__(self, unit: 'Unit', drive_type: HyperdriveType = HyperdriveType.BASIC, hull_cost: int = 10, recharge_duration: int = DEFAULT_HYPERDRIVE_RECHARGE_DURATION, jump_range: int = DEFAULT_JUMP_RANGE):
        super().__init__(unit, hull_cost=hull_cost)
        self.drive_type = drive_type
        self.jump_range = jump_range
        self.hex_jump_target = None
        self.wormhole_jump_target = None
        self.jump_status = JumpStatus.READY
        self.recharge_time_remaining = 0
        self.RECHARGE_DURATION = recharge_duration

    def start_recharge(self) -> None:
        """Initiates the hyperdrive recharge sequence."""
        self.jump_status = JumpStatus.CHARGING
        self.recharge_time_remaining = self.RECHARGE_DURATION
        self.hex_jump_target = None
        self.wormhole_jump_target = None
        print(f"Unit {self.unit.name} (id:{self.unit.id}) hyperdrive starting recharge for {self.RECHARGE_DURATION} turns. Status: CHARGING.")

    def update_recharge(self) -> None:
        """Updates the recharge status of the hyperdrive. Called each turn."""
        if self.jump_status == JumpStatus.CHARGING and self.recharge_time_remaining > 0:
            self.recharge_time_remaining -= 1
            if self.recharge_time_remaining <= 0:
                self.jump_status = JumpStatus.READY
                self.recharge_time_remaining = 0
                print(f"Unit {self.unit.name} (id:{self.unit.id}) hyperdrive recharged. Status: READY.")

@dataclasses.dataclass
class HyperspaceInhibitionFieldEmitter(UnitComponent):
    """A component that generates a hyperspace inhibition field, preventing jumps."""
    radius: float = 50.0
    is_active: bool = False

    def __init__(self, unit: 'Unit', radius: float = 50.0, hull_cost: int = 20):
        super().__init__(unit, hull_cost=hull_cost)
        self.radius = radius
        self.is_active = False

    def turn_on(self) -> None:
        """Activates the inhibition field. (Validation logic will be handled by the order)."""
        # In the future, an order will perform validation before setting this.
        self.is_active = True
        print(f"Unit {self.unit.name} inhibition field activated.")

    def turn_off(self) -> None:
        """Deactivates the inhibition field."""
        self.is_active = False
        print(f"Unit {self.unit.name} inhibition field deactivated.")

    def toggle(self, galaxy_ref: 'Galaxy') -> bool:
        """
        Directly toggles the inhibition field on or off, performing all
        necessary validation.

        Args:
            galaxy_ref: A reference to the main galaxy object.

        Returns:
            True if the toggle was successful, False otherwise.
        """
        from geometry import Circle, is_circle_contained, do_circles_intersect

        if not galaxy_ref or not self.unit.in_system or self.unit.in_hex is None:
            return False

        current_hex = galaxy_ref.systems[self.unit.in_system].hexes[self.unit.in_hex]
        
        if self.is_active:
            # --- Logic for turning the field OFF ---
            if self.unit.id in current_hex.dynamic_inhibition_zones:
                del current_hex.dynamic_inhibition_zones[self.unit.id]
            self.turn_off()
            return True
        else:
            # --- Logic for turning the field ON ---
            proposed_field = Circle(center=self.unit.position, radius=self.radius)

            # 1. Validate containment
            if not is_circle_contained(proposed_field, current_hex.boundary_circle):
                print(f"[{self.unit.name}] TOGGLE_INHIBITOR (Direct): FAILED (field would cross sector boundary).")
                return False

            # 2. Validate intersection
            for existing_zone in current_hex.get_all_inhibition_zones():
                if do_circles_intersect(proposed_field, existing_zone):
                    print(f"[{self.unit.name}] TOGGLE_INHIBITOR (Direct): FAILED (field would overlap with another).")
                    return False
            
            # All checks passed, turn it on
            self.turn_on()
            current_hex.dynamic_inhibition_zones[self.unit.id] = proposed_field
            return True

@dataclasses.dataclass
class Commander(UnitComponent):
    """Commander is a component responsible for managing and executing orders for a Unit.

    This component maintains a queue of orders and processes them in sequence,
    handling the execution and status updates of each order.
    """
    current_order: Optional[Order] = None
    orders_queue: Deque[Order] = dataclasses.field(default_factory=deque)

    def __init__(self, unit: 'Unit'):
        super().__init__(unit, hull_cost=0)
        self.current_order = None
        self.orders_queue = deque()

    def add_order(self, order: Order) -> None:
        """Add a new order to the queue.

        Args:
            order: The order to add to the queue
        """
        self.orders_queue.append(order)

        if self.current_order is None:
            self.start_next_order()

    def cancel_order(self, order_id: str) -> bool:
        """Cancel and remove a specific order by its ID.

        Args:
            order_id: The ID of the order to cancel

        Returns:
            True if the order was found and cancelled, False otherwise
        """
        if self.current_order and self.current_order.order_id == order_id:
            self.current_order.cancel()
            self.current_order = None
            self.start_next_order()
            return True

        for order_in_queue in list(self.orders_queue):
            if order_in_queue.order_id == order_id:
                order_in_queue.cancel()
                self.orders_queue.remove(order_in_queue)
                return True
        return False

    def clear_orders(self) -> None:
        """Cancel and clear all orders for this unit."""
        if self.current_order:
            self.current_order.cancel()
            self.current_order = None

        for order in self.orders_queue:
            order.cancel()
        self.orders_queue.clear()

        if self.unit.engines_component:
            self.unit.engines_component.move_target = None
        if self.unit.hyperdrive_component:
            self.unit.hyperdrive_component.hex_jump_target = None
            self.unit.hyperdrive_component.wormhole_jump_target = None

    def get_active_orders_count(self) -> int:
        """Get the total number of active orders (current + queued).

        Returns:
            The number of active orders
        """
        return len(self.orders_queue) + (1 if self.current_order else 0)

    def update(self) -> None:
        """Process the current order and update its status.

        This method should be called on each game update cycle.
        """
        if not self.current_order:
            self.start_next_order()
            if not self.current_order:
                return

        if not self.current_order:
            return

        galaxy_ref: Optional['Galaxy'] = getattr(self.unit, 'in_galaxy', None)

        if galaxy_ref:
            self.current_order.update(galaxy_ref=galaxy_ref)
        else:
            unit_name = getattr(self.unit, 'name', f"Unit ID {getattr(self.unit, 'id', 'Unknown')}")
            print(f"Error: [{unit_name}] Commander Component UPDATE: Cannot update order, unit.in_galaxy is None.")
            if self.current_order.status == OrderStatus.IN_PROGRESS:
                 self.current_order.status = OrderStatus.FAILED

        order_is_finished = False
        if self.current_order.is_completed():
            order_is_finished = True
        elif self.current_order.status in [OrderStatus.FAILED, OrderStatus.CANCELLED]:
            order_is_finished = True

        if order_is_finished:
            self.current_order = None
            self.start_next_order()

    def start_next_order(self) -> None:
        """Starts the next order from the queue if available."""
        if not self.current_order and self.orders_queue:
            self.current_order = self.orders_queue.popleft()
            
            galaxy_ref: Optional['Galaxy'] = getattr(self.unit, 'in_galaxy', None)

            if galaxy_ref:
                self.current_order.execute(galaxy_ref=galaxy_ref)
                if self.current_order and self.current_order.status == OrderStatus.IN_PROGRESS:
                    self.current_order.update(galaxy_ref=galaxy_ref)
            else:
                unit_name = getattr(self.unit, 'name', f"Unit ID {getattr(self.unit, 'id', 'Unknown')}")
                print(f"Error: [{unit_name}] Commander Component START_NEXT_ORDER: Cannot execute order, unit.in_galaxy is None.")
                if self.current_order:
                    self.current_order.status = OrderStatus.FAILED

# --- Enums for Weapons Component ---

class TurretType(Enum):
    MASS_DRIVER = "mass_driver"
    BEAM = "beam"
    MISSILE = "missile"

# --- Weapon-related dataclasses ---

@dataclasses.dataclass
class Turret:
    """
    A dataclass representing a single turret on a unit.
    This is not a component, but a data structure used by the Weapons component.
    """
    turret_type: TurretType
    damage: float
    range: float
    cooldown: int
    parent_unit: 'Unit'
    current_cooldown: int = 0
    target: Optional['Unit'] = None

    def fire(self) -> None:
        """
        Fires at the turret's current target and resets the cooldown.
        """
        if self.target:
            print(f"Turret {self.turret_type.name} from {self.parent_unit.name} firing at {self.target.name}!")
            self.target.take_damage(int(self.damage))
        self.current_cooldown = self.cooldown

    def update(self) -> None:
        """
        Updates the turret's state, primarily its cooldown.
        """
        if self.current_cooldown > 0:
            self.current_cooldown -= 1

# --- Weapons Component ---

@dataclasses.dataclass
class Weapons(UnitComponent):
    """
    Manages all weapon systems for a unit.
    """
    turrets: list[Turret] = dataclasses.field(default_factory=list)

    def __init__(self, unit: 'Unit', hull_cost: int = 0):
        super().__init__(unit, hull_cost=hull_cost)
        self.turrets = []

    def add_turret(self, turret: Turret) -> None:
        """
        Adds a pre-configured turret to the unit.
        """
        self.turrets.append(turret)

    def update(self, galaxy: 'Galaxy') -> None:
        """
        Updates all turrets and fires if a target is set and is in the same system, hex, in range and the cooldown is over.
        """

        for turret in self.turrets:
            turret.update()

        for turret in self.turrets:
            if turret.target:
                if turret.target.current_hit_points <= 0:
                    turret.target = None
                    continue

                target_in_same_system = self.unit.in_system == turret.target.in_system
                target_in_same_hex = self.unit.in_hex == turret.target.in_hex
                target_in_range = distance(self.unit.position, turret.target.position) < turret.range

                if target_in_same_system and target_in_same_hex and target_in_range:
                    if turret.current_cooldown <= 0:
                        turret.fire()

    def set_target(self, target_unit: 'Unit') -> None:
        """Sets the target of the turrets to the specified unit."""
        for turret in self.turrets:
            turret.target = target_unit
    
    def clear_target(self) -> None:
        """Clears the target of the turrets."""
        for turret in self.turrets:
            turret.target = None

@dataclasses.dataclass
class ColonyComponent(UnitComponent):
    """A component that allows a unit to transport population and colonize planets."""
    population_cargo: int = 0
    max_cargo: int = 100

    def __init__(self, unit: 'Unit', hull_cost: int = 10):
        super().__init__(unit, hull_cost=hull_cost)
        self.population_cargo = 0
        self.max_cargo = 100

    def load_population(self, planet: 'Planet', amount: int) -> bool:
        if planet.owner != self.unit.owner:
            print(f"Error: Cannot load population from unowned planet {planet.name}.")
            return False
        if planet.population < amount:
            print(f"Error: Not enough population on {planet.name} to load {amount}.")
            return False
        if self.population_cargo + amount > self.max_cargo:
            print(f"Error: Not enough cargo space to load {amount} population.")
            return False
        
        planet.population -= amount
        self.population_cargo += amount
        print(f"Loaded {amount} population from {planet.name}. Current cargo: {self.population_cargo}")
        return True

    def unload_population(self, planet: 'Planet', amount: int) -> bool:
        if self.population_cargo < amount:
            print(f"Error: Not enough population in cargo to unload {amount}.")
            return False

        if planet.owner is None:
            planet.owner = self.unit.owner
            print(f"Planet {planet.name} has been colonized by {self.unit.owner.name}.")

        if planet.owner != self.unit.owner:
            print(f"Error: Cannot unload population on planet owned by another player.")
            return False

        planet.population += amount
        self.population_cargo -= amount
        print(f"Unloaded {amount} population onto {planet.name}. Current cargo: {self.population_cargo}")
        return True

@dataclasses.dataclass
class BuildableUnit:
    unit_template_name: str
    time_to_build: int
    cost_credits: int


@dataclasses.dataclass
class Constructor(UnitComponent):
    """A component that allows a unit to construct other units (stations)."""
    buildable_units: list[BuildableUnit] = dataclasses.field(default_factory=list)
    build_range: float = 500.0
    
    # Construction state
    current_construction_target: Optional[tuple[str, Position]] = None # (unit_template_name, position)
    construction_progress: int = 0
    time_to_build: int = 0

    def __init__(self, unit: 'Unit', hull_cost: int):
        super().__init__(unit, hull_cost)
        self.buildable_units = []
        self.current_construction_target = None
        self.construction_progress = 0
        self.time_to_build = 0
        self.__post_init__()

    def __post_init__(self):
        # TODO: This should be loaded from a template or data file
        self.buildable_units.append(BuildableUnit("STATION_MK1", 10, 500))

    def can_build(self, unit_template_name: str) -> Optional[BuildableUnit]:
        """Check if this constructor can build a specific unit type."""
        for bu in self.buildable_units:
            if bu.unit_template_name == unit_template_name:
                return bu
        return None

    def start_construction(self, unit_template_name: str, position: Position, galaxy: 'Galaxy') -> bool:
        """Starts the construction of a new unit."""
        buildable = self.can_build(unit_template_name)
        if not buildable:
            print(f"Error: {self.unit.name} cannot build {unit_template_name}.")
            return False

        owner = self.unit.owner
        if owner.credits < buildable.cost_credits:
            print(f"Error: Not enough credits to build {unit_template_name}.")
            return False
        owner.credits -= buildable.cost_credits

        self.current_construction_target = (unit_template_name, position)
        self.time_to_build = buildable.time_to_build
        self.construction_progress = 0
        print(f"{self.unit.name} started constructing {unit_template_name} at {position}. Cost: {buildable.cost_credits}")
        return True

    def cancel_construction(self):
        """Cancels the current construction project."""
        if self.current_construction_target:
            print(f"Construction of {self.current_construction_target[0]} cancelled.")
            # NOTE: Resource refund should be handled by the Order
            self.current_construction_target = None
            self.construction_progress = 0
            self.time_to_build = 0

    def update(self, galaxy: 'Galaxy'):
        """Updates the construction progress. Called each turn."""
        if self.current_construction_target:
            self.construction_progress += 1
            if self.construction_progress >= self.time_to_build:
                self.finish_construction(galaxy)

    def create_unit_from_template(self, galaxy: 'Galaxy', template_name: str, owner: 'Player', system_name: str, hex_coord: 'HexCoord', position: 'Position'):
        """Creates a new unit based on the template."""
        from entities import Unit # Avoid circular import

        template = UNIT_TEMPLATES.get(template_name)
        if not template:
            print(f"Error: Unit template '{template_name}' not found.")
            return

        system = galaxy.systems.get(system_name)
        if not system:
            print(f"Error: System '{system_name}' not found for unit creation.")
            return

        new_unit = Unit(
            owner=owner,
            name=template["name"],
            hull_size=template["hull_size"],
            game=self.unit.game,
            in_system=system_name,
            in_hex=hex_coord,
            position=position,
            # Engines
            engines_speed=template["engine_speed"] if "engine_speed" in template else None,
            engines_hull_cost=template["engine_hull_cost"],
            # Hyperdrive
            hyperdrive_type=template["hyperdrive_type"] if "hyperdrive_type" in template else None,
            hyperdrive_hull_cost=template["hyperdrive_hull_cost"],
            # Weapons
            has_weapons=template["has_weapon_bays"],
            weapons_hull_cost=template["weapon_bays_hull_cost"],
            # Constructor
            has_constructor_component=template["has_constructor_component"],
            constructor_hull_cost=template["constructor_hull_cost"]
        )

        system.add_unit(new_unit)
        print(f"Created unit {new_unit.name} ({new_unit.id}) for player {owner.id} in {system_name} at {hex_coord}")

    def finish_construction(self, galaxy: 'Galaxy'):
        """Finalizes the construction and creates the new unit."""
        if not self.current_construction_target:
            return

        unit_template_name, position = self.current_construction_target
        print(f"Construction of {unit_template_name} finished by {self.unit.name}.")
        
        self.create_unit_from_template(
            galaxy=galaxy,
            template_name=unit_template_name,
            owner=self.unit.owner,
            system_name=self.unit.in_system,
            hex_coord=self.unit.in_hex,
            position=position
        )

        # Reset construction state
        self.current_construction_target = None
        self.construction_progress = 0
        self.time_to_build = 0