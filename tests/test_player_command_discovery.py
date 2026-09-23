"""Player command discovery must agree with the shared command contract."""
import pytest

from constants import PlanetType
from domain.celestials import Planet
from game_ai.command_spec import COMMAND_SPECS
from game_ai.observation import build_observation
from tests.support.campaigns import campaign


@pytest.mark.parametrize("condition,legal", [
    ("eligible", True), ("poor", False), ("empty", False),
    ("maximum", False), ("already_upgraded", False), ("no_colony", False),
])
def test_planetary_upgrade_discovery(condition, legal):
    game = campaign()
    player = game.players[0]
    player.credits = 2000
    colony = Planet((0, 0), "Sol", PlanetType.TERRAN)
    colony.owner, colony.population = player, 50
    if condition != "no_colony":
        game.galaxy.systems["Sol"].add_celestial_body(colony)
    if condition == "poor":
        player.credits = 0
    elif condition == "empty":
        colony.population = 0
    elif condition == "maximum":
        colony.fortification_level = 3
    elif condition == "already_upgraded":
        colony.last_defense_upgrade_round = game.turn_number

    commands = build_observation(game, player)["player_commands"]
    expected = sorted(name for name, spec in COMMAND_SPECS.items() if spec.player_level)
    assert commands["supported"] == expected
    assert set(commands["legal"]) <= set(commands["supported"])
    assert set(commands["options"]) <= set(commands["supported"])
    assert "upgrade_planetary_defenses" in commands["supported"]
    assert ("upgrade_planetary_defenses" in commands["legal"]) is legal
    assert {"send_message", "message_developer"} <= set(commands["legal"])
    assert {"sabotage", "relocate_agent"} <= set(commands["supported"])
    assert not {"sabotage", "relocate_agent"} & set(commands["legal"])
