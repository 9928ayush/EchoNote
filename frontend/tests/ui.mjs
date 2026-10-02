import assert from "node:assert/strict";
import { chromium } from "playwright";
// Contract fixtures are isolated to tests; the application has no demo data path.
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH,
  args: JSON.parse(process.env.PLAYWRIGHT_CHROMIUM_ARGS || "[]"),
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
let note = null;
let failList = false;
const origin = process.env.UI_TEST_ORIGIN || "http://localhost:3000";
await page.route("**/api/**", async (route) => {
  const request = route.request();
  const path = new URL(request.url()).pathname;
  const fulfill = (data, status = 200) =>
    route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(data),
    });
  if (path === "/api/config")
    return fulfill({
      max_upload_bytes: 262144000,
      max_duration_seconds: 14400,
      max_attempts: 3,
      repository_url: "https://github.com/openai/openai-python",
    });
  if (path.endsWith("/playback"))
    return fulfill(
      { error: { message: "Playback unavailable in this isolated test." } },
      503,
    );
  if (path.endsWith("/content")) {
    note.status = "QUEUED";
    note.attempts = 1;
    return fulfill(note);
  }
  if (path.endsWith("/retry")) {
    note.status = "QUEUED";
    note.error_message = null;
    return fulfill(note);
  }
  if (path.endsWith("/status")) return fulfill(note);
  if (path === "/api/audio-notes" && request.method() === "POST") {
    const body = request.postDataJSON();
    note = {
      id: "161cf706-03ea-4b11-b0f7-8bb40fa44674",
      original_filename: body.filename,
      file_size: body.file_size,
      language: body.language,
      mime_type: "audio/wav",
      status: "UPLOADING",
      created_at: "2026-10-02T09:00:00Z",
      updated_at: "2026-10-02T09:00:00Z",
      duration: null,
      error_message: null,
      retryable: false,
      attempts: 0,
      total_chunks: 0,
      completed_chunks: 0,
      transcript: null,
      summary: null,
      processing_started_at: null,
      completed_at: null,
    };
    return fulfill(note, 201);
  }
  if (path === "/api/audio-notes")
    return failList
      ? fulfill({ error: { message: "Service temporarily unavailable." } }, 503)
      : fulfill({
          items: note ? [note] : [],
          total: note ? 1 : 0,
          page: 1,
          page_size: 20,
        });
  return fulfill(note);
});
try {
  await page.goto(origin);
  await page
    .getByRole("heading", { name: "Your first note starts here" })
    .waitFor();
  await page.screenshot({ path: "/tmp/echonote-desktop.png", fullPage: true });
  await page
    .getByRole("link", { name: "Upload a recording", exact: true })
    .click();
  await page
    .locator('input[type="file"]')
    .setInputFiles({
      name: "bad.exe",
      mimeType: "application/octet-stream",
      buffer: Buffer.from("x"),
    });
  await page.locator(".error-box").waitFor();
  await page
    .locator('input[type="file"]')
    .setInputFiles({
      name: "Project review.wav",
      mimeType: "audio/wav",
      buffer: Buffer.from("test-audio"),
    });
  await page.getByRole("button", { name: "Create audio note" }).click();
  await page.waitForURL("**/notes/**");
  await page
    .getByRole("heading", { name: "Putting your note together" })
    .waitFor();
  note = {
    ...note,
    status: "COMPLETED",
    total_chunks: 5,
    completed_chunks: 5,
    duration: 125,
    summary: "The team agreed to review the launch plan on Friday.",
    transcript:
      "We will review the launch plan on Friday.\n\nAman will collect the feedback.",
  };
  await page
    .getByText(note.summary, { exact: true })
    .waitFor({ timeout: 10000 });
  await page.getByRole("searchbox").fill("Aman");
  await page.getByText("1 matching passages").waitFor();
  assert.equal(
    await page
      .getByText("We will review the launch plan on Friday.", { exact: true })
      .count(),
    0,
  );
  await page.getByRole("searchbox").fill("");
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"], { origin });
  await page.getByRole("button", { name: "Copy transcript" }).click();
  await page.getByText("Copied", { exact: true }).waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  assert.ok(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  );
  await page.screenshot({ path: "/tmp/echonote-mobile.png", fullPage: true });
  note = {
    ...note,
    status: "FAILED",
    retryable: true,
    attempts: 1,
    summary: null,
    error_message: "Transcription timed out. You can retry.",
  };
  await page.reload();
  await page.getByRole("button", { name: "Retry processing" }).click();
  await page
    .getByRole("heading", { name: "Putting your note together" })
    .waitFor();
  await page.getByRole("link", { name: "Architecture", exact: true }).click();
  await page
    .getByRole("heading", { name: "A recording, end to end." })
    .waitFor();
  assert.ok(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  );
  failList = true;
  await page.getByRole("link", { name: "Audio notes", exact: true }).click();
  await page.locator(".error-box").waitFor();
  assert.deepEqual(errors, []);
  console.log(
    "UI checks passed: empty, upload validation, upload redirect, polling, summary, search, copy, retry, architecture, error, mobile overflow.",
  );
} finally {
  await browser.close();
}
