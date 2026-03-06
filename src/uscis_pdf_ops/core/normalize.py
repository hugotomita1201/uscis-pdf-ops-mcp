"""Shared normalization helpers for field value payloads."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json(value: str | Path | list[dict[str, Any]] | dict[str, Any]) -> Any:
    """Load JSON from a path, JSON string, or already-parsed object."""
    if isinstance(value, Path):
        return json.loads(value.read_text())
    if isinstance(value, str):
        candidate = Path(value)
        if candidate.exists():
            return json.loads(candidate.read_text())
        return json.loads(value)
    return value


def normalize_field_values(raw: Any) -> list[dict[str, Any]]:
    """Normalize all accepted field_values shapes to one list format."""
    payload = load_json(raw)

    if isinstance(payload, dict) and "field_values" in payload:
        payload = payload["field_values"]

    if isinstance(payload, list):
        normalized: list[dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, dict):
                raise ValueError("Each field_values entry must be an object.")
            field_id = item.get("field_id")
            if not field_id:
                raise ValueError("Each field_values entry must include field_id.")
            normalized.append(
                {
                    "field_id": str(field_id),
                    "value": item.get("value"),
                    "page": item.get("page"),
                    "description": item.get("description"),
                }
            )
        return normalized

    if isinstance(payload, dict):
        normalized = []
        for field_id, value in payload.items():
            normalized.append(
                {
                    "field_id": str(field_id),
                    "value": value,
                    "page": None,
                    "description": None,
                }
            )
        return normalized

    raise ValueError("field_values must be a list, dict, wrapped object, path, or JSON string.")


def field_values_map(raw: Any) -> dict[str, str]:
    """Return normalized field values as a simple string map."""
    mapped: dict[str, str] = {}
    for item in normalize_field_values(raw):
        value = item.get("value")
        if value is not None:
            mapped[item["field_id"]] = str(value)
    return mapped


def load_field_info(raw: str | Path | list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Load field_info from path/JSON/object form."""
    payload = load_json(raw)
    if not isinstance(payload, list):
        raise ValueError("field_info must be a list of field metadata objects.")
    return payload
