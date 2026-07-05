import logging

logger = logging.getLogger(__name__)

import typing
from typing import Optional, Tuple, TYPE_CHECKING, Deque
import dataclasses
from collections import deque
from enum import Enum, auto
import math
import random

from utils import HexCoord
from geometry import Vector, Position, distance
from unit_orders import Order, OrderStatus
from constants import DEFAULT_HYPERDRIVE_RECHARGE_DURATION, DEFAULT_JUMP_RANGE, HullSize, SECTOR_CIRCLE_RADIUS_LOGICAL, MAX_UNIT_XP, XP_WEAPON_DAMAGE_BONUS, XP_DEFENSE_BONUS, XP_SPEED_BONUS, XP_JUMP_RANGE_BONUS
from unit_templates import UNIT_TEMPLATES

if TYPE_CHECKING:
    from entities import Unit, Wormhole, Planet
    from galaxy import Galaxy
    from game import Game

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
    DISPLAY_NAME: str = "Component"
    SIDEBAR_ORDER: int = 100

    def __init__(self, unit: 'Unit', hull_cost: int = 0):
        self.unit: 'Unit' = unit
        self.hull_cost: int = hull_cost
        self.max_hit_points: int = max(10, hull_cost * 10)
        self.current_hit_points: int = self.max_hit_points

    @property
    def is_destroyed(self) -> bool:
        return self.current_hit_points <= 0

    def on_destroyed(self) -> None:
        """Called when the component's hit points reach 0."""
        pass

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        """
        Returns a list of UI element definitions (labels, progress bars, buttons)
        to render in the sidebar when this component is selected.
        """
        status = "DESTROYED" if self.is_destroyed else f"HP: {self.current_hit_points}/{self.max_hit_points}"
        return [
            {
                'type': 'label',
                'text': f"{self.DISPLAY_NAME} [{status}]",
                'object_id': '#sidebar_section_header_label',
                'height': 28
            }
        ]

# --- UnitComponent-derived Classes (Components) ---

@dataclasses.dataclass
class Engines(UnitComponent):
    """Engines for sublight (non-faster-than-light) travel, within a single sector."""
    DISPLAY_NAME: str = "Engines"
    SIDEBAR_ORDER: int = 2
    speed: float = 0.0
    move_target: typing.Optional[Position] = None

    def __init__(self, unit: 'Unit', speed: float = 0.0, hull_cost: int = 5):
        super().__init__(unit, hull_cost=hull_cost)
        self.speed = speed
        self.move_target = None

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        xp = self.unit.experience_points
        if xp > 0:
            effective_speed = self.speed * self.unit.xp_multiplier(XP_SPEED_BONUS)
            bonus_pct = int((effective_speed / self.speed - 1.0) * 100) if self.speed else 0
            speed_text = f"Speed: {self.speed} (+{bonus_pct}% XP → {effective_speed:.1f})"
        else:
            speed_text = f"Speed: {self.speed}"
        data.append({'type': 'label', 'text': speed_text, 'object_id': '#sidebar_info_label', 'height': 20})
        return data

@dataclasses.dataclass
class Hyperdrive(UnitComponent):
    """Hyperdrive for faster-than-light travel - inter-sector (basic) or inter-system through wormholes (advanced). """
    DISPLAY_NAME: str = "Hyperdrive"
    SIDEBAR_ORDER: int = 3
    drive_type: HyperdriveType = HyperdriveType.BASIC
    jump_range: int = DEFAULT_JUMP_RANGE
    hex_jump_target: typing.Optional[Tuple[HexCoord, Position]] = None
    wormhole_jump_target: typing.Optional['Wormhole'] = None
    jump_status: JumpStatus = JumpStatus.READY
    recharge_time_remaining: int = 0
    RECHARGE_DURATION: int = DEFAULT_HYPERDRIVE_RECHARGE_DURATION

    def __init__(self, unit: 'Unit', drive_type: HyperdriveType = HyperdriveType.BASIC, hull_cost: Optional[int] = None, recharge_duration: int = DEFAULT_HYPERDRIVE_RECHARGE_DURATION, jump_range: int = DEFAULT_JUMP_RANGE):
        if hull_cost is None:
            hull_cost = 5 if drive_type == HyperdriveType.BASIC else 10
        super().__init__(unit, hull_cost=hull_cost)
        self.drive_type = drive_type
        self.jump_range = jump_range
        self.hex_jump_target = None
        self.wormhole_jump_target = None
        self.jump_status = JumpStatus.READY
        self.recharge_time_remaining = 0
        self.RECHARGE_DURATION = recharge_duration

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        drive_type_str = self.drive_type.value if self.drive_type else 'N/A'
        
        status_detail = ""
        if self.jump_status == JumpStatus.CHARGING:
            status_detail = f"Charging: {self.recharge_time_remaining} turns"
        elif self.jump_status == JumpStatus.JUMPING:
            status_detail = "Jumping"
        elif self.jump_status == JumpStatus.READY:
            status_detail = "Ready"
        elif self.jump_status == JumpStatus.ERROR:
            status_detail = "Error"

        data.append({'type': 'label', 'text': f"Type: {drive_type_str}  Status: {status_detail}", 'object_id': '#sidebar_info_label', 'height': 20})

        xp = self.unit.experience_points
        if xp > 0:
            effective_range = int(self.jump_range * self.unit.xp_multiplier(XP_JUMP_RANGE_BONUS))
            bonus_pct = int((effective_range / self.jump_range - 1.0) * 100) if self.jump_range else 0
            range_text = f"Jump Range: {self.jump_range} (+{bonus_pct}% XP → {effective_range})"
        else:
            range_text = f"Jump Range: {self.jump_range}"
        data.append({'type': 'label', 'text': range_text, 'object_id': '#sidebar_info_label', 'height': 20})
        return data

    def start_recharge(self) -> None:
        """Initiates the hyperdrive recharge sequence."""
        self.jump_status = JumpStatus.CHARGING
        self.recharge_time_remaining = self.RECHARGE_DURATION
        self.hex_jump_target = None
        self.wormhole_jump_target = None
        logger.debug(f"Unit {self.unit.name} (id:{self.unit.id}) hyperdrive starting recharge for {self.RECHARGE_DURATION} turns. Status: CHARGING.")

    def update_recharge(self) -> None:
        """Updates the recharge status of the hyperdrive. Called each turn."""
        if self.jump_status == JumpStatus.CHARGING and self.recharge_time_remaining > 0:
            self.recharge_time_remaining -= 1
            if self.recharge_time_remaining <= 0:
                self.jump_status = JumpStatus.READY
                self.recharge_time_remaining = 0
                logger.debug(f"Unit {self.unit.name} (id:{self.unit.id}) hyperdrive recharged. Status: READY.")

@dataclasses.dataclass
class HyperspaceInhibitionFieldEmitter(UnitComponent):
    """A component that generates a hyperspace inhibition field, preventing jumps."""
    DISPLAY_NAME: str = "Inhibitor"
    SIDEBAR_ORDER: int = 4
    radius: float = 50.0
    is_active: bool = False

    def __init__(self, unit: 'Unit', radius: float = 50.0, hull_cost: int = 20):
        super().__init__(unit, hull_cost=hull_cost)
        self.radius = radius
        self.is_active = False

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        data.append({
            'type': 'inhibitor_button',
            'is_active': self.is_active,
            'height': 30
        })
        return data

    def turn_on(self) -> None:
        """Activates the inhibition field. (Validation logic will be handled by the order)."""
        if self.is_destroyed:
            return
        # In the future, an order will perform validation before setting this.
        self.is_active = True
        logger.debug(f"Unit {self.unit.name} inhibition field activated.")

    def turn_off(self) -> None:
        """Deactivates the inhibition field."""
        self.is_active = False
        logger.debug(f"Unit {self.unit.name} inhibition field deactivated.")

    def on_destroyed(self) -> None:
        if self.is_active:
            galaxy_ref = getattr(self.unit, 'in_galaxy', None)
            if galaxy_ref and self.unit.in_system and self.unit.in_hex:
                current_hex = galaxy_ref.systems[self.unit.in_system].hexes.get(self.unit.in_hex)
                if current_hex and self.unit.id in current_hex.dynamic_inhibition_zones:
                    del current_hex.dynamic_inhibition_zones[self.unit.id]
            self.turn_off()

    def toggle(self, galaxy_ref: 'Galaxy') -> bool:
        """
        Directly toggles the hyperspace inhibition field on or off, performing
        all necessary spatial and game-logic validation before applying the state change.

        When turning ON, the method validates that:
        1. The proposed field (a circle based on the emitter's radius) is fully
           contained within the boundaries of the current sector (hex).
        2. The proposed field does not overlap with any existing inhibition zones
           in the current sector.
        
        If validation passes, it updates both the component's internal state and
        registers the dynamic inhibition zone within the current hex. When turning OFF,
        it cleans up the registered zone.

        Args:
            galaxy_ref ('Galaxy'): A reference to the main galaxy object, used to
                                   access the current star system and hex grid data.

        Returns:
            bool: True if the toggle operation was successful and applied. False if
                  the toggle failed due to validation errors (e.g., crossing a sector
                  boundary or overlapping with another field), or if the unit's
                  location data is invalid.
        """
        from geometry import Circle, is_circle_contained, do_circles_intersect

        if not galaxy_ref or not self.unit.in_system or self.unit.in_hex is None:
            return False

        if self.is_destroyed:
            return False

        current_hex = galaxy_ref.systems[self.unit.in_system].hexes[self.unit.in_hex]
        
        if self.is_active:
            # Deactivate the field and clean up spatial registration.
            if self.unit.id in current_hex.dynamic_inhibition_zones:
                del current_hex.dynamic_inhibition_zones[self.unit.id]
            self.turn_off()
            return True
        else:
            # Activate the field after checking sector boundaries and overlap constraints.
            proposed_field = Circle(center=self.unit.position, radius=self.radius)

            if not is_circle_contained(proposed_field, current_hex.boundary_circle):
                logger.debug(f"[{self.unit.name}] TOGGLE_INHIBITOR (Direct): FAILED (field would cross sector boundary).")
                return False

            for existing_zone in current_hex.get_all_inhibition_zones():
                if do_circles_intersect(proposed_field, existing_zone):
                    logger.debug(f"[{self.unit.name}] TOGGLE_INHIBITOR (Direct): FAILED (field would overlap with another).")
                    return False
            
            self.turn_on()
            current_hex.dynamic_inhibition_zones[self.unit.id] = proposed_field
            return True

@dataclasses.dataclass
class Commander(UnitComponent):
    """Commander is a component responsible for managing and executing orders for a Unit.

    This component maintains a queue of orders and processes them in sequence,
    handling the execution and status updates of each order.
    """
    DISPLAY_NAME: str = "Commander"
    SIDEBAR_ORDER: int = 0
    current_order: Optional[Order] = None
    orders_queue: Deque[Order] = dataclasses.field(default_factory=deque)

    def __init__(self, unit: 'Unit'):
        super().__init__(unit, hull_cost=0)
        self.current_order = None
        self.orders_queue = deque()

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = []
        # Display Current Order (always visible if exists)
        current_order = self.current_order
        if current_order:
            data.append({
                'type': 'label', 
                'text': "Current Order:", 
                'object_id': '#sidebar_section_header_label', 
                'height': 25,
                'indent_level': 0
            })

            current_order_html = game_state._generate_order_data_recursive(current_order, 0)
            data.append({
                'type': 'text_box',
                'html_text': current_order_html,
                'height': 120,
                'object_id': '#order_text_box'
            })
        else:
            data.append({'type': 'label', 'text': "Current Order: None", 'object_id': '#sidebar_info_label', 'height': 20, 'indent_level': 0})

        # Queued Orders Section Header
        data.append({'type': 'label', 'text': "Queued Orders", 'object_id': '#sidebar_section_header_label', 'height': 28, 'indent_level': 0})
    
        queued_order_count = len(self.orders_queue)
        section_key = f"{self.unit.id}_orders_queue" 
        is_queue_expanded = game_state.gui.is_section_expanded(section_key)
        button_text = "[-] Queued" if is_queue_expanded else "[+] Queued"
    
        data.append({
            'type': 'button', 
            'text': f"{button_text} ({queued_order_count})", 
            'object_id': '#sidebar_expand_button',
            'action_id': 'toggle_orders_queue', 
            'target_data': self.unit.id, 
            'height': 25,
            'indent_level': 0 
        })

        if is_queue_expanded:
            queued_orders_html = ""
            if queued_order_count == 0:
                queued_orders_html = "No queued orders"
            else:
                for i, queued_top_order in enumerate(self.orders_queue):
                    queued_orders_html += f"<b>{i+1}.</b> "
                    queued_orders_html += game_state._generate_order_data_recursive(queued_top_order, 0)
            
            data.append({
                'type': 'text_box',
                'html_text': queued_orders_html,
                'height': 150,
                'object_id': '#order_text_box',
                'indent_level': 1
            })
        return data

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
            logger.debug(f"Error: [{unit_name}] Commander Component UPDATE: Cannot update order, unit.in_galaxy is None.")
            if self.current_order.status == OrderStatus.IN_PROGRESS:
                 self.current_order.status = OrderStatus.FAILED

        if not self.current_order:
            return

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
                logger.debug(f"Error: [{unit_name}] Commander Component START_NEXT_ORDER: Cannot execute order, unit.in_galaxy is None.")
                if self.current_order:
                    self.current_order.status = OrderStatus.FAILED

# --- Ability System Enums & Data ---

class AbilityType(Enum):
    ADAPTIVE_FORCEFIELD = "adaptive_forcefield"
    CLUSTER_WARHEAD = "cluster_warhead"
    DESIGNATE_TARGET = "designate_target"
    ION_BOLT = "ion_bolt"
    MISSILE_BATTERIES = "missile_batteries"
    REPAIR_CLOUD = "repair_cloud"


@dataclasses.dataclass
class AbilityDefinition:
    """Static definition of an ability's properties (shared across all units)."""
    ability_type: AbilityType
    name: str
    description: str
    cooldown: int            # Turns before the ability can be used again
    duration: int            # Turns the effect persists (0 = instant / one-shot)
    range: float             # Max targeting distance in logical units (0 = self only)
    requires_target_unit: bool       # True if the ability needs a unit to be selected
    requires_target_position: bool   # True if the ability needs a position click


# Registry of all ability definitions. Tuned values live here.
ABILITY_DEFINITIONS: typing.Dict['AbilityType', 'AbilityDefinition'] = {
    AbilityType.ADAPTIVE_FORCEFIELD: AbilityDefinition(
        ability_type=AbilityType.ADAPTIVE_FORCEFIELD,
        name="Adaptive Forcefield",
        description="Reduces incoming damage by 75% for 3 turns.",
        cooldown=8,
        duration=3,
        range=0.0,
        requires_target_unit=False,
        requires_target_position=False,
    ),
    AbilityType.CLUSTER_WARHEAD: AbilityDefinition(
        ability_type=AbilityType.CLUSTER_WARHEAD,
        name="Cluster Warhead",
        description="Fires a missile that deals heavy splash damage at a target position.",
        cooldown=5,
        duration=0,
        range=500.0,
        requires_target_unit=False,
        requires_target_position=True,
    ),
    AbilityType.DESIGNATE_TARGET: AbilityDefinition(
        ability_type=AbilityType.DESIGNATE_TARGET,
        name="Designate Target",
        description="Marks an enemy unit. Friendly units deal +50% damage against it for 4 turns.",
        cooldown=6,
        duration=4,
        range=450.0,
        requires_target_unit=True,
        requires_target_position=False,
    ),
    AbilityType.ION_BOLT: AbilityDefinition(
        ability_type=AbilityType.ION_BOLT,
        name="Ion Bolt",
        description="Disables a target unit, preventing movement and attacks for 3 turns.",
        cooldown=7,
        duration=3,
        range=400.0,
        requires_target_unit=True,
        requires_target_position=False,
    ),
    AbilityType.MISSILE_BATTERIES: AbilityDefinition(
        ability_type=AbilityType.MISSILE_BATTERIES,
        name="Missile Batteries",
        description="Deploys 3 missile platforms that automatically attack enemies for 4 turns.",
        cooldown=10,
        duration=4,
        range=0.0,
        requires_target_unit=False,
        requires_target_position=False,
    ),
    AbilityType.REPAIR_CLOUD: AbilityDefinition(
        ability_type=AbilityType.REPAIR_CLOUD,
        name="Repair Cloud",
        description="Disperses repair nanites that restore 5 HP per turn to all friendly ships within 350 units for 4 turns.",
        cooldown=8,
        duration=4,
        range=350.0,
        requires_target_unit=False,
        requires_target_position=False,
    ),
}


# --- Enums for Weapons Component ---

class TurretType(Enum):
    MASS_DRIVER = "mass_driver"
    BEAM = "beam"
    MISSILE = "missile"

class TurretVariant(Enum):
    STANDARD = "standard"
    LONG_RANGE = "long_range"
    ANTI_STRIKECRAFT = "anti_strikecraft"

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
    variant: TurretVariant = TurretVariant.STANDARD
    current_cooldown: int = 0
    target: Optional['Unit'] = None
    target_component_type: Optional[type] = None

    def __post_init__(self) -> None:
        if self.variant == TurretVariant.LONG_RANGE:
            self.range *= 3.0
            self.cooldown *= 3

    def fire(self) -> None:
        """
        Fires at the turret's current target and resets the cooldown.
        Damage is amplified if the target is marked by Designate Target.
        The parent unit earns XP equal to the actual damage dealt.
        """
        if self.target:
            # Apply damage amplification from Designate Target (stacks additively)
            effective_damage = self.damage
            if self.target.damage_amplification > 0.0:
                effective_damage = self.damage * (1.0 + self.target.damage_amplification)

            # Apply XP weapon damage bonus from the firing unit
            effective_damage *= self.parent_unit.xp_multiplier(XP_WEAPON_DAMAGE_BONUS)

            # Anti-strikecraft damage reduced to 25% against other targets
            if self.variant == TurretVariant.ANTI_STRIKECRAFT and self.target.hull_size != HullSize.STRIKECRAFT_WING:
                effective_damage *= 0.25

            # Record target HP before damage to compute actual damage dealt for XP
            hp_before = self.target.current_hit_points

            if self.target_component_type:
                logger.debug(f"Turret {self.turret_type.name} from {self.parent_unit.name} firing at {self.target.name}'s {self.target_component_type.__name__}! (effective dmg: {effective_damage:.1f})")
                spillover = self.target.take_component_damage(self.target_component_type, int(effective_damage), damage_type=self.turret_type)
                if spillover > 0:
                    self.target.take_damage(spillover)
            else:
                logger.debug(f"Turret {self.turret_type.name} from {self.parent_unit.name} firing at {self.target.name}! (effective dmg: {effective_damage:.1f})")
                self.target.take_damage(int(effective_damage), damage_type=self.turret_type)

            # Award XP based on actual HP lost (overkill damage does not grant bonus XP)
            xp_earned = max(0, hp_before - self.target.current_hit_points)
            if xp_earned > 0:
                self.parent_unit.gain_experience(xp_earned)

        self.current_cooldown = self.cooldown

    def update(self) -> None:
        """
        Updates the turret's state, primarily its cooldown.
        """
        if self.current_cooldown > 0:
            self.current_cooldown -= 1

# --- Weapons Component ---

class Weapons(UnitComponent):
    """
    Manages all weapon systems for a unit.
    """
    DISPLAY_NAME: str = "Weapons"
    SIDEBAR_ORDER: int = 1
    turrets: list[Turret] = dataclasses.field(default_factory=list)

    def __init__(self, unit: 'Unit', hull_cost: int = 0):
        super().__init__(unit, hull_cost=hull_cost)
        self.turrets = []

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        xp = self.unit.experience_points
        xp_dmg_mult = self.unit.xp_multiplier(XP_WEAPON_DAMAGE_BONUS)
        for i, turret in enumerate(self.turrets):
            if i > 0:
                # Add a small vertical space between turrets
                data.append({
                    'type': 'label',
                    'text': '',
                    'object_id': '#sidebar_info_label',
                    'height': 5,
                    'indent_level': 1
                })
            
            variant_str = turret.variant.name.replace('_', ' ').title()
            type_str = turret.turret_type.name.replace('_', ' ').title()
            
            header_text = f"• Turret {i + 1}: {variant_str} {type_str}"
            data.append({
                'type': 'label',
                'text': header_text,
                'object_id': '#sidebar_info_label',
                'height': 20,
                'indent_level': 1
            })
            
            if xp > 0:
                effective_dmg = turret.damage * xp_dmg_mult
                bonus_pct = int((xp_dmg_mult - 1.0) * 100)
                stats_text = f"Damage: {turret.damage} (+{bonus_pct}% XP → {effective_dmg:.1f}) | Range: {turret.range} | Cooldown: {turret.cooldown}t"
            else:
                stats_text = f"Damage: {turret.damage} | Range: {turret.range} | Cooldown: {turret.cooldown}t"
            data.append({
                'type': 'label',
                'text': stats_text,
                'object_id': '#sidebar_info_label',
                'height': 18,
                'indent_level': 2
            })
            
            cooldown_status = f"On Cooldown ({turret.current_cooldown}t)" if turret.current_cooldown > 0 else "Ready"
            
            target_str = "None"
            if turret.target:
                if turret.target_component_type:
                    comp_name = getattr(turret.target_component_type, 'DISPLAY_NAME', turret.target_component_type.__name__)
                    target_str = f"{turret.target.name} ({comp_name})"
                else:
                    target_str = f"{turret.target.name} (Hull)"
                    
            status_text = f"Status: {cooldown_status} | Target: {target_str}"
            data.append({
                'type': 'label',
                'text': status_text,
                'object_id': '#sidebar_info_label',
                'height': 18,
                'indent_level': 2
            })
        return data

    def add_turret(self, turret: Turret) -> None:
        """
        Adds a pre-configured turret to the unit.
        """
        self.turrets.append(turret)

    def update(self, galaxy: 'Galaxy') -> None:
        """
        Updates all turrets and fires if a target is set and is in the same system, hex, in range and the cooldown is over.
        """
        if self.is_destroyed:
            return

        for turret in self.turrets:
            turret.update()

        for turret in self.turrets:
            if turret.target:
                if turret.target.current_hit_points <= 0:
                    turret.target = None
                    turret.target_component_type = None
                    continue

                target_in_same_system = self.unit.in_system == turret.target.in_system
                target_in_same_hex = self.unit.in_hex == turret.target.in_hex
                target_in_range = distance(self.unit.position, turret.target.position) < turret.range

                if target_in_same_system and target_in_same_hex and target_in_range:
                    if turret.current_cooldown <= 0:
                        turret.fire()

    def set_target(self, target_unit: 'Unit', target_component_type: Optional[type] = None) -> None:
        """Sets the target of the turrets to the specified unit and optionally a specific component."""
        for turret in self.turrets:
            if target_unit:
                # Standard and Long Range turrets cannot target strikecraft (strikecraft wings)
                if target_unit.hull_size == HullSize.STRIKECRAFT_WING and turret.variant != TurretVariant.ANTI_STRIKECRAFT:
                    continue

                # Attacker is a strikecraft wing:
                if self.unit.hull_size == HullSize.STRIKECRAFT_WING:
                    wing_comp = self.unit.strikecraft_wing_component
                    if wing_comp:
                        if wing_comp.wing_type == WingType.FIGHTER:
                            # Fighters can only attack strikecraft wings
                            if target_unit.hull_size != HullSize.STRIKECRAFT_WING:
                                continue
                        elif wing_comp.wing_type == WingType.BOMBER:
                            # Bombers can only attack non-strikecraft units
                            if target_unit.hull_size == HullSize.STRIKECRAFT_WING:
                                continue
            turret.target = target_unit
            turret.target_component_type = target_component_type
    
    def clear_target(self) -> None:
        """Clears the target of the turrets."""
        for turret in self.turrets:
            turret.target = None
            turret.target_component_type = None


@dataclasses.dataclass
class Defenses(UnitComponent):
    """
    Provides protection against incoming attacks.
    - Armor reduces mass driver damage.
    - Shields reduce beam damage.
    - Point defense cannons reduce missile damage.
    """
    DISPLAY_NAME: str = "Defenses"
    SIDEBAR_ORDER: int = 4
    armor: int = 0
    shields: int = 0
    point_defense: int = 0

    def __init__(self, unit: 'Unit', armor: int = 0, shields: int = 0, point_defense: int = 0, hull_cost: int = 0):
        super().__init__(unit, hull_cost=hull_cost)
        self.armor = armor
        self.shields = shields
        self.point_defense = point_defense

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        xp = self.unit.experience_points
        if xp > 0:
            mult = self.unit.xp_multiplier(XP_DEFENSE_BONUS)
            bonus_pct = int((mult - 1.0) * 100)
            def fmt(val: int) -> str:
                return f"{val} (+{bonus_pct}% XP)"
        else:
            def fmt(val: int) -> str:
                return str(val)
        data.append({'type': 'label', 'text': f"Armor: {fmt(self.armor)}", 'object_id': '#sidebar_info_label', 'height': 20})
        data.append({'type': 'label', 'text': f"Shields: {fmt(self.shields)}", 'object_id': '#sidebar_info_label', 'height': 20})
        data.append({'type': 'label', 'text': f"Point Defense: {fmt(self.point_defense)}", 'object_id': '#sidebar_info_label', 'height': 20})
        return data

    def calculate_mitigation(self, incoming_damage: int, damage_type: Optional[TurretType]) -> int:
        if self.is_destroyed or damage_type is None:
            return 0

        mitigation = 0
        if damage_type == TurretType.MASS_DRIVER:
            mitigation += random.randint(0, self.armor)
            mitigation += random.randint(0, int(math.sqrt(self.shields)))
            mitigation += random.randint(0, int(math.sqrt(self.point_defense)))
        elif damage_type == TurretType.BEAM:
            mitigation += random.randint(0, self.shields)
            mitigation += random.randint(0, int(math.sqrt(self.armor)))
            mitigation += random.randint(0, int(math.sqrt(self.point_defense)))
        elif damage_type == TurretType.MISSILE:
            mitigation += random.randint(0, self.point_defense)
            mitigation += random.randint(0, int(math.sqrt(self.armor)))
            mitigation += random.randint(0, int(math.sqrt(self.shields)))

        # Apply XP defense bonus: veteran units are more effective at blocking damage
        mitigation = int(mitigation * self.unit.xp_multiplier(XP_DEFENSE_BONUS))

        return min(incoming_damage, mitigation)


class RepairComponent(UnitComponent):
    """A component that allows a unit to repair damaged friendly units."""
    DISPLAY_NAME: str = "Repair"
    SIDEBAR_ORDER: int = 10
    repair_rate: float = 10.0
    repair_range: float = 200.0
    credit_cost_per_hp: float = 1.0
    target: Optional['Unit'] = None

    def __init__(self, unit: 'Unit', repair_rate: float = 10.0, repair_range: float = 200.0, credit_cost_per_hp: float = 1.0, hull_cost: int = 15):
        super().__init__(unit, hull_cost=hull_cost)
        self.repair_rate = repair_rate
        self.repair_range = repair_range
        self.credit_cost_per_hp = credit_cost_per_hp
        self.target = None

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        data.append({'type': 'label', 'text': f"Repair Rate: {self.repair_rate} HP/turn", 'object_id': '#sidebar_info_label', 'height': 20})
        data.append({'type': 'label', 'text': f"Repair Range: {self.repair_range}", 'object_id': '#sidebar_info_label', 'height': 20})
        target_name = self.target.name if self.target else "None"
        data.append({'type': 'label', 'text': f"Repair Target: {target_name}", 'object_id': '#sidebar_info_label', 'height': 20})
        return data

    def set_target(self, target_unit: 'Unit') -> None:
        self.target = target_unit

    def clear_target(self) -> None:
        self.target = None

    def update(self, galaxy: 'Galaxy') -> None:
        if self.is_destroyed:
            return

        if not self.target:
            return

        target_valid = (
            self.target.current_hit_points > 0 and
            self.target.owner == self.unit.owner and
            self.unit.in_system == self.target.in_system and
            self.unit.in_hex == self.target.in_hex and
            distance(self.unit.position, self.target.position) <= self.repair_range
        )

        if not target_valid:
            return

        needs_hull_repair = self.target.current_hit_points < self.target.max_hit_points
        damaged_components = [c for c in self.target.components.values() if c.current_hit_points < c.max_hit_points]

        if not needs_hull_repair and not damaged_components:
            return

        player = self.unit.owner
        if player.credits <= 0:
            logger.debug(f"Repair by {self.unit.name} on {self.target.name} halted due to insufficient credits.")
            return

        max_hp_to_repair = min(self.repair_rate, player.credits / self.credit_cost_per_hp)
        if max_hp_to_repair < 1.0:
            return

        repair_budget = int(max_hp_to_repair)
        hp_repaired = 0

        if needs_hull_repair:
            healed = self.target.heal_hull(repair_budget)
            hp_repaired += healed
            repair_budget -= healed

        if repair_budget > 0 and damaged_components:
            healed = self.target.heal_components(repair_budget)
            hp_repaired += healed
            repair_budget -= healed

        if hp_repaired > 0:
            cost = int(hp_repaired * self.credit_cost_per_hp)
            player.credits = max(0, player.credits - cost)
            logger.debug(f"Unit {self.unit.name} repaired {self.target.name} for {hp_repaired} HP, costing {cost} credits.")


class ColonyComponent(UnitComponent):
    """A component that allows a unit to transport population and colonize planets."""
    DISPLAY_NAME: str = "Colony"
    SIDEBAR_ORDER: int = 6
    population_cargo: int = 0
    max_cargo: int = 100

    def __init__(self, unit: 'Unit', hull_cost: int = 10):
        super().__init__(unit, hull_cost=hull_cost)
        self.population_cargo = 0
        self.max_cargo = 100

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        data.append({'type': 'label', 'text': f"Population Cargo: {self.population_cargo} / {self.max_cargo}", 'object_id': '#sidebar_info_label', 'height': 20})
        return data

    def load_population(self, planet: 'Planet', amount: int) -> bool:
        if self.is_destroyed:
            logger.debug(f"Error: Cannot load population, {self.unit.name}'s ColonyComponent is destroyed.")
            return False
        if planet.owner != self.unit.owner:
            logger.debug(f"Error: Cannot load population from unowned planet {planet.name}.")
            return False
        if planet.population < amount:
            logger.debug(f"Error: Not enough population on {planet.name} to load {amount}.")
            return False
        if self.population_cargo + amount > self.max_cargo:
            logger.debug(f"Error: Not enough cargo space to load {amount} population.")
            return False
        
        planet.population -= amount
        self.population_cargo += amount
        logger.debug(f"Loaded {amount} population from {planet.name}. Current cargo: {self.population_cargo}")
        return True

    def unload_population(self, planet: 'Planet', amount: int) -> bool:
        if self.is_destroyed:
            logger.debug(f"Error: Cannot unload population, {self.unit.name}'s ColonyComponent is destroyed.")
            return False
        if self.population_cargo < amount:
            logger.debug(f"Error: Not enough population in cargo to unload {amount}.")
            return False

        if planet.owner is None:
            planet.owner = self.unit.owner
            logger.debug(f"Planet {planet.name} has been colonized by {self.unit.owner.name}.")

        if planet.owner != self.unit.owner:
            logger.debug(f"Error: Cannot unload population on planet owned by another player.")
            return False

        planet.population += amount
        self.population_cargo -= amount
        logger.debug(f"Unloaded {amount} population onto {planet.name}. Current cargo: {self.population_cargo}")
        return True

class MiningComponent(UnitComponent):
    """A component that allows a unit to extract raw resources from celestial bodies."""
    DISPLAY_NAME: str = "Mining"
    SIDEBAR_ORDER: int = 7
    mining_rate: float = 10.0
    mining_range: float = 200.0
    raw_metal_cargo: float = 0.0
    raw_crystal_cargo: float = 0.0
    max_cargo: float = 100.0
    mining_target: Optional['CelestialBody'] = None

    def __init__(self, unit: 'Unit', mining_rate: float = 10.0, mining_range: float = 200.0, max_cargo: float = 100.0, hull_cost: int = 10):
        super().__init__(unit, hull_cost=hull_cost)
        self.mining_rate = mining_rate
        self.mining_range = mining_range
        self.raw_metal_cargo = 0.0
        self.raw_crystal_cargo = 0.0
        self.max_cargo = max_cargo
        self.mining_target = None

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        metal = int(self.raw_metal_cargo)
        crystal = int(self.raw_crystal_cargo)
        max_c = int(self.max_cargo)
        data.append({'type': 'label', 'text': f"Raw Cargo: {metal} Metal, {crystal} Crystal / {max_c}", 'object_id': '#sidebar_info_label', 'height': 20})
        if self.raw_metal_cargo > 0 or self.raw_crystal_cargo > 0:
            data.append({
                'type': 'button',
                'text': "Unload to Nearest Refinery",
                'object_id': '#sidebar_expand_button',
                'action_id': 'unload_resources_nearest',
                'target_data': self.unit.id,
                'height': 25
            })
        if self.mining_target:
            data.append({'type': 'label', 'text': f"Mining Target: {self.mining_target.name}", 'object_id': '#sidebar_info_label', 'height': 20})
        return data

    def set_target(self, target: 'CelestialBody') -> None:
        self.mining_target = target

    def clear_target(self) -> None:
        self.mining_target = None

    def get_cargo_fullness(self) -> float:
        """Returns the percentage of cargo that is full (0.0 to 1.0)."""
        total_cargo = self.raw_metal_cargo + self.raw_crystal_cargo
        if self.max_cargo <= 0:
            return 1.0
        return min(1.0, total_cargo / self.max_cargo)

    def update(self, galaxy: 'Galaxy') -> None:
        if self.is_destroyed:
            return

        if not self.mining_target:
            return

        # Need to be in same system and hex
        if self.unit.in_system != self.mining_target.in_system or self.unit.in_hex != self.mining_target.in_hex:
            return

        # Need to be within range
        if distance(self.unit.position, self.mining_target.position) > self.mining_range:
            return

        total_cargo = self.raw_metal_cargo + self.raw_crystal_cargo
        if total_cargo >= self.max_cargo:
            return

        available_space = self.max_cargo - total_cargo
        amount_to_mine = min(self.mining_rate, available_space)

        from entities import Asteroid, AsteroidField, Moon
        if isinstance(self.mining_target, (Asteroid, AsteroidField)):
            # Infinite yield: we extract mining_rate without depleting the asteroid
            self.raw_metal_cargo += amount_to_mine
            logger.debug(f"{self.unit.name} mined {amount_to_mine} raw metal from {self.mining_target.name}. Cargo: {self.raw_metal_cargo}/{self.max_cargo}")
        elif isinstance(self.mining_target, Moon):
            # Infinite yield: we extract mining_rate without depleting the moon
            self.raw_crystal_cargo += amount_to_mine
            logger.debug(f"{self.unit.name} mined {amount_to_mine} raw crystal from {self.mining_target.name}. Cargo: {self.raw_crystal_cargo}/{self.max_cargo}")

    def unload_to_refinery(self, unload_metal: bool = True, unload_crystal: bool = True) -> tuple[float, float]:
        """Empties cargo and returns a tuple of (metal_amount, crystal_amount) unloaded."""
        metal_amount = self.raw_metal_cargo if unload_metal else 0.0
        crystal_amount = self.raw_crystal_cargo if unload_crystal else 0.0
        if unload_metal:
            self.raw_metal_cargo = 0.0
        if unload_crystal:
            self.raw_crystal_cargo = 0.0
        return metal_amount, crystal_amount


class MetalRefineryComponent(UnitComponent):
    """A component that instantly converts raw metal into player metal upon delivery."""
    DISPLAY_NAME: str = "Metal Refinery"
    SIDEBAR_ORDER: int = 8
    unload_range: float = 300.0

    def __init__(self, unit: 'Unit', unload_range: float = 300.0, hull_cost: int = 20):
        super().__init__(unit, hull_cost=hull_cost)
        self.unload_range = unload_range

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        data.append({'type': 'label', 'text': "Metal Refinery Active", 'object_id': '#sidebar_info_label', 'height': 20})
        return data

    def accept_resources(self, amount: float) -> None:
        if self.is_destroyed:
            return
        if self.unit.owner:
            self.unit.owner.metal += amount
            logger.debug(f"{self.unit.name} refined {amount} raw metal instantly for {self.unit.owner.name}.")


class CrystalRefineryComponent(UnitComponent):
    """A component that instantly converts raw crystal into player crystal upon delivery."""
    DISPLAY_NAME: str = "Crystal Refinery"
    SIDEBAR_ORDER: int = 9
    unload_range: float = 300.0

    def __init__(self, unit: 'Unit', unload_range: float = 300.0, hull_cost: int = 20):
        super().__init__(unit, hull_cost=hull_cost)
        self.unload_range = unload_range

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        data.append({'type': 'label', 'text': "Crystal Refinery Active", 'object_id': '#sidebar_info_label', 'height': 20})
        return data

    def accept_resources(self, amount: float) -> None:
        if self.is_destroyed:
            return
        if self.unit.owner:
            self.unit.owner.crystal += amount
            logger.debug(f"{self.unit.name} refined {amount} raw crystal instantly for {self.unit.owner.name}.")


class HangarComponent(UnitComponent):
    """A component that allows a unit to store and transport smaller units."""
    DISPLAY_NAME: str = "Hangar"
    SIDEBAR_ORDER: int = 11
    max_slots: int = 0
    docked_units: list['Unit'] = dataclasses.field(default_factory=list)

    def __init__(self, unit: 'Unit', max_slots: int = 0, hull_cost: int = 0):
        super().__init__(unit, hull_cost=hull_cost)
        self.max_slots = max_slots
        self.docked_units = []

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        used_slots = self.get_used_slots()
        data.append({'type': 'label', 'text': f"Capacity: {used_slots} / {self.max_slots} slots", 'object_id': '#sidebar_info_label', 'height': 20})
        data.append({'type': 'label', 'text': "Docked Ships:", 'object_id': '#sidebar_section_header_label', 'height': 24})
        if not self.docked_units:
            data.append({'type': 'label', 'text': "  None", 'object_id': '#sidebar_info_label', 'height': 20})
        else:
            for docked_ship in self.docked_units:
                size_slots = 1 if docked_ship.hull_size == HullSize.TINY else 2
                ship_label = f"  - {docked_ship.name} ({size_slots} slot)" if size_slots == 1 else f"  - {docked_ship.name} ({size_slots} slots)"
                data.append({'type': 'label', 'text': ship_label, 'object_id': '#sidebar_info_label', 'height': 20})
                data.append({
                    'type': 'button',
                    'text': f"Deploy {docked_ship.name}",
                    'object_id': '#sidebar_expand_button',
                    'action_id': 'deploy_ship',
                    'target_data': (self.unit.id, docked_ship.id),
                    'height': 25
                })
        return data

    def get_used_slots(self) -> int:
        slots = 0
        for u in self.docked_units:
            if u.hull_size == HullSize.TINY:
                slots += 1
            elif u.hull_size == HullSize.SMALL:
                slots += 2
        return slots

    def can_dock(self, unit: 'Unit') -> bool:
        if unit.hull_size != HullSize.TINY:
            return False
        needed = 1
        return self.get_used_slots() + needed <= self.max_slots

    def dock(self, unit: 'Unit', galaxy_ref: 'Galaxy') -> bool:
        if not self.can_dock(unit):
            return False
        
        # Remove from system
        if unit.in_system and unit.in_hex is not None:
            system = galaxy_ref.systems.get(unit.in_system)
            if system:
                system.remove_unit(unit)
        
        unit.in_system = self.unit.in_system
        unit.in_hex = self.unit.in_hex
        unit.position = Position(self.unit.position.x, self.unit.position.y)
        
        self.docked_units.append(unit)
        if unit.commander_component:
            unit.commander_component.clear_orders()
            
        logger.debug(f"Unit {unit.name} docked into carrier {self.unit.name}.")
        return True

    def deploy(self, unit: 'Unit', galaxy_ref: 'Galaxy') -> bool:
        if unit not in self.docked_units:
            return False
        
        unit.in_system = self.unit.in_system
        unit.in_hex = self.unit.in_hex
        
        while True:
            angle = random.uniform(0, 2 * math.pi)
            offset_dist = random.uniform(20.0, 50.0)
            candidate_x = self.unit.position.x + math.cos(angle) * offset_dist
            candidate_y = self.unit.position.y + math.sin(angle) * offset_dist
            
            if self.unit.in_system is None:
                if math.hypot(candidate_x, candidate_y) <= SECTOR_CIRCLE_RADIUS_LOGICAL:
                    unit.position = Position(candidate_x, candidate_y)
                    break
            else:
                unit.position = Position(candidate_x, candidate_y)
                break
        
        system = galaxy_ref.systems.get(unit.in_system)
        if system:
            system.add_unit(unit)
            
        self.docked_units.remove(unit)
        logger.debug(f"Unit {unit.name} deployed from carrier {self.unit.name}.")
        return True


class WingType(Enum):
    FIGHTER = "fighter"
    BOMBER = "bomber"


class StrikecraftWingComponent(UnitComponent):
    """A component specifically for STRIKECRAFT_WING (strikecraft wings) to track individual fighter counts."""
    DISPLAY_NAME: str = "Strikecraft Wing"
    SIDEBAR_ORDER: int = 13
    mother_carrier: typing.Optional['Unit'] = None

    def __init__(self, unit: 'Unit', wing_type: WingType = WingType.FIGHTER, hull_cost: int = 0):
        super().__init__(unit, hull_cost=hull_cost)
        self.mother_carrier = None
        self.wing_type: WingType = wing_type

    @property
    def active_fighters(self) -> int:
        if self.unit.current_hit_points <= 0:
            return 0
        return math.ceil((self.unit.current_hit_points / self.unit.max_hit_points) * 4)

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        role_str = "Fighter" if self.wing_type == WingType.FIGHTER else "Bomber"
        data.append({'type': 'label', 'text': f"Role: {role_str}", 'object_id': '#sidebar_info_label', 'height': 20})
        data.append({'type': 'label', 'text': f"Active Craft: {self.active_fighters} / 4", 'object_id': '#sidebar_info_label', 'height': 20})
        mother_name = self.mother_carrier.name if self.mother_carrier else "None"
        data.append({'type': 'label', 'text': f"Mother Carrier: {mother_name}", 'object_id': '#sidebar_info_label', 'height': 20})
        return data


class StrikecraftBayComponent(UnitComponent):
    """A component that allows a unit to store, transport, and automatically construct/replenish strikecraft wings."""
    DISPLAY_NAME: str = "Strikecraft Bay"
    SIDEBAR_ORDER: int = 12
    max_slots: int = 0
    docked_units: list['Unit'] = dataclasses.field(default_factory=list)
    launched_units: list['Unit'] = dataclasses.field(default_factory=list)
    
    # Auto-construction and replenishment state
    constructing: bool = False
    construction_progress: int = 0
    replenishing_unit: typing.Optional['Unit'] = None
    replenish_progress: int = 0
    build_wing_type: WingType = WingType.FIGHTER

    def __init__(self, unit: 'Unit', max_slots: int = 0, hull_cost: int = 0):
        super().__init__(unit, hull_cost=hull_cost)
        self.max_slots = max_slots
        self.docked_units = []
        self.launched_units = []
        self.constructing = False
        self.construction_progress = 0
        self.replenishing_unit = None
        self.replenish_progress = 0
        self.build_wing_type = WingType.FIGHTER

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        used_slots = self.get_used_slots()
        data.append({'type': 'label', 'text': f"Capacity: {used_slots} / {self.max_slots} wings", 'object_id': '#sidebar_info_label', 'height': 20})
        if self.constructing:
            role_text = "Fighter" if self.build_wing_type == WingType.FIGHTER else "Bomber"
            data.append({'type': 'label', 'text': f"Constructing {role_text} Wing ({self.construction_progress + 1}/2 turns)", 'object_id': '#sidebar_info_label', 'height': 20})
        elif self.replenishing_unit:
            data.append({'type': 'label', 'text': f"Replenishing Wing: {self.replenishing_unit.name}", 'object_id': '#sidebar_info_label', 'height': 20})
        
        is_owner = self.unit.owner == game_state.players[game_state.current_player_index]

        if is_owner:
            role_text = "Fighter" if self.build_wing_type == WingType.FIGHTER else "Bomber"
            data.append({
                'type': 'button',
                'text': f"Target Wing Build: {role_text}",
                'object_id': '#sidebar_expand_button',
                'action_id': 'toggle_build_wing_type',
                'target_data': self.unit.id,
                'height': 25
            })

        # Docked Wings
        data.append({'type': 'label', 'text': "Docked Strikecraft Wings:", 'object_id': '#sidebar_section_header_label', 'height': 24})
        if self.docked_units and is_owner:
            data.append({
                'type': 'button',
                'text': "Launch All Wings",
                'object_id': '#sidebar_expand_button',
                'action_id': 'launch_all_wings',
                'target_data': self.unit.id,
                'height': 25
            })
        if not self.docked_units:
            data.append({'type': 'label', 'text': "  None", 'object_id': '#sidebar_info_label', 'height': 20})
        else:
            for docked_ship in self.docked_units:
                f_comp = docked_ship.strikecraft_wing_component
                f_count = f_comp.active_fighters if f_comp else 4
                role_str = f_comp.wing_type.value.capitalize() if f_comp else "Fighter"
                wing_label = f"  - {docked_ship.name} ({role_str}, {f_count}/4 craft, HP: {docked_ship.current_hit_points}/{docked_ship.max_hit_points})"
                data.append({'type': 'label', 'text': wing_label, 'object_id': '#sidebar_info_label', 'height': 20})
                if is_owner:
                    data.append({
                        'type': 'button',
                        'text': f"Deploy {docked_ship.name}",
                        'object_id': '#sidebar_expand_button',
                        'action_id': 'deploy_ship',
                        'target_data': (self.unit.id, docked_ship.id),
                        'height': 25
                    })

        # Launched Wings
        data.append({'type': 'label', 'text': "Launched Strikecraft Wings:", 'object_id': '#sidebar_section_header_label', 'height': 24})
        if not self.launched_units:
            data.append({'type': 'label', 'text': "  None", 'object_id': '#sidebar_info_label', 'height': 20})
        else:
            for launched_ship in self.launched_units:
                f_comp = launched_ship.strikecraft_wing_component
                f_count = f_comp.active_fighters if f_comp else 4
                role_str = f_comp.wing_type.value.capitalize() if f_comp else "Fighter"
                wing_label = f"  - {launched_ship.name} ({role_str}, {f_count}/4 craft, HP: {launched_ship.current_hit_points}/{launched_ship.max_hit_points})"
                data.append({'type': 'label', 'text': wing_label, 'object_id': '#sidebar_info_label', 'height': 20})
                if is_owner:
                    data.append({
                        'type': 'button',
                        'text': f"Recall {launched_ship.name}",
                        'object_id': '#sidebar_expand_button',
                        'action_id': 'recall_ship',
                        'target_data': (self.unit.id, launched_ship.id),
                        'height': 25
                    })
        return data

    def get_used_slots(self) -> int:
        return len(self.docked_units) + len(self.launched_units)

    def can_dock(self, unit: 'Unit') -> bool:
        if unit.hull_size != HullSize.STRIKECRAFT_WING:
            return False
        if unit in self.launched_units:
            return True
        return self.get_used_slots() < self.max_slots

    def dock(self, unit: 'Unit', galaxy_ref: 'Galaxy') -> bool:
        if not self.can_dock(unit):
            return False
        
        # Remove from system
        if unit.in_system and unit.in_hex is not None:
            system = galaxy_ref.systems.get(unit.in_system)
            if system:
                system.remove_unit(unit)
        
        unit.in_system = self.unit.in_system
        unit.in_hex = self.unit.in_hex
        unit.position = Position(self.unit.position.x, self.unit.position.y)
        
        if unit in self.launched_units:
            self.launched_units.remove(unit)
        
        # Orphaned wings are adopted
        if unit.strikecraft_wing_component:
            unit.strikecraft_wing_component.mother_carrier = self.unit
        
        self.docked_units.append(unit)
        if unit.commander_component:
            unit.commander_component.clear_orders()
            
        logger.debug(f"Strikecraft wing {unit.name} docked into carrier {self.unit.name}.")
        return True

    def deploy(self, unit: 'Unit', galaxy_ref: 'Galaxy') -> bool:
        if unit not in self.docked_units:
            return False
        
        unit.in_system = self.unit.in_system
        unit.in_hex = self.unit.in_hex
        
        while True:
            angle = random.uniform(0, 2 * math.pi)
            offset_dist = random.uniform(20.0, 50.0)
            candidate_x = self.unit.position.x + math.cos(angle) * offset_dist
            candidate_y = self.unit.position.y + math.sin(angle) * offset_dist
            
            if self.unit.in_system is None:
                if math.hypot(candidate_x, candidate_y) <= SECTOR_CIRCLE_RADIUS_LOGICAL:
                    unit.position = Position(candidate_x, candidate_y)
                    break
            else:
                unit.position = Position(candidate_x, candidate_y)
                break
        
        system = galaxy_ref.systems.get(unit.in_system)
        if system:
            system.add_unit(unit)
            
        self.docked_units.remove(unit)
        self.launched_units.append(unit)
        logger.debug(f"Strikecraft wing {unit.name} deployed from carrier {self.unit.name}.")
        return True

    def finish_auto_construction(self, galaxy: 'Galaxy'):
        """Creates the new Strikecraft Wing and docks it."""
        from entities import Unit # Avoid circular import
        from unit_templates import UNIT_TEMPLATES
        
        template_name = "FIGHTER_WING" if self.build_wing_type == WingType.FIGHTER else "BOMBER_WING"
        template = UNIT_TEMPLATES.get(template_name)
        if not template:
            logger.debug(f"Error: Unit template '{template_name}' not found for auto-construction.")
            return
 
        new_unit = Unit(
            owner=self.unit.owner,
            name=template["name"],
            hull_size=template["hull_size"],
            game=self.unit.game,
            in_system=self.unit.in_system,
            in_hex=self.unit.in_hex,
            position=Position(self.unit.position.x, self.unit.position.y),
            template_name=template.get("name", template_name)
        )

        if template.get("has_engine"):
            new_unit.add_component(Engines(new_unit, speed=template.get("engine_speed", 0), hull_cost=template.get("engine_hull_cost", 0)))
        
        if template.get("has_weapon_bays"):
            weapons_comp = Weapons(new_unit, hull_cost=template.get("weapon_bays_hull_cost", 0))
            for turret_def in template.get("turrets", []):
                variant_str = turret_def.get("variant", "STANDARD")
                try:
                    variant = TurretVariant[variant_str.upper()]
                except (KeyError, ValueError, AttributeError):
                    variant = TurretVariant.STANDARD

                turret = Turret(
                    turret_type=TurretType[turret_def["type"]],
                    damage=turret_def["damage"],
                    range=turret_def["range"],
                    cooldown=turret_def["cooldown"],
                    parent_unit=new_unit,
                    variant=variant
                )
                weapons_comp.add_turret(turret)
            new_unit.add_component(weapons_comp)

        wing_comp = StrikecraftWingComponent(new_unit, wing_type=self.build_wing_type)
        wing_comp.mother_carrier = self.unit
        new_unit.add_component(wing_comp)

        # Direct dock
        self.docked_units.append(new_unit)
        logger.debug(f"Auto-constructed and docked new strikecraft wing {new_unit.name} ({new_unit.id}) for carrier {self.unit.name}.")

    def update(self, galaxy: 'Galaxy'):
        """Automatically constructs or replenishes wings. Called each turn."""
        if self.is_destroyed:
            return

        # Prune destroyed launched units
        self.launched_units = [u for u in self.launched_units if u.current_hit_points > 0]

        owner = self.unit.owner
        if not owner:
            return

        # 1. Update ongoing replenishment
        if self.replenishing_unit:
            # If the unit was deployed or destroyed in the meantime, cancel replenishment
            if self.replenishing_unit not in self.docked_units or self.replenishing_unit.current_hit_points <= 0:
                self.replenishing_unit = None
                self.replenish_progress = 0
            else:
                self.replenish_progress += 1
                if self.replenish_progress >= 1: # 1 turn to replenish 1 fighter (10 HP)
                    self.replenishing_unit.heal_hull(10)
                    logger.debug(f"Strikecraft bay on {self.unit.name} replenished 1 craft in wing {self.replenishing_unit.name}. HP: {self.replenishing_unit.current_hit_points}/{self.replenishing_unit.max_hit_points}")
                    # If fully healed, clear. Otherwise keep replenishing on next turn
                    if self.replenishing_unit.current_hit_points >= self.replenishing_unit.max_hit_points:
                        self.replenishing_unit = None
                        self.replenish_progress = 0
                    else:
                        # Start next replenishment step immediately if we have credits
                        cost = 35
                        if owner.credits >= cost:
                            owner.credits -= cost
                            self.replenish_progress = 0
                        else:
                            self.replenishing_unit = None
                            self.replenish_progress = 0
                return

        # 2. Update ongoing construction
        if self.constructing:
            self.construction_progress += 1
            if self.construction_progress >= 2: # 2 turns to construct a new wing
                self.finish_auto_construction(galaxy)
                self.constructing = False
                self.construction_progress = 0
            return

        # 3. If not busy, check if we need to replenish a damaged wing
        damaged_wing = None
        for wing in self.docked_units:
            if wing.current_hit_points < wing.max_hit_points:
                damaged_wing = wing
                break

        if damaged_wing:
            cost = 35
            if owner.credits >= cost:
                owner.credits -= cost
                self.replenishing_unit = damaged_wing
                self.replenish_progress = 0
                logger.debug(f"Strikecraft bay on {self.unit.name} started replenishing wing {damaged_wing.name} for {cost} credits.")
                return

        # 4. If not busy and we have free slots, start constructing a new wing
        if self.get_used_slots() < self.max_slots:
            cost = 150
            if owner.credits >= cost:
                owner.credits -= cost
                self.constructing = True
                self.construction_progress = 0
                role_text = "Fighter" if self.build_wing_type == WingType.FIGHTER else "Bomber"
                logger.debug(f"Strikecraft bay on {self.unit.name} started constructing new {role_text} Wing for {cost} credits.")
                return


@dataclasses.dataclass
class BuildableUnit:
    unit_template_name: str
    time_to_build: int
    cost_credits: int


class Constructor(UnitComponent):
    """A component that allows a unit to construct other units (stations)."""
    DISPLAY_NAME: str = "Constructor"
    SIDEBAR_ORDER: int = 5
    build_range: float = 500.0
    
    # Construction state
    current_construction_target: Optional[tuple[str, Position]] = None # (unit_template_name, position)
    construction_progress: int = 0
    time_to_build: int = 0

    def __init__(self, unit: 'Unit', hull_cost: int, buildable_unit_names: typing.Optional[list[str]] = None):
        super().__init__(unit, hull_cost)
        self.current_construction_target = None
        self.construction_progress = 0
        self.time_to_build = 0

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        if self.current_construction_target:
            target_name = self.current_construction_target[0]
            progress = self.construction_progress
            total = self.time_to_build
            data.append({'type': 'label', 'text': f"Constructing: {target_name}", 'object_id': '#sidebar_info_label', 'height': 25})
            data.append({
                'type': 'progress_bar',
                'progress': progress,
                'total': total,
                'height': 25
            })
        else:
            data.append({'type': 'label', 'text': "Status: Idle", 'object_id': '#sidebar_info_label', 'height': 20})
        return data

    @property
    def buildable_units(self) -> list[BuildableUnit]:
        """Dynamically retrieve all buildable units based on UNIT_TEMPLATES."""
        from unit_templates import UNIT_TEMPLATES
        buildables = []
        for name, template in UNIT_TEMPLATES.items():
            buildables.append(BuildableUnit(
                unit_template_name=name,
                time_to_build=template.get("build_time", 10),
                cost_credits=template.get("build_cost", 500)
            ))
        return buildables

    def can_build(self, unit_template_name: str) -> Optional[BuildableUnit]:
        """Check if this constructor can build a specific unit type."""
        from unit_templates import UNIT_TEMPLATES
        template = UNIT_TEMPLATES.get(unit_template_name)
        if template:
            return BuildableUnit(
                unit_template_name=unit_template_name,
                time_to_build=template.get("build_time", 10),
                cost_credits=template.get("build_cost", 500)
            )
        return None

    def refresh_buildable_units(self, additional_names: typing.List[str]) -> None:
        """Append template names to buildable_units if not already present. (Deprecated/No-op)"""
        pass

    def start_construction(self, unit_template_name: str, position: Position, galaxy: 'Galaxy') -> bool:
        """Starts the construction of a new unit."""
        if self.is_destroyed:
            return False

        buildable = self.can_build(unit_template_name)
        if not buildable:
            logger.debug(f"Error: {self.unit.name} cannot build {unit_template_name}.")
            return False

        owner = self.unit.owner
        if owner.credits < buildable.cost_credits:
            logger.debug(f"Error: Not enough credits to build {unit_template_name}.")
            return False
        owner.credits -= buildable.cost_credits

        self.current_construction_target = (unit_template_name, position)
        self.time_to_build = buildable.time_to_build
        self.construction_progress = 0
        logger.debug(f"{self.unit.name} started constructing {unit_template_name} at {position}. Cost: {buildable.cost_credits}")
        return True

    def cancel_construction(self):
        """Cancels the current construction project."""
        if self.current_construction_target:
            logger.debug(f"Construction of {self.current_construction_target[0]} cancelled.")
            # NOTE: Resource refund should be handled by the Order
            self.current_construction_target = None
            self.construction_progress = 0
            self.time_to_build = 0

    def update(self, galaxy: 'Galaxy'):
        """Updates the construction progress. Called each turn."""
        if self.is_destroyed:
            return
        if self.current_construction_target:
            self.construction_progress += 1
            if self.construction_progress >= self.time_to_build:
                self.finish_construction(galaxy)

    def create_unit_from_template(self, galaxy: 'Galaxy', template_name: str, owner: 'Player', system_name: str, hex_coord: 'HexCoord', position: 'Position'):
        """Creates a new unit based on the template."""
        from entities import Unit # Avoid circular import

        template = UNIT_TEMPLATES.get(template_name)
        if not template:
            logger.debug(f"Error: Unit template '{template_name}' not found.")
            return

        system = galaxy.systems.get(system_name)
        if not system:
            logger.debug(f"Error: System '{system_name}' not found for unit creation.")
            return

        new_unit = Unit(
            owner=owner,
            name=template["name"],
            hull_size=template["hull_size"],
            game=self.unit.game,
            in_system=system_name,
            in_hex=hex_coord,
            position=position,
            template_name=template.get("name", template_name)
        )

        if template.get("has_engine"):
            speed = template.get("engine_speed", 0)
            new_unit.add_component(Engines(new_unit, speed=speed, hull_cost=template.get("engine_hull_cost", 0)))

        if template.get("has_hyperdrive"):
            htype_raw = template.get("hyperdrive_type", HyperdriveType.BASIC)
            if isinstance(htype_raw, str):
                raw_upper = htype_raw.upper()
                if raw_upper == "ADVANCED":
                    htype = HyperdriveType.ADVANCED
                elif raw_upper == "BASIC":
                    htype = HyperdriveType.BASIC
                else:
                    try:
                        htype = HyperdriveType(htype_raw.lower())
                    except ValueError:
                        htype = HyperdriveType.BASIC
            else:
                htype = htype_raw

            hull_size = new_unit.hull_size
            if hull_size == HullSize.TINY and htype == HyperdriveType.ADVANCED:
                logger.warning(f"Warning: Attempted to add ADVANCED hyperdrive to TINY unit template '{template_name}'. Downgrading to BASIC.")
                htype = HyperdriveType.BASIC

            cost = template.get("hyperdrive_hull_cost")
            if cost is None or cost == 0:
                cost = 5 if htype == HyperdriveType.BASIC else 10
            jump_range = template.get("hyperdrive_jump_range", DEFAULT_JUMP_RANGE)
            new_unit.add_component(Hyperdrive(new_unit, drive_type=htype, hull_cost=cost, jump_range=jump_range))

        if template.get("has_weapon_bays"):
            weapons_comp = Weapons(new_unit, hull_cost=template.get("weapon_bays_hull_cost", 0))
            for turret_def in template.get("turrets", []):
                variant_str = turret_def.get("variant", "STANDARD")
                try:
                    variant = TurretVariant[variant_str.upper()]
                except (KeyError, ValueError, AttributeError):
                    variant = TurretVariant.STANDARD

                turret = Turret(
                    turret_type=TurretType[turret_def["type"]],
                    damage=turret_def["damage"],
                    range=turret_def["range"],
                    cooldown=turret_def["cooldown"],
                    parent_unit=new_unit,
                    variant=variant
                )
                weapons_comp.add_turret(turret)
            new_unit.add_component(weapons_comp)

        if template.get("has_defenses"):
            new_unit.add_component(Defenses(
                new_unit,
                armor=template.get("armor", 0),
                shields=template.get("shields", 0),
                point_defense=template.get("point_defense", 0),
                hull_cost=template.get("defenses_hull_cost", 0)
            ))

        if template.get("has_constructor_component"):
            new_unit.add_component(Constructor(new_unit, hull_cost=template.get("constructor_hull_cost", 0)))

        if template.get("has_repair_component"):
            new_unit.add_component(RepairComponent(
                new_unit,
                repair_rate=template.get("repair_rate", 10.0),
                repair_range=template.get("repair_range", 200.0),
                credit_cost_per_hp=template.get("credit_cost_per_hp", 1.0),
                hull_cost=template.get("repair_hull_cost", 15)
            ))

        if template.get("has_mining_component"):
            new_unit.add_component(MiningComponent(
                new_unit,
                mining_rate=template.get("mining_rate", 10.0),
                mining_range=template.get("mining_range", 200.0),
                max_cargo=template.get("max_mining_cargo", 100.0),
                hull_cost=template.get("mining_hull_cost", 10)
            ))

        if template.get("has_metal_refinery_component"):
            new_unit.add_component(MetalRefineryComponent(
                new_unit,
                unload_range=template.get("unload_range", 300.0),
                hull_cost=template.get("metal_refinery_hull_cost", 20)
            ))

        if template.get("has_crystal_refinery_component"):
            new_unit.add_component(CrystalRefineryComponent(
                new_unit,
                unload_range=template.get("unload_range", 300.0),
                hull_cost=template.get("crystal_refinery_hull_cost", 20)
            ))

        if template.get("has_hangar"):
            hull_size = new_unit.hull_size
            if hull_size in (HullSize.TINY, HullSize.SMALL, HullSize.MEDIUM):
                logger.warning(f"Warning: Attempted to add hangar to forbidden hull size {hull_size.name} in template '{template_name}'. Skipping.")
            else:
                new_unit.add_component(HangarComponent(
                    new_unit,
                    max_slots=template.get("hangar_slots", 0),
                    hull_cost=template.get("hangar_hull_cost", 0)
                ))

        if template.get("has_strikecraft_bay"):
            hull_size = new_unit.hull_size
            if hull_size in (HullSize.STRIKECRAFT_WING, HullSize.TINY, HullSize.SMALL):
                logger.warning(f"Warning: Attempted to add strikecraft bay to forbidden hull size {hull_size.name} in template '{template_name}'. Skipping.")
            else:
                new_unit.add_component(StrikecraftBayComponent(
                    new_unit,
                    max_slots=template.get("strikecraft_bay_slots", 0),
                    hull_cost=template.get("strikecraft_bay_hull_cost", 0)
                ))

        if new_unit.hull_size == HullSize.STRIKECRAFT_WING:
            wing_type_str = template.get("wing_type", "FIGHTER")
            try:
                wing_type = WingType[wing_type_str.upper()]
            except (KeyError, ValueError, AttributeError):
                wing_type = WingType.FIGHTER
            new_unit.add_component(StrikecraftWingComponent(new_unit, wing_type=wing_type))

        if template.get("has_colony_component"):
            new_unit.add_component(ColonyComponent(
                new_unit,
                hull_cost=template.get("colony_hull_cost", 10)
            ))

        if template.get("has_inhibitor"):
            new_unit.add_component(HyperspaceInhibitionFieldEmitter(
                new_unit,
                radius=template.get("inhibitor_radius", 100.0),
                hull_cost=template.get("inhibitor_hull_cost", 20)
            ))

        if template.get("has_ability_component"):
            raw_ability_names = template.get("abilities", [])
            ability_types = []
            for aname in raw_ability_names:
                try:
                    ability_types.append(AbilityType(aname))
                except ValueError:
                    logger.warning(f"[create_unit_from_template] Unknown ability '{aname}' in template '{template_name}'. Skipping.")
            if ability_types:
                new_unit.add_component(AbilityComponent(
                    new_unit,
                    ability_types=ability_types,
                    hull_cost=template.get("ability_hull_cost", 10)
                ))

        system.add_unit(new_unit)
        logger.debug(f"Created unit {new_unit.name} ({new_unit.id}) for player {owner.id} in {system_name} at {hex_coord}")

    def finish_construction(self, galaxy: 'Galaxy'):
        """Finalizes the construction and creates the new unit."""
        if not self.current_construction_target:
            return

        unit_template_name, position = self.current_construction_target
        logger.debug(f"Construction of {unit_template_name} finished by {self.unit.name}.")
        
        self.create_unit_from_template(
            galaxy=galaxy,
            template_name=unit_template_name,
            owner=self.unit.owner,
            system_name=self.unit.in_system,
            hex_coord=self.unit.in_hex,
            position=position
        )

        # Construction complete; reset building state variables.
        self.current_construction_target = None
        self.construction_progress = 0
        self.time_to_build = 0


# --- Ability Component ---

@dataclasses.dataclass
class AbilityInstance:
    """Runtime state for a single ability on a unit."""
    definition: AbilityDefinition
    cooldown_remaining: int = 0
    is_active: bool = False
    duration_remaining: int = 0
    target_unit_id: typing.Optional[int] = None
    target_position: typing.Optional[Position] = None
    # For Missile Batteries: track spawned platform unit IDs
    spawned_unit_ids: typing.List[int] = dataclasses.field(default_factory=list)

    @property
    def is_ready(self) -> bool:
        """True if the ability is off cooldown and not currently active."""
        return self.cooldown_remaining <= 0 and not self.is_active


class AbilityComponent(UnitComponent):
    """
    Manages the set of special abilities available to a unit.

    Each ability has its own cooldown and active-duration tracking. This component
    is responsible for ticking cooldowns, applying ongoing effects each turn
    (e.g. Repair Cloud healing, Designate Target marking), and cleaning up expired
    effects. If this component is destroyed the unit cannot use any abilities.
    """
    DISPLAY_NAME: str = "Abilities"
    SIDEBAR_ORDER: int = 14
    abilities: typing.Dict[AbilityType, AbilityInstance] = dataclasses.field(default_factory=dict)

    def __init__(self, unit: 'Unit', ability_types: typing.List[AbilityType], hull_cost: int = 10):
        super().__init__(unit, hull_cost=hull_cost)
        self.abilities: typing.Dict[AbilityType, AbilityInstance] = {}
        for atype in ability_types:
            defn = ABILITY_DEFINITIONS.get(atype)
            if defn:
                self.abilities[atype] = AbilityInstance(definition=defn)
            else:
                logger.warning(f"[AbilityComponent] Unknown ability type: {atype}")

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        status = "DESTROYED" if self.is_destroyed else f"HP: {self.current_hit_points}/{self.max_hit_points}"
        data = [{
            'type': 'label',
            'text': f"Ability System [{status}]",
            'object_id': '#sidebar_section_header_label',
            'height': 28,
        }]

        # Show Ion Bolt / Designate Target targeting-mode indicator
        if game_state.pending_ability:
            pending_name = game_state.pending_ability[0].replace('_', ' ').title()
            data.append({
                'type': 'label',
                'text': f"\u25b6 Select target for: {pending_name}",
                'object_id': '#sidebar_hit_points_light_damage_label',
                'height': 22,
            })

        for ability_type, instance in self.abilities.items():
            defn = instance.definition
            if instance.is_active:
                cd_str = f"Active ({instance.duration_remaining} turns)"
                btn_obj_id = '#sidebar_section_header_label'
            elif instance.cooldown_remaining > 0:
                cd_str = f"Cooldown: {instance.cooldown_remaining} turns"
                btn_obj_id = '#sidebar_info_label'
            else:
                cd_str = "Ready"
                btn_obj_id = '#sidebar_expand_button'

            btn_text = f"{defn.name}  [{cd_str}]"
            data.append({
                'type': 'button',
                'text': btn_text,
                'object_id': btn_obj_id,
                'action_id': 'use_ability',
                'target_data': {
                    'ability_type_str': ability_type.value,
                    'requires_target_unit': defn.requires_target_unit,
                    'requires_target_position': defn.requires_target_position,
                },
                'height': 28,
                'enabled': instance.is_ready and not self.is_destroyed,
            })
            data.append({
                'type': 'label',
                'text': f"  {defn.description}",
                'object_id': '#sidebar_info_label',
                'height': 18,
            })
        return data

    def can_use(self, ability_type: AbilityType) -> bool:
        """Returns True if the ability exists, the component is intact, and it is off cooldown."""
        if self.is_destroyed:
            return False
        instance = self.abilities.get(ability_type)
        if not instance:
            return False
        return instance.is_ready

    def activate(
        self,
        ability_type: AbilityType,
        galaxy: 'Galaxy',
        target_unit_id: typing.Optional[int] = None,
        target_position: typing.Optional[Position] = None,
    ) -> bool:
        """
        Activates the specified ability.

        Performs validation, applies immediate effects, and sets the active
        state. Returns True on success, False on failure.
        """
        if not self.can_use(ability_type):
            logger.debug(f"[{self.unit.name}] Cannot use {ability_type.name}: not ready or component destroyed.")
            return False

        instance = self.abilities[ability_type]
        defn = instance.definition

        # --- Immediate activation effects ---
        if ability_type == AbilityType.ADAPTIVE_FORCEFIELD:
            self.unit.damage_reduction = 0.75
            logger.debug(f"[{self.unit.name}] Adaptive Forcefield activated. Damage reduction: 75%.")

        elif ability_type == AbilityType.CLUSTER_WARHEAD:
            if target_position is None:
                logger.debug(f"[{self.unit.name}] Cluster Warhead requires a target position.")
                return False
            self._apply_cluster_warhead(galaxy, target_position)

        elif ability_type == AbilityType.DESIGNATE_TARGET:
            if target_unit_id is None:
                logger.debug(f"[{self.unit.name}] Designate Target requires a target unit.")
                return False
            target_unit = galaxy.get_unit_by_id(target_unit_id)
            if not target_unit:
                logger.debug(f"[{self.unit.name}] Designate Target: target unit {target_unit_id} not found.")
                return False
            target_unit.damage_amplification += 0.5
            instance.target_unit_id = target_unit_id
            logger.debug(f"[{self.unit.name}] Designate Target applied to {target_unit.name}. Amplification now: {target_unit.damage_amplification:.2f}.")

        elif ability_type == AbilityType.ION_BOLT:
            if target_unit_id is None:
                logger.debug(f"[{self.unit.name}] Ion Bolt requires a target unit.")
                return False
            target_unit = galaxy.get_unit_by_id(target_unit_id)
            if not target_unit:
                logger.debug(f"[{self.unit.name}] Ion Bolt: target unit {target_unit_id} not found.")
                return False
            target_unit.is_disabled = True
            target_unit.disabled_by_unit_ids.add(self.unit.id)
            instance.target_unit_id = target_unit_id
            logger.debug(f"[{self.unit.name}] Ion Bolt disabled {target_unit.name}.")

        elif ability_type == AbilityType.MISSILE_BATTERIES:
            spawned = self._spawn_missile_platforms(galaxy, defn.duration)
            instance.spawned_unit_ids = spawned
            logger.debug(f"[{self.unit.name}] Missile Batteries: spawned {len(spawned)} platforms.")

        elif ability_type == AbilityType.REPAIR_CLOUD:
            # Healing applied each turn in update(); nothing immediate needed.
            logger.debug(f"[{self.unit.name}] Repair Cloud activated. Healing friendlies within {defn.range} units for {defn.duration} turns.")

        # --- Mark as active and set cooldown ---
        instance.is_active = (defn.duration > 0)
        instance.duration_remaining = defn.duration
        instance.target_position = target_position
        instance.cooldown_remaining = defn.cooldown
        return True

    def _apply_cluster_warhead(
        self,
        galaxy: 'Galaxy',
        target_position: Position,
        splash_radius: float = 200.0,
        base_damage: int = 80,
    ) -> None:
        """Deals splash damage to all units at the target position within splash_radius."""
        system = galaxy.systems.get(self.unit.in_system)
        if not system:
            return
        hex_obj = system.hexes.get(self.unit.in_hex)
        if not hex_obj:
            return
        for target_unit in list(hex_obj.units):
            if target_unit is self.unit:
                continue
            dist = distance(target_unit.position, target_position)
            if dist <= splash_radius:
                # Damage falls off linearly with distance
                falloff = max(0.0, 1.0 - (dist / splash_radius))
                damage = max(1, int(base_damage * falloff))
                target_unit.take_damage(damage)
                logger.debug(f"[Cluster Warhead] Hit {target_unit.name} for {damage} damage (dist={dist:.1f}).")

    def _spawn_missile_platforms(
        self,
        galaxy: 'Galaxy',
        lifetime: int,
        num_platforms: int = 3,
        deploy_radius: float = 60.0,
    ) -> typing.List[int]:
        """Spawns temporary missile platform units around the caster and returns their IDs."""
        from entities import Unit
        spawned_ids = []
        for i in range(num_platforms):
            angle = (2 * math.pi / num_platforms) * i
            px = self.unit.position.x + deploy_radius * math.cos(angle)
            py = self.unit.position.y + deploy_radius * math.sin(angle)
            platform_pos = Position(px, py)

            platform = Unit(
                owner=self.unit.owner,
                position=platform_pos,
                in_hex=self.unit.in_hex,
                in_system=self.unit.in_system,
                name=f"Missile Platform",
                hull_size=HullSize.TINY,
                game=self.unit.game,
            )
            platform.lifetime = lifetime
            platform.is_temporary = True

            # Add a weapons component with a single missile turret
            weapons_comp = Weapons(platform, hull_cost=0)
            turret = Turret(
                turret_type=TurretType.MISSILE,
                damage=15.0,
                range=350.0,
                cooldown=2,
                parent_unit=platform,
            )
            weapons_comp.add_turret(turret)
            platform.add_component(weapons_comp)

            system = galaxy.systems.get(self.unit.in_system)
            if system:
                system.add_unit(platform)
                spawned_ids.append(platform.id)

        return spawned_ids

    def _expire_ability(self, ability_type: AbilityType, galaxy: 'Galaxy') -> None:
        """Cleans up lingering effects when an ability's duration expires."""
        instance = self.abilities[ability_type]

        if ability_type == AbilityType.ADAPTIVE_FORCEFIELD:
            self.unit.damage_reduction = max(0.0, self.unit.damage_reduction - 0.75)
            logger.debug(f"[{self.unit.name}] Adaptive Forcefield expired. Damage reduction removed.")

        elif ability_type == AbilityType.DESIGNATE_TARGET:
            if instance.target_unit_id is not None:
                target_unit = galaxy.get_unit_by_id(instance.target_unit_id)
                if target_unit:
                    target_unit.damage_amplification = max(0.0, target_unit.damage_amplification - 0.5)
                    logger.debug(f"[{self.unit.name}] Designate Target expired on {target_unit.name}. Amplification now: {target_unit.damage_amplification:.2f}.")
            instance.target_unit_id = None

        elif ability_type == AbilityType.ION_BOLT:
            if instance.target_unit_id is not None:
                target_unit = galaxy.get_unit_by_id(instance.target_unit_id)
                if target_unit:
                    target_unit.disabled_by_unit_ids.discard(self.unit.id)
                    if not target_unit.disabled_by_unit_ids:
                        target_unit.is_disabled = False
                    logger.debug(f"[{self.unit.name}] Ion Bolt expired on {target_unit.name}. Disabled: {target_unit.is_disabled}.")
            instance.target_unit_id = None

        elif ability_type == AbilityType.MISSILE_BATTERIES:
            # Platforms have their own lifetime; despawn any still alive
            system = galaxy.systems.get(self.unit.in_system)
            if system:
                for uid in instance.spawned_unit_ids:
                    platform = galaxy.get_unit_by_id(uid)
                    if platform:
                        galaxy.remove_unit(platform)
                        logger.debug(f"[{self.unit.name}] Missile Platform {uid} despawned.")
            instance.spawned_unit_ids = []

        elif ability_type == AbilityType.REPAIR_CLOUD:
            logger.debug(f"[{self.unit.name}] Repair Cloud expired.")

        instance.is_active = False
        instance.duration_remaining = 0
        instance.target_position = None

    def _apply_repair_cloud(self, galaxy: 'Galaxy') -> None:
        """Heals all friendly units within Repair Cloud range by 5 HP."""
        defn = ABILITY_DEFINITIONS[AbilityType.REPAIR_CLOUD]
        system = galaxy.systems.get(self.unit.in_system)
        if not system:
            return
        hex_obj = system.hexes.get(self.unit.in_hex)
        if not hex_obj:
            return
        heal_per_turn = 5
        for unit in hex_obj.units:
            if unit.owner != self.unit.owner:
                continue
            if distance(self.unit.position, unit.position) <= defn.range:
                unit.heal_hull(heal_per_turn)
                logger.debug(f"[Repair Cloud] Healed {unit.name} for {heal_per_turn} HP.")

    def _auto_target_platforms(self, galaxy: 'Galaxy') -> None:
        """Assigns the nearest enemy as the weapon target for each active missile platform."""
        instance = self.abilities.get(AbilityType.MISSILE_BATTERIES)
        if not instance:
            return
        system = galaxy.systems.get(self.unit.in_system)
        if not system:
            return

        for uid in instance.spawned_unit_ids:
            platform = galaxy.get_unit_by_id(uid)
            if not platform or not platform.weapons_component:
                continue
            hex_obj = system.hexes.get(platform.in_hex)
            if not hex_obj:
                continue

            closest_enemy = None
            min_dist = float('inf')
            max_range = max((t.range for t in platform.weapons_component.turrets), default=0)
            for candidate in hex_obj.units:
                if candidate.owner == platform.owner or candidate.current_hit_points <= 0:
                    continue
                d = distance(platform.position, candidate.position)
                if d <= max_range and d < min_dist:
                    min_dist = d
                    closest_enemy = candidate

            platform.weapons_component.set_target(closest_enemy)

    def update(self, galaxy: 'Galaxy') -> None:
        """
        Called once per turn. Ticks cooldowns, applies ongoing ability effects,
        and expires abilities whose duration has elapsed.
        """
        if self.is_destroyed:
            return

        for ability_type, instance in self.abilities.items():
            # --- Tick cooldown ---
            if instance.cooldown_remaining > 0:
                instance.cooldown_remaining -= 1

            # --- Apply ongoing effects for active abilities ---
            if instance.is_active:
                if ability_type == AbilityType.REPAIR_CLOUD:
                    self._apply_repair_cloud(galaxy)

                elif ability_type == AbilityType.MISSILE_BATTERIES:
                    self._auto_target_platforms(galaxy)

                # --- Tick duration ---
                if instance.duration_remaining > 0:
                    instance.duration_remaining -= 1

                # --- Check expiry ---
                if instance.duration_remaining <= 0:
                    self._expire_ability(ability_type, galaxy)