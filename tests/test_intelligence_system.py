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

    # Execute active CI Sweep
    sweep_order = CISweepOrder(ci_ship)
    sweep_order.execute(galaxy)
    assert sweep_order.status == OrderStatus.COMPLETED
    assert agent_on_ship.is_discovered
    assert agent_on_planet.is_discovered

    # Eliminate agent on planet
    elim_order = EliminateAgentOrder(ci_ship, {"agent_id": agent_on_planet.id})
    elim_order.execute(galaxy)
    assert elim_order.status == OrderStatus.COMPLETED
    assert agent_on_planet not in planet.infiltrating_agents
    assert enemy_intel.deployed_agents == [agent_on_ship]


def test_save_and_load_intelligence_state(test_setup):
    p1, p2, galaxy, system, game = test_setup

    spy_unit = Unit(p1, Position(100, 100), (0, 0), "Sol", "Spy 1", HullSize.MEDIUM, game)
    intel_comp = IntelligenceComponent(spy_unit, agents_count=2, agents_capacity=2, has_counter_intelligence=True)
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
