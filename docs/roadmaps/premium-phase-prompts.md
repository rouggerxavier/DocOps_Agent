# Prompt Playbook By Phase

## How To Use
- Use these prompts as execution briefs for AI-assisted implementation.
- Replace placeholders in `{braces}` before running.
- Keep each run scoped to one feature slice and one PR where possible.

---

## Phase 1 Prompts: Premium Chat Experience

### Product prompt
```text
You are the product lead for DocOps.
Design the premium chat interaction spec for "{feature_slice}".

Context:
- Current chat supports SSE and non-stream fallback.
- Need premium feel: clarity, smoothness, low friction.

Deliver:
1) User story set (happy path, fallback path, edge path).
2) UX behavior contract (state transitions and copy).
3) Acceptance criteria that QA can verify.
4) Non-goals to avoid scope creep.
5) Event instrumentation list for analytics.
```

### Frontend implementation prompt
```text
You are a senior frontend engineer in a React + TypeScript app.
Implement "{feature_slice}" for chat premium UX.

Constraints:
- Do not break current chat response schema.
- Keep streaming + fallback behavior stable.
- Add robust state handling for partial stream and retries.

Deliver:
1) File-by-file change plan.
2) Final code changes.
3) Unit/integration test updates.
4) Risk notes and mitigations.
5) Manual validation checklist.
```

### Backend implementation prompt
```text
You are a backend engineer for FastAPI.
Implement "{feature_slice}" in chat streaming pipeline.

Constraints:
- Preserve backward compatibility for /api/chat.
- Keep stream event schema explicit and documented.
- Include correlation id in logs.

Deliver:
1) API contract (request/response/event schema).
2) Endpoint and service changes.
3) Error handling policy (recoverable vs fatal).
4) Test plan with contract tests for stream events.
5) Rollout controls with feature flags.
```

### QA prompt
```text
You are QA lead.
Create a full test matrix for "{feature_slice}" in chat.

Include:
- Functional tests for streaming lifecycle.
- Network degradation cases.
- Recovery from aborted stream.
- Regression checks for non-stream endpoint.
- Visual checks for UI state transitions.

Output:
1) Test cases grouped by priority.
2) Expected results.
3) Automation candidates and manual-only checks.
```

---

## Phase 2 Prompts: Trust And Evidence

### Product prompt
```text
Design a trust framework for DocOps answers focused on "{topic}".

Need:
- Clear user-facing confidence explanation.
- Actionable next steps when confidence is low.
- Balance between transparency and cognitive load.

Deliver:
1) Confidence UX spec.
2) Decision rules for low-confidence behavior.
3) Copy guidelines for warnings and recommendations.
4) Success metrics for trust improvements.
```

### Backend prompt
```text
Implement confidence scoring and evidence policy for "{topic}".

Requirements:
- Score must be decomposable into reason codes.
- Expose score + reasons in API response.
- Add guardrail behavior when confidence threshold is not met.

Deliver:
1) Scoring formula and reason taxonomy.
2) API schema updates.
3) Logging and metrics changes.
4) Unit tests and threshold tests.
```

### Frontend prompt
```text
Implement confidence and evidence surfaces for "{topic}".

Requirements:
- Show score level and reasons in plain language.
- Provide one-click recovery actions.
- Keep layout readable on desktop and mobile.

Deliver:
1) Component architecture.
2) UI states and interaction behavior.
3) Test updates.
4) Accessibility checks.
```

### QA prompt
```text
Build verification plan for trust layer "{topic}".

Cover:
- Correctness of reason-to-UI mapping.
- Threshold transitions around edge scores.
- Consistency between cited sources and evidence panel.
- Behavior in strict grounding mode.
```

---

## Phase 3 Prompts: Premium Artifact Studio

### Product prompt
```text
Define premium artifact experience for "{artifact_type}".

Need:
- Template quality that feels publish-ready.
- Practical study structure, not just pretty formatting.
- Smooth path from chat output to artifact save/export.

Deliver:
1) Template spec with section rules.
2) Metadata model users can filter and search.
3) UX flow from chat to artifact studio.
4) Acceptance criteria for quality.
```

### Backend prompt
```text
Implement artifact pipeline improvements for "{artifact_type}".

Requirements:
- Consistent metadata schema.
- Stable markdown-to-pdf rendering.
- Link artifact to source conversation turn when applicable.

Deliver:
1) Service and schema changes.
2) Migration/backward compatibility plan.
3) Error taxonomy and retries.
4) Tests for rendering and metadata integrity.
```

### Frontend prompt
```text
Implement artifact studio UI for "{artifact_type}".

Requirements:
- Template selection UX.
- Metadata preview and edit.
- Export and share actions.

Deliver:
1) Page/component changes.
2) State flow for generate/save/export.
3) Empty/error/loading states.
4) Visual polish checklist.
```

### QA prompt
```text
Create QA plan for premium artifacts "{artifact_type}".

Cover:
- Template fidelity.
- Export correctness.
- Metadata persistence.
- Chat-to-artifact transition.
```

---

## Phase 4 Prompts: Personalization And Memory

### Product prompt
```text
Design personalization controls for "{persona_segment}".

Need:
- Clear defaults and override behavior.
- Transparent memory usage.
- Easy reset controls.

Deliver:
1) Preference model and user settings IA.
2) UX copy for "using your preferences".
3) Privacy-facing explanations.
4) Success criteria for reduced setup friction.
```

### Backend prompt
```text
Implement preference persistence and runtime injection for "{persona_segment}".

Requirements:
- Preference schema versioning.
- Safe defaults when fields are missing.
- Auditable updates for sensitive fields.

Deliver:
1) Data model and API endpoints.
2) Runtime merge rules.
3) Privacy and retention guardrails.
4) Tests for consistency and isolation.
```

### Frontend prompt
```text
Implement personalization settings and per-message overrides.

Requirements:
- Settings page with grouped controls.
- Quick overrides in chat composer.
- Reset controls with clear scope.

Deliver:
1) UI changes and state model.
2) API integration details.
3) Accessibility and responsiveness checks.
4) Regression test updates.
```

### QA prompt
```text
Plan QA for personalization and memory behavior.

Cover:
- Persistence across sessions.
- Override precedence rules.
- Reset behavior per scope.
- Privacy controls and edge cases.
```

---

## Phase 5 Prompts: Proactive Copilot

### Product prompt
```text
Define recommendation system for "{recommendation_surface}".

Need:
- Helpful, non-intrusive suggestions.
- Clear "why this recommendation" explanation.
- User control over volume and category.

Deliver:
1) Recommendation taxonomy.
2) Ranking principles.
3) UX behavior for accept/dismiss/snooze.
4) Quality metrics.
```

### Backend prompt
```text
Implement recommendation engine for "{recommendation_surface}".

Requirements:
- Deterministic baseline heuristics.
- Traceable explanation fields.
- Feedback loop ingestion.

Deliver:
1) Signal model and ranking logic.
2) API contract for recommendations.
3) Telemetry events.
4) Tests for ranking and edge cases.
```

### Frontend prompt
```text
Implement recommendation cards and quick actions.

Requirements:
- One-click execution where possible.
- Explainability snippet on each recommendation.
- Snooze/mute controls.

Deliver:
1) UI and state flow.
2) Action handlers and optimistic UX.
3) Failure handling UX.
4) Tests and analytics events.
```

### QA prompt
```text
QA plan for proactive recommendation quality.

Cover:
- Relevance sanity checks.
- Control settings (mute/snooze) persistence.
- Action completion and rollback.
- Recommendation analytics integrity.
```

---

## Phase 6 Prompts: Monetization And Packaging

### Product prompt
```text
Design premium packaging for "{tier_strategy}".

Need:
- Clear free vs premium outcomes.
- Contextual and respectful upgrade points.
- No dark patterns.

Deliver:
1) Capability matrix by tier.
2) Upgrade UX moments and copy.
3) Conversion event plan.
4) Guardrails for premium messaging.
```

### Backend prompt
```text
Implement entitlement architecture for "{tier_strategy}".

Requirements:
- Backend-first enforcement.
- Capability checks reusable across endpoints.
- Safe error contracts for locked features.

Deliver:
1) Entitlement middleware design.
2) Endpoint integration plan.
3) Test matrix for free/premium paths.
4) Rollout and rollback plan.
```

### Frontend prompt
```text
Implement capability-aware UI and upgrade flows.

Requirements:
- Locked state components.
- Contextual CTA tied to user intent.
- Seamless refresh after entitlement change.

Deliver:
1) Component updates.
2) Routing and state updates.
3) Copy and visual hierarchy rules.
4) Regression tests.
```

### QA prompt
```text
QA plan for monetization and entitlement behavior.

Cover:
- Feature locks in UI and API.
- Upgrade prompt correctness.
- Post-upgrade immediate access.
- Negative tests for bypass attempts.
```

---

## Master Prompt: End-To-End Execution Controller

```text
You are an execution lead coordinating premium product implementation.

Context:
- Product: DocOps
- Current branch: {branch_name}
- Current phase: {phase_name}
- Feature slice: {feature_slice}

Objective:
Deliver this slice end-to-end with production quality.

You must output:
1) Scope summary (what is in/out).
2) Technical design (frontend/backend/data/ops).
3) Step-by-step implementation plan.
4) Testing strategy (unit/integration/e2e/manual).
5) Rollout strategy with feature flags.
6) Documentation updates required.
7) Risks and mitigations.
8) Definition of done checklist.

Constraints:
- Keep backward compatibility unless explicitly approved to break.
- Include observability and analytics in the same implementation.
- No "partial done" output: each slice must include code, tests, and docs.
```
