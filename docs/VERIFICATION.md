# Verification record

Recorded on 2026-10-02. This records evidence rather than declaring every integration tested.

## Completed checks

| Check | Result |
|---|---|
| Backend behavior tests | 33 passed; one real-PostgreSQL test skipped because PostgreSQL is unavailable |
| Backend Ruff lint | Passed |
| Backend formatting | Ruff applied |
| FastAPI and Celery imports | Passed; application routes and worker import successfully |
| PostgreSQL migration SQL generation | Passed using Alembic offline mode |
| Migration/schema agreement | Initial migration applied to disposable SQLite DB; `alembic check` reported no drift |
| Frontend lint | Passed |
| Frontend TypeScript | Passed |
| Frontend optimized build | Passed |
| Compose files | YAML parsed; services/build paths reviewed. Docker's own validator and containers not run |
| Source scan | No unfinished TODO/FIXME/dummy implementation; test mocks and the transcript input's HTML placeholder are legitimate |
| Dependency reproducibility | Python `uv.lock` and exported hashed `requirements.lock`; npm `package-lock.json` included |

The backend suite covers metadata validation, create idempotency, byte limits, streaming upload success/failure, state changes, retry fencing, partial transcription resumption, provider status/timeout mapping, the Gnani request contract, LLM request/response handling, Unicode input budgets and a real 125-second FFmpeg extraction test. A tone is not evidence of recognition quality.

Default API/worker tests use SQLite and explicit advisory-lock stand-ins. They test behavior, not PostgreSQL's lock semantics. An opt-in real PostgreSQL lock-exclusion test is included separately. One Starlette warning notes eventual migration from HTTPX to HTTPX2 for its test client; it does not fail the installed test suite.

## Browser checks

The application is tested with isolated API fixtures in `frontend/tests/ui.mjs`. Fixtures are test-only; there is no simulated provider path in application code. Browser checks do not constitute a live backend or provider integration test.

Passed in headless Chromium: empty history, unsupported-file feedback, upload/create redirect, processing polling, completed summary, transcript search, clipboard copy with permission, retry to queued state, architecture navigation, and service-error feedback. Desktop (1440 px) and mobile (390 px) screenshots were visually reviewed; the tested mobile note and architecture pages had no horizontal overflow. The ordinary browser download was unavailable, so the local check used a packaged headless Chromium binary with explicit launch settings; the repository test supports a normal Playwright Chromium installation.

## Live gates still required before submission

1. Start the full Compose stack on a machine with Docker. Run `docker compose config --quiet`; verify all long-lived services are healthy and the one-shot migration/bucket jobs exited successfully.
2. Apply/check migrations on actual PostgreSQL. Run the opt-in lock test with a dedicated test database. Never point destructive test setup at production.
3. Sign in to Gnani's playground with your account and try real speech. Configure the same real key in the deployment.
4. Upload real speech longer than two minutes through the web UI, in a supported language. Check the transcript and summary against the recording, including words at chunk boundaries.
5. Refresh during transcription, close/reopen a completed note, play its original audio, search and copy text, and inspect history from a second browser.
6. Stop the worker during a recording. Verify stale recovery/manual retry and retained ASR checkpoints. Temporarily stop Redis and verify queued work is dispatched after restoration.
7. Test invalid audio, a provider timeout/rate limit in a controlled test environment, and an LLM failure. Inspect safe user messages and structured server logs.
8. Confirm real S3 private access, signed playback expiry, HTTPS, exact CORS origins, an access gate if needed, the GitHub link and backups.
9. Open the deployed URL from an external browser. The assignment's deployment requirement is not fulfilled until this works.

No real Gnani/LLM credentials were supplied, no paid provider calls were made, and the project has not been deployed. Docker, Redis, S3 and PostgreSQL were not available as running integration services in this authoring environment. These facts must not be represented as successful end-to-end validation.
