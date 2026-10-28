"""A tiny JSON-schema subset: validate + deterministic repair. No third-party dependency.

Supported keywords: type, enum, required, properties, additionalProperties(false), items, minItems, maxItems,
minLength, maxLength, minimum, maximum, default. That is all the agent schemas use.
"""
from __future__ import annotations

from typing import Any

_TYPES = {
    "string": str, "boolean": bool, "array": list, "object": dict,
}


def _is_type(v: Any, t: str) -> bool:
    if t == "integer":
        return isinstance(v, int) and not isinstance(v, bool)
    if t == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    if t == "null":
        return v is None
    return isinstance(v, _TYPES[t])


def _types(schema: dict) -> list[str]:
    t = schema.get("type")
    return [t] if isinstance(t, str) else list(t or [])


def validate(data: Any, schema: dict, path: str = "$") -> list[str]:
    """Return a list of human-readable problems ([] means valid)."""
    errs: list[str] = []
    types = _types(schema)
    if types and not any(_is_type(data, t) for t in types):
        return [f"{path}: expected {'/'.join(types)}, got {type(data).__name__}"]
    if "enum" in schema and data not in schema["enum"]:
        errs.append(f"{path}: must be one of {schema['enum']}")
    if isinstance(data, str):
        if len(data.strip()) < schema.get("minLength", 0):
            errs.append(f"{path}: text is empty or too short")
        if "maxLength" in schema and len(data) > schema["maxLength"]:
            errs.append(f"{path}: text longer than {schema['maxLength']}")
    if isinstance(data, (int, float)) and not isinstance(data, bool):
        if "minimum" in schema and data < schema["minimum"]:
            errs.append(f"{path}: must be >= {schema['minimum']}")
        if "maximum" in schema and data > schema["maximum"]:
            errs.append(f"{path}: must be <= {schema['maximum']}")
    if isinstance(data, list):
        if len(data) < schema.get("minItems", 0):
            errs.append(f"{path}: needs at least {schema['minItems']} items")
        if "maxItems" in schema and len(data) > schema["maxItems"]:
            errs.append(f"{path}: at most {schema['maxItems']} items")
        if "items" in schema:
            for i, v in enumerate(data):
                errs += validate(v, schema["items"], f"{path}[{i}]")
    if isinstance(data, dict):
        for k in schema.get("required", []):
            if k not in data:
                errs.append(f"{path}.{k}: required field is missing")
        props = schema.get("properties", {})
        for k, sub in props.items():
            if k in data:
                errs += validate(data[k], sub, f"{path}.{k}")
        if schema.get("additionalProperties") is False:
            for k in data:
                if k not in props:
                    errs.append(f"{path}.{k}: unexpected field")
    return errs


def repair(data: Any, schema: dict) -> Any:
    """Fix what can be fixed without asking the model again: wrong scalar types, unknown fields, over-long lists,
    out-of-range numbers, a lone value where a list is expected. Never invents content for required fields."""
    types = _types(schema)
    if isinstance(data, str) and "integer" in types:
        try:
            data = int(float(data.strip().replace("،", ".")))
        except ValueError:
            pass
    elif isinstance(data, str) and "number" in types:
        try:
            data = float(data.strip())
        except ValueError:
            pass
    if isinstance(data, float) and "integer" in types and "number" not in types:
        data = int(round(data))
    if isinstance(data, (int, float)) and not isinstance(data, bool) and "string" in types and "number" not in types and "integer" not in types:
        data = str(data)
    if isinstance(data, str) and "boolean" in types:
        data = data.strip().lower() in ("true", "yes", "1", "بله")
    if "array" in types and not isinstance(data, list) and data is not None:
        data = [data]
    if isinstance(data, (int, float)) and not isinstance(data, bool):
        if "minimum" in schema and data < schema["minimum"]:
            data = schema["minimum"]
        if "maximum" in schema and data > schema["maximum"]:
            data = schema["maximum"]
    if isinstance(data, str):
        data = data.strip()
        if "maxLength" in schema and len(data) > schema["maxLength"]:
            data = data[: schema["maxLength"]].rstrip()
    if isinstance(data, list):
        items = schema.get("items")
        if items:
            data = [repair(v, items) for v in data]
        if "maxItems" in schema:
            data = data[: schema["maxItems"]]
    if isinstance(data, dict):
        props = schema.get("properties", {})
        out = {}
        for k, v in data.items():
            if k in props:
                out[k] = repair(v, props[k])
            elif schema.get("additionalProperties") is not False:
                out[k] = v
        for k, sub in props.items():
            if k not in out and "default" in sub:
                out[k] = sub["default"]
        data = out
    return data
