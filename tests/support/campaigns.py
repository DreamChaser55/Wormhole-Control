from display_config import DisplayConfig
from types import SimpleNamespace
from domain.players import Player
from domain.units import Unit
from galaxy import Galaxy, StarSystem, Hex
from geometry import Position
from constants import HullSize


def campaign():
    galaxy = Galaxy.__new__(Galaxy)
    galaxy.systems, galaxy.wormholes, galaxy.system_graph = {}, {}, {}
    galaxy.generation_x_min = galaxy.generation_y_min = 0
    galaxy.generation_x_max = galaxy.generation_y_max = 1000
    for name in ("Sol", "Beta"):
        system = StarSystem.__new__(StarSystem)
        system.name, system.position, system.radius = name, Position(10, 20), 1
        system.hexes = {(0, 0): Hex(0, 0, name), (1, 0): Hex(1, 0, name)}
        system.celestial_bodies_by_id = {}
        system.in_galaxy = galaxy
        galaxy.systems[name] = system
    players = [Player("One", (0, 200, 0)), Player("Two", (200, 0, 0))]
    game = SimpleNamespace(galaxy=galaxy, players=players, turn_number=7, current_player_index=0,
        view_mode="sector", current_system_name="Sol", current_sector_coord=(0, 0),
        campaign_id="integrity", conversations={}, message_counter=40, game_started=True,
        selected_objects=[], hovered_object=None, deselect_object=lambda obj: None)
    game.display_config = DisplayConfig()
    game.display_config = DisplayConfig()
    return game


def ship(game, name="ship", owner=0, sector=(0, 0), system="Sol", hull=HullSize.HUGE):
    unit = Unit(game.players[owner], Position(100, 0), sector, system, name, hull, game)
    game.galaxy.systems[system].hexes[sector].units.append(unit)
    return unit
