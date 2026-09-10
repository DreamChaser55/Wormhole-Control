"""Central balancing defaults for the six tactical abilities."""
from dataclasses import dataclass


@dataclass(frozen=True)
class TacticalSpec:
    name: str
    equipment: tuple
    target_kind: str
    cost: int
    range: float
    cooldown: int
    duration: int = 0
    cap: int = 0
    description: str = ''


SPECS = {
    'ghost_fleet': TacticalSpec('Ghost Fleet', ('has_sensors',), 'position', 25, 750, 8, cap=1,
        description='Deploy a persistent radar decoy. Visual inspection identifies it. Limit: 1 per deploying ship.'),
    'tractor_tether': TacticalSpec('Tractor Tether', ('has_engine',), 'unit', 20, 400, 6, 3,
        description='Pull a smaller ship 200 units per owner turn for 5 AM; caster speed -50%. Breaks beyond 600. Cancel to release.'),
    'mine_clearing_sweep': TacticalSpec('Mine-Clearing Sweep', ('has_sensors', 'has_minelayer_component'), 'position', 25, 1000, 4,
        description='Remove 3 mines across revealed enemy fields along a 200-wide sweep. Remaining fields are still hazardous.'),
    'guardian_link': TacticalSpec('Guardian Link', ('has_defenses',), 'unit', 25, 450, 7, 3,
        description='Redirect 30% of weapon damage (cap 20/hit), reducing the redirected share by 25% before guardian defenses.'),
    'fuel_cache': TacticalSpec('Fuel Cache', ('has_antimatter_storage',), 'position', 55, 250, 4, cap=3,
        description='Store 50 AM in a persistent pod for 5 AM overhead. Explicit recovery; enemies can steal it. Limit: 3 per ship.'),
    'nebula_catalyst': TacticalSpec('Nebula Catalyst', ('has_sensors', 'has_antimatter_harvester'), 'celestial_position', 30, 750, 7, 3, cap=1,
        description='Catalyze a 600-radius nebula patch: hydrogen/nitrogen benefit allies; oxygen/dust hinder enemies. Baseline effects remain.'),
}
EQUIPMENT = {'has_sensors': 'sensors_component', 'has_engine': 'engines_component',
             'has_defenses': 'defenses_component', 'has_antimatter_storage': 'antimatter_component',
             'has_antimatter_harvester': 'harvester_component', 'has_minelayer_component': 'minelayer_component'}
TRACTOR_PULL = 200.0
TRACTOR_STANDOFF = 150.0
TRACTOR_BREAK = 600.0
TRACTOR_COST = 5
TRACTOR_SPEED = 0.5
SWEEP_RADIUS = 100.0
SWEEP_MINES = 3
GUARDIAN_FRACTION = 0.30
GUARDIAN_CAP = 20
GUARDIAN_RETAINED = 0.75
RECOVERY_RANGE = 150.0

DEPLOYABLE_HP = 20
CACHE_FUEL = 50
CACHE_OVERHEAD = 5
CATALYST_RADIUS = 600.0
CATALYST_HYDROGEN_FUEL = 0.25
CATALYST_NITROGEN_COOLING = 2
CATALYST_OXYGEN_SPLASH = 1.35
CATALYST_DUST_SENSORS = 0.5
