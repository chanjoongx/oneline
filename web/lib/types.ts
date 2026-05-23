// TypeScript mirrors of the shared/ contract. These match the JSON Schemas in
// shared/schemas verbatim. The dashboard renders Candidate, JudgeScores,
// Selection, and Lesson objects, so the shapes must stay in lockstep with
// shared/. If a shape changes, it changes in shared/ first.

export type ToolCategory =
  | "timer"
  | "tracker"
  | "calculator"
  | "flashcards"
  | "checklist"
  | "decision_tool"
  | "quiz"
  | "single_user_game"
  | "log"
  | "converter"
  | "randomizer"
  | "planner"
  | "display_only"
  | "utility";

export type Accent =
  | "#5B8DEF"
  | "#3FB950"
  | "#E3A008"
  | "#A371F7"
  | "#F85149"
  | "#2DD4BF";

export type Framework = "vanilla_html" | "tailwind_cdn";
export type UxEmphasis = "speed_minimal" | "polish" | "minimal_whitespace";
export type CandidateId = "A" | "B" | "C";

// ---- Plan (shared/schemas/plan.schema.json) ----
export interface CandidateStrategy {
  id: CandidateId;
  framework: Framework;
  ux_emphasis: UxEmphasis;
}

export interface Plan {
  rejected: boolean;
  rejection_reason: string | null;
  suggested_alternative: string | null;
  tool_category: ToolCategory;
  core_interactions: string[];
  data_model: string;
  success_criteria: string[];
  candidate_strategies: CandidateStrategy[];
}

// ---- RetrievedLessons (shared/schemas/retrieved_lessons.schema.json) ----
export interface RetrievedLessonItem {
  id: string;
  lesson_text: string;
  good_pattern: string;
  relevance_score: number;
}

export interface RetrievedLessons {
  retrieved_lessons: RetrievedLessonItem[];
}

// ---- Candidate (shared/schemas/candidate.schema.json) ----
export interface Candidate {
  candidate_id: CandidateId;
  html: string;
  environment_id: string;
  steps?: number;
  rationale?: string;
  accent?: Accent;
  framework?: Framework;
  ux_emphasis?: UxEmphasis;
}

// ---- JudgeScores (shared/schemas/judge_scores.schema.json) ----
export interface FunctionalityDetail {
  functionality_score: number;
  passed: string[];
  failed: string[];
  screenshot: string | null;
}

export interface UxClaritySubScores {
  primary_action_dominance: number;
  thumb_reach: number;
  touch_target_size: number;
  visual_simplicity: number;
  feedback_states: number;
  concrete_language: number;
}

export interface UxClarityDetail {
  ux_clarity_score: number;
  sub_scores: UxClaritySubScores;
  production_app_smells: string[];
  reasoning: string;
  improvement_suggestions: string[];
}

export interface DesignCoherenceSubScores {
  token_conformance: number;
  hero_discipline: number;
  typography_consistency: number;
  spatial_consistency: number;
  restraint: number;
}

export interface DesignCoherenceDetail {
  design_coherence_score: number;
  sub_scores: DesignCoherenceSubScores;
  system_violations: string[];
  reasoning: string;
}

export interface JudgeScores {
  candidate_id: CandidateId;
  functionality_score: number;
  ux_clarity_score: number;
  design_coherence_score: number;
  functionality: FunctionalityDetail;
  ux_clarity: UxClarityDetail;
  design_coherence: DesignCoherenceDetail;
}

// ---- Selection (shared/schemas/selection.schema.json) ----
export interface ScoredCandidate extends Candidate {
  functionality_score: number;
  ux_clarity_score: number;
  design_coherence_score: number;
  final_score?: number;
}

export interface Selection {
  winner: ScoredCandidate | null;
  losers?: ScoredCandidate[];
  rationale?: string;
  reason?: string | null;
}

// ---- Lesson (shared/schemas/lesson.schema.json) ----
export type AntiPattern =
  | "buried_primary_action"
  | "cluttered_layout"
  | "tiny_touch_targets"
  | "ambiguous_cta"
  | "missing_feedback_state"
  | "generic_button_text"
  | "thumb_unreachable"
  | "overflow_scrolling"
  | "hidden_state"
  | "production_app_smell"
  | "palette_drift"
  | "typography_inconsistency"
  | "cluttered_spacing"
  | "low_contrast";

export type LessonClass = "functionality" | "ux_clarity" | "design_coherence";
export type Severity = "low" | "medium" | "high";

export interface CuratorOutput {
  tool_category: ToolCategory;
  lesson_class: LessonClass;
  ux_anti_pattern: AntiPattern;
  tags: string[];
  lesson_text: string;
  bad_pattern: string;
  good_pattern: string;
  severity: Severity;
  score_delta: number;
}

export interface Lesson extends CuratorOutput {
  id: string;
  created_at: string;
  applied_count: number;
  prevented_repeats: number;
}

// ---- Deployment (deploy client output) ----
export interface Deployment {
  url: string;
  service: string;
  ts: number;
  // Set when the live deploy degraded and a fallback URL is in use.
  fallback?: boolean;
  error?: string;
}

// ---- Aggregate run result (mirrors core/orchestrator.run) ----
export interface RunResult {
  need: string;
  status: "running" | "rejected" | "no_winner" | "deployed";
  plan?: Plan;
  rejection_reason?: string | null;
  suggested_alternative?: string | null;
  retrieved_lessons?: RetrievedLessonItem[];
  candidates?: Candidate[];
  judge_scores?: Record<string, JudgeScores>;
  selection?: Selection;
  reason?: string | null;
  deployment?: Deployment;
  lessons_added?: string[];
  prevented_repeats?: string[];
}
