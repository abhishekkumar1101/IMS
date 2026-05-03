"""Gemini 2.5 Flash Lite — incident summarizer.

- One-line natural language summary per incident, surfaced on the Live Feed.
- Wrapped in a circuit breaker so a Gemini outage cannot stall the dashboard.
- Result is cached via `RedisStore.set_cached_summary` (5-min TTL by default).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import pybreaker

log = logging.getLogger("ims.gemini")


class GeminiSummarizer:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash-lite") -> None:
        self.api_key = api_key
        self.model_name = model
        self._client = None
        self._breaker = pybreaker.CircuitBreaker(fail_max=5, reset_timeout=30)
        if api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                self._client = genai.GenerativeModel(model)
                log.info("Gemini summarizer configured (model=%s)", model)
            except Exception as e:  # noqa: BLE001
                log.exception("Gemini init failed: %s", e)
        else:
            log.info("GEMINI_API_KEY not set — summarizer disabled")

    @property
    def is_configured(self) -> bool:
        return self._client is not None

    async def summarize(self, incident: dict[str, Any], signals: list[dict[str, Any]]) -> str | None:
        if not self.is_configured:
            return None
        sample = signals[:8]
        prompt = (
            "You are an SRE assistant. Summarize this incident in ONE concise sentence (max 160 chars). "
            "Be specific about the failing component and the most likely cause. Do not start with 'The incident'.\n\n"
            f"Component: {incident['component_id']} ({incident['component_kind']})\n"
            f"Severity: {incident['severity']}\n"
            f"Signal count: {incident['signal_count']}\n"
            f"Recent signals (max 8):\n"
            + "\n".join(f"- [{s.get('severity','?')}] {s.get('message','')[:200]}" for s in sample)
        )
        try:
            return await asyncio.get_running_loop().run_in_executor(None, self._call, prompt)
        except pybreaker.CircuitBreakerError:
            log.warning("Gemini circuit OPEN — skipping")
            return None
        except Exception as e:  # noqa: BLE001
            log.warning("Gemini call failed: %s", e)
            return None

    def _call(self, prompt: str) -> str:
        @self._breaker
        def _inner() -> str:
            resp = self._client.generate_content(  # type: ignore[union-attr]
                prompt,
                generation_config={"temperature": 0.2, "max_output_tokens": 80},
            )
            return (resp.text or "").strip().replace("\n", " ")[:240]
        return _inner()
