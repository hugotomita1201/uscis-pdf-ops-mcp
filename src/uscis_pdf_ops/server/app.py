"""FastMCP server definition."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from uscis_pdf_ops.core.fill import fill_form
from uscis_pdf_ops.core.fillability import check_fillable_fields
from uscis_pdf_ops.core.field_info import extract_form_field_info, write_field_info
from uscis_pdf_ops.core.normalize import load_field_info, load_json
from uscis_pdf_ops.core.overflow import check_text_overflow
from uscis_pdf_ops.core.verify import verify_filled_pdf

mcp = FastMCP("uscis-pdf-ops-mcp")


def _resolve_json_arg(raw: Any):
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return load_json(raw)
    except Exception:
        return raw


@mcp.tool(name="check_fillable_fields")
def check_fillable_fields_tool(pdf_path: str) -> dict[str, object]:
    """Check whether a PDF has fillable form fields."""
    return check_fillable_fields(pdf_path)


@mcp.tool(name="extract_form_field_info")
def extract_form_field_info_tool(pdf_path: str, output_path: str | None = None) -> dict[str, object]:
    """Extract fillable field metadata, including labels when available."""
    if output_path:
        return write_field_info(pdf_path, output_path)
    fields = extract_form_field_info(pdf_path)
    return {"field_count": len(fields), "fields": fields}


@mcp.tool(name="check_text_overflow")
def check_text_overflow_tool(
    pdf_path: str,
    field_values: str | dict | list,
    field_info: str | list | None = None,
    font_size: float | None = None,
    font_name: str | None = None,
) -> dict[str, object]:
    """Estimate whether text will overflow text widgets."""
    return check_text_overflow(
        pdf_path=pdf_path,
        field_values=_resolve_json_arg(field_values),
        field_info=_resolve_json_arg(field_info),
        font_size=font_size,
        font_name=font_name,
    )


@mcp.tool(name="fill_form")
def fill_form_tool(
    pdf_path: str,
    field_values: str | dict | list,
    output_path: str | None = None,
    strategy: str = "auto",
    autofit: bool = True,
    field_info: str | list | None = None,
) -> dict[str, object]:
    """Fill a fillable PDF and verify the result."""
    return fill_form(
        input_pdf=pdf_path,
        field_values=_resolve_json_arg(field_values),
        output_path=output_path,
        strategy=strategy,
        autofit=autofit,
        field_info=_resolve_json_arg(field_info),
    )


@mcp.tool(name="verify_filled_pdf")
def verify_filled_pdf_tool(
    filled_pdf_path: str,
    field_values: str | dict | list,
    field_info: str | list | None = None,
    strict: bool = False,
) -> dict[str, object]:
    """Verify that the filled PDF matches the intended field values."""
    report = verify_filled_pdf(
        pdf_path=filled_pdf_path,
        field_values=_resolve_json_arg(field_values),
        field_info=_resolve_json_arg(field_info),
        strict=strict,
    )
    return {
        "total_intended": report["summary"]["total_intended"],
        "issues_found": report["summary"]["issues_found"],
        "issues": report["issues"][:20],
        "barcode_count": report["barcode_count"],
        "message": "All fields verified successfully. PDF is ready." if report["summary"]["issues_found"] == 0 else f"{report['summary']['issues_found']} issue(s) found.",
    }


def run_server(transport: str = "stdio") -> None:
    """Run the FastMCP server."""
    mcp.run(transport=transport)
