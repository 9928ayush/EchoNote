"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, date, duration, fileSize, type NoteList } from "@/lib/api";
import { Badge, ErrorBox, Skeleton } from "./common";
export function Dashboard() {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<NoteList | null>(null);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const reload = useCallback(() => setRefresh((v) => v + 1), []);
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    setData(null);
    async function load() {
      try {
        const result = await api<NoteList>(`/api/audio-notes?page=${page}`);
        if (!disposed) {
          setData(result);
          setError("");
        }
      } catch (e) {
        if (!disposed) setError((e as Error).message);
      }
      if (!disposed) timer = setTimeout(load, 8000);
    }
    void load();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [page, refresh]);
  return (
    <>
      <div className="topbar">
        <span>Workspace / Audio notes</span>
        <span className="muted">Shared workspace</span>
      </div>
      <div className="page-content">
        <header className="page-heading">
          <div>
            <div className="eyebrow">YOUR RECORDINGS, ORGANIZED</div>
            <h1>Audio notes</h1>
            <p>Pick up where the recording left off.</p>
          </div>
          <Link className="button primary" href="/upload">
            <span aria-hidden="true">+</span> New audio note
          </Link>
        </header>
        {error && <ErrorBox message={error} onRetry={reload} />}
        {!data && !error && <Skeleton />}
        {data && (
          <section className="notes-panel" aria-label="Audio note history">
            <div className="section-bar">
              <h2>
                All recordings <span className="count">{data.total}</span>
              </h2>
              <span className="muted">Newest first</span>
            </div>
            {data.items.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon" aria-hidden="true">
                  ▥
                </div>
                <h2>Your first note starts here</h2>
                <p>
                  Upload a recording to keep its transcript and summary
                  together. Meetings, lectures, or a thought worth keeping.
                </p>
                <Link className="button primary" href="/upload">
                  Upload a recording
                </Link>
                <p className="small">WAV, MP3, OGG, FLAC, AAC or M4A</p>
              </div>
            ) : (
              <>
                <div className="table-head">
                  <span>Recording</span>
                  <span>Duration</span>
                  <span>Added</span>
                  <span>Status</span>
                </div>
                <ul className="note-list">
                  {data.items.map((note) => (
                    <li key={note.id}>
                      <Link href={`/notes/${note.id}`} className="note-row">
                        <div className="recording-cell">
                          <span className="file-icon" aria-hidden="true">
                            ▥
                          </span>
                          <div>
                            <strong>{note.original_filename}</strong>
                            <small>
                              {fileSize(note.file_size)} · {note.language}
                            </small>
                          </div>
                        </div>
                        <span className="duration-cell">
                          {duration(note.duration)}
                        </span>
                        <time dateTime={note.created_at}>
                          {date(note.created_at)}
                        </time>
                        <Badge status={note.status} />
                      </Link>
                    </li>
                  ))}
                </ul>
                <div className="pagination">
                  <span>
                    Page {page} of{" "}
                    {Math.max(1, Math.ceil(data.total / data.page_size))}
                  </span>
                  <div>
                    <button
                      className="button secondary"
                      disabled={page <= 1}
                      onClick={() => setPage((p) => p - 1)}
                    >
                      Previous
                    </button>
                    <button
                      className="button secondary"
                      disabled={page * data.page_size >= data.total}
                      onClick={() => setPage((p) => p + 1)}
                    >
                      Next
                    </button>
                  </div>
                </div>
              </>
            )}
          </section>
        )}
      </div>
    </>
  );
}
