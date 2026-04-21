# Runtime Translation

This document separates two different concerns that were previously mixed together:

1. The official wire contracts for Anthropic Messages API and Amazon Bedrock Converse API.
2. The repository-specific translation rules implemented by this gateway today.

Read the document in that order. The first half defines the source and target contracts. The second half explains how the gateway currently maps between them, including intentional normalizations and current deviations from the official Anthropic contract.

Implementation lives in:

- [`gateway/domains/runtime/types.py`](/Users/jungseob/workspace/claude-code-proxy-on-aws/gateway/domains/runtime/types.py)
- [`gateway/domains/runtime/services.py`](/Users/jungseob/workspace/claude-code-proxy-on-aws/gateway/domains/runtime/services.py)
- [`gateway/domains/runtime/converter/request_converter.py`](/Users/jungseob/workspace/claude-code-proxy-on-aws/gateway/domains/runtime/converter/request_converter.py)
- [`gateway/domains/runtime/converter/response_converter.py`](/Users/jungseob/workspace/claude-code-proxy-on-aws/gateway/domains/runtime/converter/response_converter.py)
- [`gateway/domains/runtime/streaming.py`](/Users/jungseob/workspace/claude-code-proxy-on-aws/gateway/domains/runtime/streaming.py)
- [`gateway/core/dependencies.py`](/Users/jungseob/workspace/claude-code-proxy-on-aws/gateway/core/dependencies.py)

## Official Reference Links

### Anthropic

- [Create a Message](https://platform.claude.com/docs/en/api/messages/create)
- [Streaming Messages](https://platform.claude.com/docs/en/build-with-claude/streaming)
- [Extended Thinking](https://platform.claude.com/docs/en/build-with-claude/extended-thinking)
- [Tool Use Overview](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)

### Amazon Bedrock

- [Converse API Reference](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html)
- [ConverseStream API Reference](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ConverseStream.html)
- [Using the Converse API](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference-call.html)
- [Message](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Message.html)
- [SystemContentBlock](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_SystemContentBlock.html)
- [ContentBlock](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ContentBlock.html)
- [ToolConfiguration](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ToolConfiguration.html)
- [Tool](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Tool.html)
- [ToolChoice](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ToolChoice.html)
- [ToolSpecification](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ToolSpecification.html)
- [ToolUseBlock](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ToolUseBlock.html)
- [ToolResultBlock](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ToolResultBlock.html)
- [ToolResultContentBlock](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ToolResultContentBlock.html)
- [ReasoningContentBlock](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ReasoningContentBlock.html)
- [ReasoningTextBlock](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ReasoningTextBlock.html)
- [TokenUsage](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_TokenUsage.html)
- [ConverseStreamOutput](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ConverseStreamOutput.html)
- [MessageStopEvent](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_MessageStopEvent.html)
- [ConverseStreamMetadataEvent](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ConverseStreamMetadataEvent.html)

## Anthropic Messages API Official Contract

### Request shape

Anthropic's message creation endpoint is `POST /v1/messages`.

Required request body fields:

- `model`
- `max_tokens`
- `messages`

Important optional request body fields relevant to this gateway:

- `system`
- `tools`
- `tool_choice`
- `stream`
- `temperature`
- `top_p`
- `stop_sequences`
- `thinking`
- `metadata`

Anthropic also documents additional top-level request fields such as:

- `inference_geo`
- `output_config`
- `service_tier`

The official request contract matters in the following ways:

- `messages[*].role` must be `user` or `assistant`.
- There is no `"system"` role inside `messages`. System instructions must use the top-level `system` field.
- `messages[*].content` may be either a string or an array of content blocks.
- A string `content` is shorthand for a single text block.
- Anthropic combines consecutive turns with the same role.
- If the final input message is `assistant`, Claude continues from that assistant text in the response.

### Official Anthropic input content blocks

The Messages API accepts block-typed content. The broad set is feature-dependent, but the contract relevant to this repository includes:

- `text`
- `image`
- `document`
- `search_result`
- `tool_use`
- `tool_result`
- `thinking`
- `redacted_thinking`

Important block-level rules:

- `system` is officially `string` or an array of `TextBlockParam`, not an arbitrary block array.
- `tool_use.input` is a JSON object.
- `tool_result.tool_use_id` identifies the matching tool call.
- Official Anthropic `tool_result` uses `is_error: boolean`, not a `status` string.
- `thinking` blocks contain `thinking` text and optional `signature`.
- `redacted_thinking` blocks contain opaque encrypted `data`.
- Prompt caching uses `cache_control: { "type": "ephemeral", "ttl"?: "5m" | "1h" }` on supported block types.

### Tools and tool choice

Anthropic tool definitions are part of the request body:

- `tools` is an array of tool definitions.
- Tool definitions include `name`, `input_schema`, optional `description`, optional `strict`, and optional caching fields on supported tool types.
- Anthropic documents tool `name` with minimum length `1` and maximum length `128`.
- `input_schema` is a JSON Schema object describing the tool input.

Official `tool_choice` values are:

- `auto`
- `any`
- `tool`
- `none`

Anthropic also documents `disable_parallel_tool_use` on `auto`, `any`, and `tool`.

### Thinking

Anthropic documents three thinking modes:

- `{"type":"disabled"}`
- `{"type":"enabled","budget_tokens":N}`
- `{"type":"adaptive"}`

Important official constraints:

- `enabled` requires `budget_tokens >= 1024`.
- `budget_tokens` must be less than `max_tokens`.
- Claude Opus 4.6 and Claude Sonnet 4.6 recommend `adaptive` thinking instead of manual `enabled` budgeting.
- When extended thinking is enabled, responses contain `thinking` blocks before final `text` blocks.
- When you send prior thinking back in a later turn, Anthropic requires preserving the block contents and signature unmodified.
- Anthropic explicitly calls out that preserving thinking blocks is important across tool-use loops.

### Non-streaming response shape

Anthropic returns a `Message` object with:

- `id`
- `type`, always `message`
- `role`, always `assistant`
- `model`
- `content`
- `stop_reason`
- `stop_sequence`
- `usage`

Relevant official `stop_reason` values:

- `end_turn`
- `max_tokens`
- `stop_sequence`
- `tool_use`
- `pause_turn`
- `refusal`

Relevant official `usage` fields include:

- `input_tokens`
- `output_tokens`
- `cache_creation_input_tokens`
- `cache_read_input_tokens`
- cache creation breakdown by TTL
- `inference_geo`
- server-tool usage counters
- `service_tier`

Important response-content observation:

- Anthropic assistant responses are documented to emit blocks such as `text`, `thinking`, `redacted_thinking`, `tool_use`, and feature-specific server-tool blocks.
- `tool_result` is an input block shape for subsequent requests, not the normal assistant output block shape.

### Streaming response shape

Anthropic streaming is enabled with `stream: true` and uses SSE.

Official event flow:

1. `message_start`
2. zero or more content blocks, each with:
   - `content_block_start`
   - one or more `content_block_delta`
   - `content_block_stop`
3. one or more `message_delta`
4. `message_stop`

Additional official stream events:

- `ping`
- `error`

Official Anthropic streaming rules that matter here:

- `message_delta.usage` is cumulative.
- `tool_use` deltas use `input_json_delta` with partial JSON strings.
- `thinking` streams via `thinking_delta`.
- A `signature_delta` is emitted just before `content_block_stop` for a thinking block.
- Anthropic warns that new event types may be added over time and clients should ignore unknown events safely.

## Amazon Bedrock Converse Official Contract

### Converse request shape

Amazon Bedrock Converse uses:

- `POST /model/{modelId}/converse`
- `POST /model/{modelId}/converse-stream`

Relevant request body fields:

- `messages`
- `system`
- `inferenceConfig`
- `additionalModelRequestFields`
- `toolConfig`
- `requestMetadata`
- `additionalModelResponseFieldPaths`
- `guardrailConfig`
- `promptVariables`
- `outputConfig`
- `performanceConfig`
- `serviceTier`

Important Bedrock request facts:

- `modelId` is outside the JSON body and is required.
- `messages[*].role` is `user` or `assistant`.
- `messages[*].content` is always an array of `ContentBlock`. There is no string shorthand.
- `system` is always an array of `SystemContentBlock`.
- `requestMetadata` is the Bedrock field closest in purpose to caller-supplied request metadata.

### Bedrock message and content rules

The Bedrock `Message` contract adds restrictions that Anthropic callers do not see directly:

- Up to 20 images per message.
- Each image must be at most 3.75 MB and 8000x8000 px.
- Up to 5 documents per message.
- Each document must be at most 4.5 MB.
- If a message contains a `document`, the same message must also contain a `text` block.
- Images and documents are only allowed for `role = user`.

`SystemContentBlock` is a union of:

- `text`
- `guardContent`
- `cachePoint`

`ContentBlock` is a union of:

- `audio`
- `cachePoint`
- `citationsContent`
- `document`
- `guardContent`
- `image`
- `reasoningContent`
- `searchResult`
- `text`
- `toolResult`
- `toolUse`
- `video`

Only one union member may be present in any `ContentBlock`.

### Bedrock tools

`toolConfig` contains:

- `tools`, required when `toolConfig` is present
- `toolChoice`, optional

`ToolChoice` is a union of:

- `auto`
- `any`
- `tool`

Important Bedrock tool rules:

- Bedrock does not define a `none` choice.
- `any` means the model must request at least one tool and does not generate text.
- `tool` means the model must request a specific tool and is only supported by Anthropic Claude 3 and Amazon Nova models.

`ToolSpecification` contains:

- `name`
- `inputSchema`
- optional `description`
- optional `strict`

Important Bedrock tool constraints:

- Tool `name` maximum length is `64`.
- Tool `name` pattern is `[a-zA-Z0-9_-]+`.
- `ToolUseBlock.toolUseId` maximum length is `64`.
- `ToolUseBlock.input` is a JSON value.
- `ToolResultBlock.status` is an optional enum `success | error`.
- `ToolResultContentBlock` is a union of `document`, `image`, `json`, `searchResult`, `text`, or `video`.

### Bedrock reasoning

Bedrock expresses reasoning via `reasoningContent`, not Anthropic `thinking`.

`ReasoningContentBlock` is a union of:

- `reasoningText`
- `redactedContent`

`ReasoningTextBlock` contains:

- `text`
- optional `signature`

Bedrock explicitly states that if you pass a reasoning block back in a multi-turn conversation, the text and signature must be included unmodified.

### Converse non-streaming response shape

The Bedrock Converse response includes:

- `output.message`
- `stopReason`
- `usage`
- `metrics`
- optional `additionalModelResponseFields`
- optional performance and guardrail metadata

Relevant official `stopReason` values:

- `end_turn`
- `tool_use`
- `max_tokens`
- `stop_sequence`
- `guardrail_intervened`
- `content_filtered`
- `malformed_model_output`
- `malformed_tool_use`
- `model_context_window_exceeded`

`TokenUsage` includes:

- `inputTokens`
- `outputTokens`
- `totalTokens`
- `cacheReadInputTokens`
- `cacheWriteInputTokens`
- optional `cacheDetails`

### ConverseStream response shape

`ConverseStreamOutput` is an event stream. Relevant events are:

- `messageStart`
- `contentBlockStart`
- `contentBlockDelta`
- `contentBlockStop`
- `messageStop`
- `metadata`
- streamed exception events

The relevant event payload contracts are:

- `MessageStartEvent` exposes `role`
- `ContentBlockStartEvent` exposes `contentBlockIndex` and `start`
- `ContentBlockDeltaEvent` exposes `contentBlockIndex` and `delta`
- `MessageStopEvent` exposes `stopReason` and optional `additionalModelResponseFields`
- `ConverseStreamMetadataEvent` exposes `usage` and `metrics`

Bedrock stream events are not SSE-framed Anthropic events. They are Bedrock event-stream payloads that the gateway must reinterpret.

## Contract Differences That Drive Translation

This repository is translating across two similar but non-identical protocols.

### Request-side differences

| Anthropic public contract | Bedrock upstream contract | Translation consequence |
| --- | --- | --- |
| `model` is in JSON body | `modelId` is a URI parameter | Runtime must resolve aliases and move model choice to `modelId`. |
| `messages[*].content` can be a string | `messages[*].content` must be an array | Runtime must expand string shorthand into a text block array. |
| `system` is `string` or text-block array | `system` is `SystemContentBlock[]` | Runtime must normalize text to Bedrock system blocks. |
| `tool_choice` supports `none` | Bedrock supports only `auto`, `any`, `tool` | Runtime needs an explicit policy for `none`. |
| Official `tool_result` uses `is_error` | Bedrock `toolResult` uses `status: success|error` | Runtime must translate error semantics explicitly. |
| `metadata` is top-level request metadata | `requestMetadata` is the Bedrock equivalent | Runtime can choose to forward or drop metadata. |
| `thinking` is top-level Anthropic config | Bedrock expects model-specific extras in `additionalModelRequestFields` | Runtime must move and normalize thinking config. |

### Response-side differences

| Bedrock upstream contract | Anthropic public contract | Translation consequence |
| --- | --- | --- |
| `reasoningContent` | `thinking` / `redacted_thinking` | Runtime must convert reasoning blocks both non-streaming and streaming. |
| `stopReason` has extra values such as `content_filtered` and `model_context_window_exceeded` | Anthropic stop reasons are a smaller set | Runtime must map, collapse, reject, or expose off-spec values deliberately. |
| `usage` uses camelCase and includes `totalTokens` | Anthropic usage uses snake_case and a different field set | Runtime must reshape usage carefully. |
| `ConverseStream` emits Bedrock event objects | Anthropic streaming uses SSE event names and Anthropic event payloads | Runtime must synthesize Anthropic-style SSE. |

## Current Runtime Flow

For `POST /v1/messages`, the runtime pipeline is:

1. Validate the public request as [`MessageRequest`](/Users/jungseob/workspace/claude-code-proxy-on-aws/gateway/domains/runtime/types.py).
2. Evaluate the policy chain in this order:
   - virtual key
   - user status
   - team status
   - model resolver
   - user model policy
   - team model policy
   - user budget pre-check
   - team budget pre-check
   - model budget pre-check
   - cache policy capability check
3. Convert the Anthropic-compatible request into a Bedrock `converse` or `converse_stream` payload.
4. Call Bedrock.
5. Convert the Bedrock response or stream back into Anthropic-compatible output.
6. Persist usage or error state through `UsageService`.

Translation therefore depends on policy output, not just on the inbound request. In particular:

- `selected_model` is the client-facing model string from the request.
- `resolved_model` is the canonical model chosen by alias mapping and sent to Bedrock.
- Runtime uses `resolved_model.bedrock_region` when set, otherwise it falls back to the gateway `AWS_REGION`.
- `max_tokens_override` can replace the request's `max_tokens`.
- `cache_policy` comes from runtime policy evaluation and model capability checks, not from a public request field.

## Current Public Request Model

The implemented public request model is [`MessageRequest`](/Users/jungseob/workspace/claude-code-proxy-on-aws/gateway/domains/runtime/types.py).

Required fields:

- `model`
- `max_tokens`
- `messages`

Recognized optional fields:

- `system`
- `tools`
- `tool_choice`
- `stream`
- `temperature`
- `top_p`
- `stop_sequences`
- `thinking`
- `metadata`

Current validation behavior:

- `max_tokens` must be greater than `0`.
- `messages[*].content` may be a string or a list of arbitrary block objects.
- Extra top-level fields are ignored because the request model uses `extra="ignore"`.

Important consequence:

- Official Anthropic fields such as `inference_geo`, `output_config`, and `service_tier` are currently accepted only in the sense that they are silently ignored.

## Anthropic to Bedrock Request Mapping

### Top-level fields

- `model`
  - Resolved first through `model_alias_mappings`.
  - Bedrock receives `modelId = resolved_model.bedrock_model_id`.
- `max_tokens`
  - Sent as `inferenceConfig.maxTokens`.
  - Replaced by `max_tokens_override` when policy set one.
- `temperature`
  - Sent as `inferenceConfig.temperature`.
- `top_p`
  - Sent as `inferenceConfig.topP`.
- `stop_sequences`
  - Sent as `inferenceConfig.stopSequences`.
- `system`
  - String input becomes a single Bedrock text block.
  - List input is converted block-by-block.
- `tools`
  - Converted to `toolConfig.tools`.
- `tool_choice`
  - Converted to `toolConfig.toolChoice`.
  - May be rewritten when request-level thinking remains enabled.
- `thinking`
  - Converted to `additionalModelRequestFields.thinking` after model-family normalization.
  - May be dropped entirely when prior tool-use history is incompatible.
- `metadata`
  - Accepted by validation.
  - Not forwarded directly to Bedrock `requestMetadata`.
- Server-side request metadata
  - Runtime injects Bedrock `requestMetadata.request_id = context.request_id`.
  - Runtime injects Bedrock `requestMetadata.user_id = str(context.user.id)` when user resolution succeeds.
  - Runtime injects Bedrock `requestMetadata.team_id = str(context.team.id)` when a team is resolved.

### Message and system content blocks

String message content becomes:

```json
[{ "type": "text", "text": "<string>" }]
```

Supported block conversions are:

- `text` -> `{ "text": "<text>" }`
- `tool_use` -> `{ "toolUse": { "toolUseId": ..., "name": ..., "input": ... } }`
- `tool_result` -> `{ "toolResult": { "toolUseId": ..., "content": [...], "status": ... } }`
- `image` -> `{ "image": ... }`
- `document` -> `{ "document": ... }`
- `thinking` -> `{ "reasoningContent": { "reasoningText": { "text": ..., "signature": ...? } } }`
- `redacted_thinking` -> `{ "reasoningContent": { "redactedContent": ... } }`

Fallback behavior for unknown block types:

- The block is copied through unchanged.
- `cache_control` is removed from the copied block before sending to Bedrock.

Important contract deviation:

- Official Anthropic `system` is text-only, but the converter will attempt to convert arbitrary block objects when `system` is provided as a list.

### Tool-use normalization

For `tool_use` blocks:

- Object `input` values are deep-copied as-is.
- String `input` values are parsed as JSON.
- If parsed JSON is not an object, or parsing fails, the converter sends `{}`.

Within a single message:

- Duplicate `toolUse.toolUseId` values are dropped after the first occurrence.
- Duplicate `toolResult.toolUseId` values are dropped after the first occurrence.

Deduplication is per message, not across the entire request.

### Tool-result normalization

`tool_result.content` is normalized into a Bedrock `ToolResultContentBlock[]`.

Behavior:

- `null` -> `[]`
- string -> `[{ "text": "<string>" }]`
- object -> one normalized block
- list -> each entry normalized independently

Per-item normalization:

- string -> `{ "text": "<string>" }`
- `{ "type": "text", "text": ... }` -> `{ "text": ... }`
- `{ "type": "image", "source": ... }` -> `{ "image": ... }`
- `{ "type": "document", "source": ... }` -> `{ "document": ... }`
- `{ "type": "json", "json": ... }` or `{ "type": "json", "data": ... }` -> `{ "json": ... }`
- `{ "type": "search_result", ... }` -> `{ "searchResult": ... }`
- Existing Bedrock union blocks with exactly one of `document`, `image`, `json`, `searchResult`, `text`, or `video`
  - preserved as-is except `cache_control` is removed
- Any other object
  - wrapped as `{ "json": <object> }`
- Any other non-object value
  - stringified and wrapped as `{ "text": "<value>" }`

If `tool_result.status` is missing, it defaults to `"success"`.

Important contract deviation:

- Official Anthropic `tool_result` uses `is_error`, but the runtime only looks for `status`.
- An Anthropic-correct payload with `is_error: true` is currently translated as success unless the caller also sends a nonstandard `status`.
- The runtime also accepts broader non-Anthropic `tool_result.content` item shapes, including `type: "json"` and native Bedrock tool-result union blocks.

### Tool definitions and tool choice

Each public tool becomes:

```json
{
  "toolSpec": {
    "name": "...",
    "inputSchema": { "json": { ... } },
    "description": "...?",
    "strict": true|false?
  }
}
```

Current rules:

- `description` is included only when truthy.
- `strict` is included whenever the field is present on the public tool object.
- Tool-level `cache_control` can generate an adjacent Bedrock `cachePoint`.

`tool_choice` mapping:

- `{ "type": "auto" }` -> `{ "auto": {} }`
- `{ "type": "any" }` -> `{ "any": {} }`
- `{ "type": "tool", "name": "x" }` -> `{ "tool": { "name": "x" } }`
- Anything else
  - copied through unchanged

When request-level thinking is still enabled after normalization:

- `tool_choice.type == "any"` is rewritten to `{ "type": "auto" }`
- `tool_choice.type == "tool"` is rewritten to `{ "type": "auto" }`
- `tool_choice.type == "auto"` stays `auto`

Important contract deviation:

- Anthropic officially supports `tool_choice: { "type": "none" }`.
- Bedrock has no `none` choice and the current converter does not special-case it.
- A public `none` choice is therefore currently passed through unchanged and relies on Bedrock rejecting it or ignoring it.

### Thinking normalization

The runtime distinguishes between adaptive-thinking model families and earlier Claude families.

Adaptive-thinking families are currently:

- `claude-opus-4-6`
- `claude-sonnet-4-6`

The converter treats a model as adaptive-capable when any of these match:

- `resolved_model.family`
- `resolved_model.canonical_name`
- a substring in `resolved_model.bedrock_model_id`

Key normalization rules:

- `budgetTokens` is renamed to `budget_tokens` if needed.
- If both `budgetTokens` and `budget_tokens` are present, `budgetTokens` is discarded.

For adaptive-capable 4.6 families:

- `{"type":"enabled", ...}` -> `{"type":"adaptive"}`
- `{"type":"adaptive", ...}` -> `{"type":"adaptive"}`
- fixed-budget fields are stripped
- any other thinking payload is passed through after key normalization

For non-4.6 models when `thinking.type` is `enabled` or `adaptive`:

- `adaptive` is downgraded to fixed-budget `enabled`
- missing or non-integer budgets default to `1024`
- budgets below `1024` are clamped to `1024`
- budgets above `max_tokens - 1` are clamped to `max_tokens - 1`
- requests with `max_tokens <= 1024` raise a runtime `ValidationError`

For non-4.6 models with other thinking payloads:

- the payload is copied through after key normalization
- if it still contains integer `budget_tokens < 1024`, that budget is clamped to `1024`

### Thinking history guard

Request-level `thinking` is dropped before the Bedrock call when all of the following are true:

- the inbound request included request-level `thinking`
- at least one prior assistant message contains `tool_use`
- no assistant message in history contains `thinking` or `redacted_thinking`
- the last assistant message that contains `tool_use` also does not contain thinking blocks

This is an explicit compatibility safeguard for Bedrock Converse tool histories.

### Cache-point generation

The public API does not expose a request-level cache policy field. Cache behavior is derived from policy evaluation.

Current runtime behavior:

- Default policy context starts with `cache_policy = "5m"`.
- User model policy can override it.
- Team model policy can override it only if user policy did not already set `max_tokens_override`.
- If the resolved model does not support prompt cache, the cache policy is forced to `"none"`.

Bedrock cache points are generated only when all of the following are true:

- effective `cache_policy` is not `"none"`
- the source block or tool has `cache_control: { "type": "ephemeral" }`
- fewer than 4 cache points have already been generated in the request

Generated cache-point shape:

```json
{ "cachePoint": { "type": "default", "ttl": "5m|1h" } }
```

Notes:

- The converter inserts cache points adjacent to the originating system block, message block, or tool.
- The TTL is included only for `"5m"` or `"1h"`.
- The total generated cache points are capped at `4` across `system`, `messages`, and `tools`.
- `apply_cache_points()` is currently a no-op. There is no trailing request-level cache point pass.

## Bedrock to Anthropic Non-Streaming Mapping

### Message envelope

The non-streaming converter returns [`MessageResponse`](/Users/jungseob/workspace/claude-code-proxy-on-aws/gateway/domains/runtime/types.py).

Current envelope rules:

- `id`
  - `bedrock_resp.id` if present
  - otherwise `bedrock_resp.ResponseMetadata.RequestId`
  - otherwise `"msg_unknown"`
- `type`
  - always `"message"`
- `role`
  - always `"assistant"`
- `model`
  - always the original client-selected model string, not the resolved Bedrock model id
- `stop_reason`
  - mapped from Bedrock `stopReason`
- `stop_sequence`
  - always `null`

### Output content conversion

Explicit output conversions:

- `{ "text": "..." }` -> `{ "type": "text", "text": "..." }`
- `{ "toolUse": ... }` -> `{ "type": "tool_use", "id": ..., "name": ..., "input": ... }`
- `{ "toolResult": ... }` -> `{ "type": "tool_result", "tool_use_id": ..., "content": ..., "status": ... }`
- `{ "reasoningContent": { "reasoningText": { "text": "...", "signature"?: "..." } } }`
  -> `{ "type": "thinking", "thinking": "...", "signature"?: "..." }`
- `{ "reasoningContent": { "redactedContent": "..." } }`
  -> `{ "type": "redacted_thinking", "data": "..." }`

Anything else is passed through unchanged.

Important contract deviations:

- The runtime can emit `tool_result` in an assistant response, even though Anthropic documents `tool_result` as an input block shape rather than a normal assistant output block shape.

### Usage extraction

Usage is extracted from either:

- `response.usage`
- or `response.metadata.usage`

Metrics are extracted from either:

- `response.metrics`
- or `response.metadata.metrics`

Field mapping:

- `inputTokens` -> `input_tokens`
- `outputTokens` -> `output_tokens`
- `cacheReadInputTokens` -> `cache_read_input_tokens`
- `cacheWriteInputTokens` -> `cache_creation_input_tokens`
- `metrics.latencyMs` -> internal `latency_ms`
- `ResponseMetadata.RequestId` -> internal `bedrock_invocation_id`

The runtime currently ignores:

- `totalTokens`
- `cacheDetails`
- Bedrock performance metadata
- Bedrock `additionalModelResponseFields`

### Stop reason mapping

Implemented mappings:

- `end_turn` -> `end_turn`
- `tool_use` -> `tool_use`
- `max_tokens` -> `max_tokens`
- `stop_sequence` -> `stop_sequence`
- `content_filtered` -> `end_turn`

Unknown stop reasons are passed through unchanged.

Important contract deviation:

- Bedrock stop reasons such as `guardrail_intervened`, `malformed_model_output`, `malformed_tool_use`, and `model_context_window_exceeded` can leak through as off-spec Anthropic `stop_reason` values.

## Bedrock to Anthropic Streaming Mapping

The streaming path emits Anthropic-style SSE over Bedrock `converse_stream`.

Implemented SSE event names:

- `message_start`
- `content_block_start`
- `content_block_delta`
- `content_block_stop`
- `message_delta`
- `message_stop`
- `error`

Important contract deviation:

- Official Anthropic streams may also include `ping`, but the runtime does not emit a `ping` event.

### Stream event normalization

The response converter accepts both standard Converse event shapes and patch-style events. Patch-style events are normalized when an event contains `p`.

Normalization rules:

- `{"p": ..., "role": ...}` -> `messageStart`
- `{"p": ..., "contentBlockIndex": ..., "start": ...}` -> `contentBlockStart`
- `{"p": ..., "contentBlockIndex": ..., "delta": ...}` -> `contentBlockDelta`
- `{"p": ..., "contentBlockIndex": ...}` -> `contentBlockStop`
- `{"p": ..., "stopReason": ...}` -> `messageStop`
- `{"p": ..., "usage": ...}` or `{"p": ..., "metrics": ...}` -> `metadata`

### `message_start`

`message_start` is emitted on the first non-`metadata` event only.

Current stub payload:

```json
{
  "type": "message_start",
  "message": {
    "id": "msg_<request_id>",
    "type": "message",
    "role": "assistant",
    "content": [],
    "model": "<resolved bedrock model id or selected model>",
    "stop_reason": null,
    "stop_sequence": null,
    "usage": {
      "input_tokens": 0,
      "output_tokens": 0
    }
  }
}
```

The stream state uses:

- `message_id = "msg_<request_id>"`
- `model_name = resolved_model.bedrock_model_id` when available, otherwise `request.model`

Important contract deviations:

- Anthropic examples show non-zero usage in `message_start`, but the runtime emits zeroed usage.
- Streaming uses the resolved Bedrock model id when available, while non-streaming uses the original selected public model string.

### Content block starts and deltas

`contentBlockStart` mapping:

- `start.toolUse` -> `content_block_start` with `content_block.type = "tool_use"`
- `start.reasoningContent.reasoningText` -> `content_block_start` with `content_block.type = "thinking"`
- `start.reasoningContent.redactedContent` -> `content_block_start` with `content_block.type = "redacted_thinking"`
- anything else -> text block start

`contentBlockDelta` mapping:

- `delta.text` -> `text_delta`
- `delta.toolUse.input` -> `input_json_delta`
- `delta.reasoningContent.reasoningText.text` or `delta.reasoningContent.text` -> `thinking_delta`
- `delta.reasoningContent.reasoningText.signature` or `delta.reasoningContent.signature` -> `signature_delta`

Tool-use delta details:

- Non-string partial JSON is JSON-serialized compactly.
- Empty tool-use partial input is skipped.

Reasoning details:

- The converter sets stream state flags when it sees tool use or reasoning blocks.
- This is used only for summary logging, not for output shape changes.

### Synthetic block starts from deltas

If a `contentBlockDelta` arrives for an index that has not seen a start event yet, the converter may synthesize `content_block_start` first.

Implemented synthetic starts:

- tool-use delta with any id, name, or non-empty partial input
- reasoning delta that can be mapped to thinking or redacted-thinking
- text delta

### Content block stop

`contentBlockStop` always becomes:

```json
{
  "type": "content_block_stop",
  "index": <contentBlockIndex>
}
```

After this event, the stream state's current content index advances to `index + 1`.

### Message termination

`messageStop` alone does not immediately emit `message_stop`.

Instead:

- `messageStop` records the mapped `stop_reason` in stream state
- `metadata` records usage in stream state
- `message_delta` and `message_stop` are emitted only once both are present

Current `message_delta` shape:

```json
{
  "type": "message_delta",
  "delta": {
    "stop_reason": "..."
  },
  "usage": {
    "input_tokens": 0,
    "output_tokens": 0,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 0
  }
}
```

Important contract deviation:

- Official Anthropic streaming usage is cumulative and may appear across one or more `message_delta` events.
- The runtime emits a single terminal `message_delta` once Bedrock `metadata` arrives.

### End-of-stream fallback behavior

When the Bedrock iterator ends, the stream processor calls `finalize_stream()`.

Implemented fallbacks:

- If `messageStop` was seen but `metadata` never arrived:
  - emit `message_delta` with zeroed usage
  - then emit `message_stop`
- If a message was started but no termination was emitted:
  - emit synthetic `message_stop`
- If `message_delta` was already emitted:
  - emit nothing further

This preserves Anthropic-style ordering where `message_delta` must precede `message_stop`.

### Stream failure behavior

If streaming raises after response headers have already started:

- the processor logs the exception
- if success usage was not already persisted, it records an internal error usage event
- it emits one final SSE event:

```json
{
  "type": "error",
  "error": {
    "type": "api_error",
    "message": "<exception string>"
  }
}
```

Important contract deviation:

- Anthropic can emit provider-specific streaming errors such as `overloaded_error`.
- The runtime collapses stream failures into a generic Anthropic-style `api_error`.

## Usage Persistence Semantics

### Success path

Non-streaming:

- Usage is extracted from the Bedrock response after conversion.
- `UsageService.record_success()` is called exactly once.

Streaming:

- Usage is extracted from the Bedrock `metadata` event.
- `UsageService.record_success()` is called when that `metadata` event arrives.
- If the stream ends without `metadata`, no success event is persisted.

### Blocked and error paths

Non-streaming `AppError`:

- If runtime context already has `resolved_model`, `user`, and `virtual_key`, the gateway records a blocked request.

Non-streaming unexpected exception:

- If runtime context already has `resolved_model`, `user`, and `virtual_key`, the gateway records an internal error request.

Streaming setup-time `AppError` before SSE starts:

- The gateway records a blocked request when context is sufficiently resolved, then re-raises.

Streaming runtime exception after SSE starts:

- The stream processor records an internal error request only if success was not already persisted.

### Cost calculation inputs

Successful usage cost uses:

- input tokens
- output tokens
- cache read tokens
- cache write tokens
- active pricing row for the resolved model
- effective runtime cache policy

For cache write cost:

- `cache_policy == "1h"` uses `cache_write_1h_price_per_1k`
- all other policies use `cache_write_5m_price_per_1k`

## Logging That Actually Exists

Current runtime logging relevant to translation:

- `gateway.domains.runtime.router`
  - logs request receipt with `request_id`, selected model, `stream`, and `beta` query param
- `gateway.domains.usage.services`
  - logs successful runtime completion with selected model, resolved model, user id, and cache token counts
- `gateway.domains.runtime.services`
  - logs Bedrock errors with request, model, and user context

What is not currently implemented:

- no raw non-streaming request/response payload logging in the runtime service
- no persisted prompt or completion body storage

## Current Known Gaps

- Client-supplied request `metadata` is accepted but still ignored instead of being forwarded into Bedrock `requestMetadata`.
- Official Anthropic `tool_result.is_error` is not translated into Bedrock `toolResult.status`.
- Official Anthropic `tool_choice.none` has no explicit runtime handling.
- Anthropic tool names can be longer than Bedrock's 64-character limit, and the runtime does not pre-validate to the Bedrock limit.
- Extra public request fields ignored by Pydantic are not forwarded into the runtime path.
- Streaming emits Anthropic-compatible content, tool-use, and reasoning deltas, but it does not emit `ping` or other keepalive events.
- Streaming `message_start.usage` is zeroed and `message_delta.usage` is terminal-only rather than cumulative.
- The streaming error event is generic and does not preserve richer Bedrock error structure.
- Streaming and non-streaming responses do not use the same model-name echo behavior.
