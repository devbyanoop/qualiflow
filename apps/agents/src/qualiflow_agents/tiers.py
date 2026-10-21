# Stand-in for packages/model-presets (§21 of the main plan) — this
# dict IS the "provider preset" §15.3 describes, just inlined here
# since apps/agents is the only consumer so far. Promote it to its own
# package once a second consumer needs the same mapping.
#
# Using Groq here, not the OpenAI preset the main plan defaults to —
# this is exactly the pluggability §15.3 describes (each tenant maps
# tiers to whichever provider they've actually got a key for); it just
# means our first REAL preset is Groq's, not OpenAI's. LiteLLM's
# "groq/<model>" prefix routes there, reading GROQ_API_KEY from the
# environment automatically (no extra wiring needed beyond .env).
_GROQ_PRESET = {
    "qf-fast": "groq/openai/gpt-oss-20b",
    "qf-balanced": "groq/openai/gpt-oss-120b",
    "qf-strong": "groq/openai/gpt-oss-120b",
}


def resolve_tier(tier: str) -> str:
    """Tasks call this with a tier name ('qf-fast'), never a model
    string — the whole point of ADR-008 (tiers, not models). Swapping
    providers later means changing this one function, not every call
    site."""
    try:
        return _GROQ_PRESET[tier]
    except KeyError:
        raise ValueError(f"Unknown tier '{tier}'. Known tiers: {list(_GROQ_PRESET)}") from None
