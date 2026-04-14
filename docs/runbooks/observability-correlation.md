# Observability and Correlation Runbook

## Goal
Provide end-to-end traceability for chat, stream, artifacts, and recommendation flows using a shared `correlation_id`.

## Correlation Standard
- Request header: `X-Correlation-ID`
- Response header: `X-Correlation-ID`
- If client does not send one, backend generates a safe id.
- All server logs include `cid=<value>`.
- SSE events from `/api/chat/stream` include `correlation_id` in payload.

## Event Envelope (canonical)
All operational events are emitted as `DOCOPS_EVENT <json>` log lines.

Required fields:
- `schema_version` (int)
- `event` (string)
- `timestamp` (ISO-8601 UTC)
- `correlation_id` (string)

Common optional fields:
- `category` (`http`, `chat`, `chat_stream`, `artifact`, `recommendation`)
- `user_id`
- `route`, `method`, `path`
- `status_code`, `latency_ms`
- `error_type`, `detail`
- flow-specific fields such as `intent`, `source_count`, `gap_count`, `job_id`
- confidence fields for chat quality:
  - `quality_level`, `quality_score`
  - `quality_reason_codes`
  - `quality_component_support_rate`
  - `quality_component_source_breadth`
  - `quality_component_unsupported_claims`
  - `quality_component_retrieval_depth`

## Ingestion Mapping
Use log ingestion rule:
1. Filter lines containing prefix `DOCOPS_EVENT`.
2. Strip prefix and parse JSON payload.
3. Index these fields as first-class dimensions:
   - `event`
   - `correlation_id`
   - `category`
   - `status_code`
   - `latency_ms`
   - `error_type`
   - `route` or `path`
   - `user_id`

This enables pivoting by correlation id and building stable dashboards.

## Dashboard Starter Set

### 1) API Reliability
- Metric: request count by `path`, `status_code`
- Metric: p50/p95/p99 `latency_ms` by `path`
- Metric: error rate (`status_code >= 500`) by `path`

### 2) Stream Lifecycle
- Count events:
  - `chat.stream.started`
  - `chat.stream.final`
  - `chat.stream.completed`
  - `chat.stream.failed`
- Derived metric: stream completion rate = `completed / started`
- Derived metric: stream failure rate = `failed / started`

### 3) Stream Fallback Rate
- Track HTTP events on `/api/chat` with `fallback_from_stream=true`
- Derived metric: fallback rate = fallback calls / total chat requests

### 4) Artifact Pipeline Health
- Counts:
  - `artifact.generation.started`
  - `artifact.generation.completed`
  - `artifact.generation.failed`
- Breakdowns: `mode` (`sync` or `async`) and `artifact_type`

### 5) Recommendation Flow Health
- Daily question events:
  - `recommendation.daily_question.requested`
  - `recommendation.daily_question.generated`
  - `recommendation.daily_question.failed`
- Gap analysis events:
  - `recommendation.gap_analysis.started`
  - `recommendation.gap_analysis.completed`
  - `recommendation.gap_analysis.failed`

### 6) Confidence Quality Distribution
- Event source:
  - `chat.quality_signal.computed`
  - `chat.request.completed`
- Metrics:
  - distribution of `quality_score` by `quality_level`
  - moving average per component (`quality_component_*`)
  - reason taxonomy frequency from `quality_reason_codes`
- Drift checks:
  - abrupt drop in `quality_component_support_rate`
  - sustained rise in `quality_component_unsupported_claims`

### 7) Premium Conversion Funnel
- Tracked product events:
  - `premium_touchpoint_viewed`
  - `upgrade_initiated`
  - `upgrade_completed`
  - `premium_feature_activation`
- Aggregated endpoint:
  - `GET /api/analytics/premium/funnel?window_days=30`
- Tracking endpoint:
  - `POST /api/analytics/premium/events`
- Expected dimensions:
  - `touchpoint` (for example `dashboard.gap_analysis`, `artifacts.templates`)
  - `capability` (for example `premium_proactive_copilot`, `premium_artifact_templates`)
- Funnel rates available per touchpoint:
  - `view_to_upgrade_initiated`
  - `initiated_to_completed`
  - `completed_to_activation`
  - `view_to_activation`

## Alert Thresholds (initial)
- API 5xx rate > 2% for 10 minutes.
- `chat.stream.failed` rate > 5% for 10 minutes.
- Stream fallback rate > 10% for 10 minutes.
- Artifact generation failure rate > 8% for 15 minutes.
- Recommendation endpoints p95 latency > 12s for 15 minutes.

Tune thresholds after one full release cycle based on observed baseline.

## Manual Verification Checklist
1. Send one `/api/chat` request and confirm `X-Correlation-ID` in response.
2. Send one `/api/chat/stream` request and confirm all SSE events include same `correlation_id`.
3. Trigger `/api/artifact` and check `artifact.generation.*` events in logs.
4. Trigger `/api/pipeline/gap-analysis` and check `recommendation.gap_analysis.*`.
5. Search logs by one `correlation_id` and verify complete lifecycle.
