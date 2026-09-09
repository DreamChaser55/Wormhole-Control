import pytest
from constants import HullSize, PlanetType
from entities import Planet
from geometry import Position
from game_settings import GameSettings, PlayerConfig, SpawnProfile
from unit_components import Engines, AntimatterStorage

from tests.support.campaigns import campaign, ship


@pytest.fixture
def atmosphere():
    game = campaign()
    giant = Planet((0, 0), 'Sol', PlanetType.GAS_GIANT)
    game.galaxy.systems['Sol'].add_celestial_body(giant)
    unit = ship(game, hull=HullSize.MEDIUM)
    unit.in_galaxy = game.galaxy
    unit.position = Position(800, 0)
    unit.add_component(Engines(unit, speed=200))
    unit.add_component(AntimatterStorage(unit, max_capacity=1000))
    unit.antimatter_component.current_amount = 1000
    return game, giant, unit


def settings_for(galaxy, profile=SpawnProfile.NORMAL):
    from galaxy import StarSystem
    # Campaign setup uses real product bounds; smaller worlds remain engine fixtures.
    for index in range(len(galaxy.systems), 5):
        name = f'Extra{index}'
        galaxy.systems[name] = StarSystem(name, Position(index * 300, 0), radius=3)
        galaxy.systems[name].celestial_bodies_by_id.clear()
        for sector in galaxy.systems[name].hexes.values():
            sector.celestial_bodies.clear()
            sector.update_static_inhibition_zones()
    return GameSettings(num_systems=len(galaxy.systems), pregenerated_galaxy=galaxy,
                        spawn_profile=profile, player_configs=[
        PlayerConfig('One', (0, 200, 0), team_id=1, home_system_name='Sol'),
        PlayerConfig('Two', (200, 0, 0), team_id=2, home_system_name='Beta')])
