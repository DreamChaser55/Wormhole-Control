import pytest
from unittest.mock import MagicMock
from constants import (
    FieldDensity, HullSize, CELESTIAL_FIELD_RADIUS,
    ASTEROID_FIELD_RADIUS, ICE_FIELD_RADIUS, DEBRIS_FIELD_RADIUS,
    ASTEROID_FIELD_DENSITY_SPEED_MOD, ICE_FIELD_DENSITY_SPEED_MOD,
    ICE_FIELD_DENSITY_BEAM_DEFENSE_BONUS, DEBRIS_FIELD_DENSITY_SPEED_MOD,
    DEBRIS_FIELD_DENSITY_DEFENSE_BONUS, DEBRIS_FIELD_DENSITY_HAZARD_DAMAGE
)
from entities import (
    AsteroidField, DebrisField, IceField, Player, Unit,
    is_position_blocked_by_celestial_field
)
from utils import HexCoord
from geometry import Position
from galaxy import StarSystem, Hex, Galaxy


def _make_unit(name, pos, hex_coord, system_name, hull_size, game=None):
    player = Player(name="Player1", color=(255, 0, 0))
    mock_game = game or MagicMock()
    return Unit(owner=player, position=pos, in_hex=hex_coord, in_system=system_name, name=name, hull_size=hull_size, game=mock_game)


def test_field_density_defaults_and_hull_restrictions():
    # LOW density: max LARGE (blocks HUGE)
    af_low = AsteroidField(in_hex=HexCoord(0, 0), in_system="Sol", density=FieldDensity.LOW)
    assert af_low.density == FieldDensity.LOW
    assert af_low.max_hull_size == HullSize.LARGE
    assert af_low.can_unit_enter(HullSize.STRIKECRAFT_WING)
    assert af_low.can_unit_enter(HullSize.TINY)
    assert af_low.can_unit_enter(HullSize.SMALL)
    assert af_low.can_unit_enter(HullSize.MEDIUM)
    assert af_low.can_unit_enter(HullSize.LARGE)
    assert not af_low.can_unit_enter(HullSize.HUGE)

    # MEDIUM density: max MEDIUM (blocks LARGE, HUGE)
    df_med = DebrisField(in_hex=HexCoord(0, 0), in_system="Sol")  # default is MEDIUM
    assert df_med.density == FieldDensity.MEDIUM
    assert df_med.max_hull_size == HullSize.MEDIUM
    assert df_med.can_unit_enter(HullSize.STRIKECRAFT_WING)
    assert df_med.can_unit_enter(HullSize.TINY)
    assert df_med.can_unit_enter(HullSize.SMALL)
    assert df_med.can_unit_enter(HullSize.MEDIUM)
    assert not df_med.can_unit_enter(HullSize.LARGE)
    assert not df_med.can_unit_enter(HullSize.HUGE)

    # HIGH density: max SMALL (blocks MEDIUM, LARGE, HUGE)
    ice_high = IceField(in_hex=HexCoord(0, 0), in_system="Sol", density=FieldDensity.HIGH)
    assert ice_high.density == FieldDensity.HIGH
    assert ice_high.max_hull_size == HullSize.SMALL
    assert ice_high.can_unit_enter(HullSize.STRIKECRAFT_WING)
    assert ice_high.can_unit_enter(HullSize.TINY)
    assert ice_high.can_unit_enter(HullSize.SMALL)
    assert not ice_high.can_unit_enter(HullSize.MEDIUM)
    assert not ice_high.can_unit_enter(HullSize.LARGE)
    assert not ice_high.can_unit_enter(HullSize.HUGE)


def test_field_density_scaled_attributes():
    df_low = DebrisField(in_hex=HexCoord(0, 0), in_system="Sol", density=FieldDensity.LOW)
    df_high = DebrisField(in_hex=HexCoord(0, 0), in_system="Sol", density=FieldDensity.HIGH)
    assert df_low.hazard_damage == DEBRIS_FIELD_DENSITY_HAZARD_DAMAGE[FieldDensity.LOW]
    assert df_high.hazard_damage == DEBRIS_FIELD_DENSITY_HAZARD_DAMAGE[FieldDensity.HIGH]
    assert df_high.defense_bonus > df_low.defense_bonus

    ice_low = IceField(in_hex=HexCoord(0, 0), in_system="Sol", density=FieldDensity.LOW)
    ice_high = IceField(in_hex=HexCoord(0, 0), in_system="Sol", density=FieldDensity.HIGH)
    assert ice_high.beam_defense_bonus > ice_low.beam_defense_bonus


def test_is_position_blocked_by_celestial_field():
    system = StarSystem(name="Alpha", position=(0.0, 0.0))
    hex_coord = HexCoord(1, 0)
    system.hexes[hex_coord] = Hex(1, 0, "Alpha")
    
    # High density field at (0, 0)
    field = AsteroidField(in_hex=hex_coord, in_system="Alpha", density=FieldDensity.HIGH)
    field.position = Position(0.0, 0.0)
    system.hexes[hex_coord].celestial_bodies.append(field)

    galaxy = Galaxy()
    galaxy.systems["Alpha"] = system

    # Test small unit inside field -> Allowed
    small_unit = _make_unit("Scout", Position(100.0, 100.0), hex_coord, "Alpha", HullSize.SMALL)
    assert not is_position_blocked_by_celestial_field(galaxy, "Alpha", hex_coord, Position(100.0, 100.0), small_unit)

    # Test huge unit inside field (distance < CELESTIAL_FIELD_RADIUS) -> Blocked
    huge_unit = _make_unit("Titan", Position(100.0, 100.0), hex_coord, "Alpha", HullSize.HUGE)
    assert is_position_blocked_by_celestial_field(galaxy, "Alpha", hex_coord, Position(100.0, 100.0), huge_unit)

    # Test huge unit outside field (distance > ASTEROID_FIELD_RADIUS) -> Allowed
    assert not is_position_blocked_by_celestial_field(galaxy, "Alpha", hex_coord, Position(4000.0, 4000.0), huge_unit)


def test_movement_obstacle_detection():
    from unit_orders.movement import get_hex_collision_obstacles

    system = StarSystem(name="Beta", position=(0.0, 0.0))
    hex_coord = HexCoord(0, 0)
    system.hexes[hex_coord] = Hex(0, 0, "Beta")
    
    # Medium density field
    field = DebrisField(in_hex=hex_coord, in_system="Beta", density=FieldDensity.MEDIUM)
    field.position = Position(200.0, 200.0)
    system.hexes[hex_coord].celestial_bodies.append(field)

    galaxy = Galaxy()
    galaxy.systems["Beta"] = system

    # Small unit can enter -> not an obstacle
    small_unit = _make_unit("Corvette", Position(0.0, 0.0), hex_coord, "Beta", HullSize.SMALL)
    obs_small = get_hex_collision_obstacles(galaxy, "Beta", hex_coord, unit=small_unit)
    assert len(obs_small) == 0

    # Large unit cannot enter -> is an obstacle
    large_unit = _make_unit("Cruiser", Position(0.0, 0.0), hex_coord, "Beta", HullSize.LARGE)
    obs_large = get_hex_collision_obstacles(galaxy, "Beta", hex_coord, unit=large_unit)
    assert len(obs_large) == 1
    assert obs_large[0].center == Position(200.0, 200.0)
    assert obs_large[0].radius == DEBRIS_FIELD_RADIUS


def test_order_rejection_hazard_blocked():
    from unit_orders.movement import ReachWaypointOrder
    from unit_components import Engines

    system = StarSystem(name="Gamma", position=(0.0, 0.0))
    hex_coord = HexCoord(0, 0)
    system.hexes[hex_coord] = Hex(0, 0, "Gamma")

    field = IceField(in_hex=hex_coord, in_system="Gamma", density=FieldDensity.MEDIUM)
    field.position = Position(500.0, 500.0)
    system.hexes[hex_coord].celestial_bodies.append(field)

    galaxy = Galaxy()
    galaxy.systems["Gamma"] = system

    game = MagicMock()
    game.galaxy = galaxy

    battleship = _make_unit("Battleship", Position(0.0, 0.0), hex_coord, "Gamma", HullSize.LARGE, game=game)
    battleship.add_component(Engines(unit=battleship, speed=50.0))

    # Waypoint order into center of field
    order = ReachWaypointOrder(battleship, {
        "destination_system_name": "Gamma",
        "destination_hex_coord": hex_coord,
        "destination_position": Position(500.0, 500.0)
    })
    order.execute(galaxy)
    assert order.status.name == "FAILED"
    assert order.failure_reason == "hazard_blocked"


def test_serialization_and_deserialization():
    from save_manager import serialize_celestial_body, deserialize_celestial_body

    df = DebrisField(in_hex=HexCoord(2, -1), in_system="Delta", density=FieldDensity.HIGH)
    data = serialize_celestial_body(df)
    assert data["density"] == "HIGH"

    restored = deserialize_celestial_body(data, {})
    assert isinstance(restored, DebrisField)
    assert restored.density == FieldDensity.HIGH
    assert restored.max_hull_size == HullSize.SMALL

    # Test backward compatibility when density key is missing
    legacy_data = {
        "class_name": "AsteroidField",
        "in_hex": [0, 0],
        "in_system": "Delta",
        "position": [0.0, 0.0],
        "asteroid_count": 80
    }
    legacy_restored = deserialize_celestial_body(legacy_data, {})
    assert isinstance(legacy_restored, AsteroidField)
    assert legacy_restored.density == FieldDensity.MEDIUM
    assert legacy_restored.max_hull_size == HullSize.MEDIUM


def test_ai_observation_and_command_validation():
    from game_ai.observation import _body_view
    from game_ai.commands import CommandGateway, _Rejected

    field = AsteroidField(in_hex=HexCoord(0, 0), in_system="Sol", density=FieldDensity.HIGH)
    view = _body_view(field, None)
    assert view["density"] == "HIGH"
    assert view["max_hull_size"] == "SMALL"

    # Command preflight rejection
    game = MagicMock()
    galaxy = Galaxy()
    system = StarSystem(name="Sol", position=(0.0, 0.0))
    system.hexes[HexCoord(0, 0)] = Hex(0, 0, "Sol")
    field.position = Position(0.0, 0.0)
    system.hexes[HexCoord(0, 0)].celestial_bodies.append(field)
    galaxy.systems["Sol"] = system
    game.galaxy = galaxy

    gateway = CommandGateway(game)
    large_ship = _make_unit("Dreadnought", Position(2000.0, 0.0), HexCoord(0, 0), "Sol", HullSize.LARGE, game=game)

    cmd = MagicMock()
    cmd.type = "move"
    cmd.system_name = "Sol"
    cmd.hex_coord = HexCoord(0, 0)
    cmd.position = [0.0, 0.0]
    cmd.target_unit_id = None
    cmd.target_body_id = None

    with pytest.raises(_Rejected) as exc_info:
        gateway._validate_unit_command(large_ship, cmd, MagicMock())
    assert exc_info.value.code == "hazard_blocked"


def test_turn_processor_boundary_clamping():
    from turn_processor import TurnProcessor
    from unit_components import Engines, Commander
    from unit_orders.movement import ReachWaypointOrder

    galaxy = Galaxy()
    system = StarSystem(name="Sol", position=(0.0, 0.0))
    hex_coord = HexCoord(0, 0)
    system.hexes[hex_coord] = Hex(0, 0, "Sol")
    
    # High density field at (0, 0), radius = 2000
    field = DebrisField(in_hex=hex_coord, in_system="Sol", density=FieldDensity.HIGH)
    field.position = Position(0.0, 0.0)
    system.hexes[hex_coord].celestial_bodies.append(field)
    galaxy.systems["Sol"] = system

    game = MagicMock()
    game.galaxy = galaxy

    # Large ship at (2050, 0), attempting to move into center (0, 0)
    large_ship = _make_unit("Cruiser", Position(2050.0, 0.0), hex_coord, "Sol", HullSize.LARGE, game=game)
    large_ship.add_component(Engines(unit=large_ship, speed=100.0))
    large_ship.add_component(Commander(unit=large_ship))
    system.hexes[hex_coord].units.append(large_ship)

    from unit_orders import OrderStatus

    order = ReachWaypointOrder(large_ship, {
        "destination_system_name": "Sol",
        "destination_hex_coord": hex_coord,
        "destination_position": Position(-2050.0, 0.0)
    })
    order.status = OrderStatus.IN_PROGRESS
    large_ship.commander_component.current_order = order
    large_ship.engines_component.set_move_target(Position(-2050.0, 0.0), order.order_id)

    tp = TurnProcessor(game)
    tp._process_movement(large_ship.owner)

    # Ship should have halted at boundary (2001.0, 0.0)
    assert large_ship.position.x == pytest.approx(DEBRIS_FIELD_RADIUS + 1.0, abs=1.0)
    assert large_ship.engines_component.move_target is None
    assert order.status == OrderStatus.FAILED
    assert order.failure_reason == "hazard_blocked"


def test_celestial_field_radii_and_zero_inhibition():
    """Verify asteroid, ice, and debris fields have updated radii, 0.0 inhibition, and no static inhibition zones."""
    af = AsteroidField(in_hex=HexCoord(0, 0), in_system="Sol")
    assert af.radius == ASTEROID_FIELD_RADIUS == 3600.0
    assert af.inhibition_field_radius == 0.0

    ice = IceField(in_hex=HexCoord(0, 0), in_system="Sol")
    assert ice.radius == ICE_FIELD_RADIUS == 3600.0
    assert ice.inhibition_field_radius == 0.0

    df = DebrisField(in_hex=HexCoord(0, 0), in_system="Sol")
    assert df.radius == DEBRIS_FIELD_RADIUS == 2000.0
    assert df.inhibition_field_radius == 0.0

    hex_obj = Hex(0, 0, "Sol")
    hex_obj.add_celestial_body(af)
    hex_obj.add_celestial_body(ice)
    hex_obj.add_celestial_body(df)
    hex_obj.update_static_inhibition_zones()
    assert len(hex_obj.static_inhibition_zones) == 0
