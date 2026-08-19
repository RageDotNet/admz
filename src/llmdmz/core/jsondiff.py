"""T4.11: structural JSON diff (clarification #24).

Sorted-key canonicalization + a recursive walk producing per-field
changed/added/removed entries. Schemas are compared as parsed JSON trees,
never as raw text. No new dependency.
"""

from __future__ import annotations

from typing import Any


def canonical(value: Any) -> str:
    """Deterministic serialization for stable comparisons."""
    return _canonical(value)


def _canonical(value: Any) -> str:
    if isinstance(value, dict):
        return "{" + ",".join(
            f"{_canonical(k)}:{_canonical(v)}" for k, v in sorted(value.items())
        ) + "}"
    if isinstance(value, list):
        return "[" + ",".join(_canonical(v) for v in value) + "]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return repr(value)
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def diff(old: Any, new: Any, path: str = "") -> list[dict[str, Any]]:
    """Structural diff: entries {op, path, old?, new?} with ops changed/added/removed."""
    entries: list[dict[str, Any]] = []
    if canonical(old) == canonical(new):
        return entries
    label = path or "(root)"
    if isinstance(old, dict) and isinstance(new, dict):
        for key in sorted(set(old) | set(new)):
            child = f"{path}.{key}" if path else key
            if key not in old:
                entries.append({"op": "added", "path": child, "new": new[key]})
            elif key not in new:
                entries.append({"op": "removed", "path": child, "old": old[key]})
            else:
                entries.extend(diff(old[key], new[key], child))
    elif isinstance(old, list) and isinstance(new, list):
        if len(old) != len(new):
            entries.append({"op": "changed", "path": label, "old": old, "new": new})
        else:
            for i, (o, n) in enumerate(zip(old, new, strict=False)):
                entries.extend(diff(o, n, f"{label}[{i}]"))
    else:
        entries.append({"op": "changed", "path": label, "old": old, "new": new})
    return entries


def diff_payloads(old: dict[str, Any], new: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Per-field diff of two version payloads (description, schemas, instructions)."""
    result: dict[str, list[dict[str, Any]]] = {}
    for field in sorted(set(old) | set(new)):
        entries = diff(old.get(field), new.get(field), field)
        if entries:
            result[field] = entries
    return result
