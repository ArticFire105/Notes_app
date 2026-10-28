/**
 * Reserve the My Notes route for a later implementation phase.
 * The shared placeholder keeps navigation complete without extra features.
 * This module belongs to the Phase 6 browser frontend.
 * Next.js App Router supplies navigation.
 * TypeScript makes request shapes explicit.
 * Tailwind supplies the styling utilities.
 * Shared controls follow shadcn/ui conventions.
 * Navy and cream identify the learning portal.
 * Gold accents highlight useful actions.
 * Small functions keep the flow readable.
 * Application requests go only to FastAPI.
 * The public API URL comes from the process environment.
 * Database operations remain on the backend.
 * Supabase authentication remains on the backend.
 * Backend permissions remain authoritative.
 * Tokens are held only in browser memory.
 * User API keys are held only in browser memory.
 * Refreshing the tab clears the current session.
 * Logging out clears private session data.
 * No credentials are written to disk.
 * No credentials are written to URLs.
 * No credentials are written to logs.
 * HTTP errors use safe user-facing messages.
 * Requests with credentials are never cached.
 * Question scope uses backend database IDs.
 * Sources remain attached to their answers.
 * Chat histories are separated by subject.
 * Daily allowance is supplied by the backend.
 * Uploads reuse the existing PDF endpoint.
 * Ingestion status is polled until completion.
 * Later-phase features remain placeholders.
 * Layout adapts to small mobile screens.
 * Live integrations require manual verification.
 */

"use client";

import { useEffect, useState } from "react";
import { ComingSoon } from "@/components/coming-soon";
import { api, errorMessage, processNote, type Subject, type PersonalNote } from "@/lib/api";
import { LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function Page() {
  return <ComingSoon title="My Notes" description="Personal notes will be available in a future update." />;
}

function PersonalNotes() {
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [notes, setNotes] = useState<PersonalNote[]>([]);
  const [subjectId, setSubjectId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [stage, setStage] = useState("");
  const [notice, setNotice] = useState("");
  async function load() {
    const [subjects, notes] = await Promise.all([api.subjects(), api.notes()]);
    setSubjects(subjects); setNotes(notes);

  }
  useEffect(() => { void load().catch(error => setError(errorMessage(error))); }, []);
  const existing = notes.find(note => note.subject_id === Number(subjectId));
  async function upload(event: React.FormEvent) {
    event.preventDefault();
    if (!file || !subjectId) return;
    setBusy(true); setError(""); setNotice("");
    const data = new FormData();
    data.set("subject_id", subjectId); data.set("file", file);
    data.set("replace", existing ? "true" : "false");
    try { const result = await processNote(data, setStage); await load(); setNotice(result?.failed_pages?.length ? `Your note is partly ready. Pages ${result.failed_pages.join(", ")} could not be read and are not searchable.` : "Your note is ready to search."); setFile(null); }
    catch (error) { const message = errorMessage(error); setStage(message.includes("may still") ? "Status unavailable" : "Failed"); setError(message); }
    finally { setBusy(false); }
  }
  async function remove() {
    if (!existing || !window.confirm("Delete your note for this subject?")) return;
    setBusy(true); setError(""); setNotice("");
    try { await api.deleteNote(Number(subjectId)); await load(); setNotice("Note deleted."); }
    catch (error) { setError(errorMessage(error)); }
    finally { setBusy(false); }
  }
  return <div className="mx-auto max-w-2xl space-y-6"><h1 className="font-heading text-3xl font-semibold">My notes</h1>
    <p className="text-sm text-muted-foreground">One private note per subject. Upload a scanned PDF, PNG or JPEG, up to 20 MB and 30 PDF pages. Your file is sent to Google Gemini for OCR.</p>
    {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-red-800">{error}</p>}
    {notice && <p role="status" className="rounded-lg bg-green-50 p-3">{notice}</p>}
    <form onSubmit={upload} className="space-y-4 rounded-xl border bg-white p-6"><label htmlFor="note-subject">Subject</label>
      <select id="note-subject" value={subjectId} required onChange={event => setSubjectId(event.target.value)} disabled={busy}><option value="" disabled>Choose a subject</option>{subjects.map(subject => <option key={subject.id} value={subject.id}>{subject.code} - {subject.name}</option>)}</select>
      {existing?.failed_pages?.length ? <p role="alert" className="rounded-lg bg-amber-50 p-3">Pages {existing.failed_pages.join(", ")} could not be read and are not searchable. Uploading a file replaces the whole note.</p> : null}
      {subjectId && <p className="font-semibold">Selected: {subjects.find(subject => String(subject.id) === subjectId)?.name} ({subjects.find(subject => String(subject.id) === subjectId)?.code})</p>}
      <p className="text-sm">{existing ? "You already have a note for this subject. Uploading will replace it." : "No note uploaded for this subject."}</p>
      <label htmlFor="note-file" className="block text-sm font-medium">Choose your file</label><input id="note-file" type="file" className="block w-full text-sm file:mr-3 file:rounded-lg file:border file:px-4 file:py-2 file:font-medium" accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg" onChange={event => setFile(event.target.files?.[0] || null)} disabled={busy} required />
      <div className="flex gap-3"><Button disabled={busy || !file || !subjectId} type="submit">{busy ? "Processing..." : existing ? "Replace note" : "Upload note"}</Button>{existing && <Button disabled={busy} type="button" variant="outline" onClick={() => void remove()}>Delete</Button>}</div>
    </form>{stage && <p role="status" className="flex items-center gap-2 text-sm">{busy && <LoaderCircle className="animate-spin" size={18} />}{stage}</p>}<p className="text-xs text-muted-foreground">OCR can make mistakes. Check your original note when accuracy matters. Your note is included when you ask about this subject.</p>
  </div>;
}
