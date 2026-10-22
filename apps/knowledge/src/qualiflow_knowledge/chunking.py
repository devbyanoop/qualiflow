import re

from pydantic import BaseModel

# Matches a Markdown ATX heading (# through ######) at the start of a
# line -- Docling's export_to_markdown() uses these for every detected
# heading, and plain hand-written Markdown (the raw-text /ingest path)
# uses the same syntax, so one chunker serves both ingestion paths.
_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


class ChunkDraft(BaseModel):
    heading: str | None
    content: str


def chunk_by_heading(markdown: str) -> list[ChunkDraft]:
    """Structure-aware chunking by heading (plan §5.1), replacing M0.6's
    "whole document is one chunk". Each chunk is one heading's section:
    the heading text followed by everything up to the next heading at
    any level. Content before the first heading (if any) becomes its
    own chunk with heading=None, rather than being dropped."""
    matches = list(_HEADING_PATTERN.finditer(markdown))

    if not matches:
        text = markdown.strip()
        return [ChunkDraft(heading=None, content=text)] if text else []

    chunks: list[ChunkDraft] = []

    preamble = markdown[: matches[0].start()].strip()
    if preamble:
        chunks.append(ChunkDraft(heading=None, content=preamble))

    for i, match in enumerate(matches):
        heading_text = match.group(2).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        body = markdown[start:end].strip()
        content = f"{heading_text}\n\n{body}" if body else heading_text
        chunks.append(ChunkDraft(heading=heading_text, content=content))

    return chunks
