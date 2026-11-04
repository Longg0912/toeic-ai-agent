"""Document extraction, normalization, chunking and persistence."""

from __future__ import annotations

import hashlib
import logging
import re
import uuid

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
import unicodedata

from docx import Document as DocxDocument
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import Document, DocumentChunk


logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"

SUPPORTED_EXTENSIONS = {
    "pdf": ".pdf",
    "docx": ".docx",
    "txt": ".txt",
    "md": ".md",
    "html": ".html",
}


class DocumentProcessingError(Exception):
    """Raised when a document cannot be processed."""


class DocumentNotFoundError(DocumentProcessingError):
    """Raised when the requested document does not exist."""


@dataclass(frozen=True)
class ExtractedPage:
    """Text extracted from one source page or section."""

    page_number: int | None
    text: str


@dataclass(frozen=True)
class TextChunk:
    """A normalized chunk ready for database storage."""

    chunk_index: int
    page_number: int | None
    content: str


class HTMLTextExtractor(HTMLParser):
    """Extract readable text while ignoring scripts and styles."""

    BLOCK_TAGS = {
        "address",
        "article",
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "li",
        "p",
        "section",
        "tr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag in {"script", "style"}:
            self.skip_depth += 1
            return

        if self.skip_depth == 0 and tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self.skip_depth > 0:
            self.skip_depth -= 1
            return

        if self.skip_depth == 0 and tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_depth == 0:
            self.parts.append(data)

    def get_text(self) -> str:
        return "".join(self.parts)


def normalize_text(text: str) -> str:
    """Normalize extracted text without removing paragraph boundaries."""

    if not isinstance(text, str):
        raise TypeError("Text content must be a string.")

    text = unicodedata.normalize("NFC", text)
    text = text.replace("\x00", "")
    text = text.replace("\u00a0", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    normalized_lines: list[str] = []

    for line in text.split("\n"):
        line = re.sub(r"[ \t\f\v]+", " ", line)
        normalized_lines.append(line.strip())

    text = "\n".join(normalized_lines)

    # Keep at most one blank line between paragraphs.
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _read_text_file(file_path: Path) -> str:
    """Read a text file using common encodings."""

    raw_content = file_path.read_bytes()

    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return raw_content.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise DocumentProcessingError(
        "The text file encoding is not supported."
    )


def _extract_pdf(file_path: Path) -> list[ExtractedPage]:
    """Extract text from PDF pages."""

    try:
        reader = PdfReader(str(file_path))

        if reader.is_encrypted:
            raise DocumentProcessingError(
                "Password-protected PDF files are not supported."
            )

        pages: list[ExtractedPage] = []

        for page_number, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""

            if page_text.strip():
                pages.append(
                    ExtractedPage(
                        page_number=page_number,
                        text=page_text,
                    )
                )

        return pages

    except DocumentProcessingError:
        raise

    except Exception as exc:
        raise DocumentProcessingError(
            "Could not extract text from the PDF file."
        ) from exc


def _extract_docx(file_path: Path) -> list[ExtractedPage]:
    """Extract paragraphs and table content from DOCX."""

    try:
        document = DocxDocument(str(file_path))

        parts: list[str] = []

        for paragraph in document.paragraphs:
            if paragraph.text.strip():
                parts.append(paragraph.text)

        for table in document.tables:
            for row in table.rows:
                cells = [
                    cell.text.strip()
                    for cell in row.cells
                    if cell.text.strip()
                ]

                if cells:
                    parts.append(" | ".join(cells))

        return [
            ExtractedPage(
                page_number=None,
                text="\n\n".join(parts),
            )
        ]

    except Exception as exc:
        raise DocumentProcessingError(
            "Could not extract text from the DOCX file."
        ) from exc


def _extract_html(file_path: Path) -> list[ExtractedPage]:
    """Extract visible text from an HTML file."""

    try:
        html_content = _read_text_file(file_path)

        parser = HTMLTextExtractor()
        parser.feed(html_content)
        parser.close()

        return [
            ExtractedPage(
                page_number=None,
                text=parser.get_text(),
            )
        ]

    except DocumentProcessingError:
        raise

    except Exception as exc:
        raise DocumentProcessingError(
            "Could not extract text from the HTML file."
        ) from exc


def extract_document_pages(
    file_path: Path,
    document_type: str,
) -> list[ExtractedPage]:
    """Extract text from a supported document."""

    file_path = Path(file_path)

    if not file_path.exists() or not file_path.is_file():
        raise DocumentProcessingError(
            "The document file does not exist."
        )

    expected_extension = SUPPORTED_EXTENSIONS.get(document_type)

    if expected_extension is None:
        raise DocumentProcessingError(
            "The document type is not supported."
        )

    if file_path.suffix.lower() != expected_extension:
        raise DocumentProcessingError(
            "The file extension does not match the document type."
        )

    if document_type == "pdf":
        pages = _extract_pdf(file_path)

    elif document_type == "docx":
        pages = _extract_docx(file_path)

    elif document_type in {"txt", "md"}:
        pages = [
            ExtractedPage(
                page_number=None,
                text=_read_text_file(file_path),
            )
        ]

    elif document_type == "html":
        pages = _extract_html(file_path)

    else:
        raise DocumentProcessingError(
            "The document type is not supported."
        )

    normalized_pages = [
        ExtractedPage(
            page_number=page.page_number,
            text=normalize_text(page.text),
        )
        for page in pages
    ]

    return [
        page
        for page in normalized_pages
        if page.text
    ]


def _split_single_text(
    text: str,
    chunk_size: int,
    overlap: int,
) -> list[str]:
    """Split text into overlapping character-based chunks."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError(
            "overlap must be non-negative and smaller than chunk_size."
        )

    text = normalize_text(text)

    if not text:
        return []

    chunks: list[str] = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))

        if end < len(text):
            minimum_boundary = start + int(chunk_size * 0.6)

            newline_boundary = text.rfind(
                "\n",
                minimum_boundary,
                end,
            )

            space_boundary = text.rfind(
                " ",
                minimum_boundary,
                end,
            )

            boundary = max(
                newline_boundary,
                space_boundary,
            )

            if boundary > start:
                end = boundary

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        next_start = max(start + 1, end - overlap)

        while next_start < len(text) and text[next_start].isspace():
            next_start += 1

        start = next_start

    return chunks


def split_pages_into_chunks(
    pages: Iterable[ExtractedPage],
    chunk_size: int = 1200,
    overlap: int = 150,
) -> list[TextChunk]:
    """Split extracted pages while preserving source page numbers."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError(
            "overlap must be non-negative and smaller than chunk_size."
        )

    result: list[TextChunk] = []

    for page in pages:
        page_text = normalize_text(page.text)

        if not page_text:
            continue

        page_chunks = _split_single_text(
            text=page_text,
            chunk_size=chunk_size,
            overlap=overlap,
        )

        for content in page_chunks:
            result.append(
                TextChunk(
                    chunk_index=len(result),
                    page_number=page.page_number,
                    content=content,
                )
            )

    return result


def _resolve_storage_path(
    data_dir: Path,
    storage_path: str,
) -> Path:
    """Resolve a document path without allowing directory traversal."""

    data_root = Path(data_dir).resolve()
    relative_path = Path(storage_path)

    if relative_path.is_absolute():
        raise DocumentProcessingError(
            "Document storage path must be relative to the data directory."
        )

    resolved_path = (data_root / relative_path).resolve()

    if not resolved_path.is_relative_to(data_root):
        raise DocumentProcessingError(
            "Document storage path is outside the data directory."
        )

    return resolved_path


def _sha256_file(file_path: Path) -> str:
    """Calculate the SHA-256 hash of the original file."""

    digest = hashlib.sha256()

    with file_path.open("rb") as file:
        for block in iter(
            lambda: file.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def _sha256_text(content: str) -> str:
    """Calculate the SHA-256 hash of normalized chunk content."""

    return hashlib.sha256(
        content.encode("utf-8")
    ).hexdigest()


def _make_vector_id(
    document_id: int,
    chunk_index: int,
    content_hash: str,
) -> str:
    """Create a deterministic ID for future ChromaDB indexing."""

    identity = (
        f"toeic-document:{document_id}:"
        f"chunk:{chunk_index}:"
        f"hash:{content_hash}"
    )

    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            identity,
        )
    )


def process_document(
    session: Session,
    document_id: int,
    chunk_size: int = 1200,
    overlap: int = 150,
    data_dir: Path = DATA_DIR,
) -> int:
    """Extract, chunk and persist one document.

    The service owns its transaction and commits on success.
    The caller should provide a dedicated database session.
    """

    document = session.get(Document, document_id)

    if document is None:
        raise DocumentNotFoundError(
            "Document was not found."
        )

    # Mark the document as currently processing.
    document.processing_status = "processing"
    document.processing_error = None
    session.commit()

    try:
        file_path = _resolve_storage_path(
            data_dir=data_dir,
            storage_path=document.storage_path,
        )

        actual_hash = _sha256_file(file_path)

        if actual_hash != document.content_hash:
            raise DocumentProcessingError(
                "The stored file hash does not match the database record."
            )

        pages = extract_document_pages(
            file_path=file_path,
            document_type=document.document_type,
        )

        chunks = split_pages_into_chunks(
            pages=pages,
            chunk_size=chunk_size,
            overlap=overlap,
        )

        if not chunks:
            raise DocumentProcessingError(
                "No readable text was found in the document."
            )

        # Remove old chunks before saving the new version.
        document.chunks.clear()
        session.flush()

        for chunk in chunks:
            chunk_hash = _sha256_text(chunk.content)

            session.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.page_number,
                    content=chunk.content,
                    content_hash=chunk_hash,
                    token_count=None,
                    vector_id=_make_vector_id(
                        document_id=document.id,
                        chunk_index=chunk.chunk_index,
                        content_hash=chunk_hash,
                    ),
                )
            )

        # Text chunks are saved. The document is waiting
        # for embedding and vector indexing in later steps.
        document.processing_status = "pending"
        document.processing_error = None

        session.commit()

        return len(chunks)

    except Exception as exc:
        session.rollback()

        failed_document = session.get(
            Document,
            document_id,
        )

        if failed_document is not None:
            failed_document.processing_status = "failed"
            failed_document.processing_error = str(exc)[:2000]

            session.commit()

        if isinstance(exc, DocumentProcessingError):
            raise

        logger.exception(
            "Document processing failed: document_id=%s",
            document_id,
        )

        raise DocumentProcessingError(
            "An unexpected error occurred while processing the document."
        ) from exc