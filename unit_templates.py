from entities import HullSize

UNIT_TEMPLATES = {
    "CONSTRUCTOR_MK1": {
        "name": "Constructor Mk.I",
        "hull_size": HullSize.MEDIUM,
        "hull_points": 100,
        "has_engine": True,
        "engine_hull_cost": 10,
        "has_hyperdrive": True,
        "hyperdrive_hull_cost": 20,
        "has_scanner": True,
        "scanner_hull_cost": 5,
        "has_weapon_bays": False,
        "weapon_bays_hull_cost": 0,
        "has_constructor_component": True,
        "constructor_hull_cost": 15,
    },
    "STATION_MK1": {
        "name": "Station Mk.I",
        "hull_size": HullSize.LARGE,
        "hull_points": 500,
        "has_engine": False,
        "engine_hull_cost": 0,
        "has_hyperdrive": False,
        "hyperdrive_hull_cost": 0,
        "has_scanner": True,
        "scanner_hull_cost": 10,
        "has_weapon_bays": True,
        "weapon_bays_hull_cost": 20,
        "has_constructor_component": False,
        "constructor_hull_cost": 0,
    },
}
