import logging
from typing import Dict, Optional, Any, TYPE_CHECKING

from geometry import distance
from .base import Order, OrderStatus, OrderType
from .movement import MoveOrder
from custom_unit_templates import HULL_RESTRICTIONS, COMPONENT_COST_PER_HULL_POINT
from unit_components.constructor import get_component_class_by_name, get_component_hull_cost

if TYPE_CHECKING:
    from galaxy import Galaxy
    from entities import Unit

logger = logging.getLogger(__name__)


def get_hull_restriction_flag(component_name: str) -> str:
    flag_map = {
        "HangarComponent": "has_hangar",
        "Hangar": "has_hangar",
        "StrikecraftBayComponent": "has_strikecraft_bay",
        "StrikecraftBay": "has_strikecraft_bay",
        "HyperspaceInhibitionFieldEmitter": "has_inhibitor",
        "Inhibitor": "has_inhibitor",
        "Constructor": "has_constructor_component",
        "RepairComponent": "has_repair_component",
        "ColonyComponent": "has_colony_component",
        "CivilianHabitatComponent": "has_civilian_habitat_component",
        "OrbitalDefenseComponent": "has_orbital_defense_component",
        "OrbitalDefense": "has_orbital_defense_component",
        "TradeComponent": "has_trade_component",
        "Trade": "has_trade_component",
        "MetalRefineryComponent": "has_metal_refinery_component",
        "CrystalRefineryComponent": "has_crystal_refinery_component",
        "AbilityComponent": "has_ability_component",
        "AntimatterHarvester": "has_antimatter_harvester",
        "MinelayerComponent": "has_minelayer_component",
        "MarinesComponent": "has_marines_component",
        "CloakingDevice": "has_cloaking_device",
        "Hyperdrive": "has_hyperdrive",
        "IntelligenceComponent": "has_intelligence_component",
        "Intelligence": "has_intelligence_component",
    }
    return flag_map.get(component_name, f"has_{component_name.lower()}")


class RefitOrder(Order):
    """Order instructing a unit with a Constructor to add or remove components on a friendly unit."""
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.REFIT_UNIT, parameters, parent_order)

    def get_state_data(self) -> Dict[str, Any]:
        state_data = super().get_state_data()
        target_unit_id = self.parameters.get("target_unit_id")
        action = self.parameters.get("action", "ADD")
        component_type = self.parameters.get("component_type", "")
        cost_credits = self.parameters.get("cost_credits", 0)
        time_to_build = self.parameters.get("time_to_build", 1)

        target_name = None
        lookup_attempted = False
        lookup_success = False
        if target_unit_id and self.unit and self.unit.game and self.unit.game.galaxy:
            lookup_attempted = True
            target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id)
            if target_unit:
                target_name = target_unit.name
                lookup_success = True

        state_data.update({
            "target_unit_id": target_unit_id,
            "target_name": target_name,
            "action": action,
            "component_type": component_type,
            "cost_credits": cost_credits,
            "time_to_build": time_to_build,
            "lookup_attempted": lookup_attempted,
            "lookup_success": lookup_success,
        })
        return state_data

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        if not self.unit.constructor_component or self.unit.constructor_component.is_destroyed:
            self.status = OrderStatus.FAILED
            logger.debug(f"REFIT order failed: Unit {self.unit.name} has no active Constructor component.")
            return

        target_unit_id = self.parameters.get("target_unit_id")
        target_unit = galaxy_ref.get_unit_by_id(target_unit_id)

        if not target_unit or target_unit.current_hit_points <= 0:
            self.status = OrderStatus.FAILED
            logger.debug(f"REFIT order failed: Target unit {target_unit_id} not found or destroyed.")
            return

        from entities import are_allies
        if not are_allies(self.unit.owner, target_unit.owner):
            self.status = OrderStatus.FAILED
            logger.debug(f"REFIT order failed: Target unit {target_unit.name} is not friendly/allied.")
            return

        action = str(self.parameters.get("action", "ADD")).upper()
        component_type = self.parameters.get("component_type", "")
        component_config = self.parameters.get("component_config", {})
        comp_cls = get_component_class_by_name(component_type)

        if not comp_cls:
            self.status = OrderStatus.FAILED
            logger.debug(f"REFIT order failed: Unknown component type '{component_type}'.")
            return

        # Check proximity and approach if necessary
        in_same_system_and_hex = (self.unit.in_system == target_unit.in_system and self.unit.in_hex == target_unit.in_hex)
        in_range = in_same_system_and_hex and (distance(self.unit.position, target_unit.position) <= self.unit.constructor_component.build_range)

        if not in_range:
            move_order = MoveOrder.for_unit_approach(
                self.unit,
                target_unit,
                self.unit.constructor_component.build_range - 5.0,
                parent_order=self,
            )
            self.add_sub_order(move_order)

            refit_sub_order = RefitOrder(self.unit, self.parameters, parent_order=self)
            self.add_sub_order(refit_sub_order)
            return

        player = next((p for p in self.unit.game.players if p.id == self.unit.owner.id), self.unit.owner)

        if action == "ADD":
            if comp_cls in target_unit.components:
                self.status = OrderStatus.FAILED
                logger.debug(f"REFIT order failed: Unit {target_unit.name} already has {component_type}.")
                if getattr(self.unit.game, 'gui', None):
                    self.unit.game.gui.show_warning_dialog(
                        f"Unit <b>{target_unit.name}</b> already has a <b>{component_type}</b> installed.",
                        title="Component Already Installed"
                    )
                return

            # Check hull size restrictions
            forbidden_comps = HULL_RESTRICTIONS.get(target_unit.hull_size, set())
            comp_flag_key = get_hull_restriction_flag(component_type)
            if comp_flag_key in forbidden_comps:
                self.status = OrderStatus.FAILED
                logger.debug(f"REFIT order failed: Hull size {target_unit.hull_size.name} cannot mount {component_type}.")
                if getattr(self.unit.game, 'gui', None):
                    self.unit.game.gui.show_warning_dialog(
                        f"Hull size <b>{target_unit.hull_size.name}</b> cannot mount <b>{component_type}</b>.",
                        title="Hull Restriction Violation"
                    )
                return

            if component_type in ("TradeComponent", "Trade") and not getattr(target_unit, 'engines_component', None):
                self.status = OrderStatus.FAILED
                logger.debug(f"REFIT order failed: Trade component requires an Engine component.")
                if getattr(self.unit.game, 'gui', None):
                    self.unit.game.gui.show_warning_dialog(
                        f"Cannot install <b>Trade Module</b> on <b>{target_unit.name}</b> because it lacks an Engine component.",
                        title="Engine Required"
                    )
                return

            # Calculate hull cost
            hull_cost = get_component_hull_cost(component_type, target_unit, component_config)
            component_config["hull_cost"] = hull_cost

            if target_unit.current_hull_usage + hull_cost > target_unit.hull_capacity:
                self.status = OrderStatus.FAILED
                logger.debug(f"REFIT order failed: Exceeds hull capacity of {target_unit.name} ({target_unit.current_hull_usage + hull_cost:.1f}/{target_unit.hull_capacity:.1f}).")
                if getattr(self.unit.game, 'gui', None):
                    self.unit.game.gui.show_warning_dialog(
                        f"Insufficient hull capacity on <b>{target_unit.name}</b>.<br>"
                        f"Requires: {hull_cost:.1f} hull points (Available: {target_unit.hull_capacity - target_unit.current_hull_usage:.1f}).",
                        title="Insufficient Hull Capacity"
                    )
                return

            # Calculate credit cost and time to build
            cost_credits = self.parameters.get("cost_credits")
            if cost_credits is None:
                cost_credits = int(round(hull_cost * COMPONENT_COST_PER_HULL_POINT))
                self.parameters["cost_credits"] = cost_credits

            time_to_build = self.parameters.get("time_to_build")
            if time_to_build is None:
                time_to_build = max(1, int(round(hull_cost / 5.0)))
                self.parameters["time_to_build"] = time_to_build

            if player.credits < cost_credits:
                self.status = OrderStatus.FAILED
                logger.debug(f"REFIT order failed: Not enough credits ({player.credits}/{cost_credits}).")
                if getattr(self.unit.game, 'gui', None):
                    self.unit.game.gui.show_warning_dialog(
                        f"Insufficient credits to install <b>{component_type}</b>.<br>Required: {cost_credits:.0f} credits (Available: {player.credits:.0f}).",
                        title="Insufficient Resources"
                    )
                return

            success = self.unit.constructor_component.start_refit(
                target_unit=target_unit,
                action="ADD",
                component_type=component_type,
                component_config=component_config,
                cost_credits=cost_credits,
                time_to_build=time_to_build
            )
            if not success:
                self.status = OrderStatus.FAILED

        elif action == "REMOVE":
            if comp_cls not in target_unit.components:
                self.status = OrderStatus.FAILED
                logger.debug(f"REFIT order failed: Unit {target_unit.name} does not have {component_type}.")
                return

            if comp_cls.__name__ == "Commander":
                self.status = OrderStatus.FAILED
                logger.debug(f"REFIT order failed: Commander component cannot be removed.")
                if getattr(self.unit.game, 'gui', None):
                    self.unit.game.gui.show_warning_dialog(
                        f"The <b>Commander</b> component is essential and cannot be removed.",
                        title="Cannot Remove Component"
                    )
                return

            # Safety check: do not remove carrier bays if craft are docked
            comp_instance = target_unit.components[comp_cls]
            if comp_cls.__name__ in ("HangarComponent", "StrikecraftBayComponent"):
                if getattr(comp_instance, 'docked_units', None):
                    self.status = OrderStatus.FAILED
                    logger.debug(f"REFIT order failed: Cannot remove {component_type} while units are docked.")
                    if getattr(self.unit.game, 'gui', None):
                        self.unit.game.gui.show_warning_dialog(
                            f"Cannot remove <b>{component_type}</b> while strikecraft or units are docked.<br>Please deploy or undock all craft first.",
                            title="Docked Craft Present"
                        )
                    return

            time_to_build = self.parameters.get("time_to_build") or 1
            # Salvage refund (50% of component value credited upon removal)
            salvage_refund = int(round(comp_instance.hull_cost * COMPONENT_COST_PER_HULL_POINT * 0.5))
            if salvage_refund > 0:
                player.credits += salvage_refund
                logger.debug(f"Refunded {salvage_refund} salvage credits to player {player.name} for removal of {component_type} on {target_unit.name}.")

            success = self.unit.constructor_component.start_refit(
                target_unit=target_unit,
                action="REMOVE",
                component_type=component_type,
                component_config=component_config,
                cost_credits=0,
                time_to_build=time_to_build
            )
            if not success:
                self.status = OrderStatus.FAILED

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return
        constructor = self.unit.constructor_component
        if not constructor or constructor.current_refit_target is None:
            self.status = OrderStatus.COMPLETED

    def cancel(self) -> None:
        constructor = self.unit.constructor_component
        if constructor and constructor.current_refit_target:
            cost_credits = constructor.current_refit_target.get("cost_credits", 0)
            if cost_credits > 0:
                player = next((p for p in self.unit.game.players if p.id == self.unit.owner.id), self.unit.owner)
                if player:
                    player.credits += cost_credits
                    logger.debug(f"Refunded {cost_credits} credits to {player.name} for cancelled refit.")
            constructor.cancel_refit()
        super().cancel()
