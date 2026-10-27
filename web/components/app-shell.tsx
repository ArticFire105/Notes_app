/**
 * Render the shared LMS header, sidebar, and mobile navigation.
 * Protected screens render only after the backend confirms the profile.
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
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { BookOpen, GraduationCap, LayoutGrid, NotebookPen, Files, ListChecks, Settings, Upload, LogOut, Menu, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSession } from "@/components/session-provider";
import { cn } from "@/lib/utils";

const links = [
  { href: "/", label: "My subjects", icon: LayoutGrid },
  { href: "/my-notes", label: "My Notes", icon: NotebookPen },
  { href: "/past-papers", label: "Past Papers", icon: Files },
  { href: "/quiz", label: "Quiz", icon: ListChecks },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { profile, loading, logout } = useSession();
  const [menuOpen, setMenuOpen] = useState(false);
  const loginPage = pathname === "/login";
  useEffect(() => {
    if (loading) return;
    if (!profile && !loginPage) router.replace("/login");
    if (profile && loginPage) router.replace("/");
  }, [profile, loading, loginPage, router]);
  useEffect(() => { setMenuOpen(false); }, [pathname]);
  if (loading) return <div className="grid min-h-screen place-items-center text-muted-foreground" role="status">Loading?</div>;
  if (loginPage) return <>{children}</>;
  if (!profile) return <div className="grid min-h-screen place-items-center text-muted-foreground" role="status">Opening your learning portal…</div>;
  const navigation = profile.role === "admin"
    ? [...links, { href: "/admin/upload", label: "Admin upload", icon: Upload }]
    : links;

  return <div className="min-h-screen">
    <header className="sticky top-0 z-30 border-b border-white/10 bg-primary text-white shadow-sm">
      <div className="flex h-20 items-center justify-between gap-4 px-5 md:px-8">
        <Link href="/" className="flex items-center gap-3" aria-label="Lecture Notes home">
          <span className="grid size-11 place-items-center rounded-xl border border-white/20 bg-white/10"><GraduationCap size={27} /></span>
          <span><span className="block font-heading text-xl font-semibold tracking-wide">Lecture Notes</span><span className="block text-[10px] uppercase tracking-[.2em] text-white/65">Manipal Dubai · CSE</span></span>
        </Link>
        <div className="flex items-center gap-3">
          
          <span className="grid size-10 place-items-center rounded-full bg-[#dfd3b6] text-sm font-semibold text-primary" title={profile.email}>{profile.email.slice(0, 2).toUpperCase()}</span>
          <button className="rounded-lg p-2 focus-visible:outline-2 focus-visible:outline-white md:hidden" onClick={() => setMenuOpen(!menuOpen)} aria-expanded={menuOpen} aria-controls="portal-navigation" aria-label={menuOpen ? "Close navigation" : "Open navigation"}>{menuOpen ? <X /> : <Menu />}</button>
        </div>
      </div>
    </header>
    <div className="mx-auto flex max-w-[1600px]">
      <aside id="portal-navigation" className={cn("fixed bottom-0 left-0 top-20 z-20 w-64 border-r border-border bg-[#fcfaf6] p-5 md:sticky md:top-20 md:block md:h-[calc(100vh-5rem)] md:shrink-0", menuOpen ? "block shadow-xl" : "hidden")}>
        <p className="mb-4 mt-3 px-3 text-[10px] font-semibold uppercase tracking-[.22em] text-muted-foreground">Your workspace</p>
        <nav aria-label="Main navigation" className="space-y-1">
          {navigation.map(item => {
            const active = item.href === "/" ? pathname === "/" || pathname.startsWith("/subjects/") : pathname === item.href;
            return <Link key={item.href} href={item.href} aria-current={active ? "page" : undefined} className={cn("flex items-center gap-3 rounded-lg px-3 py-3 text-sm transition-colors hover:bg-primary/5", active ? "bg-primary/8 font-semibold text-primary" : "text-muted-foreground")}><item.icon size={18} />{item.label}{active && <span className="ml-auto size-1.5 rounded-full bg-gold" />}</Link>;
          })}
        </nav>
        <div className="absolute bottom-5 left-5 right-5 border-t border-border pt-5">
          
          <p className="mb-2 truncate text-xs text-muted-foreground" title={profile.email}>{profile.email}</p>
          <Button variant="ghost" size="sm" className="w-full justify-start" onClick={() => { logout(); router.replace("/login"); }}><LogOut size={16} />Log out</Button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 p-5 pb-12 sm:p-8 lg:p-10">{children}</main>
    </div>
  </div>;
}
