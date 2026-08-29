"""
tests/test_intelligence_system.py

Comprehensive test suite for Intelligence (Espionage), Counter-Intelligence, and Sabotage:
1. Component initialization, dynamic hull costs, and template validation
2. Deploying agents onto enemy units and colonized celestial bodies
3. Sensor vision sharing through infiltrating agents
4. Unit system sabotages:
   - Engines (-50% speed)
   - Weapons (-50% damage)
   - Defenses (-50% mitigation)
   - Hyperdrive (+3 recharge turns)
   - Sensors (-50% short range, 0 long range hexes)
   - Antimatter (50% current AM drained)
5. Colony sabotages:
   - Economy (-50% tax to owner, +25% siphon to agent owner)
   - Growth (halts population growth)
6. Agent relocation between valid hosts in range
7. Counter-Intelligence sweep & passive detection
8. Eliminating discovered enemy agents
9. Agent extraction back to parent intelligence vessel
10. Save and load persistence of intelligence state and agents
"""

import pytest
from unittest.mock import MagicMock
from geometry import Position
from constants import (
    HullSize,
    DEFAULT_SENSOR_SHORT_RANGE,
    TAX_RATE,
    CI_SWEEP_CREDIT_COST,
    CI_SWEEP_ANTIMATTER_COST,
    CI_SWEEP_COOLDOWN_TURNS,
    CI_SWEEP_RANGE,
)
from entities import Player, Unit, Planet, Moon, ColonizableAsteroid, Star
from unit_components import (
    Sensors,
    AntimatterStorage,
    Engines,
    Hyperdrive,
    HyperdriveType,
    Weapons,
    Turret,
    TurretType,
    TurretVariant,
    Defenses,
    IntelligenceComponent,
    Agent,
    SabotageType,
)
from unit_orders import (
    InfiltrateUnitOrder,
    InfiltratePlanetOrder,
    RelocateAgentOrder,
    SabotageOrder,
    CISweepOrder,
    EliminateAgentOrder,
    ExtractAgentOrder,
    OrderStatus,
    OrderType,
)
from visibility import VisibilityService
from galaxy import Galaxy, StarSystem
from custom_unit_templates import (
    CustomUnitTemplate,
    ComponentConfig,
    calc_intelligence_hull_cost,
    HULL_RESTRICTIONS,
)
from economy import calculate_player_income
from turn_processor import TurnProcessor
from save_manager import serialize_game_state, deserialize_game_state


@pytest.fixture
def test_setup():
    p1 = Player("Player 1", (0, 0, 255))
    p2 = Player("Player 2", (255, 0, 0))

    galaxy = Galaxy()
    system = StarSystem(name="Sol", position=Position(0, 0), radius=3)
    galaxy.systems = {"Sol": system}

    game = MagicMock()
    game.galaxy = galaxy
    game.players = [p1, p2]
    game.current_player_index = 0
    game.turn_number = 1
    game.current_system_name = "Sol"
    game.current_sector_coord = (0, 0)
    game.selected_objects = []

    return p1, p2, galaxy, system, game


def test_intelligence_component_init_and_hull_cost():
    # Cost formula: base 10 + 5 per additional agent (>1) + 10 for counter-intelligence
    assert calc_intelligence_hull_cost(1, False) == 10.0
    assert calc_intelligence_hull_cost(2, False) == 15.0
    assert calc_intelligence_hull_cost(3, False) == 20.0
    assert calc_intelligence_hull_cost(1, True) == 20.0
    assert calc_intelligence_hull_cost(3, True) == 30.0

    # Hull restrictions: prohibited on Strikecraft Wing and Tiny hulls
    assert "has_intelligence_component" in HULL_RESTRICTIONS[HullSize.STRIKECRAFT_WING]
    assert "has_intelligence_component" in HULL_RESTRICTIONS[HullSize.TINY]
    assert "has_intelligence_component" not in HULL_RESTRICTIONS[HullSize.SMALL]
    assert "has_intelligence_component" not in HULL_RESTRICTIONS[HullSize.MEDIUM]


def test_custom_template_validation(test_setup):
    p1, p2, galaxy, system, game = test_setup

    template = CustomUnitTemplate("Spy Ship", HullSize.MEDIUM)
    template.components.has_engine = True
    template.components.has_intelligence_component = True
    template.components.intelligence_agents_count = 2
    template.components.has_counter_intelligence = True

    errors = template.validate()
    assert errors == []
    assert template.components.intelligence_hull_cost == 25.0

    # Test invalid on Tiny hull
    tiny_template = CustomUnitTemplate("Tiny Spy", HullSize.TINY)
    tiny_template.components.has_intelligence_component = True
    tiny_errors = tiny_template.validate()
    assert any("Intelligence" in e or "has_intelligence_component" in e for e in tiny_errors)


def test_unit_infiltration_and_sensor_sharing(test_setup):
    p1, p2, galaxy, system, game = test_setup

    # Spy unit owned by P1
    spy_unit = Unit(p1, Position(100, 100), (0, 0), "Sol", "Spy Ship", HullSize.MEDIUM, game)
    intel_comp = IntelligenceComponent(spy_unit, agents_count=2, agents_capacity=2)
    spy_unit.add_component(intel_comp)
    system.hexes[(0, 0)].add_unit(spy_unit)

    # Enemy warship owned by P2 in same sector, far outside spy's default short sensor range (e.g., 400 units away)
    enemy_ship = Unit(p2, Position(400, 100), (0, 0), "Sol", "Enemy Cruiser", HullSize.LARGE, game)
    enemy_sensors = Sensors(enemy_ship, short_range_radius=200, long_range_hexes=1)
    enemy_ship.add_component(enemy_sensors)
    system.hexes[(0, 0)].add_unit(enemy_ship)

    # Initially, P1 cannot see enemy ship in detailed vision if out of spy's sensor radius
    spy_unit.sensors_component.short_range_radius = 50.0
    snap_before = VisibilityService.compute(galaxy, p1)
    assert enemy_ship.id not in snap_before.visible_enemy_unit_ids

    # Issue Infiltrate order
    order = InfiltrateUnitOrder(spy_unit, {"target_unit_id": enemy_ship.id})
    order.execute(galaxy)
    assert order.status == OrderStatus.COMPLETED
    assert intel_comp.available_agents == 1
    assert enemy_ship.has_infiltrating_agent_from(p1)

    # Now VisibilityService should grant detailed visibility of enemy ship and include its sensors in P1's view
    snap_after = VisibilityService.compute(galaxy, p1)
    assert enemy_ship.id in snap_after.visible_enemy_unit_ids
    assert ("Sol", (0, 0)) in snap_after.presence_hexes or len(snap_after.visible_enemy_unit_ids) > 0


def test_unit_infiltration_approaches_then_executes_action(test_setup):
    p1, p2, galaxy, system, game = test_setup

    spy_unit = Unit(p1, Position(0, 0), (0, 0), "Sol", "Spy Ship", HullSize.MEDIUM, game)
    intel_comp = IntelligenceComponent(spy_unit, agents_count=1, agents_capacity=1)
    spy_unit.add_component(intel_comp)
    system.hexes[(0, 0)].add_unit(spy_unit)

    enemy_ship = Unit(p2, Position(600, 0), (0, 0), "Sol", "Enemy Ship", HullSize.MEDIUM, game)
    system.hexes[(0, 0)].add_unit(enemy_ship)

    order = InfiltrateUnitOrder(spy_unit, {"target_unit_id": enemy_ship.id})
    order.execute(galaxy)

    assert len(order.sub_orders) == 2
    approach = order.sub_orders[0]
    assert approach.order_type == OrderType.MOVE
    assert approach.parameters["target_unit_id"] == enemy_ship.id
    assert approach.parameters["standoff_distance"] == 450.0
    assert order.sub_orders[1].order_type == OrderType.INFILTRATE_UNIT

    # Simulate completion of the movement leg at its same-sector standoff point.
    spy_unit.position = Position(150, 0)
    approach.status = OrderStatus.COMPLETED
    order.update(galaxy)

    assert order.status == OrderStatus.COMPLETED
    assert enemy_ship.has_infiltrating_agent_from(p1)


def test_unit_system_sabotages(test_setup):
    p1, p2, galaxy, system, game = test_setup

    spy_unit = Unit(p1, Position(100, 100), (0, 0), "Sol", "Spy Ship", HullSize.MEDIUM, game)
    intel_comp = IntelligenceComponent(spy_unit, agents_count=3, agents_capacity=3)
    spy_unit.add_component(intel_comp)
    system.hexes[(0, 0)].add_unit(spy_unit)

    target_unit = Unit(p2, Position(120, 100), (0, 0), "Sol", "Enemy Target", HullSize.MEDIUM, game)
    target_engines = Engines(target_unit, speed=100.0)
    target_unit.add_component(target_engines)
    target_weapons = Weapons(target_unit)
    turret = Turret(TurretType.MASS_DRIVER, damage=40.0, range=300.0, cooldown=1, parent_unit=target_unit)
    target_weapons.add_turret(turret)
    target_unit.add_component(target_weapons)
    target_defenses = Defenses(target_unit, armor=20, shields=20, point_defense=0)
    target_unit.add_component(target_defenses)
    target_hd = Hyperdrive(target_unit, HyperdriveType.BASIC)
    target_unit.add_component(target_hd)
    target_unit.antimatter_component.current_amount = 100.0
    system.hexes[(0, 0)].add_unit(target_unit)

    # Infiltrate
    agent = intel_comp.deploy_agent(target_unit)
    assert agent is not None
    assert agent in target_unit.infiltrating_agents

    # 1. Sabotage Engines -> 50% speed
    assert target_engines.effective_speed == 100.0
    sab_engines = SabotageOrder(spy_unit, {"agent_id": agent.id, "sabotage_type": SabotageType.ENGINES})
    sab_engines.execute(galaxy)
    assert target_unit.is_sabotaged(SabotageType.ENGINES)
    assert target_engines.effective_speed == 50.0

    # 2. Sabotage Weapons -> 50% damage
    sab_weap = SabotageOrder(spy_unit, {"agent_id": agent.id, "sabotage_type": SabotageType.WEAPONS})
    sab_weap.execute(galaxy)
    assert target_unit.is_sabotaged(SabotageType.WEAPONS)
    dummy_target = Unit(p1, Position(120, 150), (0, 0), "Sol", "Victim", HullSize.MEDIUM, game)
    dummy_target.remove_component(Defenses)
    turret.target = dummy_target
    turret.fire()
    # 40 damage * 0.5 = 20 damage dealt
    assert dummy_target.current_hit_points == dummy_target.max_hit_points - 20

    # 3. Sabotage Defenses -> Halved mitigation
    target_defenses.calculate_mitigation = MagicMock(return_value=20)
    sab_def = SabotageOrder(spy_unit, {"agent_id": agent.id, "sabotage_type": SabotageType.DEFENSES})
    sab_def.execute(galaxy)
    assert target_unit.is_sabotaged(SabotageType.DEFENSES)
    hp_before = target_unit.current_hit_points
    target_unit.take_damage(20, TurretType.MASS_DRIVER)
    dmg_taken = hp_before - target_unit.current_hit_points
    assert dmg_taken == 10 # 20 damage - (20 mitigation * 0.5 = 10) = 10 damage taken

    # 4. Sabotage Antimatter -> Drains 50%
    target_unit.antimatter_component.current_amount = 80.0
    sab_am = SabotageOrder(spy_unit, {"agent_id": agent.id, "sabotage_type": SabotageType.ANTIMATTER})
    sab_am.execute(galaxy)
    assert target_unit.antimatter_component.current_amount == 40.0

    # 5. Sabotage Hyperdrive -> Adds recharge turns
    target_hd.jump_status = target_hd.jump_status.READY
    sab_hd = SabotageOrder(spy_unit, {"agent_id": agent.id, "sabotage_type": SabotageType.HYPERDRIVE})
    sab_hd.execute(galaxy)
    assert target_hd.recharge_time_remaining >= 3


def test_colony_infiltration_and_sabotages(test_setup):
    p1, p2, galaxy, system, game = test_setup

    planet = Planet((0, 0), "Sol", "TERRAN")
    planet.owner = p2
    planet.population = 80.0
    planet.max_population = 100.0
    system.hexes[(0, 0)].add_celestial_body(planet)

    spy_unit = Unit(p1, Position(100, 100), (0, 0), "Sol", "Spy Ship", HullSize.MEDIUM, game)
    intel_comp = IntelligenceComponent(spy_unit, agents_count=2, agents_capacity=2)
    spy_unit.add_component(intel_comp)
    system.hexes[(0, 0)].add_unit(spy_unit)

    # Infiltrate planet
    infiltrate_order = InfiltratePlanetOrder(spy_unit, {"target_body_id": planet.id})
    infiltrate_order.execute(galaxy)
    assert infiltrate_order.status == OrderStatus.COMPLETED
    assert planet.has_infiltrating_agent_from(p1)
    agent = planet.infiltrating_agents[0]

    # Baseline Economy: 80 pop * TAX_RATE (0.1) = 8.0 credits
    p2.credits = 0.0
    p1.credits = 0.0
    assert calculate_player_income(galaxy, p2) == 8.0
    assert calculate_player_income(galaxy, p1) == 0.0

    # Sabotage Economy: P2 income halved to 4.0, P1 siphons 25% (2.0 credits)
    sab_order = SabotageOrder(spy_unit, {"agent_id": agent.id, "sabotage_type": SabotageType.ECONOMY})
    sab_order.execute(galaxy)
    assert planet.is_sabotaged(SabotageType.ECONOMY)

    assert calculate_player_income(galaxy, p2) == 4.0
    assert calculate_player_income(galaxy, p1) == 2.0

    # Sabotage Growth: Halts population growth
    planet.population = 50.0
    sab_growth = SabotageOrder(spy_unit, {"agent_id": agent.id, "sabotage_type": SabotageType.GROWTH})
    sab_growth.execute(galaxy)
    assert planet.is_sabotaged(SabotageType.GROWTH)
    planet.update_population()
    assert planet.population == 50.0 # No growth occurred


def test_agent_relocation_and_extraction(test_setup):
    p1, p2, galaxy, system, game = test_setup

    spy_unit = Unit(p1, Position(100, 100), (0, 0), "Sol", "Spy Ship", HullSize.MEDIUM, game)
    intel_comp = IntelligenceComponent(spy_unit, agents_count=1, agents_capacity=1)
    spy_unit.add_component(intel_comp)
    system.hexes[(0, 0)].add_unit(spy_unit)

    ship_a = Unit(p2, Position(150, 100), (0, 0), "Sol", "Enemy Frigate A", HullSize.SMALL, game)
    ship_b = Unit(p2, Position(250, 100), (0, 0), "Sol", "Enemy Frigate B", HullSize.SMALL, game)
    system.hexes[(0, 0)].add_unit(ship_a)
    system.hexes[(0, 0)].add_unit(ship_b)

    # Infiltrate Ship A
    agent = intel_comp.deploy_agent(ship_a)
    assert agent in ship_a.infiltrating_agents
    assert intel_comp.available_agents == 0

    # Relocate to Ship B
    reloc_order = RelocateAgentOrder(spy_unit, {
        "agent_id": agent.id,
        "target_type": "unit",
        "destination_id": ship_b.id
    })
    reloc_order.execute(galaxy)
    assert reloc_order.status == OrderStatus.COMPLETED
    assert agent not in ship_a.infiltrating_agents
    assert agent in ship_b.infiltrating_agents
    assert agent.attached_to == ship_b

    # Extract back to Spy unit
    extract_order = ExtractAgentOrder(spy_unit, {"agent_id": agent.id})
    extract_order.execute(galaxy)
    assert extract_order.status == OrderStatus.COMPLETED
    assert agent not in ship_b.infiltrating_agents
    assert intel_comp.available_agents == 1


def test_counter_intelligence_sweep_and_eliminate(test_setup):
    p1, p2, galaxy, system, game = test_setup

    # Friendly vessel with CI suite
    p1.credits = 1000.0
    ci_ship = Unit(p1, Position(100, 100), (0, 0), "Sol", "Security Ship", HullSize.MEDIUM, game)
    ci_comp = IntelligenceComponent(ci_ship, agents_count=1, agents_capacity=1, has_counter_intelligence=True)
    ci_ship.add_component(ci_comp)
    system.hexes[(0, 0)].add_unit(ci_ship)

    # Friendly colony near CI vessel
    planet = Planet((0, 0), "Sol", "TERRAN")
    planet.owner = p1
    system.hexes[(0, 0)].add_celestial_body(planet)

    # Enemy spy ship placing agents on friendly ship and colony
    enemy_spy = Unit(p2, Position(120, 100), (0, 0), "Sol", "Enemy Spy", HullSize.MEDIUM, game)
    enemy_intel = IntelligenceComponent(enemy_spy, agents_count=2, agents_capacity=2)
    enemy_spy.add_component(enemy_intel)
    system.hexes[(0, 0)].add_unit(enemy_spy)

    agent_on_ship = enemy_intel.deploy_agent(ci_ship)
    agent_on_planet = enemy_intel.deploy_agent(planet)
    assert not agent_on_ship.is_discovered
    assert not agent_on_planet.is_discovered
    assert ci_comp.is_ci_ready is True
    assert ci_comp.ci_cooldown_remaining == 0

    init_credits = p1.credits
    init_am = ci_ship.antimatter_component.current_amount

    # Execute active CI Sweep
    sweep_order = CISweepOrder(ci_ship)
    sweep_order.execute(galaxy)
    assert sweep_order.status == OrderStatus.COMPLETED
    assert agent_on_ship.is_discovered
    assert agent_on_planet.is_discovered

    # Verify resource deductions and cooldown
    assert p1.credits == init_credits - CI_SWEEP_CREDIT_COST
    assert ci_ship.antimatter_component.current_amount == init_am - CI_SWEEP_ANTIMATTER_COST
    assert ci_comp.ci_cooldown_remaining == CI_SWEEP_COOLDOWN_TURNS
    assert ci_comp.is_ci_ready is False

    # Eliminate agent on planet
    elim_order = EliminateAgentOrder(ci_ship, {"agent_id": agent_on_planet.id})
    elim_order.execute(galaxy)
    assert elim_order.status == OrderStatus.COMPLETED
    assert agent_on_planet not in planet.infiltrating_agents
    assert enemy_intel.deployed_agents == [agent_on_ship]


def test_ci_sweep_cooldown_and_costs_validation(test_setup):
    p1, p2, galaxy, system, game = test_setup
    ci_ship = Unit(p1, Position(100, 100), (0, 0), "Sol", "Security Ship", HullSize.MEDIUM, game)
    ci_comp = IntelligenceComponent(ci_ship, agents_count=1, agents_capacity=1, has_counter_intelligence=True)
    ci_ship.add_component(ci_comp)
    system.hexes[(0, 0)].add_unit(ci_ship)

    # 1. Test failure on cooldown
    ci_comp.ci_cooldown_remaining = 2
    order_cd = CISweepOrder(ci_ship)
    order_cd.execute(galaxy)
    assert order_cd.status == OrderStatus.FAILED
    assert ci_comp.ci_cooldown_remaining == 2

    # 2. Test failure with insufficient credits
    ci_comp.ci_cooldown_remaining = 0
    p1.credits = 50.0  # Needs 100.0
    order_cred = CISweepOrder(ci_ship)
    order_cred.execute(galaxy)
    assert order_cred.status == OrderStatus.FAILED
    assert p1.credits == 50.0
    assert ci_comp.ci_cooldown_remaining == 0

    # 3. Test failure with insufficient antimatter
    p1.credits = 500.0
    ci_ship.antimatter_component.current_amount = 10.0  # Needs 25.0
    order_am = CISweepOrder(ci_ship)
    order_am.execute(galaxy)
    assert order_am.status == OrderStatus.FAILED
    assert ci_ship.antimatter_component.current_amount == 10.0
    assert ci_comp.ci_cooldown_remaining == 0


def test_ci_cooldown_turn_decrement(test_setup):
    p1, p2, galaxy, system, game = test_setup
    ci_ship = Unit(p1, Position(100, 100), (0, 0), "Sol", "Security Ship", HullSize.MEDIUM, game)
    ci_comp = IntelligenceComponent(ci_ship, agents_count=1, agents_capacity=1, has_counter_intelligence=True, ci_cooldown_remaining=3)
    ci_ship.add_component(ci_comp)
    system.hexes[(0, 0)].add_unit(ci_ship)

    assert ci_comp.ci_cooldown_remaining == 3
    ci_ship.update()
    assert ci_comp.ci_cooldown_remaining == 2
    ci_ship.update()
    assert ci_comp.ci_cooldown_remaining == 1
    ci_ship.update()
    assert ci_comp.ci_cooldown_remaining == 0
    assert ci_comp.is_ci_ready is True
    # Clamped at 0
    ci_ship.update()
    assert ci_comp.ci_cooldown_remaining == 0


def test_no_passive_ci_detection_on_turn_end(test_setup):
    p1, p2, galaxy, system, game = test_setup
    from turn_processor import TurnProcessor
    turn_proc = TurnProcessor(game)

    ci_ship = Unit(p1, Position(100, 100), (0, 0), "Sol", "Security Ship", HullSize.MEDIUM, game)
    ci_comp = IntelligenceComponent(ci_ship, agents_count=1, agents_capacity=1, has_counter_intelligence=True)
    ci_ship.add_component(ci_comp)
    system.hexes[(0, 0)].add_unit(ci_ship)

    enemy_spy = Unit(p2, Position(120, 100), (0, 0), "Sol", "Enemy Spy", HullSize.MEDIUM, game)
    enemy_intel = IntelligenceComponent(enemy_spy, agents_count=1, agents_capacity=1)
    enemy_spy.add_component(enemy_intel)
    system.hexes[(0, 0)].add_unit(enemy_spy)

    agent = enemy_intel.deploy_agent(ci_ship)
    assert agent.is_discovered is False

    # Process 20 turns of unit updates for p1
    for _ in range(20):
        turn_proc._process_unit_updates(p1)
        assert agent.is_discovered is False, "Agent should never be discovered passively without active CI sweep!"


def test_save_and_load_intelligence_state(test_setup):
    p1, p2, galaxy, system, game = test_setup

    spy_unit = Unit(p1, Position(100, 100), (0, 0), "Sol", "Spy 1", HullSize.MEDIUM, game)
    intel_comp = IntelligenceComponent(spy_unit, agents_count=2, agents_capacity=2, has_counter_intelligence=True, ci_cooldown_remaining=2)
    spy_unit.add_component(intel_comp)
    system.hexes[(0, 0)].add_unit(spy_unit)

    target_unit = Unit(p2, Position(150, 100), (0, 0), "Sol", "Enemy Unit", HullSize.MEDIUM, game)
    system.hexes[(0, 0)].add_unit(target_unit)

    # Infiltrate and apply sabotage
    agent = intel_comp.deploy_agent(target_unit)
    target_unit.apply_sabotage(agent, SabotageType.ENGINES)
    agent.is_discovered = True

    # Serialize
    save_data = serialize_game_state(game)
    assert save_data is not None

    # Recreate blank game and deserialize
    new_game = MagicMock()
    success = deserialize_game_state(new_game, save_data)
    assert success is True

    loaded_galaxy = new_game.galaxy
    loaded_sys = loaded_galaxy.systems["Sol"]
    loaded_spy = next(u for u in loaded_sys.hexes[(0, 0)].units if u.name == "Spy 1")
    loaded_target = next(u for u in loaded_sys.hexes[(0, 0)].units if u.name == "Enemy Unit")

    assert loaded_spy.intelligence_component is not None
    assert loaded_spy.intelligence_component.has_counter_intelligence is True
    assert loaded_spy.intelligence_component.ci_cooldown_remaining == 2
    assert loaded_target.has_infiltrating_agent_from(new_game.players[0])
    assert loaded_target.is_sabotaged(SabotageType.ENGINES)
    loaded_agent = loaded_target.infiltrating_agents[0]
    assert loaded_agent.is_discovered is True
    assert loaded_agent.active_sabotage == SabotageType.ENGINES


def test_intelligence_context_menu_options(test_setup):
    from input_processor.context_menu_builder import build_sector_context_menu_options
    p1, p2, galaxy, system, game = test_setup

    spy_unit = Unit(p1, Position(100, 100), (0, 0), "Sol", "Spy Ship", HullSize.MEDIUM, game)
    intel_comp = IntelligenceComponent(spy_unit, agents_count=2, agents_capacity=2, has_counter_intelligence=True)
    spy_unit.add_component(intel_comp)
    system.hexes[(0, 0)].add_unit(spy_unit)

    target_unit = Unit(p2, Position(120, 100), (0, 0), "Sol", "Enemy Ship", HullSize.MEDIUM, game)
    system.hexes[(0, 0)].add_unit(target_unit)

    # Setup game state
    game.players = [p1, p2]
    game.current_player_index = 0
    game.selected_objects = [spy_unit]
    game.current_system_name = "Sol"
    game.current_sector_coord = (0, 0)
    game.galaxy = galaxy

    # Right click enemy target before infiltration -> Infiltrate Unit option present
    options, target = build_sector_context_menu_options(game, target_unit, (0, 0))
    action_ids = [opt[1] for opt in options if isinstance(opt[1], str)]
    assert "infiltrate_unit" in action_ids

    # Infiltrate enemy ship
    agent = intel_comp.deploy_agent(target_unit)
    assert agent is not None

    # Right click enemy target after infiltration -> Sabotage Systems & Extract Agent present
    options, target = build_sector_context_menu_options(game, target_unit, (0, 0))
    menu_labels = [opt[0] for opt in options]
    assert "Sabotage Systems" in menu_labels
    assert "Extract Agent" in menu_labels


def test_infiltrated_unit_visibility_and_sidebar(test_setup):
    from gui.sidebar.panels_unit import build_unit_panel
    from order_system import OrderSystem
    from events import InfiltrateUnitEvent
    p1, p2, galaxy, system, game = test_setup

    spy_unit = Unit(p1, Position(100, 100), (0, 0), "Sol", "Spy Ship", HullSize.MEDIUM, game)
    intel_comp = IntelligenceComponent(spy_unit, agents_count=1, agents_capacity=1)
    spy_unit.add_component(intel_comp)
    system.hexes[(0, 0)].add_unit(spy_unit)

    target_unit = Unit(p2, Position(150, 100), (0, 0), "Sol", "Enemy Ship", HullSize.MEDIUM, game)
    system.hexes[(0, 0)].add_unit(target_unit)

    game.players = [p1, p2]
    game.current_player_index = 0
    game.selected_objects = [spy_unit]
    game.galaxy = galaxy

    order_sys = OrderSystem(game, game.event_bus)
    event = InfiltrateUnitEvent(units=[spy_unit], target_unit=target_unit, shift_pressed=False)
    order_sys.handle_infiltrate_unit(event)

    # Infiltrate executes immediately since units are within 500 units in the same sector
    assert target_unit.has_infiltrating_agent_from(p1) is True
    assert intel_comp.available_agents == 0

    # Sidebar verification
    panel_data = build_unit_panel(game, target_unit)
    labels = [item['text'] for item in panel_data if item.get('type') == 'label']
    assert any("COVERT AGENT EMBEDDED" in lbl for lbl in labels)


def test_eliminate_agent_zero_id(test_setup):
    from unit_orders.intelligence import EliminateAgentOrder, ExtractAgentOrder, SabotageOrder, RelocateAgentOrder
    p1, p2, galaxy, system, game = test_setup

    ci_ship = Unit(p1, Position(100, 100), (0, 0), "Sol", "CI Ship", HullSize.MEDIUM, game)
    ci_comp = IntelligenceComponent(ci_ship, agents_count=1, agents_capacity=1, has_counter_intelligence=True)
    ci_ship.add_component(ci_comp)
    system.hexes[(0, 0)].add_unit(ci_ship)

    friendly_ship = Unit(p1, Position(120, 100), (0, 0), "Sol", "Target Ship", HullSize.MEDIUM, game)
    system.hexes[(0, 0)].add_unit(friendly_ship)

    # Attach enemy agent with id = 0 explicitly
    agent0 = Agent(owner=p2, source_unit_id=0, target_type="UNIT", target_id=friendly_ship.id, agent_id=0)
    friendly_ship.infiltrating_agents.append(agent0)

    # Test EliminateAgentOrder with agent_id = 0
    elim_order = EliminateAgentOrder(ci_ship, {"agent_id": 0})
    elim_order.execute(galaxy)

    assert elim_order.status == OrderStatus.COMPLETED
    assert not friendly_ship.has_infiltrating_agent_from(p2)


def test_enemy_unit_intelligence_hidden_in_sidebar_basic_info(test_setup):
    from gui.sidebar.panels_unit import build_unit_panel
    p1, p2, galaxy, system, game = test_setup

    enemy_ship = Unit(p2, Position(200, 200), (0, 0), "Sol", "Enemy Spy Ship", HullSize.MEDIUM, game)
    enemy_ship.add_component(Engines(enemy_ship, speed=100.0))
    weapons = Weapons(enemy_ship)
    weapons.turrets.append(Turret(TurretType.MASS_DRIVER, 10, 300, 2, enemy_ship))
    enemy_ship.add_component(weapons)
    enemy_ship.add_component(Hyperdrive(enemy_ship, HyperdriveType.BASIC))
    enemy_intel = IntelligenceComponent(enemy_ship, agents_count=2, agents_capacity=2, has_counter_intelligence=True)
    enemy_ship.add_component(enemy_intel)
    system.hexes[(0, 0)].add_unit(enemy_ship)

    game.players = [p1, p2]
    game.current_player_index = 0  # Player 1 is active (enemy of p2)
    game.selected_objects = [enemy_ship]
    game.selected_unit_tab = 'basic_info'

    panel_data = build_unit_panel(game, enemy_ship)
    labels = [item['text'] for item in panel_data if item.get('type') == 'label']

    # Standard components are visible in Component Overview
    assert any("Speed:" in lbl for lbl in labels)
    assert any("Turrets" in lbl for lbl in labels)
    assert any("FTL Jump:" in lbl for lbl in labels)

    # IntelligenceComponent must be completely hidden from enemy inspection
    assert not any("Intelligence:" in lbl for lbl in labels)
    assert not any("Agents" in lbl for lbl in labels)
    assert not any("CI Active" in lbl for lbl in labels)


def test_enemy_unit_intelligence_hidden_in_sidebar_components_tab(test_setup):
    from gui.sidebar.panels_unit import build_unit_panel
    p1, p2, galaxy, system, game = test_setup

    enemy_ship = Unit(p2, Position(200, 200), (0, 0), "Sol", "Enemy Spy Ship", HullSize.MEDIUM, game)
    enemy_ship.add_component(Engines(enemy_ship, speed=100.0))
    weapons = Weapons(enemy_ship)
    weapons.turrets.append(Turret(TurretType.MASS_DRIVER, 10, 300, 2, enemy_ship))
    enemy_ship.add_component(weapons)
    enemy_intel = IntelligenceComponent(enemy_ship, agents_count=2, agents_capacity=2, has_counter_intelligence=True)
    enemy_ship.add_component(enemy_intel)
    system.hexes[(0, 0)].add_unit(enemy_ship)

    game.players = [p1, p2]
    game.current_player_index = 0  # Player 1 is active
    game.selected_objects = [enemy_ship]
    game.selected_unit_tab = 'components'
    game.selected_component_name = 'Intelligence'  # Attempt to inspect Intelligence component

    panel_data = build_unit_panel(game, enemy_ship)

    dropdowns = [item for item in panel_data if item.get('type') == 'drop_down_menu']
    assert len(dropdowns) == 1
    options_list = dropdowns[0]['options_list']

    # Intelligence should NOT be an available option in the dropdown
    assert "Intelligence" not in options_list
    assert "Commander" in options_list
    assert "Engines" in options_list
    assert "Weapons" in options_list

    # Selection automatically fell back from 'Intelligence'
    assert game.selected_component_name != "Intelligence"

    # Component details should not display intelligence data
    labels = [item['text'] for item in panel_data if item.get('type') == 'label']
    assert not any("Agents:" in lbl for lbl in labels)
    assert not any("Infiltration Range:" in lbl for lbl in labels)
    assert not any("Counter-Intelligence:" in lbl for lbl in labels)


def test_friendly_unit_intelligence_visible_in_sidebar(test_setup):
    from gui.sidebar.panels_unit import build_unit_panel
    p1, p2, galaxy, system, game = test_setup

    friendly_ship = Unit(p1, Position(100, 100), (0, 0), "Sol", "Friendly Spy Ship", HullSize.MEDIUM, game)
    friendly_intel = IntelligenceComponent(friendly_ship, agents_count=2, agents_capacity=2, has_counter_intelligence=True)
    friendly_ship.add_component(friendly_intel)
    system.hexes[(0, 0)].add_unit(friendly_ship)

    game.players = [p1, p2]
    game.current_player_index = 0  # Player 1 is active (owner of friendly_ship)
    game.selected_objects = [friendly_ship]

    # 1. Basic Info Tab
    game.selected_unit_tab = 'basic_info'
    panel_data = build_unit_panel(game, friendly_ship)
    labels = [item['text'] for item in panel_data if item.get('type') == 'label']
    assert any("• Intelligence: 2/2 Agents | CI: Ready" in lbl for lbl in labels)

    # 2. Components Tab
    game.selected_unit_tab = 'components'
    game.selected_component_name = 'Intelligence'
    panel_data = build_unit_panel(game, friendly_ship)
    dropdowns = [item for item in panel_data if item.get('type') == 'drop_down_menu']
    assert "Intelligence" in dropdowns[0]['options_list']

    labels = [item['text'] for item in panel_data if item.get('type') == 'label']
    assert any("Agents: 2 / 2 Ready" in lbl for lbl in labels)
    assert any("Counter-Intelligence: Ready" in lbl for lbl in labels)
    assert any("Sweep Cost: 100c, 25am" in lbl for lbl in labels)


def test_enemy_unit_intelligence_hidden_from_attack_context_menu(test_setup):
    from input_processor.context_menu_builder import build_sector_context_menu_options
    from unit_components import HyperspaceInhibitionFieldEmitter
    p1, p2, galaxy, system, game = test_setup

    # Player 1 warship with weapons
    attacker = Unit(p1, Position(100, 100), (0, 0), "Sol", "Battleship", HullSize.LARGE, game)
    w_attacker = Weapons(attacker)
    w_attacker.turrets.append(Turret(TurretType.MASS_DRIVER, 20, 400, 2, attacker))
    attacker.add_component(w_attacker)
    system.hexes[(0, 0)].add_unit(attacker)

    # Player 2 enemy ship with Engines, Hyperdrive, Weapons, Inhibitor, and Intelligence
    enemy_ship = Unit(p2, Position(150, 100), (0, 0), "Sol", "Enemy Carrier", HullSize.LARGE, game)
    enemy_ship.add_component(Engines(enemy_ship, speed=80.0))
    enemy_ship.add_component(Hyperdrive(enemy_ship, HyperdriveType.BASIC))
    w_enemy = Weapons(enemy_ship)
    w_enemy.turrets.append(Turret(TurretType.BEAM, 15, 350, 2, enemy_ship))
    enemy_ship.add_component(w_enemy)
    enemy_ship.add_component(HyperspaceInhibitionFieldEmitter(enemy_ship, radius=1000.0))
    enemy_ship.add_component(IntelligenceComponent(enemy_ship, agents_count=2, agents_capacity=2))
    system.hexes[(0, 0)].add_unit(enemy_ship)

    game.players = [p1, p2]
    game.current_player_index = 0
    game.selected_objects = [attacker]
    game.current_system_name = "Sol"
    game.current_sector_coord = (0, 0)
    game.galaxy = galaxy

    options, target = build_sector_context_menu_options(game, enemy_ship, (150, 100))
    menu_labels = [opt[0] for opt in options]
    action_ids = [opt[1] for opt in options if isinstance(opt[1], str)]

    # Verifying standard attack options are available
    assert "Attack Hull" in menu_labels
    assert "Attack Engines" in menu_labels
    assert "Attack Hyperdrive" in menu_labels
    assert "Attack Weapons" in menu_labels
    assert "Attack Inhibitor" in menu_labels

    # Verifying Intelligence component is NOT exposed in the attack context menu
    assert not any("Attack Intelligence" in lbl for lbl in menu_labels)
    assert not any("intelligence" in act_id.lower() and "attack" in act_id.lower() for act_id in action_ids)


def test_ci_sweep_sidebar_button_data(test_setup):
    p1, p2, galaxy, system, game = test_setup
    ci_ship = Unit(p1, Position(100, 100), (0, 0), "Sol", "Security Ship", HullSize.MEDIUM, game)
    ci_comp = IntelligenceComponent(ci_ship, agents_count=1, agents_capacity=2, has_counter_intelligence=True)
    ci_ship.add_component(ci_comp)
    system.hexes[(0, 0)].add_unit(ci_ship)

    game.players = [p1, p2]
    game.current_player_index = 0

    # 1. Ready state: Button is present and enabled
    sidebar_data = ci_comp.get_sidebar_data(game)
    btn = next((item for item in sidebar_data if item.get('type') == 'button' and item.get('action_id') == 'ci_sweep'), None)
    assert btn is not None
    assert btn['target_data'] == ci_ship.id
    assert btn['enabled'] is True
    assert "CI Sweep" in btn['text']

    # 2. Cooldown state: Button is present but disabled
    ci_comp.ci_cooldown_remaining = 3
    sidebar_data_cd = ci_comp.get_sidebar_data(game)
    btn_cd = next((item for item in sidebar_data_cd if item.get('type') == 'button' and item.get('action_id') == 'ci_sweep'), None)
    assert btn_cd is not None
    assert btn_cd['enabled'] is False
    assert "[3t]" in btn_cd['text']

    # 3. Destroyed component: Button is not present
    ci_comp.ci_cooldown_remaining = 0
    ci_comp.current_hit_points = 0
    assert ci_comp.is_destroyed is True
    sidebar_data_destroyed = ci_comp.get_sidebar_data(game)
    btn_dest = next((item for item in sidebar_data_destroyed if item.get('type') == 'button' and item.get('action_id') == 'ci_sweep'), None)
    assert btn_dest is None

    # 4. Inspected by enemy player: Sidebar data is empty
    ci_comp.current_hit_points = ci_comp.max_hit_points
    game.current_player_index = 1  # Enemy player (p2)
    assert ci_comp.get_sidebar_data(game) == []


def test_ci_sweep_removed_from_context_menus(test_setup):
    from input_processor.context_menu_builder import build_sector_context_menu_options
    from constants import PlanetType
    p1, p2, galaxy, system, game = test_setup

    ci_ship = Unit(p1, Position(100, 100), (0, 0), "Sol", "Security Ship", HullSize.MEDIUM, game)
    ci_comp = IntelligenceComponent(ci_ship, agents_count=1, agents_capacity=2, has_counter_intelligence=True)
    ci_ship.add_component(ci_comp)
    system.hexes[(0, 0)].add_unit(ci_ship)

    friendly_ship = Unit(p1, Position(120, 100), (0, 0), "Sol", "Friendly Frigate", HullSize.SMALL, game)
    system.hexes[(0, 0)].add_unit(friendly_ship)

    planet = Planet((0, 0), "Sol", PlanetType.TERRAN)
    planet.owner = p1
    planet.population = 50.0
    planet.position = Position(200, 200)
    system.hexes[(0, 0)].add_celestial_body(planet)

    # Attach discovered enemy agent to friendly ship
    enemy_spy = Unit(p2, Position(500, 500), (0, 0), "Sol", "Enemy Spy", HullSize.SMALL, game)
    enemy_intel = IntelligenceComponent(enemy_spy, agents_count=1, agents_capacity=1)
    enemy_spy.add_component(enemy_intel)
    agent = enemy_intel.deploy_agent(friendly_ship)
    agent.is_discovered = True

    game.players = [p1, p2]
    game.current_player_index = 0
    game.selected_objects = [ci_ship]
    game.current_system_name = "Sol"
    game.current_sector_coord = (0, 0)
    game.galaxy = galaxy

    # 1. Empty space context menu -> no "ci_sweep"
    options_space, _ = build_sector_context_menu_options(game, None, (300, 300))
    action_ids_space = [opt[1] for opt in options_space if isinstance(opt[1], str)]
    assert "ci_sweep" not in action_ids_space

    # 2. Friendly ship context menu -> no "ci_sweep", but "eliminate_agent_" is present for discovered spy
    options_ship, _ = build_sector_context_menu_options(game, friendly_ship, (120, 100))
    action_ids_ship = [opt[1] for opt in options_ship if isinstance(opt[1], str)]
    assert "ci_sweep" not in action_ids_ship
    assert any(act.startswith("eliminate_agent_") for act in action_ids_ship)

    # 3. Friendly planet context menu -> no "ci_sweep"
    options_planet, _ = build_sector_context_menu_options(game, planet, (200, 200))
    action_ids_planet = [opt[1] for opt in options_planet if isinstance(opt[1], str)]
    assert "ci_sweep" not in action_ids_planet


def test_ci_sweep_gui_action_handling(test_setup):
    from events import EventBus
    from order_system import OrderSystem
    from game_actions import handle_gui_action
    p1, p2, galaxy, system, game = test_setup

    game.event_bus = EventBus()
    order_sys = OrderSystem(game, game.event_bus)

    ci_ship = Unit(p1, Position(100, 100), (0, 0), "Sol", "Security Ship", HullSize.MEDIUM, game)
    ci_comp = IntelligenceComponent(ci_ship, agents_count=1, agents_capacity=2, has_counter_intelligence=True)
    ci_ship.add_component(ci_comp)
    system.hexes[(0, 0)].add_unit(ci_ship)

    friendly_ship = Unit(p1, Position(150, 100), (0, 0), "Sol", "Friendly Ship", HullSize.SMALL, game)
    system.hexes[(0, 0)].add_unit(friendly_ship)

    enemy_spy = Unit(p2, Position(500, 500), (0, 0), "Sol", "Enemy Spy", HullSize.SMALL, game)
    enemy_intel = IntelligenceComponent(enemy_spy, agents_count=1, agents_capacity=1)
    enemy_spy.add_component(enemy_intel)
    agent = enemy_intel.deploy_agent(friendly_ship)
    assert agent.is_discovered is False

    game.players = [p1, p2]
    game.current_player_index = 0
    game.selected_objects = [ci_ship]
    game.galaxy = galaxy

    init_credits = p1.credits
    init_am = ci_ship.antimatter_component.current_amount

    # Execute GUI action for CI Sweep
    action_payload = {'action': 'ci_sweep', 'unit_id': ci_ship.id}
    handle_gui_action(game, action_payload)

    # Verify agent was discovered
    assert agent.is_discovered is True
    # Verify costs and cooldown applied
    assert p1.credits == init_credits - CI_SWEEP_CREDIT_COST
    assert ci_ship.antimatter_component.current_amount == init_am - CI_SWEEP_ANTIMATTER_COST
    assert ci_comp.ci_cooldown_remaining == CI_SWEEP_COOLDOWN_TURNS
    assert ci_comp.is_ci_ready is False
