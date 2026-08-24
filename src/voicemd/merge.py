from __future__ import annotations

from copy import deepcopy
from typing import Any

APPEND_UNIQUE_PATHS = {
    ("activation", "include"),
    ("activation", "exclude"),
    ("authority", "may_control"),
    ("authority", "must_not_control"),
    ("language", "allowed"),
    ("lexicon", "preferred"),
    ("lexicon", "forbidden"),
    ("formatting", "avoid"),
    ("speech", "avoid"),
}
MERGE_BY_ID_KEYS = {"rules", "tests", "examples"}


def _append_unique(base: list[Any], override: list[Any]) -> list[Any]:
    result = deepcopy(base)
    for item in override:
        if item not in result:
            result.append(deepcopy(item))
    return result


def _merge_by_id(base: list[Any], override: list[Any], path: tuple[str, ...]) -> list[Any]:
    result = deepcopy(base)
    positions = {
        item.get("id"): index
        for index, item in enumerate(result)
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    for item in override:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            result.append(deepcopy(item))
            continue
        item_id = item["id"]
        if item.get("disabled") is True:
            if item_id in positions:
                result.pop(positions[item_id])
                positions = {
                    current.get("id"): index
                    for index, current in enumerate(result)
                    if isinstance(current, dict) and isinstance(current.get("id"), str)
                }
            continue
        if item_id in positions:
            index = positions[item_id]
            result[index] = deep_merge(result[index], item, path + (item_id,))
        else:
            positions[item_id] = len(result)
            result.append(deepcopy(item))
    return result


def deep_merge(base: Any, override: Any, path: tuple[str, ...] = ()) -> Any:
    """Merge broad guidance with a more specific override."""
    if base is None:
        return deepcopy(override)
    if override is None:
        return None
    if isinstance(base, dict) and isinstance(override, dict):
        result = deepcopy(base)
        for key, value in override.items():
            if key in result:
                result[key] = deep_merge(result[key], value, path + (str(key),))
            else:
                result[key] = deepcopy(value)
        return result
    if isinstance(base, list) and isinstance(override, list):
        if path and path[-1] in MERGE_BY_ID_KEYS:
            return _merge_by_id(base, override, path)
        if path in APPEND_UNIQUE_PATHS:
            return _append_unique(base, override)
        return deepcopy(override)
    return deepcopy(override)
