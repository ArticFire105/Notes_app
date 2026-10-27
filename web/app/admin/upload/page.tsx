/**
 * Upload official PDFs using the admin-only FastAPI endpoint.
 * A cancellable polling loop stops when ingestion is ready or failed.
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

import { useEffect, useRef, useState } from "react";
import { CheckCircle2, FileText, Upload, LoaderCircle, AlertCircle } from "lucide-react";
import { api, errorMessage, invalidateData, type Document, type Module, type Subject } from "@/lib/api";
import { useSession } from "@/components/session-provider";
import { DocumentManager } from "@/components/document-manager";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

export default function UploadPage() {
  const { profile } = useSession();
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [modules, setModules] = useState<Module[]>([]);
  const [subjectId, setSubjectId] = useState("");
  const [moduleId, setModuleId] = useState("");
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [upload, setUpload] = useState<Document | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingModules, setLoadingModules] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [documentVersion, setDocumentVersion] = useState(0);
  const fileInput = useRef<HTMLInputElement>(null);
  const isAdmin = profile?.role === "admin";

  useEffect(() => {
    if (!isAdmin) return;
    let active = true;
    api.subjects().then(list => {
      if (active) { setSubjects(list); setSubjectId(String(list[0]?.id || "")); }
    }).catch(error => { if (active) setError(errorMessage(error)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [isAdmin]);

  useEffect(() => {
    if (!subjectId || !isAdmin) return;
    let active = true;
    setModules([]); setModuleId(""); setLoadingModules(true);
    api.modules(Number(subjectId)).then(list => {
      if (active) { setModules(list); setModuleId(String(list[0]?.id || "")); }
    }).catch(error => { if (active) setError(errorMessage(error)); })
      .finally(() => { if (active) setLoadingModules(false); });
    return () => { active = false; };
  }, [subjectId, isAdmin]);

  const uploadId = upload?.id;
  useEffect(() => {
    if (!uploadId || !isAdmin) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const current = await api.document(uploadId!);
        if (!active) return;
        setUpload(current); setError("");
        if (current.status !== "processing") {
          invalidateData("documents");
          setDocumentVersion(value => value + 1);
          return;
        }
      } catch (error) { if (!active) return; setError(errorMessage(error)); }
      // Schedule after completion so slow requests never overlap.
      timer = setTimeout(() => void poll(), 3000);
    }
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [uploadId, isAdmin]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!file || !title.trim() || !subjectId || !moduleId) { setError("Select a subject, module, title, and PDF or PPTX file."); return; }
    if (file.name.toLowerCase().endsWith(".ppt")) { setError("Old .ppt files are not supported. Save as .pptx and upload again."); return; }
    if (!/\.(pdf|pptx)$/i.test(file.name)) { setError("Choose a PDF or .pptx PowerPoint file."); return; }
    if (file.size > 40 * 1024 * 1024) { setError("The file must be 40 MB or smaller."); return; }
    setBusy(true); setError("");
    const data = new FormData();
    data.set("subject_id", subjectId); data.set("module_id", moduleId);
    data.set("title", title.trim()); data.set("file", file);
    try {
      setUpload(await api.upload(data));
      setDocumentVersion(value => value + 1);
      setTitle(""); setFile(null);
      if (fileInput.current) fileInput.current.value = "";
    } catch (error) { setError(errorMessage(error)); }
    finally { setBusy(false); }
  }

  if (!isAdmin) return <p role="alert" className="p-6 text-sm">Administrator access required.</p>;
  return <div className="mx-auto max-w-3xl space-y-7">
    <div><p className="mb-2 text-xs uppercase tracking-[.2em] text-gold">Educator workspace</p><h1 className="font-heading text-3xl font-semibold">Share the material.</h1><p className="mt-3 text-sm text-muted-foreground">Upload official notes and give every good question a starting point.</p></div>
    {error && <p role="alert" className="rounded-lg bg-red-50 p-4 text-sm text-red-800">{error}</p>}
    <Card><CardHeader><CardTitle>Upload lecture notes</CardTitle><CardDescription>PDFs and PowerPoint (.pptx), up to 40 MB. Pick the module these notes belong to.</CardDescription></CardHeader><CardContent>
      {loading ? <p role="status" className="text-sm text-muted-foreground">Loading subjects…</p> : <form onSubmit={submit}><fieldset disabled={busy || upload?.status === "processing"} className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2"><div className="space-y-2"><label htmlFor="upload-subject">Subject</label><select id="upload-subject" value={subjectId} required onChange={event => { setSubjectId(event.target.value); setModuleId(""); setModules([]); }}><option value="" disabled>Select a subject</option>{subjects.map(subject => <option key={subject.id} value={subject.id}>{subject.code} · {subject.name}</option>)}</select></div><div className="space-y-2"><label htmlFor="upload-module">Module</label><select id="upload-module" value={moduleId} required disabled={loadingModules} onChange={event => setModuleId(event.target.value)}><option value="" disabled>{loadingModules ? "Loading modules…" : "Select a module"}</option>{modules.map(module => <option key={module.id} value={module.id}>Module {module.number} · {module.title}</option>)}</select></div></div>
        <div className="space-y-2"><label htmlFor="title">Document title</label><Input id="title" required maxLength={500} placeholder="e.g. Memory Management" value={title} onChange={event => setTitle(event.target.value)} /></div>
        <div className="rounded-xl border border-dashed border-primary/30 bg-background/40 p-6 text-center"><Upload size={28} strokeWidth={1.3} className="mx-auto mb-3 text-primary" /><label htmlFor="file" className="mb-2 block">Choose your PDF or PowerPoint</label><Input ref={fileInput} id="file" type="file" accept=".pdf,.pptx,.ppt,application/pdf,application/vnd.openxmlformats-officedocument.presentationml.presentation" required className="mx-auto max-w-sm cursor-pointer bg-white text-xs" onChange={event => setFile(event.target.files?.[0] || null)} /><p className="mt-3 text-xs text-muted-foreground">PDF or PPTX · max 40 MB · save old .ppt as .pptx</p></div>
        <Button type="submit" disabled={loadingModules || !moduleId}><Upload size={16} />{busy ? "Uploading…" : "Upload notes"}</Button>
      </fieldset></form>}
    </CardContent></Card>
    {upload && <Card aria-live="polite"><CardContent className="flex items-start gap-4 pt-6"><span className="mt-1">{upload.status === "ready" ? <CheckCircle2 className="text-emerald-700" /> : upload.status === "failed" ? <AlertCircle className="text-red-700" /> : <LoaderCircle className="animate-spin text-gold" />}</span><div><p className="flex items-center gap-2 text-sm font-semibold"><FileText size={15} />{upload.title}</p><p className="mt-2 text-sm">{upload.status === "ready" ? "Ready. Students can now ask questions about these notes." : upload.status === "failed" ? (upload.error || "Document ingestion failed. Check backend logs for details.") : "Processing your document. Status refreshes every three seconds."}</p></div></CardContent></Card>}
    {subjectId && <DocumentManager key={subjectId} subjectId={Number(subjectId)} subjectCode={subjects.find(subject => String(subject.id) === subjectId)?.code || "this subject"} version={documentVersion} onDeleted={id => { if (upload?.id === id) setUpload(null); }} />}
  </div>;
}
