# EchoNote: understand the code before the interview

## A. Project overview

EchoNote turns an uploaded recording into a saved transcript and summary. The web app is Next.js and TypeScript. FastAPI accepts metadata and streams the audio into private object storage. PostgreSQL remembers the note and its state. Celery workers use Redis to receive work, transcribe small audio chunks with Gnani, and summarize the resulting text with an LLM.

The main design decision is to separate the browser request from slow processing. A user can close the page after upload and return to the same note later. The second decision is to keep work intent and progress in PostgreSQL, so losing a queue message does not silently lose a note.

This is a shared review workspace. It is not a multi-tenant SaaS product, and it has no user authentication. Say this clearly rather than claiming security features that are not implemented.

## B. Exact request flow

1. The user selects a file and its primary language. `upload.tsx` checks extension, nonzero size and the server's configured maximum.
2. The browser sends metadata and a random upload key to `POST /api/audio-notes`. FastAPI validates it with `CreateNote`, generates a resource UUID and creates an `UPLOADING` row.
3. The browser uses XMLHttpRequest to `PUT` the raw file. XHR is used because it exposes actual upload byte progress. The backend counts every chunk; a dishonest declared size cannot bypass the byte limit.
4. The API holds a per-note advisory lock during the upload, writes to temporary disk and transfers the file to S3. The original filename is not used as a local path or object key.
5. After S3 succeeds, the database row becomes `QUEUED`, and processing attempt one begins. The HTTP response returns. The browser goes to `/notes/{id}`.
6. Beat runs the dispatcher every 30 seconds. It selects queued rows and publishes UUID plus run token to Redis. `dispatched_at` permits redispatch if the worker never starts.
7. A Celery worker acquires the note's advisory lock, reloads the row and checks the token and state. Duplicate deliveries either cannot acquire the lock or see a completed/failed note and stop.
8. The worker downloads the original to temporary disk. FFprobe checks the audio stream and duration. FFmpeg extracts one 30-second mono 16 kHz PCM WAV chunk at a time.
9. The Gnani adapter sends each chunk using the documented multipart REST request. The successful transcript is saved in the chunks array. The joined partial transcript and heartbeat are saved too.
10. When all chunks are done, the note becomes `SUMMARIZING`. Long text is split into bounded inputs, summarized, and reduced through the provider interface.
11. The summary and completion timestamp are saved with `COMPLETED`. All writes verify the run token so an old attempt cannot overwrite a new one.
12. The browser polls `/status` every three seconds, then fetches the complete note when processing reaches a terminal state. The history page polls every eight seconds. Audio playback uses a one-hour signed S3 URL.

## C. Twenty files to understand

| File | What to understand |
|---|---|
| `backend/app/main.py` | Validation boundary, create/upload/read/retry routes, raw streaming, consistent errors and stale read recovery |
| `backend/app/models.py` | SQLAlchemy entity, lifecycle enum, timestamps and checkpoint fields |
| `backend/app/schemas.py` | Pydantic API shapes, supported extensions, path sanitization and model serialization |
| `backend/app/db.py` | Engine, pool pre-ping, session factory and request dependency |
| `backend/app/config.py` | Environment variables, defaults and validated limits |
| `backend/app/workers.py` | Celery setup, Beat dispatcher, advisory locking, run-token checks and pipeline |
| `backend/app/services/audio.py` | FFprobe validation, chunk count and FFmpeg normalization |
| `backend/app/services/storage.py` | S3 clients, streamed transfer and signed playback URLs |
| `backend/app/services/providers.py` | Gnani request, LLM request, timeouts, error mapping and bounded retries |
| `backend/app/services/summary.py` | Unicode-safe byte splitting and bounded recursive reduction |
| `backend/app/logging_config.py` | Structured events without provider bodies, secrets or exception-message leakage |
| `backend/migrations/versions/0001_audio_notes.py` | Explicit reproducible initial schema |
| `frontend/lib/api.ts` | Typed response contracts, request timeout, safe error messages and state helpers |
| `frontend/components/upload.tsx` | File selection, real upload progress, cancellation, language and redirect |
| `frontend/components/dashboard.tsx` | Paginated persisted history, empty/error/loading states and polling cleanup |
| `frontend/components/note-view.tsx` | Status polling, terminal result loading, playback, transcript search and retry |
| `frontend/app/architecture/page.tsx` | Explanation of the real system and its boundaries |
| `backend/tests/test_workers.py` | Checkpoints, partial recovery, failure, token fencing and durable dispatch intent |
| `docker-compose.yml` | Local process boundaries, persistence, migration ordering and private infrastructure ports |
| `nginx.conf` | Direct API routing, upload limits and request buffering behavior |

Also be able to locate provider/validation tests, frontend UI tests and production Compose without memorizing them.

## D. Database field dictionary

| Field | Why it exists |
|---|---|
| `id` | Externally visible UUID; stable note URL |
| `upload_key` | Unique client key; repeated metadata requests do not create duplicate rows |
| `original_filename` | Human-readable label after sanitization |
| `storage_key` | Location of the private original audio object |
| `mime_type` | Canonical content type associated with the accepted extension; actual audio is later probed |
| `file_size` | Declared size, checked against received bytes; useful display metadata |
| `language` | Explicit Gnani language code for the recording |
| `duration` | Measured by FFprobe; nullable until worker validation |
| `status` | Typed lifecycle state used by worker, API and UI |
| `transcript` | Joined transcript text, including saved partial output after failure |
| `summary` | Final LLM summary; nullable until success |
| `chunks` | Ordered array of successful ASR text chunks; retry resumes at its length |
| `total_chunks` | Measured count from duration divided by 30, rounded up |
| `error_message` | Safe human-readable failure message, not a stack trace |
| `retryable` | Whether retry makes sense for this failure; combined with attempts and upload state |
| `attempts` | Processing attempt count; zero means the original upload was never confirmed saved |
| `run_token` | Fresh UUID for each processing attempt; fences stale writes |
| `created_at` | History ordering and display |
| `updated_at` | Heartbeat and most recent state/checkpoint update |
| `processing_started_at` | First processing start; preserved through retries |
| `completed_at` | Final success time |
| `dispatched_at` | Last successful dispatch transaction; prevents constant republishing |

There are indexes for history order and dispatcher/state queries, plus the unique upload key. Text is deliberately stored both as chunks and joined transcript: small storage duplication buys simple recovery and reading. Audio bytes are not duplicated into the database.

## E. Celery and Redis from first principles

A queue decouples the person asking for work from the process doing it. Redis holds a message such as “process note X with token Y.” Celery understands how to publish, receive and acknowledge those messages and execute a registered Python task.

Beat is the scheduler process; it periodically asks the dispatcher to run. The worker process executes dispatcher and processing tasks. Redis is the broker, not the business database. There is no Celery result store because results already belong to an AudioNote row.

Late acknowledgement means a task is acknowledged after execution, not before. A worker death can cause redelivery, so handlers must tolerate duplicate messages. The advisory lock prevents concurrent execution per note during normal operation; token checks prevent stale commits. Neither guarantees exactly-once calls to Gnani.

The prefetch multiplier is one so workers do not reserve large numbers of long tasks in advance. The default worker concurrency is two. A Redis visibility timeout larger than the hard task limit avoids ordinary long work being redelivered prematurely. Hard/soft time limits and stale detection bound failure behavior.

## F. Gnani ASR in this repository

The adapter is `GnaniASR.transcribe` in `providers.py`. It opens one decoded WAV chunk and issues the documented REST v3 request with the API-key header and language form field. HTTP status handling is centralized. On success it requires a true success flag and string transcript, then strips surrounding whitespace.

The adapter does not assume timestamps, speaker labels, language auto-detection or an undocumented asynchronous job ID. Thirty-second chunks are comfortably below the linked REST API's 60-second ceiling. WAV normalization makes client file encodings independent of provider input encoding. The trade-off is fixed-boundary cuts that can lose a word or cross-chunk context.

The local 125-second tone test proves extraction/duration behavior only. It does not prove speech recognition quality. Testing real speech with your real Gnani account remains necessary before submission.

## G. LLM summary in this repository

`SummaryProvider` is a Python Protocol defining a single method. It permits isolated tests and another provider without adding a class hierarchy. `OpenAISummary` is the real implementation. Its model, base URL and key are environment configured; the default is an OpenAI Chat Completions-compatible GPT-4.1 mini configuration.

The system prompt asks for a brief overview, key points and only explicitly stated actions/decisions. Source text is placed in a user message and treated as untrusted data. This mitigates prompt injection but does not guarantee perfect faithfulness.

For long text, `split_text` counts UTF-8 bytes rather than estimating tokens from English words. It preserves every character in order. A piece is limited to 12,000 bytes, with a separate system prompt and output cap of 700 tokens. The default model has ample capacity. Each piece is summarized; multiple summaries are joined and reduced again. Eight passes and a strict shrink check prevent unbounded reduction. A truncated or empty provider completion is an error, not a finished summary.

Intermediate LLM summaries are not persisted. A summarization retry can repeat those calls, while completed ASR chunks are retained. This is an explicit simplicity/cost trade-off.

## H. Failure walkthrough

| Situation | User experience | Internal behavior |
|---|---|---|
| Network fails during upload | Clear error, select/start again | Stream closes; API marks failed when possible; stale recovery covers abrupt disappearance |
| Unsupported extension/oversize | File or request rejected | Client checks for UX, server validates independently and counts received bytes |
| Corrupt media | Visible non-retryable failure | FFprobe/FFmpeg fail safely in worker; no provider call needed |
| Storage unavailable | Upload error | Note is not queued before storage success |
| Gnani timeout/429/5xx | Processing continues through bounded retries, then actionable failure | Up to three network attempts; successful earlier chunks preserved |
| Gnani auth/client error | Owner/configuration or recording message | No repeated automatic requests; technical status logged without response body |
| LLM failure | Transcript remains available, no false completed summary | Note fails; processing retry skips already-saved ASR chunks |
| Worker crash | Eventually failed with retry option | Late-ack delivery may retry; no-heartbeat recovery works via Beat or read routes |
| Page refresh during processing | Same URL and current stage | State is in PostgreSQL; no browser-only job state |
| Duplicate task delivery | One result, no new note | Lock excludes concurrency; token and state guards reject old/finished work |
| Provider succeeds but DB fails | May need retry | The last provider call can repeat; no exactly-once claim |
| Database unavailable | Service/connectivity error | No raw SQL error shown; restore database to recover |

## I. Forty-five likely interview questions

1. **Why background jobs?** ASR, decoding and LLM work exceed a normal request's useful lifetime. Workers let the upload response finish and results persist independently of the browser.
2. **Why Celery?** It provides worker execution, late acknowledgements, concurrency, task limits and Beat scheduling without building our own task runtime.
3. **Why Redis?** It is a simple Celery broker supported by the chosen stack. It carries small job references; it is not our only record that work exists.
4. **Why PostgreSQL?** We need durable state, transactions, unique constraints, row locking and advisory locks. These directly support creation, retry and worker coordination.
5. **Why object storage?** Audio is large binary data. S3 supports streaming transfers and signed playback while the database stays focused on metadata and text.
6. **Why not store audio in PostgreSQL?** It inflates backups and DB I/O without improving relational queries. A key connects the audio object to its metadata.
7. **Why polling instead of WebSockets?** Progress changes slowly, and the client only needs coarse state. Polling has simple reconnect behavior and no persistent connection infrastructure.
8. **What exactly is the progress percentage?** Only the browser upload uses a percentage. Processing uses states and measured completed chunk counts, not estimated wall-clock percentages.
9. **How do files longer than two minutes work?** FFprobe measures them and FFmpeg extracts 30-second chunks. The worker makes successive short Gnani REST calls and saves each success.
10. **Why not submit the original long file to the linked API?** The documented REST endpoint has a 60-second ceiling. Sending a multi-minute file directly would violate its contract.
11. **Why choose fixed chunks instead of Gnani Batch?** It keeps the linked REST contract small and checkpointing explicit. The trade-off is more requests and possible boundary/context errors; batch is an alternative improvement.
12. **How are invalid files detected?** Extension and size validation happen at the API boundary, received bytes are counted, and FFprobe plus actual FFmpeg decoding validate media in the worker.
13. **Does MIME validation prove file content?** No. Browser MIME and filename extensions are untrusted hints. Decoding is the meaningful content check.
14. **Does uploading buffer the entire file in RAM?** No. Raw request chunks go to temporary disk, Boto3 transfers from disk, and the worker extracts one small WAV at a time.
15. **Why does the upload request wait for S3?** Queueing before storage success could dispatch a missing recording. The request waits for storage I/O but never for ASR or summary work.
16. **What is the source of truth for a job?** PostgreSQL. Redis transports task messages; queued rows remain eligible for publication after temporary broker failure.
17. **What if PostgreSQL commits but Redis publish fails?** The dispatcher scans the queued row again. API creation does not rely on one fragile immediate enqueue.
18. **What if Redis publish succeeds but dispatcher commit fails?** The same job can publish again. Duplicate delivery is tolerated by locks and state/token guards.
19. **What if two workers receive the same note?** A session advisory lock keyed by the note UUID permits only one at a time. The winner still verifies the current state and run token.
20. **Why both a lock and a run token?** The lock coordinates execution; the token fences stale writes after a new attempt begins. They solve related but different races.
21. **Is the system exactly once?** No. It aims for safe database state under at-least-once delivery. External provider calls can repeat around failure windows.
22. **What if Gnani succeeds but the DB update fails?** That chunk lacks a committed checkpoint, so retry may call Gnani again and incur another charge. Provider idempotency would be needed to close that gap.
23. **How does a retry resume?** The worker reads the saved `chunks` array and begins at its length. It does not redo earlier successful ASR chunks.
24. **Can two simultaneous retry clicks create two attempts?** Retry locks the row with `FOR UPDATE`. The first moves it to queued; the second sees an active state and receives 409.
25. **Are retries unlimited?** No. Transient provider calls get three attempts; processing attempts default to three total. Non-retryable failures and unsaved uploads cannot use processing retry.
26. **What if the worker crashes?** Celery late acknowledgements allow redelivery. Missing heartbeats also become visible failures after 15 minutes, allowing bounded manual recovery.
27. **What if Beat is down?** New queued work does not dispatch, but read-time stale recovery prevents an endless spinner. Restore Beat and retry eligible work.
28. **What if Redis loses all queued messages?** Queued database rows become eligible for redispatch. In-progress rows are not blindly restarted; stale recovery handles interrupted execution.
29. **Why no Celery result backend?** The application already stores status, transcript and summary in PostgreSQL. A second result store would duplicate ownership.
30. **Why use UUIDs?** Stable opaque resource URLs avoid sequential enumeration. UUIDs are not authentication or authorization.
31. **How is repeated note creation handled?** The client supplies a unique upload key. A matching key and metadata return the same row; changed metadata with that key returns 409.
32. **How are migrations handled?** Alembic has an explicit initial migration. Deployment runs it before app services. Production never calls `create_all`.
33. **What happens when the user refreshes?** The route UUID loads persisted data. The UI restarts polling if the state is still active.
34. **How are long transcripts summarized?** Split by conservative UTF-8 byte budget, summarize pieces, reduce their summaries, stop once a final input fits. Reject non-shrinking or excessive passes.
35. **Why not count words for the context limit?** Word-to-token ratios vary across languages and unbroken strings. Bytes are a conservative bound for the configured tokenizer; model changes still require checking the budget.
36. **Can the LLM invent facts?** Yes. The prompt discourages it, but we cannot guarantee faithfulness. The app retains the transcript and audio for checking important details.
37. **How are secrets protected?** Provider and storage keys stay in backend environment variables. They are never returned by config or embedded in public frontend variables; logs omit sensitive bodies.
38. **Are signed playback URLs permanent or private to one user?** They expire after one hour and are bearer links. Anyone with the link can use it until expiry; this shared workspace has no ownership checks.
39. **How would you add authentication?** Authenticate requests, add an owner ID to notes, scope every query/retry/playback route by owner, apply quotas and authorize uploads before accepting bytes.
40. **How would you support 10,000 simultaneous uploads?** Add admission control and quotas, direct multipart S3 uploads, finalize verification, rate-aware worker scaling, database capacity planning and monitoring. The current server-mediated design does not claim that scale.
41. **Why keep all chunk text and the full transcript?** It duplicates a little text to make retry resumption and reads simple. Audio dominates storage costs here.
42. **Which failures get immediate retry?** Network timeouts, rate limits and provider 5xx responses. Authentication/client errors do not improve with repeated immediate calls.
43. **Why use XHR for upload and fetch elsewhere?** XHR exposes upload progress events. Fetch is simpler for small JSON requests and polling.
44. **What did the tests actually prove?** API/worker behavior with isolated DB/provider substitutes, actual FFmpeg handling of 125-second audio, frontend builds, and fixture-based browser interactions. They do not prove live Gnani quality or unavailable infrastructure behavior.
45. **What would you improve first?** For a public product, ownership and quotas. For transcription quality, silence-aware/batch ASR. For reliability, provider-aware rate limiting, metrics and stronger handling of cross-service idempotency windows.

## J. Read the repository in this order

1. Read README scope and the API table in `docs/ARCHITECTURE.md`.
2. Draw the lifecycle, then read `models.py`, `schemas.py` and the initial migration.
3. Trace one metadata POST and content PUT through `main.py` into `storage.py`.
4. Read `workers.py` in this order: Celery configuration, dispatcher, worker entry point, checkpoint, pipeline.
5. Follow one chunk through `audio.py` and `GnaniASR`.
6. Follow one long transcript through `summary.py` and `OpenAISummary`.
7. Read `upload.tsx`, `api.ts`, `note-view.tsx`, then `dashboard.tsx`.
8. Read the tests beside the behavior they assert. Be able to explain why a SQLite lock stand-in does not prove PostgreSQL concurrency.
9. Read the Compose files, Dockerfiles and gateway together; point out every process and environment boundary.
10. Revisit the failure-window section and answer the interview questions out loud without looking at the answers.

## K. Focused study checklist

### MUST KNOW

- [ ] Reproduce the complete create → stream → store → queue → chunk → transcribe → summarize → display flow.
- [ ] Explain every AudioNote field and why status is in the database.
- [ ] Explain why a two-minute recording cannot go directly to the linked Gnani REST endpoint.
- [ ] Trace `request.stream()` and show where the received-byte limit is enforced.
- [ ] Explain the difference between API response completion and background processing completion.
- [ ] Run the default tests and explain checkpoint resumption and old-token rejection.
- [ ] Explain the API key header and multipart field names from the Gnani adapter.
- [ ] Explain the LLM prompt, byte-budget splitter, shrink check and output validation.
- [ ] Explain the advisory lock versus `FOR UPDATE` versus run-token fencing.
- [ ] Admit the external duplicate-call/billing window; do not claim exactly once.
- [ ] Explain why Redis is the broker and PostgreSQL is the source of truth.
- [ ] Know what happens when the browser refreshes or upload/network/worker/provider fails.
- [ ] Identify server-only environment variables and the public API-base setting.
- [ ] State the shared-workspace assumption and why UUIDs do not authorize access.

### SHOULD KNOW

- [ ] Explain late acknowledgement, visibility timeout, prefetch and worker concurrency using `workers.py`.
- [ ] Explain publish-before-commit and why duplicate messages are preferable to lost work here.
- [ ] Explain the queued-row redispatch interval and stale heartbeat timeout.
- [ ] Demonstrate Alembic upgrade/check on an actual disposable PostgreSQL database.
- [ ] Explain private buckets, presigned URL expiration and browser-reachable storage endpoints.
- [ ] Show the difference between client extension validation and worker content decoding.
- [ ] Explain the upload gateway's disabled request buffering and timeout settings.
- [ ] Trace every loading/error/empty/processing/success branch in the frontend.
- [ ] Explain polling cleanup on unmount and why it avoids runaway timers.
- [ ] Explain why intermediate summary requests may repeat and what persistence would cost.
- [ ] Explain the deterministic newest-first order and offset pagination limit.

### BONUS

- [ ] Sketch a direct S3 multipart upload and verified finalize endpoint that replaces the existing content PUT.
- [ ] Explain how provider-supported idempotency could reduce double billing.
- [ ] Describe migrating the note-as-outbox design into a separate transactional outbox if job types multiply.
- [ ] Explain rate-aware worker admission and why simply increasing concurrency can trigger 429s.
- [ ] Plan per-user ownership, quotas and retention around the current schema.
- [ ] Compare fixed chunks with silence-aware or batch ASR using the actual quality trade-off.
- [ ] Identify useful metrics: queue age, stale jobs, processing duration, provider status counts and retry rate.
- [ ] Explain advisory-lock connection failure and why external side effects still need separate guarantees.

A useful rehearsal: explain the project in 90 seconds, then spend five minutes tracing one failure. The interview should sound like you understand the code, not like you memorized technology names.
