"""Deterministic, recipient-scoped turn briefings. No GUI or provider dependencies.

Only committed gameplay calls the recorder. Observations read a frozen report;
they never advance collection windows or discover events.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import copy
import json
import math

MAX_ENTRIES = 128
MAX_CHARACTERS = 32_000
PRIORITY = {"friendly_and_allied_losses": 0, "enemy_losses": 1, "loss": 0,
            "capture": 1, "problem": 2, "combat": 3, "hazard": 3,
            "intelligence": 4, "development": 5, "discovery": 6, "communications": 7}
METRICS = ("credits", "metal", "crystal", "population")
FUEL_PROBLEMS = frozenset(f'{action} blocked: {reason}'
    for action in ('Movement', 'Jump')
    for reason in ('antimatter storage unavailable', 'insufficient antimatter', 'antimatter payment failed'))


@dataclass(frozen=True)
class BriefingEntry:
    event_id: int
    turn: int
    category: str
    subject_id: int | None
    name: str
    system_name: str
    hex_coord: tuple[int, int] | None
    detail: str
    count: int = 1
    amount: float = 0
    owner_id: int | None = None
    owner_name: str = ''

    def to_dict(self):
        return {**asdict(self), "hex_coord": list(self.hex_coord) if self.hex_coord is not None else None}


@dataclass(frozen=True)
class TurnSummary:
    from_turn: int = 0
    to_turn: int = 0
    entries: tuple[BriefingEntry, ...] = ()
    economy: tuple[tuple[str, float], ...] = tuple((key, 0.0) for key in METRICS)
    omitted_count: int = 0

    def to_dict(self):
        return {"from_turn": self.from_turn, "to_turn": self.to_turn,
                "entries": [entry.to_dict() for entry in self.entries],
                "economy": dict(self.economy), "omitted_count": self.omitted_count}


@dataclass
class BriefingState:
    initialized: bool = False
    collecting: bool = False
    from_turn: int = 0
    sequence: int = 0
    pending: list[BriefingEntry] = field(default_factory=list)
    omitted_count: int = 0
    baseline: dict[str, float] = field(default_factory=lambda: dict.fromkeys(METRICS, 0.0))
    seen: dict[str, list[str]] = field(default_factory=dict)
    current: TurnSummary = field(default_factory=TurnSummary)
    acknowledged: bool = True
    fuel_waits: dict[str, str] = field(default_factory=dict)
    busy_unit_ids: list[int] = field(default_factory=list)

    def to_dict(self):
        result = asdict(self)
        result["pending"] = [entry.to_dict() for entry in self.pending]
        result["current"] = self.current.to_dict()
        return result


def _state(player):
    value = getattr(player, "briefing", None)
    return value if isinstance(value, BriefingState) else None


def clear_movement_fuel_wait(unit):
    """Clear any tracked movement fuel wait silently when an order ends or is replaced."""
    if unit is None or not _live(_game(unit)):
        return
    state = _state(getattr(unit, "owner", None))
    if state is not None:
        state.fuel_waits.pop(str(unit.id), None)


def movement_fuel_state(unit, problem=None):
    """Report entry/change/recovery, keeping unchanged waits quiet across windows."""
    if not _live(_game(unit)):
        return
    state = _state(unit.owner)
    if state is None:
        return
    key = str(unit.id)
    previous = state.fuel_waits.get(key)
    if problem == previous:
        return
    if problem is None:
        state.fuel_waits.pop(key, None)
        if previous is not None:
            unit_event(unit, 'development', 'Movement resumed after fuel wait', private=True, once=True)
    elif problem in FUEL_PROBLEMS:
        state.fuel_waits[key] = problem
        while len(state.fuel_waits) > MAX_ENTRIES:
            state.fuel_waits.pop(next(iter(state.fuel_waits)))
        unit_event(unit, 'problem', problem, private=True, once=True)


def _live(game):
    return game is not None and getattr(game, "_loading", False) is not True


def _game(obj):
    return getattr(obj, "game", None) or getattr(getattr(obj, "in_galaxy", None), "game", None)


def _visible(snapshot, obj):
    from domain.deployables import Deployable
    from visibility import is_unit_visible
    if isinstance(obj, Deployable):
        return snapshot.viewer.is_allied_with(obj.owner) or obj.id in snapshot.visible_deployable_ids
    return is_unit_visible(snapshot, obj)


def _size(entries):
    return len(json.dumps([e.to_dict() for e in entries], ensure_ascii=False))


def _bound(state):
    # Reserve room for the report envelope and economic recap too.
    while len(state.pending) > MAX_ENTRIES or _size(state.pending) > MAX_CHARACTERS - 1024:
        index = max(range(len(state.pending)), key=lambda i: (PRIORITY[state.pending[i].category], -state.pending[i].event_id))
        state.omitted_count += state.pending.pop(index).count


def record(game, player, category, detail, *, subject=None, subject_id=None,
           name="", system_name="", hex_coord=None, amount=0, once=False, unit_owner=None,
           during_planning=False):
    state = _state(player)
    if not _live(game) or state is None or not (state.collecting or during_planning and state.initialized):
        return
    if subject is not None:
        subject_id, name = subject.id, str(subject.name)
        system_name = str(getattr(subject, "in_system", "") or "")
        hex_coord = getattr(subject, "in_hex", None)
    entry = BriefingEntry(state.sequence + 1, int(game.turn_number), category,
                          subject_id, name[:200], system_name[:200],
                          tuple(hex_coord) if hex_coord is not None else None,
                          detail[:500], amount=float(amount),
                          owner_id=unit_owner.id if unit_owner else None,
                          owner_name=str(unit_owner.name)[:200] if unit_owner else '')
    # Outcome history reports ownership/destruction interruptions separately.
    # Those are omitted by order_outcome so a loss has just one primary notice.
    key = lambda e: (e.category, e.subject_id, e.name, e.system_name, e.hex_coord, e.detail, e.owner_id, e.owner_name)
    for index, old in enumerate(state.pending):
        if key(old) == key(entry):
            if not once:
                state.pending[index] = replace(old, count=old.count + 1, amount=old.amount + entry.amount)
            _bound(state)
            return
    state.sequence += 1
    state.pending.append(entry)
    _bound(state)


def snapshot_unit_observers(unit, *, actor=None):
    """Capture visible observers before combat damage/destruction mutates sensors."""
    from visibility import VisibilityService
    game = _game(unit)
    if not _live(game):
        return ()
    observers = []
    for player in getattr(game, "players", ()):
        state = _state(player)
        if state is None or not state.collecting:
            continue
        snapshot = VisibilityService.compute(game.galaxy, player, record_intel=False)
        if not _visible(snapshot, unit):
            continue
        actor_visible = bool(actor is not None and _visible(snapshot, actor))
        observers.append((player, actor_visible))
    return tuple(observers)


def record_observed_unit_event(unit, category, detail, observers, *, amount=0, actor=None, once=False):
    """Record a briefing event using pre-mutation observer visibility snapshots."""
    game = _game(unit)
    if not _live(game) or not observers:
        return
    owner = unit.owner if category in {'combat', 'hazard', 'loss', 'capture'} else None
    for player, actor_visible in observers:
        public_detail = detail
        if actor is not None:
            if actor_visible:
                actor_owner = getattr(actor, "owner", None)
                actor_label = f"{actor.name} ({actor_owner.name})" if actor_owner else actor.name
                public_detail += f" by {actor_label}"
            else:
                public_detail += " by an unknown attacker"
        record(game, player, category, public_detail, subject=unit, amount=amount, once=once,
               unit_owner=owner)


def unit_event(unit, category, detail, *, amount=0, private=False, allies_only=False, component_type=None, actor=None, once=False, new_owner=None):
    """Snapshot disclosure before mutation; never look up a historical target later."""
    from visibility import VisibilityService
    from component_visibility import component_is_public
    game = _game(unit)
    if not _live(game):
        return
    for player in getattr(game, "players", ()):
        state = _state(player)
        if state is None or not state.collecting:
            continue
        if private and player is not unit.owner:
            continue
        if allies_only and player.is_enemy_of(unit.owner):
            continue
        snapshot = VisibilityService.compute(game.galaxy, player, record_intel=False)
        if not _visible(snapshot, unit):
            continue
        if component_type and not component_is_public(component_type, enemy=player.is_enemy_of(unit.owner)):
            continue
        public_detail = detail
        if new_owner is not None:
            if player is unit.owner:
                public_detail = "Captured; ownership lost"
            elif player is new_owner:
                public_detail = "Captured; ownership gained"
        if actor is not None:
            if _visible(snapshot, actor):
                actor_owner = getattr(actor, "owner", None)
                actor_label = f"{actor.name} ({actor_owner.name})" if actor_owner else actor.name
                public_detail += f" by {actor_label}"
            else:
                public_detail += " by an unknown attacker"
        public_category = category
        if category == "loss":
            public_category = "enemy_losses" if player.is_enemy_of(unit.owner) else "friendly_and_allied_losses"
        owner = unit.owner if category in {'combat', 'hazard', 'loss', 'capture'} else None
        record(game, player, public_category, public_detail, subject=unit, amount=amount, once=once,
               unit_owner=owner)


def order_outcome(order, outcome, reason, *, jump_fuel_failure=None):
    player = getattr(order, "_issuing_player", None)
    if player is None or reason in {"unit_destroyed", "ownership_lost"}:
        return
    if outcome == "failed" or (outcome == "cancelled" and reason != "cancelled"):
        detail = f"{order.order_type.name.replace('_', ' ').title()} {outcome}: {reason.replace('_', ' ')}"
        if jump_fuel_failure:
            detail += (f" (jump requires {jump_fuel_failure['required_antimatter']:g} AM, "
                       f"short by {jump_fuel_failure['shortfall_antimatter']:g} AM)")
        record(_game(order.unit), player, "problem", detail, subject=order.unit)
    elif outcome == "completed" and order.order_type.name in {
        "INFILTRATE_UNIT", "INFILTRATE_PLANET", "RELOCATE_AGENT", "SABOTAGE",
        "ELIMINATE_AGENT", "EXTRACT_AGENT",
    }:
        record(_game(order.unit), player, "intelligence",
               f"{order.order_type.name.replace('_', ' ').title()} completed", subject=order.unit)


def economy_snapshot(game, player):
    result = {key: float(getattr(player, key, 0)) for key in METRICS[:3]}
    from economy import total_population
    result["population"] = total_population(getattr(game, "galaxy", None), player)
    return result


def _owned_colony_sectors(game, player):
    from planetary_intel import is_colony_body
    galaxy = getattr(game, "galaxy", None)
    if galaxy is None:
        return set()
    return {
        (system_name, coord)
        for system_name, system in galaxy.systems.items()
        for coord, sector in system.hexes.items()
        if any(is_colony_body(body) and body.owner is player for body in sector.celestial_bodies)
    }


def _starting_known_sector_keys(game, player):
    from domain.players import are_allies
    from planetary_intel import is_colony_body
    galaxy = getattr(game, "galaxy", None)
    if galaxy is None:
        return set()
    keys = set()
    for system_name, system in galaxy.systems.items():
        for coord, sector in system.hexes.items():
            if any(are_allies(getattr(unit, "owner", None), player) and unit.current_hit_points > 0
                   for unit in sector.units) or any(
                is_colony_body(body) and are_allies(getattr(body, "owner", None), player)
                for body in sector.celestial_bodies
            ):
                keys.add(f"sector:{system_name}:{coord[0]}:{coord[1]}")
    return keys


def _discoveries(game, player):
    from visibility import VisibilityService, is_minefield_visible
    from game_ai.intelligence import discovered_enemy_agent_hosts
    snapshot = VisibilityService.compute(game.galaxy, player, turn_number=game.turn_number)
    found = {}
    for unit_id in sorted(snapshot.visible_enemy_unit_ids):
        unit = game.galaxy.get_unit_by_id(unit_id)
        if unit is not None:
            found[f"unit:{unit_id}"] = ("discovery", "New enemy contact", unit, "", None)
    for system_name, coord in sorted(snapshot.presence_hexes):
        found[f"presence:{system_name}:{coord[0]}:{coord[1]}"] = (
            "discovery", "New anonymous radar presence", None, system_name, coord)
    owned_colony_sectors = _owned_colony_sectors(game, player)
    for system_name, coord in sorted(player.sector_intel):
        if (system_name, coord) in owned_colony_sectors:
            continue
        found[f"sector:{system_name}:{coord[0]}:{coord[1]}"] = (
            "discovery", "Newly explored sector", None, system_name, coord)
    for system in game.galaxy.systems.values():
        for sector in system.hexes.values():
            for mine in getattr(sector, "minefields", ()):
                if player.is_enemy_of(mine.owner) and is_minefield_visible(snapshot, mine):
                    found[f"mine:{mine.id}"] = ("discovery", "Revealed enemy minefield", mine, "", None)
    for agent, host in discovered_enemy_agent_hosts(game.galaxy, player):
        # No enemy source ship, sabotage, or notification to the infiltrator.
        found[f"spy:{agent.id}"] = ("intelligence", "Discovered hostile agent", host, "", None)
    return found


def refresh_discoveries(game):
    if not _live(game) or getattr(game, "galaxy", None) is None:
        return
    for player in getattr(game, "players", ()):
        state = _state(player)
        if state is None or not state.initialized:
            continue
        found = _discoveries(game, player)
        known = set(state.seen.get("known", []))
        previous_presence = set(state.seen.get("presence", []))
        new_sectors_by_system: dict[str, list[tuple[int, int]]] = {}
        for key, (category, detail, subject, system_name, coord) in found.items():
            if key in (previous_presence if key.startswith("presence:") else known):
                continue
            if key.startswith("sector:") and coord is not None:
                new_sectors_by_system.setdefault(system_name, []).append(tuple(coord))
            else:
                record(game, player, category, detail, subject=subject,
                       system_name=system_name, hex_coord=coord, once=not key.startswith("spy:"))
        for system_name, coords in new_sectors_by_system.items():
            if len(coords) == 1:
                record(game, player, "discovery", "Newly explored sector",
                       system_name=system_name, hex_coord=coords[0], once=True)
            else:
                preview = ", ".join(f"[{c[0]}, {c[1]}]" for c in coords[:8])
                suffix = f" (+{len(coords) - 8} more)" if len(coords) > 8 else ""
                record(game, player, "discovery", f"Newly explored {len(coords)} sectors: {preview}{suffix}",
                       system_name=system_name, hex_coord=None, once=True)
        state.seen = {"known": sorted(known | {k for k in found if not k.startswith("presence:")}),
                      "presence": sorted(k for k in found if k.startswith("presence:"))}


def initialize_campaign(game):
    for player in game.players:
        state = player.briefing = BriefingState(initialized=True, collecting=True)
        state.baseline = economy_snapshot(game, player)
        found = _discoveries(game, player)
        known = {k for k in found if not k.startswith("presence:")} | _starting_known_sector_keys(game, player)
        state.seen = {"known": sorted(known),
                      "presence": sorted(k for k in found if k.startswith("presence:"))}
    finish_window(game, game.players[game.current_player_index])


def _owned_units(game, player):
    from campaign_graph import iter_units
    return (unit for unit, _ in iter_units(getattr(game, 'galaxy', None))
            if unit.owner is player and unit.current_hit_points > 0)


def _has_orders(unit):
    commander = unit.commander_component
    return commander is not None and commander.get_active_orders_count() > 0


def begin_window(game, player):
    state = _state(player)
    if state is None:
        return
    if state.collecting and state.from_turn == int(game.turn_number):
        return
    # Refresh while still closed so discoveries already seen while planning
    # cannot become new contacts in next turn's briefing.
    refresh_discoveries(game)
    if not state.initialized:
        found = _discoveries(game, player)
        known = {k for k in found if not k.startswith("presence:")} | _starting_known_sector_keys(game, player)
        state.seen = {"known": sorted(known),
                      "presence": sorted(k for k in found if k.startswith("presence:"))}
    if state.collecting:
        state.pending, state.omitted_count = [], 0
    state.initialized, state.collecting = True, True
    state.from_turn = int(game.turn_number)
    state.baseline = economy_snapshot(game, player)
    state.busy_unit_ids = [unit.id for unit in _owned_units(game, player) if _has_orders(unit)]


def finish_window(game, player):
    state = _state(player)
    if state is None or not state.collecting:
        return
    refresh_discoveries(game)
    previously_busy = set(state.busy_unit_ids)
    if previously_busy:
        for unit in _owned_units(game, player):
            if unit.id in previously_busy and not _has_orders(unit):
                record(game, player, 'development', 'Idle after finishing orders', subject=unit, once=True)
    state.busy_unit_ids = []
    delta = tuple((key, round(value - state.baseline[key], 6))
                  for key, value in economy_snapshot(game, player).items())
    state.current = TurnSummary(state.from_turn, int(game.turn_number),
        tuple(sorted(state.pending, key=lambda e: (PRIORITY[e.category], e.category, e.event_id))), delta, state.omitted_count)
    state.collecting = False
    state.pending, state.omitted_count = [], 0
    state.acknowledged = False


def current_construction(game, player):
    from unit_templates import get_all_templates_for_player

    rows = []
    templates = get_all_templates_for_player(player)
    for unit in _owned_units(game, player):
        constructor = unit.constructor_component
        job = getattr(constructor, 'current_construction_target', None)
        if job:
            key = job['template_name']
            rows.append(dict(unit_id=unit.id, builder=unit.name, template_name=key,
                             design=templates.get(key, {}).get('name', key), system_name=job['system_name'],
                             hex_coord=list(job['hex_coord']), turns_completed=constructor.construction_progress,
                             turns_required=constructor.time_to_build))
        bay = unit.strikecraft_bay_component
        if bay and bay.constructing:
            design = bay.production_template(bay.construction_slot_index)
            if design:
                key = bay.slot_views()[bay.construction_slot_index]['production_template']
                rows.append(dict(unit_id=unit.id, builder=unit.name, template_name=key,
                                 design=design['name'], system_name=unit.in_system, hex_coord=list(unit.in_hex),
                                 turns_completed=bay.construction_progress, turns_required=design['build_time']))
    return rows


def summary_view(player, game=None):
    state = _state(player)
    summary = copy.deepcopy((state.current if state else TurnSummary()).to_dict())
    if game is not None:
        rows = current_construction(game, player)
        if rows:
            summary["construction_progress"] = rows
    return summary


def entry_text(entry):
    prefix = f"{entry.name} ({entry.owner_name})" if entry.owner_name else entry.name
    if entry.system_name:
        prefix += f" [{entry.system_name}"
        if entry.hex_coord is not None:
            prefix += f" {entry.hex_coord[0]}, {entry.hex_coord[1]}"
        prefix += "]"
    text = f"{prefix}: {entry.detail}" if prefix else entry.detail
    if entry.count > 1:
        text += f" ({entry.count} occurrences)"
    if entry.amount:
        text += f"; total {entry.amount:g}"
    return text


def state_from_dict(raw):
    """Strict current-format decoder; historical IDs need not resolve live."""
    def fields(value, names):
        if not isinstance(value, dict) or set(value) != set(names):
            raise ValueError("Invalid briefing fields")

    def integer(value):
        if type(value) is not int or value < 0:
            raise ValueError("Invalid briefing counter")
        return value

    def real(value):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("Invalid briefing amount")
        return value

    def metrics(value, *, nonnegative=False):
        fields(value, METRICS)
        for amount in value.values():
            if real(amount) < 0 and nonnegative:
                raise ValueError("Invalid briefing baseline")
        return dict(value)

    def entries(values):
        if not isinstance(values, list) or len(values) > MAX_ENTRIES:
            raise ValueError("Invalid briefing entries")
        result = []
        ids = set()
        for value in values:
            if isinstance(value, dict):
                value = {"owner_id": None, "owner_name": "", **value}
            fields(value, BriefingEntry.__dataclass_fields__)
            for key in ("event_id", "turn", "count"):
                if integer(value[key]) == 0:
                    raise ValueError("Invalid briefing event counter")
            if value["event_id"] in ids or value["event_id"] > raw["sequence"]:
                raise ValueError("Invalid briefing event sequence")
            ids.add(value["event_id"])
            if not isinstance(value["category"], str) or value["category"] not in PRIORITY:
                raise ValueError("Invalid briefing category")
            for key, limit in (("name", 200), ("owner_name", 200), ("system_name", 200), ("detail", 500)):
                if not isinstance(value[key], str) or len(value[key]) > limit:
                    raise ValueError("Invalid briefing text")
            if real(value["amount"]) < 0:
                raise ValueError("Invalid briefing event amount")
            for key in ("subject_id", "owner_id"):
                if value[key] is not None:
                    integer(value[key])
            coord = value["hex_coord"]
            if coord is not None and (not isinstance(coord, (list, tuple)) or len(coord) != 2 or any(type(n) is not int for n in coord)):
                raise ValueError("Invalid briefing location")
            result.append(BriefingEntry(**{**value, "hex_coord": tuple(coord) if coord is not None else None}))
        if _size(result) > MAX_CHARACTERS - 1024:
            raise ValueError("Briefing exceeds retention limit")
        return result

    if isinstance(raw, dict):
        raw = {"busy_unit_ids": [], **raw}
    fields(raw, BriefingState.__dataclass_fields__)
    busy = raw["busy_unit_ids"]
    if not isinstance(busy, list) or len({integer(value) for value in busy}) != len(busy):
        raise ValueError("Invalid briefing busy units")
    for key in ("initialized", "collecting", "acknowledged"):
        if type(raw[key]) is not bool:
            raise ValueError("Invalid briefing flag")
    for key in ("sequence", "from_turn", "omitted_count"):
        integer(raw[key])
    baseline = metrics(raw["baseline"], nonnegative=True)
    waits = raw['fuel_waits']
    if (not isinstance(waits, dict) or len(waits) > MAX_ENTRIES
            or any(not isinstance(key, str) or not key.isascii() or not key.isdecimal()
                   or len(key) > 30 or str(int(key)) != key
                   or not isinstance(value, str) or value not in FUEL_PROBLEMS
                   for key, value in waits.items())):
        raise ValueError('Invalid movement fuel wait state')
    seen = raw["seen"]
    if not isinstance(seen, dict) or set(seen) - {"known", "presence"}:
        raise ValueError("Invalid briefing discovery state")
    for values in seen.values():
        if not isinstance(values, list) or any(not isinstance(v, str) or len(v) > 500 for v in values) or len(values) != len(set(values)):
            raise ValueError("Invalid briefing discovery keys")
    report = raw["current"]
    fields(report, ("from_turn", "to_turn", "entries", "economy", "omitted_count"))
    for key in ("from_turn", "to_turn", "omitted_count"):
        integer(report[key])
    if report["from_turn"] > report["to_turn"]:
        raise ValueError("Invalid briefing window")
    current = TurnSummary(report["from_turn"], report["to_turn"], tuple(entries(report["entries"])),
                          tuple(metrics(report["economy"]).items()), report["omitted_count"])
    pending = entries(raw["pending"])
    if any(not max(1, current.from_turn) <= entry.turn <= current.to_turn for entry in current.entries):
        raise ValueError("Briefing event outside report window")
    if any(entry.turn < max(1, raw["from_turn"]) for entry in pending):
        raise ValueError("Briefing event before collection window")
    if not raw["collecting"] and (busy or any(entry.turn < current.to_turn for entry in pending)):
        raise ValueError("Invalid planning-period briefing state")
    return BriefingState(**{**raw, "baseline": baseline, "seen": copy.deepcopy(seen), 'fuel_waits': dict(waits),
                            "current": current, "pending": pending})
