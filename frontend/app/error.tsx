"use client";
export default function Error({ reset }: { reset: () => void }) {
  return (
    <div className="page-content">
      <h1>This page could not load</h1>
      <p>Please try again.</p>
      <button className="button primary" onClick={reset}>
        Reload page
      </button>
    </div>
  );
}
