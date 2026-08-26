"""Luna-only model and runtime configuration for AI turns."""

from dataclasses import dataclass
from typing import Optional, Tuple


LUNA_MODEL = "gpt-5.6-luna"
SUPPORTED_REASONING_EFFORTS: Tuple[str, ...] = ("low", "medium", "high")
DEFAULT_REASONING_EFFORT = "medium"

MIN_REPAIR_RETRIES = 1
MAX_REPAIR_RETRIES = 5
DEFAULT_REPAIR_RETRIES = 2

MAX_OUTPUT_TOKENS = 7_000
TIMEOUT_SECONDS = 120.0
MAX_COMMANDS = 40


def normalize_reasoning_effort(reasoning_effort: Optional[str]) -> str:
    """Return a supported Luna reasoning effort, defaulting to medium."""
    if isinstance(reasoning_effort, str):
        normalized = reasoning_effort.strip().lower()
        if normalized in SUPPORTED_REASONING_EFFORTS:
            return normalized
    return DEFAULT_REASONING_EFFORT


def normalize_repair_retries(repair_retries: object) -> int:
    """Return a bounded semantic-repair retry count, defaulting to two."""
    if isinstance(repair_retries, bool):
        return DEFAULT_REPAIR_RETRIES
    try:
        normalized = int(repair_retries)
    except (TypeError, ValueError, OverflowError):
        return DEFAULT_REPAIR_RETRIES
    return max(MIN_REPAIR_RETRIES, min(MAX_REPAIR_RETRIES, normalized))


@dataclass(frozen=True)
class AgentRuntimeConfig:
    model: str
    reasoning_effort: str
    max_output_tokens: int
    timeout_seconds: float
    max_commands: int


def get_runtime_config(reasoning_effort: Optional[str]) -> AgentRuntimeConfig:
    """Build the shared Luna runtime with the selected reasoning effort."""
    return AgentRuntimeConfig(
        model=LUNA_MODEL,
        reasoning_effort=normalize_reasoning_effort(reasoning_effort),
        max_output_tokens=MAX_OUTPUT_TOKENS,
        timeout_seconds=TIMEOUT_SECONDS,
        max_commands=MAX_COMMANDS,
    )
