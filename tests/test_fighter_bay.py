import pytest
from unittest.mock import MagicMock
from geometry import Position
from constants import HullSize
from unit_components import FighterWingComponent, FighterBayComponent
from unit_orders import OrderStatus, OrderType, DockOrder, DeployUnitOrder, DeployAllWingsOrder
from tests.test_unit_components import MockUnit as BaseMockUnit, MockPlayer

class MockUnit(BaseMockUnit):
    @property
    def hangar_component(self):
        from unit_components import HangarComponent
        return self.get_component(HangarComponent)

    @property
    def fighter_bay_component(self):
        return self.get_component(FighterBayComponent)

    @property
    def fighter_wing_component(self):
        return self.get_component(FighterWingComponent)

def test_fighter_wing_active_fighters():
    wing = MockUnit()
    wing.max_hit_points = 40
    wing.current_hit_points = 40
    
    wing_comp = FighterWingComponent(wing)
    wing.add_component(wing_comp)

    # 40 HP = 4 fighters
    assert wing_comp.active_fighters == 4

    # 30 HP = 3 fighters
    wing.current_hit_points = 30
    assert wing_comp.active_fighters == 3

    # 25 HP = 3 fighters (ceil(25/40 * 4) = ceil(2.5) = 3)
    wing.current_hit_points = 25
    assert wing_comp.active_fighters == 3

    # 1 HP = 1 fighter
    wing.current_hit_points = 1
    assert wing_comp.active_fighters == 1

    # 0 HP = 0 fighters
    wing.current_hit_points = 0
    assert wing_comp.active_fighters == 0

def test_fighter_bay_capacity():
    carrier = MockUnit()
    fighter_bay = FighterBayComponent(carrier, max_slots=2)
    carrier.add_component(fighter_bay)

    strikecraft = MockUnit()
    strikecraft.hull_size = HullSize.STRIKECRAFT_WING

    tiny_ship = MockUnit()
    tiny_ship.hull_size = HullSize.TINY

    # Can dock strikecraft, but NOT tiny_ship
    assert fighter_bay.can_dock(strikecraft)
    assert not fighter_bay.can_dock(tiny_ship)

    # Test slots: 2 slots max
    assert fighter_bay.dock(strikecraft, carrier.in_galaxy)
    assert fighter_bay.get_used_slots() == 1

    strikecraft2 = MockUnit()
    strikecraft2.hull_size = HullSize.STRIKECRAFT_WING
    assert fighter_bay.dock(strikecraft2, carrier.in_galaxy)
    assert fighter_bay.get_used_slots() == 2

    strikecraft3 = MockUnit()
    strikecraft3.hull_size = HullSize.STRIKECRAFT_WING
    assert not fighter_bay.can_dock(strikecraft3)

def test_fighter_bay_dock_and_deploy():
    carrier = MockUnit()
    fighter_bay = FighterBayComponent(carrier, max_slots=2)
    carrier.add_component(fighter_bay)

    wing = MockUnit()
    wing.hull_size = HullSize.STRIKECRAFT_WING
    wing.in_system = "Sol"
    wing.in_hex = (0, 0)
    wing.position = Position(10, 20)

    # Mock galaxy and systems
    galaxy = MagicMock()
    mock_system = MagicMock()
    galaxy.systems = {"Sol": mock_system}
    carrier.in_galaxy = galaxy

    # Dock
    assert fighter_bay.dock(wing, galaxy)
    assert wing in fighter_bay.docked_units
    mock_system.remove_unit.assert_called_once_with(wing)
    assert wing.in_system == carrier.in_system
    assert wing.in_hex == carrier.in_hex

    # Deploy
    assert fighter_bay.deploy(wing, galaxy)
    assert wing not in fighter_bay.docked_units
    mock_system.add_unit.assert_called_once_with(wing)

def test_fighter_bay_auto_construction():
    carrier = MockUnit()
    carrier.owner.credits = 200
    fighter_bay = FighterBayComponent(carrier, max_slots=1)
    carrier.add_component(fighter_bay)

    galaxy = MagicMock()
    
    # Mock template for construction
    from unit_templates import UNIT_TEMPLATES
    UNIT_TEMPLATES["FIGHTER_WING"] = {
        "name": "Fighter Wing",
        "hull_size": HullSize.STRIKECRAFT_WING,
        "has_engine": True,
        "engine_speed": 150.0,
        "engine_hull_cost": 2
    }

    # First turn: start construction
    fighter_bay.update(galaxy)
    assert fighter_bay.constructing
    assert fighter_bay.construction_progress == 0
    assert carrier.owner.credits == 50  # 200 - 150

    # Tick 1: progress becomes 1
    fighter_bay.update(galaxy)
    assert fighter_bay.constructing
    assert fighter_bay.construction_progress == 1

    # Tick 2: construction completes and wing is docked
    fighter_bay.update(galaxy)
    assert not fighter_bay.constructing
    assert fighter_bay.get_used_slots() == 1
    
    new_wing = fighter_bay.docked_units[0]
    assert new_wing.hull_size == HullSize.STRIKECRAFT_WING
    assert new_wing.fighter_wing_component is not None

def test_fighter_bay_auto_replenishment():
    carrier = MockUnit()
    carrier.owner.credits = 100
    fighter_bay = FighterBayComponent(carrier, max_slots=1)
    carrier.add_component(fighter_bay)

    wing = MockUnit()
    wing.hull_size = HullSize.STRIKECRAFT_WING
    wing.max_hit_points = 40
    wing.current_hit_points = 20  # needs replenishment (2 fighters lost)
    wing_comp = FighterWingComponent(wing)
    wing.add_component(wing_comp)

    # Dock wing directly
    fighter_bay.docked_units.append(wing)

    galaxy = MagicMock()

    # First turn: start replenishment
    fighter_bay.update(galaxy)
    assert fighter_bay.replenishing_unit == wing
    assert fighter_bay.replenish_progress == 0
    assert carrier.owner.credits == 65  # 100 - 35

    # Tick 1: replenish completes, heals 10 HP
    fighter_bay.update(galaxy)
    assert wing.current_hit_points == 30
    
    # Immediately starts next replenishment since it's still damaged and we have credits
    assert fighter_bay.replenishing_unit == wing
    assert fighter_bay.replenish_progress == 0
    assert carrier.owner.credits == 30  # 65 - 35

    # Tick 2: replenish completes, heals 10 HP (now fully healed at 40)
    fighter_bay.update(galaxy)
    assert wing.current_hit_points == 40
    assert fighter_bay.replenishing_unit is None

def test_dock_and_deploy_orders_with_fighter_bay():
    carrier = MockUnit()
    carrier.id = 100
    carrier.in_system = "Sol"
    carrier.in_hex = (0, 0)
    carrier.position = Position(0, 0)
    
    fighter_bay = FighterBayComponent(carrier, max_slots=1)
    carrier.add_component(fighter_bay)

    wing = MockUnit()
    wing.id = 200
    wing.hull_size = HullSize.STRIKECRAFT_WING
    wing.in_system = "Sol"
    wing.in_hex = (0, 0)
    wing.position = Position(5, 5) # in range (<= 100.0)

    galaxy = MagicMock()
    galaxy.get_unit_by_id.side_effect = lambda uid: carrier if uid == carrier.id else wing
    galaxy.systems = {"Sol": MagicMock()}

    wing.game.galaxy = galaxy
    carrier.game.galaxy = galaxy

    # 1. Dock Order
    dock_order = DockOrder(wing, {"target_carrier_id": carrier.id})
    dock_order.execute(galaxy)

    assert dock_order.status == OrderStatus.COMPLETED
    assert wing in fighter_bay.docked_units

    # 2. Deploy Order
    deploy_order = DeployUnitOrder(carrier, {"docked_unit_id": wing.id})
    deploy_order.execute(galaxy)

    assert deploy_order.status == OrderStatus.COMPLETED
    assert wing not in fighter_bay.docked_units


def test_fighter_wing_limit_enforced():
    carrier = MockUnit()
    fighter_bay = FighterBayComponent(carrier, max_slots=1)
    carrier.add_component(fighter_bay)

    wing = MockUnit()
    wing.hull_size = HullSize.STRIKECRAFT_WING
    wing_comp = FighterWingComponent(wing)
    wing.add_component(wing_comp)
    
    galaxy = MagicMock()
    mock_system = MagicMock()
    galaxy.systems = {"Sol": mock_system}
    carrier.in_galaxy = galaxy
    
    # Initially 0/1 slots used
    assert fighter_bay.get_used_slots() == 0
    assert fighter_bay.can_dock(wing)

    # Dock wing: becomes 1/1
    assert fighter_bay.dock(wing, galaxy)
    assert fighter_bay.get_used_slots() == 1
    assert wing.fighter_wing_component.mother_carrier == carrier

    # Limit reached, cannot dock another wing
    other_wing = MockUnit()
    other_wing.hull_size = HullSize.STRIKECRAFT_WING
    assert not fighter_bay.can_dock(other_wing)

    # Deploy wing: still 1/1 (1 launched)
    assert fighter_bay.deploy(wing, galaxy)
    assert fighter_bay.get_used_slots() == 1
    assert wing in fighter_bay.launched_units
    assert wing not in fighter_bay.docked_units

    # Limit still reached, cannot dock another wing
    assert not fighter_bay.can_dock(other_wing)

    # Calling update with credits should NOT trigger construction since limit is reached
    carrier.owner.credits = 1000
    fighter_bay.update(galaxy)
    assert not fighter_bay.constructing

    # But we can dock the returning launched wing because it already occupies a slot
    assert fighter_bay.can_dock(wing)

    # If the launched wing is destroyed, slot is freed
    wing.current_hit_points = 0
    fighter_bay.update(galaxy)
    assert fighter_bay.get_used_slots() == 0
    assert fighter_bay.can_dock(other_wing)


def test_fighter_wing_orphan_adoption():
    carrier = MockUnit()
    fighter_bay = FighterBayComponent(carrier, max_slots=1)
    carrier.add_component(fighter_bay)

    wing = MockUnit()
    wing.hull_size = HullSize.STRIKECRAFT_WING
    wing_comp = FighterWingComponent(wing)
    wing.add_component(wing_comp)

    # Wing has no mother carrier (orphan)
    assert wing.fighter_wing_component.mother_carrier is None

    galaxy = MagicMock()
    mock_system = MagicMock()
    galaxy.systems = {"Sol": mock_system}
    carrier.in_galaxy = galaxy

    # Dock wing and check if it is adopted
    assert fighter_bay.dock(wing, galaxy)
    assert wing.fighter_wing_component.mother_carrier == carrier


def test_fighter_bay_deploy_offset():
    import math
    from constants import SECTOR_CIRCLE_RADIUS_LOGICAL
    
    carrier = MockUnit()
    carrier.position = Position(990.0, 0.0) # Near the right edge
    carrier.in_system = None # In sector view
    
    fighter_bay = FighterBayComponent(carrier, max_slots=2)
    carrier.add_component(fighter_bay)
    
    wing = MockUnit()
    wing.hull_size = HullSize.STRIKECRAFT_WING
    
    galaxy = MagicMock()
    fighter_bay.dock(wing, galaxy)
    
    # Deploy
    success = fighter_bay.deploy(wing, galaxy)
    assert success
    
    # Distance between carrier and wing should be between 20.0 and 50.0
    dist = math.hypot(wing.position.x - carrier.position.x, wing.position.y - carrier.position.y)
    assert 20.0 <= dist <= 50.0
    
    # Wing position should be inside sector radius
    wing_dist_from_center = math.hypot(wing.position.x, wing.position.y)
    assert wing_dist_from_center <= SECTOR_CIRCLE_RADIUS_LOGICAL


def test_deploy_all_wings_order():
    carrier = MockUnit()
    fighter_bay = FighterBayComponent(carrier, max_slots=2)
    carrier.add_component(fighter_bay)

    wing1 = MockUnit()
    wing1.hull_size = HullSize.STRIKECRAFT_WING
    wing1.in_system = "Sol"
    wing1.in_hex = (0, 0)
    wing1.position = Position(0, 0)

    wing2 = MockUnit()
    wing2.hull_size = HullSize.STRIKECRAFT_WING
    wing2.in_system = "Sol"
    wing2.in_hex = (0, 0)
    wing2.position = Position(0, 0)

    galaxy = MagicMock()
    mock_system = MagicMock()
    galaxy.systems = {"Sol": mock_system}
    carrier.in_galaxy = galaxy
    wing1.game.galaxy = galaxy
    wing2.game.galaxy = galaxy

    # Dock both wings
    assert fighter_bay.dock(wing1, galaxy)
    assert fighter_bay.dock(wing2, galaxy)
    assert len(fighter_bay.docked_units) == 2

    # Execute DeployAllWingsOrder
    deploy_all_order = DeployAllWingsOrder(carrier)
    deploy_all_order.execute(galaxy)

    assert deploy_all_order.status == OrderStatus.COMPLETED
    assert len(fighter_bay.docked_units) == 0
    assert len(fighter_bay.launched_units) == 2
    assert wing1 in fighter_bay.launched_units
    assert wing2 in fighter_bay.launched_units


