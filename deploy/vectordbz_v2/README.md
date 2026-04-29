# VectorDBZ V2 Deployment

Deploy only a clean git ref after local gates pass.

## Local Gates

```powershell
python -m pytest tests\vectordbz_v2 -q
python -m vectordbz_v2.init_schema
python -m vectordbz_v2.test_smoke
python -m vectordbz_v2.collector_health --limit 1
python -m vectordbz_v2.source_backfill --start 2026-04-01 --end 2026-04-28 --per-day-limit 20 --dry-run
```

Run a bounded live pipeline with checkpointing:

```powershell
python -m vectordbz_v2.long_task_runner --collect-live --github-limit 2 --hf-limit-per-type 1 --embed-max 40 --embed-batch 4 --rerank-days 30 --checkpoint-path .codex/checkpoints/v2-long-task.json --resume
```

Also run a scoped token scan before creating the deploy ref. No provider token, SSH password, database password, or PAT may be committed.

## Server Layout

```text
/opt/vectordbz-v2-harness       clean checkout or archive extraction
/opt/vectordbz-v2-harness/.venv Python virtualenv
/etc/vectordbz/v2.env           server-only secrets and runtime config
/var/lib/vectordbz_v2/checkpoints
```

Copy one environment template:

```bash
sudo mkdir -p /etc/vectordbz /var/lib/vectordbz_v2/checkpoints
sudo cp profiles/us.env.example /etc/vectordbz/v2.env
sudo nano /etc/vectordbz/v2.env
python3 -m venv /opt/vectordbz-v2-harness/.venv
/opt/vectordbz-v2-harness/.venv/bin/python -m pip install -U pip
/opt/vectordbz-v2-harness/.venv/bin/python -m pip install -r deploy/vectordbz_v2/requirements.txt
/opt/vectordbz-v2-harness/.venv/bin/python -m vectordbz_v2.init_schema
```

Install API service:

```bash
sudo cp deploy/vectordbz_v2/vectordbz-v2-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vectordbz-v2-api
sudo systemctl status vectordbz-v2-api --no-pager
```

Expose the profile port only after the service is healthy. The 153 profile defaults to
4636; the US profile defaults to 4640 to avoid the existing v1 dashboard/backend:

```bash
source /etc/vectordbz/v2.env
curl -fsS "http://127.0.0.1:${VDBZ_API_PORT}/api/v2/health"
sudo ufw allow "${VDBZ_API_PORT}/tcp" || true
```

Use cloud firewall/security-group rules to allow the same TCP port from the intended
client range.

## Long Task

```bash
cd /opt/vectordbz-v2-harness
source .venv/bin/activate
python -m vectordbz_v2.long_task_runner \
  --collect-live \
  --github-limit 10 \
  --hf-limit-per-type 10 \
  --embed-max 5000 \
  --embed-batch 64 \
  --rerank-days 30 \
  --checkpoint-path /var/lib/vectordbz_v2/checkpoints/daily.json \
  --resume
```
