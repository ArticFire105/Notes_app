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
    question: "What is paging?", subject_id: 1, module_id: 12, document_id: "fake-document", mode: "normal",
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
