"""Communications domain objects and ownership rules."""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from domain.players import Player


@dataclasses.dataclass
class Message:
    """Represents an inter-player communication transmission."""
    sender_id: int
    sender_name: str
    recipient_id: int
    turn_sent: int
    text: str
    timestamp: str = ""
    read_by_recipient: bool = False
    id: int = 0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_markdown(self, sender_player: Optional['Player'] = None, recipient_player: Optional['Player'] = None) -> str:
        s_name = sender_player.name if sender_player else self.sender_name or f"Player {self.sender_id}"
        s_type = sender_player.controller.display_name if sender_player else ""
        s_team = f", Team: {sender_player.team_id}" if (sender_player and getattr(sender_player, 'team_id', None) is not None) else ""
        s_desc = f"{s_name} (ID: {self.sender_id}{s_team}{f', {s_type}' if s_type else ''})"

        r_name = recipient_player.name if recipient_player else f"Player {self.recipient_id}"
        r_type = recipient_player.controller.display_name if recipient_player else ""
        r_team = f", Team: {recipient_player.team_id}" if (recipient_player and getattr(recipient_player, 'team_id', None) is not None) else ""
        r_desc = f"{r_name} (ID: {self.recipient_id}{r_team}{f', {r_type}' if r_type else ''})"

        lines = [
            f"### Transmission #{self.id}: **{s_name}** ➔ **{r_name}**",
            f"- **Turn**: {self.turn_sent}",
            f"- **Timestamp**: `{self.timestamp}`",
            f"- **Sender**: {s_desc}",
            f"- **Recipient**: {r_desc}",
            "",
            f"> {self.text}",
            "",
            "---",
        ]
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "sender_id": self.sender_id,
            "sender_name": self.sender_name,
            "recipient_id": self.recipient_id,
            "turn_sent": self.turn_sent,
            "text": self.text,
            "timestamp": self.timestamp,
            "read_by_recipient": self.read_by_recipient,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        return cls(
            id=data.get("id", 0),
            sender_id=data.get("sender_id", 0),
            sender_name=data.get("sender_name", ""),
            recipient_id=data.get("recipient_id", 0),
            turn_sent=data.get("turn_sent", 1),
            text=data.get("text", ""),
            timestamp=data.get("timestamp", ""),
            read_by_recipient=data.get("read_by_recipient", False),
        )


@dataclasses.dataclass
class Conversation:
    """Represents a chronological dialogue/transmission thread between two players."""
    participant_ids: Tuple[int, int]
    messages: List[Message] = dataclasses.field(default_factory=list)

    @classmethod
    def make_key(cls, p1_id: int, p2_id: int) -> Tuple[int, int]:
        return (min(p1_id, p2_id), max(p1_id, p2_id))

    def add_message(self, message: Message) -> None:
        self.messages.append(message)
        self.messages.sort(key=lambda m: (m.turn_sent, m.id))

    def get_partner_id(self, viewer_id: int) -> int:
        if self.participant_ids[0] == viewer_id:
            return self.participant_ids[1]
        return self.participant_ids[0]

    def get_messages_for_player(self, viewer_id: int, before_turn: Optional[int] = None) -> List[Message]:
        if before_turn is None:
            return list(self.messages)
        return [m for m in self.messages if m.turn_sent < before_turn]

    def get_unread_count(self, viewer_id: int, before_turn: Optional[int] = None) -> int:
        msgs = self.messages
        if before_turn is not None:
            msgs = [m for m in msgs if m.turn_sent < before_turn]
        return sum(1 for m in msgs if m.recipient_id == viewer_id and not m.read_by_recipient)

    def mark_as_read(self, viewer_id: int) -> None:
        for m in self.messages:
            if m.recipient_id == viewer_id:
                m.read_by_recipient = True

    def to_markdown(self, players_by_id: Optional[Dict[int, 'Player']] = None) -> str:
        p_dict = players_by_id or {}
        p1 = p_dict.get(self.participant_ids[0])
        p2 = p_dict.get(self.participant_ids[1])
        p1_name = p1.name if p1 else f"Player {self.participant_ids[0]}"
        p2_name = p2.name if p2 else f"Player {self.participant_ids[1]}"

        sections = [
            f"## Thread: {p1_name} & {p2_name}",
            "",
        ]
        if not self.messages:
            sections.append("*No transmissions recorded in this thread.*")
        else:
            for msg in self.messages:
                sender_p = p_dict.get(msg.sender_id)
                recip_p = p_dict.get(msg.recipient_id)
                sections.append(msg.to_markdown(sender_p, recip_p))
        return "\n".join(sections)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "participant_ids": list(self.participant_ids),
            "messages": [m.to_dict() for m in self.messages],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Conversation':
        participants = tuple(data.get("participant_ids", [0, 0]))
        messages = [
            Message.from_dict(m) if isinstance(m, dict) else m
            for m in data.get("messages", [])
        ]
        return cls(
            participant_ids=(int(participants[0]), int(participants[1])),
            messages=messages,
        )
