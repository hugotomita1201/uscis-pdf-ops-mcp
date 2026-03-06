"""Fillability checks for PDF forms."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader


def check_fillable_fields(pdf_path: str | Path) -> dict[str, object]:
    """Return whether a PDF has fillable fields and how many were found."""
    resolved = Path(pdf_path)
    reader = PdfReader(str(resolved))
    fields = reader.get_fields() or {}
    fillable = bool(fields)
    message = (
        "This PDF has fillable form fields"
        if fillable
        else "This PDF does not have fillable form fields"
    )
    return {
        "fillable": fillable,
        "field_count": len(fields),
        "message": message,
        "pdf_path": str(resolved),
    }

