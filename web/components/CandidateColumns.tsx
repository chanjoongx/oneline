"use client";

import type { CandidateView, CandidateStatus } from "@/lib/events";
import type { CandidateId, CandidateStrategy, UxEmphasis } from "@/lib/types";
import JudgeScoreBars from "./JudgeScoreBars";

const EMPHASIS_LABEL: Record<UxEmphasis, string> = {
  speed_minimal: "speed minimal",
  polish: "polish",
  minimal_whitespace: "minimal whitespace",
};

const STATUS_LABEL: Record<CandidateStatus, string> = {
  queued: "queued",
  building: "building",
  built: "built",
  judging: "judging",
  judged: "judged",
  winner: "winner",
  loser: "loser",
  failed: "failed",
};

function barWidth(status: CandidateStatus): number {
  switch (status) {
    case "queued":
      return 6;
    case "building":
      return 72;
    default:
      return 100;
  }
}

function codePreview(html?: string): string {
  if (!html) return "";
  return html.split("\n").slice(0, 16).join("\n");
}

const ORDER: CandidateId[] = ["A", "B", "C"];

export default function CandidateColumns({
  candidates,
  strategies,
}: {
  candidates: Partial<Record<CandidateId, CandidateView>>;
  strategies: CandidateStrategy[];
}) {
  const stratById: Partial<Record<CandidateId, CandidateStrategy>> = {};
  for (const s of strategies) stratById[s.id] = s;

  return (
    <section className="db-candidates" aria-label="Candidates">
      {ORDER.map((id) => {
        const cv = candidates[id];
        const strat = stratById[id];
        const status: CandidateStatus = cv?.status ?? "queued";
        const emphasis =
          cv?.candidate?.ux_emphasis ?? strat?.ux_emphasis ?? undefined;
        const isWinner = status === "winner";
        const isFailed = status === "failed";
        const isLoser = status === "loser";
        const cardCls =
          "db-card" +
          (isWinner ? " winner" : "") +
          (isLoser ? " loser" : "") +
          (isFailed ? " failed" : "");
        const busy = status === "building" || status === "judging";
        const fillCls =
          "db-bar-fill" +
          (busy ? " busy" : "") +
          (isWinner ? " win" : "") +
          (isFailed ? " fail" : "");
        const code = codePreview(cv?.candidate?.html);
        const failedChecks = cv?.scores?.functionality.failed ?? [];

        return (
          <article key={id} className={cardCls}>
            <div className="db-card-head">
              <span className="db-cid">{id}</span>
              <span className="db-emphasis">
                {emphasis ? EMPHASIS_LABEL[emphasis] : "strategy " + id}
              </span>
              <span className={"db-statuspill " + status}>{STATUS_LABEL[status]}</span>
            </div>

            <div className="db-bar">
              <span className={fillCls} style={{ width: barWidth(status) + "%" }} />
            </div>

            <div className="db-rationale">
              {cv?.candidate?.rationale ||
                (cv?.candidate?.environment_id
                  ? "sandbox " + cv.candidate.environment_id
                  : "waiting for sandbox")}
            </div>

            {code ? (
              <pre className="db-code">{code}</pre>
            ) : (
              <pre className="db-code empty">
                {status === "building" ? "building in sandbox" : "queued"}
              </pre>
            )}

            {cv?.scores ? (
              <JudgeScoreBars scores={cv.scores} />
            ) : (
              <div className="db-empty">scores pending</div>
            )}

            {isFailed && failedChecks.length > 0 && (
              <div className="db-failnote">
                Failed check: {failedChecks.join(", ")}
              </div>
            )}

            <div className="db-final">
              <span>final score</span>
              <b>{typeof cv?.final_score === "number" ? cv.final_score.toFixed(2) : "--"}</b>
            </div>
          </article>
        );
      })}
    </section>
  );
}
