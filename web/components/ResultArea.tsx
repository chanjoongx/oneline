"use client";

// The split result area. Left: QR plus open button plus live URL. Right: the
// phone mockup with the instant iframe preview. Both run in parallel; the
// preview never waits on the deploy.

import type { Deployment, ScoredCandidate } from "@/lib/types";
import PhoneMockup from "./PhoneMockup";
import QrPanel from "./QrPanel";

export default function ResultArea({
  winner,
  deployment,
}: {
  winner?: ScoredCandidate | null;
  deployment?: Deployment;
}) {
  const winnerHtml = winner?.html;
  return (
    <section className="db-result" aria-label="Result">
      <div className="db-result-left">
        <QrPanel deployment={deployment} hasWinner={!!winner} />
      </div>
      <div className="db-result-right">
        <PhoneMockup html={winnerHtml} />
      </div>
    </section>
  );
}
