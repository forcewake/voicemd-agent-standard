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
SELECTOR_CATEGORIES = {"audiences", "surfaces", "tones"}


def _is_dormant_selector_overlay(path: tuple[str, ...]) -> bool:
    """Return whether ``path`` is inside an unapplied contextual override.

    Source resolution must retain null tombstones in these subtrees so they can
    delete inherited contract fields later, when the selector is applied.
    """

    if len(path) >= 2 and path[0] in SELECTOR_CATEGORIES:
        return True
    return len(path) >= 3 and path[0] == "profiles" and path[2] == "overrides"


def _append_unique(base: list[Any], override: list[Any]) -> list[Any]:
    result = deepcopy(base)
    for item in override:
        if item not in result:
            result.append(deepcopy(item))
    return result


def _normalized_copy(
    value: Any,
    path: tuple[str, ...],
    *,
    append_unique_arrays: bool,
) -> Any:
    if isinstance(value, dict):
        return deep_merge(
            {},
            value,
            path,
            append_unique_arrays=append_unique_arrays,
        )
    if isinstance(value, list):
        return [
            _normalized_copy(
                item,
                path + (str(index),),
                append_unique_arrays=append_unique_arrays,
            )
            if isinstance(item, (dict, list))
            else deepcopy(item)
            for index, item in enumerate(value)
        ]
    return deepcopy(value)


def _merge_by_id(
    base: list[Any],
    override: list[Any],
    path: tuple[str, ...],
    *,
    append_unique_arrays: bool,
) -> list[Any]:
    result = deepcopy(base)
    preserve_tombstones = append_unique_arrays and _is_dormant_selector_overlay(path)
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
            if preserve_tombstones:
                tombstone = deepcopy(item)
                if item_id in positions:
                    result[positions[item_id]] = tombstone
                else:
                    positions[item_id] = len(result)
                    result.append(tombstone)
                continue
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
            if (
                preserve_tombstones
                and isinstance(result[index], dict)
                and result[index].get("disabled") is True
            ):
                result[index] = _normalized_copy(
                    item,
                    path + (item_id,),
                    append_unique_arrays=append_unique_arrays,
                )
            else:
                result[index] = deep_merge(
                    result[index],
                    item,
                    path + (item_id,),
                    append_unique_arrays=append_unique_arrays,
                )
        else:
            positions[item_id] = len(result)
            result.append(
                _normalized_copy(
                    item,
                    path + (item_id,),
                    append_unique_arrays=append_unique_arrays,
                )
            )
    return result


def deep_merge(
    base: Any,
    override: Any,
    path: tuple[str, ...] = (),
    *,
    append_unique_arrays: bool = True,
) -> Any:
    """Merge broad guidance with a more specific override.

    ``None`` is a delete operator when it appears as an object value. Source
    overlays append the small set of additive arrays by default and retain
    dormant selector tombstones. Selector overlays pass
    ``append_unique_arrays=False`` so a context can narrow an inherited list
    such as ``language.allowed`` and consume its ID-based deletions.
    """
    if base is None:
        return _normalized_copy(
            override,
            path,
            append_unique_arrays=append_unique_arrays,
        )
    if override is None:
        return None
    if isinstance(base, dict) and isinstance(override, dict):
        result = deepcopy(base)
        for key, value in override.items():
            if value is None:
                if append_unique_arrays and _is_dormant_selector_overlay(path):
                    result[key] = None
                else:
                    result.pop(key, None)
                continue
            if key in result:
                result[key] = deep_merge(
                    result[key],
                    value,
                    path + (str(key),),
                    append_unique_arrays=append_unique_arrays,
                )
            else:
                child_path = path + (str(key),)
                if isinstance(value, list) and str(key) in MERGE_BY_ID_KEYS:
                    result[key] = _merge_by_id(
                        [],
                        value,
                        child_path,
                        append_unique_arrays=append_unique_arrays,
                    )
                else:
                    result[key] = _normalized_copy(
                        value,
                        child_path,
                        append_unique_arrays=append_unique_arrays,
                    )
        return result
    if isinstance(base, list) and isinstance(override, list):
        if path and path[-1] in MERGE_BY_ID_KEYS:
            return _merge_by_id(
                base,
                override,
                path,
                append_unique_arrays=append_unique_arrays,
            )
        if append_unique_arrays and path in APPEND_UNIQUE_PATHS:
            return _append_unique(base, override)
        return deepcopy(override)
    return deepcopy(override)
