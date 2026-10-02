import type { Metadata } from "next";
import { RepositoryLink } from "@/components/repository-link";
export const metadata: Metadata = { title: "Architecture" };
export default function Page() {
  return (
    <>
      <div className="topbar">Workspace / Architecture</div>
      <article className="page-content architecture">
        <header className="page-heading">
          <div>
            <div className="eyebrow">HOW ECHONOTE WORKS</div>
            <h1>A recording, end to end.</h1>
            <p>A small asynchronous system with durable checkpoints.</p>
          </div>
        </header>
        <RepositoryLink />
        <div className="flow" aria-label="Processing flow">
          <div>
            <b>1 · Upload</b>
            <small>Browser → FastAPI → private S3</small>
          </div>
          <div>
            <b>2 · Transcribe</b>
            <small>PostgreSQL → Celery / Redis → Gnani</small>
          </div>
          <div>
            <b>3 · Summarize</b>
            <small>Worker → LLM → PostgreSQL → browser</small>
          </div>
        </div>
        <section>
          <h2>From upload to a finished note</h2>
          <ol>
            <li>
              The browser creates a note with a UUID and validated metadata. It
              then streams the file to FastAPI using a separate request. Browser
              transfer progress is a real byte percentage.
            </li>
            <li>
              FastAPI writes the stream to temporary disk with an enforced byte
              limit, uploads it to private S3-compatible storage, and marks the
              note as queued. It does not transcribe inside this request.
            </li>
            <li>
              A Celery Beat dispatcher scans PostgreSQL every 30 seconds and
              publishes queued work to Redis. A worker claims the note with a
              PostgreSQL advisory lock.
            </li>
            <li>
              The worker downloads the recording to temporary disk. FFprobe
              checks that it has decodable audio and an acceptable duration.
              FFmpeg produces one 30-second, mono, 16 kHz WAV chunk at a time.
            </li>
            <li>
              The Gnani adapter transcribes each chunk. Each successful response
              is saved before continuing. After transcription, a separate
              summary service calls the configured LLM.
            </li>
            <li>
              The browser polls a lightweight status endpoint every three
              seconds and retrieves the finished result. History and results
              survive page refreshes.
            </li>
          </ol>
        </section>
        <section>
          <h2>One responsibility for each part</h2>
          <dl>
            <dt>Next.js</dt>
            <dd>
              App Router pages, file selection, transfer progress, history,
              playback, transcript reading and visible errors.
            </dd>
            <dt>FastAPI</dt>
            <dd>
              Typed request validation, streamed upload, metadata and retry
              endpoints, temporary playback URLs.
            </dd>
            <dt>PostgreSQL</dt>
            <dd>
              The source of truth: filenames, storage keys, states, attempts,
              saved chunks, transcript and summary.
            </dd>
            <dt>S3</dt>
            <dd>
              Original audio bytes in a private bucket. The database stores a
              key, never the audio blob.
            </dd>
            <dt>Redis</dt>
            <dd>
              Celery message transport. It is not the authoritative record of
              unfinished work.
            </dd>
            <dt>Celery</dt>
            <dd>
              Worker execution and a scheduled dispatcher. Long network and
              audio tasks happen here.
            </dd>
          </dl>
        </section>
        <section>
          <h2>Long audio, honest progress</h2>
          <p>
            The linked Gnani REST API accepts clips up to 60 seconds. This
            application uses 30-second chunks, so a recording longer than two
            minutes needs no long-running browser request. Memory use stays
            bounded: the original file is streamed to disk and only one small
            PCM chunk is sent at a time.
          </p>
          <p>
            Processing shows stages and completed chunk counts, not guessed
            completion percentages. This is a measured fraction of chunks, not a
            prediction of time remaining. The REST response supplies plain text,
            so the app does not invent speech timestamps.
          </p>
          <p>
            The default application limits are 250 MiB and four hours; both are
            configurable. Splitting at fixed boundaries can cut words and reduce
            context. A future batch integration or silence-aware splitting could
            improve accuracy. Gnani also offers a batch API; this version
            deliberately uses the assignment’s linked REST contract.
          </p>
        </section>
        <section>
          <h2>Failure and recovery</h2>
          <div className="architecture-grid">
            <div>
              <h3>Durable work intent</h3>
              <p>
                A queued database row remains eligible for dispatch even if
                Redis is briefly unavailable. Publish happens before the
                dispatch timestamp commits. A crash can create a duplicate
                message, which the worker lock and state checks reject.
              </p>
            </div>
            <div>
              <h3>Bounded retries</h3>
              <p>
                Transient provider failures get up to three network attempts
                with bounded backoff. User-initiated processing retries are
                limited to three attempts by default. Corrupt audio and
                credential failures are shown without automatic retries.
              </p>
            </div>
            <div>
              <h3>Checkpoint and fence</h3>
              <p>
                Completed transcription chunks survive failures. A new attempt
                gets a new run token; each worker update must match it. Old
                workers cannot overwrite a newer attempt. A provider call can
                still be repeated if it succeeded just before the database write
                failed.
              </p>
            </div>
            <div>
              <h3>No endless spinner</h3>
              <p>
                A note with no heartbeat for 15 minutes is marked failed by the
                dispatcher or a read request. Hard worker limits bound
                execution. When connectivity fails, the browser displays the
                error and continues checking.
              </p>
            </div>
          </div>
        </section>
        <section>
          <h2>Summaries with a bounded input</h2>
          <p>
            A small provider interface has one implementation: an
            OpenAI-compatible Chat Completions client, configured by environment
            variables. It asks for a concise, faithful summary and treats the
            transcript as untrusted source material.
          </p>
          <p>
            Inputs are split at a conservative 12,000 UTF-8-byte budget. Each
            piece is summarized, then the partial summaries are reduced until a
            final pass fits. Output length and reduction passes are bounded; a
            non-shrinking result fails visibly. A prompt reduces hallucination
            risk but cannot guarantee accuracy. Check important details against
            the recording.
          </p>
        </section>
        <section>
          <h2>Security and deployment boundaries</h2>
          <p>
            This version is a shared review workspace without per-user
            authentication. Everyone with access can read its notes and create
            uploads. Put the deployment behind an access gateway for private
            recordings. UUIDs avoid sequential identifiers; they are not
            authorization.
          </p>
          <p>
            Audio stays in a private bucket; playback uses one-hour signed URLs.
            Secrets stay on the server. Filenames never become filesystem paths,
            file byte limits are checked while streaming, and media subprocesses
            cannot fetch network URLs. CORS uses configured origins. Logs omit
            provider bodies, secrets and transcript text.
          </p>
          <p>
            PostgreSQL migrations run as a deployment step. The included Compose
            setup starts the web app, API, worker, dispatcher, PostgreSQL,
            Redis, S3-compatible storage and an HTTP gateway. Production needs
            HTTPS, private infrastructure, backups, appropriate provider
            credentials and a real GitHub URL.
          </p>
        </section>
        <section>
          <h2>Trade-offs and next improvements</h2>
          <p>
            Polling is sufficient for a few coarse processing states and is
            easier to reconnect than a live socket. Offset pagination is
            intentionally simple for assignment-scale history. Keeping work
            intent on the note avoids a separate outbox table while preserving
            redispatch.
          </p>
          <p>
            For a public multi-user product, add account ownership and quotas
            first. At higher volume, use direct multipart uploads with
            short-lived upload authorizations, dedicated queue routing, cursor
            pagination, per-provider rate limits, object lifecycle cleanup, and
            job metrics. Exactly-once external billing needs a
            provider-supported idempotency mechanism; database locks alone
            cannot provide it.
          </p>
        </section>
      </article>
    </>
  );
}
