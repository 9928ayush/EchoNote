# EchoNote

An audio-notes workspace built with Next.js, TypeScript, FastAPI, PostgreSQL, S3-compatible storage, and Celery/Redis. Upload a recording, follow its processing stages, then reopen the transcript and summary from history.

**Scope:** a shared internship-review workspace, without account authentication. Anyone who can reach the API can read notes and spend configured provider credits. Use an access gateway for a private deployment. UUIDs are identifiers, not permissions.

**Verification status:** see [docs/VERIFICATION.md](docs/VERIFICATION.md). Source and build checks are distinct from live provider and infrastructure verification. Real credentials and infrastructure were not supplied; this repository has not been deployed or tested against paid providers.

## Run with Docker

Requirements: Docker Engine with Compose v2, enough disk for originals and temporary audio, and real Gnani and LLM API credentials. Allow outbound HTTPS to the providers and object storage.

```sh
cp .env.example .env
# Edit .env: GNANI_API_KEY, LLM_API_KEY, REPOSITORY_URL.
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 api worker beat
```

Open **http://localhost:8080**. The gateway routes `/api/` directly to FastAPI, avoiding Next.js upload buffering. The first startup creates a private MinIO bucket and runs the Alembic migration. On subsequent releases, run `docker compose run --rm migrate` before restarting application services.

Use speech in the selected language, not a sine wave, for a real ASR test. Start with a recording longer than two minutes. Test Gnani's hosted playground yourself with your account before submission: https://app.gnani.ai/voice/speech-to-text. This account-only step has not been performed here.

Local data persists in named Docker volumes. `docker compose down` stops services without removing the data. Do not use `down -v` unless you intend to erase it. MinIO ports and infrastructure ports bind only to loopback. The web gateway binds port 8080.

## Native development

Python 3.12+, Node 22+, FFmpeg/FFprobe and `uv` are required. Start local infrastructure first:

```sh
cp .env.example .env
# Fill credentials in .env, then:
docker compose up -d postgres redis minio bucket-init
```

Backend, from `backend/`:

```sh
cp .env.example .env
# Set the same database/storage passwords and real provider credentials.
uv sync --frozen --extra dev
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --no-access-log
```

Run two additional terminals in `backend/`:

```sh
uv run celery -A app.workers.celery worker --loglevel=INFO --concurrency=2
uv run celery -A app.workers.celery beat --loglevel=INFO --schedule=/tmp/echonote-beat
```

Frontend, from `frontend/`:

```sh
cp .env.example .env.local
npm ci
npm run dev
```

Open http://localhost:3000. Native development uses an explicit API base URL. Compose uses an empty base and the same-origin gateway. Do not set an internal Docker hostname as a browser-facing URL.

## Production deployment

The complete production container configuration is `docker-compose.production.yml`. It expects managed PostgreSQL, Redis and a private S3-compatible bucket. It runs only application services and the internal HTTP gateway.

1. Create the database, Redis instance and bucket. Provision restricted S3 credentials with read/write access only to the application's bucket. Configure database backups and TLS. Use a `postgresql+psycopg://` URL; percent-encode special characters in passwords. For encrypted Redis use `rediss://...` and the TLS settings required by the provider.
2. Copy `.env.production.example` to `.env.production`. Fill every required credential/endpoint, the real GitHub repository URL and the browser's origin. An empty `S3_ENDPOINT_URL` uses AWS's regional endpoint; for R2 or another provider set its real S3 API URL. `S3_PUBLIC_ENDPOINT_URL` can be empty when the normal endpoint is browser-accessible. Keep the bucket private. Browser playback URLs must use HTTPS on an HTTPS website.
3. Put a TLS reverse proxy or platform ingress in front of loopback port 8080. Forward requests without buffering and allow the intended upload size/time. Configure an access gateway if recordings are private. These are infrastructure settings, not frontend code changes.
4. Build and start:

```sh
docker compose --env-file .env.production -f docker-compose.production.yml up --build -d
# Subsequent deployments: run migration before replacing app containers.
docker compose --env-file .env.production -f docker-compose.production.yml run --rm migrate
```

5. Verify `/health/ready`, `/architecture`, the actual repository link, and the live flow described in `docs/VERIFICATION.md`. Provide the resulting public review URL to the evaluator. The assignment requires a reachable deployed application; a source ZIP alone is not submission-complete.

Alternatively deploy the frontend container, API container, worker and Beat as separate platform services. Run exactly one Beat scheduler; run migrations as a release job. Set `NEXT_PUBLIC_API_BASE_URL` **at frontend build time** if API and web use different origins. Set `CORS_ORIGINS` to a JSON array of the actual web origins. Keep PostgreSQL, Redis and storage private. Frontend secrets must never use the `NEXT_PUBLIC_` prefix.

This app needs a long-lived worker with FFmpeg, not a request-only/serverless FastAPI function. Give each worker temporary disk space for one original per concurrency slot plus a small WAV chunk. Two worker slots and 250 MiB uploads require at least 500 MiB of audio scratch space, plus runtime overhead. The API needs separate scratch capacity for concurrent uploads.

## Configuration

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLAlchemy PostgreSQL URL; schema managed by Alembic |
| `REDIS_URL` | Celery broker, no result backend |
| `S3_ENDPOINT_URL` | Server-facing S3 API endpoint; empty for AWS |
| `S3_PUBLIC_ENDPOINT_URL` | Optional browser-facing endpoint used when signing playback |
| `S3_REGION`, `S3_BUCKET` | Storage region and private bucket |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY` | Server-only credentials; AWS workload credentials also supported when empty |
| `GNANI_API_KEY`, `GNANI_URL` | REST v3 credentials and endpoint |
| `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` | OpenAI-compatible summary API; default GPT-4.1 mini |
| `CORS_ORIGINS` | JSON array of allowed browser origins |
| `REPOSITORY_URL` | Real HTTPS GitHub URL for `/architecture` |
| `MAX_UPLOAD_BYTES` | Default 262,144,000 (250 MiB), maximum setting 5 GiB |
| `MAX_DURATION_SECONDS` | Default 14,400 (four hours); adjustable |
| `MAX_ATTEMPTS` | Maximum user-initiated processing attempts, default 3 |
| `STALE_SECONDS` | No-heartbeat timeout, default 900, minimum 600 |
| `NEXT_PUBLIC_API_BASE_URL` | Optional browser-visible API origin, embedded at build time |

Limits are deliberate. The PDF says any size/length; no infrastructure can support literally unlimited uploads. Defaults comfortably exceed two minutes, and the UI states the actual limits before uploading. Raising them also requires sufficient disk, worker time limits, gateway settings and provider quota. The fixed worker hard limit is six hours of processing, independent of recording duration.

## Tests and checks

From `backend/`:

```sh
uv sync --frozen --extra dev
uv run ruff check app migrations tests
uv run pytest -q
uv run python -c 'from app.main import app; from app.workers import celery; print(len(app.routes))'
uv run alembic upgrade head --sql
```

The default suite uses SQLite for fast behavior checks and stubs external network calls. It does **not** establish PostgreSQL concurrency behavior. With a dedicated disposable PostgreSQL database:

```sh
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic upgrade head
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic check
TEST_DATABASE_URL="$TEST_DATABASE_URL" uv run pytest tests/test_postgres.py -q
```

From `frontend/`:

```sh
npm ci
npm run lint
npm run typecheck
npm run build
npx playwright install chromium
npm run dev
# In another terminal (browser tests use isolated API fixtures):
npm run test:ui
```

The build's `postbuild` script copies public/static assets into Next's standalone output. `npm run start` runs that standalone server directly. The Dockerfile uses the same standalone entry point; Docker is the recommended production path.

From root:

```sh
docker compose config --quiet
docker compose --env-file .env.production -f docker-compose.production.yml config --quiet
```

Never paste `docker compose config` output publicly: rendered environment variables can contain secrets.

## Repository map

- `frontend/app/`: App Router pages, global layout and styling.
- `frontend/components/`: upload, dashboard, note reader and shared UI.
- `frontend/lib/api.ts`: typed API client and formatting helpers.
- `backend/app/main.py`: REST routes, upload stream and error responses.
- `backend/app/models.py`, `schemas.py`: persistence model and API boundary.
- `backend/app/workers.py`: durable dispatch, lock, checkpoint, recovery and processing.
- `backend/app/services/`: media, S3, providers, long-text summarization.
- `backend/migrations/`: explicit initial database migration.
- `backend/tests/`, `frontend/tests/`: isolated behavior and UI tests.
- `docs/INTERVIEW_GUIDE.md`: request flow, field dictionary, code-reading order, 45 questions and focused study plan.
- `docs/ARCHITECTURE.md`: exact API and operational trade-offs.
- `docs/VERIFICATION.md`: completed checks and remaining live gates.

## Known trade-offs

Fixed 30-second cuts may break words and lose cross-chunk ASR context. There is no speaker diarization or invented timestamp alignment. A successful provider call followed by a failed DB checkpoint can be billed again on retry; this is at-least-once external execution, not exactly once. Summary partials are not persisted, so summary retries may repeat paid requests. Failed uploads are retained as history records. Object retention/cleanup is operational rather than automatic in this version.

No user accounts, quota enforcement or public-upload abuse prevention is claimed. Never expose this shared review workspace as an unrestricted public production service with valuable credentials. Scaling beyond review use needs ownership, quotas, direct multipart storage uploads, rate-aware workers and stronger operational monitoring.
