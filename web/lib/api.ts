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
export type Document = { id: string; title: string; module: number | null; status: "processing" | "ready" | "failed"; page_count: number | null; file_type: "pdf" | "pptx"; error?: string | null };
export type Overview = { subject: Subject; modules: Module[]; documents: (Document & { module_id: number })[]; usage: Usage };
export type Usage = { used: number; limit: number; resets_at: string };
export type Slide = { number: number; total: number; aspect: number; shapes: { kind: "text" | "image"; left: number; top: number; width: number; height: number; text?: string; data?: string; mime?: string }[] };
export type Source = { document_id?: string | null; n: number; document: string; module: number | null; page: number; page_label?: string | null; score: number };
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
    if (path.endsWith("/preview") && response.status === 503) throw new ApiError("PowerPoint preview requires LibreOffice on the backend, or conversion failed.", 503);
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
  subjects: () => cached("subjects", () => request<Subject[]>("/subjects")),
  modules: (id: number) => cached(`modules:${id}`, () => request<Module[]>(`/subjects/${id}/modules`)),
  documents: (id: number) => cached(`documents:${id}`, () => request<Document[]>(`/modules/${id}/documents`)),
  overview: (id: number) => cached(`overview:${id}`, () => request<Overview>(`/subjects/${id}/overview`)),
  document: (id: string) => request<Document>(`/documents/${id}`),
  preview: (id: string) => request<Blob>(`/documents/${id}/preview`, {}, true, false, true),
  slide: (id: string, number: number) => request<Slide>(`/documents/${id}/slides/${number}`),
  fileUrl: (id: string) => request<{ url: string }>(`/documents/${id}/file-url`),
  testKey: () => request<{ ok: boolean }>("/me/test-key", { method: "POST" }, true, true),
  ask: (question: string, subjectId: number, moduleId: number | null, documentId: string | null, mode: "normal" | "strict" = "normal", history: Message[] = []) =>
    request<Answer>("/ask", { method: "POST", body: JSON.stringify({
      question, subject_id: subjectId, module_id: moduleId, document_id: documentId, mode, history: history.slice(-6).map(({ role, content, sources }) => ({ role, content: content.slice(0, 2000), sources: sources?.slice(0, 5) || [] })),
    }) }, true, true).then(value => { invalidateData("usage"); return value; }),
  upload: (data: FormData) => request<Document>("/documents", { method: "POST", body: data }).then(value => { invalidateData("documents"); return value; }),
  deleteDocument: (id: string) => request<{ deleted: boolean; id: string }>(`/documents/${id}`, { method: "DELETE" }).then(value => { invalidateData("documents"); return value; }),
};

export function errorMessage(error: unknown) {
  return error instanceof ApiError ? error.message : "Something went wrong. Please try again.";
}
