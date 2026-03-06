"""Utilities for fitting text into PDF form widgets."""

from __future__ import annotations

import textwrap
from dataclasses import dataclass

import fitz


@dataclass
class FieldSpec:
    """Specification for a text field."""

    name: str
    width: float
    height: float
    font_size: float
    is_multiline: bool
    max_chars_per_line: int
    max_lines: int


class PDFTextFitter:
    """Approximate text fitting helper backed by widget dimensions."""

    char_width_ratio = 0.55
    line_height_ratio = 1.2

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.field_specs: dict[str, FieldSpec] = {}
        self._analyze_fields()

    def _analyze_fields(self) -> None:
        doc = fitz.open(self.pdf_path)
        for page in doc:
            for widget in page.widgets():
                if widget.field_type != fitz.PDF_WIDGET_TYPE_TEXT:
                    continue
                rect = widget.rect
                font_size = widget.text_fontsize or 10.0
                is_multiline = bool(widget.field_flags & fitz.PDF_TX_FIELD_IS_MULTILINE)
                char_width = font_size * self.char_width_ratio
                max_chars = int(rect.width / char_width) if char_width else 0
                line_height = font_size * self.line_height_ratio
                max_lines = max(1, int(rect.height / line_height))
                self.field_specs[widget.field_name] = FieldSpec(
                    name=widget.field_name,
                    width=rect.width,
                    height=rect.height,
                    font_size=font_size,
                    is_multiline=is_multiline,
                    max_chars_per_line=max_chars,
                    max_lines=max_lines,
                )
        doc.close()

    def get_field_spec(self, field_name: str) -> FieldSpec | None:
        return self.field_specs.get(field_name)

    def fit_text(
        self,
        field_name: str,
        text: str,
        min_font_size: float = 7.0,
        truncate_suffix: str = "...",
    ) -> tuple[str, float, bool]:
        spec = self.get_field_spec(field_name)
        if not spec:
            return text, 10.0, False
        if not spec.is_multiline:
            return self._fit_single_line(text, spec, truncate_suffix)
        return self._fit_multiline(text, spec, min_font_size, truncate_suffix)

    def _fit_single_line(self, text: str, spec: FieldSpec, truncate_suffix: str) -> tuple[str, float, bool]:
        clean = text.replace("\n", " ").strip()
        if len(clean) <= spec.max_chars_per_line:
            return clean, spec.font_size, False
        for font_size in [spec.font_size - 1, spec.font_size - 2, 8, 7]:
            char_width = font_size * self.char_width_ratio
            max_chars = int(spec.width / char_width) if char_width else 0
            if len(clean) <= max_chars:
                return clean, font_size, False
        max_chars = int(spec.width / (7.0 * self.char_width_ratio))
        truncated = clean[: max_chars - len(truncate_suffix)] + truncate_suffix
        return truncated, 7.0, True

    def _fit_multiline(
        self,
        text: str,
        spec: FieldSpec,
        min_font_size: float,
        truncate_suffix: str,
    ) -> tuple[str, float, bool]:
        font_size = spec.font_size
        while font_size >= min_font_size:
            char_width = font_size * self.char_width_ratio
            max_chars = int(spec.width / char_width) if char_width else 0
            line_height = font_size * self.line_height_ratio
            max_lines = max(1, int(spec.height / line_height))
            wrapped_lines = []
            for paragraph in text.split("\n"):
                if paragraph.strip():
                    wrapped_lines.extend(
                        textwrap.wrap(
                            paragraph,
                            width=max_chars,
                            break_long_words=True,
                            break_on_hyphens=True,
                        )
                        or [""]
                    )
                else:
                    wrapped_lines.append("")
            if len(wrapped_lines) <= max_lines:
                return "\n".join(wrapped_lines), font_size, False
            font_size -= 0.5

        max_chars = int(spec.width / (min_font_size * self.char_width_ratio))
        max_lines = max(1, int(spec.height / (min_font_size * self.line_height_ratio)))
        wrapped_lines = []
        for paragraph in text.split("\n"):
            if paragraph.strip():
                wrapped_lines.extend(textwrap.wrap(paragraph, width=max_chars) or [""])
            else:
                wrapped_lines.append("")

        if len(wrapped_lines) > max_lines:
            wrapped_lines = wrapped_lines[:max_lines]
            last_line = wrapped_lines[-1]
            if len(last_line) + len(truncate_suffix) <= max_chars:
                wrapped_lines[-1] = last_line + truncate_suffix
            else:
                wrapped_lines[-1] = last_line[: -len(truncate_suffix)] + truncate_suffix
            return "\n".join(wrapped_lines), min_font_size, True

        return "\n".join(wrapped_lines), min_font_size, False

