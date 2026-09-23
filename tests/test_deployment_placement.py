"""Carrier launches must preserve real sector and containment invariants."""
import math
from unittest.mock import patch

import pytest

from constants import HullSize, StormType, SECTOR_CIRCLE_RADIUS_LOGICAL
from deployment_placement import find_deployment_position
from domain.celestials import AsteroidField, Moon, Storm
from geometry import NAVIGATION_CLEARANCE, Position, distance
from tests.support.campaigns import campaign, ship
from unit_components.hangar import HangarComponent
from unit_components.strikecraft import StrikecraftBayComponent, StrikecraftWingComponent
from unit_orders.base import OrderStatus
from unit_orders.hangar import DeployAllWingsOrder, DeployUnitOrder


def docked_craft(wing=False, count=1):
    game = campaign()
    game.galaxy.game = game
    carrier = ship(game, "carrier", hull=HullSize.LARGE)
    carrier.position = Position(4990, 0)
    component = (StrikecraftBayComponent if wing else HangarComponent)(carrier, max_slots=count)
    carrier.add_component(component)
    craft = []
    for index in range(count):
        unit = ship(game, f"craft {index}", hull=HullSize.STRIKECRAFT_WING if wing else HullSize.TINY)
        if wing:
            unit.add_component(StrikecraftWingComponent(unit))
        assert component.dock(unit, game.galaxy)
        craft.append(unit)
    game.turn_number += 1  # Docked wings have completed their service interval.
    return game, carrier, component, craft


def snapshot(component, unit, galaxy):
    return (unit.in_system, unit.in_hex, unit.position.to_tuple(),
            tuple(component.docked_units), tuple(getattr(component, "launched_units", ())),
            [dict(slot) for slot in getattr(component, "slots", ())],
            [tuple(sector.units) for system in galaxy.systems.values() for sector in system.hexes.values()])


@pytest.mark.parametrize("wing", [False, True])
def test_launch_rejects_outward_candidate_then_commits_safe_position(wing):
    game, carrier, component, (unit,) = docked_craft(wing)
    with patch("deployment_placement.random.uniform", side_effect=[0, 50, math.pi, 40]):
        order = DeployUnitOrder(carrier, {"docked_unit_id": unit.id})
        order.execute(game.galaxy)
    assert order.status == OrderStatus.COMPLETED
    assert unit.position.magnitude() <= SECTOR_CIRCLE_RADIUS_LOGICAL
    assert 20 <= distance(carrier.position, unit.position) <= 50
    assert unit not in component.docked_units
    assert game.galaxy.systems["Sol"].hexes[(0, 0)].units.count(unit) == 1
    if wing:
        assert component.launched_units == [unit]
        assert unit.strikecraft_wing_component.mother_carrier is carrier
        assert component.get_used_slots() == 1


@pytest.mark.parametrize("wing", [False, True])
def test_exhausted_launch_retains_every_location_and_membership(wing):
    game, carrier, component, (unit,) = docked_craft(wing)
    carrier.in_system, carrier.in_hex = "Beta", (1, 0)
    before = snapshot(component, unit, game.galaxy)
    with patch("deployment_placement.random.uniform", side_effect=[0, 50] * 100) as rng:
        assert not component.deploy(unit, game.galaxy)
    assert rng.call_count == 200
    assert snapshot(component, unit, game.galaxy) == before


@pytest.mark.parametrize("wing", [False, True])
@pytest.mark.parametrize("location", [(None, (0, 0)), ("missing", (0, 0)), ("Sol", (99, 99))])
def test_missing_sector_fails_without_randomness_or_mutation(wing, location):
    game, carrier, component, (unit,) = docked_craft(wing)
    carrier.in_system, carrier.in_hex = location
    before = snapshot(component, unit, game.galaxy)
    with patch("deployment_placement.random.uniform") as rng:
        assert not component.deploy(unit, game.galaxy)
    rng.assert_not_called()
    assert snapshot(component, unit, game.galaxy) == before


@pytest.mark.parametrize("wing", [False, True])
def test_launch_uses_navigation_clearance_at_solid_body(wing):
    game, carrier, component, (unit,) = docked_craft(wing)
    moon = Moon((0, 0), "Sol")
    moon.position = Position(0, 0)
    game.galaxy.systems["Sol"].add_celestial_body(moon)
    carrier.position = Position(moon.collision_radius + NAVIGATION_CLEARANCE + 10, 0)
    with patch("deployment_placement.random.uniform", side_effect=[math.pi, 40, 0, 40]):
        assert component.deploy(unit, game.galaxy)
    assert distance(unit.position, moon.position) >= moon.collision_radius + NAVIGATION_CLEARANCE


@pytest.mark.parametrize("wing", [False, True])
def test_completely_obstructed_launch_fails_order_and_preserves_craft(wing):
    game, carrier, component, (unit,) = docked_craft(wing)
    carrier.position = Position(0, 0)
    game.galaxy.systems["Sol"].add_celestial_body(Moon((0, 0), "Sol"))
    before = snapshot(component, unit, game.galaxy)
    order = DeployUnitOrder(carrier, {"docked_unit_id": unit.id})
    order.execute(game.galaxy)
    assert order.status == OrderStatus.FAILED
    assert snapshot(component, unit, game.galaxy) == before


def test_candidate_storm_check_uses_wing_location_not_only_carrier():
    game, carrier, component, (unit,) = docked_craft(True)
    storm = Storm((0, 0), "Sol", StormType.MAGNETIC)
    storm.position, storm.radius = Position(0, 0), 100
    game.galaxy.systems["Sol"].add_celestial_body(storm)
    carrier.position = Position(110, 0)
    with patch("deployment_placement.random.uniform", side_effect=[math.pi, 40, 0, 50]):
        assert component.deploy(unit, game.galaxy)
    assert distance(unit.position, storm.position) >= storm.radius + NAVIGATION_CLEARANCE


@pytest.mark.parametrize("wing", [False, True])
def test_magnetic_carrier_restriction_is_wing_specific(wing):
    game, carrier, component, (unit,) = docked_craft(wing)
    carrier.position = Position(0, 0)
    game.galaxy.systems["Sol"].add_celestial_body(Storm((0, 0), "Sol", StormType.MAGNETIC))
    before = snapshot(component, unit, game.galaxy)
    assert component.deploy(unit, game.galaxy) is (not wing)
    if wing:
        assert snapshot(component, unit, game.galaxy) == before


def test_hull_blocking_fields_and_wing_exemption_use_shared_navigation_rules():
    game, carrier, _, (unit,) = docked_craft(True)
    field = AsteroidField((0, 0), "Sol")
    field.position, field.radius = Position(0, 0), 100
    game.galaxy.systems["Sol"].add_celestial_body(field)
    carrier.position = Position(110, 0)
    unit.hull_size = HullSize.HUGE
    with patch("deployment_placement.random.uniform", side_effect=[math.pi, 40, 0, 50]):
        position = find_deployment_position(carrier, unit, game.galaxy)
    assert position.x == 160
    unit.hull_size = HullSize.STRIKECRAFT_WING
    with patch("deployment_placement.random.uniform", side_effect=[math.pi, 40]):
        position = find_deployment_position(carrier, unit, game.galaxy)
    assert position.x == 70


def test_bulk_launch_keeps_blocked_wings_docked():
    game, carrier, component, (first, second) = docked_craft(True, count=2)
    with patch("deployment_placement.random.uniform", side_effect=[math.pi, 40] + [0, 50] * 100):
        order = DeployAllWingsOrder(carrier)
        order.execute(game.galaxy)
    assert order.status == OrderStatus.COMPLETED
    assert component.launched_units == [first]
    assert component.docked_units == [second]
    assert second.position == carrier.position
    assert component.get_used_slots() == 2
