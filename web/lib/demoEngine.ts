// The demo engine. It drives one request through the full pipeline and yields
// the same event stream the dashboard would receive from a live core run. It
// produces schema-accurate Plan, Candidate, JudgeScores, Selection, and Lesson
// objects, then calls the real deploy client for the winner.
//
// This is the resilient default so the three columns always fill live and the
// learning loop is always visible. A real core run produces the same shapes;
// the dashboard renders either identically.

import { deployWinner } from "./deployClient";
import type { RunEvent } from "./events";
import { classify, isOutOfScope, specForCategory } from "./fixtures/tools";
import type {
  CandidateId,
  CuratorOutput,
  JudgeScores,
  Lesson,
  Plan,
  RetrievedLessonItem,
  ScoredCandidate,
  Candidate,
  UxEmphasis,
} from "./types";

const ALWAYS_ON = [
  "mobile_first",
  "touch_targets",
  "primary_cta",
  "thumb_zone",
  "single_screen",
];

const WEIGHTS = { functionality: 0.4, ux_clarity: 0.35, design_coherence: 0.25 };
const GATE = 0.9;

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

function finalScore(f: number, u: number, d: number): number {
  return round2(
    WEIGHTS.functionality * f + WEIGHTS.ux_clarity * u + WEIGHTS.design_coherence * d
  );
}

function nextLessonId(existing: Lesson[]): number {
  let max = 0;
  for (const l of existing) {
    const m = /^lesson_(\d+)$/.exec(l.id);
    if (m) max = Math.max(max, parseInt(m[1], 10));
  }
  return max + 1;
}

function lessonId(n: number): string {
  return "lesson_" + String(n).padStart(3, "0");
}

// Deterministic tag-overlap retrieval. Mirrors the spirit of the core retriever:
// lessons that share the category or the always-on mobile tags surface, capped
// at five, only at or above relevance 0.5.
function retrieve(plan: Plan, lessons: Lesson[]): RetrievedLessonItem[] {
  const planTags = new Set<string>([plan.tool_category, ...ALWAYS_ON]);
  const scored = lessons
    .map((l) => {
      const ltags = new Set<string>([l.tool_category, ...l.tags]);
      let overlap = 0;
      planTags.forEach((t) => {
        if (ltags.has(t)) overlap += 1;
      });
      const sameCat = l.tool_category === plan.tool_category ? 0.2 : 0;
      const rel = overlap === 0 ? 0 : Math.min(1, 0.5 + 0.1 * overlap + sameCat);
      return { l, rel };
    })
    .filter((x) => x.rel >= 0.5)
    .sort((a, b) => b.rel - a.rel)
    .slice(0, 5);
  return scored.map((x) => ({
    id: x.l.id,
    lesson_text: x.l.lesson_text,
    good_pattern: x.l.good_pattern,
    relevance_score: round2(x.rel),
  }));
}

function makePlan(need: string): Plan {
  if (isOutOfScope(need)) {
    return {
      rejected: true,
      rejection_reason:
        "That needs accounts, a server, or other people, so it is outside personal-tool scope.",
      suggested_alternative:
        "A single-screen version that keeps the spirit and runs on your phone with local storage.",
      tool_category: "utility",
      core_interactions: ["Use the tool on one device with no sign in"],
      data_model: "Local only, in the browser. No backend.",
      success_criteria: ["The tool works for one person without any account"],
      candidate_strategies: [
        { id: "A", framework: "vanilla_html", ux_emphasis: "speed_minimal" },
      ],
    };
  }
  const spec = classify(need);
  const interactions: Record<string, string[]> = {
    timer: ["Start and pause the interval timer", "Advance through custom rounds"],
    flashcards: ["Flip a card to reveal the answer", "Move to the next card"],
    decision_tool: ["Add an option to the list", "Pick one option at random"],
    tracker: ["Increment the count with one tap", "Reset the count"],
    checklist: ["Add an item", "Mark an item done"],
  };
  const data: Record<string, string> = {
    timer: "Rounds and durations in localStorage. Current round index in memory.",
    flashcards: "A fixed deck of term and answer pairs held in localStorage.",
    decision_tool: "The option list held in localStorage.",
    tracker: "The running count and a short history in localStorage.",
    checklist: "Items and their done state in localStorage.",
  };
  const success: Record<string, string[]> = {
    timer: ["Starting the timer counts down the first round", "Completing a round advances to the next"],
    flashcards: ["Tapping a card reveals the answer", "Next moves through the deck"],
    decision_tool: ["Adding an option shows it in the list", "Pick selects one option"],
    tracker: ["Tapping adds one to the count", "Reset returns the count to zero"],
    checklist: ["Adding an item shows it in the list", "Tapping an item marks it done"],
  };
  const cat = spec.category;
  return {
    rejected: false,
    rejection_reason: null,
    suggested_alternative: null,
    tool_category: cat,
    core_interactions: interactions[cat] || interactions.tracker,
    data_model: data[cat] || data.tracker,
    success_criteria: success[cat] || success.tracker,
    candidate_strategies: [
      { id: "A", framework: "vanilla_html", ux_emphasis: "speed_minimal" },
      { id: "B", framework: "tailwind_cdn", ux_emphasis: "polish" },
      { id: "C", framework: "tailwind_cdn", ux_emphasis: "minimal_whitespace" },
    ],
  };
}

function byCategory(cat: Plan["tool_category"]) {
  return specForCategory(cat);
}

function makeCandidate(
  id: CandidateId,
  plan: Plan,
  emphasis: UxEmphasis,
  framework: "vanilla_html" | "tailwind_cdn"
): Candidate {
  const builder = byCategory(plan.tool_category);
  const html = builder.build(builder.accent, emphasis);
  const layout: Record<UxEmphasis, string> = {
    speed_minimal: "sparse single screen, one action",
    polish: "considered detail, hero centered, action in the thumb zone",
    minimal_whitespace: "generous spacing, hero dominant",
  };
  return {
    candidate_id: id,
    html,
    environment_id: "env-" + id.toLowerCase() + "-" + Math.floor(Date.now() / 1000),
    steps: 4 + Math.floor(Math.random() * 4),
    rationale: "Rationale: " + builder.accent + " accent, " + layout[emphasis] + ".",
    accent: builder.accent,
    framework,
    ux_emphasis: emphasis,
  };
}

function makeScores(
  id: CandidateId,
  f: number,
  u: number,
  d: number,
  failedChecks: string[]
): JudgeScores {
  const passed = ["loads_under_3s", "primary_action_works", "state_persists"].filter(
    (c) => !failedChecks.includes(c)
  );
  return {
    candidate_id: id,
    functionality_score: f,
    ux_clarity_score: u,
    design_coherence_score: d,
    functionality: {
      functionality_score: f,
      passed,
      failed: failedChecks,
      screenshot: null,
    },
    ux_clarity: {
      ux_clarity_score: u,
      sub_scores: {
        primary_action_dominance: round2(Math.min(1, u + 0.04)),
        thumb_reach: 1.0,
        touch_target_size: 1.0,
        visual_simplicity: round2(u),
        feedback_states: round2(Math.max(0, u - 0.05)),
        concrete_language: 1.0,
      },
      production_app_smells: [],
      reasoning:
        u >= 0.9
          ? "Primary action is the largest element and sits in the thumb zone. Reads in a glance."
          : "Primary action is clear but the secondary controls compete for attention.",
      improvement_suggestions: u >= 0.9 ? [] : ["Name the primary action with a verb and a noun"],
    },
    design_coherence: {
      design_coherence_score: d,
      sub_scores: {
        token_conformance: round2(Math.min(1, d + 0.06)),
        hero_discipline: 1.0,
        typography_consistency: round2(d),
        spatial_consistency: round2(d),
        restraint: round2(Math.max(0, d - 0.03)),
      },
      system_violations: [],
      reasoning:
        "Single accent, one mono hero, spacing on the 8px grid. Dark base throughout.",
    },
  };
}

function scoredFrom(c: Candidate, s: JudgeScores, withFinal: boolean): ScoredCandidate {
  const out: ScoredCandidate = {
    ...c,
    functionality_score: s.functionality_score,
    ux_clarity_score: s.ux_clarity_score,
    design_coherence_score: s.design_coherence_score,
  };
  if (withFinal) {
    out.final_score = finalScore(
      s.functionality_score,
      s.ux_clarity_score,
      s.design_coherence_score
    );
  }
  return out;
}

function curateFrom(loser: ScoredCandidate, plan: Plan): CuratorOutput | null {
  if (loser.candidate_id === "A") {
    return {
      tool_category: plan.tool_category,
      lesson_class: "ux_clarity",
      ux_anti_pattern: "generic_button_text",
      tags: ["mobile_first", "primary_cta", "thumb_zone", plan.tool_category],
      lesson_text:
        "Name the primary action with a verb and a noun so the next tap is obvious without reading anything else.",
      bad_pattern: "a generic primary button labeled Go or Submit",
      good_pattern: "a verb plus noun primary button in the thumb zone",
      severity: "medium",
      score_delta: -0.1,
    };
  }
  if (loser.candidate_id === "C") {
    return {
      tool_category: plan.tool_category,
      lesson_class: "ux_clarity",
      ux_anti_pattern: "missing_feedback_state",
      tags: ["mobile_first", "single_screen", "primary_cta", plan.tool_category],
      lesson_text:
        "Every primary tap needs an immediate visible change so the user knows it worked.",
      bad_pattern: "a primary action that updates nothing visible on tap",
      good_pattern: "an instant state change on the hero value or list",
      severity: "medium",
      score_delta: -0.15,
    };
  }
  return null;
}

export interface EngineInput {
  need: string;
  sessionLessons: Lesson[];
}

// The full pipeline as an async event stream.
export async function* runEngine(input: EngineInput): AsyncGenerator<RunEvent> {
  const need = (input.need || "").trim();

  // 1. Plan
  yield { type: "phase", phase: "planning" };
  await sleep(600);
  const plan = makePlan(need);
  yield { type: "plan", plan };
  if (plan.rejected) {
    await sleep(300);
    yield {
      type: "rejected",
      rejection_reason: plan.rejection_reason,
      suggested_alternative: plan.suggested_alternative,
    };
    yield { type: "phase", phase: "done" };
    yield { type: "done" };
    return;
  }

  // 2. Retrieve. Merge the seed and any session lessons sent by the client so
  // retrieval reflects prior runs.
  yield { type: "phase", phase: "retrieving" };
  await sleep(450);
  const baseLessons = dedupe(input.sessionLessons || []);
  const retrieved = retrieve(plan, baseLessons);
  yield { type: "retrieved", retrieved_lessons: retrieved };
  await sleep(250);

  // 3. Build three candidates in parallel.
  yield { type: "phase", phase: "building" };
  const strat = plan.candidate_strategies;
  const cands: Record<CandidateId, Candidate> = {
    A: makeCandidate("A", plan, "speed_minimal", "vanilla_html"),
    B: makeCandidate("B", plan, "polish", "tailwind_cdn"),
    C: makeCandidate("C", plan, "minimal_whitespace", "tailwind_cdn"),
  };
  const order: CandidateId[] = strat.map((s) => s.id) as CandidateId[];
  for (const id of order) {
    yield { type: "candidate", candidate_id: id, status: "queued" };
    await sleep(120);
  }
  for (const id of order) {
    yield { type: "candidate", candidate_id: id, status: "building" };
  }
  // Finish at staggered times so the parallel build reads as three sandboxes
  // working at once and completing independently.
  const buildOrder: Array<[CandidateId, number]> = [
    ["A", 1500],
    ["C", 900],
    ["B", 1100],
  ];
  for (const [id, ms] of buildOrder) {
    await sleep(ms);
    yield { type: "candidate", candidate_id: id, status: "built", candidate: cands[id] };
  }

  // 4. Judge each candidate.
  yield { type: "phase", phase: "judging" };
  const scores: Record<CandidateId, JudgeScores> = {
    A: makeScores("A", 1.0, 0.86, 0.83, []),
    B: makeScores("B", 1.0, 0.94, 0.91, []),
    C: makeScores("C", 0.5, 0.88, 0.86, ["primary_action_works"]),
  };
  for (const id of ["A", "B", "C"] as CandidateId[]) {
    yield { type: "candidate", candidate_id: id, status: "judging" };
    await sleep(700);
    yield { type: "judge", candidate_id: id, scores: scores[id] };
    yield { type: "candidate", candidate_id: id, status: "judged" };
  }

  // 5. Select. Functionality gate, then weighted score, tie-break on UX.
  yield { type: "phase", phase: "selecting" };
  await sleep(450);
  const qualifying = (["A", "B", "C"] as CandidateId[]).filter(
    (id) => scores[id].functionality_score >= GATE
  );
  const ranked = qualifying
    .map((id) => scoredFrom(cands[id], scores[id], true))
    .sort(
      (a, b) =>
        (b.final_score || 0) - (a.final_score || 0) ||
        b.ux_clarity_score - a.ux_clarity_score
    );
  const winner = ranked[0];
  const losers: ScoredCandidate[] = [];
  for (const id of ["A", "B", "C"] as CandidateId[]) {
    if (id === winner.candidate_id) continue;
    const gated = scores[id].functionality_score >= GATE;
    losers.push(scoredFrom(cands[id], scores[id], gated));
  }
  const selection = {
    winner,
    losers,
    rationale: "Selected " + winner.candidate_id + " at " + (winner.final_score || 0).toFixed(2),
    reason: null,
  };
  yield { type: "selection", selection };
  yield { type: "candidate", candidate_id: winner.candidate_id, status: "winner" };
  for (const l of losers) {
    const gated = scores[l.candidate_id].functionality_score >= GATE;
    yield {
      type: "candidate",
      candidate_id: l.candidate_id,
      status: gated ? "loser" : "failed",
    };
  }

  // 6. Curate losers into lessons and grow the knowledge base.
  let allLessons = baseLessons.slice();
  const added: string[] = [];
  let n = nextLessonId(allLessons);
  for (const loser of losers) {
    const curated = curateFrom(loser, plan);
    if (!curated) continue;
    const lesson: Lesson = {
      ...curated,
      id: lessonId(n),
      created_at: new Date().toISOString(),
      applied_count: 0,
      prevented_repeats: 0,
    };
    allLessons.push(lesson);
    added.push(lesson.id);
    n += 1;
  }
  // Mark retrieved lessons as applied.
  const retrievedIds = new Set(retrieved.map((r) => r.id));
  allLessons = allLessons.map((l) =>
    retrievedIds.has(l.id) ? { ...l, applied_count: l.applied_count + 1 } : l
  );
  // Repeat-failures metric: a retrieved lesson counts as prevented when the
  // winner shows none of its anti-pattern (the winner has no violations here).
  const winnerViolations = new Set<string>([
    ...scores[winner.candidate_id].design_coherence.system_violations.map((v) => v.toLowerCase()),
    ...scores[winner.candidate_id].ux_clarity.production_app_smells.map((v) => v.toLowerCase()),
  ]);
  const prevented = retrieved
    .filter((r) => {
      const lesson = allLessons.find((l) => l.id === r.id);
      const anti = (lesson?.ux_anti_pattern || "").toLowerCase();
      return anti && !Array.from(winnerViolations).some((v) => v.includes(anti) || anti.includes(v));
    })
    .map((r) => r.id);
  const preventedSet = new Set(prevented);
  allLessons = allLessons.map((l) =>
    preventedSet.has(l.id) ? { ...l, prevented_repeats: l.prevented_repeats + 1 } : l
  );
  yield {
    type: "lessons",
    lessons_added: added,
    prevented_repeats: prevented,
    lessons: allLessons,
  };

  // 7. Deploy the winner. The phone preview already shows the result client
  // side, so this runs in parallel and the demo never waits on it.
  yield { type: "phase", phase: "deploying" };
  const deployment = await deployWinner(winner.html);
  yield { type: "deployment", deployment };

  yield { type: "phase", phase: "done" };
  yield { type: "done" };
}

function dedupe(lessons: Lesson[]): Lesson[] {
  const seen = new Set<string>();
  const out: Lesson[] = [];
  for (const l of lessons) {
    if (seen.has(l.id)) continue;
    seen.add(l.id);
    out.push(l);
  }
  return out;
}
