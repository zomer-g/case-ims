"""Shared field classification utilities."""
import re
import json as _json


def classify_value(val) -> tuple:
    if val is None:
        return None, False
    if isinstance(val, bool):
        return "boolean", False
    if isinstance(val, (int, float)):
        return "numeric", False
    if isinstance(val, list):
        if not val:
            return "array_keyword", True
        if isinstance(val[0], dict):
            return "array_object", True
        return "array_keyword", True
    if isinstance(val, dict):
        return None, False
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None, False
        try:
            float(s)
            return "numeric", False
        except (ValueError, TypeError):
            pass
        if re.match(r"^\d{4}-\d{2}-\d{2}", s):
            return "date", False
        if len(s) > 200:
            return "text", False
        return "keyword", False
    return None, False


def classify_json_value(raw_json_value) -> tuple:
    if raw_json_value is None:
        return None, False
    if isinstance(raw_json_value, bool):
        return "boolean", False
    if isinstance(raw_json_value, (int, float)):
        return "numeric", False

    s = str(raw_json_value).strip()
    if not s:
        return None, False

    if s.startswith("["):
        try:
            arr = _json.loads(s)
            return classify_value(arr)
        except (ValueError, TypeError):
            pass

    if s.startswith("{"):
        return None, False

    if s.lower() in ("true", "false"):
        return "boolean", False

    return classify_value(s)
