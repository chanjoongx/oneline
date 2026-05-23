// Live bridge. Spawns the core JSON event entry point
//   python -m core.live --events "<need>"
// which runs the real pipeline (real Gemini Managed Agents build, real
// three-layer judge, real Cloud Run deploy) and writes one JSON object per line
// on stdout: { "event": string, "t": number, "data": object }. This maps that
// stream to the SSE RunEvent shape the dashboard already renders, so the three
// columns, code previews, scores, winner, QR, and phone preview fill live.
//
// Core streams per-candidate candidate_built (with html) and candidate_judged
// (with full scores) from its build and judge worker threads, so each column
// fills the moment that sandbox finishes. The winner preview is synthesized at
// select time, before the deploy returns, so it never waits on Cloud Run.
//
// Offline smoke test: ONELINE_LIVE_STUB=1 spawns web/live_runner.py instead,
// which emits the identical event shape over stub deps and a temp knowledge
// base, so the bridge and dashboard can be verified without credentials.

import { spawn } from "node:child_process";
import path from "node:path";
import { readSeedLessons } from "./kb";
import type { CandidateId, Candidate, JudgeScores, Selection } from "./types";
import type { RunEvent } from "./events";

interface CoreEvent {
  event: string;
  t?: number;
  data?: Record<string, unknown>;
}

function finalScore(s?: JudgeScores): number | undefined {
  if (!s) return undefined;
  return (
    Math.round(
      (0.4 * s.functionality_score +
        0.35 * s.ux_clarity_score +
        0.25 * s.design_coherence_score) *
        100
    ) / 100
  );
}

function createMapper() {
  const built: Partial<Record<CandidateId, Candidate>> = {};
  const scores: Partial<Record<CandidateId, JudgeScores>> = {};
  const failed = new Set<CandidateId>();
  const seen = new Set<CandidateId>();

  function scored(id: CandidateId): Selection["winner"] {
    const c = built[id];
    if (!c) return null;
    const s = scores[id];
    return {
      ...c,
      functionality_score: s?.functionality_score ?? 0,
      ux_clarity_score: s?.ux_clarity_score ?? 0,
      design_coherence_score: s?.design_coherence_score ?? 0,
      final_score: finalScore(s),
    };
  }

  // Maps one core event to zero or more SSE events. Terminal events (done,
  // error) are handled by the generator so it can read the knowledge base.
  function map(raw: CoreEvent): RunEvent[] {
    const d = (raw.data ?? {}) as Record<string, any>;
    switch (raw.event) {
      case "start":
        return [];

      case "plan":
        return [{ type: "plan", plan: d.plan }];

      case "rejected":
        return [
          {
            type: "rejected",
            rejection_reason: d.reason ?? null,
            suggested_alternative: d.alternative ?? null,
          },
        ];

      case "retrieve":
        return [
          { type: "phase", phase: "retrieving" },
          { type: "retrieved", retrieved_lessons: d.retrieved_lessons ?? [] },
        ];

      case "build_start": {
        const ids: CandidateId[] = (d.strategies ?? []).map((s: any) =>
          typeof s === "string" ? s : s?.id
        );
        const out: RunEvent[] = [{ type: "phase", phase: "building" }];
        for (const id of ids) {
          if (!id) continue;
          seen.add(id);
          out.push({ type: "candidate", candidate_id: id, status: "building" });
        }
        return out;
      }

      case "candidate_built": {
        const c: Candidate = {
          candidate_id: d.candidate_id,
          accent: d.accent,
          framework: d.framework,
          ux_emphasis: d.ux_emphasis,
          steps: d.steps,
          rationale: d.rationale,
          html: d.html,
          environment_id: d.environment_id ?? "",
        };
        built[c.candidate_id] = c;
        seen.add(c.candidate_id);
        return [{ type: "candidate", candidate_id: c.candidate_id, status: "built", candidate: c }];
      }

      case "build_done": {
        // Core has no per-candidate judging-start event, so the judge phase
        // begins here: survivors flip to judging, build failures to failed.
        const builtIds: CandidateId[] = d.built ?? [];
        const errs: Array<{ candidate_id: CandidateId }> = d.build_errors ?? [];
        const out: RunEvent[] = [{ type: "phase", phase: "judging" }];
        for (const id of builtIds) out.push({ type: "candidate", candidate_id: id, status: "judging" });
        for (const e of errs) {
          failed.add(e.candidate_id);
          out.push({ type: "candidate", candidate_id: e.candidate_id, status: "failed" });
        }
        return out;
      }

      case "candidate_judged": {
        const id = d.candidate_id as CandidateId;
        const s: JudgeScores = {
          candidate_id: id,
          functionality_score: d.functionality_score,
          ux_clarity_score: d.ux_clarity_score,
          design_coherence_score: d.design_coherence_score,
          functionality: d.functionality,
          ux_clarity: d.ux_clarity,
          design_coherence: d.design_coherence,
        };
        scores[id] = s;
        return [
          { type: "judge", candidate_id: id, scores: s },
          { type: "candidate", candidate_id: id, status: "judged" },
        ];
      }

      case "judge_done": {
        const errs: Array<{ candidate_id: CandidateId }> = d.judge_errors ?? [];
        return errs.map((e) => {
          failed.add(e.candidate_id);
          return { type: "candidate", candidate_id: e.candidate_id, status: "failed" } as RunEvent;
        });
      }

      case "select": {
        const winner = d.winner as CandidateId;
        const out: RunEvent[] = [{ type: "phase", phase: "selecting" }];
        const w = scored(winner);
        if (w) out.push({ type: "selection", selection: { winner: w } as Selection });
        out.push({ type: "candidate", candidate_id: winner, status: "winner" });
        for (const id of seen) {
          if (id === winner || failed.has(id)) continue;
          out.push({ type: "candidate", candidate_id: id, status: "loser" });
        }
        return out;
      }

      case "no_winner":
        return [{ type: "no_winner", reason: d.reason ?? null }];

      case "deploy_start":
        return [{ type: "phase", phase: "deploying" }];

      case "deploy_done":
        return [{ type: "deployment", deployment: d.deployment }];

      case "curate_done":
        return [];

      default:
        return [];
    }
  }

  return { map };
}

export async function* runLive(need: string): AsyncGenerator<RunEvent> {
  // Light up the phase strip immediately, before the subprocess produces output.
  yield { type: "phase", phase: "planning" };

  const python = process.env.PYTHON || "python";
  const webDir = process.cwd();
  const repoRoot = path.join(webDir, "..");
  const stub = process.env.ONELINE_LIVE_STUB === "1";

  const child = stub
    ? spawn(python, [path.join(webDir, "live_runner.py"), need], {
        cwd: webDir,
        env: { ...process.env, PYTHONUTF8: "1", ONELINE_NEED: need },
      })
    : spawn(python, ["-m", "core.live", "--events", need], {
        cwd: repoRoot,
        env: { ...process.env, PYTHONUTF8: "1", ONELINE_NEED: need },
      });

  const mapper = createMapper();
  const queue: CoreEvent[] = [];
  let wake: (() => void) | null = null;
  let closed = false;
  let stdoutBuf = "";
  let stderrTail = "";

  const push = (ev: CoreEvent) => {
    queue.push(ev);
    if (wake) {
      wake();
      wake = null;
    }
  };

  child.stdout.on("data", (chunk: Buffer) => {
    stdoutBuf += chunk.toString("utf8");
    let nl = stdoutBuf.indexOf("\n");
    while (nl >= 0) {
      const line = stdoutBuf.slice(0, nl).trim();
      stdoutBuf = stdoutBuf.slice(nl + 1);
      nl = stdoutBuf.indexOf("\n");
      if (!line) continue;
      try {
        const parsed = JSON.parse(line);
        if (parsed && typeof parsed.event === "string") push(parsed);
      } catch {
        // not a JSON event line; ignore
      }
    }
  });

  child.stderr.on("data", (chunk: Buffer) => {
    const s = chunk.toString("utf8");
    stderrTail = (stderrTail + s).slice(-2000);
    process.stderr.write(s);
  });

  child.on("close", () => {
    closed = true;
    if (wake) {
      wake();
      wake = null;
    }
  });
  child.on("error", (e) => {
    stderrTail += "\nspawn error: " + String(e);
    closed = true;
    if (wake) {
      wake();
      wake = null;
    }
  });

  let emittedDone = false;
  try {
    for (;;) {
      while (queue.length) {
        const raw = queue.shift() as CoreEvent;

        if (raw.event === "done") {
          const d = (raw.data ?? {}) as Record<string, any>;
          // Core's done carries ids only; the full lesson objects come from the
          // knowledge base on disk that core just wrote. The stub mirror inlines
          // its own list under data.lessons.
          const lessons = Array.isArray(d.lessons) ? d.lessons : await readSeedLessons();
          yield {
            type: "lessons",
            lessons_added: d.lessons_added ?? [],
            prevented_repeats: d.prevented_repeats ?? [],
            lessons,
          };
          const status = d.status as string;
          if (status !== "deployed" && status !== "rejected" && status !== "no_winner") {
            yield { type: "error", message: d.reason || "run ended with status " + status };
          }
          yield { type: "phase", phase: "done" };
          yield { type: "done" };
          emittedDone = true;
          continue;
        }

        if (raw.event === "error") {
          const d = (raw.data ?? {}) as Record<string, any>;
          yield { type: "error", message: d.message || "live run failed" };
          yield { type: "phase", phase: "done" };
          yield { type: "done" };
          emittedDone = true;
          continue;
        }

        for (const e of mapper.map(raw)) yield e;
      }

      if (emittedDone) break;
      if (closed && queue.length === 0) break;

      await new Promise<void>((resolve) => {
        wake = resolve;
      });
    }
  } finally {
    if (!closed) {
      try {
        child.kill();
      } catch {
        // already gone
      }
    }
  }

  if (!emittedDone) {
    yield {
      type: "error",
      message: "live runner exited early: " + (stderrTail.slice(-400) || "no output"),
    };
    yield { type: "phase", phase: "done" };
    yield { type: "done" };
  }
}
