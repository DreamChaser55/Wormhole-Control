"""OpenAI Responses API implementation of the planning provider."""

from __future__ import annotations

import hashlib
import json
from time import perf_counter
from typing import Any

from game_ai.config import load_openai_api_key
from game_ai.contracts import ContractError, TurnPlan
from game_ai.runtime import AgentRuntimeConfig
from game_ai.prompts import SYSTEM_INSTRUCTIONS
from game_ai.schema import responses_text_config

from .base import PlanningOutputError, PlanningRequest, PlanningResult


class OpenAIResponsesProvider:
    def __init__(self, *, client: Any | None = None):
        self._client = client

    def _client_for(self, runtime_config: AgentRuntimeConfig):
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
            timeout=runtime_config.timeout_seconds,
            max_retries=2,
        )
        return self._client

    def plan_turn(
        self,
        request: PlanningRequest,
        runtime_config: AgentRuntimeConfig,
    ) -> PlanningResult:
        started = perf_counter()
        client = self._client_for(runtime_config)
        response = client.responses.create(
            model=runtime_config.model,
            instructions=SYSTEM_INSTRUCTIONS,
            input=json.dumps(request.to_dict(), separators=(",", ":"), ensure_ascii=False),
            reasoning={"effort": runtime_config.reasoning_effort},
            text=responses_text_config(),
            max_output_tokens=runtime_config.max_output_tokens,
            store=False,
            metadata={
                "game": "wormhole-control",
                "campaign": request.campaign_id[:64],
                "turn": str(request.turn_number),
            },
            safety_identifier=_safe_identifier(request.agent_id),
            prompt_cache_key="wormhole-control-turn-v2",
        )
        latency_seconds = perf_counter() - started
        response_id = getattr(response, "id", None)
        usage = _usage_dict(getattr(response, "usage", None))
        output_text = getattr(response, "output_text", None)
        if not output_text:
            raise PlanningOutputError(
                "missing_output",
                "OpenAI returned no structured turn output.",
                provider="openai",
                model=runtime_config.model,
                reasoning_effort=runtime_config.reasoning_effort,
                response_id=response_id,
                usage=usage,
                latency_seconds=latency_seconds,
            )
        try:
            raw = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise PlanningOutputError(
                "invalid_json",
                "OpenAI returned invalid JSON.",
                provider="openai",
                model=runtime_config.model,
                reasoning_effort=runtime_config.reasoning_effort,
                response_id=response_id,
                usage=usage,
                latency_seconds=latency_seconds,
            ) from exc
        try:
            plan = TurnPlan.from_dict(raw, max_commands=runtime_config.max_commands)
        except ContractError as exc:
            raise PlanningOutputError(
                "invalid_contract",
                str(exc),
                provider="openai",
                model=runtime_config.model,
                reasoning_effort=runtime_config.reasoning_effort,
                response_id=response_id,
                usage=usage,
                latency_seconds=latency_seconds,
            ) from exc
        return PlanningResult(
            plan=plan,
            provider="openai",
            model=runtime_config.model,
            reasoning_effort=runtime_config.reasoning_effort,
            response_id=response_id,
            usage=usage,
            latency_seconds=latency_seconds,
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
