import logging
from typing import Dict, Optional, Any, TYPE_CHECKING

from geometry import distance
from .base import Order, OrderStatus, OrderType
from .movement import MoveOrder

if TYPE_CHECKING:
    from galaxy import Galaxy
    from entities import Unit

logger = logging.getLogger(__name__)


class TransferAntimatterOrder(Order):
    """Transfers antimatter from this unit's own AntimatterStorage into a
    friendly target unit's AntimatterStorage. This is how units without an
    AntimatterHarvester component are replenished: another unit (typically
    a harvester, but any unit with stored antimatter) must fly over and
    transfer some of its reserves.

    Modeled on RepairOrder: approaches the target if out of range, then
    transfers ANTIMATTER_TRANSFER_RATE per turn until the target is full
    or the source is depleted.
    """
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.TRANSFER_ANTIMATTER, parameters, parent_order)

    def get_state_data(self) -> Dict[str, Any]:
        state_data = super().get_state_data()
        target_unit_id = self.parameters.get("target_unit_id")
        target_name = None
        lookup_attempted = False
        lookup_success = False
        if target_unit_id and self.unit and self.unit.game:
            lookup_attempted = True
            target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id)
            if target_unit:
                target_name = target_unit.name
                lookup_success = True
        state_data["target_unit_id"] = target_unit_id
        state_data["target_name"] = target_name
        state_data["lookup_attempted"] = lookup_attempted
        state_data["lookup_success"] = lookup_success
        return state_data

    def _get_transfer_range(self) -> float:
        from constants import ANTIMATTER_TRANSFER_RANGE
        return ANTIMATTER_TRANSFER_RANGE

    def _do_transfer_tick(self, target_unit: 'Unit') -> None:
        """Performs a single turn's worth of antimatter transfer from this unit to the target."""
        from constants import ANTIMATTER_TRANSFER_RATE, ANTIMATTER_HARVESTER_RETURN_THRESHOLD
        source_am = self.unit.antimatter_component
        target_am = target_unit.antimatter_component
        if not source_am or not target_am:
            return
        if getattr(self.unit, 'harvester_component', None):
            available_am = max(0.0, source_am.current_amount - ANTIMATTER_HARVESTER_RETURN_THRESHOLD)
        else:
            available_am = source_am.current_amount
        amount_to_send = min(ANTIMATTER_TRANSFER_RATE, available_am)
        if amount_to_send <= 0:
            return
        added = target_am.add(amount_to_send)
        if added > 0:
            source_am.consume(added)
            logger.debug(f"TRANSFER_ANTIMATTER: {self.unit.name} transferred {added:.1f} antimatter to {target_unit.name}. "
                         f"Source: {source_am.current_amount:.1f}/{source_am.max_capacity:.1f}, "
                         f"Target: {target_am.current_amount:.1f}/{target_am.max_capacity:.1f}")

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        if not self.unit.antimatter_component:
            self.fail("execution_failed")
            logger.debug(f"TRANSFER_ANTIMATTER order failed: Unit {self.unit.name} has no AntimatterStorage.")
            return

        target_unit_id = self.parameters.get("target_unit_id")
        target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id)

        if not target_unit:
            self.fail("target_unavailable")
            logger.debug(f"TRANSFER_ANTIMATTER order failed: Target unit {target_unit_id} not found.")
            return

        from entities import are_allies
        if not are_allies(self.unit.owner, target_unit.owner):
            self.fail("target_unavailable")
            logger.debug(f"TRANSFER_ANTIMATTER order failed: Target unit {target_unit.name} is not friendly/allied.")
            return

        if not target_unit.antimatter_component:
            self.fail("target_unavailable")
            logger.debug(f"TRANSFER_ANTIMATTER order failed: Target unit {target_unit.name} has no AntimatterStorage.")
            return

        transfer_range = self._get_transfer_range()
        in_same_system_and_hex = (self.unit.in_system == target_unit.in_system and self.unit.in_hex == target_unit.in_hex)
        in_range = in_same_system_and_hex and (distance(self.unit.position, target_unit.position) <= transfer_range)

        if not in_range:
            self.add_sub_order(MoveOrder.for_unit_approach(
                self.unit,
                target_unit,
                transfer_range - 5.0,
                parent_order=self,
            ))

    def update(self, galaxy_ref: 'Galaxy') -> None:
        super().update(galaxy_ref)

        if self.status != OrderStatus.IN_PROGRESS:
            return
        if self.sub_orders:
            # Still approaching the target unit.
            return

        target_unit_id = self.parameters.get("target_unit_id")
        target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id) if target_unit_id else None

        from entities import are_allies
        if (not target_unit or not are_allies(self.unit.owner, target_unit.owner) or
                not target_unit.antimatter_component or not self.unit.antimatter_component):
            self.status = OrderStatus.FAILED
            return

        transfer_range = self._get_transfer_range()
        in_same_system_and_hex = (self.unit.in_system == target_unit.in_system and self.unit.in_hex == target_unit.in_hex)
        in_range = in_same_system_and_hex and (distance(self.unit.position, target_unit.position) <= transfer_range)

        if not in_range:
            # Target moved away since we last checked; re-approach.
            self.add_sub_order(MoveOrder.for_unit_approach(
                self.unit,
                target_unit,
                transfer_range - 5.0,
                parent_order=self,
            ))
            return

        self._do_transfer_tick(target_unit)
        self.check_completion_conditions()

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return

        target_unit_id = self.parameters.get("target_unit_id")
        target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id) if target_unit_id else None

        source_am = self.unit.antimatter_component
        target_am = target_unit.antimatter_component if target_unit else None

        if not target_unit or not source_am or not target_am:
            self.status = OrderStatus.COMPLETED
            return

        from constants import ANTIMATTER_HARVESTER_RETURN_THRESHOLD
        min_reserve = ANTIMATTER_HARVESTER_RETURN_THRESHOLD if getattr(self.unit, 'harvester_component', None) else 0.0

        # Complete once the source drops to or below min reserve, or target is fully topped up.
        if source_am.current_amount <= min_reserve or target_am.current_amount >= target_am.max_capacity:
            self.status = OrderStatus.COMPLETED
            logger.debug(f"TRANSFER_ANTIMATTER order completed: {self.unit.name} -> {target_unit.name}.")


class ContinuousResupplyOrder(Order):
    """Automates the harvest → transfer → return cycle for antimatter harvester units.

    The harvester will:
    1. Move to the target star and wait (passively harvesting) until its own
       AntimatterStorage is full.
    2. Find the closest friendly unit that has AntimatterStorage with available
       space and issue a TransferAntimatterOrder to it.
    3. Return to the star and repeat.

    If no friendly unit needs antimatter the harvester idles patiently at the
    star (order stays IN_PROGRESS) rather than failing, so it can react as
    soon as demand arises.
    """

    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.CONTINUOUS_RESUPPLY, parameters, parent_order)

    # ------------------------------------------------------------------
    # Sub-order factories
    # ------------------------------------------------------------------

    def _spawn_harvest_move(self, star: 'CelestialBody') -> None:
        """Issue a MoveOrder to travel to (or remain at) the target star."""
        move_params = {
            "destination_system_name": star.in_system,
            "destination_hex_coord": star.in_hex,
            "destination_position": star.position,
        }
        self.add_sub_order(MoveOrder(self.unit, move_params, parent_order=self))

    def _spawn_transfer_order(self, target_unit_id) -> None:
        transfer_params = {"target_unit_id": target_unit_id}
        self.add_sub_order(TransferAntimatterOrder(self.unit, transfer_params, parent_order=self))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_star(self, galaxy_ref: 'Galaxy') -> Optional['CelestialBody']:
        """Return the target Star object, or None if not found."""
        target_id = self.parameters.get("target_id")
        if target_id is None:
            return None
        return galaxy_ref.get_celestial_body_by_id(target_id)

    def _is_at_star(self, star: 'CelestialBody') -> bool:
        """True when the harvester is in the same system+hex as the star."""
        return (self.unit.in_system == star.in_system and
                self.unit.in_hex == star.in_hex)

    def _storage_is_full(self) -> bool:
        am = self.unit.antimatter_component
        if not am:
            return False
        return am.current_amount >= am.max_capacity

    def _find_closest_needy_unit(self, galaxy_ref: 'Galaxy') -> Optional['Unit']:
        """Return the closest friendly unit that has AntimatterStorage with space,
        excluding the harvester itself and units that are already full."""
        from geometry import hex_distance
        from pathfinding import find_intersystem_path

        needy: list = []
        for system in galaxy_ref.systems.values():
            for hex_obj in system.hexes.values():
                for u in hex_obj.units:
                    if u is self.unit:
                        continue
                    if u.owner != self.unit.owner:
                        continue
                    am = getattr(u, 'antimatter_component', None)
                    if am and am.current_amount < am.max_capacity:
                        needy.append(u)

        if not needy:
            return None

        def get_dist(candidate):
            if self.unit.in_system == candidate.in_system:
                if self.unit.in_hex == candidate.in_hex:
                    from geometry import distance as geo_distance
                    return geo_distance(self.unit.position, candidate.position)
                else:
                    return hex_distance(self.unit.in_hex, candidate.in_hex) * 10000.0
            else:
                path = find_intersystem_path(
                    galaxy_ref.system_graph,
                    self.unit.in_system,
                    candidate.in_system,
                    self.unit.hull_size
                )
                if path is None:
                    return float('inf')
                return (len(path) - 1) * 1_000_000.0 + hex_distance(self.unit.in_hex, candidate.in_hex) * 10000.0

        return min(needy, key=get_dist)

    def _decide_next_step(self, galaxy_ref: 'Galaxy') -> None:
        """Choose whether to go harvest or go transfer, and spawn the sub-order."""
        star = self._get_star(galaxy_ref)
        if not star:
            self.fail("target_unavailable")
            logger.debug(f"[{self.unit.name}] CONTINUOUS_RESUPPLY: target star not found, order failed.")
            return

        from constants import ANTIMATTER_HARVESTER_RETURN_THRESHOLD
        am = self.unit.antimatter_component
        current_reserve = am.current_amount if am else 0.0

        if current_reserve <= ANTIMATTER_HARVESTER_RETURN_THRESHOLD:
            logger.debug(f"[{self.unit.name}] CONTINUOUS_RESUPPLY: reserve low ({current_reserve:.1f} <= {ANTIMATTER_HARVESTER_RETURN_THRESHOLD}), heading to star to harvest.")
            if not self._is_at_star(star):
                self._spawn_harvest_move(star)
        else:
            can_supply = self._storage_is_full() if self._is_at_star(star) else True
            target_unit = self._find_closest_needy_unit(galaxy_ref) if can_supply else None
            if target_unit:
                logger.debug(f"[{self.unit.name}] CONTINUOUS_RESUPPLY: heading to resupply {target_unit.name}.")
                self._spawn_transfer_order(target_unit.id)
            else:
                logger.debug(f"[{self.unit.name}] CONTINUOUS_RESUPPLY: no needy units found or filling up at star; heading to/idling at star.")
                if not self._is_at_star(star):
                    self._spawn_harvest_move(star)

    # ------------------------------------------------------------------
    # Order interface
    # ------------------------------------------------------------------

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        if not self.unit.harvester_component:
            self.fail("execution_failed")
            logger.debug(f"[{self.unit.name}] CONTINUOUS_RESUPPLY order failed: unit has no AntimatterHarvester component.")
            return

        if not self.unit.antimatter_component:
            self.fail("execution_failed")
            logger.debug(f"[{self.unit.name}] CONTINUOUS_RESUPPLY order failed: unit has no AntimatterStorage component.")
            return

        target_id = self.parameters.get("target_id")
        if target_id is None:
            self.fail("invalid_parameters")
            logger.debug(f"[{self.unit.name}] CONTINUOUS_RESUPPLY order failed: no target_id.")
            return

        star = self._get_star(galaxy_ref)
        if not star:
            self.fail("target_unavailable")
            logger.debug(f"[{self.unit.name}] CONTINUOUS_RESUPPLY order failed: target star (id={target_id}) not found.")
            return

        self._decide_next_step(galaxy_ref)

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return
        if self.sub_orders:
            return

        # No sub-orders pending — time to decide what to do next.
        galaxy_ref = self.unit.game.galaxy
        self._decide_next_step(galaxy_ref)
