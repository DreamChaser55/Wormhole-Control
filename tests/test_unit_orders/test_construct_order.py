from unittest.mock import MagicMock
from geometry import Position
from constants import HullSize
from unit_orders.base import OrderStatus, OrderType
from unit_orders.construction import ConstructOrder
from unit_components.constructor import Constructor
from unit_templates import register_template, unregister_template
from tests.support.units import ComponentUnit, ComponentPlayer


def test_construct_order():
    register_template("Station", {
        "name": "Station",
        "hull_size": HullSize.MEDIUM,
        "build_time": 3,
        "build_cost": 300
    })

    try:
        # Setup unit and constructor component
        unit = ComponentUnit()
        constructor = Constructor(unit, hull_cost=10)
        unit.add_component(constructor)

        galaxy = MagicMock()
        
        # Mock player credits and matching owner ID
        player = ComponentPlayer()
        player.id = unit.owner.id
        player.credits = 500
        unit.game.players = [player]
        unit.owner = player

        # Valid order
        order = ConstructOrder(unit, {
            "unit_template_name": "Station",
            "target_position": Position(10, 10)
        })

        assert order.status == OrderStatus.PENDING

        # Execute
        order.execute(galaxy)

        assert order.status == OrderStatus.IN_PROGRESS
        assert player.credits == 200
        assert constructor.current_construction_target == ("Station", Position(10, 10))
        assert constructor.construction_progress == 0

        # Progress turn
        constructor.update(galaxy)
        assert constructor.construction_progress == 1
        order.update(galaxy)
        assert order.status == OrderStatus.IN_PROGRESS

        # Complete construction
        constructor.update(galaxy) # progress = 2
        constructor.update(galaxy) # progress = 3 -> completes
        assert constructor.current_construction_target is None

        # Check order completion
        order.update(galaxy)
        assert order.status == OrderStatus.COMPLETED

        # Cancellation refund
        player.credits = 500
        order_cancel = ConstructOrder(unit, {
            "unit_template_name": "Station",
            "target_position": Position(10, 10)
        })
        order_cancel.execute(galaxy)
        assert order_cancel.status == OrderStatus.IN_PROGRESS
        assert player.credits == 200
        assert constructor.current_construction_target == ("Station", Position(10, 10))

        order_cancel.cancel()
        assert order_cancel.status == OrderStatus.CANCELLED
        assert player.credits == 500
        assert constructor.current_construction_target is None

        # Insufficient credits case
        player.credits = 100
        order_fail = ConstructOrder(unit, {
            "unit_template_name": "Station",
            "target_position": Position(10, 10)
        })
        order_fail.execute(galaxy)
        assert order_fail.status == OrderStatus.FAILED
    finally:
        unregister_template("Station")
    assert player.credits == 100


def test_construct_order_out_of_range_approaches():
    from unit_components.movement import Engines
    from geometry import distance

    register_template("Station", {
        "name": "Station",
        "hull_size": HullSize.MEDIUM,
        "build_time": 3,
        "build_cost": 300
    })

    try:
        unit = ComponentUnit()
        unit.position = Position(2000, 2000)
        constructor = Constructor(unit, hull_cost=10)
        unit.add_component(constructor)
        unit.add_component(Engines(unit, speed=200, hull_cost=10))

        galaxy = MagicMock()
        player = ComponentPlayer()
        player.id = unit.owner.id
        player.credits = 1000
        unit.game.players = [player]
        unit.owner = player

        order = ConstructOrder(unit, {
            "unit_template_name": "Station",
            "target_position": Position(0, 0)
        })
        order.execute(galaxy)

        assert order.status == OrderStatus.IN_PROGRESS
        # Sub-orders spawned: MoveOrder + ConstructOrder
        assert len(order.sub_orders) == 2
        assert order.sub_orders[0].order_type == OrderType.MOVE
        assert order.sub_orders[1].order_type == OrderType.CONSTRUCT
        # Standoff destination is within build_range - 5.0 (495.0)
        dest_pos = order.sub_orders[0].parameters["destination_position"]
        assert abs(distance(dest_pos, Position(0, 0)) - (constructor.build_range - 5.0)) < 0.1
        # Credits NOT charged upfront
        assert player.credits == 1000
        assert constructor.current_construction_target is None

        # Cancel while in transit
        order.cancel()
        assert order.status == OrderStatus.CANCELLED
        assert order.sub_orders[0].status == OrderStatus.CANCELLED
        assert player.credits == 1000
    finally:
        unregister_template("Station")


def test_construct_order_out_of_range_stationary_fails():
    register_template("Station", {
        "name": "Station",
        "hull_size": HullSize.MEDIUM,
        "build_time": 3,
        "build_cost": 300
    })

    try:
        unit = ComponentUnit()
        unit.position = Position(0, 0)
        constructor = Constructor(unit, hull_cost=10)
        unit.add_component(constructor)
        # Unit has NO engines (e.g. stationary shipyard)

        galaxy = MagicMock()
        player = ComponentPlayer()
        player.id = unit.owner.id
        player.credits = 1000
        unit.game.players = [player]
        unit.owner = player

        order = ConstructOrder(unit, {
            "unit_template_name": "Station",
            "target_position": Position(1000, 1000)
        })
        order.execute(galaxy)

        assert order.status == OrderStatus.FAILED
        assert order.failure_reason == "target_out_of_range"
        assert len(order.sub_orders) == 0
        assert player.credits == 1000
    finally:
        unregister_template("Station")


def test_constructor_start_construction_direct_range_check():
    register_template("Station", {
        "name": "Station",
        "hull_size": HullSize.MEDIUM,
        "build_time": 3,
        "build_cost": 300
    })

    try:
        unit = ComponentUnit()
        unit.position = Position(0, 0)
        constructor = Constructor(unit, hull_cost=10)
        unit.add_component(constructor)

        galaxy = MagicMock()
        player = ComponentPlayer()
        player.id = unit.owner.id
        player.credits = 1000
        unit.game.players = [player]
        unit.owner = player

        # Beyond build_range (500)
        assert not constructor.start_construction("Station", Position(600, 0), galaxy)
        assert player.credits == 1000
        assert constructor.current_construction_target is None

        # Within build_range (500)
        assert constructor.start_construction("Station", Position(400, 0), galaxy)
        assert player.credits == 700
        assert constructor.current_construction_target == ("Station", Position(400, 0))
    finally:
        unregister_template("Station")


def test_construct_order_approach_completion_lifecycle():
    from unit_components.movement import Engines

    register_template("Station", {
        "name": "Station",
        "hull_size": HullSize.MEDIUM,
        "build_time": 2,
        "build_cost": 300
    })

    try:
        unit = ComponentUnit()
        unit.position = Position(600, 0)
        constructor = Constructor(unit, hull_cost=10)
        unit.add_component(constructor)
        unit.add_component(Engines(unit, speed=200, hull_cost=10))

        galaxy = MagicMock()
        player = ComponentPlayer()
        player.id = unit.owner.id
        player.credits = 1000
        unit.game.players = [player]
        unit.owner = player

        order = ConstructOrder(unit, {
            "unit_template_name": "Station",
            "target_position": Position(0, 0)
        })
        order.execute(galaxy)

        assert order.status == OrderStatus.IN_PROGRESS
        assert len(order.sub_orders) == 2
        assert player.credits == 1000

        # Simulate movement reaching standoff position (495, 0)
        unit.position = Position(495, 0)
        order.sub_orders[0].status = OrderStatus.COMPLETED

        # First update pops completed MoveOrder and executes child ConstructOrder
        order.update(galaxy)
        assert len(order.sub_orders) == 1
        child = order.sub_orders[0]
        assert child.status == OrderStatus.IN_PROGRESS
        assert player.credits == 700
        assert constructor.current_construction_target == ("Station", Position(0, 0))

        # Update construction progress
        constructor.update(galaxy) # progress = 1
        order.update(galaxy)
        assert order.status == OrderStatus.IN_PROGRESS
        assert child.status == OrderStatus.IN_PROGRESS

        # Complete construction
        constructor.update(galaxy) # progress = 2 -> finish_construction
        assert constructor.current_construction_target is None
        order.update(galaxy) # child completes, parent completes
        assert order.status == OrderStatus.COMPLETED
    finally:
        unregister_template("Station")
