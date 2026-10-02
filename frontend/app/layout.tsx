import type { Metadata } from "next";
import { Navigation } from "@/components/navigation";
import "./globals.css";
export const metadata: Metadata = {
  title: { default: "EchoNote · Audio notes", template: "%s · EchoNote" },
  description:
    "Your recordings, transcribed and summarized in one calm workspace.",
  icons: { icon: "/favicon.svg" },
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main">
          Skip to content
        </a>
        <div className="app">
          <Navigation />
          <main id="main">{children}</main>
        </div>
      </body>
    </html>
  );
}
