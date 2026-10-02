import { NoteView } from "@/components/note-view";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <NoteView id={id} />;
}
