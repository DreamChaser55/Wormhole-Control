from unittest.mock import MagicMock
from geometry import Position
from constants import HullSize
from unit_orders import OrderStatus, ConstructOrder
from unit_components import Constructor
from tests.test_unit_components import MockUnit, MockPlayer
from unit_templates import register_template, unregister_template


def test_construct_order():
    register_template("Station", {
        "name": "Station",
        "hull_size": HullSize.MEDIUM,
        "build_time": 3,
        "build_cost": 300
    })

    try:
        # Setup unit and constructor component
        unit = MockUnit()
        constructor = Constructor(unit, hull_cost=10)
        unit.add_component(constructor)

        galaxy = MagicMock()
        
        # Mock player credits and matching owner ID
        player = MockPlayer()
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
