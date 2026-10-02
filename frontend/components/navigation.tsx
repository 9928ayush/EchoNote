"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
export function Navigation() {
  const path = usePathname();
  return (
    <aside className="sidebar">
      <Link href="/" className="brand" aria-label="EchoNote home">
        <span className="brand-icon" aria-hidden="true">
          ▥
        </span>
        EchoNote
      </Link>
      <div className="workspace-label">AUDIO WORKSPACE</div>
      <nav aria-label="Main navigation">
        <Link
          aria-current={
            path === "/" || path.startsWith("/notes/") ? "page" : undefined
          }
          href="/"
        >
          <span aria-hidden="true">▤</span> Audio notes
        </Link>
        <Link
          aria-current={path === "/upload" ? "page" : undefined}
          href="/upload"
        >
          <span aria-hidden="true">+</span> New audio note
        </Link>
        <Link
          aria-current={path === "/architecture" ? "page" : undefined}
          href="/architecture"
        >
          <span aria-hidden="true">⌘</span> Architecture
        </Link>
      </nav>
      <div className="sidebar-footer">
        <strong>From recording to reference.</strong>
        <p>A shared workspace for transcripts and summaries.</p>
      </div>
    </aside>
  );
}
