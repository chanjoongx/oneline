// Read-only access to the seed knowledge base. The dashboard never edits
// shared/; it reads the committed seed and then tracks session growth in the
// browser (localStorage) so the learning loop is visible across requests
// without writing to the shared contract.

import { readFile } from "node:fs/promises";
import path from "node:path";
import type { Lesson } from "./types";

const SEED: Lesson[] = [
  {
    id: "lesson_001",
    created_at: "2026-05-23T13:10:00Z",
    tool_category: "tracker",
    lesson_class: "ux_clarity",
    ux_anti_pattern: "buried_primary_action",
    tags: ["mobile_first", "tracker", "primary_cta", "touch_targets"],
    lesson_text:
      "Primary action must sit in the bottom third for thumb reach. Top-right buttons fail on tall layouts.",
    bad_pattern: "top-right action button on a tall single-screen layout",
    good_pattern: "bottom-center sticky full-width action",
    severity: "high",
    score_delta: -0.4,
    applied_count: 0,
    prevented_repeats: 0,
  },
];

export async function readSeedLessons(): Promise<Lesson[]> {
  // process.cwd() is the web/ directory when running next; the seed lives one
  // level up in shared/.
  const candidates = [
    path.join(process.cwd(), "..", "shared", "knowledge_base.json"),
    path.join(process.cwd(), "shared", "knowledge_base.json"),
  ];
  for (const p of candidates) {
    try {
      const raw = await readFile(p, "utf-8");
      const data = JSON.parse(raw);
      if (data && Array.isArray(data.lessons) && data.lessons.length) {
        return data.lessons as Lesson[];
      }
    } catch {
      // try the next path, then fall back to the inlined seed
    }
  }
  return SEED;
}
