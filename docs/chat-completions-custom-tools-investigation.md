# Chat Completions Custom Tools Investigation

Checked on 2026-05-18.

This note answers whether OpenAI upstream appears to support
`/v1/chat/completions` requests with `tools[].type == "custom"`, and records
the SLAIF enablement boundary.

## Evidence Checked

OpenAI API reference:

- The current Chat Completions API reference lists `ChatCompletionTool` as a
  union of function tools and `ChatCompletionCustomTool`, and describes the
  custom variant as a tool with `custom` metadata and `type: "custom"`.
- The same reference lists `ChatCompletionNamedToolChoiceCustom`, allowing
  `tool_choice` to force a specific custom tool by name.
- Source: [OpenAI Chat Completions API reference](https://platform.openai.com/docs/api-reference/chat/create?lang=curl).

OpenAI function-calling guide:

- The guide says function calling covers JSON-schema function tools and custom
  tools with free-form text inputs/outputs.
- The concrete custom-tool examples in the guide use
  `client.responses.create(...)`, not `client.chat.completions.create(...)`.
- The guide therefore supports the feature concept, but its executable examples
  are Responses-oriented rather than Chat Completions examples.
- Source: [OpenAI function-calling guide](https://platform.openai.com/docs/guides/function-calling?api-mode=chat).

Official `openai-python` SDK:

- The repository currently has `openai` 2.32.0 installed in the project
  virtualenv. Package metadata identifies it as the official OpenAI Python
  library and links to `https://github.com/openai/openai-python`.
- The 2.32.0 generated types include:
  - `CompletionCreateParamsBase.tools:
    Iterable[ChatCompletionToolUnionParam]`;
  - `ChatCompletionToolUnionParam =
    Union[ChatCompletionFunctionToolParam, ChatCompletionCustomToolParam]`;
  - `ChatCompletionCustomToolParam` with `type: Literal["custom"]`,
    custom name/description, and text or grammar format metadata;
  - `ChatCompletionNamedToolChoiceCustomParam` for forcing a named custom tool;
  - `ChatCompletionMessageCustomToolCall` for custom tool-call responses.
- The current upstream tag checked during this investigation was
  `openai-python` `v2.36.0` (`38d75d74a5626472cd7d1be9705ea8aba29a6b22`).
  Its generated Chat Completions type surface still includes the same custom
  tool request, tool-choice, and response types.
- Source: [openai/openai-python](https://github.com/openai/openai-python).

SLAIF implementation after the enablement PR:

- Non-streaming Chat Completions custom tools are accepted only as
  local/client-side custom tool-call intent when the resolved route explicitly
  sets `capabilities.chat_completions.chat_custom_tools=true`.
- The supported request shape is the documented Chat Completions shape:
  `{"type":"custom","custom":{"name":..., "description"?:..., "format"?:...}}`.
  `format` may be `{"type":"text"}` or
  `{"type":"grammar","grammar":{"syntax":"lark"|"regex","definition":...}}`.
- Named custom tool choice is accepted only as
  `{"type":"custom","custom":{"name":...}}` and only when the name matches a
  declared custom tool in the same request.
- Streaming Chat Completions custom tools remain unsupported because the
  installed official OpenAI Python SDK stream chunk type only models function
  tool deltas for Chat Completions.
- Custom tools use ordinary Chat Completions input/output token accounting.
  SLAIF adds no custom-tool pricing, billing unit, execution fee, or ledger
  cost category.

## Conclusion

The upstream evidence is mixed but leans toward Chat Completions API support:
the API reference and official Python SDK generated types include
Chat Completions custom-tool shapes, while the function-calling guide's
custom-tool examples are Responses API examples.

The enablement boundary is intentionally narrow:

Custom tools are local/client-side tool intent, not provider-hosted execution
authority. OpenAI does not execute the local custom tool merely because it is
declared, and SLAIF does not execute it. SLAIF does not police downstream
application behavior after local tool-call output and therefore does not reject
custom tool names such as `run_shell`, `send_email`, `delete_file`, or
`code_exec`. Hosted/provider-side tools, MCP/connectors, web search, file
search, code interpreter or shell/container execution, computer use, image
generation tools, and tool search remain denied by default.
