"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  api,
  date,
  duration,
  fileSize,
  isActive,
  type Config,
  type Note,
  type NoteStatus,
} from "@/lib/api";
import { Badge, CopyButton, ErrorBox, Skeleton } from "./common";
const stages = [
  "UPLOADING",
  "QUEUED",
  "TRANSCRIBING",
  "SUMMARIZING",
  "COMPLETED",
];
const stageNames = [
  "Uploaded",
  "Queued",
  "Transcribing",
  "Summarizing",
  "Ready",
];
export function NoteView({ id }: { id: string }) {
  const [note, setNote] = useState<Note | null>(null);
  const [config, setConfig] = useState<Config | null>(null);
  const [error, setError] = useState("");
  const [audioError, setAudioError] = useState("");
  const [audioUrl, setAudioUrl] = useState("");
  const [refreshAudio, setRefreshAudio] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [retrying, setRetrying] = useState(false);
  const [query, setQuery] = useState("");
  const player = useRef<HTMLAudioElement>(null);
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    let current: Note | null = null;
    setError("");
    async function load() {
      try {
        if (!current) {
          const [n, c] = await Promise.all([
            api<Note>(`/api/audio-notes/${id}`),
            api<Config>("/api/config"),
          ]);
          current = n;
          if (alive) setConfig(c);
        } else {
          const status = await api<NoteStatus>(`/api/audio-notes/${id}/status`);
          current = { ...current, ...status };
          if (!isActive(status.status))
            current = await api<Note>(`/api/audio-notes/${id}`);
        }
        if (alive) {
          setNote(current);
          setError("");
        }
      } catch (e) {
        if (alive) setError((e as Error).message);
      }
      if (alive && (!current || isActive(current.status)))
        timer = setTimeout(load, 3000);
    }
    void load();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [id, refresh]);
  const hasUpload = !!note && note.attempts > 0;
  useEffect(() => {
    if (!hasUpload) return;
    let alive = true;
    api<{ url: string }>(`/api/audio-notes/${id}/playback`)
      .then((data) => {
        if (alive) {
          setAudioUrl(data.url);
          setAudioError("");
        }
      })
      .catch((e) => {
        if (alive) setAudioError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [id, hasUpload, refreshAudio]);
  async function retry() {
    setRetrying(true);
    setError("");
    try {
      const result = await api<Note>(`/api/audio-notes/${id}/retry`, {
        method: "POST",
      });
      setNote(result);
      setRefresh((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRetrying(false);
    }
  }
  const paragraphs = (note?.transcript || "")
    .split("\n\n")
    .filter((p) => p.trim());
  const filtered = paragraphs.filter((p) =>
    p.toLocaleLowerCase().includes(query.toLocaleLowerCase()),
  );
  const stageIndex = note ? stages.indexOf(note.status) : -1;
  return (
    <>
      <div className="topbar">
        <Link href="/">Audio notes</Link>
        <span>/ Recording</span>
      </div>
      <div className="page-content">
        {error && (
          <ErrorBox message={error} onRetry={() => setRefresh((v) => v + 1)} />
        )}
        {!note && !error && <Skeleton />}
        {note && (
          <>
            <header className="page-heading note-heading">
              <div>
                <div className="eyebrow">AUDIO NOTE</div>
                <h1>{note.original_filename}</h1>
                <p>
                  {date(note.created_at)} <span aria-hidden="true">·</span>{" "}
                  {fileSize(note.file_size)} <span aria-hidden="true">·</span>{" "}
                  {duration(note.duration)}
                </p>
              </div>
              <Badge status={note.status} />
            </header>
            {hasUpload && (
              <section className="audio-panel" aria-label="Recording playback">
                <div className="audio-label">
                  <span className="file-icon" aria-hidden="true">
                    ▥
                  </span>
                  <div>
                    <strong>Original recording</strong>
                    <small>{note.language}</small>
                  </div>
                </div>
                {audioUrl && (
                  <audio
                    ref={player}
                    controls
                    preload="metadata"
                    src={audioUrl}
                    onError={() =>
                      setAudioError(
                        "Playback failed or the temporary link expired. Reload the audio link.",
                      )
                    }
                  />
                )}
                {audioError && (
                  <div className="audio-error" role="alert">
                    {audioError}
                    <button
                      className="button secondary"
                      onClick={() => setRefreshAudio((v) => v + 1)}
                    >
                      Reload audio
                    </button>
                  </div>
                )}
              </section>
            )}
            {isActive(note.status) && (
              <section className="processing-panel" aria-live="polite">
                <div className="section-bar">
                  <h2>Putting your note together</h2>
                  <span className="muted">
                    You can return after upload finishes.
                  </span>
                </div>
                <ol className="timeline">
                  {stageNames.map((name, index) => (
                    <li
                      key={name}
                      className={
                        index < stageIndex
                          ? "done"
                          : index === stageIndex
                            ? "current"
                            : ""
                      }
                    >
                      <span>{index < stageIndex ? "✓" : index + 1}</span>
                      {name}
                    </li>
                  ))}
                </ol>
                <p>
                  {note.status === "UPLOADING"
                    ? "Waiting for the file upload to finish. An interrupted upload will be marked as failed."
                    : note.status === "TRANSCRIBING" && note.total_chunks
                      ? `${note.completed_chunks} of ${note.total_chunks} audio chunks transcribed.`
                      : note.status === "SUMMARIZING"
                        ? "The transcript is ready. Generating a faithful summary…"
                        : "Your recording is waiting for a worker."}
                </p>
                <p className="small muted">
                  Progress refreshes automatically. No need to keep this page
                  open after upload.
                </p>
              </section>
            )}
            {note.status === "FAILED" && (
              <section className="failure-panel">
                <ErrorBox
                  message={note.error_message || "Processing failed."}
                />
                <div className="failure-actions">
                  {note.retryable &&
                  note.attempts > 0 &&
                  config &&
                  note.attempts < config.max_attempts ? (
                    <button
                      className="button primary"
                      disabled={retrying}
                      onClick={retry}
                    >
                      {retrying ? "Queuing…" : "Retry processing"}
                    </button>
                  ) : (
                    <Link className="button primary" href="/upload">
                      Upload a new recording
                    </Link>
                  )}
                  <span className="muted">
                    {note.attempts
                      ? `Processing attempt ${note.attempts}${config ? ` of ${config.max_attempts}` : ""}. Completed transcription chunks are retained.`
                      : "The file was not fully uploaded."}
                  </span>
                </div>
              </section>
            )}
            <div className="reading-grid">
              <section className="summary-panel">
                <div className="section-bar">
                  <div>
                    <div className="eyebrow">THE IMPORTANT PARTS</div>
                    <h2>Summary</h2>
                  </div>
                  {note.summary && (
                    <CopyButton text={note.summary} label="summary" />
                  )}
                </div>
                {note.summary ? (
                  <div className="prose-text">{note.summary}</div>
                ) : (
                  <p className="muted">
                    {note.status === "FAILED"
                      ? "A summary is not available for this attempt."
                      : "Your summary will appear here when processing finishes."}
                  </p>
                )}
              </section>
              <section className="transcript-panel">
                <div className="section-bar">
                  <div>
                    <div className="eyebrow">IN FULL</div>
                    <h2>Transcript</h2>
                  </div>
                  {note.transcript && (
                    <CopyButton text={note.transcript} label="transcript" />
                  )}
                </div>
                {note.transcript ? (
                  <>
                    <label className="sr-only" htmlFor="search">
                      Search transcript
                    </label>
                    <input
                      id="search"
                      className="search-input"
                      type="search"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      placeholder="Search transcript…"
                    />
                    {query && (
                      <p className="small muted" role="status">
                        {filtered.length} matching passages
                      </p>
                    )}
                    <div className="transcript-text">
                      {filtered.map((p, i) => (
                        <p key={i}>{p}</p>
                      ))}
                      {!filtered.length && (
                        <p className="muted">No passages match your search.</p>
                      )}
                    </div>
                    {isActive(note.status) && (
                      <p className="small muted">
                        This transcript may be partial while processing
                        continues.
                      </p>
                    )}
                  </>
                ) : (
                  <p className="muted">
                    {note.status === "FAILED"
                      ? "No transcript was saved."
                      : "Transcribed speech will appear here."}
                  </p>
                )}
              </section>
            </div>
          </>
        )}
      </div>
    </>
  );
}
