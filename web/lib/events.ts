// The event protocol between /api/run (server) and the dashboard (client).
// Server-Sent Events carry the pipeline forward so the three candidate columns
// fill in real time. Every payload uses the shared shapes from lib/types.

import type {
  Candidate,
  CandidateId,
  Deployment,
  JudgeScores,
  Lesson,
  Plan,
  RetrievedLessonItem,
  Selection,
} from "./types";

export type Phase =
  | "idle"
  | "planning"
  | "retrieving"
  | "building"
  | "judging"
  | "selecting"
  | "deploying"
  | "done";

export const PHASE_ORDER: Phase[] = [
  "planning",
  "retrieving",
  "building",
  "judging",
  "selecting",
  "deploying",
  "done",
];

export const PHASE_LABEL: Record<Phase, string> = {
  idle: "Ready",
  planning: "Plan",
  retrieving: "Retrieve",
  building: "Build",
  judging: "Judge",
  selecting: "Select",
  deploying: "Deploy",
  done: "Done",
};

// Live status of a single candidate column during the build.
export type CandidateStatus =
  | "queued"
  | "building"
  | "built"
  | "judging"
  | "judged"
  | "winner"
  | "loser"
  | "failed";

// Discriminated union of everything the stream can send.
export type RunEvent =
  | { type: "phase"; phase: Phase }
  | { type: "plan"; plan: Plan }
  | {
      type: "rejected";
      rejection_reason: string | null;
      suggested_alternative: string | null;
    }
  | { type: "retrieved"; retrieved_lessons: RetrievedLessonItem[] }
  | {
      type: "candidate";
      candidate_id: CandidateId;
      status: CandidateStatus;
      candidate?: Candidate;
    }
  | { type: "judge"; candidate_id: CandidateId; scores: JudgeScores }
  | { type: "selection"; selection: Selection }
  | { type: "no_winner"; reason: string | null }
  | {
      type: "lessons";
      lessons_added: string[];
      prevented_repeats: string[];
      lessons: Lesson[];
    }
  | { type: "deployment"; deployment: Deployment }
  | { type: "error"; message: string }
  | { type: "done" };

// What the client carries about each candidate as the run unfolds.
export interface CandidateView {
  candidate_id: CandidateId;
  status: CandidateStatus;
  candidate?: Candidate;
  scores?: JudgeScores;
  final_score?: number;
  is_winner?: boolean;
}
