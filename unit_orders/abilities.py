from unit_orders.base import OrderTargetField
import logging
from game_logging import format_unit_for_log
from typing import Dict, Optional, Any, TYPE_CHECKING

from geometry import distance, position_at_distance_from_target, is_point_in_circle
from .base import Order, OrderStatus, OrderType
from .movement import MoveOrder

if TYPE_CHECKING:
    from galaxy import Galaxy
    from domain.units import Unit

logger = logging.getLogger(__name__)


class UseAbilityOrder(Order):
    """
    Order to activate a unit's special ability.

    Ordinary unit targets and ranged position effects such as Cluster Warhead
    create approach suborders when out of range. Tactical unit links also
    approach; tactical position casts and carrier/anti-strikecraft casts require
    local range without approach. Microjump stays within the current sector.
    Self-targeted abilities require neither a unit nor a position target.
    """
    target_fields = (OrderTargetField('target_unit_id', 'unit', public=True), OrderTargetField('target_body_id', 'celestial', public=True))

    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.USE_ABILITY, parameters, parent_order)

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        """Validate and start this cast, creating approach work when allowed.

        Read the order's ability/target/location parameters against the live galaxy
        and equipment. Ordinary ranged targets and tactical unit links may append
        Move plus retry-cast children, leaving this root in progress until they
        run. Tactical position and carrier casts require local range; Microjump
        requires the current sector and self casts need no approach.

        In range, delegate activation, payment, effects and cooldowns to the
        ability service/component. Successful activation completes the order;
        invalid input, unavailable equipment or rejected activation fails it.
        Some ordinary failures display GUI warnings. Return None; unexpected
        activation exceptions propagate without promising reversal of effects.
        """
        from location_validation import validate_order
        if not validate_order(self, galaxy_ref):
            return
        super().execute(galaxy_ref)

        from unit_components.enums import AbilityType

        if not self.unit.ability_component:
            logger.debug(f"[{format_unit_for_log(self.unit)}] USE_ABILITY order failed: unit has no AbilityComponent.")
            self.fail("ability_unavailable")
            return

        ability_type_str = self.parameters.get("ability_type")
        if not ability_type_str:
            logger.debug(f"[{format_unit_for_log(self.unit)}] USE_ABILITY order failed: no ability_type parameter.")
            self.fail("ability_unavailable")
            return

        try:
            ability_type = AbilityType(ability_type_str)
        except ValueError:
            logger.debug(f"[{format_unit_for_log(self.unit)}] USE_ABILITY order failed: unknown ability_type '{ability_type_str}'.")
            self.fail("ability_unavailable")
            return

        from titan_balance import TITAN_ABILITIES
        if ability_type_str in TITAN_ABILITIES:
            # Remain in progress; only the dedicated owner phase may pay/cast.
            return

        from tactical_balance import STRIKECRAFT_ABILITIES
        if ability_type_str in STRIKECRAFT_ABILITIES:
            from tactical_abilities import validate, activate
            target = self.parameters.get('target_unit_id')
            blocker = validate(self.unit, ability_type_str, galaxy_ref, target,
                               self.parameters.get('target_position'), ignore_reservations=True)
            if blocker:
                self.fail(blocker)
            elif activate(self.unit, ability_type_str, galaxy_ref, target):
                self.status = OrderStatus.COMPLETED
            else:
                self.fail('execution_failed')
            return

        if not self.unit.ability_component.can_use(ability_type, ignore_reservations=True):
            logger.debug(f"[{format_unit_for_log(self.unit)}] USE_ABILITY order failed: ability {ability_type.name} not ready (on cooldown or already active).")
            gui = getattr(getattr(self.unit, 'game', None), 'gui', None)
            if gui:
                gui.show_warning_dialog(
                    f"Ability <b>{ability_type.name}</b> on unit <b>{self.unit.name}</b> is on cooldown or cannot be activated.",
                    title="Ability Unavailable"
                )
            self.fail("ability_unavailable")
            return

        from unit_components.abilities import ABILITY_DEFINITIONS
        defn = ABILITY_DEFINITIONS.get(ability_type)
        if not defn:
            self.fail("ability_unavailable")
            return

        target_unit_id = self.parameters.get("target_unit_id")
        target_position = self.parameters.get("target_position")

        from tactical_abilities import SPECS, validate
        if ability_type.value in SPECS:
            spec = SPECS[ability_type.value]
            target_id = self.parameters.get('target_body_id') if spec.target_kind == 'celestial_position' else target_unit_id
            error = validate(self.unit, ability_type.value, galaxy_ref, target_id, target_position, approach=spec.target_kind == 'unit', ignore_reservations=True)
            if error:
                self.fail(error)
                return
            if spec.target_kind != 'unit':
                success = self.unit.ability_component.activate(ability_type, galaxy_ref,
                    target_position=target_position, target_body_id=target_id,
                    target_system_name=self.parameters.get('target_system_name'), target_hex_coord=self.parameters.get('target_hex_coord'))
                if success:
                    self.status = OrderStatus.COMPLETED
                else:
                    self.fail('execution_failed')
                return

        from unit_targeting import legacy_target_blocker
        target = galaxy_ref.get_unit_by_id(target_unit_id) if target_unit_id is not None else None
        if ability_type == AbilityType.CAPTURE_UNIT and target is not None:
            from constants import HullSize
            from titan_acquisition import blocker
            if target.hull_size == HullSize.TITAN and blocker(galaxy_ref, self.unit.owner, exclude_order=self):
                self.fail("titan_limit_reached")
                return
        error = legacy_target_blocker(self.unit, ability_type.value, target, galaxy_ref, execution=True, check_path=False)
        if error:
            if error == "target_not_disabled":
                gui = getattr(getattr(self.unit, 'game', None), 'gui', None)
                if gui:
                    gui.show_warning_dialog("Cannot capture target: Unit engines, weapons, and defenses must be disabled first!", title="Capture Failed")
            self.fail(error)
            return

        # --- Pre-validation for MICROJUMP ability ---
        if ability_type == AbilityType.MICROJUMP:
            if target_position is not None:
                target_sys = self.parameters["target_system_name"]
                target_hex = self.parameters["target_hex_coord"]

                # Microjump is strictly intra-sector
                if target_sys != self.unit.in_system or target_hex != self.unit.in_hex:
                    logger.debug(f"[{format_unit_for_log(self.unit)}] USE_ABILITY (Microjump) failed: target is in a different sector.")
                    gui = getattr(getattr(self.unit, 'game', None), 'gui', None)
                    if gui:
                        gui.show_warning_dialog(
                            f"Cannot microjump unit <b>{self.unit.name}</b>: Target position is in a different sector. Microjumps are restricted to the local sector.",
                            title="Microjump Failed"
                        )
                    self.fail("target_out_of_range")
                    return

                system = galaxy_ref.systems.get(self.unit.in_system) if galaxy_ref else None
                hex_obj = system.hexes.get(self.unit.in_hex) if system else None
                if hex_obj:
                    inhibition_zones = hex_obj.get_all_inhibition_zones()
                    for zone in inhibition_zones:
                        if is_point_in_circle(self.unit.position, zone):
                            logger.debug(f"[{format_unit_for_log(self.unit)}] USE_ABILITY (Microjump) failed: origin position is inside an inhibition field.")
                            gui = getattr(getattr(self.unit, 'game', None), 'gui', None)
                            if gui:
                                gui.show_warning_dialog(
                                    f"Cannot microjump unit <b>{self.unit.name}</b>: Origin position is inside a hyperspace inhibition field.",
                                    title="Microjump Failed"
                                )
                            self.fail("jump_inhibited")
                            return
                        if is_point_in_circle(target_position, zone):
                            logger.debug(f"[{format_unit_for_log(self.unit)}] USE_ABILITY (Microjump) failed: destination position is inside an inhibition field.")
                            gui = getattr(getattr(self.unit, 'game', None), 'gui', None)
                            if gui:
                                gui.show_warning_dialog(
                                    f"Cannot microjump unit <b>{self.unit.name}</b>: Destination position is inside a hyperspace inhibition field.",
                                    title="Microjump Failed"
                                )
                            self.fail("jump_inhibited")
                            return

        # --- Range check for unit-targeted abilities ---
        if defn.requires_target_unit and target_unit_id is not None:
            target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id)
            if not target_unit or target_unit.current_hit_points <= 0:
                logger.debug(f"[{format_unit_for_log(self.unit)}] USE_ABILITY: target unit {target_unit_id} not found or dead.")
                self.fail("target_unavailable")
                return

            in_same_hex = (self.unit.in_system == target_unit.in_system and
                           self.unit.in_hex == target_unit.in_hex)
            in_range = in_same_hex and (distance(self.unit.position, target_unit.position) <= defn.range)

            if not in_range:
                if not self.has_active_sub_orders():
                    self.add_sub_order(MoveOrder.for_unit_approach(
                        self.unit,
                        target_unit,
                        defn.range - 5.0,
                        parent_order=self,
                    ))
                    # Re-queue this ability order to fire once in range
                    self.add_sub_order(UseAbilityOrder(self.unit, self.parameters, parent_order=self))
                return

        # --- Range check for position-targeted projectile/effect abilities (e.g. Cluster Warhead) ---
        elif defn.requires_target_position and target_position is not None and ability_type != AbilityType.MICROJUMP:
            target_sys = self.parameters["target_system_name"]
            target_hex = self.parameters["target_hex_coord"]

            in_same_hex = (self.unit.in_system == target_sys and
                           self.unit.in_hex == target_hex)
            in_range = in_same_hex and (distance(self.unit.position, target_position) <= defn.range)

            if not in_range:
                if not self.has_active_sub_orders():
                    if in_same_hex:
                        dest_pos = position_at_distance_from_target(self.unit.position, target_position, defn.range - 5.0)
                    else:
                        dest_pos = target_position
                    
                    move_params = {
                        "destination_system_name": target_sys,
                        "destination_hex_coord": target_hex,
                        "destination_position": dest_pos,
                    }
                    self.add_sub_order(MoveOrder(self.unit, move_params, parent_order=self))
                    # Re-queue this ability order to fire once in range
                    self.add_sub_order(UseAbilityOrder(self.unit, self.parameters, parent_order=self))
                return

        # --- Activate the ability ---
        success = self.unit.ability_component.activate(
            ability_type=ability_type,
            galaxy=galaxy_ref,
            target_unit_id=target_unit_id,
            target_position=target_position,
            target_system_name=self.parameters.get("target_system_name"),
            target_hex_coord=self.parameters.get("target_hex_coord"),
        )
        if success:
            logger.debug(f"[{format_unit_for_log(self.unit)}] USE_ABILITY: {ability_type.name} activated successfully.")
            self.status = OrderStatus.COMPLETED
        else:
            logger.debug(f"[{format_unit_for_log(self.unit)}] USE_ABILITY: {ability_type.name} activation failed.")
            self.fail("capture_resisted" if ability_type == AbilityType.CAPTURE_UNIT else "ability_unavailable")

    def cancel(self) -> None:
        super().cancel()
        from titan_abilities import cancel, instance
        if self.parameters.get("ability_type") == "siege_lance":
            inst = instance(self.unit, "siege_lance")
            if inst and inst.order_id == self.public_id:
                cancel(self.unit, "siege_lance")

    def check_completion_conditions(self) -> None:
        from titan_balance import TITAN_ABILITIES
        if self.parameters.get("ability_type") in TITAN_ABILITIES:
            return
        if self.status != OrderStatus.IN_PROGRESS:
            return
        if not self.sub_orders:
            self.status = OrderStatus.COMPLETED
