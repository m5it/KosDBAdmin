"""Utility helpers for KosDBAdmin."""

from typing import Any


def format_value(value: Any) -> str:
    """Convert a value to a display string."""
    if value is None:
        return "NULL"
    if isinstance(value, (list, dict)):
        import json
        return json.dumps(value)
    return str(value)


def parse_simple_result(text: str) -> str:
    """Strip OK: prefix for status messages."""
    if text.startswith("OK:"):
        return text[3:].strip()
    return text
