"""The ordinary, damageable equipment prerequisite for Titan powers."""
from .base import UnitComponent
from titan_balance import CORE_HULL_COST


class TitanComponent(UnitComponent):
    DISPLAY_NAME = 'Titan Core'
    SIDEBAR_ORDER = 13
    STATE_CONFIG = ()
    STATE_RUNTIME = ()
    STATE_REFS = ()

    def __init__(self, unit, hull_cost=CORE_HULL_COST):
        super().__init__(unit, CORE_HULL_COST)

    @staticmethod
    def calc_hull_cost():
        return CORE_HULL_COST

    def validate_state(self):
        from constants import HullSize
        if self.hull_cost != CORE_HULL_COST or self.unit.hull_size != HullSize.TITAN:
            raise ValueError("Titan Core requires Titan hull and canonical 100 hull cost")

    def on_destroyed(self):
        from titan_abilities import reconcile
        if self.unit.in_galaxy:
            reconcile(self.unit.in_galaxy)

    def get_sidebar_data(self, game_state):
        data = super().get_sidebar_data(game_state)
        data.append({'type': 'label', 'text': '100 hull; unlocks equipped Titan powers', 'height': 24})
        if self.unit.owner == game_state.players[game_state.current_player_index]:
            from titan_acquisition import capacity
            state = capacity(game_state.galaxy, self.unit.owner)
            data.append({'type': 'label', 'text': f'Titan capacity: {len(state["owned_unit_ids"])} owned, {len(state["reservations"])} reserved / 1', 'height': 24})
        return data
