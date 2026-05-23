"use client";

// The knowledge base panel. It shows the lessons learned, grows visibly when a
// new request adds lessons, lists the lessons applied to the current build, and
// reports the repeat-failures metric so the learning loop is legible.

import type { KbState } from "@/lib/useRun";
import type { RetrievedLessonItem } from "@/lib/types";

export default function KnowledgePanel({
  kb,
  retrieved,
  lessonsAdded,
  onClear,
}: {
  kb: KbState;
  retrieved: RetrievedLessonItem[];
  lessonsAdded: string[];
  onClear: () => void;
}) {
  const freshIds = new Set(lessonsAdded);
  // Newest lessons first.
  const lessons = [...kb.lessons].reverse();

  return (
    <div>
      <div className="db-kb-title">
        <h2>Knowledge base</h2>
        <button className="db-kb-clear" onClick={onClear} type="button">
          reset
        </button>
      </div>

      <div className="db-metrics">
        <div className="db-metric">
          <div className="db-metric-num">{kb.lessons.length}</div>
          <div className="db-metric-label">lessons</div>
        </div>
        <div className="db-metric">
          <div className="db-metric-num">{kb.runs}</div>
          <div className="db-metric-label">builds</div>
        </div>
        <div className="db-metric prevent">
          <div className="db-metric-num">{kb.totalPrevented}</div>
          <div className="db-metric-label">repeats prevented</div>
        </div>
      </div>

      {retrieved.length > 0 && (
        <>
          <div className="db-kb-section">Applied to this build</div>
          <div className="db-applied">
            {retrieved.map((r) => (
              <div className="db-applied-item" key={r.id}>
                <div className="db-applied-head">
                  <span className="db-applied-id">{r.id}</span>
                  <span className="db-applied-rel">rel {r.relevance_score.toFixed(2)}</span>
                </div>
                <div className="db-applied-text">{r.lesson_text}</div>
              </div>
            ))}
          </div>
        </>
      )}

      <div className="db-kb-section">Lessons</div>
      {lessons.length === 0 ? (
        <div className="db-empty">No lessons yet. Run a build to start the loop.</div>
      ) : (
        <div className="db-lessons">
          {lessons.map((l) => {
            const fresh = freshIds.has(l.id);
            return (
              <div className={"db-lesson" + (fresh ? " fresh" : "")} key={l.id}>
                <div className="db-lesson-head">
                  <span className="db-lesson-anti">{l.ux_anti_pattern}</span>
                  {fresh && <span className="db-lesson-badge">new</span>}
                  <span className="db-lesson-tag">{l.tool_category}</span>
                  <span className="db-lesson-tag">{l.lesson_class}</span>
                </div>
                <div className="db-lesson-text">{l.lesson_text}</div>
                <div className="db-lesson-foot">
                  <span>applied {l.applied_count}</span>
                  <span>prevented {l.prevented_repeats}</span>
                  <span>{l.severity}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
