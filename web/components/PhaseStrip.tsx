"use client";

import { PHASE_LABEL, PHASE_ORDER, type Phase } from "@/lib/events";
import React from "react";

const STEPS: Phase[] = ["planning", "retrieving", "building", "judging", "selecting", "deploying"];

export default function PhaseStrip({ phase }: { phase: Phase }) {
  const currentIndex = PHASE_ORDER.indexOf(phase);
  return (
    <div className="db-phase" aria-label="Pipeline progress">
      {STEPS.map((step, i) => {
        const stepIndex = PHASE_ORDER.indexOf(step);
        const isDone = phase === "done" || stepIndex < currentIndex;
        const isActive = stepIndex === currentIndex && phase !== "done";
        const cls = isActive ? "active" : isDone ? "done" : "";
        return (
          <React.Fragment key={step}>
            {i > 0 && <span className="db-phase-sep" />}
            <span className={"db-phase-step " + cls}>
              <span className="db-phase-dot" />
              {PHASE_LABEL[step]}
            </span>
          </React.Fragment>
        );
      })}
    </div>
  );
}
