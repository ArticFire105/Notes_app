/**
 * Render a consistent placeholder for later-phase learning tools.
 * No backend work is started for features outside the current phase.
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

import Link from "next/link";
import { ArrowLeft, BookMarked } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export function ComingSoon({ title, description }: { title: string; description: string }) {
  return <div className="mx-auto max-w-3xl pt-4 sm:pt-10">
    <p className="mb-2 text-xs uppercase tracking-[.2em] text-gold">A little more to look forward to</p>
    <h1 className="mb-8 font-heading text-3xl font-semibold">{title}</h1>
    <Card><CardContent className="flex flex-col items-center px-6 py-16 text-center">
      <span className="mb-6 grid size-16 place-items-center rounded-2xl bg-background"><BookMarked size={30} strokeWidth={1.2} className="text-primary" /></span>
      <span className="mb-4 rounded-full border border-gold/30 bg-gold/10 px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-primary">Coming soon</span>
      <h2 className="font-heading text-2xl">Good things are taking shape.</h2>
      <p className="mb-7 mt-3 max-w-sm text-sm leading-7 text-muted-foreground">{description}</p>
      <Button asChild variant="outline"><Link href="/"><ArrowLeft size={16} />Back to my subjects</Link></Button>
    </CardContent></Card>
  </div>;
}
