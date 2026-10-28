/**
 * Show subject cards with real module counts from FastAPI.
 * Colour covers give the home screen a quiet university LMS identity.
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
import { useEffect, useState } from "react";
import { ArrowUpRight, BookOpen, Layers, Sparkles, Cpu, Globe, Shield, Briefcase, Code } from "lucide-react";
import { api, errorMessage, type Subject } from "@/lib/api";
import { useSession } from "@/components/session-provider";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const covers: Record<string, { color: string; icon: typeof Cpu; tag: string }> = {
  OS: { color: "#294b62", icon: Cpu, tag: "SYSTEMS & COMPUTING" },
  SE: { color: "#637366", icon: Code, tag: "DESIGN & DEVELOPMENT" },
  POC: { color: "#796349", icon: Shield, tag: "SECURITY & CRYPTOGRAPHY" },
  CN: { color: "#526780", icon: Globe, tag: "NETWORKS & CONNECTIONS" },
  EOM: { color: "#80605e", icon: Briefcase, tag: "PEOPLE & ORGANISATIONS" },
};

export default function HomePage() {
  const { profile } = useSession();
  const [subjects, setSubjects] = useState<(Subject & { count: number })[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const list = await api.subjects();
        const cards = await Promise.all(list.map(async subject => ({ ...subject, count: (await api.modules(subject.id)).length })));
        if (active) setSubjects(cards);
      } catch (error) { if (active) setError(errorMessage(error)); }
      finally { if (active) setLoading(false); }
    }
    void load();
    return () => { active = false; };
  }, []);
  return <div className="mx-auto max-w-6xl space-y-9">
    <div><p className="mb-2 text-xs font-medium uppercase tracking-[.18em] text-muted-foreground">Your learning, in one place</p><h1 className="font-heading text-3xl font-semibold sm:text-4xl">Welcome back{profile?.role === "admin" ? ", educator" : ""}.</h1><p className="mt-3 text-sm leading-6 text-muted-foreground">A fresh perspective starts with a good question. What will you explore today?</p></div>
    <section className="relative overflow-hidden rounded-2xl bg-primary px-7 py-8 text-white sm:px-9">
      <div className="relative z-10 max-w-xl"><span className="mb-4 inline-flex items-center gap-2 text-xs text-[#e3cd7c]"><Sparkles size={16} />A little help, grounded in your notes</span><h2 className="font-heading text-2xl sm:text-3xl">Less searching. More understanding.</h2><p className="mt-3 max-w-lg text-sm leading-6 text-white/70">Open a subject, choose your notes, and ask away. Every answer points you back to the page it came from.</p></div>
      <BookOpen aria-hidden size={150} strokeWidth={0.7} className="absolute -bottom-4 right-5 -rotate-12 text-white/10 sm:right-10" />
    </section>
    <section>
      <div className="mb-5 flex items-end justify-between gap-3"><div><p className="mb-1 text-[10px] font-semibold uppercase tracking-[.2em] text-gold">Your curriculum</p><h2 className="font-heading text-2xl font-semibold">My subjects</h2></div><span className="rounded-full border border-border bg-white/60 px-3 py-1 text-xs text-muted-foreground">{loading ? "Loading…" : `${subjects.length} subjects`}</span></div>
      {error && <div role="alert" className="rounded-lg bg-red-50 p-4 text-sm text-red-800">{error}<Button variant="outline" size="sm" className="ml-3" onClick={() => window.location.reload()}>Return to login</Button></div>}
      {loading ? <div role="status" className="grid gap-6 sm:grid-cols-2 xl:grid-cols-3">{[1, 2, 3, 4, 5].map(id => <div key={id} className="h-64 animate-pulse rounded-2xl bg-white/70" />)}<span className="sr-only">Loading subjects</span></div> :
        <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-3">{subjects.map(subject => {
          const cover = covers[subject.code] || covers.OS;
          const Icon = cover.icon;
          return <Link href={`/subjects/${subject.id}`} key={subject.id} className="group rounded-2xl">
            <Card className="h-full overflow-hidden transition-all duration-200 group-hover:-translate-y-1 group-hover:shadow-lg">
              <div className="course-cover flex h-32 items-center justify-between px-6 text-white" style={{ backgroundColor: cover.color }}><div className="relative z-10"><p className="mb-2 text-[9px] tracking-[.17em] text-white/65">{cover.tag}</p><span className="font-heading text-3xl font-medium">{subject.code}</span></div><Icon aria-hidden size={46} strokeWidth={1} className="relative z-10 text-white/65" /></div>
              <CardContent className="pt-5"><h3 className="min-h-12 font-heading text-xl font-semibold">{subject.name}</h3><div className="mt-5 flex items-center justify-between border-t border-border pt-4"><span className="flex items-center gap-2 text-xs text-muted-foreground"><Layers size={14} />{subject.count} modules</span><span className="flex items-center gap-1 text-xs font-semibold text-primary">Explore<ArrowUpRight size={16} /></span></div></CardContent>
            </Card>
          </Link>;
        })}</div>}
      {!loading && !error && subjects.length === 0 && <p className="text-sm text-muted-foreground">No subjects yet. Ask your administrator to complete the subject setup.</p>}
    </section>
    <div className="flex items-start gap-3 border-t border-border pt-6 text-sm text-muted-foreground"><span className="mt-0.5 size-2 shrink-0 rounded-full bg-gold" /><p>One subject at a time. Choose a module to keep your answers focused, or explore the whole subject.</p></div>
  </div>;
}
