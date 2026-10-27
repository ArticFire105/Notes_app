/**
 * Exercise the real browser API client with Node's built-in test runner.
 * All responses and credentials are fake and remain in memory.
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

import test, { afterEach } from "node:test";
import assert from "node:assert/strict";
import { api, ApiError, clearSession, saveSession, setUserKey } from "../lib/api.ts";

const originalFetch = globalThis.fetch;
globalThis.window = new EventTarget();
const session = { access_token: "fake-access", refresh_token: "fake-refresh", expires_at: 9999999999 };

afterEach(() => { clearSession(); globalThis.fetch = originalFetch; });

test("scope IDs and BYOK travel only to the backend with the correct headers", async () => {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    return Response.json({ answer: "Mock answer", sources: [], remaining: 4 });
  };
  saveSession(session); setUserKey("fake-user-key");
  await api.ask("What is paging?", 1, 12, "fake-document");
  await api.usage();
  assert.equal(calls[0].url, "http://localhost:8000/ask");
  assert.equal(calls[0].init.headers.get("Authorization"), "Bearer fake-access");
  assert.equal(calls[0].init.headers.get("X-User-Api-Key"), "fake-user-key");
  assert.equal(calls[0].init.cache, "no-store");
  assert.equal(calls[0].init.redirect, "error");
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    question: "What is paging?", subject_id: 1, module_id: 12, document_id: "fake-document", mode: "normal", history: [],
  });
  assert.equal(calls[1].init.headers.has("X-User-Api-Key"), false);
});

test("public OTP requests never inherit saved credentials", async () => {
  saveSession(session); setUserKey("fake-user-key");
  globalThis.fetch = async (url, init) => {
    assert.equal(init.headers.has("Authorization"), false);
    assert.equal(init.headers.has("X-User-Api-Key"), false);
    return Response.json({ message: "Mock code sent" });
  };
  await api.sendCode("student@dxb.manipal.edu");
});

test("concurrent calls share a single refresh and use its rotated token", async () => {
  saveSession({ ...session, expires_at: 1 });
  let refreshes = 0;
  globalThis.fetch = async (url, init) => {
    if (url.endsWith("/auth/refresh")) {
      refreshes += 1;
      await new Promise(resolve => setTimeout(resolve, 10));
      return Response.json({ ...session, access_token: "fake-rotated" });
    }
    assert.equal(init.headers.get("Authorization"), "Bearer fake-rotated");
    return Response.json({});
  };
  await Promise.all([api.me(), api.usage()]);
  assert.equal(refreshes, 1);
});

test("provider diagnostics are hidden and 401 clears the session", async () => {
  saveSession(session);
  globalThis.fetch = async () => new Response("fake-sensitive-provider-message", { status: 401 });
  await assert.rejects(api.me(), error => error instanceof ApiError && error.status === 401 && !error.message.includes("fake-sensitive"));
  await assert.rejects(api.me(), /Please sign in/);
});

test("logout clears a BYOK key and rejects an older in-flight response", async () => {
  saveSession(session); setUserKey("fake-user-key");
  let finish;
  globalThis.fetch = () => new Promise(resolve => { finish = resolve; });
  const pending = api.me();
  await new Promise(resolve => setTimeout(resolve, 0));
  clearSession();
  finish(Response.json({ email: "student@dxb.manipal.edu", role: "student" }));
  await assert.rejects(pending, /session changed/);
  saveSession(session);
  globalThis.fetch = async (url, init) => {
    assert.equal(init.headers.has("X-User-Api-Key"), false);
    return Response.json({});
  };
  await api.testKey();
});

test("empty-deck upload errors are clear while other diagnostics stay hidden", async () => {
  saveSession(session);
  globalThis.fetch = async () => Response.json({ detail: "No readable text found in slides" }, { status: 400 });
  await assert.rejects(api.upload(new FormData()), error =>
    error instanceof ApiError && error.status === 400 && error.message === "No readable text found in slides");
  globalThis.fetch = async () => Response.json({ detail: "fake-private-error https://private.invalid" }, { status: 400 });
  await assert.rejects(api.upload(new FormData()), error =>
    !error.message.includes("fake-private-error") && !error.message.includes("https://"));
});

test("document deletion uses DELETE with authentication and without a BYOK key", async () => {
  saveSession(session); setUserKey("fake-user-key");
  globalThis.fetch = async (url, init) => {
    assert.equal(url, "http://localhost:8000/documents/fake-document");
    assert.equal(init.method, "DELETE");
    assert.equal(init.headers.get("Authorization"), "Bearer fake-access");
    assert.equal(init.headers.has("X-User-Api-Key"), false);
    return Response.json({ deleted: true, id: "fake-document" });
  };
  assert.deepEqual(await api.deleteDocument("fake-document"), { deleted: true, id: "fake-document" });
});

test("safe deletion failures are visible but arbitrary diagnostics remain hidden", async () => {
  saveSession(session);
  const reason = "Could not complete document deletion. Please retry or check backend logs.";
  globalThis.fetch = async () => Response.json({ detail: reason }, { status: 503 });
  await assert.rejects(api.deleteDocument("fake-document"), error => error.message === reason);
  globalThis.fetch = async () => Response.json({ detail: "fake-secret-storage-diagnostic" }, { status: 503 });
  await assert.rejects(api.deleteDocument("fake-document"), error => !error.message.includes("fake-secret"));
});


test("restore uses cookie credentials and strict mode is sent to the backend", async () => {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    if (url.endsWith("/auth/refresh")) return Response.json({ access_token: "fake-access", expires_at: 9999999999 });
    return Response.json({ answer: "Answer [1]", sources: [], remaining: 4 });
  };
  await api.restore();
  await api.ask("Explain", 1, null, null, "strict");
  assert.equal(calls[0].init.credentials, "include");
  assert.equal(calls[0].init.headers.get("X-Browser-Session"), "1");
  assert.equal(calls[0].init.body, undefined);
  assert.equal(JSON.parse(calls[1].init.body).mode, "strict");
});


test("subject data is shared across navigation and invalidated after changes", async () => {
  saveSession(session);
  let reads = 0;
  globalThis.fetch = async (url, init) => {
    if (url.endsWith("/overview")) { reads++; return Response.json({}); }
    return Response.json({ deleted: true });
  };
  await Promise.all([api.overview(1), api.overview(1)]);
  await api.overview(1);
  assert.equal(reads, 1);
  await api.deleteDocument("fake-document");
  await api.overview(1);
  assert.equal(reads, 2);
});


test("follow-up sends recent text without source metadata", async () => {
  saveSession(session);
  globalThis.fetch = async (url, init) => {
    const body = JSON.parse(init.body);
    assert.deepEqual(body.history, [{ role: "user", content: "What is paging?", sources: [] }]);
    return Response.json({ answer: "Answer", sources: [], remaining: 4 });
  };
  await api.ask("Explain it", 1, null, null, "strict", [{ role: "user", content: "What is paging?", sources: [] }]);
});


test("slide viewer requests the cited slide with authorization", async () => {
  saveSession(session);
  globalThis.fetch = async (url, init) => {
    assert.ok(url.endsWith("/documents/doc-1/slides/5"));
    assert.equal(init.headers.get("Authorization"), "Bearer fake-access");
    return Response.json({ number: 5, total: 8, aspect: 1.7, shapes: [] });
  };
  assert.equal((await api.slide("doc-1", 5)).number, 5);
});


test("assistant sources travel with the follow-up", async () => {
  saveSession(session);
  const source = { n: 1, document_id: "00000000-0000-0000-0000-000000000001", document: "Notes", module: 1, page: 5, score: 0.9 };
  globalThis.fetch = async (url, init) => {
    assert.deepEqual(JSON.parse(init.body).history[0].sources, [source]);
    return Response.json({ answer: "Simple", sources: [source], remaining: 3 });
  };
  await api.ask("Explain it more simply", 1, null, null, "normal", [{ role: "assistant", content: "Earlier answer [1]", sources: [source] }]);
});


test("PowerPoint preview returns a PDF blob", async () => {
  saveSession(session);
  globalThis.fetch = async (url, init) => {
    assert.ok(url.endsWith("/documents/doc-1/preview"));
    assert.equal(init.headers.get("Authorization"), "Bearer fake-access");
    return new Response("%PDF-test", { headers: { "Content-Type": "application/pdf" } });
  };
  assert.equal(await (await api.preview("doc-1")).text(), "%PDF-test");
});


test("admin adds a subject and invalidates the subjects cache", async () => {
  saveSession(session);
  let reads = 0;
  globalThis.fetch = async (url, init) => {
    if (init.method === "POST") {
      assert.deepEqual(JSON.parse(init.body), { code: "AI", name: "Artificial Intelligence" });
      return Response.json({ id: 9, code: "AI", name: "Artificial Intelligence" });
    }
    reads++;
    return Response.json([]);
  };
  await api.subjects();
  await api.createSubject("AI", "Artificial Intelligence");
  await api.subjects();
  assert.equal(reads, 2);
});


test("note upload job preserves the explicitly selected subject", async () => {
  saveSession(session);
  globalThis.fetch = async (url, init) => {
    assert.ok(url.endsWith("/notes/jobs"));
    assert.equal(init.body.get("subject_id"), "4");
    assert.equal(init.body.get("replace"), "false");
    return Response.json({ id: "job" }, { status: 202 });
  };
  const data = new FormData();
  data.set("subject_id", "4"); data.set("replace", "false");
  data.set("file", new Blob(["image"], { type: "image/png" }), "note.png");
  assert.equal((await api.startNoteJob(data)).id, "job");
});


test("module and subject management send authenticated requests", async () => {
  saveSession(session);
  const calls = [];
  globalThis.fetch = async (url, init) => { calls.push({ url, init }); return Response.json({ id: 12, subject_id: 4, number: 6, title: "Threads" }); };
  await api.createModule(4, 6, "Threads");
  await api.renameModule(12, "Scheduling");
  await api.deleteModule(12);
  await api.deleteSubject(4);
  assert.deepEqual(calls.map(call => call.init.method), ["POST", "PUT", "DELETE", "DELETE"]);
  assert.ok(calls.every(call => call.init.headers.get("Authorization") === "Bearer fake-access"));
  assert.deepEqual(JSON.parse(calls[0].init.body), { number: 6, title: "Threads" });
});
