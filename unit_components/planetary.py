"""Dedicated troop cargo and siege equipment; boarding Marines remain independent."""
from .base import UnitComponent
from planetary_balance import TROOP_DEFAULT_CAPACITY, TROOP_HULL_COST, SIEGE_HULL_COST, SIEGE_RANGE, SIEGE_DAMAGE, SIEGE_AM_COST


class TroopTransportComponent(UnitComponent):
    DISPLAY_NAME = "Troop Transport"
    SIDEBAR_ORDER = 7
    STATE_CONFIG = ('capacity',)
    STATE_RUNTIME = ('troops',)
    STATE_REFS = ()

    def __init__(self, unit, capacity=TROOP_DEFAULT_CAPACITY, hull_cost=None):
        super().__init__(unit, self.calc_hull_cost(capacity) if hull_cost is None else hull_cost)
        self.capacity = capacity
        self.troops = 0

    @staticmethod
    def calc_hull_cost(capacity=TROOP_DEFAULT_CAPACITY):
        return capacity * TROOP_HULL_COST

    def validate_state(self):
        if type(self.capacity) is not int or self.capacity < 1 or type(self.troops) is not int or not 0 <= self.troops <= self.capacity:
            raise ValueError('Invalid troop capacity or cargo')
        if self.is_destroyed and self.troops:
            raise ValueError('Destroyed transport contains troops')

    def on_destroyed(self):
        self.troops = 0

    def get_sidebar_data(self, game_state):
        from component_visibility import unit_details_are_public_in_game
        data = super().get_sidebar_data(game_state)
        if unit_details_are_public_in_game(self.unit, game_state):
            data.append({'type': 'label', 'text': f'Troops: {self.troops}/{self.capacity}', 'height': 24})
        else:
            data.append({'type': 'label', 'text': f'Troop capacity: {self.capacity}', 'height': 24})
        return data

    def get_basic_sidebar_data(self, game_state):
        return self.get_sidebar_data(game_state)


class SiegeBatteryComponent(UnitComponent):
    STATE_CONFIG = ()
    STATE_RUNTIME = ()
    STATE_REFS = ()
    DISPLAY_NAME = "Siege Battery"
    SIDEBAR_ORDER = 8

    def __init__(self, unit, hull_cost=SIEGE_HULL_COST):
        super().__init__(unit, hull_cost)

    @staticmethod
    def calc_hull_cost():
        return SIEGE_HULL_COST

    def get_sidebar_data(self, game_state):
        return super().get_sidebar_data(game_state) + [
            {'type': 'label', 'text': f'Siege: {SIEGE_DAMAGE:g} defense damage / {SIEGE_AM_COST:g} AM', 'height': 24},
            {'type': 'label', 'text': f'Range: {SIEGE_RANGE:g} from surface; once per owner turn', 'height': 24},
        ]

    def get_basic_sidebar_data(self, game_state):
        return self.get_sidebar_data(game_state)
