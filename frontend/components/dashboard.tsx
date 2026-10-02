"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  date,
  duration,
  fileSize,
  type NoteList,
  type NoteSummary,
} from "@/lib/api";
import { Badge, ErrorBox, Skeleton } from "./common";

export function Dashboard() {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<NoteList | null>(null);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState("");

  const deleteInProgress = useRef(false);
  const deletedIds = useRef(new Set<string>());

  const reload = useCallback(() => setRefresh((value) => value + 1), []);

  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    setData(null);
    setError("");

    async function load() {
      try {
        const result = await api<NoteList>(
          `/api/audio-notes?page=${page}`,
        );

        if (!disposed) {
          // Ignore records from a response started before deletion.
          const items = result.items.filter(
            (note) => !deletedIds.current.has(note.id),
          );
          const removedCount = result.items.length - items.length;
          const total = Math.max(0, result.total - removedCount);
          const lastPage = Math.max(
            1,
            Math.ceil(total / result.page_size),
          );

          if (page > lastPage) {
            setPage(lastPage);
            return;
          }

          setData({ ...result, items, total });
          setError("");
        }
      } catch (error) {
        if (!disposed) {
          setError(
            error instanceof Error
              ? error.message
              : "Could not load recordings.",
          );
        }
      }

      if (!disposed) {
        timer = setTimeout(load, 8000);
      }
    }

    void load();

    return () => {
      disposed = true;
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [page, refresh]);

  async function deleteRecording(note: NoteSummary) {
    if (deleteInProgress.current) return;

    const confirmed = window.confirm(
      `Delete "${note.original_filename}"?\n\n` +
        "This permanently removes its audio, transcript, and summary.",
    );

    if (!confirmed) return;

    deleteInProgress.current = true;
    setDeletingId(note.id);
    setDeleteError("");

    try {
      await api<{ deleted: boolean; id: string }>(
        `/api/audio-notes/${note.id}`,
        { method: "DELETE" },
      );

      deletedIds.current.add(note.id);

      setData((current) => {
        if (!current) return current;

        const exists = current.items.some(
          (item) => item.id === note.id,
        );

        return {
          ...current,
          items: current.items.filter((item) => item.id !== note.id),
          total: Math.max(0, current.total - (exists ? 1 : 0)),
        };
      });

      reload();
    } catch (error) {
      setDeleteError(
        error instanceof Error
          ? error.message
          : "Could not delete the recording. Please retry.",
      );
    } finally {
      deleteInProgress.current = false;
      setDeletingId(null);
    }
  }

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

        {deleteError && (
          <div role="alert">
            <ErrorBox message={deleteError} />
          </div>
        )}

        {!data && !error && <Skeleton />}

        {data && (
          <section
            className="notes-panel"
            aria-label="Audio note history"
          >
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
                <p className="small">
                  WAV, MP3, OGG, FLAC, AAC or M4A
                </p>
              </div>
            ) : (
              <>
                <div
                  className="table-head"
                  style={{ paddingRight: "120px" }}
                >
                  <span>Recording</span>
                  <span>Duration</span>
                  <span>Added</span>
                  <span>Status</span>
                </div>

                <ul className="note-list">
                  {data.items.map((note) => (
                    <li
                      key={note.id}
                      style={{
                        display: "flex",
                        alignItems: "center",
                      }}
                    >
                      <Link
                        href={`/notes/${note.id}`}
                        className="note-row"
                        style={{ flex: 1, minWidth: 0 }}
                      >
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

                      <div
                        style={{
                          width: "120px",
                          flexShrink: 0,
                          display: "flex",
                          justifyContent: "center",
                        }}
                      >
                        <button
                          type="button"
                          className="button secondary"
                          disabled={deletingId !== null}
                          aria-label={`Delete ${note.original_filename}`}
                          onClick={() => void deleteRecording(note)}
                          style={{ color: "#b42318" }}
                        >
                          {deletingId === note.id
                            ? "Deleting…"
                            : "Delete"}
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>

                <div className="pagination">
                  <span>
                    Page {page} of{" "}
                    {Math.max(
                      1,
                      Math.ceil(data.total / data.page_size),
                    )}
                  </span>

                  <div>
                    <button
                      type="button"
                      className="button secondary"
                      disabled={page <= 1 || deletingId !== null}
                      onClick={() => setPage((current) => current - 1)}
                    >
                      Previous
                    </button>

                    <button
                      type="button"
                      className="button secondary"
                      disabled={
                        page * data.page_size >= data.total ||
                        deletingId !== null
                      }
                      onClick={() => setPage((current) => current + 1)}
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