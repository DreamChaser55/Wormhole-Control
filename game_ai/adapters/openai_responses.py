"""OpenAI Responses API implementation of the planning provider."""

from __future__ import annotations

import hashlib
import json
import os
import ssl
from time import perf_counter
from typing import Any

from game_ai.config import load_openai_api_key
from game_ai.contracts import ContractError, TurnPlan
from game_ai.runtime import AgentRuntimeConfig
from game_ai.prompts import SYSTEM_INSTRUCTIONS
from game_ai.prompt_context import planning_context
from game_ai.schema import responses_text_config

from .base import PlanningOutputError, PlanningRequest, PlanningResult

PROMPT_CACHE_KEY = "wormhole-control-turn-v29"


class OpenAIResponsesProvider:
    def __init__(self, *, client: Any | None = None):
        self._client = client
        self._owns_client = client is None
        self._closed = False

    def _client_for(self, runtime_config: AgentRuntimeConfig):
        if self._closed:
            raise RuntimeError("The planning provider is closed.")
        if self._client is not None:
            return self._client
        try:
            from openai import AsyncOpenAI, DefaultAsyncHttpxClient
        except ImportError as exc:
            raise RuntimeError(
                "The OpenAI SDK is not installed. Install the project requirements."
            ) from exc
        self._client = AsyncOpenAI(
            api_key=load_openai_api_key(),
            timeout=runtime_config.timeout_seconds,
            max_retries=2,
            http_client=DefaultAsyncHttpxClient(verify=_tls_context()),
        )
        return self._client

    async def aclose(self) -> None:
        """Close an internally created client on the same loop as its requests."""
        if self._closed:
            return
        self._closed = True
        if self._owns_client and self._client is not None:
            await self._client.close()

    async def plan_turn(
        self,
        request: PlanningRequest,
        runtime_config: AgentRuntimeConfig,
    ) -> PlanningResult:
        started = perf_counter()
        client = self._client_for(runtime_config)
        messages, prompt_metrics = planning_context(request)
        response = await client.responses.create(
            model=runtime_config.model,
            instructions=SYSTEM_INSTRUCTIONS,
            input=messages,
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
            prompt_cache_key=PROMPT_CACHE_KEY,
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
                prompt_metrics=prompt_metrics,
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
                prompt_metrics=prompt_metrics,
            ) from exc
        try:
            plan = TurnPlan.from_dict(raw, max_commands=runtime_config.max_commands, strict=True)
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
                prompt_metrics=prompt_metrics,
            ) from exc
        return PlanningResult(
            plan=plan,
            provider="openai",
            model=runtime_config.model,
            reasoning_effort=runtime_config.reasoning_effort,
            response_id=response_id,
            usage=usage,
            latency_seconds=latency_seconds,
            prompt_metrics=prompt_metrics,
        )


def _safe_identifier(agent_id: str) -> str:
    return hashlib.sha256(agent_id.encode("utf-8")).hexdigest()[:64]


def _tls_context() -> ssl.SSLContext:
    """Honor CA overrides; otherwise combine bundled and operating system roots."""
    import certifi
    from game_ai.provider_errors import CertificateConfigurationError

    try:
        if os.environ.get("SSL_CERT_FILE"):
            return ssl.create_default_context(cafile=os.environ["SSL_CERT_FILE"])
        if os.environ.get("SSL_CERT_DIR"):
            return ssl.create_default_context(capath=os.environ["SSL_CERT_DIR"])
        context = ssl.create_default_context(cafile=certifi.where())
        # On Windows this includes the ROOT and CA system certificate stores.
        context.load_default_certs(ssl.Purpose.SERVER_AUTH)
        return context
    except (OSError, ssl.SSLError) as exc:
        raise CertificateConfigurationError("Could not load TLS CA configuration.") from exc


def _usage_dict(usage: Any) -> dict[str, int]:
    if usage is None:
        return {}
    result = {}
    for name in ("input_tokens", "output_tokens", "total_tokens"):
        value = getattr(usage, name, None)
        if type(value) is int and value >= 0:
            result[name] = value
    details = getattr(usage, "input_tokens_details", None)
    cached = getattr(details, "cached_tokens", None)
    if type(cached) is int and cached >= 0:
        result["cached_input_tokens"] = cached
        if "input_tokens" in result:
            result["uncached_input_tokens"] = max(0, result["input_tokens"] - cached)
    return result
