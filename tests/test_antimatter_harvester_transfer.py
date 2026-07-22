import pytest
from unittest.mock import MagicMock
from geometry import Position
from entities import Unit, Star
from unit_components import AntimatterStorage, AntimatterHarvester
from unit_orders import TransferAntimatterOrder, OrderStatus
from constants import (
    HullSize, StarType,
    DEFAULT_ANTIMATTER_HARVEST_RATE, DEFAULT_ANTIMATTER_HARVEST_RANGE,
    ANTIMATTER_TRANSFER_RATE, ANTIMATTER_TRANSFER_RANGE,
)
from tests.test_unit_components import MockPlayer


class FakeHex:
    def __init__(self, celestial_bodies=None):
        self.celestial_bodies = celestial_bodies or []


class FakeSystem:
    def __init__(self, hexes):
        self.hexes = hexes


class FakeGalaxy:
    def __init__(self, systems):
        self.systems = systems


def make_unit(owner, hull_size=HullSize.MEDIUM, position=None, in_hex=(0, 0), in_system="Sol"):
    game = MagicMock()
    unit = Unit(
        owner=owner,
        position=position or Position(0, 0),
        in_hex=in_hex,
        in_system=in_system,
        name="Test Unit",
        hull_size=hull_size,
        game=game,
    )
    return unit


def test_harvester_replenishes_near_star():
    player = MockPlayer()
    unit = make_unit(player, position=Position(0, 0), in_hex=(0, 0))
    harvester = AntimatterHarvester(unit, harvest_rate=DEFAULT_ANTIMATTER_HARVEST_RATE, harvest_range=DEFAULT_ANTIMATTER_HARVEST_RANGE)
    unit.add_component(harvester)

    am_comp = unit.antimatter_component
    am_comp.current_amount = 50.0

    star = Star(in_system="Sol", star_type=StarType.G_TYPE)
    star.position = Position(0, 0)

    hex_obj = FakeHex(celestial_bodies=[star])
    system = FakeSystem(hexes={(0, 0): hex_obj})
    galaxy = FakeGalaxy(systems={"Sol": system})

    harvester.update(galaxy)

    assert harvester.is_harvesting is True
    assert am_comp.current_amount == 50.0 + DEFAULT_ANTIMATTER_HARVEST_RATE


def test_harvester_does_nothing_without_star():
    player = MockPlayer()
    unit = make_unit(player, position=Position(0, 0), in_hex=(1, 1))
    harvester = AntimatterHarvester(unit)
    unit.add_component(harvester)

    am_comp = unit.antimatter_component
    am_comp.current_amount = 50.0

    # Hex with no star present
    hex_obj = FakeHex(celestial_bodies=[])
    system = FakeSystem(hexes={(1, 1): hex_obj})
    galaxy = FakeGalaxy(systems={"Sol": system})

    harvester.update(galaxy)

    assert harvester.is_harvesting is False
    assert am_comp.current_amount == 50.0


def test_harvester_respects_max_capacity():
    player = MockPlayer()
    unit = make_unit(player)
    harvester = AntimatterHarvester(unit, harvest_rate=1000.0)
    unit.add_component(harvester)

    am_comp = unit.antimatter_component
    max_cap = am_comp.max_capacity
    am_comp.current_amount = max_cap - 5.0

    star = Star(in_system="Sol", star_type=StarType.G_TYPE)
    star.position = Position(0, 0)
    hex_obj = FakeHex(celestial_bodies=[star])
    system = FakeSystem(hexes={(0, 0): hex_obj})
    galaxy = FakeGalaxy(systems={"Sol": system})

    harvester.update(galaxy)

    assert am_comp.current_amount == max_cap


def test_unit_without_harvester_does_not_auto_regenerate_on_update():
    """Confirms that Unit.update() no longer passively regenerates antimatter
    for units that lack an AntimatterHarvester component."""
    player = MockPlayer()
    unit = make_unit(player)
    unit.in_galaxy = None  # Avoid triggering other component updates that need a galaxy

    am_comp = unit.antimatter_component
    am_comp.current_amount = 40.0

    unit.update()

    # No harvester present, so antimatter should remain unchanged.
    assert am_comp.current_amount == 40.0


def test_antimatter_storage_add_respects_capacity():
    player = MockPlayer()
    unit = make_unit(player)
    am_comp = unit.antimatter_component
    am_comp.current_amount = am_comp.max_capacity - 3.0

    added = am_comp.add(10.0)

    assert added == 3.0
    assert am_comp.current_amount == am_comp.max_capacity


def test_transfer_antimatter_order_moves_am_when_in_range():
    player = MockPlayer()
    source = make_unit(player, position=Position(0, 0), in_hex=(0, 0))
    target = make_unit(player, position=Position(10, 0), in_hex=(0, 0))

    source.antimatter_component.current_amount = 100.0
    target.antimatter_component.current_amount = 0.0

    galaxy = MagicMock()
    galaxy.get_unit_by_id.side_effect = lambda uid: target if uid == target.id else None
    source.game.galaxy = galaxy
    source.in_galaxy = galaxy

    order = TransferAntimatterOrder(source, {"target_unit_id": target.id})
    order.execute(galaxy)

    assert order.status == OrderStatus.IN_PROGRESS
    assert not order.sub_orders  # already in range, no approach needed

    order.update(galaxy)

    expected_transfer = min(ANTIMATTER_TRANSFER_RATE, 100.0)
    assert target.antimatter_component.current_amount == expected_transfer
    assert source.antimatter_component.current_amount == 100.0 - expected_transfer


def test_transfer_antimatter_order_fails_for_unfriendly_target():
    player = MockPlayer()
    enemy_player = MockPlayer()
    enemy_player.id = 2

    source = make_unit(player, position=Position(0, 0), in_hex=(0, 0))
    target = make_unit(enemy_player, position=Position(0, 0), in_hex=(0, 0))

    galaxy = MagicMock()
    galaxy.get_unit_by_id.side_effect = lambda uid: target if uid == target.id else None
    source.game.galaxy = galaxy

    order = TransferAntimatterOrder(source, {"target_unit_id": target.id})
    order.execute(galaxy)

    assert order.status == OrderStatus.FAILED


def test_transfer_antimatter_order_completes_when_target_full():
    player = MockPlayer()
    source = make_unit(player, position=Position(0, 0), in_hex=(0, 0))
    target = make_unit(player, position=Position(0, 0), in_hex=(0, 0))

    source.antimatter_component.current_amount = 100.0
    target.antimatter_component.current_amount = target.antimatter_component.max_capacity

    galaxy = MagicMock()
    galaxy.get_unit_by_id.side_effect = lambda uid: target if uid == target.id else None
    source.game.galaxy = galaxy
    source.in_galaxy = galaxy

    order = TransferAntimatterOrder(source, {"target_unit_id": target.id})
    order.execute(galaxy)
    order.update(galaxy)

    assert order.status == OrderStatus.COMPLETED
