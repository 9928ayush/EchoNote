"use client";
import { useEffect, useState } from "react";
import { api, type Config } from "@/lib/api";
export function RepositoryLink() {
  const [url, setUrl] = useState("");
  useEffect(() => {
    api<Config>("/api/config")
      .then((c) => {
        try {
          const u = new URL(c.repository_url);
          if (u.protocol === "https:" && u.hostname === "github.com")
            setUrl(u.href);
        } catch {}
      })
      .catch(() => {});
  }, []);
  return url ? (
    <a href={url} target="_blank" rel="noreferrer">
      View the source on GitHub
    </a>
  ) : (
    <p className="small muted">
      The workspace owner has not configured a GitHub repository link.
    </p>
  );
}
