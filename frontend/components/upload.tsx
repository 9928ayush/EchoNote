"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { API, api, fileSize, type Config, type Note } from "@/lib/api";
import { ErrorBox } from "./common";
const languages = {
  "en-IN": "English",
  "hi-IN": "Hindi",
  "gu-IN": "Gujarati",
  "bn-IN": "Bengali",
  "kn-IN": "Kannada",
  "ml-IN": "Malayalam",
  "mr-IN": "Marathi",
  "pa-IN": "Punjabi",
  "ta-IN": "Tamil",
  "te-IN": "Telugu",
};
export function Upload() {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const xhr = useRef<XMLHttpRequest | null>(null);
  const inFlight = useRef(false);
  const [file, setFile] = useState<File | null>(null);
  const [language, setLanguage] = useState("en-IN");
  const [config, setConfig] = useState<Config | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let alive = true;
    api<Config>("/api/config")
      .then((c) => {
        if (alive) {
          setConfig(c);
          setError("");
        }
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [refresh]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (inFlight.current) event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => {
      window.removeEventListener("beforeunload", warn);
      xhr.current?.abort();
    };
  }, []);
  function choose(selected: File | undefined) {
    if (busy || !selected) return;
    setError("");
    if (!/\.(wav|mp3|ogg|flac|aac|m4a)$/i.test(selected.name)) {
      setError("Choose a WAV, MP3, OGG, FLAC, AAC or M4A recording.");
      return;
    }
    if (!selected.size) {
      setError("This file is empty. Choose a recording with audio.");
      return;
    }
    if (config && selected.size > config.max_upload_bytes) {
      setError(
        `Choose a recording smaller than ${fileSize(config.max_upload_bytes)}.`,
      );
      return;
    }
    setFile(selected);
    setProgress(0);
  }
  async function submit() {
    if (!file || !config || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    setProgress(0);
    try {
      const note = await api<Note>("/api/audio-notes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: file.name,
          file_size: file.size,
          language,
          upload_key: crypto.randomUUID(),
        }),
      });
      await new Promise<void>((resolve, reject) => {
        const request = new XMLHttpRequest();
        xhr.current = request;
        request.open("PUT", `${API}/api/audio-notes/${note.id}/content`);
        request.setRequestHeader("Content-Type", "application/octet-stream");
        request.timeout = 1800000;
        request.upload.onprogress = (event) => {
          if (event.lengthComputable)
            setProgress(Math.round((event.loaded / event.total) * 100));
        };
        request.onload = () => {
          if (request.status >= 200 && request.status < 300) resolve();
          else {
            let message = "Upload failed. Please try again.";
            try {
              message =
                JSON.parse(request.responseText).error?.message || message;
            } catch {}
            reject(new Error(message));
          }
        };
        request.onerror = () =>
          reject(new Error("Connection lost during upload. Please try again."));
        request.ontimeout = () =>
          reject(
            new Error(
              "Upload timed out. Please try again on a stable connection.",
            ),
          );
        request.onabort = () =>
          reject(
            new Error("Upload cancelled. You can start again when ready."),
          );
        request.send(file);
      });
      inFlight.current = false;
      router.push(`/notes/${note.id}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      inFlight.current = false;
      setBusy(false);
      xhr.current = null;
    }
  }
  return (
    <>
      <div className="topbar">
        <Link href="/">Audio notes</Link>
        <span>/ New recording</span>
      </div>
      <div className="page-content narrow">
        <header className="page-heading">
          <div>
            <div className="eyebrow">ADD TO YOUR WORKSPACE</div>
            <h1>New audio note</h1>
            <p>Upload once. Come back to the important parts.</p>
          </div>
        </header>
        {error && (
          <ErrorBox
            message={error}
            onRetry={!config ? () => setRefresh((v) => v + 1) : undefined}
          />
        )}
        <div className="upload-panel">
          <input
            ref={input}
            type="file"
            className="sr-only"
            tabIndex={-1}
            accept=".wav,.mp3,.ogg,.flac,.aac,.m4a"
            onChange={(e) => choose(e.target.files?.[0])}
            disabled={busy}
            aria-label="Select audio recording"
          />
          <button
            type="button"
            disabled={busy || !config}
            className={`dropzone ${dragging ? "dragging" : ""}`}
            onClick={() => input.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              if (e.dataTransfer.files.length > 1)
                setError("Upload one recording at a time.");
              else choose(e.dataTransfer.files[0]);
            }}
          >
            <span className="upload-icon" aria-hidden="true">
              +
            </span>
            <strong>
              {file
                ? "Choose a different recording"
                : "Drop your recording here"}
            </strong>
            <span>or click to browse files</span>
            <small>
              {config
                ? `Up to ${fileSize(config.max_upload_bytes)} · ${config.max_duration_seconds / 60} minutes`
                : "Checking upload availability…"}
            </small>
          </button>
          {file && (
            <div className="selected-file">
              <span className="file-icon" aria-hidden="true">
                ▥
              </span>
              <div>
                <strong>{file.name}</strong>
                <small>
                  {fileSize(file.size)} ·{" "}
                  {file.name.split(".").pop()?.toUpperCase()} audio
                </small>
              </div>
              <button
                className="button secondary"
                disabled={busy}
                onClick={() => {
                  setFile(null);
                  if (input.current) input.current.value = "";
                }}
              >
                Remove
              </button>
            </div>
          )}
          <div className="form-field">
            <label htmlFor="language">Recording language</label>
            <select
              id="language"
              value={language}
              disabled={busy}
              onChange={(e) => setLanguage(e.target.value)}
            >
              {Object.entries(languages).map(([code, label]) => (
                <option key={code} value={code}>
                  {label}
                </option>
              ))}
            </select>
            <p>Choose the main spoken language for transcription.</p>
          </div>
          {busy && (
            <div className="upload-progress" role="status">
              <div>
                <strong>
                  {progress < 100
                    ? `Uploading · ${progress}%`
                    : "Saving recording…"}
                </strong>
                <span>Keep this page open until the upload finishes.</span>
              </div>
              <progress
                value={progress}
                max={100}
                aria-label="Upload progress"
              />
            </div>
          )}
          <div className="upload-actions">
            <span className="muted">WAV · MP3 · OGG · FLAC · AAC · M4A</span>
            {busy ? (
              <button
                className="button secondary"
                onClick={() => xhr.current?.abort()}
                disabled={!xhr.current}
              >
                Cancel upload
              </button>
            ) : (
              <button
                className="button primary"
                disabled={!file || !config}
                onClick={submit}
              >
                Create audio note
              </button>
            )}
          </div>
        </div>
        <p className="privacy-note">
          This is a shared workspace. Recordings are sent to Gnani for
          transcription; transcript text is sent to the configured summary
          provider.
        </p>
      </div>
    </>
  );
}
