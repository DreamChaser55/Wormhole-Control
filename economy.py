"""Player income and fleet upkeep calculations."""
import typing
from dataclasses import dataclass
from itertools import chain

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
    colonies: tuple[dict, ...] = ()
    habitats: tuple[dict, ...] = ()

    @property
    def total_credits(self) -> float:
        return self.colony_credits + self.habitat_credits + self.siphoned_credits


def calculate_income_breakdown(galaxy: typing.Any, player: Player, *, details=False) -> IncomeBreakdown:
    """Preview one owner's income without changing resources or world state.

    Use current colony ownership, population, sabotage and habitat eligibility.
    Each enemy colony pays siphoned tax at most once to this player, regardless
    of agent count. Passive minerals belong only to the colony owner. Trade,
    growth and upkeep resolve separately; an absent galaxy produces zero income.
    """
    colony_credits = habitat_credits = siphoned_credits = metal = crystal = 0.0
    colonies, habitats = [], []
    if galaxy is None:
        return IncomeBreakdown()

    for system in galaxy.systems.values():
        for body in _bodies(system):
            if not isinstance(body, (Planet, Moon, ColonizableAsteroid)):
                continue
            base_tax = body.population * TAX_RATE
            if body.owner == player:
                tax = base_tax * (0.5 if body.is_sabotaged(SabotageType.ECONOMY) else 1.0)
                local_metal = max(0.0, getattr(body, 'passive_metal', 0.0))
                local_crystal = max(0.0, getattr(body, 'passive_crystal', 0.0))
                colony_credits += tax
                metal += local_metal
                crystal += local_crystal
                if details:
                    colonies.append(dict(body_id=body.id, name=body.name, system_name=body.in_system,
                                         credits=tax, metal=local_metal, crystal=local_crystal))
            elif are_enemies(player, body.owner) and any(
                agent.owner == player and agent.active_sabotage == SabotageType.ECONOMY
                for agent in body.infiltrating_agents
            ):
                siphoned_credits += base_tax * 0.25

        for unit in _deployed(system):
            if unit.owner != player:
                continue
            habitat = getattr(unit, 'civilian_habitat_component', None)
            if habitat and not habitat.is_destroyed and habitat.is_active(galaxy):
                habitat_credits += habitat.economic_bonus
                if details:
                    habitats.append(dict(unit_id=unit.id, name=unit.name, system_name=unit.in_system,
                                         credits=habitat.economic_bonus))

    return IncomeBreakdown(colony_credits, habitat_credits, siphoned_credits, metal, crystal,
                           tuple(colonies), tuple(habitats))


def calculate_player_income(galaxy: typing.Any, player: Player) -> float:
    """Return previewed credits for the next income phase, before upkeep."""
    return calculate_income_breakdown(galaxy, player).total_credits


def _bodies(system):
    get_all = getattr(system, 'get_all_celestial_bodies', None)
    if get_all is not None:
        yield from (body for _, body in get_all())
    else:
        for sector in getattr(system, 'hexes', {}).values():
            yield from getattr(sector, 'celestial_bodies', ())


def _deployed(system):
    get_all = getattr(system, 'get_all_units', None)
    if get_all is not None:
        yield from (unit for unit, _ in get_all())
    else:
        for sector in getattr(system, 'hexes', {}).values():
            yield from getattr(sector, 'units', ())


def total_population(galaxy: typing.Any, player: Player) -> float:
    return sum(
        float(getattr(body, "population", 0))
        for system in getattr(galaxy, "systems", {}).values()
        for body in _bodies(system)
        if getattr(body, "owner", None) is player
    )


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
    if hull_size == HullSize.TITAN:
        from titan_balance import UPKEEP_BASE, UPKEEP_PER_HULL
        return UPKEEP_BASE + UPKEEP_PER_HULL * max(0.0, float(current_hull_usage))
    return max(0.0, float(current_hull_usage) * UPKEEP_COST_PER_HULL_POINT)


def _unit_upkeep(galaxy, player):
    for system in getattr(galaxy, 'systems', {}).values():
        submerged = (unit for body in _bodies(system) for unit in (getattr(body, 'hidden_units', None) or ()))
        for unit in chain(_deployed(system), submerged):
            if getattr(unit, 'owner', None) != player or getattr(unit, 'is_temporary', False):
                continue
            credits = calculate_unit_upkeep(
                getattr(unit, 'hull_size', None), getattr(unit, 'current_hull_usage', 0.0),
            )
            if credits > 0:
                yield unit, credits


def calculate_player_upkeep(galaxy: typing.Any, player: Player) -> float:
    """Return recurring credit upkeep for deployed and submerged owned units."""
    return sum(credits for _, credits in _unit_upkeep(galaxy, player))


def recurring_economy(galaxy, player) -> dict:
    """An owner-only breakdown using the same rates as turn settlement."""
    income = calculate_income_breakdown(galaxy, player, details=True)
    units = [dict(unit_id=unit.id, name=unit.name, system_name=unit.in_system, credits=credits)
             for unit, credits in _unit_upkeep(galaxy, player)]
    return {
        "income": income.total_credits,
        "upkeep": sum(unit["credits"] for unit in units),
        "income_breakdown": {
            "colonies": list(income.colonies),
            "habitats": list(income.habitats),
            "siphoned_credits": income.siphoned_credits,
        },
        "upkeep_breakdown": units,
    }
