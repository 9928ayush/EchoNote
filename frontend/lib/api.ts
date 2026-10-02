export type Status =
  | "UPLOADING"
  | "QUEUED"
  | "TRANSCRIBING"
  | "SUMMARIZING"
  | "COMPLETED"
  | "FAILED";
export type NoteStatus = {
  id: string;
  status: Status;
  error_message: string | null;
  retryable: boolean;
  attempts: number;
  completed_chunks: number;
  total_chunks: number;
  updated_at: string;
};
export type NoteSummary = NoteStatus & {
  original_filename: string;
  mime_type: string;
  file_size: number;
  language: string;
  duration: number | null;
  created_at: string;
};
export type Note = NoteSummary & {
  transcript: string | null;
  summary: string | null;
  processing_started_at: string | null;
  completed_at: string | null;
};
export type Config = {
  max_upload_bytes: number;
  max_duration_seconds: number;
  max_attempts: number;
  repository_url: string;
};
export type NoteList = {
  items: NoteSummary[];
  total: number;
  page: number;
  page_size: number;
};
export const API = (process.env.NEXT_PUBLIC_API_BASE_URL || "").replace(
  /\/$/,
  "",
);

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(`${API}${path}`, {
      ...init,
      cache: "no-store",
      signal: controller.signal,
    });
    const data = await response.json().catch(() => null);
    if (!response.ok)
      throw new Error(
        data?.error?.message || "The service is unavailable. Please try again.",
      );
    if (!data) throw new Error("The service returned an unreadable response.");
    return data as T;
  } catch (error) {
    if (
      error instanceof TypeError ||
      (error instanceof DOMException && error.name === "AbortError")
    ) {
      throw new Error(
        "Cannot reach the service. Check your connection and try again.",
      );
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}
export const isActive = (status: Status) =>
  !["COMPLETED", "FAILED"].includes(status);
export const labels: Record<Status, string> = {
  UPLOADING: "Uploading",
  QUEUED: "Queued",
  TRANSCRIBING: "Transcribing",
  SUMMARIZING: "Summarizing",
  COMPLETED: "Ready",
  FAILED: "Needs attention",
};
export const fileSize = (bytes: number) =>
  bytes < 1048576
    ? `${(bytes / 1024).toFixed(0)} KB`
    : `${(bytes / 1048576).toFixed(1)} MB`;
export const duration = (seconds: number | null) =>
  seconds === null
    ? "Duration pending"
    : `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
export const date = (iso: string) =>
  new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
