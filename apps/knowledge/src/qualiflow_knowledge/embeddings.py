import httpx

from .settings import settings


def embed(text: str) -> list[float]:
    """Calls the self-hosted TEI service directly over HTTP rather than
    through LiteLLM's embedding wrapper — TEI's /embed is a plain POST,
    and going straight to it keeps this one call transparent rather
    than routed through an abstraction we haven't needed elsewhere yet."""
    response = httpx.post(
        f"{settings.embeddings_url}/embed",
        json={"inputs": text},
        timeout=30,
    )
    response.raise_for_status()
    # TEI returns a list of embeddings (one per input) even for a
    # single string input — [0] is this text's vector.
    return response.json()[0]
