"""Fillable PDF writing strategies."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import fitz
from pypdf import PdfReader, PdfWriter

from uscis_pdf_ops.core.field_info import extract_form_field_info
from uscis_pdf_ops.core.normalize import load_field_info, normalize_field_values
from uscis_pdf_ops.core.overflow import check_text_overflow
from uscis_pdf_ops.core.text_fit import PDFTextFitter
from uscis_pdf_ops.core.verify import verify_filled_pdf


def _monkeypatch_pypdf_method() -> None:
    from pypdf.constants import FieldDictionaryAttributes
    from pypdf.generic import DictionaryObject

    original_get_inherited = DictionaryObject.get_inherited

    def patched_get_inherited(self, key: str, default=None):
        result = original_get_inherited(self, key, default)
        if key == FieldDictionaryAttributes.Opt:
            if isinstance(result, list) and all(isinstance(value, list) and len(value) == 2 for value in result):
                result = [item[0] for item in result]
        return result

    DictionaryObject.get_inherited = patched_get_inherited


def _field_info_map(field_info_list):
    return {item["field_id"]: item for item in field_info_list if item.get("field_id")}


def validate_field_values(field_values, field_info_list) -> None:
    """Validate field ids, page hints, and enumerated values."""
    info_map = _field_info_map(field_info_list)
    errors = []
    for field in normalize_field_values(field_values):
        existing = info_map.get(field["field_id"])
        if not existing:
            errors.append(f"`{field['field_id']}` is not a valid field ID")
            continue
        if field.get("page") and existing.get("page") and field["page"] != existing["page"]:
            errors.append(
                f"Incorrect page number for `{field['field_id']}` (got {field['page']}, expected {existing['page']})"
            )
        value = field.get("value")
        if value is None:
            continue
        field_type = existing.get("type")
        if field_type == "checkbox":
            valid = {existing.get("checked_value"), existing.get("unchecked_value")}
            if str(value) not in {str(item) for item in valid if item is not None}:
                errors.append(
                    f'Invalid value "{value}" for checkbox field "{field["field_id"]}". '
                    f'Use "{existing.get("checked_value")}" or "{existing.get("unchecked_value")}".'
                )
        elif field_type == "radio_group":
            valid = [option["value"] for option in existing.get("radio_options", [])]
            if str(value) not in {str(item) for item in valid}:
                errors.append(
                    f'Invalid value "{value}" for radio group field "{field["field_id"]}". Valid values are: {valid}'
                )
        elif field_type == "choice":
            valid = [option["value"] for option in existing.get("choice_options", [])]
            if str(value) not in {str(item) for item in valid}:
                errors.append(
                    f'Invalid value "{value}" for choice field "{field["field_id"]}". Valid values are: {valid}'
                )
    if errors:
        raise ValueError("; ".join(errors))


def _fill_with_pypdf(input_pdf: str | Path, field_values, output_path: str | Path) -> dict[str, object]:
    _monkeypatch_pypdf_method()
    normalized = normalize_field_values(field_values)
    fields_by_page: dict[int, dict[str, object]] = {}
    fields_filled = 0
    for field in normalized:
        if "value" not in field or field.get("value") is None:
            continue
        page = field.get("page")
        if page is None:
            continue
        fields_by_page.setdefault(page, {})[field["field_id"]] = field["value"]
        fields_filled += 1

    reader = PdfReader(str(input_pdf))
    writer = PdfWriter(clone_from=reader)
    for page_number, page_fields in fields_by_page.items():
        writer.update_page_form_field_values(
            writer.pages[page_number - 1],
            page_fields,
            auto_regenerate=False,
        )
    writer.set_need_appearances_writer(True)
    with Path(output_path).open("wb") as handle:
        writer.write(handle)
    return {"strategy_used": "pypdf", "fields_filled": fields_filled}


def _looks_truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip() not in {"", "Off", "/Off", "false", "False", "0", "No", "no", "N", "None"}


def _checkbox_checked_value(field_info_entry) -> object:
    """Return the most reliable checked value for PyMuPDF checkbox writes."""
    if field_info_entry:
        checked = field_info_entry.get("checked_value")
        if checked not in (None, ""):
            return checked
    return True


def _fill_with_pymupdf(input_pdf: str | Path, field_values, output_path: str | Path, field_info_list, autofit: bool) -> dict[str, object]:
    value_map = {item["field_id"]: item.get("value") for item in normalize_field_values(field_values)}
    info_map = _field_info_map(field_info_list)
    text_fitter = PDFTextFitter(str(input_pdf)) if autofit else None
    doc = fitz.open(str(input_pdf))
    fields_filled = 0
    for page in doc:
        for widget in page.widgets():
            field_name = widget.field_name
            if field_name not in value_map:
                continue
            value = value_map[field_name]
            if value is None:
                continue
            field_info = info_map.get(field_name, {})
            if widget.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                if _looks_truthy(value):
                    # Some USCIS checkboxes expose an encoded On state such as
                    # "#20APT#20" that does not persist when written back via
                    # PyMuPDF. The extracted checked export value is the stable
                    # write target, and falling back to True works for simpler
                    # widgets.
                    desired = _checkbox_checked_value(field_info)
                else:
                    desired = field_info.get("unchecked_value", "Off")
                widget.field_value = desired
            elif widget.field_type == fitz.PDF_WIDGET_TYPE_RADIOBUTTON:
                widget.field_value = str(value)
            elif widget.field_type in (fitz.PDF_WIDGET_TYPE_COMBOBOX, fitz.PDF_WIDGET_TYPE_LISTBOX):
                widget.field_value = str(value)
            else:
                text_value = str(value)
                if autofit and text_fitter is not None:
                    fitted_text, font_size, _ = text_fitter.fit_text(field_name, text_value)
                    widget.text_fontsize = font_size
                    widget.field_value = fitted_text
                else:
                    widget.field_value = text_value
            widget.update()
            fields_filled += 1
    doc.save(str(output_path), garbage=0, deflate=True)
    doc.close()
    return {"strategy_used": "pymupdf", "fields_filled": fields_filled}


def _escape_for_fdf(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )


def _pdftk_command() -> str | None:
    return shutil.which("pdftk") or shutil.which("pdftk-java")


def _fill_with_pdftk(input_pdf: str | Path, field_values, output_path: str | Path) -> dict[str, object]:
    pdftk = _pdftk_command()
    if not pdftk:
        raise RuntimeError("pdftk is not available")
    value_map = {item["field_id"]: item.get("value") for item in normalize_field_values(field_values) if item.get("value") is not None}
    with tempfile.NamedTemporaryFile("w", suffix=".fdf", delete=False, encoding="latin1") as handle:
        handle.write("%FDF-1.2\n1 0 obj\n<<\n/FDF <<\n/Fields [\n")
        for field_name, value in value_map.items():
            text = str(value)
            if _looks_truthy(text) and text not in {"Off", "/Off"}:
                if any(ch in text for ch in " /()"):
                    handle.write(f"<< /T ({field_name}) /V ({_escape_for_fdf(text)}) >>\n")
                else:
                    handle.write(f"<< /T ({field_name}) /V /{text} >>\n")
            else:
                handle.write(f"<< /T ({field_name}) /V /Off >>\n")
        handle.write("]\n>>\n>>\nendobj\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF")
        fdf_path = handle.name
    try:
        subprocess.run(
            [pdftk, str(input_pdf), "fill_form", fdf_path, "output", str(output_path), "need_appearances"],
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        Path(fdf_path).unlink(missing_ok=True)
    return {"strategy_used": "pdftk", "fields_filled": len(value_map)}


def _choose_auto_strategy(input_pdf: str | Path, field_values, field_info_list, autofit: bool) -> str:
    info_map = _field_info_map(field_info_list)
    if any(
        info_map.get(field["field_id"], {}).get("type") in {"checkbox", "radio_group", "choice"}
        for field in normalize_field_values(field_values)
        if field.get("value") is not None
    ):
        return "pymupdf"
    if autofit:
        overflow = check_text_overflow(input_pdf, field_values, field_info_list)
        if overflow["overflow_count"] > 0:
            return "pymupdf"
    return "pypdf"


def fill_form(
    input_pdf: str | Path,
    field_values,
    output_path: str | Path | None = None,
    strategy: str = "auto",
    autofit: bool = True,
    field_info=None,
) -> dict[str, object]:
    """Fill a PDF using the requested strategy and verify the result."""
    source = Path(input_pdf)
    destination = Path(output_path) if output_path else source.with_name(f"{source.stem}.filled.pdf")
    field_info_list = load_field_info(field_info) if field_info is not None else extract_form_field_info(source)
    validate_field_values(field_values, field_info_list)

    primary = strategy
    if strategy == "auto":
        primary = _choose_auto_strategy(source, field_values, field_info_list, autofit)

    attempts = [primary]
    if strategy == "auto":
        if primary == "pypdf":
            attempts.append("pymupdf")
            if _pdftk_command():
                attempts.append("pdftk")
        elif primary == "pymupdf" and _pdftk_command():
            attempts.append("pdftk")

    warnings = []
    last_report = None
    last_strategy = None
    for index, attempt in enumerate(dict.fromkeys(attempts)):
        target = destination if index == len(dict.fromkeys(attempts)) - 1 else Path(tempfile.NamedTemporaryFile(suffix=".pdf", delete=False).name)
        try:
            if attempt == "pypdf":
                fill_result = _fill_with_pypdf(source, field_values, target)
            elif attempt == "pymupdf":
                fill_result = _fill_with_pymupdf(source, field_values, target, field_info_list, autofit)
            elif attempt == "pdftk":
                fill_result = _fill_with_pdftk(source, field_values, target)
            else:
                raise ValueError(f"Unknown fill strategy: {attempt}")
        except Exception as exc:
            warnings.append(f"{attempt} failed: {exc}")
            continue

        last_strategy = fill_result["strategy_used"]
        report = verify_filled_pdf(target, field_values, field_info_list)
        last_report = report
        if report["summary"]["issues_found"] == 0 or strategy != "auto":
            if target != destination:
                target.replace(destination)
            return {
                "output_path": str(destination),
                "strategy_used": fill_result["strategy_used"],
                "fields_filled": fill_result["fields_filled"],
                "warnings": warnings,
                "verification": {
                    "total_intended": report["summary"]["total_intended"],
                    "issues_found": report["summary"]["issues_found"],
                    "issues": report["issues"],
                },
            }
        warnings.append(f"{attempt} verification found {report['summary']['issues_found']} issue(s); trying fallback.")
        if target != destination:
            target.unlink(missing_ok=True)

    raise RuntimeError(
        f"Unable to produce a clean filled PDF. Last strategy={last_strategy}, last report={last_report}, warnings={warnings}"
    )
