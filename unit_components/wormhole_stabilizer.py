"""Dedicated equipment for maintaining a wormhole connection."""
from .base import UnitComponent
from wormhole_stabilization import STABILIZE, STABILIZER_HULL_COST, SUPPORT_RANGE, SUPPORT_UPKEEP


class WormholeSupportMixin:
    """Share payment and presentation behavior between wormhole components."""

    SIDEBAR_ORDER = 5
    STATE_OPTIONAL_TYPES = {'last_paid_owner_id': int}

    def __init__(self, unit, hull_cost=None):
        super().__init__(unit, self.HULL_COST if hull_cost is None else hull_cost)
        self.last_paid_round = 0
        self.last_paid_owner_id = None

    @classmethod
    def calc_hull_cost(cls):
        return cls.HULL_COST

    def validate_state(self):
        payer = self.last_paid_owner_id
        if payer is not None and (type(payer) is not int or payer < 0):
            raise ValueError('Invalid wormhole support payer')

    def on_destroyed(self):
        from wormhole_stabilization import interrupt
        interrupt(self.unit, mode=self.SUPPORT_MODE)

    def _support_rows(self, game_state):
        from component_visibility import unit_details_are_public_in_game
        from wormhole_stabilization import current_order, state_view
        data = [{'type': 'label', 'text': f'{SUPPORT_RANGE:g} range · {SUPPORT_UPKEEP:g} AM per owner turn', 'height': 24},
                {'type': 'label', 'text': self.EFFECT_SUMMARY, 'height': 24}]
        if unit_details_are_public_in_game(self.unit, game_state):
            state = state_view(self.unit, mode=self.SUPPORT_MODE)
            data.append({'type': 'label', 'text': state['phase'].replace('_', ' ').title(), 'height': 24})
            order = current_order(self.unit, self.SUPPORT_MODE)
            if order:
                from game_ai.rules import body_is_public
                target = game_state.galaxy.wormholes.get(order.parameters['target_id'])
                viewer = game_state.players[game_state.current_player_index]
                if target and body_is_public(game_state, viewer, target):
                    data.append({'type': 'label', 'text': f'Target: {target.name}', 'height': 24})
        return data

    def get_sidebar_data(self, game_state):
        return super().get_sidebar_data(game_state) + self._support_rows(game_state)

    def get_basic_sidebar_data(self, game_state):
        return [self._basic_sidebar_health_row(), *self._support_rows(game_state)]


class WormholeStabilizerComponent(WormholeSupportMixin, UnitComponent):
    DISPLAY_NAME = 'Wormhole Stabilizer'
    STATE_CONFIG = ()
    STATE_RUNTIME = ('last_paid_round', 'last_paid_owner_id')
    HULL_COST = STABILIZER_HULL_COST
    SUPPORT_MODE = STABILIZE
    EFFECT_SUMMARY = '100% stability in both directions when uncontested'
