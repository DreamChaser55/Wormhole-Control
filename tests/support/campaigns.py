from types import SimpleNamespace
from entities import Player, Unit
from galaxy import Galaxy, StarSystem, Hex
from geometry import Position
from constants import HullSize


def campaign():
    galaxy = Galaxy.__new__(Galaxy)
    galaxy.systems, galaxy.wormholes, galaxy.system_graph = {}, {}, {}
    galaxy.generation_x_min = galaxy.generation_y_min = 0
    galaxy.generation_x_max = galaxy.generation_y_max = 1000
    for name in ("Sol", "Beta"):
        system = StarSystem.__new__(StarSystem)
        system.name, system.position, system.radius = name, Position(10, 20), 1
        system.hexes = {(0, 0): Hex(0, 0, name), (1, 0): Hex(1, 0, name)}
        system.celestial_bodies_by_id = {}
        system.in_galaxy = galaxy
        galaxy.systems[name] = system
    players = [Player("One", (0, 200, 0)), Player("Two", (200, 0, 0))]
    game = SimpleNamespace(galaxy=galaxy, players=players, turn_number=7, current_player_index=0,
        view_mode="sector", current_system_name="Sol", current_sector_coord=(0, 0),
        campaign_id="integrity", conversations={}, message_counter=40, game_started=True,
        selected_objects=[], hovered_object=None, deselect_object=lambda obj: None)
    return game


def ship(game, name="ship", owner=0, sector=(0, 0), system="Sol", hull=HullSize.HUGE):
    unit = Unit(game.players[owner], Position(100, 0), sector, system, name, hull, game)
    game.galaxy.systems[system].hexes[sector].units.append(unit)
    return unit


def legacy_document(version):
    """Historical wire fixtures are intentionally independent of the current writer."""
    order = {"order_type": "MOVE", "status": "PENDING", "parameters": {
        "destination_system_name": "Sol", "destination_hex_coord": [0, 0],
        "destination_position": [200, 100]}, "sub_orders": []}
    if version == "3.2":
        order.update(public_id="0123456789abcdef0123456789abcdef", runtime_state={}, outcome_recorded=False)
    unit = {"id": 10, "owner_id": 0, "name": "Legacy ship", "position": [100, 0],
        "in_system": "Sol", "in_hex": [0, 0], "hull_size": "SMALL", "template_name": None,
        "current_hit_points": 40, "max_hit_points": 50, "damage_reduction": 0.75,
        "is_disabled": True, "disabled_by_unit_ids": [123], "components": {
            "Commander": {}, "AntimatterStorage": {"max_capacity": 60, "current_amount": 15},
            "Engines": {"speed": 37.5, "hull_cost": 1.875}, "Sensors": {"short_range_radius": 567.5, "long_range_hexes": 1}}}
    if version in (None, "3.0"):
        unit["orders"] = [order]
    else:
        unit["commander"] = {"stance": "attack_weapon_range", "current_order": order, "orders_queue": []}
    data = {"game_state": {"turn_number": 8, "current_player_index": 0, "view_mode": "galaxy",
        "current_system_name": "Sol", "current_sector_coord": [0, 0], "object_counter": 500, "player_counter": 20,
        "message_counter": 7, "campaign_id": "legacy-fixture"},
        "players": [{"id": 0, "controller": "human", "name": "Legacy", "color": [0, 100, 200], "credits": 1250}],
        "galaxy": {"systems": [{"name": "Sol", "position": [10, 20], "radius": 1, "hexes": [{
            "q": 0, "r": 0, "in_system": "Sol", "units": [unit], "minefields": [], "celestial_bodies": [
                {"id": 1, "class_name": "Star", "position": [0, 0], "in_system": "Sol", "in_hex": [0, 0]},
                {"id": 2, "class_name": "Nebula", "position": [1000, 0], "in_system": "Sol", "in_hex": [0, 0]},
                {"id": 3, "class_name": "Storm", "position": [-1000, 0], "in_system": "Sol", "in_hex": [0, 0]},
            ]}]}]}, "conversations": []}
    if version is not None:
        data["version"] = version
    return data
