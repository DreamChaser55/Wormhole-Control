import pytest
from unittest.mock import MagicMock
from geometry import Position, Circle, Vector
from unit_components import (
    Engines, Hyperdrive, HyperdriveType, JumpStatus,
    HyperspaceInhibitionFieldEmitter, Commander,
    Turret, TurretType, Weapons, ColonyComponent,
    Constructor, BuildableUnit, RepairComponent,
    MiningComponent, MetalRefineryComponent, CrystalRefineryComponent
)
from unit_orders import Order, OrderStatus, OrderType

from constants import HullSize

# Custom simple mocks to avoid Pygame setup during unit tests
class MockPlayer:
    def __init__(self, name="Test Player"):
        self.id = 1
        self.name = name
        self.credits = 1000
        self.metal = 1000
        self.crystal = 1000

class MockUnit:
    def __init__(self):
        self.id = 123
        self.name = "Test Unit"
        self.position = Position(0, 0)
        self.in_hex = (0, 0)
        self.in_system = "Sol"
        self.owner = MockPlayer()
        self.components = {}
        self.in_galaxy = MagicMock()
        self.current_hit_points = 100
        self.max_hit_points = 100
        self.game = MagicMock()
        self.hull_size = HullSize.HUGE
        
    def add_component(self, component):
        self.components[type(component)] = component
        
    def get_component(self, component_type):
        return self.components.get(component_type)
        
    @property
    def engines_component(self): return self.get_component(Engines)
    @property
    def hyperdrive_component(self): return self.get_component(Hyperdrive)
    @property
    def inhibitor_component(self): return self.get_component(HyperspaceInhibitionFieldEmitter)
    @property
    def weapons_component(self): return self.get_component(Weapons)
    @property
    def colony_component(self): return self.get_component(ColonyComponent)
    @property
    def constructor_component(self): return self.get_component(Constructor)
    @property
    def repair_component(self): return self.get_component(RepairComponent)
    @property
    def commander_component(self): return self.get_component(Commander)
    @property
    def mining_component(self): return self.get_component(MiningComponent)
    @property
    def metal_refinery_component(self): return self.get_component(MetalRefineryComponent)
    @property
    def crystal_refinery_component(self): return self.get_component(CrystalRefineryComponent)

    def take_damage(self, amount):
        self.current_hit_points -= amount

    def take_component_damage(self, component_type, amount):
        component = self.get_component(component_type)
        if not component or component.is_destroyed:
            return amount
        component.current_hit_points -= amount
        spillover = 0
        if component.current_hit_points <= 0:
            spillover = abs(component.current_hit_points)
            component.current_hit_points = 0
            component.on_destroyed()
        return spillover

    def heal_hull(self, amount):
        if self.current_hit_points >= self.max_hit_points:
            return 0
        healed = min(amount, self.max_hit_points - self.current_hit_points)
        self.current_hit_points += healed
        return healed

    def heal_components(self, amount):
        healed_total = 0
        for component in self.components.values():
            if amount <= 0:
                break
            if component.current_hit_points < component.max_hit_points:
                needed = component.max_hit_points - component.current_hit_points
                healed = min(amount, needed)
                component.current_hit_points += healed
                healed_total += healed
                amount -= healed
        return healed_total

    def update(self):
        if self.hyperdrive_component:
            self.hyperdrive_component.update_recharge()
        if self.weapons_component and self.in_galaxy:
            self.weapons_component.update(self.in_galaxy)
        if self.constructor_component and self.in_galaxy:
            self.constructor_component.update(self.in_galaxy)
        if self.repair_component and self.in_galaxy:
            self.repair_component.update(self.in_galaxy)
        if self.commander_component:
            self.commander_component.update()

def test_engines():
    unit = MockUnit()
    engines = Engines(unit, speed=100.0)
    assert engines.speed == 100.0
    assert engines.move_target is None

def test_hyperdrive_recharge():
    unit = MockUnit()
    hd = Hyperdrive(unit, drive_type=HyperdriveType.BASIC, recharge_duration=3)
    
    assert hd.jump_status == JumpStatus.READY
    assert hd.recharge_time_remaining == 0
    
    hd.start_recharge()
    assert hd.jump_status == JumpStatus.CHARGING
    assert hd.recharge_time_remaining == 3
    
    hd.update_recharge()
    assert hd.recharge_time_remaining == 2
    assert hd.jump_status == JumpStatus.CHARGING
    
    hd.update_recharge()
    hd.update_recharge()
    assert hd.recharge_time_remaining == 0
    assert hd.jump_status == JumpStatus.READY

def test_inhibition_field():
    unit = MockUnit()
    emitter = HyperspaceInhibitionFieldEmitter(unit, radius=100.0)
    
    assert not emitter.is_active
    
    # Set up mock spatial structure for toggle validation
    mock_hex = MagicMock()
    mock_hex.boundary_circle = Circle(Position(0, 0), 500.0)
    mock_hex.dynamic_inhibition_zones = {}
    mock_hex.get_all_inhibition_zones.return_value = []
    
    mock_system = MagicMock()
    mock_system.hexes = {(0, 0): mock_hex}
    
    mock_galaxy = MagicMock()
    mock_galaxy.systems = {"Sol": mock_system}
    
    # 1. Success path
    success = emitter.toggle(mock_galaxy)
    assert success
    assert emitter.is_active
    assert unit.id in mock_hex.dynamic_inhibition_zones
    
    # 2. Toggle off
    success_off = emitter.toggle(mock_galaxy)
    assert success_off
    assert not emitter.is_active
    assert unit.id not in mock_hex.dynamic_inhibition_zones
    
    # 3. Fail: Field boundary crosses hex boundary
    unit.position = Position(450, 0) # Close to boundary of 500
    success_boundary_fail = emitter.toggle(mock_galaxy)
    assert not success_boundary_fail
    assert not emitter.is_active
    
    # 4. Fail: Overlaps with an existing zone
    unit.position = Position(0, 0)
    existing_zone = Circle(Position(50, 0), 100.0)
    mock_hex.get_all_inhibition_zones.return_value = [existing_zone]
    success_overlap_fail = emitter.toggle(mock_galaxy)
    assert not success_overlap_fail
    assert not emitter.is_active

def test_commander():
    unit = MockUnit()
    commander = Commander(unit)
    
    order1 = MagicMock(spec=Order)
    order1.order_id = "1"
    order1.is_completed.return_value = False
    order1.status = OrderStatus.PENDING
    
    order2 = MagicMock(spec=Order)
    order2.order_id = "2"
    
    commander.add_order(order1)
    commander.add_order(order2)
    
    assert commander.get_active_orders_count() == 2
    assert commander.current_order == order1
    order1.execute.assert_called_once()
    
    # Cancel order 2 from queue
    cancelled = commander.cancel_order("2")
    assert cancelled
    assert commander.get_active_orders_count() == 1
    order2.cancel.assert_called_once()
    
    # Clear orders
    commander.clear_orders()
    assert commander.get_active_orders_count() == 0
    order1.cancel.assert_called_once()

def test_weapons_and_turrets():
    unit = MockUnit()
    target = MockUnit()
    weapons = Weapons(unit)
    
    turret = Turret(
        turret_type=TurretType.MASS_DRIVER,
        damage=10,
        range=100.0,
        cooldown=2,
        parent_unit=unit
    )
    
    weapons.add_turret(turret)
    assert len(weapons.turrets) == 1
    
    weapons.set_target(target)
    assert turret.target == target
    
    # Set coordinates for range check
    unit.in_system = "Sol"
    unit.in_hex = (0, 0)
    unit.position = Position(0, 0)
    
    target.in_system = "Sol"
    target.in_hex = (0, 0)
    target.position = Position(50, 0) # within range of 100
    
    # Update weapons: turret should fire
    mock_galaxy = MagicMock()
    weapons.update(mock_galaxy)
    
    # Target takes damage
    assert target.current_hit_points == 90
    assert turret.current_cooldown == 2
    
    # Update cooldown
    weapons.update(mock_galaxy)
    assert turret.current_cooldown == 1
    
    # Clear target
    weapons.clear_target()
    assert turret.target is None

def test_colony_component():
    unit = MockUnit()
    colony = ColonyComponent(unit)
    
    planet = MagicMock()
    planet.name = "Terra"
    planet.owner = unit.owner
    planet.population = 80
    planet.max_population = 100
    
    # Load population
    success = colony.load_population(planet, 50)
    assert success
    assert planet.population == 30
    assert colony.population_cargo == 50
    
    # Load too much (exceeds cargo limit of 100)
    success_fail = colony.load_population(planet, 60)
    assert not success_fail
    
    # Unload population to unowned planet
    unowned_planet = MagicMock()
    unowned_planet.name = "Mars"
    unowned_planet.owner = None
    unowned_planet.population = 0
    
    success_unload = colony.unload_population(unowned_planet, 30)
    assert success_unload
    assert unowned_planet.owner == unit.owner
    assert unowned_planet.population == 30
    assert colony.population_cargo == 20

def test_constructor():
    unit = MockUnit()
    constructor = Constructor(unit, hull_cost=10)
    
    bu = BuildableUnit(unit_template_name="Station", time_to_build=3, cost_credits=300)
    constructor.buildable_units.append(bu)
    
    assert constructor.can_build("Station") == bu
    assert constructor.can_build("Fighter") is None
    
    # Start construction
    unit.owner.credits = 500
    galaxy = MagicMock()
    
    success = constructor.start_construction("Station", Position(10, 10), galaxy)
    assert success
    assert unit.owner.credits == 200
    assert constructor.current_construction_target == ("Station", Position(10, 10))
    assert constructor.time_to_build == 3
    assert constructor.construction_progress == 0
    
    # Update construction
    constructor.update(galaxy)
    assert constructor.construction_progress == 1
    
    # Cancel construction
    constructor.cancel_construction()
    assert constructor.current_construction_target is None


def test_repair_component():
    # Setup repairer unit
    repairer = MockUnit()
    repair_comp = RepairComponent(
        repairer,
        repair_rate=15.0,
        repair_range=200.0,
        credit_cost_per_hp=1.0,
        hull_cost=10
    )
    repairer.add_component(repair_comp)

    # Setup target unit
    target = MockUnit()
    target.owner = repairer.owner  # Friendly
    target.in_system = repairer.in_system
    target.in_hex = repairer.in_hex
    target.position = Position(50, 0)  # within 200 range

    # Damage target
    target.take_damage(20)
    assert target.current_hit_points == 80

    # Set target
    repair_comp.set_target(target)
    assert repair_comp.target == target

    # Update: target should be repaired by 15 HP
    mock_galaxy = MagicMock()
    initial_credits = repairer.owner.credits
    repair_comp.update(mock_galaxy)

    # Target repaired: 80 -> 95. Credits deducted: 15
    assert target.current_hit_points == 95
    assert repairer.owner.credits == initial_credits - 15

    # Update again: target should be repaired to 100 max HP
    repair_comp.update(mock_galaxy)
    assert target.current_hit_points == 100
    # Repair amount was 5 (95 -> 100). Total credits deducted should be 15 + 5 = 20
    assert repairer.owner.credits == initial_credits - 20

    # Damage target component
    some_comp = Engines(target, hull_cost=5)
    some_comp.current_hit_points = 20  # damaged from 50 (max_hit_points = max(10, 50) = 50)
    target.add_component(some_comp)

    # Update: component should be repaired
    current_credits = repairer.owner.credits
    repair_comp.update(mock_galaxy)
    # Target hull is full (100). Target component should get 15 HP (20 -> 35). Credits: 15 deducted
    assert some_comp.current_hit_points == 35
    assert repairer.owner.credits == current_credits - 15

    # Test out of credits
    repairer.owner.credits = 5
    current_credits = repairer.owner.credits
    repair_comp.update(mock_galaxy)
    # Should only repair 5 HP because of credits limit
    assert some_comp.current_hit_points == 40
    assert repairer.owner.credits == 0

def test_mining_component():
    unit = MockUnit()
    mining = MiningComponent(unit, mining_rate=10.0, max_cargo=50.0)
    
    from entities import Asteroid, AsteroidField, Moon
    asteroid = Asteroid(in_hex=(0,0), in_system="Sol")
    asteroid.position = Position(10, 0) # within 200 range
    
    # Not targeting
    mock_galaxy = MagicMock()
    mining.update(mock_galaxy)
    assert mining.raw_metal_cargo == 0
    
    # Target asteroid
    mining.set_target(asteroid)
    mining.update(mock_galaxy)
    assert mining.raw_metal_cargo == 10.0
    assert mining.get_cargo_fullness() == 10.0 / 50.0
    
    # Out of range
    asteroid.position = Position(300, 0)
    mining.update(mock_galaxy)
    assert mining.raw_metal_cargo == 10.0
    
    # Back in range and fill cargo
    asteroid.position = Position(0, 0)
    for _ in range(5):
        mining.update(mock_galaxy)
        
    assert mining.raw_metal_cargo == 50.0
    assert mining.get_cargo_fullness() == 1.0
    
    # Verify unload
    metal, crystal = mining.unload_to_refinery()
    assert metal == 50.0
    assert crystal == 0.0
    assert mining.raw_metal_cargo == 0.0

    # Target asteroid field
    asteroid_field = AsteroidField(in_hex=(0,0), in_system="Sol")
    asteroid_field.position = Position(0, 0)
    mining.set_target(asteroid_field)
    mining.update(mock_galaxy)
    assert mining.raw_metal_cargo == 10.0

def test_refinery_components():
    unit = MockUnit()
    unit.owner.metal = 100
    unit.owner.crystal = 100
    
    metal_refinery = MetalRefineryComponent(unit)
    metal_refinery.accept_resources(50)
    assert unit.owner.metal == 150
    
    crystal_refinery = CrystalRefineryComponent(unit)
    crystal_refinery.accept_resources(30)
    assert unit.owner.crystal == 130


def test_ship_size_hyperdrive_restrictions_in_constructor():
    # Setup constructor
    unit = MockUnit()
    constructor = Constructor(unit, hull_cost=10)
    
    # We will mock the galaxy and systems
    galaxy = MagicMock()
    mock_system = MagicMock()
    galaxy.systems = {"Sol": mock_system}
    
    # Let's mock the UNIT_TEMPLATES dict in unit_components module to have custom templates
    import unit_components
    from constants import HullSize
    
    # Backup original
    original_templates = unit_components.UNIT_TEMPLATES
    try:
        unit_components.UNIT_TEMPLATES = {
            "TINY_TEST": {
                "name": "Tiny Test",
                "hull_size": HullSize.TINY,
                "has_engine": True,
                "has_hyperdrive": True,
                "hyperdrive_type": "BASIC"
            },
            "SMALL_TEST_ADVANCED": {
                "name": "Small Test",
                "hull_size": HullSize.SMALL,
                "has_engine": True,
                "has_hyperdrive": True,
                "hyperdrive_type": "ADVANCED"
            },
            "MEDIUM_TEST_ADVANCED": {
                "name": "Medium Test",
                "hull_size": HullSize.MEDIUM,
                "has_engine": True,
                "has_hyperdrive": True,
                "hyperdrive_type": "ADVANCED"
            }
        }
        
        # Test TINY_TEST template creation
        constructor.create_unit_from_template(galaxy, "TINY_TEST", unit.owner, "Sol", (0, 0), Position(0, 0))
        created_units = mock_system.add_unit.call_args_list
        assert len(created_units) == 1
        tiny_unit = created_units[0][0][0]
        # TINY ship should NOT have a hyperdrive component
        assert tiny_unit.hyperdrive_component is None
        
        # Reset mock
        mock_system.add_unit.reset_mock()
        
        # Test SMALL_TEST_ADVANCED template creation
        constructor.create_unit_from_template(galaxy, "SMALL_TEST_ADVANCED", unit.owner, "Sol", (0, 0), Position(0, 0))
        created_units = mock_system.add_unit.call_args_list
        assert len(created_units) == 1
        small_unit = created_units[0][0][0]
        # SMALL ship should have a BASIC hyperdrive component, even though template said ADVANCED
        assert small_unit.hyperdrive_component is not None
        assert small_unit.hyperdrive_component.drive_type == HyperdriveType.BASIC
        
        # Reset mock
        mock_system.add_unit.reset_mock()
        
        # Test MEDIUM_TEST_ADVANCED template creation
        constructor.create_unit_from_template(galaxy, "MEDIUM_TEST_ADVANCED", unit.owner, "Sol", (0, 0), Position(0, 0))
        created_units = mock_system.add_unit.call_args_list
        assert len(created_units) == 1
        medium_unit = created_units[0][0][0]
        # MEDIUM ship should have an ADVANCED hyperdrive component
        assert medium_unit.hyperdrive_component is not None
        assert medium_unit.hyperdrive_component.drive_type == HyperdriveType.ADVANCED

    finally:
        unit_components.UNIT_TEMPLATES = original_templates


def test_shipyard_refinery_options():
    from unit_templates import UNIT_TEMPLATES
    
    # 1. Verify template contains the refinery options
    shipyard_tmpl = UNIT_TEMPLATES.get("SHIPYARD_MK1")
    assert shipyard_tmpl is not None
    buildable = shipyard_tmpl.get("buildable_units", [])
    assert "METAL_REFINERY_STATION" in buildable
    assert "CRYSTAL_REFINERY_STATION" in buildable

    # 2. Verify Constructor component populated from templates registers them
    unit = MockUnit()
    constructor = Constructor(
        unit, 
        hull_cost=30, 
        buildable_unit_names=shipyard_tmpl.get("buildable_units")
    )
    
    assert constructor.can_build("METAL_REFINERY_STATION") is not None
    assert constructor.can_build("CRYSTAL_REFINERY_STATION") is not None

