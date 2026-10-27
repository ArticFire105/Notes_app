/**
 * Manage usage and an explicitly saved session-only Google key.
 * Key testing uses the saved key through the FastAPI backend.
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
import { KeyRound, ShieldCheck, ExternalLink, Check, Trash2 } from "lucide-react";
import { api, errorMessage, type Usage } from "@/lib/api";
import { useSession } from "@/components/session-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function SettingsPage() {
  const { savedKey, saveKey } = useSession();
  const [draft, setDraft] = useState(savedKey);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    api.usage().then(value => { if (active) setUsage(value); }).catch(error => { if (active) setError(errorMessage(error)); });
    return () => { active = false; };
  }, []);

  function save(event: React.FormEvent) {
    event.preventDefault();
    if (!draft.trim() || /\s/.test(draft.trim())) { setError("Paste a nonempty key without spaces."); return; }
    saveKey(draft.trim()); setDraft(draft.trim()); setError("");
    setNotice("Key saved for this tab's session.");
  }
  async function test() {
    setBusy(true); setNotice(""); setError("");
    try { await api.testKey(); setNotice("Your saved key works. You can use it for questions."); }
    catch (error) { setError(errorMessage(error)); }
    finally { setBusy(false); }
  }
  return <div className="mx-auto max-w-3xl space-y-7">
    <div><p className="mb-2 text-xs uppercase tracking-[.2em] text-gold">Make yourself at home</p><h1 className="font-heading text-3xl font-semibold">Settings</h1><p className="mt-3 text-sm text-muted-foreground">Your daily allowance and a little extra room to explore.</p></div>
    {error && <p role="alert" className="rounded-lg bg-red-50 p-4 text-sm text-red-800">{error}</p>}
    {notice && <p role="status" className="rounded-lg bg-emerald-50 p-4 text-sm text-emerald-800">{notice}</p>}
    <Card><CardHeader><CardTitle>Today's allowance</CardTitle><CardDescription>Shared-key questions reset each day at midnight in Dubai.</CardDescription></CardHeader><CardContent>{usage ? <><div className="mb-4 flex items-baseline gap-2"><span className="font-heading text-4xl text-primary">{Math.max(0, usage.limit - usage.used)}</span><span className="text-sm text-muted-foreground">of {usage.limit} questions remaining</span></div><progress className="h-2 w-full overflow-hidden rounded-full accent-primary" value={Math.min(usage.used, usage.limit)} max={usage.limit} aria-label="Daily questions used" /><p className="mt-3 text-xs text-muted-foreground">{usage.used} used · Resets {new Date(usage.resets_at).toLocaleString(undefined, { timeZone: "Asia/Dubai" })} (Dubai)</p></> : <p role="status" className="text-sm text-muted-foreground">Loading usage…</p>}</CardContent></Card>
    <Card><CardHeader><div className="mb-2 flex items-center justify-between gap-2"><KeyRound className="text-gold" size={23} />{savedKey && <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-3 py-1 text-xs text-emerald-800"><Check size={12} />Key saved</span>}</div><CardTitle>Keep the questions coming.</CardTitle><CardDescription>Use your own Google AI Studio key when you reach the shared allowance.</CardDescription></CardHeader><CardContent className="space-y-5">
      <div className="rounded-xl bg-background p-4 text-sm leading-7"><a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-semibold underline">Get a key in Google AI Studio<ExternalLink size={13} /></a><p className="text-xs text-muted-foreground">Sign in → Create API key → paste below → Save key.</p></div>
      <form onSubmit={save} className="space-y-3"><label htmlFor="key">Your Google AI Studio key</label><Input id="key" type="password" autoComplete="off" spellCheck={false} placeholder="Paste your key here" value={draft} onChange={event => setDraft(event.target.value)} disabled={busy} /><div className="flex flex-wrap gap-2"><Button disabled={busy || !draft.trim()}>Save key</Button><Button type="button" variant="outline" disabled={busy || !savedKey} onClick={() => void test()}>{busy ? "Testing…" : "Test key"}</Button><Button type="button" variant="ghost" disabled={busy || (!savedKey && !draft)} onClick={() => { saveKey(""); setDraft(""); setError(""); setNotice("Your key has been removed."); }}><Trash2 size={15} />Remove</Button></div><p className="text-xs text-muted-foreground">Test key checks the saved key and makes a small provider call.</p></form>
      <div className="flex gap-3 rounded-lg border border-border p-4"><ShieldCheck size={20} className="shrink-0 text-primary" /><p className="text-xs leading-6 text-muted-foreground">Your key stays in memory in this tab. Refreshing, closing the tab, or logging out clears it. It is sent only to FastAPI with your question or key test.</p></div>
      <p className="text-xs leading-6 text-muted-foreground">Free AI Studio keys: Google may use your content to improve its products. Don't upload personal info. <a href="https://ai.google.dev/gemini-api/terms" target="_blank" rel="noopener noreferrer" className="underline">Read Google's terms.</a></p>
      <p className="border-t border-border pt-4 text-xs text-muted-foreground">Other providers: coming later.</p>
    </CardContent></Card>
  </div>;
}
