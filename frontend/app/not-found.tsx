import Link from "next/link";
export default function NotFound() {
  return (
    <div className="page-content">
      <h1>Page not found</h1>
      <Link className="button primary" href="/">
        Back to audio notes
      </Link>
    </div>
  );
}
