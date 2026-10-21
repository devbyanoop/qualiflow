import json
import time
from contextlib import contextmanager
from typing import Any

# Fallback pricing for models LiteLLM's cost map doesn't resolve yet.
# groq/openai/gpt-oss-20b trips this because the model string's nested
# "openai/" confuses LiteLLM's provider-prefix stripping (it reports
# custom_llm_provider=openai instead of groq) -- the pricing likely IS
# in LiteLLM's map under a different key, this is a lookup miss, not
# truly unpriced data. Verified against three independent third-party
# aggregators (CloudZero, Sim, FutureAGI — the latter citing LiteLLM
# itself as its source) on 2026-10-21; USD per 1M tokens, (input, output).
_FALLBACK_PRICING_PER_MILLION_TOKENS = {
    "groq/openai/gpt-oss-20b": (0.075, 0.30),
}


def _fallback_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    pricing = _FALLBACK_PRICING_PER_MILLION_TOKENS.get(model)
    if pricing is None:
        return None
    input_price, output_price = pricing
    return (prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000


@contextmanager
def log_llm_call(tier: str, model: str):
    """Langfuse would normally capture this. Without it (§0), this is
    the crude-but-honest substitute: one JSON line per call, with the
    same underlying numbers a trace UI would show — just printed
    instead of rendered."""
    start = time.perf_counter()
    record: dict[str, Any] = {"tier": tier, "model": model}

    def _finish(response: Any) -> None:
        record["latency_ms"] = round((time.perf_counter() - start) * 1000, 1)
        record["prompt_tokens"] = response.usage.prompt_tokens
        record["completion_tokens"] = response.usage.completion_tokens
        import litellm

        try:
            record["cost_usd"] = round(litellm.completion_cost(completion_response=response), 6)
        except Exception as exc:
            fallback = _fallback_cost(record["model"], record["prompt_tokens"], record["completion_tokens"])
            if fallback is not None:
                record["cost_usd"] = round(fallback, 6)
                record["cost_source"] = "manual fallback — see _FALLBACK_PRICING_PER_MILLION_TOKENS"
            else:
                # Genuinely unpriced, not just a lookup miss — log that
                # honestly rather than fabricate a number.
                record["cost_usd"] = None
                record["cost_unavailable_reason"] = str(exc)
        print(json.dumps(record))

    try:
        yield _finish
    except Exception as exc:
        record["error"] = str(exc)
        print(json.dumps(record))
        raise
