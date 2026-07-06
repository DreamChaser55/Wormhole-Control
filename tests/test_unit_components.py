import pytest
from unittest.mock import MagicMock
from geometry import Position, Circle, Vector
from unit_components import (
    Engines, Hyperdrive, HyperdriveType, JumpStatus,
    HyperspaceInhibitionFieldEmitter, Commander, UnitStance,
    Turret, TurretType, TurretVariant, Weapons, ColonyComponent,
    Constructor, BuildableUnit, RepairComponent,
    MiningComponent, MetalRefineryComponent, CrystalRefineryComponent,
    Defenses, AntimatterStorage
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
        self.is_disabled = False
        self.damage_amplification = 0.0
        self.is_temporary = False
        self.current_hull_usage = 0
        # XP system
        self.experience_points = 0
        
    def add_component(self, component):
        self.components[type(component)] = component
        
    def get_component(self, component_type):
        return self.components.get(component_type)
        
    @property
    def engines_component(self): return self.get_component(Engines)
    @property
    def antimatter_component(self): return self.get_component(AntimatterStorage)
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

    def take_damage(self, amount, damage_type=None):
        if damage_type:
            defenses = self.get_component(Defenses)
            if defenses:
                amount = max(0, amount - defenses.calculate_mitigation(amount, damage_type))
        self.current_hit_points -= amount

    def take_component_damage(self, component_type, amount, damage_type=None):
        if damage_type:
            defenses = self.get_component(Defenses)
            if defenses:
                amount = max(0, amount - defenses.calculate_mitigation(amount, damage_type))
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

    def gain_experience(self, amount: int) -> None:
        from constants import MAX_UNIT_XP
        if self.experience_points >= MAX_UNIT_XP:
            return
        self.experience_points = min(MAX_UNIT_XP, self.experience_points + max(0, amount))

    def xp_multiplier(self, max_bonus: float) -> float:
        from constants import MAX_UNIT_XP
        return 1.0 + max_bonus * (self.experience_points / MAX_UNIT_XP)

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

def test_commander_stances():
    # Setup players
    player_friendly = MockPlayer()
    player_friendly.id = 1
    player_enemy = MockPlayer()
    player_enemy.id = 2

    # Setup units
    friendly = MockUnit()
    friendly.id = 100
    friendly.name = "Friendly Unit"
    friendly.owner = player_friendly
    friendly.in_system = "Sol"
    friendly.in_hex = (0, 0)
    friendly.position = Position(0, 0)

    enemy_in_range = MockUnit()
    enemy_in_range.id = 200
    enemy_in_range.name = "Enemy in Range"
    enemy_in_range.owner = player_enemy
    enemy_in_range.in_system = "Sol"
    enemy_in_range.in_hex = (0, 0)
    enemy_in_range.position = Position(10, 0) # 10 distance
    enemy_in_range.current_hit_points = 50

    enemy_in_sector = MockUnit()
    enemy_in_sector.id = 300
    enemy_in_sector.name = "Enemy in Sector but out of range"
    enemy_in_sector.owner = player_enemy
    enemy_in_sector.in_system = "Sol"
    enemy_in_sector.in_hex = (0, 0)
    enemy_in_sector.position = Position(500, 0) # 500 distance (out of 100 range)
    enemy_in_sector.current_hit_points = 50

    enemy_in_jump_range = MockUnit()
    enemy_in_jump_range.id = 400
    enemy_in_jump_range.name = "Enemy in different sector, within jump range"
    enemy_in_jump_range.owner = player_enemy
    enemy_in_jump_range.in_system = "Sol"
    enemy_in_jump_range.in_hex = (0, 1) # hex distance 1
    enemy_in_jump_range.position = Position(0, 0)
    enemy_in_jump_range.current_hit_points = 50

    enemy_far = MockUnit()
    enemy_far.id = 500
    enemy_far.name = "Enemy far away in system"
    enemy_far.owner = player_enemy
    enemy_far.in_system = "Sol"
    enemy_far.in_hex = (0, 5) # hex distance 5
    enemy_far.position = Position(0, 0)
    enemy_far.current_hit_points = 50

    # Add components to friendly unit
    weapons = Weapons(friendly)
    turret = Turret(
        turret_type=TurretType.MASS_DRIVER,
        damage=10,
        range=100.0,
        cooldown=2,
        parent_unit=friendly
    )
    weapons.add_turret(turret)
    friendly.add_component(weapons)

    hyperdrive = Hyperdrive(friendly, drive_type=HyperdriveType.BASIC, jump_range=2)
    friendly.add_component(hyperdrive)

    commander = Commander(friendly)
    friendly.add_component(commander)

    # Setup mock galaxy and system structure
    mock_galaxy = MagicMock()
    friendly.in_galaxy = mock_galaxy
    friendly.game.galaxy = mock_galaxy
    mock_galaxy.get_unit_by_id.side_effect = lambda uid: {
        100: friendly,
        200: enemy_in_range,
        300: enemy_in_sector,
        400: enemy_in_jump_range,
        500: enemy_far
    }.get(uid)

    mock_system = MagicMock()
    mock_galaxy.systems.get.return_value = mock_system

    # Set up hexes containing units
    hex_center = MagicMock()
    hex_center.units = [friendly, enemy_in_range, enemy_in_sector]
    hex_jump = MagicMock()
    hex_jump.units = [enemy_in_jump_range]
    hex_far = MagicMock()
    hex_far.units = [enemy_far]

    mock_system.hexes = {
        (0, 0): hex_center,
        (0, 1): hex_jump,
        (0, 5): hex_far
    }

    # Test Stance: DO_NOTHING
    commander.stance = UnitStance.DO_NOTHING
    commander.update()
    assert commander.current_order is None
    assert turret.target is None

    # Test Stance: ATTACK_WEAPON_RANGE
    commander.stance = UnitStance.ATTACK_WEAPON_RANGE
    commander.update()
    assert commander.current_order is None
    assert turret.target == enemy_in_range

    # If the target moves out of range or dies, it should clear and find no target
    enemy_in_range.position = Position(200, 0) # out of 100 range
    commander.update()
    assert turret.target is None

    # Move target back
    enemy_in_range.position = Position(10, 0)
    commander.update()
    assert turret.target == enemy_in_range

    # Test Stance: ATTACK_SAME_SECTOR
    enemy_in_range.current_hit_points = 0 # dead
    commander.stance = UnitStance.ATTACK_SAME_SECTOR
    weapons.clear_target()
    commander.update()
    assert commander.current_order is not None
    assert getattr(commander.current_order, 'is_stance_order', False)
    assert commander.current_order.parameters["target_unit_id"] == enemy_in_sector.id

    # If enemy_in_sector leaves the sector, the order should get cancelled
    enemy_in_sector.in_hex = (0, 1)
    commander.update()
    assert commander.current_order is None

    # Test Stance: ATTACK_INTRA_SYSTEM_JUMP_RANGE
    enemy_in_sector.current_hit_points = 0 # dead
    commander.stance = UnitStance.ATTACK_INTRA_SYSTEM_JUMP_RANGE
    commander.update()
    assert commander.current_order is not None
    assert commander.current_order.parameters["target_unit_id"] == enemy_in_jump_range.id

    # If the target moves too far away (e.g. to (0, 5)), the order should be cancelled
    enemy_in_jump_range.in_hex = (0, 5)
    commander.update()
    assert commander.current_order is None

    # Test Stance: ATTACK_SAME_SYSTEM
    enemy_in_jump_range.current_hit_points = 0 # dead
    commander.stance = UnitStance.ATTACK_SAME_SYSTEM
    commander.update()
    assert commander.current_order is not None
    assert commander.current_order.parameters["target_unit_id"] == enemy_far.id

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
    from unit_templates import register_template, unregister_template
    from constants import HullSize

    register_template("Station", {
        "name": "Station",
        "hull_size": HullSize.MEDIUM,
        "build_time": 3,
        "build_cost": 300
    })

    try:
        unit = MockUnit()
        constructor = Constructor(unit, hull_cost=10)
        
        bu = constructor.can_build("Station")
        assert bu is not None
        assert bu.unit_template_name == "Station"
        assert bu.time_to_build == 3
        assert bu.cost_credits == 300
        
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
    finally:
        unregister_template("Station")


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
        # TINY ship should have a BASIC hyperdrive component
        assert tiny_unit.hyperdrive_component is not None
        assert tiny_unit.hyperdrive_component.drive_type == HyperdriveType.BASIC
        assert tiny_unit.hyperdrive_component.hull_cost == 5
        
        # Reset mock
        mock_system.add_unit.reset_mock()
        
        # Test SMALL_TEST_ADVANCED template creation
        constructor.create_unit_from_template(galaxy, "SMALL_TEST_ADVANCED", unit.owner, "Sol", (0, 0), Position(0, 0))
        created_units = mock_system.add_unit.call_args_list
        assert len(created_units) == 1
        small_unit = created_units[0][0][0]
        # SMALL ship should have an ADVANCED hyperdrive component
        assert small_unit.hyperdrive_component is not None
        assert small_unit.hyperdrive_component.drive_type == HyperdriveType.ADVANCED
        assert small_unit.hyperdrive_component.hull_cost == 10
        
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
    # Verify Constructor component can build refinery templates
    unit = MockUnit()
    constructor = Constructor(unit, hull_cost=30)
    
    assert constructor.can_build("METAL_REFINERY_STATION") is not None
    assert constructor.can_build("CRYSTAL_REFINERY_STATION") is not None


def test_defenses():
    # Test Defenses component mitigation logic directly
    unit = MockUnit()
    defenses = Defenses(unit, armor=20, shields=50, point_defense=10)
    unit.add_component(defenses)

    # Mitigation with MASS_DRIVER
    # Armor (matching): random(0, 20) -> avg 10
    # Shields (non-matching): random(0, sqrt(50)) -> random(0, 7) -> avg 3.5
    # Point Defense (non-matching): random(0, sqrt(10)) -> random(0, 3) -> avg 1.5
    # Max mitigation = 20 + 7 + 3 = 30
    mitigations = [defenses.calculate_mitigation(100, TurretType.MASS_DRIVER) for _ in range(100)]
    assert all(0 <= m <= 30 for m in mitigations)
    # Check that we actually rolled some values > 0
    assert any(m > 0 for m in mitigations)

    # Test that mitigation is capped at incoming damage
    assert defenses.calculate_mitigation(5, TurretType.MASS_DRIVER) <= 5

    # Test take_damage integration
    unit.current_hit_points = 100
    # Mocking random to return max values
    import unittest.mock as mock
    with mock.patch("random.randint", side_effect=lambda a, b: b):
        unit.take_damage(50, TurretType.MASS_DRIVER)
        # Expected mitigation:
        # armor = 20
        # shields = sqrt(50) = 7
        # point_defense = sqrt(10) = 3
        # Total mitigation = 20 + 7 + 3 = 30
        # Damage taken = 50 - 30 = 20
        # Remaining HP = 100 - 20 = 80
        assert unit.current_hit_points == 80


def test_turret_variants():
    unit = MockUnit()
    target_normal = MockUnit()
    target_normal.hull_size = HullSize.MEDIUM
    target_strikecraft = MockUnit()
    target_strikecraft.hull_size = HullSize.STRIKECRAFT_WING

    # 1. Standard turret: Cannot target strikecraft
    weapons_std = Weapons(unit)
    turret_std = Turret(
        turret_type=TurretType.MASS_DRIVER,
        damage=10.0,
        range=100.0,
        cooldown=2,
        parent_unit=unit,
        variant=TurretVariant.STANDARD
    )
    weapons_std.add_turret(turret_std)
    
    # Try targeting normal target
    weapons_std.set_target(target_normal)
    assert turret_std.target == target_normal

    # Try targeting strikecraft (should be filtered out by set_target)
    weapons_std.clear_target()
    weapons_std.set_target(target_strikecraft)
    assert turret_std.target is None

    # 2. Long range turret: 3x range, 3x cooldown
    turret_lr = Turret(
        turret_type=TurretType.MASS_DRIVER,
        damage=10.0,
        range=100.0,
        cooldown=2,
        parent_unit=unit,
        variant=TurretVariant.LONG_RANGE
    )
    assert turret_lr.range == 300.0
    assert turret_lr.cooldown == 6

    # 3. Anti-strikecraft turret: Can target strikecraft, damage to others reduced to 25%
    weapons_as = Weapons(unit)
    turret_as = Turret(
        turret_type=TurretType.MASS_DRIVER,
        damage=100.0,
        range=100.0,
        cooldown=2,
        parent_unit=unit,
        variant=TurretVariant.ANTI_STRIKECRAFT
    )
    weapons_as.add_turret(turret_as)

    # Can target strikecraft
    weapons_as.set_target(target_strikecraft)
    assert turret_as.target == target_strikecraft

    # Damage against strikecraft: 100% (damage is 100)
    target_strikecraft.current_hit_points = 500
    turret_as.fire()
    assert target_strikecraft.current_hit_points == 400

    # Can target normal target, but damage is 25% (damage is 100 -> 25)
    weapons_as.clear_target()
    weapons_as.set_target(target_normal)
    assert turret_as.target == target_normal

    target_normal.current_hit_points = 500
    turret_as.fire()
    assert target_normal.current_hit_points == 475


def test_weapons_sidebar_data():
    # Setup unit and weapons component
    unit = MockUnit()
    weapons = Weapons(unit)
    unit.add_component(weapons)

    # Add standard turret
    turret1 = Turret(
        turret_type=TurretType.MASS_DRIVER,
        damage=15.0,
        range=300.0,
        cooldown=2,
        parent_unit=unit,
        variant=TurretVariant.STANDARD
    )
    weapons.add_turret(turret1)

    # Add long-range turret on cooldown, targeting Engines component of target_unit
    target_unit = MockUnit()
    target_unit.name = "Enemy Cruisey"
    
    turret2 = Turret(
        turret_type=TurretType.BEAM,
        damage=30.0,
        range=200.0,
        cooldown=3,
        parent_unit=unit,
        variant=TurretVariant.LONG_RANGE,
        current_cooldown=2,
        target=target_unit,
        target_component_type=Engines
    )
    weapons.add_turret(turret2)

    # Call get_sidebar_data
    mock_game = MagicMock()
    sidebar_data = weapons.get_sidebar_data(mock_game)
    
    # Assert elements exist
    assert len(sidebar_data) > 0
    assert sidebar_data[0]['type'] == 'label'
    assert "Weapons" in sidebar_data[0]['text']

    # Now verify turret 1 labels
    t1_header = sidebar_data[1]
    assert t1_header['type'] == 'label'
    assert "Turret 1" in t1_header['text']
    assert "Standard" in t1_header['text']
    assert "Mass Driver" in t1_header['text']

    t1_stats = sidebar_data[2]
    assert "Damage: 15" in t1_stats['text']
    assert "Range: 300" in t1_stats['text']
    assert "Cooldown: 2t" in t1_stats['text']

    t1_status = sidebar_data[3]
    assert "Status: Ready" in t1_status['text']
    assert "Target: None" in t1_status['text']

    # Spacer at index 4
    spacer = sidebar_data[4]
    assert spacer['text'] == ''
    assert spacer['height'] == 5

    # Turret 2 at index 5
    t2_header = sidebar_data[5]
    assert "Turret 2" in t2_header['text']
    assert "Long Range" in t2_header['text']
    assert "Beam" in t2_header['text']

    t2_stats = sidebar_data[6]
    assert "Damage: 30" in t2_stats['text']
    assert "Range: 600" in t2_stats['text']
    assert "Cooldown: 9t" in t2_stats['text']

    t2_status = sidebar_data[7]
    assert "Status: On Cooldown (2t)" in t2_status['text']
    assert "Target: Enemy Cruisey (Engines)" in t2_status['text']


def test_unit_template_name_assignment():
    from unittest.mock import MagicMock
    from entities import Unit
    from unit_components import Constructor, HangarComponent, WingType
    from constants import HullSize
    from geometry import Position
    import unit_components

    # 1. Test create_unit_from_template assigns template_name
    owner_unit = MockUnit()
    constructor = Constructor(owner_unit, hull_cost=30)
    owner_unit.add_component(constructor)

    galaxy = MagicMock()
    mock_system = MagicMock()
    galaxy.systems = {"Sol": mock_system}

    original_templates = unit_components.UNIT_TEMPLATES
    try:
        unit_components.UNIT_TEMPLATES = {
            "TEST_TEMPLATE": {
                "name": "Test Template Friendly Name",
                "hull_size": HullSize.TINY,
                "has_engine": True,
                "has_hyperdrive": False
            },
            "FIGHTER_WING": {
                "name": "Fighter Wing",
                "hull_size": HullSize.STRIKECRAFT_WING,
                "has_engine": True,
                "wing_type": "FIGHTER"
            }
        }
        
        # Test creation via create_unit_from_template
        constructor.create_unit_from_template(galaxy, "TEST_TEMPLATE", owner_unit.owner, "Sol", (0, 0), Position(0, 0))
        created_units = mock_system.add_unit.call_args_list
        assert len(created_units) == 1
        unit = created_units[0][0][0]
        assert unit.template_name == "Test Template Friendly Name"

        # 2. Test auto-construction in StrikecraftBayComponent assigns template_name
        from unit_components import StrikecraftBayComponent
        carrier_unit = MockUnit()
        carrier_unit.game = owner_unit.game
        bay = StrikecraftBayComponent(carrier_unit, max_slots=2)
        carrier_unit.add_component(bay)
        bay.build_wing_type = WingType.FIGHTER
        
        # Call auto-construction
        bay.finish_auto_construction(galaxy)
        assert len(bay.docked_units) == 1
        wing = bay.docked_units[0]
        assert wing.template_name == "Fighter Wing"

    finally:
        unit_components.UNIT_TEMPLATES = original_templates


def test_unit_template_name_in_sidebar():
    from entities import Unit
    from game import Game
    from unittest.mock import MagicMock
    from constants import HullSize
    from geometry import Position
    
    # Setup mock game and unit
    mock_game = MagicMock()
    mock_game.galaxy = MagicMock()
    mock_game.sidebar_needs_update = True
    mock_game.selected_objects = []
    
    player = MagicMock()
    player.name = "Player 1"
    
    unit = Unit(
        owner=player,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="My Constructor",
        hull_size=HullSize.MEDIUM,
        game=mock_game,
        template_name="Constructor Mk.I"
    )
    
    mock_game.selected_objects = [unit]
    mock_game.players = [player]
    mock_game.current_player_index = 0
    mock_game.selected_component_name = None
    mock_game.gui = MagicMock()
    
    # Call update_side_bar_content (which is on Game class)
    Game.update_side_bar_content(mock_game)
    
    # Verify that the gui update was called with sidebar data containing the template label
    mock_game.gui.update_side_bar_content.assert_called_once()
    data_list = mock_game.gui.update_side_bar_content.call_args[0][0]
    
    template_labels = [d for d in data_list if d.get("type") == "label" and "Template: Constructor Mk.I" in d.get("text", "")]
    assert len(template_labels) == 1





