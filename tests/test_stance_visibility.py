import pytest
from unittest.mock import MagicMock
from geometry import Position, distance
from entities import Player, Unit, Planet
from galaxy import Galaxy, StarSystem, Hex
from unit_components import (
    Commander, UnitStance, Weapons, Turret, TurretType, TurretVariant,
    Engines, Hyperdrive, HyperdriveType, Sensors, CloakingDevice
)
from unit_components.enums import CloakingType
from unit_orders import OrderStatus, AttackOrder
from visibility import VisibilityService, is_unit_visible, hex_has_presence


def create_test_galaxy():
    """Build a standard two-player galaxy with system 'Sol' and multiple hex sectors."""
    galaxy = Galaxy()
    p1 = Player(name="Player 1", color=(255, 0, 0), team_id=1)
    p2 = Player(name="Player 2", color=(0, 0, 255), team_id=2)
    galaxy.game = MagicMock()
    galaxy.game.galaxy = galaxy
    galaxy.game.turn_number = 1

    sol = StarSystem(name="Sol", position=Position(0, 0), radius=3)
    sol.in_galaxy = galaxy

    # Create hex sectors: (0, 0), (0, 1), (0, 2), (0, 3)
    for q, r in [(0, 0), (0, 1), (0, 2), (0, 3)]:
        hex_coord = (q, r)
        hex_obj = Hex(q=q, r=r, in_system="Sol")
        sol.hexes[hex_coord] = hex_obj

    galaxy.systems["Sol"] = sol
    return galaxy, p1, p2


from constants import HullSize

def create_combat_ship(galaxy, player, name, hex_coord, pos=(0, 0), short_range=2500.0, long_range=0):
    """Helper to assemble a combat vessel with engines, hyperdrive, weapons, sensors, and commander."""
    unit = Unit(
        owner=player,
        position=Position(pos[0], pos[1]),
        in_hex=hex_coord,
        in_system="Sol",
        name=name,
        hull_size=HullSize.MEDIUM,
        game=galaxy.game
    )

    # Weapons
    weapons = Weapons(unit)
    turret = Turret(
        turret_type=TurretType.MASS_DRIVER,
        variant=TurretVariant.STANDARD,
        damage=20,
        range=300.0,
        cooldown=1,
        parent_unit=unit
    )
    weapons.add_turret(turret)
    unit.add_component(weapons)

    # Engines & Hyperdrive
    unit.add_component(Engines(unit, speed=100.0))
    unit.add_component(Hyperdrive(unit, drive_type=HyperdriveType.BASIC, jump_range=3))

    # Sensors
    unit.add_component(Sensors(unit, short_range_radius=short_range, long_range_hexes=long_range))

    # Commander
    commander = Commander(unit)
    unit.add_component(commander)

    # Place in galaxy
    system = galaxy.systems["Sol"]
    hex_obj = system.hexes[hex_coord]
    hex_obj.units.append(unit)
    return unit


def test_stance_does_not_target_enemy_in_fog_of_war():
    """Unit set to ATTACK_SAME_SYSTEM must ignore enemies in unobserved sectors."""
    galaxy, p1, p2 = create_test_galaxy()

    # P1 friendly ship in (0, 0) with short-range sensors only (0 long range)
    p1_ship = create_combat_ship(galaxy, p1, "P1 Cruiser", (0, 0), pos=(0, 0), short_range=1000.0, long_range=0)
    p1_ship.commander_component.stance = UnitStance.ATTACK_SAME_SYSTEM

    # P2 enemy ship in (0, 2) - completely hidden in fog of war
    p2_enemy = create_combat_ship(galaxy, p2, "P2 Scout", (0, 2), pos=(0, 0), short_range=500.0, long_range=0)

    # P1 calculates visibility
    snap = VisibilityService.compute(galaxy, p1)
    assert is_unit_visible(snap, p2_enemy) is False

    # Process stance
    p1_ship.commander_component.update()

    # P1 must NOT acquire target or create attack order
    assert p1_ship.commander_component.current_order is None
    assert p1_ship.weapons_component.turrets[0].target is None


def test_stance_long_range_presence_alone_does_not_grant_targeting():
    """Long-range sensor presence reveals a hex is occupied, but does NOT allow stance target lock."""
    galaxy, p1, p2 = create_test_galaxy()

    # P1 ship has long_range_hexes=2 (covers (0, 1)), but short_range_radius is local to (0, 0)
    p1_ship = create_combat_ship(galaxy, p1, "P1 Sensor Cruiser", (0, 0), pos=(0, 0), short_range=1000.0, long_range=2)
    p1_ship.commander_component.stance = UnitStance.ATTACK_INTRA_SYSTEM_JUMP_RANGE

    # P2 enemy ship in (0, 1) - covered by long-range radar
    p2_enemy = create_combat_ship(galaxy, p2, "P2 Raider", (0, 1), pos=(0, 0), short_range=500.0, long_range=0)

    snap = VisibilityService.compute(galaxy, p1)
    # Long range gives presence in (0, 1), but detailed unit is not visible
    assert hex_has_presence(snap, "Sol", (0, 1)) is True
    assert is_unit_visible(snap, p2_enemy) is False

    # Process stance
    p1_ship.commander_component.update()

    # Stance must not target the enemy since it lacks detailed visibility
    assert p1_ship.commander_component.current_order is None


def test_stance_targets_visible_enemy_in_short_range_and_different_sector_with_scout():
    """When an enemy is genuinely visible (detailed) via a friendly scout, ATTACK_INTRA_SYSTEM_JUMP_RANGE acquires it."""
    galaxy, p1, p2 = create_test_galaxy()

    p1_ship = create_combat_ship(galaxy, p1, "P1 Battleship", (0, 0), pos=(0, 0), short_range=1000.0, long_range=0)
    p1_ship.commander_component.stance = UnitStance.ATTACK_INTRA_SYSTEM_JUMP_RANGE

    # P1 also has a scout in (0, 1) granting short-range visibility in (0, 1)
    p1_scout = create_combat_ship(galaxy, p1, "P1 Scout", (0, 1), pos=(0, 0), short_range=1000.0, long_range=0)

    # P2 enemy in (0, 1) close to P1 scout
    p2_enemy = create_combat_ship(galaxy, p2, "P2 Frigate", (0, 1), pos=(50, 50), short_range=500.0, long_range=0)

    snap = VisibilityService.compute(galaxy, p1)
    assert is_unit_visible(snap, p2_enemy) is True

    # Process stance
    p1_ship.commander_component.update()

    # P1 battleship should acquire an AttackOrder targeting p2_enemy
    assert p1_ship.commander_component.current_order is not None
    assert getattr(p1_ship.commander_component.current_order, 'is_stance_order', False) is True
    assert p1_ship.commander_component.current_order.parameters["target_unit_id"] == p2_enemy.id


def test_stance_ignores_cloaked_enemy_outside_visual_radius():
    """Cloaked enemies in same sector hex outside short-range visual circles are ignored."""
    galaxy, p1, p2 = create_test_galaxy()

    # P1 ship at (0, 0) with short-range sensor radius 500
    p1_ship = create_combat_ship(galaxy, p1, "P1 Guard", (0, 0), pos=(0, 0), short_range=500.0, long_range=2)
    p1_ship.commander_component.stance = UnitStance.ATTACK_SAME_SECTOR

    # P2 enemy at (0, 0), position (800, 0) with active cloak
    p2_stealth = create_combat_ship(galaxy, p2, "P2 Stealth", (0, 0), pos=(800, 0), short_range=500.0, long_range=0)
    cloak = CloakingDevice(p2_stealth, device_type=CloakingType.BASIC)
    cloak.is_active = True
    p2_stealth.add_component(cloak)

    snap = VisibilityService.compute(galaxy, p1)
    assert is_unit_visible(snap, p2_stealth) is False

    p1_ship.commander_component.update()
    assert p1_ship.commander_component.current_order is None


def test_stance_targets_cloaked_enemy_inside_short_range_visual_circle():
    """Cloaking does NOT defeat short-range visual circles; cloaked enemies within visual radius are targeted."""
    galaxy, p1, p2 = create_test_galaxy()

    # P1 ship at (0, 0) with short-range sensor radius 500
    p1_ship = create_combat_ship(galaxy, p1, "P1 Guard", (0, 0), pos=(0, 0), short_range=500.0, long_range=0)
    p1_ship.commander_component.stance = UnitStance.ATTACK_WEAPON_RANGE

    # P2 enemy at (0, 0), position (150, 0) - within 500 visual radius and within 300 weapon range
    p2_stealth = create_combat_ship(galaxy, p2, "P2 Stealth", (0, 0), pos=(150, 0), short_range=500.0, long_range=0)
    cloak = CloakingDevice(p2_stealth, device_type=CloakingType.BASIC)
    cloak.is_active = True
    p2_stealth.add_component(cloak)

    snap = VisibilityService.compute(galaxy, p1)
    assert is_unit_visible(snap, p2_stealth) is True

    p1_ship.commander_component.update()
    assert p1_ship.weapons_component.turrets[0].target == p2_stealth


def test_stance_order_cancelled_when_target_slips_into_fog_of_war():
    """If a stance-directed attack order is pursuing an enemy and visibility is lost, the order auto-cancels."""
    galaxy, p1, p2 = create_test_galaxy()

    p1_ship = create_combat_ship(galaxy, p1, "P1 Interceptor", (0, 0), pos=(0, 0), short_range=1000.0, long_range=0)
    p1_ship.commander_component.stance = UnitStance.ATTACK_SAME_SYSTEM

    # P1 scout providing vision in (0, 1)
    p1_scout = create_combat_ship(galaxy, p1, "P1 Scout", (0, 1), pos=(0, 0), short_range=1000.0, long_range=0)

    # P2 enemy in (0, 1)
    p2_enemy = create_combat_ship(galaxy, p2, "P2 Runner", (0, 1), pos=(0, 0), short_range=500.0, long_range=0)

    # Initial update creates stance order
    p1_ship.commander_component.update()
    assert p1_ship.commander_component.current_order is not None
    assert getattr(p1_ship.commander_component.current_order, 'is_stance_order', False) is True

    # Scout gets destroyed or moves away, leaving (0, 1) in Fog of War
    galaxy.systems["Sol"].hexes[(0, 1)].units.remove(p1_scout)

    # Next update should detect target is no longer visible and cancel the stance order
    p1_ship.commander_component.update()
    assert p1_ship.commander_component.current_order is None


def test_weapons_update_clears_target_if_visibility_is_lost():
    """Weapons.update() verifies target visibility and clears the target if it enters fog of war."""
    galaxy, p1, p2 = create_test_galaxy()

    p1_ship = create_combat_ship(galaxy, p1, "P1 Gunboat", (0, 0), pos=(0, 0), short_range=1000.0, long_range=0)
    p2_enemy = create_combat_ship(galaxy, p2, "P2 Target", (0, 0), pos=(100, 0), short_range=500.0, long_range=0)

    # Lock target
    p1_ship.commander_component.add_order(
        AttackOrder(p1_ship, {"target_unit_id": p2_enemy.id})
    )
    assert p1_ship.weapons_component.turrets[0].target == p2_enemy

    # Disable / destroy P1 sensors so P1 loses all visibility
    p1_ship.sensors_component.short_range_radius = 0.0

    # Weapons update should clear invisible target
    p1_ship.weapons_component.update(galaxy)
    assert p1_ship.weapons_component.turrets[0].target is None
    assert p2_enemy.current_hit_points == p2_enemy.max_hit_points  # Did not fire


def test_stance_infiltrated_target_visible():
    """If an enemy unit in another sector is infiltrated by an agent, ATTACK_SAME_SYSTEM acquires it."""
    from unit_components.intelligence import Agent
    galaxy, p1, p2 = create_test_galaxy()

    p1_ship = create_combat_ship(galaxy, p1, "P1 Hunter", (0, 0), pos=(0, 0), short_range=1000.0, long_range=0)
    p1_ship.commander_component.stance = UnitStance.ATTACK_SAME_SYSTEM

    # P2 enemy in (0, 2) is infiltrated by P1's agent
    p2_enemy = create_combat_ship(galaxy, p2, "P2 Infiltrated", (0, 2), pos=(0, 0), short_range=500.0, long_range=0)
    agent = Agent(owner=p1, source_unit_id=p1_ship.id, target_type="UNIT", target_id=p2_enemy.id)
    p2_enemy.infiltrating_agents.append(agent)

    snap = VisibilityService.compute(galaxy, p1)
    assert is_unit_visible(snap, p2_enemy) is True

    p1_ship.commander_component.update()
    assert p1_ship.commander_component.current_order is not None
    assert getattr(p1_ship.commander_component.current_order, 'is_stance_order', False) is True
    assert p1_ship.commander_component.current_order.parameters["target_unit_id"] == p2_enemy.id


def test_patrol_order_respects_visibility():
    """Patrolling unit will only attack enemies that are visible under sensor visibility rules."""
    from unit_orders import PatrolOrder
    galaxy, p1, p2 = create_test_galaxy()

    p1_ship = create_combat_ship(galaxy, p1, "P1 Patrol", (0, 0), pos=(0, 0), short_range=500.0, long_range=0)
    # Cloaked enemy at distance 800 (outside 500 sensor radius)
    p2_enemy = create_combat_ship(galaxy, p2, "P2 Stealth", (0, 0), pos=(800, 0), short_range=500.0, long_range=0)
    cloak = CloakingDevice(p2_enemy, device_type=CloakingType.BASIC)
    cloak.is_active = True
    p2_enemy.add_component(cloak)

    patrol_params = {
        "waypoints": [{"system_name": "Sol", "hex_coord": (0, 0), "position": Position(0, 0)}]
    }
    patrol_order = PatrolOrder(p1_ship, patrol_params)
    p1_ship.commander_component.add_order(patrol_order)

    # Update patrol order
    p1_ship.commander_component.update()

    # Should not find hidden enemy as closest enemy
    assert patrol_order._find_nearby_enemy(galaxy) is None


def test_protect_order_respects_visibility():
    """Protecting unit will only intercept enemies that are visible under sensor visibility rules."""
    from unit_orders import ProtectOrder
    galaxy, p1, p2 = create_test_galaxy()

    p1_vip = create_combat_ship(galaxy, p1, "P1 VIP", (0, 0), pos=(0, 0), short_range=500.0, long_range=0)
    p1_guard = create_combat_ship(galaxy, p1, "P1 Guard", (0, 0), pos=(10, 0), short_range=500.0, long_range=0)

    # Cloaked enemy at distance 800 (outside 500 sensor radius)
    p2_enemy = create_combat_ship(galaxy, p2, "P2 Stealth", (0, 0), pos=(800, 0), short_range=500.0, long_range=0)
    cloak = CloakingDevice(p2_enemy, device_type=CloakingType.BASIC)
    cloak.is_active = True
    p2_enemy.add_component(cloak)

    protect_params = {"target_unit_id": p1_vip.id}
    protect_order = ProtectOrder(p1_guard, protect_params)
    p1_guard.commander_component.add_order(protect_order)

    # Update protect order
    p1_guard.commander_component.update()

    assert protect_order._find_nearby_enemy(galaxy, p1_vip) is None
