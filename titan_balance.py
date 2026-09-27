"""Canonical Titan economics and strategic-power tuning."""

CORE_HULL_COST = 100.0
ABILITY_HULL_COST = 25.0
UPKEEP_BASE = 50.0
UPKEEP_PER_HULL = 0.1
GATHER_RADIUS = 750.0
ESCORT_CAPACITY = 800.0
AEGIS_RADIUS = 1000.0
LANCE_DAMAGE = 500.0
TITAN_ABILITIES = frozenset({
    'fleet_jump', 'aegis_field', 'siege_lance', 'deep_scan', 'carrier_supremacy',
})


def specifications(spec_type):
    common = ('has_titan_component', 'has_antimatter_storage')
    return {
        'fleet_jump': spec_type('Fleet Jump', common + ('has_engine', 'has_hyperdrive'), 'position', 200, 0, 30,
            description='Jump anywhere in this system with owned ships within 750; at most 800 escort hull. Requires a ready Basic or Advanced Hyperdrive. Preserves formation; replaces passenger orders.'),
        'aegis_field': spec_type('Aegis Field', common + ('has_defenses',), 'self', 150, 1000, 20, 10,
            description='Moving 1,000-radius field halves incoming weapon damage to deployed allies for 10 rounds. Does not protect against mines or hazards.'),
        'siege_lance': spec_type('Siege Lance', common + ('has_weapon_bays', 'has_sensors'), 'unit', 200, 3000, 25, 1,
            description='Hold position and charge a 500-damage beam until the next owner End Turn. Interruptions abort without refund; no ordinary firing while charging.'),
        'deep_scan': spec_type('Deep Scan', common + ('has_sensors',), 'sector', 150, 0, 20, 5,
            description='Continuously observe one hex anywhere in this system with ordinary short-range sensor detail for 5 rounds. Shares with allies; excludes mines, hidden atmospheric craft and private information.'),
        'carrier_supremacy': spec_type('Carrier Supremacy', common + ('has_strikecraft_bay', 'has_sensors'), 'self', 200, 0, 25, 10,
            description='All deployed friendly wings in this sector gain double weapon damage, +50% speed and half incoming weapon damage for 10 rounds. Preserves orders and servicing; no identical stacking.'),
    }

