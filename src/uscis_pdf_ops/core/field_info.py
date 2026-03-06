"""Extract field metadata and nearby labels from fillable PDFs."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pypdf import PdfReader


def get_full_annotation_field_id(annotation):
    """Return full field name by walking parent annotations."""
    components = []
    while annotation:
        field_name = annotation.get("/T")
        if field_name:
            components.append(field_name)
        annotation = annotation.get("/Parent")
    return ".".join(reversed(components)) if components else None


def _strip_pdf_name_prefix(value):
    if isinstance(value, str) and value.startswith("/"):
        return value[1:]
    return value


def _make_field_dict(field, field_id):
    field_dict = {"field_id": field_id}
    field_type = field.get("/FT")
    if field_type == "/Tx":
        field_dict["type"] = "text"
    elif field_type == "/Btn":
        field_dict["type"] = "checkbox"
        states = field.get("/_States_", [])
        if len(states) == 2:
            if "/Off" in states:
                checked = states[0] if states[0] != "/Off" else states[1]
                field_dict["checked_value"] = _strip_pdf_name_prefix(checked)
                field_dict["unchecked_value"] = "Off"
            else:
                field_dict["checked_value"] = _strip_pdf_name_prefix(states[0])
                field_dict["unchecked_value"] = _strip_pdf_name_prefix(states[1])
    elif field_type == "/Ch":
        field_dict["type"] = "choice"
        field_dict["choice_options"] = [
            {"value": state[0], "text": state[1]}
            for state in field.get("/_States_", [])
        ]
    else:
        field_dict["type"] = f"unknown ({field_type})"
    return field_dict


def _sort_key(field):
    if "radio_options" in field:
        rect = field["radio_options"][0]["rect"] or [0, 0, 0, 0]
    else:
        rect = field.get("rect") or [0, 0, 0, 0]
    return [field.get("page"), [-rect[1], rect[0]]]


def _extract_text_spans(fitz_page):
    spans = []
    for block in fitz_page.get_text("dict")["blocks"]:
        if "lines" not in block:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                text = span["text"].strip()
                if text:
                    bbox = span["bbox"]
                    spans.append(
                        {
                            "text": text,
                            "x": bbox[0],
                            "y": bbox[1],
                            "x2": bbox[2],
                            "y2": bbox[3],
                        }
                    )
    spans.sort(key=lambda item: (item["y"], item["x"]))
    return spans


def _is_noise_label(text):
    token = text.strip()
    if len(token) <= 1:
        return True
    if re.match(r"^(\d+[a-z]?|[A-Za-z])\.$", token):
        return True
    return token.lower() in {"yes", "no", "n/a", "none", "or"}


def _find_context(widget_y, widget_x, text_spans, field_type="text"):
    part = None
    section = None
    label = None
    candidates = []

    for i, span in enumerate(text_spans):
        if span["y"] > widget_y + 5:
            break
        if re.match(r"^Part \d+\.", span["text"]):
            desc_parts = [span["text"]]
            for j in range(i + 1, len(text_spans)):
                if abs(text_spans[j]["y"] - span["y"]) < 3:
                    desc_parts.append(text_spans[j]["text"])
                else:
                    break
            part = " ".join(desc_parts)

        if span["x"] < 45 and re.match(r"^\d+[a-z]?\.$", span["text"]) and span["y"] <= widget_y + 5:
            desc_parts = [span["text"]]
            for j in range(i + 1, len(text_spans)):
                if abs(text_spans[j]["y"] - span["y"]) < 3:
                    desc_parts.append(text_spans[j]["text"])
                else:
                    break
            section = " ".join(desc_parts)

        if -5 <= widget_y - span["y"] < 20 and abs(span["x"] - widget_x) < 200:
            candidates.append((i, span))

    if candidates:
        if field_type in {"text", "choice"}:
            same_line_tol = 3
            same_line_left = [
                (idx, span) for idx, span in candidates
                if abs(span["y"] - widget_y) <= same_line_tol
                and span["x2"] <= widget_x + 5
                and not _is_noise_label(span["text"])
            ]
            above = [
                (idx, span) for idx, span in candidates
                if widget_y - span["y"] > same_line_tol
                and not _is_noise_label(span["text"])
            ]
            if same_line_left:
                _, best = min(same_line_left, key=lambda pair: widget_x - pair[1]["x2"])
                label = best["text"]
            elif above:
                closest_y = max(span["y"] for _, span in above)
                closest_line = [
                    (idx, span) for idx, span in above
                    if abs(span["y"] - closest_y) < same_line_tol
                ]
                _, best = min(closest_line, key=lambda pair: abs(pair[1]["x"] - widget_x))
                label = best["text"]
            else:
                non_noise = [
                    (idx, span) for idx, span in candidates
                    if not _is_noise_label(span["text"])
                ]
                if non_noise:
                    label = non_noise[-1][1]["text"]
        else:
            label = candidates[-1][1]["text"]

    return part, section, label


def _enrich_with_labels(field_info_list, pdf_path: str | Path) -> None:
    try:
        import fitz
    except ImportError:
        return

    doc = fitz.open(str(pdf_path))
    fitz_widget_positions = {}
    for page_idx in range(len(doc)):
        page = doc[page_idx]
        for widget in page.widgets():
            name = widget.field_name
            if name:
                fitz_widget_positions[name] = (page_idx, widget.rect.y0, widget.rect.x0)

    text_spans_by_page = {page_idx: _extract_text_spans(doc[page_idx]) for page_idx in range(len(doc))}

    for field in field_info_list:
        position = fitz_widget_positions.get(field.get("field_id"))
        if not position:
            continue
        page_idx, widget_y, widget_x = position
        part, section, label = _find_context(
            widget_y,
            widget_x,
            text_spans_by_page.get(page_idx, []),
            field.get("type", "text"),
        )
        if part:
            field["part"] = part
        if section:
            field["section_label"] = section
        if label:
            field["label"] = label

    doc.close()


def extract_form_field_info(pdf_path: str | Path) -> list[dict[str, object]]:
    """Return ordered field metadata for a fillable PDF."""
    reader = PdfReader(str(pdf_path))
    fields = reader.get_fields() or {}
    field_info_by_id = {}
    possible_radio_names = set()

    for field_id, field in fields.items():
        if field.get("/Kids"):
            if field.get("/FT") == "/Btn":
                possible_radio_names.add(field_id)
            continue
        field_info_by_id[field_id] = _make_field_dict(field, field_id)

    radio_fields_by_id = {}
    for page_index, page in enumerate(reader.pages):
        for annotation in page.get("/Annots", []):
            field_id = get_full_annotation_field_id(annotation)
            if field_id in field_info_by_id:
                field_info_by_id[field_id]["page"] = page_index + 1
                field_info_by_id[field_id]["rect"] = annotation.get("/Rect")
            elif field_id in possible_radio_names:
                try:
                    on_values = [value for value in annotation["/AP"]["/N"] if value != "/Off"]
                except KeyError:
                    continue
                if len(on_values) == 1:
                    radio_fields_by_id.setdefault(
                        field_id,
                        {
                            "field_id": field_id,
                            "type": "radio_group",
                            "page": page_index + 1,
                            "radio_options": [],
                        },
                    )["radio_options"].append(
                        {
                            "value": _strip_pdf_name_prefix(on_values[0]),
                            "rect": annotation.get("/Rect"),
                        }
                    )

    fields_with_location = [
        field for field in field_info_by_id.values() if "page" in field
    ] + list(radio_fields_by_id.values())
    fields_with_location.sort(key=_sort_key)
    _enrich_with_labels(fields_with_location, pdf_path)
    return fields_with_location


def write_field_info(pdf_path: str | Path, output_path: str | Path) -> dict[str, object]:
    """Persist field metadata to JSON and return a compact summary."""
    field_info = extract_form_field_info(pdf_path)
    destination = Path(output_path)
    destination.write_text(json.dumps(field_info, indent=2))
    return {
        "field_count": len(field_info),
        "output_path": str(destination),
        "fields": field_info,
    }

