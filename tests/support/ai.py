from types import SimpleNamespace

EMPTY_PATCH = {
    "strategy": None,
    "objectives": None,
    "commitments": None,
    "beliefs": None,
    "lessons": None,
    "misc": None,
}


class _Player:
    def __init__(self, player_id, team_id):
        self.id = player_id
        self.name = f"P{player_id}"
        self.team_id = team_id
        self.credits = self.metal = self.crystal = 10

    def is_allied_with(self, other):
        return other is not None and self.team_id == other.team_id


class _Commander:
    def __init__(self):
        self.current_order = None
        self.orders_queue = []
        self.stance = SimpleNamespace(value="do_nothing")
        self.clear_count = 0

    def clear_orders(self):
        self.clear_count += 1
        self.current_order = None
        self.orders_queue.clear()

    def add_order(self, order):
        self.orders_queue.append(order)

    def get_allowed_stances(self):
        return []


def _unit(unit_id, owner):
    return SimpleNamespace(
        id=unit_id,
        name=f"U{unit_id}",
        owner=owner,
        in_system="Sol",
        in_hex=(0, 0),
        position=SimpleNamespace(x=0, y=0),
        hull_size=SimpleNamespace(value="small"),
        current_hit_points=10,
        max_hit_points=10,
        is_disabled=False,
        components={},
        antimatter_component=None,
        commander_component=_Commander(),
        engines_component=None,
        weapons_component=None,
        colony_component=None,
        constructor_component=None,
        repair_component=None,
        mining_component=None,
        harvester_component=None,
        hangar_component=None,
        strikecraft_bay_component=None,
        trade_component=None,
        inhibitor_component=None,
        cloaking_component=None,
        ability_component=None,
    )
