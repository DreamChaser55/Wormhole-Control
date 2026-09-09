from types import SimpleNamespace
from game_ai.commands import CommandGateway
from game_ai.contracts import CommandBatch

from tests.support.combat import create_combat_ship, create_test_galaxy


def world():
    galaxy, player, enemy = create_test_galaxy()
    game = SimpleNamespace(galaxy=galaxy, players=[player, enemy], turn_number=1,
                           sidebar_needs_update=False, visibility_dirty=False, gui=None)
    galaxy.game = game
    unit = create_combat_ship(galaxy, player, "Scout", (0, 0))
    return game, player, enemy, unit


def issue(game, player, *commands):
    return CommandGateway(game).apply_batch(player, CommandBatch(tuple(commands)))


def waypoint(x=500):
    return {"system_name": "Sol", "hex_coord": [0, 0], "position": [x, 0]}
