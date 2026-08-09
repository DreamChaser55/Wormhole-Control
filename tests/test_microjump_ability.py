import pytest
from unittest.mock import MagicMock
from geometry import Position, Circle, distance
from entities import Unit, Player, OrderType
from constants import HullSize
from unit_components import (
    AbilityComponent,
    AbilityType,
    AntimatterStorage,
    Hyperdrive,
    HyperdriveType,
)
from unit_components.abilities.microjump import MicrojumpAbility
from unit_orders import UseAbilityOrder, OrderStatus
from tests.test_unit_components import MockPlayer
from gui.unit_editor_gui.catalog import ABILITY_NAMES


class DummyHex:
    def __init__(self):
        self.static_inhibition_zones = []
        self.dynamic_inhibition_zones = {}

    def get_all_inhibition_zones(self):
        return self.static_inhibition_zones + list(self.dynamic_inhibition_zones.values())


class DummySystem:
    def __init__(self):
        self.hexes = {(0, 0): DummyHex()}


class DummyGalaxy:
    def __init__(self):
        self.systems = {"Sol": DummySystem()}

    def get_unit_by_id(self, unit_id):
        return None


class DummyGUI:
    def __init__(self):
        self.warning_dialogs = []

    def show_warning_dialog(self, text, title=None):
        self.warning_dialogs.append((text, title))


class DummyGame:
    def __init__(self):
        self.galaxy = DummyGalaxy()
        self.gui = DummyGUI()
        self.selected_objects = []
        self.pending_ability = None
        self.current_system_name = "Sol"
        self.current_sector_coord = (0, 0)


def create_test_unit(game=None, position=None):
    if game is None:
        game = DummyGame()
    if position is None:
        position = Position(0, 0)

    player = MockPlayer()
    unit = Unit(
        owner=player,
        position=position,
        in_hex=(0, 0),
        in_system="Sol",
        name="Jumper",
        hull_size=HullSize.MEDIUM,
        game=game,
    )

    # Add Hyperdrive
    hd = Hyperdrive(unit, drive_type=HyperdriveType.BASIC, jump_range=3)
    unit.add_component(hd)

    # Add Antimatter
    am = AntimatterStorage(unit, max_capacity=100.0)
    unit.add_component(am)

    # Add Microjump Ability
    ac = AbilityComponent(unit, [AbilityType.MICROJUMP])
    unit.add_component(ac)

    return unit, game


def test_microjump_definition():
    defn = MicrojumpAbility.DEFINITION
    assert defn.ability_type == AbilityType.MICROJUMP
    assert defn.name == "Microjump"
    assert defn.requires_target_position is True
    assert defn.requires_target_unit is False
    assert defn.range == 600.0
    assert defn.cooldown == 5
    assert defn.antimatter_cost == 25
    assert "microjump" in ABILITY_NAMES


def test_microjump_successful_jump():
    unit, game = create_test_unit(position=Position(0, 0))
    target_pos = Position(300, 200)

    order = UseAbilityOrder(
        unit,
        {
            "ability_type": "microjump",
            "target_position": target_pos,
            "target_system_name": "Sol",
            "target_hex_coord": (0, 0),
        },
    )

    order.execute(game.galaxy)

    assert order.status == OrderStatus.COMPLETED
    assert unit.position == target_pos
    assert unit.antimatter_component.current_amount == 75.0
    instance = unit.ability_component.abilities[AbilityType.MICROJUMP]
    assert instance.cooldown_remaining == 5


def test_microjump_fails_when_origin_inhibited():
    unit, game = create_test_unit(position=Position(0, 0))
    # Place an inhibition zone over origin (0, 0)
    hex_obj = game.galaxy.systems["Sol"].hexes[(0, 0)]
    hex_obj.static_inhibition_zones.append(Circle(Position(0, 0), 100.0))

    target_pos = Position(300, 200)
    order = UseAbilityOrder(
        unit,
        {
            "ability_type": "microjump",
            "target_position": target_pos,
            "target_system_name": "Sol",
            "target_hex_coord": (0, 0),
        },
    )

    order.execute(game.galaxy)

    assert order.status == OrderStatus.FAILED
    assert unit.position == Position(0, 0)  # Position unchanged
    assert unit.antimatter_component.current_amount == 100.0  # Antimatter not spent
    assert len(game.gui.warning_dialogs) == 1
    assert "Origin position is inside a hyperspace inhibition field" in game.gui.warning_dialogs[0][0]


def test_microjump_fails_when_destination_inhibited():
    unit, game = create_test_unit(position=Position(0, 0))
    target_pos = Position(300, 200)

    # Place an inhibition zone over destination (300, 200)
    hex_obj = game.galaxy.systems["Sol"].hexes[(0, 0)]
    hex_obj.static_inhibition_zones.append(Circle(target_pos, 100.0))

    order = UseAbilityOrder(
        unit,
        {
            "ability_type": "microjump",
            "target_position": target_pos,
            "target_system_name": "Sol",
            "target_hex_coord": (0, 0),
        },
    )

    order.execute(game.galaxy)

    assert order.status == OrderStatus.FAILED
    assert unit.position == Position(0, 0)  # Position unchanged
    assert unit.antimatter_component.current_amount == 100.0  # Antimatter not spent
    assert len(game.gui.warning_dialogs) == 1
    assert "Destination position is inside a hyperspace inhibition field" in game.gui.warning_dialogs[0][0]


def test_microjump_fails_insufficient_antimatter():
    unit, game = create_test_unit(position=Position(0, 0))
    unit.antimatter_component.current_amount = 10.0  # Cost is 25

    target_pos = Position(300, 200)
    order = UseAbilityOrder(
        unit,
        {
            "ability_type": "microjump",
            "target_position": target_pos,
            "target_system_name": "Sol",
            "target_hex_coord": (0, 0),
        },
    )

    order.execute(game.galaxy)

    assert order.status == OrderStatus.FAILED
    assert unit.position == Position(0, 0)
    assert unit.antimatter_component.current_amount == 10.0


def test_microjump_fails_out_of_range():
    unit, game = create_test_unit(position=Position(0, 0))
    # Target at distance 700 > range 600
    target_pos = Position(700, 0)

    success = unit.ability_component.activate(
        ability_type=AbilityType.MICROJUMP,
        galaxy=game.galaxy,
        target_position=target_pos,
    )

    assert success is False
    assert unit.position == Position(0, 0)
    assert unit.antimatter_component.current_amount == 100.0
