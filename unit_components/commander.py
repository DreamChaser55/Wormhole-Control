import logging
from game_logging import format_unit_for_log
from typing import Optional, Deque, TYPE_CHECKING, Iterable
from collections import deque
import dataclasses

from .base import UnitComponent
from .enums import UnitStance
from unit_orders.base import Order, OrderStatus, OrderType
from unit_orders.stance import StanceOrder

if TYPE_CHECKING:
    from domain.units import Unit
    from galaxy import Galaxy
    from game import Game

logger = logging.getLogger(__name__)

@dataclasses.dataclass
class Commander(UnitComponent):
    """Commander is a component responsible for managing and executing orders for a Unit.

    This component maintains a queue of orders and processes them in sequence,
    handling the execution and status updates of each order.
    """
    STATE_CONFIG = ('stance',)
    STATE_RUNTIME = ()
    STATE_REFS = ()
    STATE_EXTRA = ("current_order", "orders_queue")

    def _extra_state(self):
        from save_manager import serialize_order
        return {"current_order": serialize_order(self.current_order) if self.current_order else None,
                "orders_queue": [serialize_order(o) for o in self.orders_queue]}

    def _restore_extra_state(self, runtime):
        self.unit._saved_commander_data = {"stance": self.stance.value,
                                           "current_order": runtime["current_order"],
                                           "orders_queue": runtime["orders_queue"]}

    DISPLAY_NAME: str = "Commander"
    SIDEBAR_ORDER: int = 0
    current_order: Optional[Order] = None
    orders_queue: Deque[Order] = dataclasses.field(default_factory=deque)
    standing_order: StanceOrder = dataclasses.field(init=False)
    _stance: UnitStance = dataclasses.field(init=False, default=UnitStance.DO_NOTHING)

    def __init__(self, unit: 'Unit'):
        super().__init__(unit, hull_cost=0)
        self.current_order = None
        self._restored_pending = None
        self.orders_queue = deque()
        self._stance = UnitStance.DO_NOTHING
        self.standing_order = StanceOrder(unit, {"stance": self._stance.value})

    @property
    def stance(self) -> UnitStance:
        """Assignments use the stance lifecycle safely."""
        return self._stance

    @stance.setter
    def stance(self, stance: UnitStance) -> None:
        self.set_stance(stance)

    @property
    def supports_stances(self) -> bool:
        """Installed turrets support policy selection even while damaged or cooling."""
        weapons = self.unit.weapons_component
        return weapons is not None and bool(weapons.turrets)

    def reconcile_stance_capability(self) -> None:
        """Restore the unarmed invariant without issuing commands or clearing work."""
        if not self.supports_stances:
            self.suspend_stance_activity("weapons removed")
            self._replace_stance(UnitStance.DO_NOTHING)

    def get_allowed_stances(self) -> list[UnitStance]:
        """Gets the list of allowed stances for this unit based on its components."""
        if not self.supports_stances:
            return [UnitStance.DO_NOTHING]
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
        self.reconcile_stance_capability()
        from strikecraft_service import required
        if required(self.unit):
            return
        from dismantling import offline
        if offline(self.unit) or self.current_order or self.orders_queue:
            return
        galaxy_ref: Optional['Galaxy'] = (
            getattr(self.unit, 'in_galaxy', None)
            or getattr(getattr(self.unit, 'game', None), 'galaxy', None)
        )
        if galaxy_ref:
            self.standing_order.update(galaxy_ref)


    def get_basic_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_basic_sidebar_data(game_state)
        from component_visibility import unit_details_are_public_in_game
        if not unit_details_are_public_in_game(self.unit, game_state):
            return data
        if self.is_destroyed:
            return data
        from dismantling import state_view
        dismantling = state_view(self.unit)
        if dismantling:
            data.append({'type': 'label', 'text': 'Dismantling: ' + (dismantling['waiting_reason'] or dismantling['phase']).replace('_', ' '),
                         'object_id': '#sidebar_info_label', 'height': 25})
            data.append({'type': 'progress_bar', 'progress': dismantling['turns_completed'],
                         'total': dismantling['turns_required'], 'height': 25})
            if self.unit.owner == game_state.players[game_state.current_player_index]:
                data.append({'type': 'button', 'text': 'Cancel dismantling', 'object_id': '#sidebar_expand_button',
                             'action_id': 'cancel_dismantling',
                             'target_data': (dismantling['executor_id'], dismantling['order_id']), 'height': 25})
        orders_count = self.get_active_orders_count()
        if self.current_order:
            curr_name = self.current_order.order_type.name.replace('_', ' ').title()
        elif self.standing_order.has_engagement:
            curr_name = "Standing Attack"
        else:
            curr_name = "None"
        obj_id = '#sidebar_status_active_label' if orders_count > 0 else '#sidebar_value_label'
        stance_prefix = f"Stance: [{self.stance.display_name}] | " if self.supports_stances else ""
        data.append({
            'type': 'label',
            'text': f"• {stance_prefix}Order: {curr_name} ({orders_count} active)",
            'object_id': obj_id,
            'height': 18,
            'indent_level': 1
        })
        is_owned = (self.unit.owner == game_state.players[game_state.current_player_index])
        from strikecraft_service import required
        if is_owned and orders_count > 0 and not required(self.unit):
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
        from component_visibility import unit_details_are_public_in_game
        if not unit_details_are_public_in_game(self.unit, game_state):
            return super().get_sidebar_data(game_state)
        data = []

        is_owned = (self.unit.owner == game_state.players[game_state.current_player_index])
        from strikecraft_service import required
        if self.supports_stances:
            data.append({
                'type': 'label',
                'text': "Stance:",
                'object_id': '#sidebar_info_label',
                'height': 20,
                'indent_level': 0
            })
            if is_owned and not required(self.unit):
                data.append({
                    'type': 'drop_down_menu',
                    'options_list': [s.display_name for s in self.get_allowed_stances()],
                    'starting_option': self.stance.display_name,
                    'action_id': 'set_stance',
                    'target_data': self.unit.id,
                    'height': 25,
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
            data.append({
                'type': 'label',
                'text': "",
                'object_id': '#sidebar_info_label',
                'height': 5,
                'indent_level': 0
            })

        if is_owned and self.get_active_orders_count() > 0 and not required(self.unit):
            data.append({
                'type': 'button',
                'text': "Stop Unit",
                'object_id': '#sidebar_expand_button',
                'action_id': 'stop_unit',
                'target_data': self.unit.id,
                'height': 25,
                'indent_level': 0
            })

        if self.supports_stances:
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

    def add_order(self, order: Order, *, internal: bool = False) -> None:
        """Own an explicit root, suspend stance engagement, and append it FIFO.

        An idle commander starts it synchronously; execution may complete or mutate
        the world before return. Existing foreground work is preserved. Callers
        validate issuance first and use clear_explicit_orders for replacement.
        """
        from strikecraft_service import required
        if not internal and required(self.unit):
            order.fail('wing_service_required')
            return
        from dismantling import offline
        if offline(self.unit):
            order.fail('dismantling_conflict')
            return
        self.suspend_stance_activity("explicit order started")
        order.register_explicit_root()
        self.orders_queue.append(order)

        if self.current_order is None:
            self.start_next_order()

    def set_stance(self, stance: UnitStance, *, internal: bool = False) -> None:
        """Replace the standing policy without interrupting explicit work."""
        from strikecraft_service import required
        if not internal and required(self.unit):
            return
        from dismantling import offline
        if offline(self.unit):
            return
        if not isinstance(stance, UnitStance):
            raise TypeError("stance must be a UnitStance")
        self._replace_stance(stance)

    def _replace_stance(self, stance: UnitStance) -> None:
        """Engine policy replacement, also used by equipment reconciliation."""
        old_stance = getattr(self, "_stance", UnitStance.DO_NOTHING)
        old_order = getattr(self, "standing_order", None)
        # A normal assignment of the same policy is idempotent, but do not
        # leave a standing order permanently cancelled if an integration
        # cancelled/replaced the root directly.  Recreate the root in that
        # case so the ``stance`` property remains safe.
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
            "[%s] Commander: stance changed from %s to %s.",
            format_unit_for_log(self.unit),
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


    def suspend_stance_activity(self, reason: str = "suspended") -> None:
        """Cancel only the transient engagement while retaining its policy."""
        if self.standing_order.has_engagement:
            logger.debug(
                "[%s] Commander: suspending stance activity (%s).",
                format_unit_for_log(self.unit),
                reason,
            )
            self.standing_order.cancel_engagement(reason)

    def _release_current_order(self) -> None:
        """Release foreground authority after its owner has settled/cancelled it.

        Queue promotion is deliberately separate: hidden ships and bulk cancellation
        must not execute the next root while releasing the previous one.
        """
        self.current_order = None
        self._clear_weapon_target()

    def clear_explicit_orders(self, *, internal: bool = False) -> None:
        """Cancel owned explicit roots without promoting any queued work.

        Concrete cancellation hooks release their own actuators/jobs and refund
        their own charges once. The standing policy remains selected and resumes
        through normal updates; this method returns no new execution result.
        """
        from strikecraft_service import required
        if not internal and required(self.unit):
            return
        if self.current_order:
            self.current_order.cancel()
            self._release_current_order()
        for order in self.orders_queue:
            order.cancel()
        self.orders_queue.clear()
        if not self.standing_order.has_engagement:
            self._clear_weapon_target()

    def stop_and_idle(self, *, internal: bool = False) -> None:
        """Cancel all work, clear component state, and select Do Nothing."""
        from strikecraft_service import required
        if not internal and required(self.unit):
            return
        self.clear_explicit_orders(internal=internal)
        self.suspend_stance_activity("unit stopped")
        self.set_stance(UnitStance.DO_NOTHING, internal=internal)
        if self.unit.engines_component:
            self.unit.engines_component.clear_move_target()
        if self.unit.hyperdrive_component:
            self.unit.hyperdrive_component.clear_jump_target()
        self._clear_weapon_target()


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
        for root in [current_order, *self.orders_queue]:
            if root is not None:
                root.register_explicit_root(restored=True)
        constructor = self.unit.constructor_component
        self._restored_pending = self.current_order if self.current_order and self.current_order.status == OrderStatus.PENDING else None
        if constructor and self.current_order:
            for node in self._active_front_chain():
                if node.order_type == OrderType.REFIT_UNIT and constructor.current_refit_target:
                    constructor.refit_order_id = node.public_id
        if galaxy_ref is None:
            galaxy_ref = getattr(self.unit, "in_galaxy", None)
        if (self.current_order and galaxy_ref and self.current_order.status == OrderStatus.IN_PROGRESS
                and not getattr(self.unit, 'is_hidden_in_gas_giant', False)):
            self.current_order.resume(galaxy_ref=galaxy_ref)

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
        from strikecraft_service import required
        if required(self.unit):
            return None
        root = self.current_order
        if root and root.order_type == OrderType.ATTACK_RUN and getattr(root, 'phase', None) != 'release':
            return None
        for order in self._active_front_chain():
            if order.order_type in {OrderType.ATTACK, OrderType.ATTACK_LONG_RANGE} and order.status == OrderStatus.IN_PROGRESS:
                return order
        return None

    def _clear_weapon_target(self) -> None:
        """Clear any cached turret target after current-order authority ends."""
        weapons = self.unit.weapons_component
        if weapons:
            weapons.clear_target()

    def attack_for_visibility_check(self) -> Optional[Order]:
        """The active engagement, including approach; Attack Run owns its own aborts."""
        from unit_orders.combat import AttackOrder
        if self.current_order and self.current_order.order_type == OrderType.ATTACK_RUN:
            return None
        return next((order for order in self._active_front_chain() if isinstance(order, AttackOrder)), None)

    def cancel_hidden_attack(self, galaxy_ref, visibility_snapshot=None) -> bool:
        """Cancellation only: never promote queued work or advance a parent mission."""
        attack = self.attack_for_visibility_check()
        cancelled = bool(attack and attack.cancel_if_target_not_visible(galaxy_ref, visibility_snapshot))
        root = self.current_order
        if root and root.status == OrderStatus.CANCELLED and root.failure_reason == "target_not_visible":
            self._release_current_order()
            cancelled = True
        return cancelled

    def cancel_order(self, local_order_id: int, *, promote_next: bool = True) -> bool:
        """Cancel an explicit root by its process-local ID.

        Args:
            local_order_id: Process-local Order.local_order_id, never a public UUID.
            promote_next: False settles cancellation without starting queued work.

        Returns:
            True if the order was found and cancelled, False otherwise
        """
        from strikecraft_service import required
        if required(self.unit):
            return False
        if self.current_order and self.current_order.local_order_id == local_order_id:
            self.current_order.cancel()
            self._release_current_order()
            if promote_next:
                self.start_next_order()
            return True

        for order_in_queue in list(self.orders_queue):
            if order_in_queue.local_order_id == local_order_id:
                order_in_queue.cancel()
                self.orders_queue.remove(order_in_queue)
                if promote_next and self.current_order is None:
                    self.start_next_order()
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
        self.reconcile_stance_capability()
        galaxy_ref: Optional['Galaxy'] = (
            getattr(self.unit, "in_galaxy", None)
            or getattr(getattr(self.unit, "game", None), "galaxy", None)
        )
        self.cancel_hidden_attack(galaxy_ref)
        from dismantling import offline
        if not self.unit.is_disabled and not offline(self.unit):
            # A turn-end cancellation deliberately did not activate this owner's
            # queue. Promote now so its next movement is ready for this phase.
            while not self.current_order and self.orders_queue:
                self.start_next_order()
                if not self.cancel_hidden_attack(galaxy_ref):
                    break
            root = self.get_active_order_root()
            if (root and root.sub_orders
                    and root.sub_orders[0].status == OrderStatus.CANCELLED
                    and root.sub_orders[0].failure_reason == "target_not_visible"):
                root.update(galaxy_ref)
        # Capability loss invalidates the selected standing policy even while an
        # explicit foreground order is running; the explicit order itself is not
        # interrupted, but the stale stance cannot resume later.
        if self.stance not in self.get_allowed_stances():
            self.set_stance(UnitStance.DO_NOTHING)
        elif galaxy_ref and not self.current_order:
            self.standing_order.validate_engagement(galaxy_ref)
        if galaxy_ref and getattr(self.current_order, "order_type", None) in {OrderType.ATTACK, OrderType.ATTACK_LONG_RANGE}:
            from tactical_abilities import combat_target
            target_id = self.current_order.parameters.get("target_unit_id")
            target = combat_target(galaxy_ref, target_id) if target_id is not None else None
            from domain.players import are_enemies
            weapons = self.unit.weapons_component
            if (
                target is None
                or target.current_hit_points <= 0
                or not are_enemies(self.unit.owner, target.owner)
            ):
                self.cancel_order(self.current_order.local_order_id)
            elif not weapons or self.current_order.approach_range(target) is None:
                # Let the order fail and release its approach before movement.
                self.current_order.update(galaxy_ref)

        # A Do Nothing standing policy must not leave a stale weapon lock from
        # an order that was removed by an external integration.
        if not self.current_order and self.stance == UnitStance.DO_NOTHING:
            self._clear_weapon_target()

        active_ids = {
            order.local_order_id
            for order in self._active_front_chain()
            if order.status == OrderStatus.IN_PROGRESS
            and order.order_type == OrderType.REACH_WAYPOINT
        }
        engines = self.unit.engines_component
        if engines and engines.move_target is not None and engines.move_target_order_id not in active_ids:
            logger.debug(
                "[%s] Commander: clearing orphaned engine target owned by order %s.",
                format_unit_for_log(self.unit),
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
                "[%s] Commander: clearing orphaned hyperdrive target owned by order %s.",
                format_unit_for_log(self.unit),
                drive.jump_target_order_id,
            )
            drive.clear_jump_target()

    def update(self) -> None:
        """Process the current order and update its status.

        This method should be called on each game update cycle.
        """
        from dismantling import offline
        if offline(self.unit):
            return
        if getattr(self.unit, 'is_hidden_in_gas_giant', False):
            self._update_hidden_orders()
            return
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
            if self.current_order is self._restored_pending and self.current_order.status == OrderStatus.PENDING:
                self._restored_pending = None
                self.current_order.execute(galaxy_ref=galaxy_ref)
            self.current_order.update(galaxy_ref=galaxy_ref)
        else:
            unit_name = format_unit_for_log(self.unit)
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
            self._release_current_order()
            self.start_next_order()
            if not self.current_order:
                logger.debug("[%s] Commander: resuming standing stance.", format_unit_for_log(self.unit))
                self.process_stance()

    def _update_hidden_orders(self) -> None:
        """Settle entry and process departure without running external work or stance.

        FIFO is intentional: a paused non-Leave root blocks later departures until
        the player cancels it or replaces the queue. No new persistence state is needed.
        """
        galaxy = getattr(self.unit, 'in_galaxy', None) or getattr(getattr(self.unit, 'game', None), 'galaxy', None)
        order = self.current_order
        if order and order.order_type == OrderType.ENTER_GAS_GIANT and order.status == OrderStatus.IN_PROGRESS:
            # Entry can have completed in an approach descendant during movement.
            order.update(galaxy_ref=galaxy)
        if self.current_order and self.current_order.status in {OrderStatus.COMPLETED, OrderStatus.FAILED, OrderStatus.CANCELLED}:
            self._release_current_order()
        if self.current_order is not None:
            if self.current_order.order_type != OrderType.LEAVE_GAS_GIANT:
                return
            if self.current_order.status == OrderStatus.PENDING:
                self.current_order.execute(galaxy_ref=galaxy)
            elif self.current_order.status == OrderStatus.IN_PROGRESS:
                self.current_order.update(galaxy_ref=galaxy)
        else:
            self.start_next_order()
        if not getattr(self.unit, 'is_hidden_in_gas_giant', False):
            self.update()

    def start_next_order(self) -> None:
        """Promote only the FIFO head when idle, respecting atmospheric blocking.

        Pending roots execute immediately; restored active roots resume bindings
        without replaying startup effects. Promotion may finish work synchronously.
        Outside-space work ahead of Leave stays queued while hidden.
        """
        if not self.current_order and self.orders_queue:
            if (getattr(self.unit, 'is_hidden_in_gas_giant', False)
                    and self.orders_queue[0].order_type != OrderType.LEAVE_GAS_GIANT):
                return
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
                if self.current_order and self.current_order.status == OrderStatus.IN_PROGRESS and self.current_order.update_on_start:
                    self.current_order.update(galaxy_ref=galaxy_ref)
            else:
                unit_name = format_unit_for_log(self.unit)
                logger.debug(f"Error: [{unit_name}] Commander Component START_NEXT_ORDER: Cannot execute order, unit.in_galaxy is None.")
                if self.current_order:
                    self.current_order.status = OrderStatus.FAILED
