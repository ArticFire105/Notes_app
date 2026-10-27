/**
 * Render college email login with 6–8 digit OTP verification.
 * A failed resend leaves the previous email and code form intact.
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

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, BookOpen, GraduationCap, ShieldCheck } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useSession } from "@/components/session-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

export default function LoginPage() {
  const router = useRouter();
  const { signIn } = useSession();
  const [email, setEmail] = useState("");
  const [sentEmail, setSentEmail] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function sendCode(event: React.FormEvent) {
    event.preventDefault();
    const normalized = email.trim().toLowerCase();
    if (!/^[^@\s]+@dxb\.manipal\.edu$/.test(normalized)) {
      setError("Use your @dxb.manipal.edu college email address.");
      return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      await api.sendCode(normalized);
      // Commit the target only after success, preserving the old OTP form on resend failure.
      setSentEmail(normalized);
      setNotice("Code sent. Check your college inbox, including spam.");
    } catch (error) { setError(errorMessage(error)); }
    finally { setBusy(false); }
  }

  async function verify(event: React.FormEvent) {
    event.preventDefault();
    if (!/^[0-9]{6,8}$/.test(code.trim())) {
      setError("Enter the 6–8 digit code from your email."); return;
    }
    setBusy(true); setError("");
    try {
      await signIn(await api.verifyCode(sentEmail, code.trim()));
      setCode("");
      router.replace("/");
    } catch (error) { setError(errorMessage(error)); }
    finally { setBusy(false); }
  }

  return <main className="grid min-h-screen lg:grid-cols-2">
    <section className="relative hidden flex-col justify-between overflow-hidden bg-primary p-12 text-white lg:flex xl:p-20">
      <div className="flex items-center gap-3"><GraduationCap size={36} /><span className="font-heading text-2xl">Lecture Notes</span></div>
      <div className="relative z-10 max-w-lg">
        <p className="mb-6 text-xs uppercase tracking-[.3em] text-[#dfc975]">Manipal Dubai · Computer Science</p>
        <h1 className="font-heading text-5xl leading-[1.16] xl:text-6xl">A little clarity.<br />A world of<br /><span className="text-[#dfc975]">possibilities.</span></h1>
        <p className="mt-8 max-w-sm text-base leading-7 text-white/70">Your course notes, thoughtfully organised. Find the answer, follow the source, and make every study session count.</p>
        <div className="mt-10 flex gap-3 text-sm text-white/75"><BookOpen size={20} className="text-[#dfc975]" />Learn from the notes you know.</div>
      </div>
      <p className="relative z-10 text-xs text-white/45">A learning space for the CSE community.</p>
      <div aria-hidden className="absolute -bottom-40 -right-36 size-[560px] rounded-full border border-white/10" />
      <div aria-hidden className="absolute -bottom-20 -right-16 size-[400px] rounded-full border border-white/10" />
    </section>
    <section className="flex items-center justify-center px-5 py-12 sm:px-12">
      <div className="w-full max-w-md">
        <div className="mb-8 flex items-center justify-center gap-3 text-primary lg:hidden"><GraduationCap size={30} /><span className="font-heading text-2xl">Lecture Notes</span></div>
        <Card className="shadow-[0_8px_40px_#1e3a5f08]">
          <CardHeader className="px-8 pb-5 pt-8"><p className="text-xs font-semibold uppercase tracking-[.2em] text-gold">Welcome to your workspace</p><CardTitle className="text-3xl">Good to have you here.</CardTitle><CardDescription>Sign in with your college email to get started.</CardDescription></CardHeader>
          <CardContent className="space-y-5 px-8 pb-8">
            {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p>}
            {notice && <p role="status" className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</p>}
            <form onSubmit={sendCode} className="space-y-3">
              <label htmlFor="email">College email</label>
              <Input id="email" type="email" autoComplete="email" placeholder="you@dxb.manipal.edu" required value={email} onChange={event => setEmail(event.target.value)} disabled={busy} />
              <Button className="w-full" disabled={busy}>{busy ? "Please wait…" : sentEmail ? "Resend code" : "Send sign-in code"}<ArrowRight size={16} /></Button>
            </form>
            {sentEmail && <form onSubmit={verify} className="space-y-3 border-t border-border pt-5">
              <label htmlFor="code">Email verification code</label>
              <p className="break-all text-xs text-muted-foreground">Enter the 6–8 digit code sent to {sentEmail}.</p>
              <Input id="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6,8}" minLength={6} maxLength={8} required value={code} onChange={event => setCode(event.target.value)} className="tracking-[.3em]" disabled={busy} />
              <Button className="w-full" disabled={busy}>Verify & enter portal<ArrowRight size={16} /></Button>
            </form>}
            <div className="flex items-start gap-2 text-xs leading-5 text-muted-foreground"><ShieldCheck size={17} className="mt-0.5 shrink-0" /><span>No password needed.</span></div>
          </CardContent>
        </Card>
        <p className="mt-6 text-center text-xs text-muted-foreground">For students with a @dxb.manipal.edu email.</p>
      </div>
    </section>
  </main>;
}
