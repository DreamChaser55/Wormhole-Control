"""Real entities with small default setups for component and order tests.

Only the game/galaxy collaborators are mocked. Damage, healing, component
lifecycle, diplomacy and XP always execute the production entity methods.
"""
from unittest.mock import MagicMock

from constants import HullSize
from entities import Player, Unit
from geometry import Position
from unit_components import Commander, Sensors


class ComponentPlayer(Player):
    """Player with the resource defaults used by isolated component tests."""

    def __init__(self, name="Test Player", player_id=None, team_id=None):
        super().__init__(name, (255, 0, 0), team_id=team_id)
        if player_id is not None:
            self.id = player_id
            if team_id is None:
                self.team_id = player_id
        self.credits = self.metal = self.crystal = 1000


class ComponentUnit(Unit):
    """Real unit whose surrounding application can be configured by each test."""

    def __init__(self):
        game = MagicMock()
        game.galaxy.systems = {}
        super().__init__(ComponentPlayer(), Position(0, 0), (0, 0), "Sol",
                         "Test Unit", HullSize.MEDIUM, game)
        self.current_hit_points = self.max_hit_points = 100
        # Order tests opt into a commander explicitly, as they do for engines.
        self.remove_component(Commander)
        self.add_component(Sensors(self, short_range_radius=2500.0, long_range_hexes=5))
