"""Text overflow checks for PDF form widgets."""

from __future__ import annotations

import re
from pathlib import Path

import fitz

from uscis_pdf_ops.core.field_info import extract_form_field_info
from uscis_pdf_ops.core.normalize import field_values_map, load_field_info

_PDF_TO_BASE14 = {
    "CourierNewPS-BoldMT": "cobo",
    "CourierNewPSMT": "cour",
    "CourierStd": "cour",
    "CourierNew": "cour",
    "Courier": "cour",
    "Courier-Bold": "cobo",
    "Courier-Oblique": "coit",
    "Courier-BoldOblique": "cobi",
    "TimesNewRomanPSMT": "tiro",
    "TimesNewRomanPS-BoldMT": "tibo",
    "TimesNewRomanPS-ItalicMT": "tiit",
    "TimesNewRomanPS-BoldItalicMT": "tibi",
    "TimesNewRoman": "tiro",
    "Helvetica": "helv",
    "Helvetica-Bold": "hebo",
    "Helvetica-Oblique": "heit",
    "Helvetica-BoldOblique": "hebi",
    "Helv": "helv",
    "Arial": "helv",
    "ArialMT": "helv",
    "Arial-BoldMT": "hebo",
}


def _normalize_font_name(font_name: str | None) -> str | None:
    if not font_name:
        return font_name
    if font_name.startswith("/"):
        font_name = font_name[1:]
    if "+" in font_name and len(font_name.split("+")[0]) == 6:
        font_name = font_name.split("+", 1)[1]
    return font_name.split(",")[0]


def _get_base14_name(font_name: str | None) -> str | None:
    if not font_name:
        return None
    if font_name in _PDF_TO_BASE14:
        return _PDF_TO_BASE14[font_name]
    normalized = _normalize_font_name(font_name)
    return _PDF_TO_BASE14.get(normalized)


def _extract_pdf_font_cache(pdf_path: str | Path, field_info_map: dict[str, dict]) -> dict[str, dict]:
    doc = fitz.open(str(pdf_path))
    font_cache: dict[str, dict] = {}

    for index in range(1, doc.xref_length()):
        try:
            obj = doc.xref_object(index)
        except Exception:
            continue
        if "/BaseFont" not in obj or "/Widths" not in obj:
            continue
        name_match = re.search(r"/BaseFont\s+/(\S+)", obj)
        if not name_match:
            continue
        font_name = name_match.group(1)
        if font_name in font_cache:
            continue
        widths_match = re.search(r"/Widths\s*\[([^\]]+)\]", obj)
        if not widths_match:
            continue
        try:
            widths = [float(width) for width in widths_match.group(1).split()]
        except ValueError:
            continue
        if not widths:
            continue
        avg_width = sum(widths) / len(widths)
        is_monospace = len(set(widths)) <= 2
        ascent = None
        descent = None
        fd_match = re.search(r"/FontDescriptor\s+(\d+)\s+\d+\s+R", obj)
        if fd_match:
            try:
                fd_obj = doc.xref_object(int(fd_match.group(1)))
                asc_match = re.search(r"/Ascent\s+(-?\d+)", fd_obj)
                desc_match = re.search(r"/Descent\s+(-?\d+)", fd_obj)
                if asc_match:
                    ascent = int(asc_match.group(1))
                if desc_match:
                    descent = int(desc_match.group(1))
            except Exception:
                pass
        font_cache[font_name] = {
            "ascent": ascent,
            "descent": descent,
            "avg_char_width": round(avg_width),
            "is_monospace": is_monospace,
            "base14_name": _get_base14_name(font_name),
        }

    for page in doc:
        for widget in page.widgets():
            if widget.field_type != fitz.PDF_WIDGET_TYPE_TEXT:
                continue
            field_name = widget.field_name
            if field_name in field_info_map:
                field_info_map[field_name]["_pdf_text_font"] = widget.text_font
                field_info_map[field_name]["_pdf_text_fontsize"] = widget.text_fontsize
                field_info_map[field_name]["_pdf_is_multiline"] = bool(
                    widget.field_flags & fitz.PDF_TX_FIELD_IS_MULTILINE
                )
                field_info_map[field_name]["_pdf_text_maxlen"] = getattr(widget, "text_maxlen", 0) or 0

    doc.close()
    return font_cache


def _safe_text_length(text: str, font_name: str, font_size: float, fallback_char_width: float) -> float:
    try:
        return fitz.get_text_length(text, fontname=font_name, fontsize=font_size)
    except Exception:
        return len(text) * fallback_char_width


def _resolve_font_params(field_info: dict, pdf_font_cache: dict | None, font_size: float | None, font_name: str | None):
    if font_size is not None and font_name is not None:
        avg_char_width = _safe_text_length(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,()-/",
            font_name,
            font_size,
            font_size * 0.5,
        ) / 70
        return font_size, avg_char_width, font_size * 1.2, font_name, False, False, 0, "cli_override"

    if pdf_font_cache is not None:
        text_font = field_info.get("_pdf_text_font")
        text_fontsize = field_info.get("_pdf_text_fontsize", 0)
        is_multiline = field_info.get("_pdf_is_multiline", False)
        text_maxlen = field_info.get("_pdf_text_maxlen", 0)
        resolved_size = float(font_size or text_fontsize or 10)
        if text_font:
            font_metrics = pdf_font_cache.get(text_font) or pdf_font_cache.get(_normalize_font_name(text_font))
            if font_metrics:
                ascent = font_metrics.get("ascent")
                descent = font_metrics.get("descent")
                line_height = resolved_size * (ascent - descent) / 1000.0 if ascent is not None and descent is not None else resolved_size * 1.2
                if line_height < resolved_size:
                    line_height = resolved_size * 1.2
                avg_char_width = font_metrics.get("avg_char_width", 500) / 1000.0 * resolved_size
                return (
                    resolved_size,
                    avg_char_width,
                    line_height,
                    font_metrics.get("base14_name") or "helv",
                    font_metrics.get("is_monospace", False),
                    is_multiline,
                    text_maxlen,
                    "pdf_metrics",
                )
            base14 = _get_base14_name(text_font)
            if base14:
                avg_char_width = _safe_text_length(
                    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,()-/",
                    base14,
                    resolved_size,
                    resolved_size * 0.5,
                ) / 70
                return resolved_size, avg_char_width, resolved_size * 1.2, base14, False, is_multiline, text_maxlen, "pdf_base14_fallback"
            return resolved_size, resolved_size * 0.6, resolved_size * 2.0, "helv", False, is_multiline, text_maxlen, "conservative_fallback"

    return 10.0, 10.0 * 0.6, 10.0 * 2.0, "helv", False, False, 0, "conservative_fallback"


def _simulate_wrap(text: str, usable_width: float, font_size: float, font_name: str, is_monospace: bool, avg_char_width: float) -> int:
    words = text.split()
    if not words:
        return 1
    lines = 1
    current_line_width = 0.0
    space_width = avg_char_width if is_monospace else _safe_text_length(" ", font_name, font_size, avg_char_width)
    for word in words:
        word_width = len(word) * avg_char_width if is_monospace else _safe_text_length(word, font_name, font_size, avg_char_width)
        needed = word_width + (space_width if current_line_width > 0 else 0)
        if current_line_width + needed > usable_width and current_line_width > 0:
            lines += 1
            current_line_width = word_width
        else:
            current_line_width += needed
        if current_line_width > usable_width and usable_width > 0:
            extra_lines = int(current_line_width / usable_width)
            lines += extra_lines
            current_line_width -= extra_lines * usable_width
    return lines


def _find_word_boundary_split(text: str, max_chars: int) -> int:
    if len(text) <= max_chars:
        return len(text)
    for index in range(max_chars, max(max_chars - 40, 0), -1):
        if text[index] in " \n\t":
            return index
    return max_chars


def _check_field(text: str, field_width: float, field_height: float, font_size: float, avg_char_width: float, line_height: float, font_name: str, is_monospace: bool, is_multiline: bool) -> dict:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    usable_width = field_width * 0.95
    max_lines = max(1, int(field_height / line_height) - 1) if is_multiline else max(1, int(field_height / line_height))
    max_chars_per_line = int(usable_width / avg_char_width) if avg_char_width > 0 else 999
    max_total_chars = max_chars_per_line * max_lines
    current_chars = len(text)

    if max_lines == 1:
        text_width = len(text) * avg_char_width if is_monospace else _safe_text_length(text, font_name, font_size, avg_char_width)
        fits = text_width <= usable_width
        visual_lines_used = 1
    elif "\n" in text:
        visual_lines_used = 0
        for segment in text.split("\n"):
            if not segment.strip():
                visual_lines_used += 1
            else:
                visual_lines_used += _simulate_wrap(segment, usable_width, font_size, font_name, is_monospace, avg_char_width)
        fits = visual_lines_used <= max_lines
    else:
        visual_lines_used = _simulate_wrap(text, usable_width, font_size, font_name, is_monospace, avg_char_width)
        fits = visual_lines_used <= max_lines

    result = {
        "max_chars_per_line": max_chars_per_line,
        "max_lines": max_lines,
        "lines_used": visual_lines_used,
        "current_chars": current_chars,
        "max_total_chars": max_total_chars,
    }
    if fits:
        result["status"] = "ok"
        return result

    result.update(
        {
            "status": "overflow",
            "chars_over": max(0, current_chars - max_total_chars),
            "split_at": _find_word_boundary_split(text, max_total_chars),
        }
    )
    if max_lines == 1:
        result["message"] = (
            f"Single-line field: text is {current_chars} chars, max ~{max_chars_per_line} chars at {font_size}pt."
        )
    else:
        result["message"] = (
            f"Text overflows at {font_size}pt. Max ~{max_total_chars} chars across {max_lines} lines."
        )
    return result


def check_text_overflow(
    pdf_path: str | Path,
    field_values,
    field_info=None,
    font_size: float | None = None,
    font_name: str | None = None,
) -> dict[str, object]:
    """Check whether text values fit in their corresponding text fields."""
    info_list = load_field_info(field_info) if field_info is not None else extract_form_field_info(pdf_path)
    info_map = {item["field_id"]: item for item in info_list if item.get("field_id")}
    value_map = field_values_map(field_values)
    pdf_font_cache = _extract_pdf_font_cache(pdf_path, info_map)

    fields = []
    overflow_count = 0
    ok_count = 0
    checked_count = 0

    for field_id, value in value_map.items():
        info = info_map.get(field_id)
        if not info or info.get("type") not in {"text", None}:
            continue
        rect = info.get("rect")
        if not rect or len(rect) < 4:
            continue
        field_width = abs(rect[2] - rect[0])
        field_height = abs(rect[3] - rect[1])
        if field_width < 1 or field_height < 1 or not value.strip():
            continue
        checked_count += 1
        resolved = _resolve_font_params(info, pdf_font_cache, font_size, font_name)
        font_size_used, avg_char_width, line_height, fitz_font_name, is_monospace, is_multiline, text_maxlen, source = resolved
        result = _check_field(
            value,
            field_width,
            field_height,
            font_size_used,
            avg_char_width,
            line_height,
            fitz_font_name,
            is_monospace,
            is_multiline,
        )
        if text_maxlen > 0:
            result["max_total_chars"] = min(result["max_total_chars"], text_maxlen)
            if result["current_chars"] > result["max_total_chars"] and result["status"] == "ok":
                result["status"] = "overflow"
                result["chars_over"] = result["current_chars"] - result["max_total_chars"]
                result["message"] = f"Exceeds field maxLen={text_maxlen}. Current: {result['current_chars']} chars."
        result.update(
            {
                "field_id": field_id,
                "value": value[:100] + ("..." if len(value) > 100 else ""),
                "field_width_pt": round(field_width, 1),
                "field_height_pt": round(field_height, 1),
                "font_size_used": font_size_used,
                "font_name_used": info.get("_pdf_text_font", font_name or "unknown"),
                "metrics_source": source,
            }
        )
        if result["status"] == "overflow":
            overflow_count += 1
        else:
            ok_count += 1
        fields.append(result)

    return {
        "fields": fields,
        "overflow_count": overflow_count,
        "ok_count": ok_count,
        "checked_count": checked_count,
    }
