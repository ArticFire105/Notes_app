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
import { api, errorMessage, type Subject, type Module, type Document, type Usage } from "@/lib/api";
import { useSession } from "@/components/session-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type Scope = "module" | "document" | "subject";

export default function SubjectPage() {
  const { id } = useParams<{ id: string }>();
  const subjectId = Number(id);
  const { histories, appendChat, savedKey } = useSession();
  const [subject, setSubject] = useState<Subject | null>(null);
  const [modules, setModules] = useState<Module[]>([]);
  const [documents, setDocuments] = useState<Record<number, Document[]>>({});
  const [moduleId, setModuleId] = useState<number | null>(null);
  const [documentId, setDocumentId] = useState("");
  const [mode, setMode] = useState<"normal" | "strict">("normal");
  const [scope, setScope] = useState<Scope>("module");
  const [usage, setUsage] = useState<Usage | null>(null);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [fileLinks, setFileLinks] = useState<Record<string, string>>({});
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
        const [subjects, list, allowance] = await Promise.all([api.subjects(), api.modules(subjectId), api.usage()]);
        const entries = await Promise.all(list.map(async module => [module.id, await api.documents(module.id)] as const));
        if (!active) return;
        setSubject(subjects.find(item => item.id === subjectId) || null);
        setModules(list); setDocuments(Object.fromEntries(entries)); setUsage(allowance);
        setModuleId(list[0]?.id ?? null);
      } catch (error) { if (active) setError(errorMessage(error)); }
      finally { if (active) setLoading(false); }
    }
    void load();
    return () => { active = false; };
  }, [subjectId]);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [messages.length, busy]);

  const selectedModule = modules.find(module => module.id === moduleId);
  const ready = (documents[moduleId || 0] || []).filter(document => document.status === "ready");
  const selectedDocumentId = ready.some(document => document.id === documentId) ? documentId : ready[0]?.id || "";
  const remaining = usage ? Math.max(0, usage.limit - usage.used) : null;

  async function viewDocument(document: Document) {
    setOpeningFile(document.id); setError("");
    // Open synchronously so browsers treat this as a user-initiated tab.
    const tab = window.open("about:blank", "_blank");
    if (tab) tab.opener = null;
    try {
      const { url } = await api.fileUrl(document.id);
      const parsed = new URL(url);
      if (!["https:", "http:"].includes(parsed.protocol)) throw new Error("Unsupported URL");
      setFileLinks(previous => ({ ...previous, [document.id]: url }));
      if (tab) tab.location.href = url;
    } catch (error) { tab?.close(); setError(errorMessage(error)); }
    finally { setOpeningFile(""); }
  }

  async function ask(event: React.FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (!text || busy || (scope !== "subject" && !moduleId) || (scope === "document" && !selectedDocumentId)) return;
    setBusy(true); setError("");
    try {
      const answer = await api.ask(text, subjectId, scope === "subject" ? null : moduleId, scope === "document" ? selectedDocumentId : null, mode);
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
    <div className="grid items-start gap-6 xl:grid-cols-[290px_minmax(0,1fr)]">
      <section aria-label="Module documents" className="space-y-4">
        <div className="flex items-center gap-2"><Layers size={17} /><h2 className="font-heading text-xl font-semibold">Course material</h2><span className="ml-auto text-xs text-muted-foreground">{modules.length} modules</span></div>
        {modules.map(module => <Card key={module.id} className={cn("overflow-hidden", moduleId === module.id && "border-primary/35")}>
          <details open={moduleId === module.id}>
            <summary className="flex list-none items-center gap-3 p-4"><span className="grid size-8 shrink-0 place-items-center rounded-lg bg-background text-xs font-semibold text-primary">{String(module.number).padStart(2, "0")}</span><div className="min-w-0 flex-1"><p className="text-xs text-muted-foreground">Module {module.number}</p><h3 className="mt-1 text-sm font-medium">{module.title}</h3></div><ChevronDown size={15} className="shrink-0" /></summary>
            <div className="space-y-3 border-t border-border px-4 pb-4 pt-3">
              {(documents[module.id] || []).map(document => <div key={document.id} className="rounded-lg bg-background/60 p-3">
                <div className="flex items-start gap-2"><FileText size={16} className="mt-1 shrink-0 text-muted-foreground" /><div className="min-w-0"><p className="break-words text-xs font-medium leading-5">{document.title}</p><p className="mt-1 text-[10px] capitalize text-muted-foreground">{document.status}{document.page_count ? ` · ${document.page_count} ${document.file_type === "pptx" ? "slides" : "pages"}` : ""}</p></div></div>
                {document.status === "ready" && <Button variant="ghost" size="sm" className="mt-2 h-7 px-0 text-xs" disabled={!!openingFile} onClick={() => void viewDocument(document)}>{openingFile === document.id ? "Opening…" : (document.file_type === "pptx" ? "Download PPTX" : "View PDF")}<ArrowUpRight size={13} /></Button>}
                {fileLinks[document.id] && <a href={fileLinks[document.id]} target="_blank" rel="noopener noreferrer" className="mt-1 block text-xs underline">Open source file in a new tab</a>}
              </div>)}
              {!documents[module.id]?.length && <p className="text-xs text-muted-foreground">No documents uploaded yet.</p>}
              <Button variant="outline" size="sm" className="w-full" disabled={busy || moduleId === module.id} onClick={() => { setModuleId(module.id); setDocumentId(""); }}>{moduleId === module.id ? "Selected for chat" : "Use this module"}</Button>
            </div>
          </details>
        </Card>)}
        {!modules.length && <p className="text-sm text-muted-foreground">No modules yet. Whole-subject chat remains available.</p>}
      </section>
      <Card className="overflow-hidden">
        <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-5 sm:px-6"><div className="flex items-center gap-3"><span className="grid size-9 place-items-center rounded-xl bg-background"><Sparkles size={18} className="text-gold" /></span><div><h2 className="font-heading text-xl font-semibold">Ask your notes</h2></div></div><span className="rounded-full bg-background px-3 py-1.5 text-xs text-primary">{remaining ?? "—"}/{usage?.limit ?? "—"} left today</span></div>
        <div className="space-y-4 border-b border-border bg-[#fcfbf8] p-5 sm:px-6">
          <fieldset disabled={busy}><legend className="mb-2 text-xs font-medium text-muted-foreground">Answer mode</legend><div className="flex gap-1 rounded-lg bg-muted p-1">{(["normal", "strict"] as const).map(value => <label key={value} className={cn("flex-1 cursor-pointer rounded-md px-3 py-2 text-center text-xs capitalize", mode === value ? "bg-white text-primary shadow-sm" : "text-muted-foreground")}><input type="radio" name="mode" value={value} checked={mode === value} onChange={() => setMode(value)} className="sr-only" />{value}</label>)}</div></fieldset>
          <fieldset disabled={busy}><legend className="mb-2 text-xs font-medium text-muted-foreground">Question scope</legend><div className="grid grid-cols-3 gap-1 rounded-lg bg-muted p-1">{([["module", "This module"], ["document", "This document"], ["subject", "Whole subject"]] as const).map(([value, label]) => <label key={value} className={cn("cursor-pointer rounded-md px-1 py-2 text-center text-xs transition-colors sm:px-3", scope === value ? "bg-white text-primary shadow-sm" : "text-muted-foreground")}><input type="radio" name="scope" value={value} checked={scope === value} onChange={() => setScope(value)} className="sr-only" />{label}</label>)}</div></fieldset>
          {scope !== "subject" && <div className="grid gap-3 sm:grid-cols-2"><div><label htmlFor="module" className="sr-only">Selected module</label><select id="module" value={moduleId ?? ""} disabled={busy} onChange={event => { setModuleId(Number(event.target.value)); setDocumentId(""); }}><option value="" disabled>Select module</option>{modules.map(module => <option key={module.id} value={module.id}>Module {module.number} · {module.title}</option>)}</select></div>{scope === "document" && <div><label htmlFor="pdf" className="sr-only">Selected document</label><select id="pdf" value={selectedDocumentId} disabled={busy || !ready.length} onChange={event => setDocumentId(event.target.value)}>{!ready.length && <option value="">No ready documents</option>}{ready.map(document => <option key={document.id} value={document.id}>{document.title}</option>)}</select></div>}</div>}
        </div>
        <CardContent className="p-0">
          <div className="max-h-[560px] min-h-80 space-y-6 overflow-y-auto p-5 sm:p-6" aria-live="polite" aria-busy={busy}>
            {!messages.length && !busy && <div className="flex min-h-64 flex-col items-center justify-center text-center"><span className="mb-5 grid size-14 place-items-center rounded-2xl border border-border bg-background"><BookOpen size={26} strokeWidth={1.3} className="text-primary" /></span><h3 className="font-heading text-xl">Start with a question.</h3><p className="mt-2 max-w-xs text-sm leading-6 text-muted-foreground">Ask about a concept, request an explanation, or connect ideas from your course notes.</p></div>}
            {messages.map((message, index) => <div key={index} className={cn("flex", message.role === "user" ? "justify-end" : "justify-start")}><div className={cn("max-w-[95%] rounded-2xl px-4 py-3 text-sm leading-7 sm:max-w-[90%]", message.role === "user" ? "rounded-br-sm bg-primary text-white" : "w-full rounded-bl-sm border border-border bg-[#fcfbf8]")}><p className="mb-1 text-[10px] font-semibold uppercase tracking-wider opacity-60">{message.role === "user" ? "You" : "Lecture Notes"}</p><p className="whitespace-pre-wrap break-words">{message.content}</p>{message.role === "assistant" && <details className="mt-4 border-t border-border pt-3"><summary className="text-xs font-medium text-primary">Sources ({message.sources?.length || 0})</summary><div className="mt-3 space-y-2">{message.sources?.map(source => <p key={source.n} className="rounded-lg bg-white p-3 text-xs leading-5 text-muted-foreground">[{source.n}] {subject.code} · {source.module !== null ? `Module ${source.module}` : "Whole subject"} · {source.document} · {source.page_label || `p.${source.page}`} </p>)}{!message.sources?.length && <p className="text-xs text-muted-foreground">No supporting notes found in this scope.</p>}</div></details>}</div></div>)}
            {busy && <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground"><Sparkles size={16} className="animate-pulse text-gold" />Looking through your notes…</p>}
            <div ref={bottom} />
          </div>
          {remaining === 0 && !savedKey && <p className="mx-5 mb-4 rounded-lg bg-background p-3 text-xs leading-5">Your shared allowance is used. <Link href="/settings" className="font-semibold underline">Add your own key in Settings</Link> to continue.</p>}
          <form onSubmit={ask} className="border-t border-border p-4 sm:p-5"><label htmlFor="question" className="sr-only">Your question</label><div className="flex items-end gap-3 rounded-xl border border-input bg-white p-2 focus-within:ring-2 focus-within:ring-ring"><textarea id="question" rows={2} maxLength={1000} value={question} onChange={event => setQuestion(event.target.value)} placeholder="What would you like to understand?" disabled={busy} className="min-h-14 w-full resize-none border-0 bg-transparent p-2 text-sm outline-none focus-visible:outline-none" /><Button type="submit" size="icon" aria-label="Send question" disabled={busy || !question.trim() || (scope !== "subject" && !moduleId) || (scope === "document" && !selectedDocumentId)}><Send size={17} /></Button></div></form>
        </CardContent>
      </Card>
    </div>
  </div>;
}
