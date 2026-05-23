"use client";

import type { JudgeScores } from "@/lib/types";

function pct(n: number): string {
  return Math.round(n * 100) + "%";
}

function band(n: number, gate = false): string {
  if (gate && n < 0.9) return "bad";
  if (n >= 0.9) return "good";
  return "";
}

function Row({
  label,
  value,
  gate,
}: {
  label: string;
  value: number;
  gate?: boolean;
}) {
  return (
    <div className="db-score-row">
      <span className="db-score-label">{label}</span>
      <span className="db-score-track">
        <span
          className={"db-score-bar " + band(value, gate)}
          style={{ width: pct(value) }}
        />
      </span>
      <span className="db-score-val">{value.toFixed(2)}</span>
    </div>
  );
}

export default function JudgeScoreBars({ scores }: { scores: JudgeScores }) {
  return (
    <div className="db-scores">
      <Row label="Function" value={scores.functionality_score} gate />
      <Row label="UX" value={scores.ux_clarity_score} />
      <Row label="Design" value={scores.design_coherence_score} />
    </div>
  );
}
