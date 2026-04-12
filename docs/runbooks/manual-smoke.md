# Manual Smoke Runbook

This smoke validates the core user journey:
- auth -> ingest -> chat -> summarize -> artifact download

## 1. Start API (local or server)
Example local:
```bash
python -m uvicorn docops.api.app:app --host 127.0.0.1 --port 8000
```

Health:
```bash
curl -i http://127.0.0.1:8000/api/health
curl -i http://127.0.0.1:8000/api/ready
```

## 2. Auth
```bash
PORT=8000
EMAIL="smoke_$(date +%s)@example.com"
PASS="SmokePass123!"

curl -s -X POST "http://127.0.0.1:$PORT/api/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"Smoke User\",\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" >/dev/null || true

TOKEN=$(curl -s -X POST "http://127.0.0.1:$PORT/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "TOKEN_LEN=${#TOKEN}"
```

Expected: `TOKEN_LEN` greater than `0`.

## 3. Ingest
```bash
DOC_TITLE="smoke_doc_$(date +%s)"
DOC_FILE="${DOC_TITLE}.txt"

curl -s -X POST "http://127.0.0.1:$PORT/api/ingest/clip" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"title\":\"$DOC_TITLE\",\"text\":\"Smoke content: metric 71%, cost R$ 1010, ETA 30 days.\"}"
```

Expected: JSON with `files_loaded >= 1`.

## 4. Chat
```bash
curl -s -X POST "http://127.0.0.1:$PORT/api/chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"Summarize ${DOC_TITLE} in 3 bullets.\",\"doc_names\":[\"$DOC_FILE\"]}"
```

Expected: non-empty `answer`.

## 4.1 Capabilities (feature flag snapshot)
```bash
curl -s -X GET "http://127.0.0.1:$PORT/api/capabilities" \
  -H "Authorization: Bearer $TOKEN"
```

Expected:
- JSON with `map` and `flags`
- `chat_streaming_enabled` present in `map`

## 4.2 Stream chat endpoint (when enabled)
```bash
curl -N -s -X POST "http://127.0.0.1:$PORT/api/chat/stream" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"Resumo rapido de ${DOC_TITLE}\"}"
```

Expected:
- `data: {"type":"start"...}`
- multiple `data: {"type":"delta"...}`
- one `data: {"type":"final"...}`

## 5. Summary and artifact creation
```bash
curl -s -X POST "http://127.0.0.1:$PORT/api/summarize" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"doc\":\"$DOC_FILE\",\"summary_mode\":\"brief\",\"save\":true}" \
  > /tmp/smoke_summary.json

cat /tmp/smoke_summary.json
```

Expected:
- `answer` non-empty
- `artifact_filename` present

## 6. Artifact list and download by ID
```bash
ART_ID=$(curl -s -X GET "http://127.0.0.1:$PORT/api/artifacts" \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; a=json.load(sys.stdin); print(a[0]['id'] if a else '')")

curl -s -X GET "http://127.0.0.1:$PORT/api/artifacts/id/$ART_ID" \
  -H "Authorization: Bearer $TOKEN" > /tmp/smoke_artifact.md

test -s /tmp/smoke_artifact.md && echo "ARTIFACT_OK"
```

Expected: `ARTIFACT_OK`.

## Optional cleanup
```bash
curl -i -X DELETE "http://127.0.0.1:$PORT/api/artifacts/id/$ART_ID" \
  -H "Authorization: Bearer $TOKEN"
```
