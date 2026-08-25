"""Balanced model/runtime profiles exposed by the new-game UI and saves."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentProfile:
    id: str
    label: str
    model: str
    reasoning_effort: str
    max_output_tokens: int
    timeout_seconds: float
    max_commands: int


PROFILES: dict[str, AgentProfile] = {
    "fast": AgentProfile("fast", "Fast", "gpt-5.6-luna", "low", 3000, 45.0, 20),
    "balanced": AgentProfile("balanced", "Balanced", "gpt-5.6-terra", "medium", 5000, 75.0, 32),
    "strategic": AgentProfile("strategic", "Strategic", "gpt-5.6-sol", "high", 7000, 120.0, 40),
}


def get_profile(profile_id: str | None) -> AgentProfile:
    return PROFILES.get(profile_id or "balanced", PROFILES["balanced"])
