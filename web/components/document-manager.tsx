/**
 * List documents for the subject selected on the admin upload page.
 * Confirmed deletion calls the FastAPI backend and reloads the list.
 * This component belongs only to the current document-management change.
 * The parent page supplies the selected subject.
 * Module and document metadata come from existing read endpoints.
 * Only the admin page renders this component.
 * The backend checks the current role on every deletion.
 * Browser confirmation names the selected document.
 * Cancel leaves the document untouched.
 * Delete buttons are disabled while a request is running.
 * Successful deletion refreshes the current subject list.
 * Failed deletion keeps the error visible.
 * A manual refresh supports changes by another administrator.
 * Module numbers are display labels rather than database IDs.
 * Processing, ready, and failed uploads appear in the list.
 * The backend coordinates deletion with ingestion locks.
 * File deletion belongs to the backend.
 * Chunk deletion belongs to the backend.
 * Cache invalidation belongs to the backend.
 * No database client is imported here.
 * No Storage client is imported here.
 * No service role credential reaches the browser.
 * Authentication is supplied by the existing API client.
 * No user API key is needed for deleting documents.
 * No secrets are printed to the console.
 * Error messages come from the safe API boundary.
 * React state exists only in the current browser session.
 * Uploads trigger a refresh through the parent version prop.
 * Leaving a subject cancels updates from its old read requests.
 * Existing PDF and PowerPoint behaviour stays unchanged.
 * No new package is required for confirmation.
 * Live role and deletion checks remain manual integration tests.
 * Run npm test from the web directory for API-client coverage.
 */

"use client";

import { useEffect, useState } from "react";
import { RefreshCw, Trash2 } from "lucide-react";
import { api, errorMessage, type Document } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

type ListedDocument = Document & { moduleNumber: number };

export function DocumentManager({ subjectId, subjectCode, version, onDeleted }: {
  subjectId: number; subjectCode: string; version: number; onDeleted: (id: string) => void;
}) {
  const [documents, setDocuments] = useState<ListedDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);
  const [deleting, setDeleting] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    async function load() {
      try {
        const modules = await api.modules(subjectId);
        const groups = await Promise.all(modules.map(async module =>
          (await api.documents(module.id)).map(document => ({ ...document, moduleNumber: module.number }))));
        if (active) setDocuments(groups.flat());
      } catch (error) { if (active) setError(errorMessage(error)); }
      finally { if (active) setLoading(false); }
    }
    void load();
    return () => { active = false; };
  }, [subjectId, version, refresh]);

  async function remove(document: ListedDocument) {
    if (!window.confirm(`Are you sure you want to delete "${document.title}"? This removes its file, all searchable chunks, and cached answers for this subject.`)) return;
    setDeleting(document.id); setError(""); setNotice("");
    try {
      await api.deleteDocument(document.id);
      onDeleted(document.id);
      setNotice("Document deleted.");
      setRefresh(value => value + 1);
    } catch (error) { setError(errorMessage(error)); }
    finally { setDeleting(""); }
  }

  return <Card>
    <CardHeader><div className="flex items-center justify-between gap-3"><CardTitle>Documents in {subjectCode}</CardTitle><Button type="button" variant="ghost" size="sm" disabled={loading || !!deleting} onClick={() => { setError(""); setRefresh(value => value + 1); }}><RefreshCw size={15} />Refresh</Button></div><CardDescription>Choose a subject above to manage its uploaded PDF and PowerPoint documents.</CardDescription></CardHeader>
    <CardContent className="space-y-3">
      {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p>}
      {notice && <p role="status" className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</p>}
      {loading ? <p role="status" className="text-sm text-muted-foreground">Loading documents…</p> : documents.length === 0 ? <p className="text-sm text-muted-foreground">No uploaded documents for this subject.</p> : documents.map(document =>
        <div key={document.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border p-4">
          <div className="min-w-0"><p className="break-words text-sm font-medium">{document.title}</p><p className="mt-1 text-xs text-muted-foreground">Module {document.moduleNumber} · {document.file_type.toUpperCase()} · {document.status}</p></div>
          <Button type="button" variant="outline" size="sm" className="text-red-800 hover:bg-red-50" disabled={!!deleting} onClick={() => void remove(document)}><Trash2 size={14} />{deleting === document.id ? "Deleting…" : "Delete"}</Button>
        </div>)}
    </CardContent>
  </Card>;
}
