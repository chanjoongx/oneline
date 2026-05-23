"use client";

// Client hook that runs a request and consumes the SSE stream so the dashboard
// updates live. It also keeps the knowledge base in localStorage so the learning
// loop is visible across requests: lessons accumulate and the repeat-failures
// metric grows on every subsequent run.

import { useCallback, useEffect, useRef, useState } from "react";
import type { CandidateView, Phase, RunEvent } from "./events";
import type {
  CandidateId,
  Deployment,
  Lesson,
  Plan,
  RetrievedLessonItem,
  Selection,
} from "./types";

export type RunStatus =
  | "idle"
  | "running"
  | "rejected"
  | "no_winner"
  | "deployed"
  | "error";

export interface RunState {
  status: RunStatus;
  phase: Phase;
  need: string;
  plan?: Plan;
  rejection?: { reason: string | null; alternative: string | null };
  retrieved: RetrievedLessonItem[];
  candidates: Partial<Record<CandidateId, CandidateView>>;
  selection?: Selection;
  noWinnerReason?: string | null;
  deployment?: Deployment;
  lessonsAdded: string[];
  prevented: string[];
  error?: string;
}

export interface KbState {
  lessons: Lesson[];
  runs: number;
  totalPrevented: number;
}

const LS_LESSONS = "oneline.kb.lessons";
const LS_RUNS = "oneline.kb.runs";
const LS_PREVENTED = "oneline.kb.prevented";

function emptyRun(need: string): RunState {
  return {
    status: "running",
    phase: "planning",
    need,
    retrieved: [],
    candidates: {},
    lessonsAdded: [],
    prevented: [],
  };
}

function loadKb(): KbState {
  if (typeof window === "undefined") {
    return { lessons: [], runs: 0, totalPrevented: 0 };
  }
  let lessons: Lesson[] = [];
  try {
    const raw = window.localStorage.getItem(LS_LESSONS);
    if (raw) lessons = JSON.parse(raw);
  } catch {
    lessons = [];
  }
  const runs = parseInt(window.localStorage.getItem(LS_RUNS) || "0", 10) || 0;
  const totalPrevented =
    parseInt(window.localStorage.getItem(LS_PREVENTED) || "0", 10) || 0;
  return { lessons, runs, totalPrevented };
}

function saveKb(kb: KbState): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LS_LESSONS, JSON.stringify(kb.lessons));
    window.localStorage.setItem(LS_RUNS, String(kb.runs));
    window.localStorage.setItem(LS_PREVENTED, String(kb.totalPrevented));
  } catch {
    // storage full or blocked; the dashboard still works in memory
  }
}

// Parse a Server-Sent Events buffer into discrete data payloads.
function parseEvents(buffer: string): { events: RunEvent[]; rest: string } {
  const events: RunEvent[] = [];
  const blocks = buffer.split("\n\n");
  const rest = blocks.pop() ?? "";
  for (const block of blocks) {
    const dataLine = block
      .split("\n")
      .find((l) => l.startsWith("data:"));
    if (!dataLine) continue;
    const json = dataLine.slice(5).trim();
    if (!json) continue;
    try {
      events.push(JSON.parse(json) as RunEvent);
    } catch {
      // partial or malformed; skip
    }
  }
  return { events, rest };
}

export function useRun() {
  const [state, setState] = useState<RunState>({
    status: "idle",
    phase: "idle",
    need: "",
    retrieved: [],
    candidates: {},
    lessonsAdded: [],
    prevented: [],
  });
  const [kb, setKb] = useState<KbState>({ lessons: [], runs: 0, totalPrevented: 0 });
  const kbRef = useRef<KbState>(kb);
  kbRef.current = kb;
  const runningRef = useRef(false);

  // Load persisted KB, seeding from the shared knowledge base on first visit.
  useEffect(() => {
    const local = loadKb();
    if (local.lessons.length > 0 || local.runs > 0) {
      setKb(local);
      return;
    }
    let cancelled = false;
    fetch("/api/kb")
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return;
        const seeded: KbState = {
          lessons: Array.isArray(data?.lessons) ? data.lessons : [],
          runs: 0,
          totalPrevented: 0,
        };
        setKb(seeded);
        saveKb(seeded);
      })
      .catch(() => {
        // keep empty; the panel still renders
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const apply = useCallback((event: RunEvent) => {
    setState((prev) => {
      switch (event.type) {
        case "phase":
          return { ...prev, phase: event.phase };
        case "plan": {
          const candidates: Partial<Record<CandidateId, CandidateView>> = {};
          for (const s of event.plan.candidate_strategies) {
            candidates[s.id] = { candidate_id: s.id, status: "queued" };
          }
          return { ...prev, plan: event.plan, candidates };
        }
        case "rejected":
          return {
            ...prev,
            status: "rejected",
            rejection: {
              reason: event.rejection_reason,
              alternative: event.suggested_alternative,
            },
          };
        case "retrieved":
          return { ...prev, retrieved: event.retrieved_lessons };
        case "candidate": {
          const existing = prev.candidates[event.candidate_id] || {
            candidate_id: event.candidate_id,
            status: "queued",
          };
          const next: CandidateView = {
            ...existing,
            status: event.status,
            candidate: event.candidate ?? existing.candidate,
            is_winner: event.status === "winner" ? true : existing.is_winner,
          };
          return {
            ...prev,
            candidates: { ...prev.candidates, [event.candidate_id]: next },
          };
        }
        case "judge": {
          const existing = prev.candidates[event.candidate_id] || {
            candidate_id: event.candidate_id,
            status: "judging",
          };
          const s = event.scores;
          const final_score =
            0.4 * s.functionality_score +
            0.35 * s.ux_clarity_score +
            0.25 * s.design_coherence_score;
          return {
            ...prev,
            candidates: {
              ...prev.candidates,
              [event.candidate_id]: {
                ...existing,
                scores: s,
                final_score: Math.round(final_score * 100) / 100,
              },
            },
          };
        }
        case "selection":
          return { ...prev, selection: event.selection };
        case "no_winner":
          return { ...prev, status: "no_winner", noWinnerReason: event.reason };
        case "lessons":
          return {
            ...prev,
            lessonsAdded: event.lessons_added,
            prevented: event.prevented_repeats,
          };
        case "deployment":
          return { ...prev, deployment: event.deployment };
        case "error":
          return { ...prev, status: "error", error: event.message };
        case "done":
          return {
            ...prev,
            phase: "done",
            status:
              prev.status === "rejected" ||
              prev.status === "no_winner" ||
              prev.status === "error"
                ? prev.status
                : "deployed",
          };
        default:
          return prev;
      }
    });

    // Knowledge base growth is committed when the lessons event arrives.
    if (event.type === "lessons") {
      setKb((prevKb) => {
        const next: KbState = {
          lessons: event.lessons.length ? event.lessons : prevKb.lessons,
          runs: prevKb.runs + 1,
          totalPrevented: prevKb.totalPrevented + event.prevented_repeats.length,
        };
        saveKb(next);
        return next;
      });
    }
  }, []);

  const start = useCallback(
    async (need: string) => {
      if (runningRef.current) return;
      runningRef.current = true;
      setState(emptyRun(need));
      try {
        const res = await fetch("/api/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ need, sessionLessons: kbRef.current.lessons }),
        });
        if (!res.body) throw new Error("no response stream");
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const { events, rest } = parseEvents(buffer);
          buffer = rest;
          for (const ev of events) apply(ev);
        }
        // flush any trailing event
        const { events } = parseEvents(buffer + "\n\n");
        for (const ev of events) apply(ev);
      } catch (e) {
        setState((prev) => ({ ...prev, status: "error", error: String(e) }));
      } finally {
        runningRef.current = false;
      }
    },
    [apply]
  );

  const reset = useCallback(() => {
    setState({
      status: "idle",
      phase: "idle",
      need: "",
      retrieved: [],
      candidates: {},
      lessonsAdded: [],
      prevented: [],
    });
  }, []);

  const clearKb = useCallback(() => {
    const cleared: KbState = { lessons: [], runs: 0, totalPrevented: 0 };
    setKb(cleared);
    saveKb(cleared);
    fetch("/api/kb")
      .then((r) => r.json())
      .then((data) => {
        const seeded: KbState = {
          lessons: Array.isArray(data?.lessons) ? data.lessons : [],
          runs: 0,
          totalPrevented: 0,
        };
        setKb(seeded);
        saveKb(seeded);
      })
      .catch(() => {});
  }, []);

  return { state, kb, start, reset, clearKb };
}
