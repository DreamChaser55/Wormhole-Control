"""Dedicated equipment for maintaining a wormhole connection."""
from .base import UnitComponent
from wormhole_stabilization import STABILIZER_HULL_COST, STABILIZER_RANGE, STABILIZER_UPKEEP


class WormholeStabilizerComponent(UnitComponent):
    DISPLAY_NAME = 'Wormhole Stabilizer'
    SIDEBAR_ORDER = 5
    STATE_CONFIG = ()
    STATE_RUNTIME = ('last_paid_round', 'last_paid_owner_id')
    STATE_OPTIONAL_TYPES = {'last_paid_owner_id': int}
    STATE_REFS = ()

    def __init__(self, unit, hull_cost=STABILIZER_HULL_COST):
        super().__init__(unit, hull_cost)
        self.last_paid_round = 0
        self.last_paid_owner_id = None

    @staticmethod
    def calc_hull_cost():
        return STABILIZER_HULL_COST

    def validate_state(self):
        if self.last_paid_owner_id is not None and (type(self.last_paid_owner_id) is not int or self.last_paid_owner_id < 0):
            raise ValueError('Invalid stabilizer payer')

    def on_destroyed(self):
        from wormhole_stabilization import interrupt
        interrupt(self.unit)

    def get_sidebar_data(self, game_state):
        from component_visibility import unit_details_are_public_in_game
        from wormhole_stabilization import current_order, state_view
        data = super().get_sidebar_data(game_state)
        data += [{'type': 'label', 'text': f'Range: {STABILIZER_RANGE:g}; upkeep: {STABILIZER_UPKEEP:g} AM/owner turn', 'height': 24},
                 {'type': 'label', 'text': '100% stability for everyone in both directions', 'height': 24}]
        if unit_details_are_public_in_game(self.unit, game_state):
            state = state_view(self.unit)
            data.append({'type': 'label', 'text': state['phase'].replace('_', ' ').title(), 'height': 24})
            order = current_order(self.unit)
            if order:
                from game_ai.rules import body_is_public
                target = game_state.galaxy.wormholes.get(order.parameters['target_id'])
                viewer = game_state.players[game_state.current_player_index]
                if target and body_is_public(game_state, viewer, target):
                    data.append({'type': 'label', 'text': f'Target: {target.name}', 'height': 24})
        return data

    def get_basic_sidebar_data(self, game_state):
        return self.get_sidebar_data(game_state)
