"""Post-fill PDF verification."""

from __future__ import annotations

import re
from pathlib import Path

import fitz

from uscis_pdf_ops.core.normalize import field_values_map, load_field_info

TYPE_NAMES = {
    fitz.PDF_WIDGET_TYPE_TEXT: "text",
    fitz.PDF_WIDGET_TYPE_CHECKBOX: "checkbox",
    fitz.PDF_WIDGET_TYPE_RADIOBUTTON: "radio",
    fitz.PDF_WIDGET_TYPE_COMBOBOX: "combobox",
    fitz.PDF_WIDGET_TYPE_LISTBOX: "listbox",
}

UNCHECKED_VALUES = {"Off", "/Off", "off", "", "False", "false", "No", "no", None}


def read_pdf_widgets(pdf_path: str | Path) -> dict[str, list[dict]]:
    """Read widget records from a filled PDF."""
    doc = fitz.open(str(pdf_path))
    widgets_by_name: dict[str, list[dict]] = {}
    for page_idx, page in enumerate(doc):
        for widget in page.widgets():
            name = widget.field_name
            if not name:
                continue
            record = {
                "field_name": name,
                "field_value": widget.field_value,
                "field_type": widget.field_type,
                "field_type_name": TYPE_NAMES.get(widget.field_type, "unknown"),
                "page": page_idx + 1,
                "text_maxlen": getattr(widget, "text_maxlen", 0) or 0,
                "rect": list(widget.rect),
            }
            if widget.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                try:
                    record["on_state"] = widget.on_state()
                except Exception:
                    record["on_state"] = None
            widgets_by_name.setdefault(name, []).append(record)
    doc.close()
    return widgets_by_name


def _is_checkbox_checked(value, on_state=None) -> bool:
    if isinstance(value, bool):
        return value
    value_str = str(value).strip() if value is not None else ""
    if value_str in UNCHECKED_VALUES:
        return False
    if on_state and value_str == on_state:
        return True
    return bool(value_str)


def _intended_means_checked(intended_value, field_info_entry=None) -> bool:
    if field_info_entry:
        unchecked = field_info_entry.get("unchecked_value", "/Off")
        if str(intended_value) == str(unchecked):
            return False
        checked = field_info_entry.get("checked_value")
        if checked and str(intended_value) == str(checked):
            return True
    value_str = str(intended_value).strip() if intended_value is not None else ""
    return value_str not in UNCHECKED_VALUES and bool(value_str)


def _compare_checkbox(field_id, intended_value, widget_records, field_info_entry=None):
    widget = widget_records[0]
    actual = widget["field_value"]
    on_state = widget.get("on_state")
    want_checked = _intended_means_checked(intended_value, field_info_entry)
    actually_checked = _is_checkbox_checked(actual, on_state)
    if want_checked == actually_checked:
        return None
    if want_checked and not actually_checked:
        hint = ""
        if on_state:
            hint = f" The field's on_state is '{on_state}'."
        elif field_info_entry and field_info_entry.get("checked_value"):
            hint = f" field_info says checked_value is '{field_info_entry['checked_value']}'."
        return {
            "field_id": field_id,
            "issue_type": "CHECKBOX_UNCHECKED",
            "expected": str(intended_value),
            "actual": str(actual) if actual else "(empty)",
            "message": f"Checkbox should be checked but isn't.{hint}",
        }
    return {
        "field_id": field_id,
        "issue_type": "VALUE_MISMATCH",
        "expected": str(intended_value),
        "actual": str(actual),
        "message": "Checkbox should be unchecked but is checked.",
    }


def _compare_radio(field_id, intended_value, widget_records, field_info_entry=None):
    actual_values = [record["field_value"] for record in widget_records]
    actual_str = ""
    for value in actual_values:
        candidate = str(value).strip() if value else ""
        if candidate and candidate not in UNCHECKED_VALUES:
            actual_str = candidate
            break
    intended_str = str(intended_value).strip()
    if actual_str == intended_str or actual_str.lstrip("/") == intended_str.lstrip("/"):
        return None
    if not actual_str or actual_str in UNCHECKED_VALUES:
        options_hint = ""
        if field_info_entry and field_info_entry.get("radio_options"):
            options_hint = f" Available options: {[item['value'] for item in field_info_entry['radio_options']]}."
        return {
            "field_id": field_id,
            "issue_type": "FIELD_EMPTY",
            "expected": intended_str,
            "actual": "(none selected)",
            "message": f"Radio group has no selection.{options_hint}",
        }
    return {
        "field_id": field_id,
        "issue_type": "VALUE_MISMATCH",
        "expected": intended_str,
        "actual": actual_str,
        "message": f"Radio group value is '{actual_str}', expected '{intended_str}'.",
    }


def _compare_text(field_id, intended_value, widget_records, strict=False):
    widget = widget_records[0]
    actual = widget["field_value"]
    actual_str = str(actual) if actual else ""
    intended_str = str(intended_value)
    if strict:
        actual_cmp = actual_str
        intended_cmp = intended_str
    else:
        actual_cmp = re.sub(r"\s+", " ", actual_str).strip()
        intended_cmp = re.sub(r"\s+", " ", intended_str).strip()
    if actual_cmp == intended_cmp:
        return None
    if not actual_cmp and intended_cmp:
        return {
            "field_id": field_id,
            "issue_type": "FIELD_EMPTY",
            "expected": intended_str[:80],
            "actual": "(empty)",
            "message": f"Field is empty. Expected {len(intended_str)} chars of text.",
        }
    maxlen = widget.get("text_maxlen", 0)
    if intended_cmp.startswith(actual_cmp) and len(actual_cmp) < len(intended_cmp):
        return {
            "field_id": field_id,
            "issue_type": "TRUNCATED",
            "expected": intended_str[:80],
            "actual": actual_str[:80],
            "message": f"Value truncated from {len(intended_str)} to {len(actual_str)} chars.",
        }
    if maxlen > 0 and len(intended_str) > maxlen:
        return {
            "field_id": field_id,
            "issue_type": "TRUNCATED",
            "expected": intended_str[:80],
            "actual": actual_str[:80],
            "message": f"Value exceeds MaxLen={maxlen}.",
        }
    return {
        "field_id": field_id,
        "issue_type": "VALUE_MISMATCH",
        "expected": intended_str[:80],
        "actual": actual_str[:80],
        "message": f"Value mismatch. Expected '{intended_str[:50]}', got '{actual_str[:50]}'.",
    }


def _compare_choice(field_id, intended_value, widget_records, field_info_entry=None):
    actual = widget_records[0]["field_value"]
    actual_str = str(actual).strip() if actual else ""
    intended_str = str(intended_value).strip()
    if actual_str == intended_str:
        return None
    if not actual_str:
        options_hint = ""
        if field_info_entry and field_info_entry.get("choice_options"):
            options_hint = f" Available options: {[item.get('value', item.get('text', '')) for item in field_info_entry['choice_options'][:10]]}."
        return {
            "field_id": field_id,
            "issue_type": "FIELD_EMPTY",
            "expected": intended_str,
            "actual": "(empty)",
            "message": f"Dropdown/list has no selection.{options_hint}",
        }
    return {
        "field_id": field_id,
        "issue_type": "VALUE_MISMATCH",
        "expected": intended_str,
        "actual": actual_str,
        "message": f"Dropdown value is '{actual_str}', expected '{intended_str}'.",
    }


def verify_filled_pdf(
    pdf_path: str | Path,
    field_values,
    field_info=None,
    strict: bool = False,
) -> dict[str, object]:
    """Verify a filled PDF against intended values."""
    intended_map = field_values_map(field_values)
    field_info_map = {}
    if field_info is not None:
        field_info_map = {item["field_id"]: item for item in load_field_info(field_info) if item.get("field_id")}
    widgets_by_name = read_pdf_widgets(pdf_path)

    issues = []
    verified_fields = []
    fields_not_in_pdf = 0
    for field_id, intended_value in intended_map.items():
        if field_id not in widgets_by_name:
            fields_not_in_pdf += 1
            issues.append(
                {
                    "field_id": field_id,
                    "issue_type": "FIELD_NOT_FOUND",
                    "expected": intended_value[:80],
                    "actual": "(field does not exist in PDF)",
                    "message": f"Field '{field_id}' not found in the PDF.",
                }
            )
            continue
        widget_records = widgets_by_name[field_id]
        field_type = widget_records[0]["field_type"]
        field_info_entry = field_info_map.get(field_id)
        if field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
            issue = _compare_checkbox(field_id, intended_value, widget_records, field_info_entry)
        elif field_type == fitz.PDF_WIDGET_TYPE_RADIOBUTTON:
            issue = _compare_radio(field_id, intended_value, widget_records, field_info_entry)
        elif field_type in (fitz.PDF_WIDGET_TYPE_COMBOBOX, fitz.PDF_WIDGET_TYPE_LISTBOX):
            issue = _compare_choice(field_id, intended_value, widget_records, field_info_entry)
        else:
            issue = _compare_text(field_id, intended_value, widget_records, strict)
        if issue:
            issues.append(issue)
        else:
            actual = widget_records[0]["field_value"]
            verified_fields.append({"field_id": field_id, "status": "ok", "value": str(actual)[:80] if actual else ""})

    doc = fitz.open(str(pdf_path))
    barcode_pattern = re.compile(r"(?i)(barcode|PDF417)")
    barcode_count = sum(
        1 for page in doc for widget in page.widgets()
        if widget.field_name and barcode_pattern.search(widget.field_name)
    )
    doc.close()

    return {
        "summary": {
            "total_intended": len(intended_map),
            "verified_ok": len(verified_fields),
            "issues_found": len(issues),
            "fields_not_in_pdf": fields_not_in_pdf,
        },
        "barcode_count": barcode_count,
        "issues": issues,
        "verified_fields": verified_fields,
    }
