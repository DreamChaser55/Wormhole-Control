import logging
import typing
from typing import Optional, Deque, TYPE_CHECKING, Iterable
from collections import deque
import dataclasses

from .base import UnitComponent
from .enums import UnitStance, TurretVariant, WingType
from unit_orders import Order, OrderStatus, OrderType
from unit_orders import StanceOrder

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
    standing_order: StanceOrder = dataclasses.field(init=False)
    _stance: UnitStance = dataclasses.field(init=False, default=UnitStance.DO_NOTHING)

    def __init__(self, unit: 'Unit'):
        super().__init__(unit, hull_cost=0)
        self.current_order = None
        self.orders_queue = deque()
        self._stance = UnitStance.DO_NOTHING
        self.standing_order = StanceOrder(unit, {"stance": self._stance.value})

    @property
    def stance(self) -> UnitStance:
        """Compatibility property; assignments use the stance lifecycle safely."""
        return self._stance

    @stance.setter
    def stance(self, stance: UnitStance) -> None:
        self.set_stance(stance)

    def get_allowed_stances(self) -> list[UnitStance]:
        """Gets the list of allowed stances for this unit based on its components."""
        allowed = [UnitStance.DO_NOTHING, UnitStance.ATTACK_WEAPON_RANGE]
        if self.unit.engines_component is not None and self.unit.engines_component.is_operational:
            allowed.append(UnitStance.ATTACK_SAME_SECTOR)
            if (
                self.unit.hyperdrive_component is not None
                and self.unit.hyperdrive_component.is_functional
            ):
                allowed.append(UnitStance.ATTACK_INTRA_SYSTEM_JUMP_RANGE)
                allowed.append(UnitStance.ATTACK_SAME_SYSTEM)
        return allowed

    def process_stance(self) -> None:
        """Update the standing policy while no explicit order is active."""
        if self.current_order or self.orders_queue:
            return
        galaxy_ref: Optional['Galaxy'] = (
            getattr(self.unit, 'in_galaxy', None)
            or getattr(getattr(self.unit, 'game', None), 'galaxy', None)
        )
        if galaxy_ref:
            self.standing_order.update(galaxy_ref)

    def is_target_valid_for_stance(self, target: 'Unit', galaxy_ref: 'Galaxy', visibility_snapshot: Optional[typing.Any] = None) -> bool:
        """Compatibility wrapper around the first-class standing order."""
        return self.standing_order.is_target_valid(target, galaxy_ref, visibility_snapshot)

    def find_stance_target(self, galaxy_ref: 'Galaxy', visibility_snapshot: Optional[typing.Any] = None) -> Optional['Unit']:
        """Compatibility wrapper around the first-class standing order."""
        return self.standing_order.find_target(galaxy_ref, visibility_snapshot)

    def get_basic_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_basic_sidebar_data(game_state)
        if self.is_destroyed:
            return data
        orders_count = self.get_active_orders_count()
        if self.current_order:
            curr_name = self.current_order.order_type.name.replace('_', ' ').title()
        elif self.standing_order.has_engagement:
            curr_name = "Standing Attack"
        else:
            curr_name = "None"
        obj_id = '#sidebar_status_active_label' if orders_count > 0 else '#sidebar_value_label'
        data.append({
            'type': 'label',
            'text': f"• Stance: [{self.stance.display_name}] | Order: {curr_name} ({orders_count} active)",
            'object_id': obj_id,
            'height': 18,
            'indent_level': 1
        })
        is_owned = (self.unit.owner == game_state.players[game_state.current_player_index])
        if is_owned and orders_count > 0:
            data.append({
                'type': 'button',
                'text': "Stop Unit",
                'object_id': '#sidebar_expand_button',
                'action_id': 'stop_unit',
                'target_data': self.unit.id,
                'height': 25,
                'indent_level': 1
            })
        return data

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

        if is_owned and self.get_active_orders_count() > 0:
            data.append({
                'type': 'button',
                'text': "Stop Unit",
                'object_id': '#sidebar_expand_button',
                'action_id': 'stop_unit',
                'target_data': self.unit.id,
                'height': 25,
                'indent_level': 0
            })

        data.append({
            'type': 'label',
            'text': "Stance Order:",
            'object_id': '#sidebar_section_header_label',
            'height': 25,
            'indent_level': 0,
        })
        data.append({
            'type': 'text_box',
            'html_text': game_state._generate_order_data_recursive(self.standing_order, 0),
            'height': 120 if self.standing_order.has_engagement else 45,
            'object_id': '#order_text_box',
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
        """Add an explicit order, suspending any transient stance engagement."""
        self.suspend_stance_activity("explicit order started")
        self.orders_queue.append(order)

        if self.current_order is None:
            self.start_next_order()

    def set_stance(self, stance: UnitStance) -> None:
        """Replace the standing policy without interrupting explicit work."""
        if not isinstance(stance, UnitStance):
            try:
                stance = UnitStance(stance)
            except (TypeError, ValueError):
                raw_name = str(stance)
                if raw_name.startswith("UnitStance."):
                    raw_name = raw_name.rsplit(".", 1)[-1]
                try:
                    stance = UnitStance[raw_name.upper()]
                except (KeyError, TypeError) as exc:
                    raise ValueError(f"Unknown unit stance: {stance!r}") from exc
        old_stance = getattr(self, "_stance", UnitStance.DO_NOTHING)
        old_order = getattr(self, "standing_order", None)
        # A normal assignment of the same policy is idempotent, but do not
        # leave a standing order permanently cancelled if an integration
        # cancelled/replaced the root directly.  Recreate the root in that
        # case so the compatibility ``stance`` property remains safe.
        if (
            old_order
            and old_stance == stance
            and old_order.status in {OrderStatus.PENDING, OrderStatus.IN_PROGRESS}
        ):
            return
        if old_order:
            old_order.cancel()
        self._stance = stance
        self.standing_order = StanceOrder(self.unit, {"stance": stance.value})
        logger.debug(
            "[%s (id:%s)] Commander: stance changed from %s to %s.",
            self.unit.name,
            self.unit.id,
            old_stance.value,
            stance.value,
        )
        # Changing a stance must not interrupt a foreground explicit attack.
        # Its weapon lock remains authoritative until that order completes;
        # only an idle unit should have its cached target cleared here.
        if (
            stance == UnitStance.DO_NOTHING
            and not self.current_order
            and self.unit.weapons_component
        ):
            self.unit.weapons_component.clear_target()

    def get_active_order_root(self) -> Order:
        """Return the explicit foreground root, otherwise the standing root."""
        return self.current_order or self.standing_order

    def get_observable_active_order(self) -> Optional[Order]:
        """Keep observation schema v3 by exposing the stance's Attack child."""
        return self.current_order or self.standing_order.active_attack

    def suspend_stance_activity(self, reason: str = "suspended") -> None:
        """Cancel only the transient engagement while retaining its policy."""
        if self.standing_order.has_engagement:
            logger.debug(
                "[%s (id:%s)] Commander: suspending stance activity (%s).",
                self.unit.name,
                self.unit.id,
                reason,
            )
            self.standing_order.cancel_engagement(reason)

    def clear_explicit_orders(self) -> None:
        """Cancel foreground work while preserving the selected stance."""
        if self.current_order:
            self.current_order.cancel()
            self.current_order = None
        for order in self.orders_queue:
            order.cancel()
        self.orders_queue.clear()
        if not self.standing_order.has_engagement:
            self._clear_weapon_target()

    def stop_and_idle(self) -> None:
        """Cancel all work, clear component state, and select Do Nothing."""
        self.clear_explicit_orders()
        self.suspend_stance_activity("unit stopped")
        self.set_stance(UnitStance.DO_NOTHING)
        if self.unit.engines_component:
            self.unit.engines_component.clear_move_target()
        if self.unit.hyperdrive_component:
            self.unit.hyperdrive_component.clear_jump_target()
        self._clear_weapon_target()

    def clear_orders(self) -> None:
        """Backward-compatible stop operation; new code should use an explicit API."""
        self.stop_and_idle()

    def restore_explicit_orders(
        self,
        current_order: Optional[Order],
        queued_orders: Iterable[Order],
        galaxy_ref: Optional['Galaxy'] = None,
    ) -> None:
        """Restore serialized foreground roots without replaying side effects."""
        self.suspend_stance_activity("loaded explicit order")
        self.current_order = current_order
        self.orders_queue = deque(queued_orders)
        if galaxy_ref is None:
            galaxy_ref = getattr(self.unit, "in_galaxy", None)
        if not self.current_order:
            # A malformed or hand-authored save may contain only queued roots.
            # Promote the first one immediately so it still outranks the
            # standing stance during the next movement phase.
            if self.orders_queue:
                if galaxy_ref:
                    self.start_next_order()
                else:
                    self.current_order = self.orders_queue.popleft()
            return
        if not galaxy_ref:
            return
        if self.current_order.status == OrderStatus.PENDING:
            self.current_order.execute(galaxy_ref)
        elif self.current_order.status == OrderStatus.IN_PROGRESS:
            self.current_order.resume(galaxy_ref)

    def _active_front_chain(self) -> Iterable[Order]:
        root = self.get_active_order_root()
        current: Optional[Order] = root
        while current is not None and current.status in {OrderStatus.PENDING, OrderStatus.IN_PROGRESS}:
            yield current
            sub_orders = getattr(current, "sub_orders", None)
            if not sub_orders:
                break
            child = sub_orders[0]
            if child.status not in {OrderStatus.PENDING, OrderStatus.IN_PROGRESS}:
                break
            current = child

    def is_order_on_active_front_chain(self, target: Optional[Order]) -> bool:
        """Return whether ``target`` is the active root/front-child path.

        Cancellation needs this status-agnostic traversal because ``Order.cancel``
        marks a parent cancelled before recursively cancelling its children. The
        normal authority traversal intentionally filters cancelled orders; this
        helper is only for deciding which child may release component state while
        that cancellation is being unwound.
        """
        if target is None:
            return False
        current: Optional[Order] = self.get_active_order_root()
        while current is not None:
            if current is target:
                return True
            sub_orders = getattr(current, "sub_orders", None)
            if not sub_orders:
                return False
            current = sub_orders[0]
        return False

    def get_active_attack_order(self) -> Optional[Order]:
        """Return the Attack order authorized to control the unit's turrets.

        A direct Attack remains authoritative while it runs its own movement
        sub-orders.  Patrol, Protect, and Defend may also authorize their active
        front Attack sub-order.  Queued and finished orders never authorize fire.
        """
        for order in self._active_front_chain():
            if order.order_type == OrderType.ATTACK and order.status == OrderStatus.IN_PROGRESS:
                return order
        return None

    def _clear_weapon_target(self) -> None:
        """Clear any cached turret target after current-order authority ends."""
        weapons = self.unit.weapons_component
        if weapons:
            weapons.clear_target()

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
            self._clear_weapon_target()
            self.start_next_order()
            return True

        for order_in_queue in list(self.orders_queue):
            if order_in_queue.order_id == order_id:
                order_in_queue.cancel()
                self.orders_queue.remove(order_in_queue)
                return True
        return False

    def get_active_orders_count(self) -> int:
        """Get the total number of active orders (current + queued).

        Returns:
            The number of active orders
        """
        return (
            len(self.orders_queue)
            + (1 if self.current_order else 0)
            + (1 if self.standing_order.has_engagement else 0)
        )

    def prepare_for_movement(self) -> None:
        """Invalidate stance scope and reject actuator targets without an active owner."""
        galaxy_ref: Optional['Galaxy'] = (
            getattr(self.unit, "in_galaxy", None)
            or getattr(getattr(self.unit, "game", None), "galaxy", None)
        )
        # Capability loss invalidates the selected standing policy even while an
        # explicit foreground order is running; the explicit order itself is not
        # interrupted, but the stale stance cannot resume later.
        if self.stance not in self.get_allowed_stances():
            self.set_stance(UnitStance.DO_NOTHING)
        elif galaxy_ref and not self.current_order:
            self.standing_order.validate_engagement(galaxy_ref)
        elif galaxy_ref and getattr(self.current_order, "order_type", None) == OrderType.ATTACK:
            target_id = self.current_order.parameters.get("target_unit_id")
            target = galaxy_ref.get_unit_by_id(target_id) if target_id is not None else None
            from entities import are_enemies
            weapons = self.unit.weapons_component
            if (
                target is None
                or target.current_hit_points <= 0
                or not are_enemies(self.unit.owner, target.owner)
                or not weapons
                or not weapons.eligible_turrets_for(target)
            ):
                self.cancel_order(self.current_order.order_id)

        # A Do Nothing standing policy must not leave a stale weapon lock from
        # an order that was removed by an external integration.
        if not self.current_order and self.stance == UnitStance.DO_NOTHING:
            self._clear_weapon_target()

        active_ids = {
            order.order_id
            for order in self._active_front_chain()
            if order.status == OrderStatus.IN_PROGRESS
            and order.order_type == OrderType.REACH_WAYPOINT
        }
        engines = self.unit.engines_component
        if engines and engines.move_target is not None and engines.move_target_order_id not in active_ids:
            logger.debug(
                "[%s (id:%s)] Commander: clearing orphaned engine target owned by order %s.",
                self.unit.name,
                self.unit.id,
                engines.move_target_order_id,
            )
            engines.clear_move_target()
        drive = self.unit.hyperdrive_component
        if (
            drive
            and (drive.hex_jump_target is not None or drive.wormhole_jump_target is not None)
            and drive.jump_target_order_id not in active_ids
        ):
            logger.debug(
                "[%s (id:%s)] Commander: clearing orphaned hyperdrive target owned by order %s.",
                self.unit.name,
                self.unit.id,
                drive.jump_target_order_id,
            )
            drive.clear_jump_target()

    def update(self) -> None:
        """Process the current order and update its status.

        This method should be called on each game update cycle.
        """
        if not self.current_order:
            self.start_next_order()
            if not self.current_order:
                self.process_stance()
                return

        galaxy_ref: Optional['Galaxy'] = (
            getattr(self.unit, 'in_galaxy', None)
            or getattr(getattr(self.unit, 'game', None), 'galaxy', None)
        )

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
            self._clear_weapon_target()
            self.start_next_order()
            if not self.current_order:
                logger.debug("[%s (id:%s)] Commander: resuming standing stance.", self.unit.name, self.unit.id)
                self.process_stance()

    def start_next_order(self) -> None:
        """Starts the next order from the queue if available."""
        if not self.current_order and self.orders_queue:
            self.current_order = self.orders_queue.popleft()
            self._clear_weapon_target()
            
            galaxy_ref: Optional['Galaxy'] = (
                getattr(self.unit, 'in_galaxy', None)
                or getattr(getattr(self.unit, 'game', None), 'galaxy', None)
            )

            if galaxy_ref:
                if self.current_order.status == OrderStatus.PENDING:
                    self.current_order.execute(galaxy_ref=galaxy_ref)
                elif self.current_order.status == OrderStatus.IN_PROGRESS:
                    self.current_order.resume(galaxy_ref=galaxy_ref)
                if self.current_order and self.current_order.status == OrderStatus.IN_PROGRESS:
                    self.current_order.update(galaxy_ref=galaxy_ref)
            else:
                unit_name = getattr(self.unit, 'name', f"Unit ID {getattr(self.unit, 'id', 'Unknown')}")
                logger.debug(f"Error: [{unit_name}] Commander Component START_NEXT_ORDER: Cannot execute order, unit.in_galaxy is None.")
                if self.current_order:
                    self.current_order.status = OrderStatus.FAILED
