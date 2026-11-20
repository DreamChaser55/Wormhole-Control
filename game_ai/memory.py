"""Bounded, save-authoritative long-term memory for one AI player."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import groupby
from pathlib import Path
import re
from typing import Any, Iterable, Mapping
from persistence_paths import validate_identity, sidecar_paths


MEMORY_VERSION = 2
MAX_RECEIPTS_TOTAL_CHARS = 8_000


@dataclass
class AgentMemory:
    strategy: str = (
        "Observe the board, preserve the fleet, expand the economy, and pursue victory."
    )
    objectives: list[str] = field(default_factory=list)
    commitments: list[str] = field(default_factory=list)
    beliefs: list[str] = field(default_factory=list)
    important_events: list[str] = field(default_factory=list)
    lessons: list[str] = field(default_factory=list)
    misc: list[str] = field(default_factory=list)
    receipts: list[str] = field(default_factory=list)
    updated_turn: int = 0

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any] | None) -> "AgentMemory":
        raw = raw if isinstance(raw, Mapping) else {}
        default_strategy = cls().strategy
        return cls(
            strategy=_text(raw.get("strategy"), 3000) or default_strategy,
            objectives=_text_list(raw.get("objectives"), 12),
            commitments=_text_list(raw.get("commitments"), 12),
            beliefs=_text_list(raw.get("beliefs"), 16),
            important_events=_text_list(raw.get("important_events"), 16),
            lessons=_merge_lessons(_text_list(raw.get("lessons"), 16)),
            misc=_text_list(raw.get("misc"), 16),
            receipts=_bound_receipts(raw.get("receipts")),
            updated_turn=_int(raw.get("updated_turn"), 0),
        )

    def apply_patch(self, patch: Mapping[str, Any] | None, *, turn: int) -> None:
        if not isinstance(patch, Mapping):
            return
        if patch.get("strategy") is not None:
            self.strategy = _text(patch.get("strategy"), 3000) or self.strategy
        for field_name, limit in (
            ("objectives", 12),
            ("commitments", 12),
            ("beliefs", 16),
            ("important_events", 16),
            ("misc", 16),
        ):
            if patch.get(field_name) is not None:
                setattr(self, field_name, _text_list(patch.get(field_name), limit))
        if patch.get("lessons") is not None:
            self.lessons = _merge_lessons(self.lessons + _text_list(patch.get("lessons"), 16))
        self.updated_turn = max(0, int(turn))

    def add_receipt(self, text: str, *, turn: int) -> None:
        self.add_receipts((text,), turn=turn)

    def reconcile_combat_losses(self, summary: Mapping[str, Any]) -> None:
        """Close explicit commitments to enemies whose destruction the player observed."""
        losses = {}
        for event in summary.get('entries', ()):
            if event.get('category') != 'enemy_losses' or event.get('detail') != 'Destroyed':
                continue
            identity = event.get('subject_id')
            if type(identity) is not int:
                continue
            name = event['name']
            named_id = name if name.endswith(f' {identity}') else f'{name} {identity}'
            # Support the prompt's explicit target marker and older name-and-ID commitments.
            losses[identity] = re.compile(
                rf'\[target:{identity}\]|\b(?:attack(?:ing)?|engag(?:e|ing)|target(?:ing)?)\s+'
                rf'(?:{re.escape(named_id)}\b|{re.escape(name)}\s*\(id:{identity}\))', re.IGNORECASE)
            coord = event.get('hex_coord')
            location = f" in {event['system_name']} {coord}" if coord else ''
            fact = f"Turn {event['turn']}: {name} (id:{identity}) destroyed{location}."
            if fact not in self.important_events:
                self.important_events = [fact, *self.important_events][:16]

        if losses:
            commitments = []
            for entry in self.commitments:
                clauses = re.split(r';\s*(?=[^:;]+:)', entry)
                remaining = [clause for clause in clauses if not any(pattern.search(clause) for pattern in losses.values())]
                if remaining:
                    commitments.append('; '.join(remaining))
            self.commitments = commitments

    def add_receipts(self, receipts: Iterable[str], *, turn: int) -> None:
        actions = [f"Turn {turn}: {text.strip()}" for text in receipts if isinstance(text, str) and text.strip()]
        if actions:
            self.receipts = _bound_receipts([*self.receipts, *actions])
            self.updated_turn = max(0, int(turn))

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": MEMORY_VERSION,
            "strategy": self.strategy,
            "objectives": list(self.objectives),
            "commitments": list(self.commitments),
            "beliefs": list(self.beliefs),
            "important_events": list(self.important_events),
            "lessons": list(self.lessons),
            "misc": list(self.misc),
            "receipts": list(self.receipts),
            "updated_turn": self.updated_turn,
        }

    def to_markdown(self, *, player_name: str, campaign_id: str, agent_id: str) -> str:
        sections = [
            f"# {player_name} — Agent Memory",
            "",
            "> Derived export of current agent memory.",
            "",
            f"- Campaign: {campaign_id}",
            f"- Agent: {agent_id}",
            f"- Last updated turn: {self.updated_turn}",
            f"- Generated: {datetime.now(timezone.utc).isoformat()}",
            "",
            "## Strategy",
            "",
            self.strategy,
        ]
        for title, items in (
            ("Objectives", self.objectives),
            ("Commitments", self.commitments),
            ("Beliefs", self.beliefs),
            ("Important events in previous turns", self.important_events),
            ("Lessons", self.lessons),
            ("Misc", self.misc),
        ):
            sections.extend(["", f"## {title}", ""])
            sections.extend([f"- {item}" for item in items] or ["- None recorded."])

        sections.extend(["", "## Recent receipts", ""])
        receipt_lines: list[str] = []
        for turn, receipts in groupby(self.receipts, key=_receipt_turn):
            if turn:
                receipt_lines.append(f"- {turn}:")
                receipt_lines.extend(f"  - {receipt.split(': ', 1)[1]}" for receipt in receipts)
            else:
                receipt_lines.extend(f"- {receipt}" for receipt in receipts)
        sections.extend(receipt_lines or ["- None recorded."])
        return "\n".join(sections) + "\n"


def write_memory_sidecar(
    root: Path,
    *,
    campaign_id: str,
    agent_id: str,
    player_name: str,
    memory: AgentMemory,
) -> Path:
    """Atomically write the derived memory.md sidecar below the save directory."""
    validate_identity(campaign_id, "campaign_id")
    validate_identity(agent_id, "agent_id")
    target, temporary = sidecar_paths(root, "agent_memory", (campaign_id, agent_id), "memory.md")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(
        memory.to_markdown(
            player_name=player_name,
            campaign_id=campaign_id,
            agent_id=agent_id,
        ),
        encoding="utf-8",
    )
    temporary.replace(target)
    return target


def _text(value: Any, max_length: int) -> str:
    return value.strip()[:max_length] if isinstance(value, str) else ""


def _text_list(value: Any, limit: int, *, max_length: int = 500) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        clean = _text(item, max_length)
        if clean:
            result.append(clean)
        if len(result) >= limit:
            break
    return result


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _lesson_identity(text: str) -> tuple[str, int]:
    """Prefer explicit constraint keys; coalesce common generic paraphrases."""
    normalized = re.sub(r"[^a-z0-9_]+", " ", text.casefold()).strip()
    keyed = re.match(r"^\[([a-z0-9_./:-]+)\]", text.casefold())
    from .command_spec import COMMAND_SPECS
    if keyed and (re.split(r"[/.:]", keyed.group(1))[0] in COMMAND_SPECS
                  or keyed.group(1).startswith('output/')):
        return keyed.group(1), 3
    concrete = bool(re.search(r"\d|slot|cooldown|range|hyperdrive|capacity|required", normalized))
    if not concrete:
        if (re.search(r"preserv|retain|keep|replac|interrupt|cancel", normalized)
                and re.search(r"order|mission|work", normalized)):
            return "preserve_ongoing_work", 0
        if (re.search(r"target|ids?", normalized)
                and re.search(r"visible|visibility|legal|listed|observ|current", normalized)):
            return "use_disclosed_legal_targets", 0
    specific = concrete or any(command in normalized.split() for command in COMMAND_SPECS)
    return keyed.group(1) if keyed else normalized, 2 if specific else 1


def _merge_lessons(entries: list[str]) -> list[str]:
    merged: dict[str, tuple[int, int, str]] = {}
    for index, entry in enumerate(entries):
        key, priority = _lesson_identity(entry)
        if key in merged and merged[key][2] == entry:
            continue
        merged[key] = priority, index, entry
    # Generic advice must not evict a concrete command/equipment constraint.
    kept = sorted(merged.values(), key=lambda item: (item[0], item[1]))[-16:]
    return [item[2] for item in sorted(kept, key=lambda item: item[1])]


def rejection_lessons(plan, issues, observation) -> list[str]:
    """Derive bounded constraints from public errors, committed only after repair."""
    lessons = []
    units = {unit['id']: unit for unit in observation.get('units', [])}
    for issue in issues:
        if plan is None or issue.command_index is None or not 0 <= issue.command_index < len(plan.batch.commands):
            continue
        command = plan.batch.commands[issue.command_index]
        actors = command.unit_ids or (None,)
        for unit_id in actors:
            key = f"{command.type}/{issue.code}"
            if command.ability:
                key += '/' + command.ability
            if unit_id is not None:
                key += f"/unit-{unit_id}"
            choices = units.get(unit_id, {}).get('command_options', {})
            if command.type == 'set_wing_production':
                slots = choices.get('set_wing_production', {}).get('slot_indices', [])
                detail = f"Use this carrier's editable slot_indices {slots}; slot_index and explicit template_name are required (null clears). Recheck current options."
            else:
                detail = f"{issue.message} Recheck current options and terminal order_history before repeating this command."
            lessons.append(f"[{key}] {detail}"[:500])
    return _merge_lessons(lessons)


def _bound_receipts(
    value: Any,
    max_total_chars: int = MAX_RECEIPTS_TOTAL_CHARS,
) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str):
            clean = item.strip()
            if clean:
                result.append(clean)
    total_chars = sum(len(r) for r in result)
    while total_chars > max_total_chars and result:
        removed = result.pop(0)
        total_chars -= len(removed)
        turn = _receipt_turn(removed)
        while turn is not None and result and _receipt_turn(result[0]) == turn:
            total_chars -= len(result.pop(0))
    return result


def _receipt_turn(entry: str) -> str | None:
    label, separator, _ = entry.partition(": ")
    return label if separator and label.startswith("Turn ") else None

