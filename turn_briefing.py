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
PRIORITY = {"loss": 0, "capture": 0, "problem": 1, "combat": 2,
            "hazard": 2, "intelligence": 3, "development": 4,
            "discovery": 5, "communications": 6}
METRICS = ("credits", "metal", "crystal", "population")


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

    def to_dict(self):
        result = asdict(self)
        result["pending"] = [entry.to_dict() for entry in self.pending]
        result["current"] = self.current.to_dict()
        return result


def _state(player):
    value = getattr(player, "briefing", None)
    return value if isinstance(value, BriefingState) else None


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
           name="", system_name="", hex_coord=None, amount=0, once=False):
    state = _state(player)
    if not _live(game) or state is None or not state.collecting:
        return
    if subject is not None:
        subject_id, name = subject.id, str(subject.name)
        system_name = str(getattr(subject, "in_system", "") or "")
        hex_coord = getattr(subject, "in_hex", None)
    entry = BriefingEntry(state.sequence + 1, int(game.turn_number), category,
                          subject_id, name[:200], system_name[:200],
                          tuple(hex_coord) if hex_coord is not None else None,
                          detail[:500], amount=float(amount))
    # Outcome history reports ownership/destruction interruptions separately.
    # Those are omitted by order_outcome so a loss has just one primary notice.
    key = lambda e: (e.category, e.subject_id, e.name, e.system_name, e.hex_coord, e.detail)
    for index, old in enumerate(state.pending):
        if key(old) == key(entry):
            if not once:
                state.pending[index] = replace(old, count=old.count + 1, amount=old.amount + entry.amount)
            _bound(state)
            return
    state.sequence += 1
    state.pending.append(entry)
    _bound(state)


def unit_event(unit, category, detail, *, amount=0, private=False, component_type=None, actor=None, once=False, new_owner=None):
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
            public_detail += f" by {actor.name}" if _visible(snapshot, actor) else " by an unknown attacker"
        record(game, player, category, public_detail, subject=unit, amount=amount, once=once)


def order_outcome(order, outcome, reason):
    player = getattr(order, "_issuing_player", None)
    if player is None or reason in {"unit_destroyed", "ownership_lost"}:
        return
    if outcome == "failed" or (outcome == "cancelled" and reason != "cancelled"):
        record(_game(order.unit), player, "problem",
               f"{order.order_type.name.replace('_', ' ').title()} {outcome}: {reason.replace('_', ' ')}",
               subject=order.unit)
    elif outcome == "completed" and order.order_type.name in {
        "INFILTRATE_UNIT", "INFILTRATE_PLANET", "RELOCATE_AGENT", "SABOTAGE",
        "ELIMINATE_AGENT", "EXTRACT_AGENT",
    }:
        record(_game(order.unit), player, "intelligence",
               f"{order.order_type.name.replace('_', ' ').title()} completed", subject=order.unit)


def economy_snapshot(game, player):
    result = {key: float(getattr(player, key, 0)) for key in METRICS[:3]}
    result["population"] = sum(float(getattr(body, "population", 0))
        for system in getattr(getattr(game, "galaxy", None), "systems", {}).values()
        for _, body in system.get_all_celestial_bodies() if getattr(body, "owner", None) is player)
    return result


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
    for system_name, coord in sorted(player.sector_intel):
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
        for key, (category, detail, subject, system_name, coord) in found.items():
            if key not in (previous_presence if key.startswith("presence:") else known):
                record(game, player, category, detail, subject=subject,
                       system_name=system_name, hex_coord=coord, once=not key.startswith("spy:"))
        state.seen = {"known": sorted(known | {k for k in found if not k.startswith("presence:")}),
                      "presence": sorted(k for k in found if k.startswith("presence:"))}


def initialize_campaign(game):
    for player in game.players:
        state = player.briefing = BriefingState(initialized=True, collecting=True)
        state.baseline = economy_snapshot(game, player)
        found = _discoveries(game, player)
        state.seen = {"known": sorted(k for k in found if not k.startswith("presence:")),
                      "presence": sorted(k for k in found if k.startswith("presence:"))}
    finish_window(game, game.players[game.current_player_index])


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
        state.seen = {"known": sorted(k for k in found if not k.startswith("presence:")),
                      "presence": sorted(k for k in found if k.startswith("presence:"))}
    state.initialized, state.collecting = True, True
    state.from_turn = int(game.turn_number)
    state.baseline = economy_snapshot(game, player)
    state.pending, state.omitted_count = [], 0


def finish_window(game, player):
    state = _state(player)
    if state is None or not state.collecting:
        return
    refresh_discoveries(game)
    delta = tuple((key, round(value - state.baseline[key], 6))
                  for key, value in economy_snapshot(game, player).items())
    state.current = TurnSummary(state.from_turn, int(game.turn_number),
        tuple(sorted(state.pending, key=lambda e: (PRIORITY[e.category], e.category, e.event_id))), delta, state.omitted_count)
    state.collecting = False
    state.pending, state.omitted_count = [], 0
    state.acknowledged = False


def summary_view(player):
    state = _state(player)
    return copy.deepcopy((state.current if state else TurnSummary()).to_dict())


def entry_text(entry):
    prefix = entry.name
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
            fields(value, BriefingEntry.__dataclass_fields__)
            for key in ("event_id", "turn", "count"):
                if integer(value[key]) == 0:
                    raise ValueError("Invalid briefing event counter")
            if value["event_id"] in ids or value["event_id"] > raw["sequence"]:
                raise ValueError("Invalid briefing event sequence")
            ids.add(value["event_id"])
            if not isinstance(value["category"], str) or value["category"] not in PRIORITY:
                raise ValueError("Invalid briefing category")
            for key, limit in (("name", 200), ("system_name", 200), ("detail", 500)):
                if not isinstance(value[key], str) or len(value[key]) > limit:
                    raise ValueError("Invalid briefing text")
            if real(value["amount"]) < 0:
                raise ValueError("Invalid briefing event amount")
            if value["subject_id"] is not None:
                integer(value["subject_id"])
            coord = value["hex_coord"]
            if coord is not None and (not isinstance(coord, (list, tuple)) or len(coord) != 2 or any(type(n) is not int for n in coord)):
                raise ValueError("Invalid briefing location")
            result.append(BriefingEntry(**{**value, "hex_coord": tuple(coord) if coord is not None else None}))
        if _size(result) > MAX_CHARACTERS - 1024:
            raise ValueError("Briefing exceeds retention limit")
        return result

    fields(raw, BriefingState.__dataclass_fields__)
    for key in ("initialized", "collecting", "acknowledged"):
        if type(raw[key]) is not bool:
            raise ValueError("Invalid briefing flag")
    for key in ("sequence", "from_turn", "omitted_count"):
        integer(raw[key])
    baseline = metrics(raw["baseline"], nonnegative=True)
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
    if not raw["collecting"] and (pending or raw["omitted_count"]):
        raise ValueError("Closed briefing has pending events")
    return BriefingState(**{**raw, "baseline": baseline, "seen": copy.deepcopy(seen),
                            "current": current, "pending": pending})
