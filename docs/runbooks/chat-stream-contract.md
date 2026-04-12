# Chat Stream Contract (`/api/chat/stream`)

## Purpose
Define the stable Server-Sent Events (SSE) contract consumed by chat clients.

## Transport
- Method: `POST`
- Endpoint: `/api/chat/stream`
- Content-Type response: `text/event-stream`
- Payload format: SSE `data: {json}`

## Common Envelope
Every SSE payload includes:
- `type`: event type
- `correlation_id`: request trace id (same value across one stream)

## Event Types
- `start`
  - fields: `session_id` (`string | null`)
- `status`
  - fields: `stage` (`string`), `detail` (`string`)
  - stage values currently used: `analyzing`, `retrieving`, `drafting`, `finalizing`
- `delta`
  - fields: `delta` (`string`)
- `final`
  - fields: `response` (`ChatResponse` object)
- `error`
  - fields: `status_code` (`integer`), `detail` (`string`)
- `done`
  - no additional required fields

## Lifecycle Rules
- Stream starts with exactly one `start`.
- Success path emits exactly one `final` followed by terminal `done`.
- Error path emits terminal `error` and does not emit `final` or `done`.
- `final` can appear at most once.
- Exactly one terminal event is allowed: `done` or `error`.
- No event is valid after a terminal event.

## Validation Source Of Truth
- Runtime sequence validator: `docops/api/contracts.py` (`validate_chat_stream_sequence`)
- Snapshot schema: `tests/contracts/snapshots/chat_stream.contract.json`
- Contract tests: `tests/contracts/test_chat_contracts.py`

## Client Guidance
- Render `delta` incrementally.
- Treat `final.response` as authoritative final payload.
- If `error` is received, keep partial deltas and optionally fallback to non-stream `/api/chat`.
