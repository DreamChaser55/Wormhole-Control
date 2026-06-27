import pytest
from unittest.mock import MagicMock
from geometry import Position
from constants import HullSize
from unit_components import FighterWingComponent, FighterBayComponent
from unit_orders import OrderStatus, OrderType, DockOrder, DeployUnitOrder
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
    strikecraft.hull_size = HullSize.STRIKECRAFT

    tiny_ship = MockUnit()
    tiny_ship.hull_size = HullSize.TINY

    # Can dock strikecraft, but NOT tiny_ship
    assert fighter_bay.can_dock(strikecraft)
    assert not fighter_bay.can_dock(tiny_ship)

    # Test slots: 2 slots max
    assert fighter_bay.dock(strikecraft, carrier.in_galaxy)
    assert fighter_bay.get_used_slots() == 1

    strikecraft2 = MockUnit()
    strikecraft2.hull_size = HullSize.STRIKECRAFT
    assert fighter_bay.dock(strikecraft2, carrier.in_galaxy)
    assert fighter_bay.get_used_slots() == 2

    strikecraft3 = MockUnit()
    strikecraft3.hull_size = HullSize.STRIKECRAFT
    assert not fighter_bay.can_dock(strikecraft3)

def test_fighter_bay_dock_and_deploy():
    carrier = MockUnit()
    fighter_bay = FighterBayComponent(carrier, max_slots=2)
    carrier.add_component(fighter_bay)

    wing = MockUnit()
    wing.hull_size = HullSize.STRIKECRAFT
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
        "hull_size": HullSize.STRIKECRAFT,
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
    assert new_wing.hull_size == HullSize.STRIKECRAFT
    assert new_wing.fighter_wing_component is not None

def test_fighter_bay_auto_replenishment():
    carrier = MockUnit()
    carrier.owner.credits = 100
    fighter_bay = FighterBayComponent(carrier, max_slots=1)
    carrier.add_component(fighter_bay)

    wing = MockUnit()
    wing.hull_size = HullSize.STRIKECRAFT
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
    wing.hull_size = HullSize.STRIKECRAFT
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
