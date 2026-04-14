# Main Premium Implementation Brief

## Context
Work from the current `main` frontend baseline.

Base branch:
- `origin/main`

Working branch:
- `feat/main-premium-gap-implementation`

Important constraint:
- Do not rebuild the old premium UI from the deprecated roadmap branch.
- Preserve the current frontend shell, mobile behavior, layout patterns, navigation, and design language already present in `main`.

## Objective
Complete the remaining premium roadmap work on top of the new frontend already living in `main`.

This implementation should extend the current product, not replace it.

## What Is Already Present
Do not redo these unless needed for integration:
- streaming chat lifecycle and fallback UX
- trust/evidence card and explainability panel
- artifact templates, metadata, filters, and chat-to-artifact flow
- personalization APIs and preferences UI
- daily question surface
- observability, correlation, and contract-test foundations

## What Still Needs To Be Implemented

### Priority 1: Gap Analysis Product Surface
Build a real frontend flow for the existing backend endpoint.

Deliver:
- visible user entry point for gap analysis
- loading, success, empty, and error states
- readable presentation of identified learning gaps
- actionable next steps from results
- connection to study actions where possible

Must integrate with existing backend:
- `POST /api/pipeline/gap-analysis`

### Priority 2: Proactive Copilot Completion
Turn the existing partial recommendation groundwork into real product UX.

Deliver:
- dashboard recommendation surfaces
- contextual study recommendations
- "why this recommendation" explanation
- one-click actions where possible
- dismiss and snooze controls
- recommendation fatigue controls in product behavior

If needed, add backend support for recommendation ranking and persistence, but keep the product experience aligned with the new frontend.

### Priority 3: Entitlement And Premium Packaging Foundation
Implement premium gating in a backend-first way.

Deliver:
- entitlement guard layer for premium routes/features
- consistent locked-feature contract
- frontend locked states for premium-only actions
- capability-aware rendering

Do not add intrusive upgrade UX before entitlement checks are real.

### Priority 4: Upgrade UX And Premium Messaging
After entitlement enforcement exists:
- add contextual upgrade prompts
- keep prompts tied to real user intent
- avoid generic or spammy CTA placement
- ensure post-upgrade capability refresh is immediate

## Frontend Guidance
- Keep the new `main` visual language.
- Preserve mobile-first behavior already introduced in the current frontend.
- Avoid reintroducing older page structures from the deprecated branch.
- Reuse existing capability and API client patterns.
- Follow the current app’s component and page conventions instead of creating parallel product shells.

## Backend Guidance
- Prefer backend-first enforcement for premium controls.
- Reuse existing feature flag infrastructure.
- Reuse existing observability event patterns.
- Add tests for every new route or capability change.

## Delivery Strategy
Implement in small vertical slices, in this order:
1. gap analysis UI
2. proactive recommendation surfaces
3. entitlement enforcement
4. locked-state UI
5. upgrade messaging

Each slice should include:
- code
- tests
- docs/runbook updates when behavior changes

## Ready-To-Use Prompt
```text
You are implementing the remaining premium roadmap work for DocOps.

Branch context:
- Base the work on the current main frontend architecture.
- Do not restore or recreate the deprecated premium UI from the old roadmap branch.
- Preserve the current responsive layout, mobile behavior, page structure, and design language already present in main.

Primary objective:
Implement the missing premium roadmap functionality that is not yet fully delivered in main.

Start with this execution order:
1. Build a real product surface for gap analysis using the existing backend endpoint.
2. Complete proactive copilot UX with recommendation cards, why-this explanations, and dismiss/snooze controls.
3. Implement backend-first premium entitlement enforcement.
4. Add locked premium states and contextual upgrade UX only after entitlement enforcement exists.

Requirements:
- Reuse existing API/client/capabilities infrastructure.
- Keep observability and tests in the same implementation slice.
- Do not regress existing chat, artifact, personalization, or dashboard behavior.
- Prefer incremental integration into the new frontend instead of parallel replacement flows.

Deliver:
1. Scope summary.
2. File-by-file implementation plan.
3. Code changes.
4. Tests added or updated.
5. Notes about flags, rollout, and remaining risks.
```
