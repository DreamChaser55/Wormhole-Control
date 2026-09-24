"""Player income and fleet upkeep calculations."""
import typing
from dataclasses import dataclass

from constants import TAX_RATE, UPKEEP_COST_PER_HULL_POINT
from domain.celestials import Planet, Moon, ColonizableAsteroid
from constants import HullSize
from domain.players import Player, are_enemies
from unit_components.enums import SabotageType


@dataclass(frozen=True)
class IncomeBreakdown:
    """Resources generated in one owner's income phase, before fleet upkeep."""

    colony_credits: float = 0.0
    habitat_credits: float = 0.0
    siphoned_credits: float = 0.0
    metal: float = 0.0
    crystal: float = 0.0

    @property
    def total_credits(self) -> float:
        return self.colony_credits + self.habitat_credits + self.siphoned_credits


def calculate_income_breakdown(galaxy: typing.Any, player: Player) -> IncomeBreakdown:
    """Preview one owner's income without changing resources or world state.

    Use current colony ownership, population, sabotage and habitat eligibility.
    Each enemy colony pays siphoned tax at most once to this player, regardless
    of agent count. Passive minerals belong only to the colony owner. Trade,
    growth and upkeep resolve separately; an absent galaxy produces zero income.
    """
    colony_credits = habitat_credits = siphoned_credits = metal = crystal = 0.0
    if galaxy is None:
        return IncomeBreakdown()

    for system in galaxy.systems.values():
        for _, body in system.get_all_celestial_bodies():
            if not isinstance(body, (Planet, Moon, ColonizableAsteroid)):
                continue
            base_tax = body.population * TAX_RATE
            if body.owner == player:
                colony_credits += base_tax * (0.5 if body.is_sabotaged(SabotageType.ECONOMY) else 1.0)
                metal += max(0.0, getattr(body, 'passive_metal', 0.0))
                crystal += max(0.0, getattr(body, 'passive_crystal', 0.0))
            elif are_enemies(player, body.owner) and any(
                agent.owner == player and agent.active_sabotage == SabotageType.ECONOMY
                for agent in body.infiltrating_agents
            ):
                siphoned_credits += base_tax * 0.25

        for unit, _ in system.get_all_units():
            if unit.owner != player:
                continue
            habitat = unit.civilian_habitat_component
            if habitat and not habitat.is_destroyed and habitat.is_active(galaxy):
                habitat_credits += habitat.economic_bonus

    return IncomeBreakdown(colony_credits, habitat_credits, siphoned_credits, metal, crystal)


def calculate_player_income(galaxy: typing.Any, player: Player) -> float:
    """Return previewed credits for the next income phase, before upkeep."""
    return calculate_income_breakdown(galaxy, player).total_credits


def calculate_unit_upkeep(hull_size: typing.Optional[HullSize], current_hull_usage: float) -> float:
    """Calculates credit upkeep cost per turn for an individual unit design or instance.

    Strikecraft wings are exempt from upkeep (0.0 credits/turn).
    For other hull sizes, upkeep is current_hull_usage * UPKEEP_COST_PER_HULL_POINT.

    Args:
        hull_size (Optional[HullSize]): Hull size classification of the unit.
        current_hull_usage (float): Hull points currently consumed by installed components.

    Returns:
        float: Upkeep cost per turn in credits.
    """
    if hull_size == HullSize.STRIKECRAFT_WING:
        return 0.0
    return max(0.0, float(current_hull_usage) * UPKEEP_COST_PER_HULL_POINT)


def calculate_player_upkeep(galaxy: typing.Any, player: Player) -> float:
    """Calculates total credit upkeep cost per turn for a player's active fleet.

    Args:
        galaxy: Active Galaxy object or None.
        player (Player): Player whose upkeep is being computed.

    Returns:
        float: Total upkeep cost per turn based on hull sizes of active units.
    """
    total_upkeep = 0.0
    if galaxy:
        for system_obj in galaxy.systems.values():
            for unit, _ in system_obj.get_all_units():
                if getattr(unit, 'owner', None) != player:
                    continue
                if getattr(unit, 'is_temporary', False):
                    continue
                total_upkeep += calculate_unit_upkeep(
                    getattr(unit, 'hull_size', None),
                    getattr(unit, 'current_hull_usage', 0.0)
                )
            for _, body in system_obj.get_all_celestial_bodies():
                if getattr(body, 'hidden_units', None):
                    for unit in body.hidden_units:
                        if getattr(unit, 'owner', None) != player:
                            continue
                        if getattr(unit, 'is_temporary', False):
                            continue
                        total_upkeep += calculate_unit_upkeep(
                            getattr(unit, 'hull_size', None),
                            getattr(unit, 'current_hull_usage', 0.0)
                        )
    return total_upkeep
