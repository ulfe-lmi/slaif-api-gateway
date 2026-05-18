# Chat Completions Custom Tools Investigation

Checked on 2026-05-18.

This note answers whether OpenAI upstream appears to support
`/v1/chat/completions` requests with `tools[].type == "custom"`, and records
the current SLAIF decision. It is an evidence note only; it does not change
gateway runtime behavior.

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

Current SLAIF implementation:

- `tools[].type == "custom"` is rejected by
  `app/slaif_gateway/services/chat_completion_field_policy.py` with
  `custom_tool_not_supported`.
- Existing unit tests assert this rejection in both request-policy and
  `/v1/chat/completions` policy paths.
- This investigation PR does not change request policy, provider forwarding,
  accounting, routing, capability metadata, or tests.

## Conclusion

The upstream evidence is mixed but leans toward Chat Completions API support:
the API reference and official Python SDK generated types include
Chat Completions custom-tool shapes, while the function-calling guide's
custom-tool examples are Responses API examples.

SLAIF should continue rejecting Chat Completions custom tools until a dedicated
implementation PR proves compatibility and safety. A future enablement PR would
need at least:

- explicit request-field and cap validation for custom-tool definitions,
  grammar definitions, and generated custom-tool input;
- route/model capability metadata and key/template policy gating;
- provider adapter tests for OpenAI and OpenRouter request/response shapes;
- mocked official OpenAI Python client E2E coverage;
- input-estimation and accounting checks showing custom-tool definitions and
  generated custom-tool input affect normal token usage without introducing a
  separate hosted-tool billing unit unless a provider documents one;
- no-content/no-secret tests proving prompts, completions, request bodies,
  custom-tool definitions, custom-tool input, grammar definitions, tool
  payloads, provider keys, gateway plaintext keys, Authorization headers,
  cookies, CSRF/session tokens, and other secrets are not stored, logged, or
  displayed.

Custom tools are local/client-side tool intent, not provider-hosted execution
authority. SLAIF does not police downstream application behavior after local
tool-call output. Hosted/provider-side tools, MCP/connectors, web search, file
search, code interpreter or shell/container execution, computer use, image
generation tools, and tool search remain denied by default.
