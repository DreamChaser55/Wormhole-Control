"""Target declarations retain public selection, namespaces and private agent hosts."""
from unit_orders.base import Order, OrderType
from unit_orders.movement import MoveOrder
from unit_orders.intelligence import InfiltratePlanetOrder, RelocateAgentOrder
from unit_orders.repair import RepairOrder
from game_ai.order_view import order_layers
from tests.support.campaigns import campaign, ship


def test_target_declarations_preserve_zero_and_unit_approach_precedence():
    unit = ship(campaign())
    order = MoveOrder(unit, {'target_unit_id': 0, 'target_celestial_id': 9})
    assert order.primary_target_reference() == ('unit', 0)
    order.parameters['target_unit_id'] = None
    assert order.primary_target_reference() == ('celestial', 9)
    # Unrecognized fields on an untargeted order do not invent target semantics.
    assert Order(unit, OrderType.STANCE, {'target_id': 9}).primary_target_reference() is None


def test_agent_destinations_do_not_become_generic_public_targets():
    unit = ship(campaign())
    assert InfiltratePlanetOrder(unit, {'target_body_id': 9}).primary_target_reference() is None
    assert RelocateAgentOrder(unit, {'destination_id': 9}).primary_target_reference() is None


def test_unit_target_cannot_be_revealed_by_visible_body_id():
    unit = ship(campaign())
    order = RepairOrder(unit, {'target_unit_id': 9})
    unit.commander_component.restore_explicit_orders(None, [order], preserve_queue=True)
    view = order_layers(unit, 'self', set(), {9})['queued_orders'][0]
    assert view['target_id'] is None
    assert view['target_visibility'] == 'unavailable'
    assert view['parameters'] == {}
