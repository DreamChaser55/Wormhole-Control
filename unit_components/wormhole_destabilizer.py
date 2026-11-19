"""Equipment that increases the risk of crossing a wormhole."""

from wormhole_stabilization import DESTABILIZE, DESTABILIZER_HULL_COST, DESTABILIZATION_PENALTY
from .base import UnitComponent
from .wormhole_stabilizer import WormholeSupportMixin


class WormholeDestabilizerComponent(WormholeSupportMixin, UnitComponent):
    DISPLAY_NAME = 'Wormhole Destabilizer'
    STATE_CONFIG = ()
    STATE_RUNTIME = ('last_paid_round', 'last_paid_owner_id')
    HULL_COST = DESTABILIZER_HULL_COST
    SUPPORT_MODE = DESTABILIZE
    EFFECT_SUMMARY = f'−{DESTABILIZATION_PENALTY} stability points in both directions when uncontested'
