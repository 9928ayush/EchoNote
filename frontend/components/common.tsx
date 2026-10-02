"use client";
import { useState } from "react";
import { labels, type Status } from "@/lib/api";
export function Badge({ status }: { status: Status }) {
  return (
    <span className={`badge ${status.toLowerCase()}`}>
      <span aria-hidden="true" />
      {labels[status]}
    </span>
  );
}
export function ErrorBox({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="error-box" role="alert">
      <div>
        <strong>Something needs attention</strong>
        <p>{message}</p>
      </div>
      {onRetry && (
        <button className="button secondary" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}
export function Skeleton() {
  return (
    <div
      className="skeleton-list"
      aria-label="Loading audio notes"
      role="status"
    >
      {[1, 2, 3].map((i) => (
        <div key={i} className="skeleton" />
      ))}
      <span className="sr-only">Loading…</span>
    </div>
  );
}
export function CopyButton({ text, label }: { text: string; label: string }) {
  const [message, setMessage] = useState("");
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setMessage("Copied");
    } catch {
      setMessage("Copy unavailable. Select the text and copy it manually.");
    }
  }
  return (
    <div className="copy-control">
      <button
        onClick={copy}
        className="button secondary"
        aria-label={`Copy ${label}`}
      >
        Copy {label}
      </button>
      <span role="status">{message}</span>
    </div>
  );
}
