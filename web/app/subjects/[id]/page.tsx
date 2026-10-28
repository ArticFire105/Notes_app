/**
 * Browse module PDFs and ask questions in one of three scopes.
 * Answers, numbered sources, and per-subject history share one workspace.
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

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowUpRight, BookOpen, FileText, Send, Sparkles, Layers, ChevronDown } from "lucide-react";
import { api, errorMessage, processNote, type PersonalNote, type Subject, type Module, type Document, type Usage, type Source } from "@/lib/api";
import { useSession } from "@/components/session-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Worksheets, WorksheetChat } from "@/components/worksheets";
import { cn } from "@/lib/utils";

type Scope = "module" | "document" | "subject" | "worksheet";

function Figure({ id }: { id: string }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    let active = true;
    let objectUrl = "";
    api.figure(id).then(blob => {
      if (active) { objectUrl = URL.createObjectURL(blob); setUrl(objectUrl); }
    }).catch(() => {});
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [id]);
  return url ? <img src={url} alt="Diagram from the cited notes" className="mt-2 max-h-80 max-w-full rounded-lg border" /> : null;
}

// Keep the implementation in place while personal notes are postponed.
function personalNotesAvailable(): boolean { return false; }

export default function SubjectPage() {
  const { id } = useParams<{ id: string }>();
  const subjectId = Number(id);
  const { histories, appendChat, clearChat, savedKey } = useSession();
  const [subject, setSubject] = useState<Subject | null>(null);
  const [modules, setModules] = useState<Module[]>([]);
  const [documents, setDocuments] = useState<Record<number, Document[]>>({});
  const [moduleId, setModuleId] = useState<number | null>(null);
  const [documentId, setDocumentId] = useState("");
  const [mode, setMode] = useState<"normal" | "strict">("normal");
  const [scope, setScope] = useState<Scope>("module");
  const [worksheetId, setWorksheetId] = useState("");
  const [answerMethod, setAnswerMethod] = useState("one");
  const [usage, setUsage] = useState<Usage | null>(null);
  const [personalNote, setPersonalNote] = useState<PersonalNote | null>(null);
  const [noteFile, setNoteFile] = useState<File | null>(null);
  const [noteStage, setNoteStage] = useState("");
  const [noteBusy, setNoteBusy] = useState(false);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [viewer, setViewer] = useState<{ document: Document; page: number; url: string; downloadUrl?: string } | null>(null);
  const [zoom, setZoom] = useState(100);
  const [openingFile, setOpeningFile] = useState("");
  const bottom = useRef<HTMLDivElement>(null);
  const messages = histories[subjectId] || [];

  useEffect(() => {
    let active = true;
    async function load() {
      if (!Number.isInteger(subjectId) || subjectId <= 0) {
        setError("Choose a valid subject from Home."); setLoading(false); return;
      }
      try {
        const [overview, notes] = await Promise.all([api.overview(subjectId), api.notes().catch(() => null)]);
        if (!active) return;
        setSubject(overview.subject);
        setPersonalNote(notes?.find(note => note.subject_id === subjectId) || null);
        if (!notes) setError("Could not load your personal note. You can still use course notes.");
        setModules(overview.modules);
        const groups: Record<number, Document[]> = {};
        for (const document of overview.documents) {
          (groups[document.module_id] ||= []).push(document);
        }
        setDocuments(groups); setUsage(overview.usage);
        setModuleId(overview.modules[0]?.id ?? null);
      } catch (error) { if (active) setError(errorMessage(error)); }
      finally { if (active) setLoading(false); }
    }
    void load();
    return () => { active = false; };
  }, [subjectId]);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [messages.length, busy]);

  useEffect(() => {
    const url = viewer?.url;
    const downloadUrl = viewer?.downloadUrl;
    return () => { if (url?.startsWith("blob:")) URL.revokeObjectURL(url); if (downloadUrl?.startsWith("blob:")) URL.revokeObjectURL(downloadUrl); };
  }, [viewer?.url, viewer?.downloadUrl]);

  const selectedModule = modules.find(module => module.id === moduleId);
  const ready = (documents[moduleId || 0] || []).filter(document => document.status === "ready");
  const selectedDocumentId = ready.some(document => document.id === documentId) ? documentId : ready[0]?.id || "";
  const remaining = usage ? Math.max(0, usage.limit - usage.used) : null;

  async function viewDocument(document: Document, page = 1) {
    setOpeningFile(document.id); setError("");
    try {
      if (document.file_type === "pptx") {
        const [pdf, original] = await Promise.all([api.preview(document.id), api.file(document.id)]);
        const url = URL.createObjectURL(pdf);
        setViewer({ document, page, url, downloadUrl: URL.createObjectURL(original) });
      } else {
        const url = URL.createObjectURL(await api.file(document.id));
        setViewer({ document, page, url });
      }
      setZoom(100);
    } catch (error) { setError(errorMessage(error)); }
    finally { setOpeningFile(""); }
  }

  async function openSource(source: Source) {
    if (source.source_type === "personal" && source.document_id) {
      try {
        const url = URL.createObjectURL(await api.noteFile(source.document_id));
        setViewer({ document: { id: source.document_id, title: "My note", module: null, status: "ready", page_count: null, file_type: "pdf" }, page: source.page, url });
        setZoom(100);
      } catch (error) { setError(errorMessage(error)); }
      return;
    }
    const all = Object.values(documents).flat();
    const document = all.find(item => item.id === source.document_id) ||
      all.find(item => item.title === source.document && item.module === source.module);
    if (document) void viewDocument(document, source.page);
    else setError("This source is no longer available.");
  }

  async function replaceNote(event: React.FormEvent) {
    event.preventDefault();
    if (!noteFile) return;
    setNoteBusy(true); setError("");
    const data = new FormData();
    data.set("subject_id", String(subjectId)); data.set("file", noteFile); data.set("replace", "true");
    try {
      await processNote(data, setNoteStage);
      setPersonalNote((await api.notes()).find(note => note.subject_id === subjectId) || null);
      setNoteFile(null);
    } catch (error) { const message = errorMessage(error); setNoteStage(message.includes("may still") ? "Status unavailable" : "Failed"); setError(message); }
    finally { setNoteBusy(false); }
  }

  async function deletePersonalNote() {
    if (!window.confirm("Delete your personal note for this subject?")) return;
    setNoteBusy(true); setError("");
    try { await api.deleteNote(subjectId); setPersonalNote(null); setNoteStage("Note deleted."); }
    catch (error) { setError(errorMessage(error)); }
    finally { setNoteBusy(false); }
  }

  async function ask(event: React.FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (!text || busy || (scope !== "subject" && !moduleId) || (scope === "document" && !selectedDocumentId)) return;
    setBusy(true); setError("");
    try {
      const answer = await api.ask(text, subjectId, scope === "subject" ? null : moduleId, scope === "document" ? selectedDocumentId : null, mode, messages);
      appendChat(subjectId, [
        { role: "user", content: text },
        { role: "assistant", content: answer.answer, sources: answer.sources },
      ]);
      setQuestion("");
      setUsage(previous => previous ? { ...previous, used: Math.max(0, previous.limit - answer.remaining) } : previous);
    } catch (error) {
      setError(errorMessage(error));
      try { setUsage(await api.usage()); } catch { /* The original error remains visible. */ }
    } finally { setBusy(false); }
  }

  if (loading) return <p role="status" className="py-12 text-center text-muted-foreground">Opening your subject notes…</p>;
  if (!subject) return <div><p role="alert">{error || "Subject not found."}</p><Link href="/" className="mt-4 inline-block underline">Back to subjects</Link></div>;
  return <div className="mx-auto max-w-6xl">
    <Link href="/" className="mb-6 inline-flex items-center gap-2 text-xs text-muted-foreground hover:text-primary"><ArrowLeft size={14} />All subjects</Link>
    <div className="mb-7 flex flex-wrap items-center gap-4"><span className="grid size-14 place-items-center rounded-xl bg-primary text-lg font-semibold text-white">{subject.code}</span><div><p className="mb-1 text-[10px] font-medium uppercase tracking-[.2em] text-gold">Your course workspace</p><h1 className="font-heading text-2xl font-semibold sm:text-3xl">{subject.name}</h1></div></div>
    {error && <p role="alert" className="mb-5 rounded-lg bg-red-50 p-4 text-sm text-red-800">{error}</p>}
    {viewer && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-2 sm:p-4" role="dialog" aria-modal="true" aria-label={viewer.document.title}>
      <div className="flex h-full w-full flex-col rounded-xl bg-white p-3 shadow-xl">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><h2 className="truncate font-semibold">{viewer.document.title}</h2><div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setZoom(value => Math.max(50, value - 25))} aria-label="Zoom out">-</Button><span className="text-sm">{zoom}%</span><Button variant="outline" size="sm" onClick={() => setZoom(value => Math.min(250, value + 25))} aria-label="Zoom in">+</Button>
          {viewer.downloadUrl && <a className="px-2 text-sm underline" href={viewer.downloadUrl} download={`${viewer.document.title}.pptx`}>Download PPTX</a>}
          <Button variant="outline" size="sm" onClick={() => setViewer(null)}>Close</Button></div></div>
        <iframe title={viewer.document.title} className="w-full flex-1" src={`${viewer.url}#page=${viewer.page}&zoom=${zoom}`} />
      </div>
    </div>}
    <div className="grid items-start gap-6 xl:grid-cols-[290px_minmax(0,1fr)]">
      <section aria-label="Module documents" className="space-y-4">
        {personalNote && personalNotesAvailable() && <Card><CardContent className="space-y-3 pt-5"><h2 className="font-semibold">My note</h2><Button type="button" variant="outline" size="sm" onClick={() => void openSource({ n: 1, document_id: personalNote.id, document: "My note", module: null, page: 1, score: 1, source_type: "personal" })}>View</Button><form onSubmit={replaceNote} className="space-y-2"><label htmlFor="replace-note" className="block text-sm">Choose a replacement</label><p className="text-xs">Your file is sent to Google Gemini for OCR.</p><input id="replace-note" type="file" accept=".pdf,.png,.jpg,.jpeg" disabled={noteBusy} onChange={event => setNoteFile(event.target.files?.[0] || null)} className="block w-full text-xs file:mr-2 file:rounded file:border file:px-2 file:py-1" /><div className="flex gap-2"><Button type="submit" size="sm" disabled={noteBusy || !noteFile}>Replace</Button><Button type="button" variant="outline" size="sm" disabled={noteBusy} onClick={() => void deletePersonalNote()}>Delete</Button></div></form>{noteStage && <p role="status" className="text-xs">{noteBusy && <span className="mr-2 inline-block size-3 animate-spin rounded-full border-2 border-current border-t-transparent" />}{noteStage}</p>}</CardContent></Card>}
        <Worksheets subjectId={subjectId} selected={worksheetId} select={id => { setWorksheetId(id); if (id) { setScope("worksheet"); void api.worksheet(id).then(item => setMode(item.mode)).catch(e => setError(errorMessage(e))); } }} answerMethod={answerMethod} />
        <div className="flex items-center gap-2"><Layers size={17} /><h2 className="font-heading text-xl font-semibold">Course material</h2><span className="ml-auto text-xs text-muted-foreground">{modules.length} modules</span></div>
        {modules.map(module => <Card key={module.id} className={cn("overflow-hidden", moduleId === module.id && "border-primary/35")}>
          <details open={moduleId === module.id}>
            <summary className="flex list-none items-center gap-3 p-4"><span className="grid size-8 shrink-0 place-items-center rounded-lg bg-background text-xs font-semibold text-primary">{String(module.number).padStart(2, "0")}</span><div className="min-w-0 flex-1"><p className="text-xs text-muted-foreground">Module {module.number}</p><h3 className="mt-1 text-sm font-medium">{module.title}</h3></div><ChevronDown size={15} className="shrink-0" /></summary>
            <div className="space-y-3 border-t border-border px-4 pb-4 pt-3">
              {(documents[module.id] || []).map(document => <div key={document.id} className="rounded-lg bg-background/60 p-3">
                <div className="flex items-start gap-2"><FileText size={16} className="mt-1 shrink-0 text-muted-foreground" /><div className="min-w-0"><p className="break-words text-xs font-medium leading-5">{document.title}</p><p className="mt-1 text-[10px] capitalize text-muted-foreground">{document.status}{document.page_count ? ` · ${document.page_count} ${document.file_type === "pptx" ? "slides" : "pages"}` : ""}</p></div></div>
                {document.status === "ready" && <Button variant="ghost" size="sm" className="mt-2 h-7 px-0 text-xs" disabled={!!openingFile} onClick={() => void viewDocument(document)}>{openingFile === document.id ? "Opening…" : "View"}<ArrowUpRight size={13} /></Button>}
              </div>)}
              {!documents[module.id]?.length && <p className="text-xs text-muted-foreground">No documents uploaded yet.</p>}
              <Button variant="outline" size="sm" className="w-full" disabled={busy || moduleId === module.id} onClick={() => { setModuleId(module.id); setDocumentId(""); }}>{moduleId === module.id ? "Selected for chat" : "Use this module"}</Button>
            </div>
          </details>
        </Card>)}
        {!modules.length && <p className="text-sm text-muted-foreground">No modules yet. Whole-subject chat remains available.</p>}
      </section>
      <Card className="overflow-hidden">
        <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-5 sm:px-6"><div className="flex items-center gap-3"><span className="grid size-9 place-items-center rounded-xl bg-background"><Sparkles size={18} className="text-gold" /></span><div><h2 className="font-heading text-xl font-semibold">Ask your notes</h2></div></div><Button variant="ghost" size="sm" disabled={busy || !messages.length} onClick={() => clearChat(subjectId)}>New chat</Button><span className="rounded-full bg-background px-3 py-1.5 text-xs text-primary">{remaining ?? "—"}/{usage?.limit ?? "—"} left today</span></div>
        <div className="space-y-4 border-b border-border bg-[#fcfbf8] p-5 sm:px-6">
          <fieldset disabled={busy}><legend className="mb-2 text-xs font-medium text-muted-foreground">Answer mode</legend><div className="flex gap-1 rounded-lg bg-muted p-1">{(["normal", "strict"] as const).map(value => <label key={value} className={cn("flex-1 cursor-pointer rounded-md px-3 py-2 text-center text-xs capitalize", mode === value ? "bg-white text-primary shadow-sm" : "text-muted-foreground")}><input type="radio" name="mode" value={value} checked={mode === value} onChange={() => { setMode(value); if (scope === "worksheet" && worksheetId) void api.worksheetMode(worksheetId, value).catch(e => setError(errorMessage(e))); }} className="sr-only" />{value}</label>)}</div></fieldset>
          <fieldset disabled={busy}><legend className="mb-2 text-xs font-medium text-muted-foreground">Question scope</legend><div className="grid grid-cols-2 sm:grid-cols-4 gap-1 rounded-lg bg-muted p-1">{([["module", "This module"], ["document", "This document"], ["subject", "Whole subject"], ["worksheet", "Worksheet"]] as const).map(([value, label]) => <label key={value} className={cn("cursor-pointer rounded-md px-1 py-2 text-center text-xs transition-colors sm:px-3", scope === value ? "bg-white text-primary shadow-sm" : "text-muted-foreground")}><input type="radio" name="scope" value={value} checked={scope === value} onChange={() => setScope(value)} className="sr-only" />{label}</label>)}</div></fieldset>
          {scope !== "subject" && scope !== "worksheet" && <div className="grid gap-3 sm:grid-cols-2"><div><label htmlFor="module" className="sr-only">Selected module</label><select id="module" value={moduleId ?? ""} disabled={busy} onChange={event => { setModuleId(Number(event.target.value)); setDocumentId(""); }}><option value="" disabled>Select module</option>{modules.map(module => <option key={module.id} value={module.id}>Module {module.number} · {module.title}</option>)}</select></div>{scope === "document" && <div><label htmlFor="pdf" className="sr-only">Selected document</label><select id="pdf" value={selectedDocumentId} disabled={busy || !ready.length} onChange={event => setDocumentId(event.target.value)}>{!ready.length && <option value="">No ready documents</option>}{ready.map(document => <option key={document.id} value={document.id}>{document.title}</option>)}</select></div>}</div>}
        </div>
        {scope === "worksheet" ? <WorksheetChat selected={worksheetId} answerMethod={answerMethod} setAnswerMethod={setAnswerMethod} openSource={openSource} Figure={Figure} /> : <CardContent className="p-0">
          <div className="max-h-[560px] min-h-80 space-y-6 overflow-y-auto p-5 sm:p-6" aria-live="polite" aria-busy={busy}>
            {!messages.length && !busy && <div className="flex min-h-64 flex-col items-center justify-center text-center"><span className="mb-5 grid size-14 place-items-center rounded-2xl border border-border bg-background"><BookOpen size={26} strokeWidth={1.3} className="text-primary" /></span><h3 className="font-heading text-xl">Start with a question.</h3><p className="mt-2 max-w-xs text-sm leading-6 text-muted-foreground">Ask about a concept, request an explanation, or connect ideas from your course notes.</p></div>}
            {messages.map((message, index) => <div key={index} className={cn("flex", message.role === "user" ? "justify-end" : "justify-start")}><div className={cn("max-w-[95%] rounded-2xl px-4 py-3 text-sm leading-7 sm:max-w-[90%]", message.role === "user" ? "rounded-br-sm bg-primary text-white" : "w-full rounded-bl-sm border border-border bg-[#fcfbf8]")}><p className="mb-1 text-[10px] font-semibold uppercase tracking-wider opacity-60">{message.role === "user" ? "You" : "Lecture Notes"}</p><p className="whitespace-pre-wrap break-words">{message.content}</p>{message.role === "assistant" && !!message.sources?.length && <details className="mt-4 border-t border-border pt-3"><summary className="text-xs font-medium text-primary">Sources ({message.sources?.length || 0})</summary><div className="mt-3 space-y-2">{message.sources?.map(source => <button type="button" key={source.n} onClick={() => openSource(source)} className="block w-full rounded-lg bg-white p-3 text-left text-xs leading-5 text-primary underline">[{source.n}] {subject.code} · {source.module !== null ? `Module ${source.module}` : "Whole subject"} · {source.document} · {source.page_label || `p.${source.page}`} </button>)}{message.sources?.filter(source => source.figure_id).map(source => <Figure key={source.n} id={source.figure_id!} />)}{!message.sources?.length && <p className="text-xs text-muted-foreground">No supporting notes found in this scope.</p>}</div></details>}</div></div>)}
            {busy && <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground"><Sparkles size={16} className="animate-pulse text-gold" />Looking through your notes…</p>}
            <div ref={bottom} />
          </div>
          {remaining === 0 && !savedKey && <p className="mx-5 mb-4 rounded-lg bg-background p-3 text-xs leading-5">Your shared allowance is used. <Link href="/settings" className="font-semibold underline">Add your own key in Settings</Link> to continue.</p>}
          <form onSubmit={ask} className="border-t border-border p-4 sm:p-5"><label htmlFor="question" className="sr-only">Your question</label><div className="flex items-end gap-3 rounded-xl border border-input bg-white p-2 focus-within:ring-2 focus-within:ring-ring"><textarea id="question" rows={2} maxLength={1000} value={question} onChange={event => setQuestion(event.target.value)} placeholder="What would you like to understand?" disabled={busy} className="min-h-14 w-full resize-none border-0 bg-transparent p-2 text-sm outline-none focus-visible:outline-none" /><Button type="submit" size="icon" aria-label="Send question" disabled={busy || !question.trim() || (scope !== "subject" && !moduleId) || (scope === "document" && !selectedDocumentId)}><Send size={17} /></Button></div></form>
        </CardContent>}
      </Card>
    </div>
  </div>;
}
