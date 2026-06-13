import pytest
from unittest.mock import MagicMock
from geometry import Position
from turn_processor import TurnProcessor
from unit_orders import MoveOrder, OrderStatus, ReachWaypointOrder
from unit_components import Engines, Hyperdrive, HyperdriveType, Commander, JumpStatus
from tests.test_unit_components import MockPlayer, MockUnit

class SimpleHex:
    def __init__(self, q, r, in_system):
        self.q = q
        self.r = r
        self.in_system = in_system
        self.units = []
        self.celestial_bodies = []
        from geometry import Circle
        self.boundary_circle = Circle(Position(0, 0), 1000.0)
        self.dynamic_inhibition_zones = {}
        self.static_inhibition_zones = []
        
    def get_all_inhibition_zones(self):
        return []
        
    def add_unit(self, unit):
        self.units.append(unit)
        
    def remove_unit(self, unit):
        if unit in self.units:
            self.units.remove(unit)
            
    def coordinates(self):
        return (self.q, self.r)

class SimpleSystem:
    def __init__(self, name):
        self.name = name
        self.hexes = {}
        # Generate grid with radius 3
        for q in range(-3, 4):
            r1 = max(-3, -q - 3)
            r2 = min(3, -q + 3)
            for r in range(r1, r2 + 1):
                self.hexes[(q, r)] = SimpleHex(q, r, name)
                    
    def get_all_units(self):
        units = []
        for hex_obj in self.hexes.values():
            for unit in hex_obj.units:
                units.append((unit, (hex_obj.q, hex_obj.r)))
        return units
        
    def get_all_celestial_bodies(self):
        bodies = []
        for hex_obj in self.hexes.values():
            for body in hex_obj.celestial_bodies:
                bodies.append(((hex_obj.q, hex_obj.r), body))
        return bodies
        
    def add_unit(self, unit):
        hex_obj = self.hexes.get(unit.in_hex)
        if hex_obj:
            hex_obj.add_unit(unit)
            
    def remove_unit(self, unit):
        hex_obj = self.hexes.get(unit.in_hex)
        if hex_obj:
            if unit in hex_obj.units:
                hex_obj.remove_unit(unit)
                return True
        return False
        
    def move_unit_between_hexes(self, unit, destination_hex):
        self.remove_unit(unit)
        unit.in_hex = destination_hex
        self.add_unit(unit)
        return True

class SimpleWormhole:
    def __init__(self, wh_id, in_system, in_hex, exit_system_name, exit_wormhole_id, position):
        self.id = wh_id
        self.in_system = in_system
        self.in_hex = in_hex
        self.exit_system_name = exit_system_name
        self.exit_wormhole_id = exit_wormhole_id
        self.position = position
        self.name = f"Wormhole-{wh_id}"

class SimpleGalaxy:
    def __init__(self):
        self.systems = {
            "Sol": SimpleSystem("Sol"),
            "Vega": SimpleSystem("Vega")
        }
        self.wormholes = {}
        self.system_graph = {"Sol": ["Vega"], "Vega": ["Sol"]}
        
    def get_unit_by_id(self, unit_id):
        for sys in self.systems.values():
            for unit, _ in sys.get_all_units():
                if unit.id == unit_id:
                    return unit
        return None
        
    def remove_unit(self, unit):
        if unit.in_system in self.systems:
            self.systems[unit.in_system].remove_unit(unit)

    def move_unit_between_systems(self, unit, origin_system_name, destination_system_name, destination_hex):
        orig = self.systems[origin_system_name]
        dest = self.systems[destination_system_name]
        orig.remove_unit(unit)
        unit.in_system = destination_system_name
        unit.in_hex = destination_hex
        dest.add_unit(unit)
        return True

def test_integration_sublight_movement_flow():
    game = MagicMock()
    galaxy = SimpleGalaxy()
    game.galaxy = galaxy
    
    player = MockPlayer()
    game.players = [player]
    game.current_player_index = 0
    
    # Setup Unit
    unit = MockUnit()
    unit.owner = player
    unit.game = game
    unit.in_galaxy = galaxy
    unit.in_system = "Sol"
    unit.in_hex = (0, 0)
    unit.position = Position(0, 0)
    
    engines = Engines(unit, speed=50.0)
    commander = Commander(unit)
    unit.add_component(engines)
    unit.add_component(commander)
    
    galaxy.systems["Sol"].add_unit(unit)
    
    # Assign order: sublight move within hex (0,0) to Position(120, 0)
    move_order = MoveOrder(unit, {
        "destination_system_name": "Sol",
        "destination_hex_coord": (0, 0),
        "destination_position": Position(120, 0)
    })
    commander.add_order(move_order)
    
    # Verify order execution sets engines target
    assert commander.current_order == move_order
    assert len(move_order.sub_orders) == 1
    assert engines.move_target == Position(120, 0)
    
    tp = TurnProcessor(game)
    
    # Turn 1
    tp.process_turn()
    assert unit.position.x == 50.0
    assert move_order.status == OrderStatus.IN_PROGRESS
    
    # Turn 2
    tp.process_turn()
    assert unit.position.x == 100.0
    assert move_order.status == OrderStatus.IN_PROGRESS
    
    # Turn 3
    tp.process_turn()
    assert unit.position.x == 120.0 # Arrives
    # The TurnProcessor executes movements first, then unit updates.
    # By the end of Turn 3, the movement arrived and unit.update() was called which triggered commander update,
    # moving the ReachWaypointOrder to COMPLETED and thus the MoveOrder to COMPLETED.
    assert move_order.status == OrderStatus.COMPLETED
    assert engines.move_target is None

def test_integration_wormhole_jump_flow():
    game = MagicMock()
    galaxy = SimpleGalaxy()
    game.galaxy = galaxy
    
    player = MockPlayer()
    game.players = [player]
    game.current_player_index = 0
    
    # Setup linked wormholes
    # Sol wormhole in hex (1, 1) leading to Vega. exit_wh is Vega wormhole in hex (-1, -1)
    wh_sol = SimpleWormhole(1, "Sol", (1, 1), "Vega", 2, Position(5, 5))
    wh_vega = SimpleWormhole(2, "Vega", (-1, -1), "Sol", 1, Position(10, 10))
    galaxy.wormholes[1] = wh_sol
    galaxy.wormholes[2] = wh_vega
    
    galaxy.systems["Sol"].hexes[(1, 1)].celestial_bodies.append(wh_sol)
    galaxy.systems["Vega"].hexes[(-1, -1)].celestial_bodies.append(wh_vega)
    
    # Setup Unit in Sol at (0, 0)
    unit = MockUnit()
    unit.owner = player
    unit.game = game
    unit.in_galaxy = galaxy
    unit.in_system = "Sol"
    unit.in_hex = (0, 0)
    unit.position = Position(0, 0)
    
    engines = Engines(unit, speed=100.0)
    hd = Hyperdrive(unit, drive_type=HyperdriveType.ADVANCED, jump_range=5, recharge_duration=3)
    commander = Commander(unit)
    unit.add_component(engines)
    unit.add_component(hd)
    unit.add_component(commander)
    
    galaxy.systems["Sol"].add_unit(unit)
    
    # Move order to Vega hex (-1, -1) position (10, 10)
    move_order = MoveOrder(unit, {
        "destination_system_name": "Vega",
        "destination_hex_coord": (-1, -1),
        "destination_position": Position(10, 10)
    })
    commander.add_order(move_order)
    
    # Pathplanning creates:
    # 1. ReachWaypointOrder (hex jump) from (0,0) to wormhole hex (1,1) position (5,5)
    # 2. ReachWaypointOrder (wormhole jump) from (1,1) in Sol to (-1,-1) in Vega position (10,10)
    assert len(move_order.sub_orders) == 2
    assert move_order.sub_orders[0].parameters["destination_hex_coord"] == (1, 1)
    assert move_order.sub_orders[1].parameters["destination_hex_coord"] == (-1, -1)
    
    # First sub-order (hex jump) becomes active
    assert hd.hex_jump_target == ((1, 1), Position(5, 5))
    
    tp = TurnProcessor(game)
    
    # Turn 1: process movement (executes hex jump) -> unit moves to (1,1) in Sol. hd goes to CHARGING status.
    tp.process_turn()
    assert unit.in_system == "Sol"
    assert unit.in_hex == (1, 1)
    assert hd.jump_status == JumpStatus.CHARGING
    assert hd.recharge_time_remaining == 2
    
    # Turn 2: charging (1 turn left)
    tp.process_turn()
    assert hd.jump_status == JumpStatus.CHARGING
    assert hd.recharge_time_remaining == 1
    
    # Turn 3: recharge completes (hd ready). Next sub-order (system jump) starts.
    tp.process_turn()
    assert hd.jump_status == JumpStatus.READY
    # By the end of this turn, since hd became ready during _process_unit_updates (update_recharge),
    # the commander will update, see sub-order 1 (hex jump) completed, and start sub-order 2 (system jump).
    # Commander start_next_order will set hd.wormhole_jump_target to wh_sol
    assert hd.wormhole_jump_target == wh_sol
    
    # Turn 4: Turn processor executes the system jump!
    tp.process_turn()
    # Unit should now be in Vega, hex (-1, -1)
    assert unit.in_system == "Vega"
    assert unit.in_hex == (-1, -1)
    assert unit.position == Position(10, 10)
    assert move_order.status == OrderStatus.COMPLETED


def test_integration_multi_system_movement():
    game = MagicMock()
    galaxy = SimpleGalaxy()
    # Add third system
    galaxy.systems["Sirius"] = SimpleSystem("Sirius")
    galaxy.system_graph = {
        "Sol": ["Vega"],
        "Vega": ["Sol", "Sirius"],
        "Sirius": ["Vega"]
    }
    game.galaxy = galaxy
    
    player = MockPlayer()
    game.players = [player]
    game.current_player_index = 0
    
    # Setup wormholes
    wh_sol_to_vega = SimpleWormhole(1, "Sol", (1, 1), "Vega", 2, Position(5, 5))
    wh_vega_from_sol = SimpleWormhole(2, "Vega", (-1, -1), "Sol", 1, Position(5, 5))
    wh_vega_to_sirius = SimpleWormhole(3, "Vega", (1, 1), "Sirius", 4, Position(10, 10))
    wh_sirius_from_vega = SimpleWormhole(4, "Sirius", (-2, 2), "Vega", 3, Position(20, 20))
    
    galaxy.wormholes[1] = wh_sol_to_vega
    galaxy.wormholes[2] = wh_vega_from_sol
    galaxy.wormholes[3] = wh_vega_to_sirius
    galaxy.wormholes[4] = wh_sirius_from_vega
    
    galaxy.systems["Sol"].hexes[(1, 1)].celestial_bodies.append(wh_sol_to_vega)
    galaxy.systems["Vega"].hexes[(-1, -1)].celestial_bodies.append(wh_vega_from_sol)
    galaxy.systems["Vega"].hexes[(1, 1)].celestial_bodies.append(wh_vega_to_sirius)
    galaxy.systems["Sirius"].hexes[(-2, 2)].celestial_bodies.append(wh_sirius_from_vega)
    
    # Setup Unit in Sol at (0, 0)
    unit = MockUnit()
    unit.owner = player
    unit.game = game
    unit.in_galaxy = galaxy
    unit.in_system = "Sol"
    unit.in_hex = (0, 0)
    unit.position = Position(0, 0)
    
    engines = Engines(unit, speed=100.0)
    hd = Hyperdrive(unit, drive_type=HyperdriveType.ADVANCED, jump_range=5, recharge_duration=1)
    commander = Commander(unit)
    unit.add_component(engines)
    unit.add_component(hd)
    unit.add_component(commander)
    
    galaxy.systems["Sol"].add_unit(unit)
    
    # Move order to Sirius, hex (-2, 2), Position(20, 20)
    move_order = MoveOrder(unit, {
        "destination_system_name": "Sirius",
        "destination_hex_coord": (-2, 2),
        "destination_position": Position(20, 20)
    })
    
    from unittest.mock import patch
    with patch("unit_orders.find_intersystem_path", return_value=["Sol", "Vega", "Sirius"]):
        commander.add_order(move_order)
    
    # We expect 5 sub-orders (including the final arrival waypoint check in Sirius)
    assert len(move_order.sub_orders) == 5
    assert move_order.sub_orders[0].parameters["destination_system_name"] == "Sol"
    assert move_order.sub_orders[0].parameters["destination_hex_coord"] == (1, 1)
    assert move_order.sub_orders[1].parameters["destination_system_name"] == "Vega"
    assert move_order.sub_orders[1].parameters["destination_hex_coord"] == (-1, -1)
    assert move_order.sub_orders[2].parameters["destination_system_name"] == "Vega"
    assert move_order.sub_orders[2].parameters["destination_hex_coord"] == (1, 1)
    assert move_order.sub_orders[3].parameters["destination_system_name"] == "Sirius"
    assert move_order.sub_orders[3].parameters["destination_hex_coord"] == (-2, 2)
    assert move_order.sub_orders[4].parameters["destination_system_name"] == "Sirius"
    assert move_order.sub_orders[4].parameters["destination_hex_coord"] == (-2, 2)
    
    tp = TurnProcessor(game)
    
    # Turn 1: executes hex jump Sol (0,0) -> Sol (1,1)
    tp.process_turn()
    assert unit.in_system == "Sol"
    assert unit.in_hex == (1, 1)
    assert hd.jump_status == JumpStatus.READY # recharge completes in same turn updates
    assert hd.wormhole_jump_target == wh_sol_to_vega
    
    # Turn 2: executes system jump Sol -> Vega (-1, -1)
    tp.process_turn()
    assert unit.in_system == "Vega"
    assert unit.in_hex == (-1, -1)
    assert hd.jump_status == JumpStatus.READY
    assert hd.hex_jump_target == ((1, 1), Position(10, 10))
    
    # Turn 3: executes hex jump Vega (-1, -1) -> Vega (1, 1)
    tp.process_turn()
    assert unit.in_system == "Vega"
    assert unit.in_hex == (1, 1)
    assert hd.jump_status == JumpStatus.READY
    assert hd.wormhole_jump_target == wh_vega_to_sirius
    
    # Turn 4: executes system jump Vega -> Sirius (-2, 2)
    tp.process_turn()
    assert unit.in_system == "Sirius"
    assert unit.in_hex == (-2, 2)
    assert unit.position == Position(20, 20)
    assert move_order.status == OrderStatus.COMPLETED

