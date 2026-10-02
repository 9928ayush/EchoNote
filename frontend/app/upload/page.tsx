import type { Metadata } from "next";
import { Upload } from "@/components/upload";
export const metadata: Metadata = { title: "New audio note" };
export default function Page() {
  return <Upload />;
}
