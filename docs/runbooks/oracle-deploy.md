# Oracle Deploy Runbook

This runbook reflects the current GitHub Actions workflow:
- `.github/workflows/deploy-oracle.yml`

## Prerequisites
- Oracle VM reachable over SSH.
- `docops` systemd service installed on VM.
- Repository cloned at `/home/ubuntu/DocOps_Agent`.
- GitHub secrets configured:
  - `ORACLE_HOST`
  - `ORACLE_USER`
  - `ORACLE_SSH_KEY`

## Important compatibility note
- CI runs on Python `3.11` and can use `requirements.lock.txt`.
- Oracle host currently uses Python `3.10`.
- Deploy workflow installs `requirements.txt` on server to avoid `3.11+` lockfile conflicts.

## Automatic flow (main branch push)
1. Backend pytest gate runs.
2. Frontend lint/build gate runs.
3. SSH deploy job:
   - `git fetch --prune origin main`
   - `git checkout main`
   - `git pull --ff-only origin main`
   - `source .venv/bin/activate`
   - `pip install -r requirements.txt`
   - `sudo systemctl restart docops`
   - healthcheck loop on `http://127.0.0.1:8000/api/health`

## Manual verification after deploy
On Oracle host:
```bash
cd /home/ubuntu/DocOps_Agent
source .venv/bin/activate
curl -i http://127.0.0.1:8000/api/health
curl -i http://127.0.0.1:8000/api/ready
sudo systemctl --no-pager --full status docops | head -n 30
```

## Troubleshooting
If service is unhealthy:
```bash
sudo journalctl -u docops -n 200 --no-pager
```

## Fast rollback via feature flags
If deploy is healthy but a premium capability misbehaves, use environment flags
to disable features without reverting code.

Example (`/home/ubuntu/DocOps_Agent/.env`):
```bash
FEATURE_FLAGS_DISABLE_ALL=true
```

Or disable only streaming:
```bash
FEATURE_CHAT_STREAMING_ENABLED=false
```

Then restart:
```bash
sudo systemctl restart docops
```

Validate:
```bash
curl -s -H "Authorization: Bearer <TOKEN>" \
  http://127.0.0.1:8000/api/capabilities | jq '.map'
```

If dependency install fails due Python version:
- keep `requirements.txt` path for deploy on Python `3.10`
- do not force lockfile install on server until host is upgraded to Python `3.11+`

If SSH connection hangs/refuses:
- check VM state in OCI console
- validate NSG/security list ingress for TCP `22`
- run local check:
```powershell
Test-NetConnection <oracle-ip> -Port 22
```
