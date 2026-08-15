import pytest
from geometry import Position
from utils import HexCoord
from constants import HullSize, HULL_CAPACITIES
from entities import Unit, Player
from galaxy import Galaxy, StarSystem
from game import Game
from unit_components import (
    Constructor, Defenses, Weapons, Engines, RepairComponent, MiningComponent,
    HangarComponent, Commander, AntimatterStorage
)
from unit_orders import RefitOrder, OrderStatus, OrderType
from events import RefitUnitEvent, EventBus
from order_system import OrderSystem
from save_manager import serialize_unit, deserialize_unit, serialize_order, deserialize_order


class MockGame:
    def __init__(self, galaxy, players):
        self.galaxy = galaxy
        self.players = players
        self.current_player_index = 0
        self.event_bus = EventBus()
        self.sidebar_needs_update = False
        self.gui = None


@pytest.fixture
def setup_universe():
    player = Player(name="Player 1", color=(0, 0, 255), is_human=True)
    player.credits = 5000
    player.metal = 1000
    player.crystal = 1000

    enemy_player = Player(name="Player 2", color=(255, 0, 0), is_human=False)
    enemy_player.credits = 5000
    enemy_player.metal = 1000
    enemy_player.crystal = 1000

    galaxy = Galaxy()
    system = StarSystem(name="Sol", position=Position(0, 0))
    galaxy.systems["Sol"] = system

    game = MockGame(galaxy, [player, enemy_player])
    galaxy.game = game

    # Constructor unit
    constructor_unit = Unit(
        owner=player,
        position=Position(100, 100),
        in_hex=HexCoord(0, 0),
        in_system="Sol",
        name="Constructor-1",
        hull_size=HullSize.LARGE,
        game=game,
        template_name="Construction Ship"
    )
    constructor_unit.add_component(Constructor(constructor_unit, hull_cost=15.0))
    system.add_unit(constructor_unit)

    # Friendly target unit (Scout / Medium hull)
    target_unit = Unit(
        owner=player,
        position=Position(150, 150),
        in_hex=HexCoord(0, 0),
        in_system="Sol",
        name="Scout-1",
        hull_size=HullSize.MEDIUM,
        game=game,
        template_name="Scout"
    )
    system.add_unit(target_unit)

    return game, galaxy, player, enemy_player, constructor_unit, target_unit


def test_refit_add_component_success(setup_universe):
    game, galaxy, player, _, constructor_unit, target_unit = setup_universe
    initial_credits = player.credits
    initial_hull_usage = target_unit.current_hull_usage

    assert target_unit.get_component(Defenses) is None

    # Issue refit order to install Defenses
    order = RefitOrder(constructor_unit, {
        "target_unit_id": target_unit.id,
        "action": "ADD",
        "component_type": "Defenses",
        "component_config": {"armor": 50, "shields": 50, "point_defense": 0, "hull_cost": 10.0},
        "cost_credits": 300,
        "time_to_build": 2
    })
    order.execute(galaxy)

    assert constructor_unit.constructor_component.current_refit_target is not None
    assert player.credits == initial_credits - 300
    assert order.status == OrderStatus.IN_PROGRESS

    # Tick 1: Progress = 1 / 2
    constructor_unit.constructor_component.update(galaxy)
    assert constructor_unit.constructor_component.refit_progress == 1
    assert target_unit.get_component(Defenses) is None

    # Tick 2: Progress = 2 / 2 -> Finishes
    constructor_unit.constructor_component.update(galaxy)
    order.check_completion_conditions()

    assert target_unit.get_component(Defenses) is not None
    assert target_unit.current_hull_usage > initial_hull_usage
    assert constructor_unit.constructor_component.current_refit_target is None
    assert order.status == OrderStatus.COMPLETED


def test_refit_remove_component_with_refund(setup_universe):
    game, galaxy, player, _, constructor_unit, target_unit = setup_universe

    # Install Repair component on target unit initially
    repair_comp = RepairComponent(target_unit, repair_rate=10.0, repair_range=200.0, hull_cost=10.0)
    target_unit.add_component(repair_comp)
    assert target_unit.get_component(RepairComponent) is not None
    hull_usage_before = target_unit.current_hull_usage
    credits_before = player.credits

    # Issue refit order to remove RepairComponent
    order = RefitOrder(constructor_unit, {
        "target_unit_id": target_unit.id,
        "action": "REMOVE",
        "component_type": "RepairComponent",
        "time_to_build": 1
    })
    order.execute(galaxy)

    assert order.status == OrderStatus.IN_PROGRESS
    # Salvage refund granted on removal start/order
    assert player.credits > credits_before

    # Complete 1 turn
    constructor_unit.constructor_component.update(galaxy)
    order.check_completion_conditions()

    assert target_unit.get_component(RepairComponent) is None
    assert target_unit.current_hull_usage < hull_usage_before
    assert order.status == OrderStatus.COMPLETED


def test_refit_remove_via_event_with_none_time_to_build(setup_universe):
    game, galaxy, player, _, constructor_unit, target_unit = setup_universe
    order_system = OrderSystem(game, game.event_bus)

    weapons_comp = Weapons(target_unit, hull_cost=5.0)
    target_unit.add_component(weapons_comp)
    assert target_unit.get_component(Weapons) is not None

    # Publish event as input_processor does (time_to_build and cost_credits are None)
    event = RefitUnitEvent(
        units=[constructor_unit],
        target_unit=target_unit,
        action="REMOVE",
        component_type="Weapons"
    )
    game.event_bus.publish(event)

    order = constructor_unit.commander_component.current_order
    assert isinstance(order, RefitOrder)
    assert order.status == OrderStatus.IN_PROGRESS
    assert constructor_unit.constructor_component.current_refit_target is not None

    # 1 turn ticks and finishes
    constructor_unit.constructor_component.update(galaxy)
    order.check_completion_conditions()

    assert target_unit.get_component(Weapons) is None
    assert order.status == OrderStatus.COMPLETED


def test_refit_exceeding_hull_capacity_fails(setup_universe):
    game, galaxy, player, _, constructor_unit, target_unit = setup_universe

    # Fill target unit's hull usage almost to maximum capacity
    cap = target_unit.hull_capacity
    target_unit.current_hull_usage = cap - 2.0

    # Attempt to install a component requiring 15 hull points
    order = RefitOrder(constructor_unit, {
        "target_unit_id": target_unit.id,
        "action": "ADD",
        "component_type": "RepairComponent",
        "component_config": {"hull_cost": 15.0},
        "cost_credits": 450,
        "time_to_build": 2
    })
    order.execute(galaxy)

    assert order.status == OrderStatus.FAILED
    assert target_unit.get_component(RepairComponent) is None
    assert constructor_unit.constructor_component.current_refit_target is None


def test_refit_hull_restriction_fails(setup_universe):
    game, galaxy, player, _, constructor_unit, target_unit = setup_universe

    # Change target unit to TINY hull size (forbidden from mounting Hangar)
    target_unit.hull_size = HullSize.TINY

    order = RefitOrder(constructor_unit, {
        "target_unit_id": target_unit.id,
        "action": "ADD",
        "component_type": "HangarComponent",
        "component_config": {"max_slots": 2, "hull_cost": 10.0},
        "cost_credits": 300,
        "time_to_build": 2
    })
    order.execute(galaxy)

    assert order.status == OrderStatus.FAILED
    assert target_unit.get_component(HangarComponent) is None


def test_refit_already_installed_fails(setup_universe):
    game, galaxy, player, _, constructor_unit, target_unit = setup_universe

    target_unit.add_component(Defenses(target_unit, armor=50, shields=50, point_defense=0, hull_cost=10.0))

    order = RefitOrder(constructor_unit, {
        "target_unit_id": target_unit.id,
        "action": "ADD",
        "component_type": "Defenses",
        "component_config": {"hull_cost": 10.0},
        "cost_credits": 300,
        "time_to_build": 2
    })
    order.execute(galaxy)

    assert order.status == OrderStatus.FAILED


def test_refit_remove_commander_fails(setup_universe):
    game, galaxy, player, _, constructor_unit, target_unit = setup_universe

    order = RefitOrder(constructor_unit, {
        "target_unit_id": target_unit.id,
        "action": "REMOVE",
        "component_type": "Commander",
        "time_to_build": 1
    })
    order.execute(galaxy)

    assert order.status == OrderStatus.FAILED
    assert target_unit.commander_component is not None


def test_refit_remove_hangar_with_docked_units_fails(setup_universe):
    game, galaxy, player, _, constructor_unit, target_unit = setup_universe

    hangar = HangarComponent(target_unit, max_slots=2, hull_cost=10.0)
    target_unit.add_component(hangar)

    # Dock a craft inside hangar
    docked_craft = Unit(owner=player, position=Position(150, 150), in_hex=HexCoord(0, 0), in_system="Sol", name="Fighter-1", hull_size=HullSize.TINY, game=game)
    hangar.docked_units.append(docked_craft)

    order = RefitOrder(constructor_unit, {
        "target_unit_id": target_unit.id,
        "action": "REMOVE",
        "component_type": "HangarComponent",
        "time_to_build": 1
    })
    order.execute(galaxy)

    assert order.status == OrderStatus.FAILED
    assert target_unit.get_component(HangarComponent) is not None


def test_refit_out_of_range_approaches_target(setup_universe):
    game, galaxy, player, _, constructor_unit, target_unit = setup_universe

    # Place constructor far away from target (> 500 px)
    constructor_unit.position = Position(2000, 2000)
    constructor_unit.add_component(Engines(constructor_unit, speed=200, hull_cost=10.0))

    order = RefitOrder(constructor_unit, {
        "target_unit_id": target_unit.id,
        "action": "ADD",
        "component_type": "MiningComponent",
        "cost_credits": 300,
        "time_to_build": 2
    })
    order.execute(galaxy)

    # Sub-orders should be spawned: MoveOrder + RefitOrder
    assert len(order.sub_orders) == 2
    assert order.sub_orders[0].order_type == OrderType.MOVE
    assert order.sub_orders[1].order_type == OrderType.REFIT_UNIT


def test_refit_cancel_refunds_credits(setup_universe):
    game, galaxy, player, _, constructor_unit, target_unit = setup_universe
    initial_credits = player.credits

    order = RefitOrder(constructor_unit, {
        "target_unit_id": target_unit.id,
        "action": "ADD",
        "component_type": "MiningComponent",
        "cost_credits": 400,
        "time_to_build": 3
    })
    order.execute(galaxy)

    assert player.credits == initial_credits - 400
    assert constructor_unit.constructor_component.current_refit_target is not None

    # Cancel order
    order.cancel()
    assert order.status == OrderStatus.CANCELLED
    assert player.credits == initial_credits
    assert constructor_unit.constructor_component.current_refit_target is None


def test_refit_save_load_persistence(setup_universe):
    game, galaxy, player, enemy_player, constructor_unit, target_unit = setup_universe

    # Add a component to target unit dynamically
    mining_comp = MiningComponent(target_unit, mining_rate=15.0, mining_range=250.0, max_cargo=120.0, hull_cost=12.0)
    target_unit.add_component(mining_comp)

    # Start an in-progress refit on constructor
    constructor_unit.constructor_component.start_refit(
        target_unit=target_unit,
        action="ADD",
        component_type="Defenses",
        component_config={"armor": 40, "shields": 60, "point_defense": 10, "hull_cost": 15.0},
        cost_credits=450,
        time_to_build=3
    )
    constructor_unit.constructor_component.refit_progress = 1

    # Serialize both units
    target_data = serialize_unit(target_unit)
    constructor_data = serialize_unit(constructor_unit)

    players_by_id = {player.id: player, enemy_player.id: enemy_player}

    # Deserialize
    loaded_target = deserialize_unit(target_data, players_by_id, game)
    loaded_constructor = deserialize_unit(constructor_data, players_by_id, game)

    # Verify loaded target has the dynamically added MiningComponent
    loaded_mining = loaded_target.get_component(MiningComponent)
    assert loaded_mining is not None
    assert loaded_mining.mining_rate == 15.0
    assert loaded_mining.max_cargo == 120.0

    # Verify loaded constructor preserved refit progress
    assert loaded_constructor.constructor_component.current_refit_target is not None
    assert loaded_constructor.constructor_component.current_refit_target["component_type"] == "Defenses"
    assert loaded_constructor.constructor_component.refit_progress == 1
    assert loaded_constructor.constructor_component.refit_time == 3


def test_refit_event_and_order_system(setup_universe):
    game, galaxy, player, _, constructor_unit, target_unit = setup_universe
    order_system = OrderSystem(game, game.event_bus)

    event = RefitUnitEvent(
        units=[constructor_unit],
        target_unit=target_unit,
        action="ADD",
        component_type="Defenses",
        component_config={"hull_cost": 10.0},
        cost_credits=300,
        time_to_build=2
    )
    game.event_bus.publish(event)

    assert constructor_unit.commander_component.current_order is not None
    order = constructor_unit.commander_component.current_order
    assert isinstance(order, RefitOrder)
    assert order.parameters["target_unit_id"] == target_unit.id
    assert order.parameters["component_type"] == "Defenses"


def test_input_processor_get_refit_context_options(setup_universe):
    game, galaxy, player, _, constructor_unit, target_unit = setup_universe
    from input_processor import InputProcessor
    ip = InputProcessor(game)

    options = ip.get_refit_context_options([constructor_unit], target_unit)
    assert len(options) > 0

    option_labels = [opt[0] for opt in options]
    assert "Add Component" in option_labels
    assert "Remove Component" in option_labels

    # Check Add options
    add_sub = next(opt[1] for opt in options if opt[0] == "Add Component")
    add_action_ids = [sub[1] for sub in add_sub]
    assert "refit_add_Defenses" in add_action_ids
    assert "refit_add_MiningComponent" in add_action_ids
