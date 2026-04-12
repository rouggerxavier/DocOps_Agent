# API Contract Versioning Policy

## Purpose
Keep `/api/chat` and `/api/chat/stream` contracts stable, detectable, and safe for frontend/backward compatibility.

## Source Of Truth
- Stream lifecycle reference:
  - `docs/runbooks/chat-stream-contract.md`
- Contract snapshots:
  - `tests/contracts/snapshots/chat_response.contract.json`
  - `tests/contracts/snapshots/chat_stream.contract.json`
- Runtime validator:
  - `docops/api/contracts.py` (`validate_chat_stream_sequence`)
- Contract tests:
  - `tests/contracts/test_chat_contracts.py`

## Version Fields
- `CHAT_RESPONSE_CONTRACT_VERSION` in `docops/api/contracts.py`
- `CHAT_STREAM_CONTRACT_VERSION` in `docops/api/contracts.py`
- Matching `version` field inside each snapshot file

All three must stay aligned.

## Semver Rules
- Patch (`x.y.Z`):
  - Internal refactor with no schema or sequence impact.
  - Snapshot files unchanged.
- Minor (`x.Y.z`):
  - Backward-compatible additive change.
  - Example: adding optional field/event metadata accepted by existing clients.
  - Update snapshots and bump version.
- Major (`X.y.z`):
  - Breaking change.
  - Examples:
    - rename/remove required field
    - type change on existing field
    - stream event order/lifecycle break
  - Update snapshots, bump version, and coordinate frontend rollout.

## Change Process
1. Update implementation.
2. Update snapshot JSON files to the new contract.
3. Bump corresponding version constant in `docops/api/contracts.py`.
4. Run:
   - `pytest -q tests/contracts`
   - `pytest -q`
5. Update docs when behavior changes.

## CI Enforcement
- Workflow: `.github/workflows/ci-quality-gates.yml`
- Contract gate: `python -m pytest -q tests/contracts`
- Full regression still runs after contract tests.

If contract snapshots drift unintentionally, CI fails and blocks merge.
