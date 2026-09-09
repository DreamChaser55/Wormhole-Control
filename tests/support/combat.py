from unittest.mock import MagicMock
from geometry import Position
from domain.players import Player
from domain.units import Unit
from galaxy import Galaxy, StarSystem, Hex
from unit_components.commander import Commander
from unit_components.weapons import Weapons, Turret
from unit_components.enums import TurretType, TurretVariant, HyperdriveType
from unit_components.movement import Engines, Hyperdrive
from unit_components.sensors import Sensors
from constants import HullSize


def create_test_galaxy():
    """Build a standard two-player galaxy with system 'Sol' and multiple hex sectors."""
    galaxy = Galaxy(num_systems=0)
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
