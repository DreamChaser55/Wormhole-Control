"""Automated tests for Gas Giant atmospheric hiding mechanics, orders, visibility, upkeep, UI, and AI."""
import math
import pytest
from constants import PlanetType, HullSize
from entities import Unit, Planet, Player
from geometry import Position, distance
from utils import HexCoord
from unit_components import Engines, Weapons, HyperspaceInhibitionFieldEmitter, CloakingDevice, Commander, UnitStance
from unit_components.weapons import Turret
from unit_components.enums import TurretType
from unit_orders.gas_giant import EnterGasGiantOrder, LeaveGasGiantOrder
from unit_orders.base import OrderStatus
from visibility import is_unit_visible
from economy import calculate_player_upkeep
from gui.sidebar.panels_world import build_celestial_body_panel
from gui.sidebar.panels_unit import build_unit_panel
from input_processor.context_menu_builder import build_sector_context_menu_options
from game_ai.command_spec import COMMAND_SPECS
from game_ai.rules import supported_commands, capability_blocker, command_guidance
from game_ai.commands import CommandBatch, CommandGateway
from game_ai.observation import build_observation
from save_manager import serialize_game_state, deserialize_game_state


class DummyHex:
    def __init__(self, coord=HexCoord(0, 0), in_system="Sol"):
        self.coord = coord
        self.q = coord.q
        self.r = coord.r
        self.in_system = in_system
        self.units = []
        self.celestial_bodies = []
        self.minefields = []

    def add_unit(self, unit):
        self.units.append(unit)

    def remove_unit(self, unit):
        if unit in self.units:
            self.units.remove(unit)


class DummySystem:
    def __init__(self, name="Sol"):
        self.name = name
        self.hexes = {HexCoord(0, 0): DummyHex(HexCoord(0, 0), in_system=name)}
        self.position = Position(0, 0)
        self.radius = 5000

    def add_unit(self, unit, hex_coord=None):
        target_hex = hex_coord or unit.in_hex or HexCoord(0, 0)
        if target_hex in self.hexes:
            self.hexes[target_hex].add_unit(unit)
            unit.in_system = self.name
            unit.in_hex = target_hex

    def get_all_units(self):
        units = []
        for hex_coord, hex_obj in self.hexes.items():
            for unit in hex_obj.units:
                units.append((unit, hex_coord))
        return units

    def get_all_celestial_bodies(self):
        bodies = []
        for hex_coord, hex_obj in self.hexes.items():
            for body in hex_obj.celestial_bodies:
                bodies.append((hex_coord, body))
        return bodies

    def remove_unit(self, unit):
        for hex_obj in self.hexes.values():
            if unit in hex_obj.units:
                hex_obj.remove_unit(unit)
                unit.in_system = None
                return True
        return False


class DummyGalaxy:
    def __init__(self):
        self.systems = {"Sol": DummySystem("Sol")}
        self.turn_number = 1
        self.system_graph = {"Sol": {}}

    def get_celestial_body_by_id(self, body_id):
        for system in self.systems.values():
            for _, body in system.get_all_celestial_bodies():
                if body.id == body_id:
                    return body
        return None

    def get_unit_by_id(self, unit_id):
        for system in self.systems.values():
            for hex_obj in system.hexes.values():
                for unit in hex_obj.units:
                    if unit.id == unit_id:
                        return unit
                for body in hex_obj.celestial_bodies:
                    for u in getattr(body, 'hidden_units', []):
                        if u.id == unit_id:
                            return u
        return None

    def remove_unit(self, unit):
        if unit.in_system in self.systems:
            return self.systems[unit.in_system].remove_unit(unit)
        return False


class DummyGame:
    def __init__(self):
        self.galaxy = DummyGalaxy()
        self.players = [Player("Player 1", (0, 100, 255)), Player("Player 2", (255, 50, 50))]
        self.current_player_index = 0
        self.selected_objects = []
        self.turn_number = 1
        self.sidebar_needs_update = False
        self.visibility_dirty = False
        self.current_system_name = "Sol"
        self.current_sector_coord = HexCoord(0, 0)
        self.pending_ability = None
        self.selected_unit_tab = 'basic_info'
        self.selected_component_name = None

    @property
    def current_player(self):
        return self.players[self.current_player_index]


def create_test_setup():
    game = DummyGame()
    p1 = game.players[0]
    p2 = game.players[1]
    hex_obj = game.galaxy.systems["Sol"].hexes[HexCoord(0, 0)]

    gas_giant = Planet(HexCoord(0, 0), "Sol", PlanetType.GAS_GIANT)
    gas_giant.name = "Jupiter"
    gas_giant.position = Position(1000.0, 1000.0)
    gas_giant.id = 101
    hex_obj.celestial_bodies.append(gas_giant)

    ship = Unit(
        owner=p1,
        position=Position(1000.0, 1000.0),
        in_hex=HexCoord(0, 0),
        in_system="Sol",
        name="Cruiser Alpha",
        hull_size=HullSize.MEDIUM,
        game=game
    )
    ship.id = 1
    engines = Engines(ship, speed=150.0)
    ship.add_component(engines)
    hex_obj.add_unit(ship)

    wing = Unit(
        owner=p1,
        position=Position(1000.0, 1000.0),
        in_hex=HexCoord(0, 0),
        in_system="Sol",
        name="Fighter Wing",
        hull_size=HullSize.STRIKECRAFT_WING,
        game=game
    )
    wing.id = 2
    wing_engines = Engines(wing, speed=250.0)
    wing.add_component(wing_engines)
    hex_obj.add_unit(wing)

    enemy_ship = Unit(
        owner=p2,
        position=Position(1000.0, 1000.0),
        in_hex=HexCoord(0, 0),
        in_system="Sol",
        name="Enemy Scout",
        hull_size=HullSize.SMALL,
        game=game
    )
    enemy_ship.id = 3
    enemy_engines = Engines(enemy_ship, speed=180.0)
    enemy_ship.add_component(enemy_engines)
    hex_obj.add_unit(enemy_ship)

    return game, gas_giant, ship, wing, enemy_ship


# --- Tests ---

def test_can_hide_unit_validation():
    game, gas_giant, ship, wing, enemy_ship = create_test_setup()

    # Eligible medium ship with operational engines can hide
    assert gas_giant.can_hide_unit(ship) is True

    # Strikecraft wings are strictly prohibited
    assert gas_giant.can_hide_unit(wing) is False

    station = Unit(
        owner=game.players[0],
        position=Position(1000.0, 1000.0),
        in_hex=HexCoord(0, 0),
        in_system="Sol",
        name="Orbital Station",
        hull_size=HullSize.LARGE,
        game=game
    )
    assert gas_giant.can_hide_unit(station) is False

    # Non-gas giant planet cannot hide ships
    terran_planet = Planet(HexCoord(0, 0), "Sol", PlanetType.TERRAN)
    terran_planet.name = "Earth"
    terran_planet.position = Position(2000.0, 2000.0)
    assert terran_planet.can_hide_unit(ship) is False


def test_hide_unit_and_release_unit_mechanics():
    game, gas_giant, ship, wing, enemy_ship = create_test_setup()
    hex_obj = game.galaxy.systems["Sol"].hexes[HexCoord(0, 0)]

    # Add active components
    inhibitor = HyperspaceInhibitionFieldEmitter(ship, radius=2000.0)
    inhibitor.is_active = True
    ship.add_component(inhibitor)

    cloak = CloakingDevice(ship)
    cloak.is_active = True
    ship.add_component(cloak)

    weapons = Weapons(ship)
    turret = Turret(turret_type=TurretType.BEAM, damage=10.0, range=300.0, cooldown=1, parent_unit=ship)
    weapons.add_turret(turret)
    ship.add_component(weapons)
    weapons.set_target(enemy_ship)
    assert turret.target == enemy_ship

    assert ship in hex_obj.units
    assert ship not in gas_giant.hidden_units

    # Submerge ship
    success = gas_giant.hide_unit(ship, game.galaxy)
    assert success is True
    assert ship not in hex_obj.units
    assert ship in gas_giant.hidden_units
    assert ship.is_hidden_in_gas_giant is True
    assert ship.hidden_in_gas_giant_id == gas_giant.id

    # Active systems and targets suppressed
    assert all(t.target is None for t in weapons.turrets)
    assert ship.commander_component.stance == UnitStance.DO_NOTHING
    assert inhibitor.is_active is False
    assert cloak.is_active is False

    # Updating ship while hidden returns early without error or movement
    initial_pos = Position(ship.position.x, ship.position.y)
    ship.update()
    assert ship.position == initial_pos

    # Release ship
    emerge_pos = gas_giant.release_unit(ship, game.galaxy)
    assert emerge_pos is not None
    assert ship in hex_obj.units
    assert ship not in gas_giant.hidden_units
    assert ship.is_hidden_in_gas_giant is False
    assert ship.hidden_in_gas_giant_id is None

    # Emerges outside collision radius (675.0 + 50.0 = 725.0)
    d = distance(emerge_pos, gas_giant.position)
    assert pytest.approx(d, abs=0.5) == 725.0


def test_multiple_units_emerge_on_distinct_vectors():
    game, gas_giant, ship, wing, enemy_ship = create_test_setup()

    ship2 = Unit(
        owner=game.players[0],
        position=Position(1000.0, 1000.0),
        in_hex=HexCoord(0, 0),
        in_system="Sol",
        name="Cruiser Beta",
        hull_size=HullSize.MEDIUM,
        game=game
    )
    ship2.id = 4
    ship2.add_component(Engines(ship2, speed=150.0))

    gas_giant.hide_unit(ship, game.galaxy)
    gas_giant.hide_unit(ship2, game.galaxy)
    assert len(gas_giant.hidden_units) == 2

    pos1 = gas_giant.release_unit(ship, game.galaxy)
    pos2 = gas_giant.release_unit(ship2, game.galaxy)

    assert distance(pos1, gas_giant.position) > gas_giant.collision_radius
    assert distance(pos2, gas_giant.position) > gas_giant.collision_radius
    # Verify they don't emerge on the exact same spot
    assert distance(pos1, pos2) > 1.0


def test_sensor_invisibility_and_non_attackable():
    game, gas_giant, ship, wing, enemy_ship = create_test_setup()
    p1 = game.players[0]
    p2 = game.players[1]

    from visibility import VisibilityService, is_unit_visible
    snapshot_p2 = VisibilityService.compute(game.galaxy, p2)
    assert is_unit_visible(snapshot_p2, ship) is True

    # Submerge ship
    gas_giant.hide_unit(ship, game.galaxy)

    snapshot_p2_after = VisibilityService.compute(game.galaxy, p2)
    # Invisible to enemy short-range / long-range sensors
    assert is_unit_visible(snapshot_p2_after, ship) is False

    # Also hide enemy ship in the same gas giant
    gas_giant.hide_unit(enemy_ship, game.galaxy)

    snapshot_p1_after = VisibilityService.compute(game.galaxy, p1)
    # Neither can see each other
    assert is_unit_visible(snapshot_p2_after, ship) is False
    assert is_unit_visible(snapshot_p1_after, enemy_ship) is False


def test_submerged_unit_upkeep():
    game, gas_giant, ship, wing, enemy_ship = create_test_setup()
    p1 = game.players[0]

    upkeep_before = calculate_player_upkeep(game.galaxy, p1)
    assert upkeep_before > 0

    # Submerge ship
    gas_giant.hide_unit(ship, game.galaxy)

    upkeep_after = calculate_player_upkeep(game.galaxy, p1)
    # Upkeep continues while submerged in gas giant
    assert upkeep_after == upkeep_before


def test_enter_gas_giant_order():
    game, gas_giant, ship, wing, enemy_ship = create_test_setup()

    # Strikecraft wings cannot execute enter gas giant order
    wing_order = EnterGasGiantOrder(wing, {"target_id": gas_giant.id})
    wing_order.execute(game.galaxy)
    assert wing_order.status == OrderStatus.FAILED

    # Ship far away from gas giant will spawn approach sub-order
    ship.position = Position(3000.0, 3000.0)
    order = EnterGasGiantOrder(ship, {"target_id": gas_giant.id})
    ship.commander_component.add_order(order)
    assert ship.commander_component.current_order is not None

    # When close (within collision radius + buffer), execute directly submerges
    ship.position = Position(1000.0, 1000.0)
    close_order = EnterGasGiantOrder(ship, {"target_id": gas_giant.id})
    close_order.execute(game.galaxy)
    assert ship.is_hidden_in_gas_giant is True
    assert close_order.status == OrderStatus.COMPLETED


def test_leave_gas_giant_order():
    game, gas_giant, ship, wing, enemy_ship = create_test_setup()
    gas_giant.hide_unit(ship, game.galaxy)
    assert ship.is_hidden_in_gas_giant is True

    leave_order = LeaveGasGiantOrder(ship, {})
    leave_order.execute(game.galaxy)
    assert ship.is_hidden_in_gas_giant is False
    assert leave_order.status == OrderStatus.COMPLETED


def test_sidebar_and_context_menu():
    game, gas_giant, ship, wing, enemy_ship = create_test_setup()
    hex_obj = game.galaxy.systems["Sol"].hexes[HexCoord(0, 0)]

    # Hide friendly ship and enemy ship
    gas_giant.hide_unit(ship, game.galaxy)
    gas_giant.hide_unit(enemy_ship, game.galaxy)

    # Celestial body sidebar panel for gas giant
    panel_data = build_celestial_body_panel(game, gas_giant)
    button_actions = [item.get('action_id') for item in panel_data if item.get('type') == 'button']
    button_texts = [item.get('text', '') for item in panel_data]

    # Friendly hidden ship is listed, but enemy ship is NOT
    assert any(ship.name in text for text in button_texts)
    assert not any(enemy_ship.name in text for text in button_texts)
    assert 'order_unit_leave_gas_giant' in button_actions

    # Unit panel for submerged ship
    unit_panel_data = build_unit_panel(game, ship)
    unit_panel_texts = [item.get('text', '') for item in unit_panel_data]
    assert any("SUBMERGED IN GAS GIANT" in t for t in unit_panel_texts)
    assert any(item.get('action_id') == 'order_unit_leave_gas_giant' for item in unit_panel_data)

    # Context menu on gas giant
    options, target = build_sector_context_menu_options(game, gas_giant, gas_giant.position)
    opt_labels = [opt[0] for opt in options]
    assert any("Leave" in label for label in opt_labels)


def test_agentic_ai_commands_and_observation():
    game, gas_giant, ship, wing, enemy_ship = create_test_setup()
    p1 = game.players[0]

    # Check command specs
    assert "enter_gas_giant" in COMMAND_SPECS
    assert "leave_gas_giant" in COMMAND_SPECS

    # Check supported commands
    assert "enter_gas_giant" in supported_commands(ship)
    assert "enter_gas_giant" not in supported_commands(wing)
    assert capability_blocker(wing, "enter_gas_giant") is not None

    # AI Observation hides enemy submerged units
    gas_giant.hide_unit(ship, game.galaxy)
    gas_giant.hide_unit(enemy_ship, game.galaxy)

    obs = build_observation(game, p1)
    body_data = next((b for s in obs["systems"] for b in s.get("celestial_bodies", []) if b["id"] == gas_giant.id), None)
    assert body_data is not None
    # Friendly hidden unit id is exposed, enemy is not
    assert "hidden_unit_ids" in body_data
    assert ship.id in body_data["hidden_unit_ids"]
    assert enemy_ship.id not in body_data["hidden_unit_ids"]

    # Submerged unit legal commands in guidance
    submerged_ship_data = next((u for u in obs["units"] if u["id"] == ship.id), None)
    assert submerged_ship_data is not None
    assert submerged_ship_data.get("is_hidden_in_gas_giant") is True
    assert "leave_gas_giant" in submerged_ship_data["legal_commands"]
    assert "move" not in submerged_ship_data["legal_commands"]
    assert "attack" not in submerged_ship_data["legal_commands"]


def test_save_load_roundtrip_with_submerged_units():
    game, gas_giant, ship, wing, enemy_ship = create_test_setup()
    gas_giant.hide_unit(ship, game.galaxy)
    assert ship.is_hidden_in_gas_giant is True

    from save_manager import serialize_celestial_body, deserialize_celestial_body
    serialized_body = serialize_celestial_body(gas_giant)
    assert "hidden_units" in serialized_body
    assert len(serialized_body["hidden_units"]) == 1

    restored_gg = deserialize_celestial_body(serialized_body, game)
    assert restored_gg is not None
    assert len(restored_gg.hidden_units) == 1
    restored_ship = restored_gg.hidden_units[0]
    assert restored_ship.id == ship.id
    assert restored_ship.is_hidden_in_gas_giant is True
    assert restored_ship.hidden_in_gas_giant_id == gas_giant.id

    # Full game state roundtrip
    from game import Game
    full_game = Game()
    full_game.start_new_game()
    gg = None
    for sys in full_game.galaxy.systems.values():
        for hex_obj in sys.hexes.values():
            for body in hex_obj.celestial_bodies:
                if getattr(body, 'planet_type', None) == PlanetType.GAS_GIANT:
                    gg = body
                    break
            if gg:
                break
        if gg:
            break
    if gg:
        player = full_game.players[0]
        test_ship = Unit(
            owner=player,
            position=gg.position,
            in_hex=gg.in_hex,
            in_system=gg.in_system,
            name="Test Submerged Ship",
            hull_size=HullSize.MEDIUM,
            game=full_game
        )
        test_ship.add_component(Engines(test_ship, speed=100.0))
        full_game.galaxy.systems[gg.in_system].hexes[gg.in_hex].add_unit(test_ship)
        gg.hide_unit(test_ship, full_game.galaxy)

        payload = serialize_game_state(full_game)
        restored = Game()
        deserialize_game_state(restored, payload)
        loaded_gg = restored.galaxy.get_celestial_body_by_id(gg.id)
        assert loaded_gg is not None
        assert any(u.id == test_ship.id for u in loaded_gg.hidden_units)
