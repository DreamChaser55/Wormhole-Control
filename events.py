import typing

from utils import HexCoord

class Event:
    """Base class for all events in the game."""
    pass

class EventBus:
    """A simple synchronous event bus for publish-subscribe communication."""
    def __init__(self):
        self._listeners: typing.Dict[typing.Type[Event], typing.List[typing.Callable[[typing.Any], None]]] = {}

    def subscribe(self, event_type: typing.Type[Event], callback: typing.Callable[[typing.Any], None]):
        """Subscribe a callback to a specific event type."""
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(callback)

    def publish(self, event: Event):
        """Publish an event to all subscribers of its type."""
        event_type = type(event)
        # Call handlers for exact type matches
        if event_type in self._listeners:
            for callback in self._listeners[event_type]:
                callback(event)

class CancelOrdersEvent(Event):
    def __init__(self, units: list):
        self.units = units

class IssueMoveOrderEvent(Event):
    def __init__(self, units: list, system_name: str, sector_coord: typing.Any, destination: typing.Any, shift_pressed: bool):
        self.units = units
        self.system_name = system_name
        self.sector_coord = sector_coord
        self.destination = destination
        self.shift_pressed = shift_pressed

class IssuePatrolOrderEvent(Event):
    def __init__(self, units: list, system_name: str, sector_coord: typing.Any, destination: typing.Any, shift_pressed: bool = False, add_waypoint: bool = False, ctrl_pressed: bool = False):
        self.units = units
        self.system_name = system_name
        self.sector_coord = sector_coord
        self.destination = destination
        self.shift_pressed = shift_pressed
        self.add_waypoint = add_waypoint or ctrl_pressed
        self.ctrl_pressed = self.add_waypoint

class JumpInterhexEvent(Event):
    def __init__(self, units: list, system_name: str, target_hex: typing.Any, shift_pressed: bool):
        self.units = units
        self.system_name = system_name
        self.target_hex = target_hex
        self.shift_pressed = shift_pressed

class JumpWormholeEvent(Event):
    def __init__(self, units: list, wormhole: typing.Any, shift_pressed: bool):
        self.units = units
        self.wormhole = wormhole
        self.shift_pressed = shift_pressed

class AttackUnitEvent(Event):
    def __init__(self, units: list, target_unit: typing.Any, shift_pressed: bool, target_component_type_str: typing.Optional[str] = None):
        self.units = units
        self.target_unit = target_unit
        self.shift_pressed = shift_pressed
        self.target_component_type_str = target_component_type_str

class IssueProtectOrderEvent(Event):
    def __init__(self, units: list, target_unit: typing.Any, shift_pressed: bool):
        self.units = units
        self.target_unit = target_unit
        self.shift_pressed = shift_pressed

class ColonizeEvent(Event):
    def __init__(self, units: list, target_body: typing.Any, shift_pressed: bool):
        self.units = units
        self.target_body = target_body
        self.shift_pressed = shift_pressed

class LoadColonistsEvent(Event):
    def __init__(self, units: list, target_body: typing.Any, amount: int, shift_pressed: bool):
        self.units = units
        self.target_body = target_body
        self.amount = amount
        self.shift_pressed = shift_pressed

class ConstructEvent(Event):
    def __init__(self, units: list, unit_template_name: str, target_position: typing.Any, shift_pressed: bool):
        self.units = units
        self.unit_template_name = unit_template_name
        self.target_position = target_position
        self.shift_pressed = shift_pressed

class RepairUnitEvent(Event):
    def __init__(self, units: list, target_unit: typing.Any, shift_pressed: bool):
        self.units = units
        self.target_unit = target_unit
        self.shift_pressed = shift_pressed

class RefitUnitEvent(Event):
    """Fired when the player orders constructor units to refit a friendly unit (add/remove components)."""
    def __init__(self, units: list, target_unit: typing.Any, action: str, component_type: str,
                 component_config: typing.Optional[dict] = None, cost_credits: typing.Optional[int] = None,
                 time_to_build: typing.Optional[int] = None, shift_pressed: bool = False):
        self.units = units
        self.target_unit = target_unit
        self.action = action
        self.component_type = component_type
        self.component_config = component_config or {}
        self.cost_credits = cost_credits
        self.time_to_build = time_to_build
        self.shift_pressed = shift_pressed

class TransferAntimatterEvent(Event):
    """Fired when the player orders selected units to transfer antimatter from
    their own storage to a friendly target unit's storage."""
    def __init__(self, units: list, target_unit: typing.Any, shift_pressed: bool):
        self.units = units
        self.target_unit = target_unit
        self.shift_pressed = shift_pressed


class ContinuousResupplyEvent(Event):
    """Fired when the player orders a harvester unit to continuously harvest
    antimatter at a star and resupply nearby friendly units."""
    def __init__(self, units: list, target_body: typing.Any, shift_pressed: bool):
        self.units = units
        self.target_body = target_body
        self.shift_pressed = shift_pressed


class MineEvent(Event):
    def __init__(self, units: list, target_body: typing.Any, shift_pressed: bool):
        self.units = units
        self.target_body = target_body
        self.shift_pressed = shift_pressed

class ContinuousMineEvent(Event):
    def __init__(self, units: list, target_body: typing.Any, shift_pressed: bool):
        self.units = units
        self.target_body = target_body
        self.shift_pressed = shift_pressed


class UnloadResourcesEvent(Event):
    def __init__(self, units: list, target_unit: typing.Any, shift_pressed: bool):
        self.units = units
        self.target_unit = target_unit
        self.shift_pressed = shift_pressed

class DockEvent(Event):
    def __init__(self, units: list, target_carrier: typing.Any, shift_pressed: bool):
        self.units = units
        self.target_carrier = target_carrier
        self.shift_pressed = shift_pressed


class UseAbilityEvent(Event):
    """Fired when the player activates a special ability for one or more units."""
    def __init__(
        self,
        units: list,
        ability_type_str: str,
        target_unit: typing.Optional[typing.Any] = None,
        target_position: typing.Optional[typing.Any] = None,
        target_system_name: typing.Optional[str] = None,
        target_hex_coord: typing.Optional[HexCoord] = None,
        shift_pressed: bool = False,
    ):
        self.units = units
        self.ability_type_str = ability_type_str   # AbilityType.value string
        self.target_unit = target_unit             # Optional Unit for unit-targeted abilities
        self.target_position = target_position     # Optional Position for position-targeted abilities
        self.target_system_name = target_system_name
        self.target_hex_coord = target_hex_coord
        self.shift_pressed = shift_pressed


class LayMinefieldEvent(Event):
    """Fired when the player orders selected units to lay a minefield."""
    def __init__(self, units: list, minefield_type: typing.Any = "anti_ship", shift_pressed: bool = False):
        self.units = units
        from unit_components import MinefieldType
        if isinstance(minefield_type, str):
            try:
                self.minefield_type = MinefieldType(minefield_type)
            except ValueError:
                self.minefield_type = MinefieldType.ANTI_SHIP
        else:
            self.minefield_type = minefield_type
        self.shift_pressed = shift_pressed


class TradeEvent(Event):
    """Fired when the player orders trade ship(s) to trade with an active Civilian Habitat."""
    def __init__(self, units: list, target_unit: typing.Any, shift_pressed: bool):
        self.units = units
        self.target_unit = target_unit
        self.shift_pressed = shift_pressed


class ContinuousTradeEvent(Event):
    """Fired when the player orders trade ship(s) to start continuous trade."""
    def __init__(self, units: list, target_unit: typing.Any, shift_pressed: bool):
        self.units = units
        self.target_unit = target_unit
        self.shift_pressed = shift_pressed


class InfiltrateUnitEvent(Event):
    """Fired when ordering intelligence units to infiltrate an enemy unit."""
    def __init__(self, units: list, target_unit: typing.Any, shift_pressed: bool = False):
        self.units = units
        self.target_unit = target_unit
        self.shift_pressed = shift_pressed


class InfiltratePlanetEvent(Event):
    """Fired when ordering intelligence units to infiltrate a colonized celestial body."""
    def __init__(self, units: list, target_body: typing.Any, target_system: str, target_hex: typing.Any, shift_pressed: bool = False):
        self.units = units
        self.target_body = target_body
        self.target_system = target_system
        self.target_hex = target_hex
        self.shift_pressed = shift_pressed


class RelocateAgentEvent(Event):
    """Fired when relocating an agent to a new host target."""
    def __init__(self, units: list, agent_id: int, target_type: str, destination_id: int, shift_pressed: bool = False):
        self.units = units
        self.agent_id = agent_id
        self.target_type = target_type
        self.destination_id = destination_id
        self.shift_pressed = shift_pressed


class SabotageEvent(Event):
    """Fired when ordering an agent to sabotage a target."""
    def __init__(self, units: list, agent_id: int, sabotage_type: str, shift_pressed: bool = False):
        self.units = units
        self.agent_id = agent_id
        self.sabotage_type = sabotage_type
        self.shift_pressed = shift_pressed


class CISweepEvent(Event):
    """Fired when ordering a Counter-Intelligence sweep."""
    def __init__(self, units: list, shift_pressed: bool = False):
        self.units = units
        self.shift_pressed = shift_pressed


class EliminateAgentEvent(Event):
    """Fired when ordering counter-intelligence to eliminate a discovered enemy agent."""
    def __init__(self, units: list, agent_id: int, shift_pressed: bool = False):
        self.units = units
        self.agent_id = agent_id
        self.shift_pressed = shift_pressed


class ExtractAgentEvent(Event):
    """Fired when extracting an agent back into an intelligence vessel."""
    def __init__(self, units: list, agent_id: int, shift_pressed: bool = False):
        self.units = units
        self.agent_id = agent_id
        self.shift_pressed = shift_pressed
