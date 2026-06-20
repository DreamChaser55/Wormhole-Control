import typing

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

class MineEvent(Event):
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
