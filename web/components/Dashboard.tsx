"use client";

import { useState } from "react";
import { useRun } from "@/lib/useRun";
import CandidateColumns from "./CandidateColumns";
import KnowledgePanel from "./KnowledgePanel";
import PhaseStrip from "./PhaseStrip";
import ResultArea from "./ResultArea";

const SUGGESTIONS = [
  "interval timer with four one minute rounds",
  "Korean flashcards for this week's words",
  "decide what to eat for dinner",
  "water intake tracker for today",
  "packing checklist for a weekend trip",
];

export default function Dashboard() {
  const { state, kb, start, clearKb } = useRun();
  const [need, setNeed] = useState("");
  const running = state.status === "running";

  const submit = (value: string) => {
    const text = value.trim();
    if (!text || running) return;
    start(text);
  };

  const winner = state.selection?.winner ?? null;
  const strategies = state.plan?.candidate_strategies ?? [];

  return (
    <div className="db-shell">
      <header className="db-header">
        <div className="db-brand">
          <span className="db-logo">Oneline</span>
          <span className="db-tag">software for one</span>
        </div>
        <form
          className="db-need"
          onSubmit={(e) => {
            e.preventDefault();
            submit(need);
          }}
        >
          <input
            className="db-input"
            value={need}
            onChange={(e) => setNeed(e.target.value)}
            placeholder="Describe a tool you need"
            aria-label="Describe a tool you need"
            autoFocus
          />
          <button className="db-build" type="submit" disabled={running || !need.trim()}>
            {running ? "Building" : "Build"}
          </button>
        </form>
      </header>

      <div className="db-suggest">
        <span className="db-suggest-label">Try:</span>
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            className="db-suggest-chip"
            onClick={() => {
              setNeed(s);
              submit(s);
            }}
            disabled={running}
          >
            {s}
          </button>
        ))}
      </div>

      <PhaseStrip phase={state.phase} />

      <div className="db-body">
        <main className="db-main">
          {state.status === "rejected" && state.rejection && (
            <div className="db-notice">
              <h3>Out of personal-tool scope</h3>
              <p>{state.rejection.reason}</p>
              {state.rejection.alternative && (
                <p>
                  <strong>In-scope alternative:</strong> {state.rejection.alternative}
                </p>
              )}
            </div>
          )}

          {state.status === "error" && (
            <div className="db-notice error">
              <h3>Run error</h3>
              <p>{state.error}</p>
              <p>The pre-built fallback tool is available for the demo.</p>
            </div>
          )}

          <CandidateColumns candidates={state.candidates} strategies={strategies} />

          <ResultArea winner={winner} deployment={state.deployment} />
        </main>

        <aside className="db-sidebar">
          <KnowledgePanel
            kb={kb}
            retrieved={state.retrieved}
            lessonsAdded={state.lessonsAdded}
            onClear={clearKb}
          />
        </aside>
      </div>
    </div>
  );
}
