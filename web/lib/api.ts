/**
 * Send typed requests to the configured FastAPI backend.
 * An in-memory session and single refresh promise prevent token races.
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

export type Session = { access_token: string; expires_at: number };
export type Profile = { email: string; role: string };
export type Subject = { id: number; code: string; name: string };
export type Module = { id: number; subject_id: number; number: number; title: string };
export type Document = { id: string; title: string; module: number | null; status: "processing" | "ready" | "failed"; page_count: number | null; file_type: "pdf" | "pptx"; error?: string | null; embedded_chunks?: number | null; total_chunks?: number | null };
export type QueueDocument = Document & { queue_status: "queued" | "indexing" | "ready" | "failed" };
export type Worksheet = { id: string; subject_id: number; mode: "normal" | "strict"; status: string; error: string | null; created_at: string };
export type WorksheetQuestion = { id: number; position: number; question_number: string | null; question_text: string; marks: number | null; question_type: string | null; status: string; answer: string | null; sources: Source[] | null; error: string | null };
export type WorksheetTurn = { id: number; question_id: number | null; message: string; answer: string; sources: Source[] };
export type WorksheetDetail = Worksheet & { questions: WorksheetQuestion[]; chat: WorksheetTurn[] };
export type Overview = { subject: Subject; modules: Module[]; documents: (Document & { module_id: number })[]; usage: Usage };
export type Usage = { used: number; limit: number; resets_at: string };
export type Slide = { number: number; total: number; aspect: number; shapes: { kind: "text" | "image"; left: number; top: number; width: number; height: number; text?: string; data?: string; mime?: string }[] };
export type NoteJob = { stage: "reading" | "indexing" | "ready" | "failed"; page: number; total?: number; error?: string; result?: PersonalNote };
export type PersonalNote = { id: string; subject_id: number; title: string; file_type: "pdf" | "image"; failed_pages: number[] };
export type Source = { figure_id?: string | null; source_type?: "official" | "personal"; document_id?: string | null; n: number; document: string; module: number | null; page: number; page_label?: string | null; score: number };
export type Answer = { answer: string; sources: Source[]; remaining: number };
export type Message = { role: "user" | "assistant"; content: string; sources?: Source[] };

let session: Session | null = null;
let userKey = "";
let revision = 0;
const cache = new Map<string, { value: unknown; expires: number }>();
const pending = new Map<string, Promise<unknown>>();
let cacheRevision = 0;

export function invalidateData(scope: "all" | "documents" | "usage" = "all") {
  for (const key of cache.keys()) {
    if (scope === "all" || key.startsWith("overview:") || (scope === "documents" && key.startsWith("documents:"))) cache.delete(key);
  }
  // In-flight requests started before a mutation must not repopulate stale data.
  cacheRevision += 1;
  pending.clear();
}

async function cached<T>(key: string, load: () => Promise<T>): Promise<T> {
  const entry = cache.get(key);
  if (entry && entry.expires > Date.now()) return entry.value as T;
  const existing = pending.get(key);
  if (existing) return existing as Promise<T>;
  const started = cacheRevision;
  const promise = load().then(value => {
    if (started === cacheRevision) cache.set(key, { value, expires: Date.now() + 60000 });
    return value;
  }).finally(() => { if (pending.get(key) === promise) pending.delete(key); });
  pending.set(key, promise);
  return promise;
}

let refreshPromise: Promise<void> | null = null;

const baseUrl = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  constructor(message: string, status = 0) { super(message); this.status = status; }
}

export function saveSession(value: Session) {
  revision += 1;
  session = value;
}
export function setUserKey(value: string) { userKey = value.trim(); }
export function clearSession() {
  revision += 1;
  session = null;
  userKey = "";
  invalidateData();
}

function expireSession() {
  clearSession();
  window.dispatchEvent(new Event("session-expired"));
}

async function refreshSession() {
  if (session && session.expires_at * 1000 > Date.now() + 30000) return;
  if (!refreshPromise) {
    const previousRevision = revision;
    refreshPromise = (async () => {
      try {
        const next = await request<Session>("/auth/refresh", {
          method: "POST",
        }, false);
        if (revision === previousRevision) session = next;
      } catch (error) {
        if (error instanceof ApiError && error.status === 401 && revision === previousRevision) expireSession();
        throw error;
      } finally { refreshPromise = null; }
    })();
  }
  await refreshPromise;
}

async function request<T>(path: string, init: RequestInit = {}, authenticated = true, byok = false, binary = false): Promise<T> {
  const startedRevision = revision;
  if (authenticated) {
    await refreshSession();
    if (!session) throw new ApiError("Please sign in to continue.", 401);
  }
  const headers = new Headers(init.headers);
  if (path.startsWith("/auth/")) headers.set("X-Browser-Session", "1");
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (authenticated && session) headers.set("Authorization", "Bearer " + session.access_token);
  if (byok && userKey) headers.set("X-User-Api-Key", userKey);
  let response: Response;
  try {
    response = await fetch(baseUrl + path, { ...init, headers, cache: "no-store", redirect: "error", credentials: "include" });
  } catch {
    throw new ApiError("Cannot reach the backend. Check that FastAPI is running.");
  }
  if (authenticated && startedRevision !== revision) throw new ApiError("Your session changed. Please try again.");
  if (!response.ok) {
    if (response.status === 429 && response.headers.has("Retry-After")) {
      throw new ApiError("Too many requests. Please wait and try again.", 429);
    }
    const messages: Record<number, string> = {
      400: "Check your input and try again. For email codes, you may need to wait before resending.",
      401: "Your session or email code has expired. Please sign in again.",
      403: "Use your college account. This action may require administrator access.",
      404: "This item is unavailable. Older documents may need to be uploaded again for PDF viewing.",
      409: "This document already exists. Choose another title.",
      413: "Choose a PDF or PPTX file of 40 MB or smaller.",
      422: "Check the required fields and selected scope.",
      429: "Daily allowance or rate limit reached. Add your own key in Settings, or try later.",
      503: "The model or API key is unavailable. Check your key or try again later.",
    };
    if (response.status === 401 && authenticated) expireSession();
    if (/^\/subjects\/\d+\/modules$/.test(path) && init.method === "POST" && response.status === 409) throw new ApiError("This module number already exists.", 409);
    if (path === "/subjects" && init.method === "POST" && response.status === 409) throw new ApiError("A subject with this code already exists.", 409);
    if (path.startsWith("/notes/jobs/") && response.status === 404) throw new ApiError("Processing status is unavailable. The server may have restarted; check My Notes before retrying.", 404);
    if (path === "/notes/jobs" && response.status === 413) throw new ApiError("Your note must be 20 MB or smaller.", 413);
    if (path === "/notes" && response.status === 409) throw new ApiError("You already have a note for this subject. Choose Replace to upload a new one.", 409);
    if (path === "/notes" && response.status === 400) throw new ApiError("Choose a readable PDF (up to 30 pages), PNG, or JPEG image.", 400);
    if (path.startsWith("/notes/") && init.method === "DELETE" && response.status === 503) throw new ApiError("Could not delete your note. Please try again.", 503);
    if (path === "/notes" && response.status === 503) throw new ApiError("Could not process or save your note. Check the backend OCR setup and try again.", 503);
    if (path === "/notes" && response.status === 413) throw new ApiError("Your note must be 20 MB or smaller.", 413);
    if (path.endsWith("/preview") && response.status === 503) throw new ApiError("PowerPoint preview requires LibreOffice on the backend, or conversion failed.", 503);
    if (init.method === "DELETE" && response.status === 503 && (/^\/subjects\/\d+$/.test(path) || /^\/modules\/\d+$/.test(path))) {
      const body = await response.json().catch(() => null);
      const recovery = "Deletion failed and some files could not be restored. Contact an administrator.";
      throw new ApiError(body?.detail === recovery ? recovery : "Could not delete this item. Please try again.", 503);
    }
    if (init.method === "DELETE" && response.status === 503) {
      const body = await response.json().catch(() => null);
      const safeReasons = [
        "Could not complete document deletion. Please retry or check backend logs.",
        "Delete failed and the file could not be restored. Contact the administrator and check backend logs.",
      ];
      if (safeReasons.includes(body?.detail)) throw new ApiError(body.detail, 503);
    }
    if (path === "/documents" && response.status === 400) {
      const body = await response.json().catch(() => null);
      // Only this fixed public reason is allowed through; arbitrary provider diagnostics stay hidden.
      if (body?.detail === "No readable text found in slides") {
        throw new ApiError("No readable text found in slides", 400);
      }
    }
    if (path === "/documents" && response.status === 413) {
      throw new ApiError("Choose a file of at most 40 MB and 200 pages or slides.", 413);
    }
    // Provider response bodies can contain diagnostics; display only fixed messages.
    throw new ApiError(messages[response.status] || "The backend could not complete this request.", response.status);
  }
  if (binary) return response.blob() as Promise<T>;
  return response.json() as Promise<T>;
}

export const api = {
  restore: () => refreshSession(),
  logout: () => request("/auth/logout", { method: "POST" }, false),
  sendCode: (email: string) => request("/auth/send-code", { method: "POST", body: JSON.stringify({ email }) }, false),
  verifyCode: (email: string, code: string) => request<Session>("/auth/verify", { method: "POST", body: JSON.stringify({ email, code }) }, false),
  me: () => request<Profile>("/me"),
  usage: () => request<Usage>("/me/usage"),
  notes: () => request<PersonalNote[]>("/notes"),
  startNoteJob: (data: FormData, signal?: AbortSignal) => request<{ id: string }>("/notes/jobs", { method: "POST", body: data, signal }, true, true),
  noteJob: (id: string, signal?: AbortSignal) => request<NoteJob>(`/notes/jobs/${id}`, { signal }),
  uploadNote: (data: FormData) => request<PersonalNote>("/notes", { method: "POST", body: data }, true, true).then(value => { invalidateData("documents"); return value; }),
  deleteNote: (subjectId: number) => request(`/notes/${subjectId}`, { method: "DELETE" }).then(value => { invalidateData("documents"); return value; }),
  noteFile: (id: string) => request<{ url: string }>(`/notes/${id}/file-url`),
  deleteSubject: (id: number) => request(`/subjects/${id}`, { method: "DELETE" }).then(value => { invalidateData(); return value; }),
  createModule: (subjectId: number, number: number, title: string) => request<Module>(`/subjects/${subjectId}/modules`, { method: "POST", body: JSON.stringify({ number, title }) }).then(value => { invalidateData(); return value; }),
  renameModule: (id: number, title: string) => request<Module>(`/modules/${id}`, { method: "PUT", body: JSON.stringify({ title }) }).then(value => { invalidateData(); return value; }),
  deleteModule: (id: number) => request(`/modules/${id}`, { method: "DELETE" }).then(value => { invalidateData(); return value; }),
  createSubject: (code: string, name: string) => request<Subject>("/subjects", { method: "POST", body: JSON.stringify({ code, name }) }).then(value => { invalidateData(); return value; }),
  subjects: () => cached("subjects", () => request<Subject[]>("/subjects")),
  modules: (id: number) => cached(`modules:${id}`, () => request<Module[]>(`/subjects/${id}/modules`)),
  documents: (id: number) => cached(`documents:${id}`, () => request<Document[]>(`/modules/${id}/documents`)),
  overview: (id: number) => cached(`overview:${id}`, () => request<Overview>(`/subjects/${id}/overview`)),
  document: (id: string) => request<Document>(`/documents/${id}`),
  figure: (id: string) => request<Blob>(`/figures/${id}`, {}, true, false, true),
  preview: (id: string) => request<Blob>(`/documents/${id}/preview`, {}, true, false, true),
  slide: (id: string, number: number) => request<Slide>(`/documents/${id}/slides/${number}`),
  fileUrl: (id: string) => request<{ url: string }>(`/documents/${id}/file-url`),
  testKey: () => request<{ ok: boolean }>("/me/test-key", { method: "POST" }, true, true),
  ask: (question: string, subjectId: number, moduleId: number | null, documentId: string | null, mode: "normal" | "strict" = "normal", history: Message[] = []) =>
    request<Answer>("/ask", { method: "POST", body: JSON.stringify({
      question, subject_id: subjectId, module_id: moduleId, document_id: documentId, mode, history: history.slice(-6).map(({ role, content, sources }) => ({ role, content: content.slice(0, 2000), sources: sources?.slice(0, 5) || [] })),
    }) }, true, true).then(value => { invalidateData("usage"); return value; }),
  worksheets: (subjectId: number) => request<Worksheet[]>(`/worksheets?subject_id=${subjectId}`),
  worksheet: (id: string) => request<WorksheetDetail>(`/worksheets/${id}`),
  uploadWorksheet: (data: FormData) => request<{ id: string }>("/worksheets", { method: "POST", body: data }, true, true),
  deleteWorksheet: (id: string) => request<{ deleted: boolean }>(`/worksheets/${id}`, { method: "DELETE" }),
  worksheetMode: (id: string, mode: string) => request<{ mode: string }>(`/worksheets/${id}/mode`, { method: "POST", body: JSON.stringify({ mode }) }),
  answerWorksheet: (id: string) => request<{ queued: boolean }>(`/worksheets/${id}/answer-all`, { method: "POST" }, true, true),
  askWorksheet: (id: string, questionId: number | null, message: string) => request<{ answer: string; sources: Source[] }>(`/worksheets/${id}/ask`, { method: "POST", body: JSON.stringify({ question_id: questionId, message }) }, true, true),
  retryWorksheetQuestion: (id: string, question: number) => request<{ queued: boolean }>(`/worksheets/${id}/questions/${question}/retry`, { method: "POST" }, true, true),
  uploadQueue: () => request<QueueDocument[]>("/admin/upload-queue"),
  retryUpload: (id: string) => request<{ queued: boolean }>(`/admin/upload-queue/${id}/retry`, { method: "POST" }),
  upload: (data: FormData) => request<Document>("/documents", { method: "POST", body: data }).then(value => { invalidateData("documents"); return value; }),
  deleteDocument: (id: string) => request<{ deleted: boolean; id: string }>(`/documents/${id}`, { method: "DELETE" }).then(value => { invalidateData("documents"); return value; }),
};

export async function processNote(data: FormData, update: (message: string) => void) {
  update("Uploading file...");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 120000);
  let job: { id: string };
  try { job = await api.startNoteJob(data, controller.signal); }
  catch (error) {
    if (controller.signal.aborted) throw new ApiError("Upload timed out. Check your connection and try again.");
    throw error;
  } finally { clearTimeout(timer); }
  const deadline = Date.now() + 30 * 60 * 1000;
  while (Date.now() < deadline) {
    const statusController = new AbortController();
    const statusTimer = setTimeout(() => statusController.abort(), 30000);
    let status: NoteJob;
    try { status = await api.noteJob(job.id, statusController.signal); }
    catch (error) {
      if (statusController.signal.aborted) throw new ApiError("Status check timed out. Processing may still finish; check My Notes before retrying.");
      throw error;
    } finally { clearTimeout(statusTimer); }
    if (status.stage === "ready") { invalidateData("documents"); update("Ready"); return status.result; }
    if (status.stage === "failed") throw new ApiError(status.error || "Processing failed. Please try again.");
    update(status.stage === "indexing" ? `Indexing your note: ${status.page} of ${status.total} chunks` : `Reading handwriting${status.page ? ` - through page ${status.page}` : "..."}`);
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
  throw new ApiError("Processing is taking longer than 30 minutes. It may still finish; check My Notes before retrying.");
}

export function errorMessage(error: unknown) {
  return error instanceof ApiError ? error.message : "Something went wrong. Please try again.";
}
