from __future__ import annotations

from pathlib import Path

from uscis_pdf_ops.core.fill import fill_form
from uscis_pdf_ops.core.fillability import check_fillable_fields
from uscis_pdf_ops.core.field_info import extract_form_field_info
from uscis_pdf_ops.core.overflow import check_text_overflow
from uscis_pdf_ops.core.verify import verify_filled_pdf


def _valid_field_values(field_info):
    info_map = {item["field_id"]: item for item in field_info}
    return [
        {"field_id": "full_name", "page": 1, "value": "Homer Simpson"},
        {
            "field_id": "notes",
            "page": 1,
            "value": "A long enough note to test multiline behavior without overflowing the field.",
        },
        {
            "field_id": "consent_box",
            "page": 1,
            "value": info_map["consent_box"]["checked_value"],
        },
        {
            "field_id": "color_group",
            "page": 1,
            "value": info_map["color_group"]["radio_options"][1]["value"],
        },
        {
            "field_id": "status_choice",
            "page": 1,
            "value": info_map["status_choice"]["choice_options"][1]["value"],
        },
    ]


def test_check_fillable_fields(fillable_pdf: Path):
    result = check_fillable_fields(fillable_pdf)
    assert result["fillable"] is True
    assert result["field_count"] >= 4


def test_extract_form_field_info(fillable_pdf: Path):
    field_info = extract_form_field_info(fillable_pdf)
    info_map = {item["field_id"]: item for item in field_info}
    assert info_map["full_name"]["type"] == "text"
    assert info_map["consent_box"]["type"] == "checkbox"
    assert info_map["color_group"]["type"] == "radio_group"
    assert info_map["status_choice"]["type"] == "choice"


def test_check_text_overflow_flags_long_values(fillable_pdf: Path):
    field_info = extract_form_field_info(fillable_pdf)
    result = check_text_overflow(
        pdf_path=fillable_pdf,
        field_info=field_info,
        field_values={
            "notes": "This text is intentionally much longer than the multiline field can safely hold without overflowing and should trigger the overflow checker to flag it immediately."
        },
    )
    assert result["overflow_count"] >= 1


def test_fill_form_accepts_all_supported_field_value_shapes(fillable_pdf: Path, tmp_path: Path):
    field_info = extract_form_field_info(fillable_pdf)
    valid_values = _valid_field_values(field_info)

    list_result = fill_form(fillable_pdf, valid_values, tmp_path / "list.pdf", field_info=field_info)
    assert list_result["verification"]["issues_found"] == 0

    wrapped_result = fill_form(
        fillable_pdf,
        {"field_values": valid_values},
        tmp_path / "wrapped.pdf",
        field_info=field_info,
    )
    assert wrapped_result["verification"]["issues_found"] == 0

    flat_result = fill_form(
        fillable_pdf,
        {item["field_id"]: item["value"] for item in valid_values},
        tmp_path / "flat.pdf",
        field_info=field_info,
    )
    assert flat_result["verification"]["issues_found"] == 0


def test_verify_filled_pdf_reports_field_not_found(fillable_pdf: Path, tmp_path: Path):
    field_info = extract_form_field_info(fillable_pdf)
    output_pdf = tmp_path / "verified.pdf"
    valid_values = _valid_field_values(field_info)
    fill_form(fillable_pdf, valid_values, output_pdf, field_info=field_info)

    report = verify_filled_pdf(
        output_pdf,
        {
            "full_name": "Homer Simpson",
            "missing_field": "should fail",
        },
        field_info=field_info,
    )
    assert report["summary"]["issues_found"] == 1
    assert report["issues"][0]["issue_type"] == "FIELD_NOT_FOUND"

