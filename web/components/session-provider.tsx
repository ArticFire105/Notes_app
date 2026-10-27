/**
 * Own account, key, and chat state for the current browser tab.
 * The provider clears everything when logout or token expiry occurs.
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

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, clearSession, saveSession, setUserKey, type Message, type Profile, type Session } from "@/lib/api";

type SessionContext = {
  profile: Profile | null;
  loading: boolean;
  savedKey: string;
  histories: Record<number, Message[]>;
  signIn: (session: Session) => Promise<void>;
  logout: () => void;
  saveKey: (key: string) => void;
  appendChat: (id: number, messages: Message[]) => void;
  clearChat: (id: number) => void;
};
const Context = createContext<SessionContext | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [savedKey, setSavedKey] = useState("");
  const [histories, setHistories] = useState<Record<number, Message[]>>({});
  const logout = useCallback(() => {
    clearSession();
    void api.logout().catch(() => {});
    setProfile(null);
    setSavedKey("");
    setHistories({});
  }, []);
  useEffect(() => {
    window.addEventListener("session-expired", logout);
    return () => window.removeEventListener("session-expired", logout);
  }, [logout]);

  useEffect(() => {
    let active = true;
    async function restore() {
      try {
        await api.restore();
        const current = await api.me();
        if (active) setProfile(current);
      } catch { /* A missing or expired cookie simply shows the sign-in page. */ }
      finally { if (active) setLoading(false); }
    }
    void restore();
    return () => { active = false; };
  }, []);

  async function signIn(session: Session) {
    saveSession(session);
    try { setProfile(await api.me()); }
    catch (error) { logout(); throw error; }
  }
  function saveKey(value: string) {
    setUserKey(value);
    setSavedKey(value.trim());
  }
  const appendChat = useCallback((id: number, messages: Message[]) => {
    setHistories(previous => ({ ...previous, [id]: [...(previous[id] || []), ...messages] }));
  }, []);

  const clearChat = useCallback((id: number) => {
    setHistories(previous => ({ ...previous, [id]: [] }));
  }, []);

  return <Context.Provider value={{ profile, loading, savedKey, histories, signIn, logout, saveKey, appendChat, clearChat }}>
    {children}
  </Context.Provider>;
}

export function useSession() {
  const value = useContext(Context);
  if (!value) throw new Error("SessionProvider is required.");
  return value;
}
