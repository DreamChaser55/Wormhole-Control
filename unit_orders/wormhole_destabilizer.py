"""Continuous order for destabilizing a wormhole connection."""

from wormhole_stabilization import DESTABILIZE
from .wormhole_stabilizer import WormholeSupportOrder


class DestabilizeWormholeOrder(WormholeSupportOrder):
    support_mode = DESTABILIZE
