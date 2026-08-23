"""PDF text extraction with page-level metadata."""
import os

from langchain_community.document_loaders import PyPDFLoader


class DocumentLoadError(Exception):
    """Raised when a PDF cannot be read or is not a valid PDF."""


def load_pdf(file_path):
    """Load a PDF file and return Documents with source/page metadata.

    Every page becomes one Document (so the page number is never lost),
    and empty pages are skipped safely.
    """
    name = os.path.basename(file_path)
    try:
        documents = PyPDFLoader(file_path).load()
    except DocumentLoadError:
        raise
    except Exception as exc:
        raise DocumentLoadError(
            f"Could not read '{name}'. It may be corrupted, encrypted, or "
            f"not a valid PDF. ({exc})"
        ) from exc

    cleaned = []
    for doc in documents:
        if not doc.page_content.strip():
            continue
        doc.metadata["source"] = file_path
        # PyPDFLoader pages are 0-based; show humans a 1-based page number.
        doc.metadata["page"] = int(doc.metadata.get("page", 0)) + 1
        cleaned.append(doc)

    return cleaned
