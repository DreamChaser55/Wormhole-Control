import logging
import typing
from typing import Optional, Deque, TYPE_CHECKING
from collections import deque
import dataclasses

from .base import UnitComponent
from .enums import UnitStance, TurretVariant, WingType
from geometry import distance, hex_distance
from constants import HullSize, XP_JUMP_RANGE_BONUS
from unit_orders import Order, OrderStatus

if TYPE_CHECKING:
    from entities import Unit
    from galaxy import Galaxy
    from game import Game

logger = logging.getLogger(__name__)

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
    stance: UnitStance = UnitStance.DO_NOTHING

    def __init__(self, unit: 'Unit'):
        super().__init__(unit, hull_cost=0)
        self.current_order = None
        self.orders_queue = deque()
        self.stance = UnitStance.DO_NOTHING

    def get_allowed_stances(self) -> list[UnitStance]:
        """Gets the list of allowed stances for this unit based on its components."""
        allowed = [UnitStance.DO_NOTHING, UnitStance.ATTACK_WEAPON_RANGE]
        if self.unit.engines_component is not None:
            allowed.append(UnitStance.ATTACK_SAME_SECTOR)
            if self.unit.hyperdrive_component is not None:
                allowed.append(UnitStance.ATTACK_INTRA_SYSTEM_JUMP_RANGE)
                allowed.append(UnitStance.ATTACK_SAME_SYSTEM)
        return allowed

    def process_stance(self) -> None:
        """Processes the unit's stance when it has no active or queued orders."""
        allowed_stances = self.get_allowed_stances()
        if self.stance not in allowed_stances:
            logger.warning(f"Unit {self.unit.name} (id:{self.unit.id}) has stance {self.stance} which is not allowed. Resetting to DO_NOTHING.")
            self.stance = UnitStance.DO_NOTHING

        if self.stance == UnitStance.DO_NOTHING:
            if self.unit.weapons_component:
                self.unit.weapons_component.clear_target()
            return

        if self.unit.is_disabled:
            return

        galaxy_ref: Optional['Galaxy'] = getattr(self.unit, 'in_galaxy', None)
        if not galaxy_ref:
            return

        weapons = self.unit.weapons_component
        if not weapons or weapons.is_destroyed or not weapons.turrets:
            return

        target = self.find_stance_target(galaxy_ref)
        if not target:
            if self.stance == UnitStance.ATTACK_WEAPON_RANGE:
                weapons.clear_target()
            return

        if self.stance == UnitStance.ATTACK_WEAPON_RANGE:
            weapons.set_target(target)
        else:
            from unit_orders import AttackOrder
            attack_order = AttackOrder(self.unit, {"target_unit_id": target.id})
            attack_order.is_stance_order = True
            self.add_order(attack_order)

    def is_target_valid_for_stance(self, target: 'Unit', galaxy_ref: 'Galaxy') -> bool:
        """Checks if the given target is still valid under the unit's current stance."""
        if self.stance not in self.get_allowed_stances():
            return False

        if target.current_hit_points <= 0 or target.owner == self.unit.owner:
            return False

        if target.in_system != self.unit.in_system:
            return False

        if self.stance == UnitStance.ATTACK_WEAPON_RANGE:
            if target.in_hex != self.unit.in_hex:
                return False

            weapons = self.unit.weapons_component
            if not weapons or weapons.is_destroyed:
                return False

            dist = distance(self.unit.position, target.position)
            for t in weapons.turrets:
                if target.hull_size == HullSize.STRIKECRAFT_WING and t.variant != TurretVariant.ANTI_STRIKECRAFT:
                    continue
                # Attacker is a strikecraft wing:
                if self.unit.hull_size == HullSize.STRIKECRAFT_WING:
                    wing_comp = self.unit.strikecraft_wing_component
                    if wing_comp:
                        if wing_comp.wing_type == WingType.FIGHTER:
                            if target.hull_size != HullSize.STRIKECRAFT_WING:
                                continue
                        elif wing_comp.wing_type == WingType.BOMBER:
                            if target.hull_size == HullSize.STRIKECRAFT_WING:
                                continue
                if dist <= t.range:
                    return True
            return False

        elif self.stance == UnitStance.ATTACK_SAME_SECTOR:
            return target.in_hex == self.unit.in_hex

        elif self.stance == UnitStance.ATTACK_INTRA_SYSTEM_JUMP_RANGE:
            if not self.unit.hyperdrive_component:
                return target.in_hex == self.unit.in_hex

            effective_jump_range = int(self.unit.hyperdrive_component.jump_range * self.unit.xp_multiplier(XP_JUMP_RANGE_BONUS))
            return hex_distance(self.unit.in_hex, target.in_hex) <= effective_jump_range

        elif self.stance == UnitStance.ATTACK_SAME_SYSTEM:
            return True

        return False

    def find_stance_target(self, galaxy_ref: 'Galaxy') -> Optional['Unit']:
        """Scans the system for the closest eligible target matching the current stance."""
        system = galaxy_ref.systems.get(self.unit.in_system)
        if not system:
            return None

        candidates = []
        if self.stance in [UnitStance.ATTACK_WEAPON_RANGE, UnitStance.ATTACK_SAME_SECTOR]:
            hex_obj = system.hexes.get(self.unit.in_hex)
            if hex_obj:
                candidates = hex_obj.units
        else:
            for hex_obj in system.hexes.values():
                candidates.extend(hex_obj.units)

        eligible_targets = []
        for candidate in candidates:
            if candidate.owner == self.unit.owner or candidate.current_hit_points <= 0:
                continue

            if not self.is_target_valid_for_stance(candidate, galaxy_ref):
                continue

            h_dist = hex_distance(self.unit.in_hex, candidate.in_hex)
            p_dist = distance(self.unit.position, candidate.position)
            dist_score = h_dist * 1000000.0 + p_dist

            eligible_targets.append((dist_score, candidate))

        if not eligible_targets:
            return None

        eligible_targets.sort(key=lambda x: x[0])
        return eligible_targets[0][1]

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = []
        
        # Display Unit Stance
        data.append({
            'type': 'label',
            'text': "Stance:",
            'object_id': '#sidebar_info_label',
            'height': 20,
            'indent_level': 0
        })
        
        is_owned = (self.unit.owner == game_state.players[game_state.current_player_index])
        if is_owned:
            options_list = [s.display_name for s in self.get_allowed_stances()]
            data.append({
                'type': 'drop_down_menu',
                'options_list': options_list,
                'starting_option': self.stance.display_name,
                'action_id': 'set_stance',
                'target_data': self.unit.id,
                'height': 30,
                'indent_level': 0
            })
        else:
            data.append({
                'type': 'label',
                'text': self.stance.display_name,
                'object_id': '#sidebar_info_label',
                'height': 20,
                'indent_level': 1
            })
            
        # Add a vertical gap before order list
        data.append({
            'type': 'label',
            'text': "",
            'object_id': '#sidebar_info_label',
            'height': 5,
            'indent_level': 0
        })

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
        # If we have a stance-generated order, validate if the target is still valid under our current stance.
        # If not, cancel the order.
        if self.current_order and getattr(self.current_order, 'is_stance_order', False):
            target_unit_id = self.current_order.parameters.get("target_unit_id")
            target_unit = None
            galaxy_ref = getattr(self.unit, 'in_galaxy', None)
            if galaxy_ref and target_unit_id:
                target_unit = galaxy_ref.get_unit_by_id(target_unit_id)
            
            if not target_unit or not self.is_target_valid_for_stance(target_unit, galaxy_ref):
                self.current_order.cancel()
                self.current_order = None

        if not self.current_order:
            self.start_next_order()
            if not self.current_order:
                self.process_stance()
                return

        if not self.current_order:
            self.process_stance()
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
            self.process_stance()
            return

        order_is_finished = False
        if self.current_order.is_completed():
            order_is_finished = True
        elif self.current_order.status in [OrderStatus.FAILED, OrderStatus.CANCELLED]:
            order_is_finished = True

        if order_is_finished:
            self.current_order = None
            self.start_next_order()
            if not self.current_order:
                self.process_stance()

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
