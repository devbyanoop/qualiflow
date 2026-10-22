import io

from docling.datamodel.base_models import DocumentStream
from docling.document_converter import DocumentConverter

# One converter instance, reused across requests -- Docling loads its
# layout/OCR models on first use; building a new DocumentConverter per
# request would reload them every time.
_converter = DocumentConverter()


def parse_to_markdown(filename: str, data: bytes) -> str:
    """Parses a real PDF/DOCX/XLSX (or anything else Docling supports)
    into Markdown, preserving heading structure -- chunk_by_heading()
    depends on that structure being real ATX headings (#, ##, ...),
    not just plain paragraphs."""
    stream = DocumentStream(name=filename, stream=io.BytesIO(data))
    result = _converter.convert(stream)
    return result.document.export_to_markdown()
