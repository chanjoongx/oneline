# Shared schemas, the Oneline contract

These JSON Schema files (draft 2020-12) are the data contract between the code
modules. Every module codes against these shapes. The core module owns this
directory. If a shape must change, only core edits it and tells the other
modules; no one else edits `shared/`.

Every model call in the product is `gemini-3.5-flash`. No em dashes in any
generated value, anywhere. Hyphens only.

## Files

| Schema | Producer | Consumers |
|---|---|---|
| `plan.schema.json` | core Planner | core Retriever, sandbox Implementers |
| `retrieved_lessons.schema.json` | core Retriever | sandbox Implementers |
| `candidate.schema.json` | sandbox Implementer | judges, core Selector, web |
| `judge_scores.schema.json` | judges | core Selector, web, curator |
| `selection.schema.json` | core Selector | web, core (routes losers to curator) |
| `lesson.schema.json` | curator (subset) plus core write helper | core Retriever, web |

`../knowledge_base.json` is the persistent store of lessons, an object with a
`lessons` array of `Lesson` objects. It ships with one seed lesson.

## The pipeline in shapes

```
need (string)
  -> Planner            -> Plan
  -> Retriever(Plan, KB) -> RetrievedLessons
  -> Implementer x3      -> Candidate (one per strategy, in its own sandbox)
  -> Judge x3 per cand   -> JudgeScores (functionality, ux_clarity, design_coherence)
  -> Selector            -> Selection (winner, losers, rationale)
       winner -> Deployer -> Cloud Run URL -> QR
       losers -> Curator  -> Lesson(s) -> knowledge_base.json
```

## Canonical decisions (read these, they remove ambiguity)

1. **`candidate_id` is the one identifier.** A candidate is identified by
   `candidate_id`, a value in `A`, `B`, `C`, equal to the strategy `id` in the
   Plan. Earlier selector pseudocode used `c["id"]`; in this
   contract that key is `candidate_id`. Producers emit `candidate_id`; the
   selector and dashboard read `candidate_id`. Do not introduce a separate
   `id` on candidates.

2. **JudgeScores carries both headline and detail.** The three top-level
   numbers `functionality_score`, `ux_clarity_score`, `design_coherence_score`
   are what the deterministic selector reads. The three detail objects
   (`functionality`, `ux_clarity`, `design_coherence`) carry sub-scores and
   reasoning for the dashboard and the curator. The detail objects match the
   judge prompt outputs verbatim.

3. **A scored candidate is Candidate plus the three headline scores plus
   `final_score`.** The selector merges JudgeScores headline numbers onto the
   Candidate, computes `final_score`, and that merged object is what appears as
   `winner` and inside `losers` in the Selection. `final_score` is present for
   candidates that cleared the functionality gate; gate failures in `losers`
   may omit it. See `selection.schema.json` `$defs.scored_candidate`.

4. **Selection is one of two shapes.** On success: `winner` is a scored
   candidate, `losers` is an array, `rationale` is a string. On total failure
   (no candidate clears the 0.9 functionality gate): `winner` is `null` and
   `reason` is a string. The schema enforces this with if/then/else.

5. **Lesson has two forms.** The **stored** form (`lesson.schema.json` root)
   has all 13 fields and lives in `knowledge_base.json`. The **curator output**
   form (`$defs.curator_output`) is the 9-field subset the curator emits per
   loser, or `null` when nothing generalizable is found. The core write helper
   adds `id`, `created_at`, `applied_count: 0`, and `prevented_repeats: 0` when
   appending. The judges module targets `curator_output`; core writes the stored
   form.

## Selector math (deterministic, lives in core)

```
gate = 0.9
qualifying = [c for c in candidates if c.functionality_score >= gate]
if not qualifying: winner = null, reason = "..."
final_score = 0.40 * functionality_score
            + 0.35 * ux_clarity_score
            + 0.25 * design_coherence_score
winner = max(qualifying, key = (final_score, ux_clarity_score))   # tie-break on UX clarity
```

## Shared vocabulary

Tool categories: `timer, tracker, calculator, flashcards, checklist,
decision_tool, quiz, single_user_game, log, converter, randomizer, planner,
display_only, utility`.

UX anti-patterns: `buried_primary_action, cluttered_layout, tiny_touch_targets,
ambiguous_cta, missing_feedback_state, generic_button_text, thumb_unreachable,
overflow_scrolling, hidden_state, production_app_smell`.

Design anti-patterns: `palette_drift, typography_inconsistency,
cluttered_spacing, low_contrast`.

Always-on mobile tags: `mobile_first, touch_targets, primary_cta, thumb_zone,
single_screen`.

Approved accents (pick exactly one per tool, assign to `--accent`):
`#5B8DEF` blue, `#3FB950` green, `#E3A008` amber, `#A371F7` violet,
`#F85149` red, `#2DD4BF` teal. The full token block is in `../base.css`.
