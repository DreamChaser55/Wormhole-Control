"""Intelligence, Espionage, Counter-Intelligence, and Sabotage module."""
import logging
import typing
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from .base import UnitComponent
from .enums import SabotageType

if TYPE_CHECKING:
    from entities import Unit, Player, CelestialBody
    from game import Game

logger = logging.getLogger(__name__)

INTELLIGENCE_BASE_HULL_COST: float = 10.0
INTELLIGENCE_EXTRA_AGENT_HULL_COST: float = 5.0
COUNTER_INTELLIGENCE_HULL_COST: float = 10.0
DEFAULT_INFILTRATION_RANGE: float = 500.0


class Agent:
    """Represents a covert operative infiltrating an enemy unit or colonized celestial body."""
    agent_counter = 0

    def __init__(
        self,
        owner: 'Player',
        source_unit_id: int,
        target_type: str,
        target_id: int,
        agent_id: Optional[int] = None,
        is_discovered: bool = False,
        active_sabotage: Optional[SabotageType] = None,
        turns_active: int = 0
    ):
        if agent_id is not None:
            self.id = agent_id
            Agent.agent_counter = max(Agent.agent_counter, agent_id + 1)
        else:
            self.id = Agent.agent_counter
            Agent.agent_counter += 1

        self.owner = owner
        self.source_unit_id = source_unit_id
        self.target_type = target_type  # "UNIT" or "CELESTIAL_BODY"
        self.target_id = target_id
        self.is_discovered = is_discovered
        self.active_sabotage = active_sabotage
        self.turns_active = turns_active
        self.attached_to: Optional[Any] = None
        self._source_unit: Optional['Unit'] = None

    @property
    def source_unit(self) -> Optional['Unit']:
        """Attempts to resolve the parent Unit that deployed this agent."""
        if getattr(self, '_source_unit', None):
            return self._source_unit
        if self.owner and hasattr(self.owner, 'units'):
            for u in getattr(self.owner, 'units', []):
                if u.id == self.source_unit_id:
                    return u
        return None

    def clear_sabotage(self) -> None:
        """Clears any active sabotage operation applied by this agent."""
        self.active_sabotage = None

    def serialize(self) -> Dict[str, Any]:
        """Serializes agent state for persistence."""
        return {
            "id": self.id,
            "owner_id": self.owner.id if self.owner else None,
            "source_unit_id": self.source_unit_id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "is_discovered": self.is_discovered,
            "active_sabotage": self.active_sabotage.name if self.active_sabotage else None,
            "turns_active": self.turns_active,
        }

    def to_dict(self) -> Dict[str, Any]:
        return self.serialize()

    @staticmethod
    def deserialize(data: Dict[str, Any], players_by_id: Dict[int, 'Player']) -> 'Agent':
        """Restores an Agent from serialized dictionary."""
        owner_id = data.get("owner_id")
        owner = players_by_id.get(owner_id) if owner_id is not None else None
        
        sabotage_raw = data.get("active_sabotage")
        active_sabotage = None
        if sabotage_raw:
            try:
                active_sabotage = SabotageType[sabotage_raw]
            except KeyError:
                active_sabotage = None

        return Agent(
            owner=owner,
            source_unit_id=data.get("source_unit_id", 0),
            target_type=data.get("target_type", "UNIT"),
            target_id=data.get("target_id", 0),
            agent_id=data.get("id"),
            is_discovered=data.get("is_discovered", False),
            active_sabotage=active_sabotage,
            turns_active=data.get("turns_active", 0),
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any], players_by_id: Dict[int, 'Player'], attached_to: Optional[Any] = None) -> 'Agent':
        agent = cls.deserialize(data, players_by_id)
        agent.attached_to = attached_to
        return agent

    def __repr__(self) -> str:
        owner_name = self.owner.name if self.owner else "None"
        sab_str = f", Sabotage={self.active_sabotage.name}" if self.active_sabotage else ""
        disc_str = " [DISCOVERED]" if self.is_discovered else ""
        return f"Agent(id={self.id}, Owner={owner_name}, Target={self.target_type}:{self.target_id}{sab_str}{disc_str})"


class IntelligenceComponent(UnitComponent):
    """Component enabling covert operations: deploying invisible agents, sensor tapping, sabotage, and counter-intelligence."""
    DISPLAY_NAME: str = "Intelligence"
    SIDEBAR_ORDER: int = 14

    def __init__(
        self,
        unit: 'Unit',
        agents_count: int = 1,
        agents_capacity: int = 1,
        has_counter_intelligence: bool = False,
        infiltration_range: float = DEFAULT_INFILTRATION_RANGE,
        hull_cost: float = 0.0,
        ci_cooldown_remaining: int = 0
    ):
        super().__init__(unit, hull_cost)
        self.agents_capacity: int = max(1, int(agents_capacity))
        self.agents_count: int = min(self.agents_capacity, max(0, int(agents_count)))
        self.has_counter_intelligence: bool = bool(has_counter_intelligence)
        self.infiltration_range: float = float(infiltration_range)
        self.counter_intelligence_range: float = float(infiltration_range)
        self.ci_cooldown_remaining: int = max(0, int(ci_cooldown_remaining))
        self._deployed_agents: List[Agent] = []

    @staticmethod
    def calc_hull_cost(agents_capacity: int = 1, has_counter_intelligence: bool = False) -> float:
        """Compute the hull cost of an Intelligence component based on agent capacity and counter-intelligence capability."""
        cap = max(1, int(agents_capacity))
        cost = INTELLIGENCE_BASE_HULL_COST + (cap - 1) * INTELLIGENCE_EXTRA_AGENT_HULL_COST
        if has_counter_intelligence:
            cost += COUNTER_INTELLIGENCE_HULL_COST
        return float(cost)

    @property
    def is_ci_ready(self) -> bool:
        """Returns True if the Counter-Intelligence suite is functional and off cooldown."""
        return self.has_counter_intelligence and not self.is_destroyed and self.ci_cooldown_remaining <= 0

    def update(self) -> None:
        """Called each turn to decrement active cooldowns."""
        if self.ci_cooldown_remaining > 0:
            self.ci_cooldown_remaining -= 1

    @property
    def available_agents(self) -> int:
        return self.agents_count

    @property
    def deployed_agents(self) -> List[Agent]:
        return self._deployed_agents

    @property
    def can_deploy_agent(self) -> bool:
        """Return True if component is functional and has at least one ready agent."""
        return not self.is_destroyed and self.agents_count > 0

    def deploy_agent(self, target_obj: typing.Union['Unit', 'CelestialBody']) -> Optional[Agent]:
        """Deploys an operative onto an enemy unit or celestial body."""
        if not self.can_deploy_agent:
            logger.debug(f"[{self.unit.name}] Intelligence component cannot deploy agent: no available agents.")
            return None

        from entities import Unit
        target_type = "UNIT" if isinstance(target_obj, Unit) else "CELESTIAL_BODY"

        agent = Agent(
            owner=self.unit.owner,
            source_unit_id=self.unit.id,
            target_type=target_type,
            target_id=target_obj.id,
        )
        agent.attached_to = target_obj
        agent._source_unit = self.unit

        if not hasattr(target_obj, 'infiltrating_agents'):
            target_obj.infiltrating_agents = []
        target_obj.infiltrating_agents.append(agent)
        self.agents_count = max(0, self.agents_count - 1)
        self._deployed_agents.append(agent)

        logger.debug(f"[{self.unit.name}] Deployed agent {agent.id} onto {target_type} {target_obj.name} (id:{target_obj.id}).")
        return agent

    def remove_agent_reference(self, agent: Agent) -> None:
        """Removes an agent from the component's deployed list."""
        if agent in self._deployed_agents:
            self._deployed_agents.remove(agent)

    def retrieve_agent(self, agent: Agent, target_obj: Optional[typing.Union['Unit', 'CelestialBody']] = None) -> bool:
        """Extracts an operative from a target back to this ship."""
        target = target_obj or getattr(agent, 'attached_to', None)
        if target and hasattr(target, 'infiltrating_agents') and agent in target.infiltrating_agents:
            target.infiltrating_agents.remove(agent)
        agent.attached_to = None
        self.remove_agent_reference(agent)
        self.agents_count = min(self.agents_capacity, self.agents_count + 1)
        logger.debug(f"[{self.unit.name}] Retrieved agent {agent.id}.")
        return True

    def _is_enemy_of_active_player(self, game_state: 'Game') -> bool:
        """Returns True if the active player in game_state is an enemy of the unit's owner."""
        if not game_state or not self.unit or not self.unit.owner:
            return False
        current_player = (
            game_state.players[game_state.current_player_index]
            if getattr(game_state, 'players', None) and 0 <= getattr(game_state, 'current_player_index', 0) < len(game_state.players)
            else getattr(game_state, 'current_player', None)
        )
        from entities import are_enemies
        return are_enemies(current_player, self.unit.owner)

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        if self._is_enemy_of_active_player(game_state):
            return []
        data = super().get_sidebar_data(game_state)
        data.append({
            'type': 'label',
            'text': f"Agents: {self.agents_count} / {self.agents_capacity} Ready",
            'object_id': '#sidebar_info_label',
            'height': 20
        })
        if self.has_counter_intelligence:
            if self.ci_cooldown_remaining > 0:
                ci_status = f"Cooldown ({self.ci_cooldown_remaining} turn{'s' if self.ci_cooldown_remaining > 1 else ''})"
            else:
                ci_status = "Ready"
            from constants import CI_SWEEP_CREDIT_COST, CI_SWEEP_ANTIMATTER_COST
            data.append({
                'type': 'label',
                'text': f"Counter-Intelligence: {ci_status}",
                'object_id': '#sidebar_info_label',
                'height': 20
            })
            data.append({
                'type': 'label',
                'text': f"Sweep Cost: {int(CI_SWEEP_CREDIT_COST)}c, {int(CI_SWEEP_ANTIMATTER_COST)}am",
                'object_id': '#sidebar_info_label',
                'height': 20
            })
        else:
            data.append({
                'type': 'label',
                'text': "Counter-Intelligence: None",
                'object_id': '#sidebar_info_label',
                'height': 20
            })
        data.append({
            'type': 'label',
            'text': f"Infiltration Range: {int(self.infiltration_range)}",
            'object_id': '#sidebar_info_label',
            'height': 20
        })
        return data

    def get_basic_sidebar_data(self, game_state: 'Game') -> list[dict]:
        if self._is_enemy_of_active_player(game_state):
            return []
        data = super().get_basic_sidebar_data(game_state)
        if self.is_destroyed:
            return data
        if self.has_counter_intelligence:
            if self.ci_cooldown_remaining > 0:
                ci_text = f" | CI: Cooldown ({self.ci_cooldown_remaining}t)"
            else:
                ci_text = " | CI: Ready"
        else:
            ci_text = ""
        data.append({
            'type': 'label',
            'text': f"• Intelligence: {self.agents_count}/{self.agents_capacity} Agents{ci_text}",
            'object_id': '#sidebar_value_label',
            'height': 18,
            'indent_level': 1
        })
        return data
