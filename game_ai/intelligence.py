"""Player-scoped intelligence disclosure and side-effect-free legality helpers."""

from __future__ import annotations

from typing import Any, Iterable, Iterator

from geometry import distance
from unit_components.enums import SabotageType
from unit_orders.intelligence import INTELLIGENCE_OPERATIONAL_RANGE


UNIT_SABOTAGE_TYPES = (
    SabotageType.ENGINES,
    SabotageType.WEAPONS,
    SabotageType.DEFENSES,
    SabotageType.HYPERDRIVE,
    SabotageType.SENSORS,
    SabotageType.ANTIMATTER,
)
COLONY_SABOTAGE_TYPES = (SabotageType.ECONOMY, SabotageType.GROWTH)


def relation(viewer: Any, owner: Any) -> str:
    if owner is None:
        return "neutral"
    if owner is viewer or getattr(owner, "id", None) == getattr(viewer, "id", None):
        return "self"
    if hasattr(viewer, "is_allied_with") and viewer.is_allied_with(owner):
        return "ally"
    return "enemy"


def iter_agent_hosts(galaxy: Any) -> Iterator[tuple[Any, Any]]:
    """Yield every embedded agent with its authoritative host."""
    for system in getattr(galaxy, "systems", {}).values():
        for sector in getattr(system, "hexes", {}).values():
            for host in [*getattr(sector, "units", []), *getattr(sector, "celestial_bodies", [])]:
                for agent in getattr(host, "infiltrating_agents", []) or []:
                    yield agent, host


def find_agent_host(galaxy: Any, agent_id: int) -> tuple[Any, Any] | tuple[None, None]:
    for agent, host in iter_agent_hosts(galaxy):
        if getattr(agent, "id", None) == agent_id:
            return agent, host
    return None, None


def owned_agent_hosts(galaxy: Any, player: Any) -> list[tuple[Any, Any]]:
    return [
        (agent, host)
        for agent, host in iter_agent_hosts(galaxy)
        if relation(player, getattr(agent, "owner", None)) == "self"
    ]


def discovered_enemy_agent_hosts(galaxy: Any, player: Any) -> list[tuple[Any, Any]]:
    """Return discovered enemy agents hosted by the player or an ally."""
    return [
        (agent, host)
        for agent, host in iter_agent_hosts(galaxy)
        if bool(getattr(agent, "is_discovered", False))
        and relation(player, getattr(agent, "owner", None)) == "enemy"
        and relation(player, getattr(host, "owner", None)) in {"self", "ally"}
    ]


def host_kind(host: Any) -> str | None:
    from entities import ColonizableAsteroid, Moon, Planet, Unit

    if isinstance(host, Unit):
        return "unit"
    if isinstance(host, (Planet, Moon, ColonizableAsteroid)):
        return "colony"
    return None


def sabotage_types_for_host(host: Any) -> list[str]:
    kind = host_kind(host)
    values = UNIT_SABOTAGE_TYPES if kind == "unit" else COLONY_SABOTAGE_TYPES if kind == "colony" else ()
    return [value.value for value in values]


def own_agent_view(agent: Any, host: Any) -> dict[str, Any]:
    sabotage = getattr(agent, "active_sabotage", None)
    return {
        "agent_id": int(agent.id),
        "source_unit_id": int(agent.source_unit_id),
        "host_type": host_kind(host),
        "target_id": int(host.id),
        "active_sabotage": getattr(sabotage, "value", None),
    }


def discovered_agent_view(agent: Any, host: Any) -> dict[str, Any]:
    return {
        "agent_id": int(agent.id),
        "owner_id": int(agent.owner.id),
        "host_type": host_kind(host),
        "target_id": int(host.id),
    }


def relocation_target_ids(
    player: Any,
    host: Any,
    *,
    visible_units: Iterable[Any],
    exact_bodies: Iterable[Any],
) -> list[int]:
    candidates = [*visible_units, *exact_bodies]
    result = []
    for target in candidates:
        if target is host or host_kind(target) not in {"unit", "colony"}:
            continue
        if relation(player, getattr(target, "owner", None)) != "enemy":
            continue
        if getattr(target, "in_system", None) != getattr(host, "in_system", None):
            continue
        if getattr(target, "in_hex", None) != getattr(host, "in_hex", None):
            continue
        if distance(host.position, target.position) > INTELLIGENCE_OPERATIONAL_RANGE:
            continue
        result.append(int(target.id))
    return sorted(set(result))


def intelligence_observation(
    galaxy: Any,
    player: Any,
    *,
    visible_units: Iterable[Any],
    exact_bodies: Iterable[Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    owned = sorted(owned_agent_hosts(galaxy, player), key=lambda item: item[0].id)
    discovered = sorted(
        discovered_enemy_agent_hosts(galaxy, player), key=lambda item: item[0].id
    )
    sabotage_agents = [
        {
            "agent_id": int(agent.id),
            "sabotage_types": sabotage_types_for_host(host),
        }
        for agent, host in owned
    ]
    relocation_agents = [
        {
            "agent_id": int(agent.id),
            "target_ids": relocation_target_ids(
                player,
                host,
                visible_units=visible_units,
                exact_bodies=exact_bodies,
            ),
        }
        for agent, host in owned
    ]
    intelligence = {
        "owned_agents": [own_agent_view(agent, host) for agent, host in owned],
        "discovered_enemy_agents": [
            discovered_agent_view(agent, host) for agent, host in discovered
        ],
    }
    player_options = {
        "sabotage": {"agents": sabotage_agents},
        "relocate_agent": {"agents": relocation_agents},
    }
    return intelligence, player_options
