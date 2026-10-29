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
import { api, ApiError, errorMessage, invalidateData, type Document, type QueueDocument, type Module, type Subject } from "@/lib/api";
import { useSession } from "@/components/session-provider";
import { DocumentManager } from "@/components/document-manager";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

export default function UploadPage() {
  const { profile } = useSession();
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [modules, setModules] = useState<Module[]>([]);
  const [newModuleNumber, setNewModuleNumber] = useState("");
  const [newModuleTitle, setNewModuleTitle] = useState("");
  const [managing, setManaging] = useState(false);
  const [newCode, setNewCode] = useState("");
  const [newName, setNewName] = useState("");
  const [addingSubject, setAddingSubject] = useState(false);
  const [subjectId, setSubjectId] = useState("");
  const [moduleId, setModuleId] = useState("");
  const [title, setTitle] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [queue, setQueue] = useState<QueueDocument[]>([]);
  const [uploadErrors, setUploadErrors] = useState<string[]>([]);
  const [uploadStatus, setUploadStatus] = useState("");
  const [retrying, setRetrying] = useState<string | null>(null);
  const [retryError, setRetryError] = useState("");
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

  useEffect(() => {
    if (!isAdmin) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const items = await api.uploadQueue();
        if (active) setQueue(items);
      } catch (error) { if (active) setError(errorMessage(error)); }
      if (active) timer = setTimeout(() => void poll(), 3000);
    }
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [isAdmin]);

  async function addSubject(event: React.FormEvent) {
    event.preventDefault();
    setAddingSubject(true); setError("");
    try {
      const subject = await api.createSubject(newCode, newName);
      setSubjects(await api.subjects());
      setSubjectId(String(subject.id)); setNewCode(""); setNewName("");
    } catch (error) { setError(errorMessage(error)); }
    finally { setAddingSubject(false); }
  }

  async function refreshModules() {
    const list = await api.modules(Number(subjectId));
    setModules(list); setModuleId(current => list.some(module => String(module.id) === current) ? current : String(list[0]?.id || ""));
    setDocumentVersion(value => value + 1);
  }

  async function addModule(event: React.FormEvent) {
    event.preventDefault();
    if (!subjectId) return;
    setManaging(true); setError("");
    try { await api.createModule(Number(subjectId), Number(newModuleNumber), newModuleTitle); await refreshModules(); setNewModuleNumber(""); setNewModuleTitle(""); }
    catch (error) { setError(errorMessage(error)); }
    finally { setManaging(false); }
  }

  async function renameModule(module: Module) {
    const title = window.prompt("New module title:", module.title);
    if (!title || !title.trim()) return;
    setManaging(true); setError("");
    try { await api.renameModule(module.id, title.trim()); await refreshModules(); }
    catch (error) { setError(errorMessage(error)); }
    finally { setManaging(false); }
  }

  async function deleteModule(module: Module) {
    if (!window.confirm(`Delete Module ${module.number}: ${module.title}? This also deletes its documents, searchable chunks, and figures.`)) return;
    setManaging(true); setError("");
    try { await api.deleteModule(module.id); await refreshModules(); }
    catch (error) { setError(errorMessage(error)); }
    finally { setManaging(false); }
  }

  async function deleteSubject() {
    const subject = subjects.find(item => String(item.id) === subjectId);
    if (!subject || !window.confirm(`Delete ${subject.code} - ${subject.name}? This permanently deletes all its modules, documents, figures, and every student's personal note for this subject.`)) return;
    setManaging(true); setError("");
    try {
      await api.deleteSubject(subject.id);
      const list = await api.subjects(); setSubjects(list); setSubjectId(String(list[0]?.id || ""));
      setModules([]); setModuleId(""); setUpload(null);
    } catch (error) { setError(errorMessage(error)); }
    finally { setManaging(false); }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!files.length || !subjectId || !moduleId) { setError("Select a subject, module, and files."); return; }
    setBusy(true); setError(""); setUploadErrors([]);
    const errors: string[] = [];
    for (const file of files) {
      if (!/\.(pdf|pptx)$/i.test(file.name)) { errors.push(`${file.name}: Choose a PDF or .pptx PowerPoint file.`); continue; }
      if (file.size > 40 * 1024 * 1024) { errors.push(`${file.name}: The file must be 40 MB or smaller.`); continue; }
      const data = new FormData();
      data.set("subject_id", subjectId); data.set("module_id", moduleId);
      data.set("title", files.length === 1 && title.trim() ? title.trim() : file.name.replace(/\.(pdf|pptx)$/i, ""));
      data.set("file", file);
      while (true) {
        try { await api.upload(data); setUploadStatus(""); break; }
        catch (error) {
          if (error instanceof ApiError && error.status === 429 && error.retryAfter) {
            setUploadStatus(`Upload limit reached. Waiting ${error.retryAfter} seconds before continuing with ${file.name}. Keep this page open.`);
            await new Promise(resolve => setTimeout(resolve, error.retryAfter! * 1000));
            continue;
          }
          errors.push(`${file.name}: ${errorMessage(error)}`); break;
        }
      }
    }
    setUploadErrors(errors);
    try { setQueue(await api.uploadQueue()); } catch { setError("Could not load upload status."); }
    setDocumentVersion(value => value + 1);
    setTitle(""); setFiles([]);
    if (fileInput.current) fileInput.current.value = "";
    setBusy(false);
  }

  async function retry(id: string) {
    setRetrying(id); setRetryError("");
    try { await api.retryUpload(id); setQueue(await api.uploadQueue()); }
    catch (error) { setRetryError(`Could not start retry: ${errorMessage(error)}`); }
    finally { setRetrying(null); }
  }

  if (!isAdmin) return <p role="alert" className="p-6 text-sm">Administrator access required.</p>;
  return <div className="mx-auto max-w-3xl space-y-7">
    <div><p className="mb-2 text-xs uppercase tracking-[.2em] text-gold">Educator workspace</p><h1 className="font-heading text-3xl font-semibold">Share the material.</h1><p className="mt-3 text-sm text-muted-foreground">Upload official notes and give every good question a starting point.</p></div>
    {error && <p role="alert" className="rounded-lg bg-red-50 p-4 text-sm text-red-800">{error}</p>}
    <Card><CardHeader><CardTitle>Add subject</CardTitle><CardDescription>Five placeholder modules are created automatically.</CardDescription></CardHeader><CardContent>
      <form onSubmit={addSubject} className="flex flex-wrap items-end gap-3"><div className="space-y-2"><label htmlFor="subject-code">Code</label><Input id="subject-code" required maxLength={20} value={newCode} onChange={event => setNewCode(event.target.value)} placeholder="e.g. OS" /></div><div className="min-w-48 flex-1 space-y-2"><label htmlFor="subject-name">Name</label><Input id="subject-name" required maxLength={100} value={newName} onChange={event => setNewName(event.target.value)} placeholder="Subject name" /></div><Button type="submit" disabled={addingSubject}>{addingSubject ? "Adding..." : "Add subject"}</Button></form>
    </CardContent></Card>
    <Card><CardHeader><CardTitle>Upload lecture notes</CardTitle><CardDescription>PDFs and PowerPoint (.pptx), up to 40 MB each. Keep this page open until uploading finishes; indexing continues after you leave.</CardDescription></CardHeader><CardContent>
      {loading ? <p role="status" className="text-sm text-muted-foreground">Loading subjects…</p> : <form onSubmit={submit}><fieldset disabled={busy} className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2"><div className="space-y-2"><label htmlFor="upload-subject">Subject</label><select id="upload-subject" value={subjectId} required onChange={event => { setSubjectId(event.target.value); setModuleId(""); setModules([]); }}><option value="" disabled>Select a subject</option>{subjects.map(subject => <option key={subject.id} value={subject.id}>{subject.code} · {subject.name}</option>)}</select></div><div className="space-y-2"><label htmlFor="upload-module">Module</label><select id="upload-module" value={moduleId} required disabled={loadingModules} onChange={event => setModuleId(event.target.value)}><option value="" disabled>{loadingModules ? "Loading modules…" : "Select a module"}</option>{modules.map(module => <option key={module.id} value={module.id}>Module {module.number} · {module.title}</option>)}</select></div></div>
        <div className="space-y-2"><label htmlFor="title">Document title</label><Input id="title" maxLength={500} placeholder="e.g. Memory Management" value={title} onChange={event => setTitle(event.target.value)} /></div>
        <div onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); setFiles(Array.from(event.dataTransfer.files)); }} className="rounded-xl border border-dashed border-primary/30 bg-background/40 p-6 text-center"><Upload size={28} strokeWidth={1.3} className="mx-auto mb-3 text-primary" /><p className="mb-3">Choose files or drop them here</p><input ref={fileInput} id="file" type="file" multiple accept=".pdf,.pptx,.ppt,application/pdf,application/vnd.openxmlformats-officedocument.presentationml.presentation" className="sr-only" tabIndex={-1} onChange={event => setFiles(Array.from(event.target.files || []))} /><Button type="button" variant="outline" onClick={() => fileInput.current?.click()}>Choose files</Button><p className="mt-3 text-sm" aria-live="polite">{files.length ? files.map(file => file.name).join(", ") : "No files selected"}</p><p className="mt-3 text-xs text-muted-foreground">PDF or PPTX · max 40 MB · save old .ppt as .pptx</p></div>
        <Button type="submit" disabled={loadingModules || !moduleId}><Upload size={16} />{busy ? "Uploading…" : "Upload notes"}</Button>
      </fieldset></form>}
    </CardContent></Card>
    {uploadErrors.map(message => <p key={message} role="alert" className="text-sm text-red-700">{message}</p>)}
    {uploadStatus && <p role="status" className="text-sm">{uploadStatus}</p>}
    {retryError && <p role="alert" className="text-sm text-red-700">{retryError}</p>}
    {queue.length > 0 && <Card aria-live="polite"><CardHeader><CardTitle>Upload queue</CardTitle></CardHeader><CardContent className="space-y-3">{queue.map(item => <div key={item.id} className="rounded-lg border p-3"><p className="font-medium">{item.title}</p><p className="text-sm">{item.queue_status === "queued" ? "Queued" : item.queue_status === "indexing" ? item.total_chunks != null ? `Indexing ${item.embedded_chunks ?? 0} of ${item.total_chunks} chunks` : "Indexing: preparing document" : item.queue_status === "ready" ? item.error ? `Ready. ${item.error}` : "Ready" : item.error || "Failed"}</p>{item.queue_status === "failed" && <Button type="button" size="sm" variant="outline" disabled={retrying !== null} onClick={() => void retry(item.id)}>{retrying === item.id ? "Starting…" : "Retry"}</Button>}</div>)}</CardContent></Card>}
    {subjectId && <Card><CardHeader><CardTitle>Manage subject and modules</CardTitle></CardHeader><CardContent className="space-y-4">
      <Button type="button" variant="outline" disabled={managing || busy} onClick={() => void deleteSubject()}>Delete this subject</Button>
      <form onSubmit={addModule} className="flex flex-wrap items-end gap-3"><div><label htmlFor="module-number" className="block text-sm">Number</label><Input id="module-number" type="number" min={1} max={999} required value={newModuleNumber} onChange={event => setNewModuleNumber(event.target.value)} /></div><div className="min-w-48 flex-1"><label htmlFor="module-title" className="block text-sm">Title</label><Input id="module-title" required maxLength={200} value={newModuleTitle} onChange={event => setNewModuleTitle(event.target.value)} /></div><Button type="submit" disabled={managing || !newModuleNumber || !newModuleTitle.trim()}>Add module</Button></form>
      {modules.map(module => <div key={module.id} className="flex flex-wrap items-center gap-2 rounded-lg border p-3"><span className="min-w-0 flex-1 text-sm">Module {module.number} - {module.title}</span><Button type="button" variant="outline" size="sm" disabled={managing || busy} onClick={() => void renameModule(module)}>Rename</Button><Button type="button" variant="outline" size="sm" disabled={managing || busy} onClick={() => void deleteModule(module)}>Delete</Button></div>)}
    </CardContent></Card>}
    {subjectId && <DocumentManager key={subjectId} subjectId={Number(subjectId)} subjectCode={subjects.find(subject => String(subject.id) === subjectId)?.code || "this subject"} version={documentVersion} onDeleted={id => { if (upload?.id === id) setUpload(null); }} />}
  </div>;
}
