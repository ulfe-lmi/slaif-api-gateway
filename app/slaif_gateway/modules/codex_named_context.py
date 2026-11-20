"""Pure lowering for validated, client-authored Codex context outputs.

The pinned AdditionalContextToolOutput is a function output with a name
but no call ID. It supplies context, not a completion of a model tool call.
It must never acquire a synthetic call, replay ownership, or instruction role.
"""

import copy
import json
from collections.abc import Mapping
from typing import Any


def is_codex_named_context_output(item: Mapping[str, Any]) -> bool:
    return (
        item.get("type") == "function_call_output"
        and item.get("call_id") is None
        and isinstance(item.get("name"), str)
        and bool(item["name"])
    )


def lower_codex_named_context_output(item: Mapping[str, Any]) -> dict[str, Any]:
    """Lower an already bounded/validated context output to ordinary user data.

    JSON-encoded labels retain the name/namespace without giving the label
    markup or instruction authority. Text and image parts retain their order
    and values. The optional inert item ID remains transient input metadata.
    """
    identity = {"name": item["name"]}
    if item.get("namespace") is not None:
        identity["namespace"] = item["namespace"]
    label = "Codex client context " + json.dumps(identity, ensure_ascii=True, separators=(",", ":"))
    output = item["output"]
    parts = [{"type": "input_text", "text": label}]
    if isinstance(output, str):
        parts.append({"type": "input_text", "text": output})
    else:
        parts.extend(copy.deepcopy(output))
    result = {"type": "message", "role": "user", "content": parts}
    if item.get("id") is not None:
        result["id"] = item["id"]
    return result


def lower_codex_named_context_input(value: Any) -> Any:
    """Normalize validated context only after original request controls pass."""
    if not isinstance(value, list):
        return value
    return [
        lower_codex_named_context_output(item)
        if isinstance(item, Mapping) and is_codex_named_context_output(item) else item
        for item in value
    ]
