from __future__ import annotations

import ast
from pathlib import Path


ALLOWED_UPSTREAM_BUILDERS = {
    "build_audio_speech_upstream_body",
    "build_audio_transcription_upstream_body",
    "build_audio_translation_upstream_body",
    "build_embeddings_upstream_body",
    "build_conversation_update_upstream_body",
    "build_conversation_items_create_upstream_body",
    "build_conversation_items_query_params",
    "build_chat_completion_upstream_body",
    "build_responses_compact_upstream_body",
    "build_responses_input_tokens_upstream_body",
    "build_responses_input_items_query_params",
    "build_responses_upstream_body",
    "_build_safe_chat_completion_upstream_body",
    "_build_safe_conversation_update_upstream_body",
    "_build_safe_conversation_items_create_upstream_body",
    "_build_safe_conversation_items_query_params",
    "_build_safe_responses_compact_upstream_body",
    "_build_safe_responses_input_tokens_upstream_body",
    "_build_safe_responses_upstream_body",
    "_build_safe_embeddings_upstream_body",
}

ALLOWED_UPSTREAM_BODY_PARAMETERS = {
    ("app/slaif_gateway/services/chat_completion_gateway.py", "_streaming_chat_completion_response", "upstream_body"),
    ("app/slaif_gateway/services/responses_gateway.py", "_streaming_responses_response", "upstream_body"),
    ("app/slaif_gateway/services/audio_gateway.py", "_handle_audio_operation", "provider_request_body"),
    ("app/slaif_gateway/services/embeddings_gateway.py", "handle_embeddings_create", "upstream_body"),
}


def _iter_python_sources() -> list[Path]:
    return sorted(
        p
        for p in [
            *Path("app/slaif_gateway/api").rglob("*.py"),
            *Path("app/slaif_gateway/services").rglob("*.py"),
            *Path("app/slaif_gateway/providers").rglob("*.py"),
        ]
        if p.is_file()
    )


def _extract_provider_request_calls(tree: ast.AST) -> list[tuple[int, list[tuple[str | None, ast.AST]]]]:
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "ProviderRequest":
            body_keywords = []
            for kw in node.keywords:
                if kw.arg == "body":
                    body_keywords.append((None, kw.value))
            calls.append((node.lineno, body_keywords))
        elif isinstance(func, ast.Attribute) and func.attr == "ProviderRequest":
            body_keywords = []
            for kw in node.keywords:
                if kw.arg == "body":
                    body_keywords.append((func.attr, kw.value))
            calls.append((node.lineno, body_keywords))
    return calls


def _name_from_call(callee: ast.AST) -> str | None:
    if isinstance(callee, ast.Name):
        return callee.id
    if isinstance(callee, ast.Attribute):
        return callee.attr
    return None


def _is_allowed_builder_call(expr: ast.AST) -> bool:
    if not isinstance(expr, ast.Call):
        return False
    callee = _name_from_call(expr.func)
    return callee in ALLOWED_UPSTREAM_BUILDERS


def _is_empty_literal_dict(expr: ast.AST) -> bool:
    return isinstance(expr, ast.Dict) and not expr.keys and not expr.values


def _call_lines(function_node: ast.FunctionDef | ast.AsyncFunctionDef, callee_name: str) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(function_node):
        if not isinstance(node, ast.Call):
            continue
        if _name_from_call(node.func) == callee_name:
            lines.append(node.lineno)
    return sorted(lines)


def _find_function(tree: ast.AST, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"Function {name} not found")


def _iter_function_nodes(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _assignment_targets(node: ast.Assign) -> list[str]:
    names: list[str] = []
    for target in node.targets:
        if isinstance(target, ast.Name):
            names.append(target.id)
    return names


def _last_assignment_before(
    function_node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    variable_name: str,
    lineno: int,
) -> ast.Assign | None:
    assignments = [
        node
        for node in ast.walk(function_node)
        if isinstance(node, ast.Assign)
        and node.lineno < lineno
        and variable_name in _assignment_targets(node)
    ]
    if not assignments:
        return None
    return max(assignments, key=lambda node: node.lineno)


def test_provider_request_body_uses_normalized_contract_builders() -> None:
    failing = []
    for path in _iter_python_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function_node in _iter_function_nodes(tree):
            for lineno, body_keywords in _extract_provider_request_calls(function_node):
                for _, value in body_keywords:
                    if _is_empty_literal_dict(value):
                        continue
                    if isinstance(value, ast.Call) and _is_allowed_builder_call(value):
                        continue
                    if isinstance(value, ast.Name):
                        parameter_allowlist_key = (
                            str(path),
                            function_node.name,
                            value.id,
                        )
                        if parameter_allowlist_key in ALLOWED_UPSTREAM_BODY_PARAMETERS:
                            continue
                        assignment = _last_assignment_before(
                            function_node,
                            variable_name=value.id,
                            lineno=lineno,
                        )
                        if assignment is not None and _is_allowed_builder_call(assignment.value):
                            continue
                    failing.append((path, lineno, ast.unparse(value)))
    assert not failing, (
        "ProviderRequest body construction must use canonical upstream-body builders. "
        f"Found non-normalized body sources: {failing}"
    )


def test_normalized_body_is_built_before_rate_limit_and_quota_side_effects() -> None:
    chat_tree = ast.parse(
        Path("app/slaif_gateway/services/chat_completion_gateway.py").read_text(
            encoding="utf-8"
        )
    )
    chat_handler = _find_function(chat_tree, "handle_chat_completion")
    chat_build_lines = _call_lines(chat_handler, "_build_safe_chat_completion_upstream_body")
    assert chat_build_lines, "Chat handler must build the normalized upstream body"
    assert chat_build_lines[0] < _call_lines(chat_handler, "_reserve_redis_rate_limit")[0]
    assert chat_build_lines[0] < _call_lines(chat_handler, "_reserve_chat_completion_quota")[0]

    responses_tree = ast.parse(
        Path("app/slaif_gateway/services/responses_gateway.py").read_text(encoding="utf-8")
    )
    responses_handler = _find_function(responses_tree, "handle_response_create")
    responses_build_lines = _call_lines(responses_handler, "_build_safe_responses_upstream_body")
    assert responses_build_lines, "Responses handler must build the normalized upstream body"
    assert responses_build_lines[0] < _call_lines(responses_handler, "_reserve_redis_rate_limit")[0]
    assert responses_build_lines[0] < _call_lines(responses_handler, "_reserve_responses_quota")[0]

    compact_handler = _find_function(responses_tree, "handle_response_compact")
    compact_build_lines = _call_lines(compact_handler, "_build_safe_responses_compact_upstream_body")
    assert compact_build_lines, "Responses compact handler must build the normalized upstream body"
    assert compact_build_lines[0] < _call_lines(compact_handler, "_reserve_redis_rate_limit")[0]
    assert compact_build_lines[0] < _call_lines(compact_handler, "_reserve_responses_quota")[0]

    input_tokens_handler = _find_function(responses_tree, "handle_response_input_tokens_count")
    input_tokens_build_lines = _call_lines(
        input_tokens_handler, "_build_safe_responses_input_tokens_upstream_body"
    )
    assert input_tokens_build_lines, "Responses input-token handler must build the normalized upstream body"

    conversation_update_handler = _find_function(responses_tree, "handle_conversation_update")
    conversation_update_build_lines = _call_lines(
        conversation_update_handler,
        "_build_safe_conversation_update_upstream_body",
    )
    assert (
        conversation_update_build_lines
    ), "Conversation update handler must build the normalized upstream body"

    conversation_item_create_handler = _find_function(
        responses_tree, "handle_conversation_item_create"
    )
    conversation_item_create_build_lines = _call_lines(
        conversation_item_create_handler,
        "_build_safe_conversation_items_create_upstream_body",
    )
    assert (
        conversation_item_create_build_lines
    ), "Conversation item create handler must build the normalized upstream body"

    conversation_items_list_handler = _find_function(responses_tree, "handle_conversation_items_list")
    conversation_items_list_build_lines = _call_lines(
        conversation_items_list_handler,
        "_build_safe_conversation_items_query_params",
    )
    assert (
        conversation_items_list_build_lines
    ), "Conversation items list handler must build normalized upstream query params"

    conversation_item_retrieve_handler = _find_function(
        responses_tree, "handle_conversation_item_retrieve"
    )
    conversation_item_retrieve_build_lines = _call_lines(
        conversation_item_retrieve_handler,
        "_build_safe_conversation_items_query_params",
    )
    assert (
        conversation_item_retrieve_build_lines
    ), "Conversation item retrieve handler must build normalized upstream query params"

    audio_tree = ast.parse(
        Path("app/slaif_gateway/services/audio_gateway.py").read_text(encoding="utf-8")
    )
    audio_speech_handler = _find_function(audio_tree, "handle_audio_speech")
    audio_speech_build_lines = _call_lines(
        audio_speech_handler,
        "_build_safe_audio_speech_upstream_body",
    )
    assert audio_speech_build_lines, "Audio speech handler must build the normalized upstream body"
    assert audio_speech_build_lines[0] < _call_lines(audio_speech_handler, "_handle_audio_operation")[0]

    audio_transcription_handler = _find_function(audio_tree, "handle_audio_transcription")
    audio_transcription_build_lines = _call_lines(
        audio_transcription_handler,
        "_build_safe_audio_transcription_upstream_body",
    )
    assert (
        audio_transcription_build_lines
    ), "Audio transcription handler must build the normalized upstream body"
    assert audio_transcription_build_lines[0] < _call_lines(
        audio_transcription_handler, "_handle_audio_operation"
    )[0]

    audio_translation_handler = _find_function(audio_tree, "handle_audio_translation")
    audio_translation_build_lines = _call_lines(
        audio_translation_handler,
        "_build_safe_audio_translation_upstream_body",
    )
    assert (
        audio_translation_build_lines
    ), "Audio translation handler must build the normalized upstream body"
    assert audio_translation_build_lines[0] < _call_lines(
        audio_translation_handler, "_handle_audio_operation"
    )[0]

    embeddings_tree = ast.parse(
        Path("app/slaif_gateway/services/embeddings_gateway.py").read_text(encoding="utf-8")
    )
    embeddings_handler = _find_function(embeddings_tree, "handle_embeddings_create")
    embeddings_build_lines = _call_lines(
        embeddings_handler,
        "_build_safe_embeddings_upstream_body",
    )
    assert embeddings_build_lines, "Embeddings handler must build the normalized upstream body"
    assert embeddings_build_lines[0] < _call_lines(
        embeddings_handler, "_reserve_embeddings_quota"
    )[0]


def test_no_direct_forwarding_passthrough_names_in_provider_paths() -> None:
    suspicious: list[tuple[str, int, str]] = []
    for path in _iter_python_sources():
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        for i, line in enumerate(lines, start=1):
            if "ProviderRequest(" not in line:
                continue
            if "effective_body" in line:
                suspicious.append((str(path), i, line.strip()))
            if "payload" in line and "request_body" not in line and "payload" in line:
                # Avoid unrelated payload usage outside forwarding body construction.
                suspicious.append((str(path), i, line.strip()))

    assert not suspicious, (
        "Potential forwarding passthrough token near ProviderRequest callsites: "
        f"{suspicious}"
    )
