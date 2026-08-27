"""Bounded, save-authoritative long-term memory for one AI player."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


MEMORY_VERSION = 1


@dataclass
class AgentMemory:
    strategy: str = (
        "Observe the board, preserve the fleet, expand the economy, and pursue victory."
    )
    objectives: list[str] = field(default_factory=list)
    commitments: list[str] = field(default_factory=list)
    beliefs: list[str] = field(default_factory=list)
    lessons: list[str] = field(default_factory=list)
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
            lessons=_text_list(raw.get("lessons"), 16),
            receipts=_text_list(raw.get("receipts"), 20, max_length=600),
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
            ("lessons", 16),
        ):
            if patch.get(field_name) is not None:
                setattr(self, field_name, _text_list(patch.get(field_name), limit))
        self.updated_turn = max(0, int(turn))

    def add_receipt(self, text: str, *, turn: int) -> None:
        clean = _text(text, 600)
        if clean:
            self.receipts = (self.receipts + [f"Turn {turn}: {clean}"])[-20:]
            self.updated_turn = max(0, int(turn))

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": MEMORY_VERSION,
            "strategy": self.strategy,
            "objectives": list(self.objectives),
            "commitments": list(self.commitments),
            "beliefs": list(self.beliefs),
            "lessons": list(self.lessons),
            "receipts": list(self.receipts),
            "updated_turn": self.updated_turn,
        }

    def to_markdown(self, *, player_name: str, campaign_id: str, agent_id: str) -> str:
        sections = [
            f"# {player_name} — Agent Memory",
            "",
            "> Generated from the save file. Editing this sidecar does not alter the campaign.",
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
            ("Lessons", self.lessons),
        ):
            sections.extend(["", f"## {title}", ""])
            sections.extend([f"- {item}" for item in items] or ["- None recorded."])

        sections.extend(["", "## Recent receipts", ""])
        receipt_lines: list[str] = []
        for receipt in self.receipts:
            receipt_lines.extend(_format_receipt_entry(receipt))
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
    target_dir = root / "agent_memory" / campaign_id / agent_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "memory.md"
    temporary = target.with_suffix(".md.tmp")
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


def _format_receipt_entry(entry: str) -> list[str]:
    clean = _text(entry, 2000)
    if not clean:
        return []
    if clean.startswith("Turn ") and ": " in clean:
        turn_label, rest = clean.split(": ", 1)
        actions = [act.strip() for act in rest.split(";") if act.strip()]
        if not actions:
            return [f"- {turn_label}:", "  - No commands issued."]
        return [f"- {turn_label}:"] + [f"  - {act}" for act in actions]
    actions = [act.strip() for act in clean.split(";") if act.strip()]
    if not actions:
        return []
    if len(actions) == 1:
        return [f"- {actions[0]}"]
    return [f"- {act}" for act in actions]

