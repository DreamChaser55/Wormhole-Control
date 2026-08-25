"""OpenAI Responses API implementation of the planning provider."""

from __future__ import annotations

import hashlib
import json
from time import perf_counter
from typing import Any

from game_ai.config import load_openai_api_key
from game_ai.contracts import ContractError, TurnPlan
from game_ai.profiles import AgentProfile
from game_ai.prompts import SYSTEM_INSTRUCTIONS
from game_ai.schema import responses_text_config

from .base import PlanningRequest, PlanningResult


class OpenAIResponsesProvider:
    def __init__(self, *, client: Any | None = None):
        self._client = client

    def _client_for(self, profile: AgentProfile):
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The OpenAI SDK is not installed. Install the project requirements."
            ) from exc
        self._client = OpenAI(
            api_key=load_openai_api_key(),
            timeout=profile.timeout_seconds,
            max_retries=2,
        )
        return self._client

    def plan_turn(
        self,
        request: PlanningRequest,
        profile: AgentProfile,
    ) -> PlanningResult:
        started = perf_counter()
        client = self._client_for(profile)
        response = client.responses.create(
            model=profile.model,
            instructions=SYSTEM_INSTRUCTIONS,
            input=json.dumps(request.to_dict(), separators=(",", ":"), ensure_ascii=False),
            reasoning={"effort": profile.reasoning_effort},
            text=responses_text_config(),
            max_output_tokens=profile.max_output_tokens,
            store=False,
            metadata={
                "game": "wormhole-control",
                "campaign": request.campaign_id[:64],
                "turn": str(request.turn_number),
            },
            safety_identifier=_safe_identifier(request.agent_id),
            prompt_cache_key="wormhole-control-turn-v1",
        )
        output_text = getattr(response, "output_text", None)
        if not output_text:
            raise RuntimeError("OpenAI returned no structured turn output.")
        try:
            raw = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise ContractError("OpenAI returned invalid JSON.") from exc
        plan = TurnPlan.from_dict(raw, max_commands=profile.max_commands)
        return PlanningResult(
            plan=plan,
            provider="openai",
            model=profile.model,
            response_id=getattr(response, "id", None),
            usage=_usage_dict(getattr(response, "usage", None)),
            latency_seconds=perf_counter() - started,
        )


def _safe_identifier(agent_id: str) -> str:
    return hashlib.sha256(agent_id.encode("utf-8")).hexdigest()[:64]


def _usage_dict(usage: Any) -> dict[str, int]:
    if usage is None:
        return {}
    result = {}
    for name in ("input_tokens", "output_tokens", "total_tokens"):
        value = getattr(usage, name, None)
        if isinstance(value, int):
            result[name] = value
    return result
