# AI Interactions Log

> **Stretch features only.** Only fill in the sections that apply to stretch features you attempted. If you did not attempt a stretch feature, leave its section blank or delete it. This file is not required for the core project.

---

## Agent Workflow (SF7)

> Document your experience using an AI agent (e.g., Cursor Agent, Claude, Copilot) to make multi-step changes autonomously.

**Files modified**

- `pawpal_system.py`: added `Scheduler.find_next_available_slot()`.
- `tests/test_pawpal.py`: added 4 tests for the new method.
- `ai_interactions.md`: this section.

**What task did you give the agent?**

"Add a third algorithmic capability (like 'next available slot', weighted prioritization, etc.) that goes beyond the basic requirements." The first two capabilities were sorting/filtering and conflict detection. The agent chose which feature to build.

**What did the agent do?**

1. Read `pawpal_system.py` and searched the project for existing classes and tests, so the change would fit the current design.
2. Chose "next available slot" because it reuses existing pieces: `Owner.schedule` availability windows, `Task.occurs_on`/`time_on`, and the touching-is-not-a-conflict rule.
3. Added `Scheduler.find_next_available_slot(owner, duration_minutes, after, max_days=14)`. For each day it builds the availability windows (the whole day if none are set) and the sorted busy intervals from pending tasks, including recurring ones. A cursor sweeps each window and returns the first gap that fits, otherwise it moves to the next day. It returns `None` if nothing fits within `max_days` or the duration is not positive.
4. Appended 4 tests: back-to-back placement, gap too small versus big enough, availability windows rolling to the next day, and completed tasks plus the `None` cases.
5. Ran `python -m pytest`: 34 passed.

**What did you have to verify or fix manually?**

- **Agent's own test bug:** the first test run had 1 failure. My "nothing fits" case used 600 minutes, which fits in a 24-hour day, so the method was right and the test was wrong. I changed it to 1500 minutes and all tests passed.
- **Manual review still to do:** I (the user) have not yet reviewed the algorithm or run the app by hand. Items to check: the method is not wired into `app.py`, so it is not visible in the UI. Tasks that run past midnight are not handled, as with `_overlaps`. `after` is treated as a naive datetime like every other time in the project.
- **Other uncommitted changes:** `README.md`, `app.py`, `reflection.md` and the diagrams were already modified before this session and were not touched by this task.

---

## Prompt Comparison (SF11)

> Compare two different prompts (or two different models) on the same task.

| | Option A | Option B |
|-|----------|----------|
| **Model / tool used** | | |
| **Prompt** | | |
| **Response summary** | | |
| **What was useful** | | |
| **Problems noticed** | | |
| **Decision** | | |

**Which approach did you use in your final implementation and why?**

<!-- Your conclusion -->

---

## Agent Reasoning Traces (RAG + validation agent)

Each run's step-by-step reasoning (plan, tool calls, retrieval, validation, human decision), written by `agent.py`.

### Agent run 2026-11-18 01:12:09: plan for 2026-10-01
- **Request:** Plan Max's day
- **Explainer:** mock (offline, rule-based)
1. **PLAN**: Request "Plan Max's day": covering Max on 2026-10-01 (pets named in the request)
2. **ACT**: Tool build_daily_schedule -> 2 task(s): Vet appointment, Grooming. Tool conflict_warnings -> 4 warning(s).
3. **RETRIEVE**: Per-task retrieval: Vet appointment -> vet_visits.md (0.375); Grooming -> vet_visits.md (0.217). Request retrieval: medication.md, vet_visits.md.
4. **EXPLAIN**: Attempt 1 via mock (offline, rule-based): drafted 2 item(s).
5. **VALIDATE**: Attempt 1: passed (3 warning(s), needs_human=True).
   - `76ba30ed` 'Vet appointment' has highest priority, is scheduled for 14:00 (once). It is #1 of 2 today: it has the highest priority of the day. It overlaps with 'Grooming'. Guidance: Treat vet appointments as the highest priority on the schedule, and do not overlap them with other tasks. [vet_visits.md]
   - `e93bbfc5` 'Grooming' has low priority, is scheduled for 14:30 (once). It is #2 of 2 today: 'Vet appointment' comes first because it has higher priority (highest). It overlaps with 'Vet appointment'. Guidance: Plan extra time around a vet appointment. [vet_visits.md]
   - warning [rules] 'Vet appointment' and 'Grooming' overlap.
   - warning [safety] Medication or vet-related item: human review required.
   - warning [safety] Medication or vet-related item: human review required.
- **Outcome:** ok=True, used_fallback=False, needs_human=True, attempts=1

### Agent run 2026-11-18 01:12:09: plan for 2026-10-01
- **Request:** Plan Buddy's day
- **Explainer:** mock (offline, rule-based) + injected fault (1 bad attempt(s))
1. **PLAN**: Request "Plan Buddy's day": covering Buddy on 2026-10-01 (pets named in the request)
2. **ACT**: Tool build_daily_schedule -> 3 task(s): Breakfast, Evening walk, Brushing. Tool conflict_warnings -> 4 warning(s).
3. **RETRIEVE**: Per-task retrieval: Breakfast -> feeding.md (0.212); Evening walk -> exercise.md (0.258); Brushing -> grooming.md (0.327). Request retrieval: medication.md, vet_visits.md.
4. **EXPLAIN**: Attempt 1 via mock (offline, rule-based) + injected fault (1 bad attempt(s)): drafted 3 item(s).
5. **VALIDATE**: Attempt 1: FAILED with 1 error(s): [grounding] Cites 'dog_handbook.md', which was not retrieved.
6. **EXPLAIN**: Attempt 2 via mock (offline, rule-based) + injected fault (1 bad attempt(s)): drafted 3 item(s). Included validator feedback.
7. **VALIDATE**: Attempt 2: passed (0 warning(s), needs_human=False).
   - `b7321bb3` 'Breakfast' has high priority, is scheduled for 08:00 (daily). It is #1 of 3 today: it has the highest priority of the day. Guidance: Most adult dogs do well with two meals a day, roughly 8 to 12 hours apart, for example breakfast at 8:00 and dinner at 18:00. [feeding.md]
   - `9401f774` 'Evening walk' has medium priority, is scheduled for 16:00 (once). It is #2 of 3 today: 'Breakfast' comes first because it has higher priority (high). Guidance: In hot weather, walk early in the morning or in the evening and bring water. [exercise.md]
   - `bc054596` 'Brushing' has low priority, is scheduled for 11:00 (once). It is #3 of 3 today: 'Evening walk' comes first because it has higher priority (medium). Guidance: Brushing frequency depends on coat type. [grooming.md]
- **Outcome:** ok=True, used_fallback=False, needs_human=False, attempts=2

### Agent run 2026-11-18 01:12:09: plan for 2026-10-01
- **Request:** Plan Joe's day
- **Explainer:** mock (offline, rule-based) + injected fault (99 bad attempt(s))
1. **PLAN**: Request "Plan Joe's day": covering Joe on 2026-10-01 (pets named in the request)
2. **ACT**: Tool build_daily_schedule -> 3 task(s): Medication, Training session, Playtime. Tool conflict_warnings -> 4 warning(s).
3. **RETRIEVE**: Per-task retrieval: Medication -> medication.md (0.217); Training session -> exercise.md (0.379); Playtime -> no match. Request retrieval: medication.md, vet_visits.md.
4. **EXPLAIN**: Attempt 1 via mock (offline, rule-based) + injected fault (99 bad attempt(s)): drafted 3 item(s).
5. **VALIDATE**: Attempt 1: FAILED with 1 error(s): [grounding] Cites 'dog_handbook.md', which was not retrieved.
6. **EXPLAIN**: Attempt 2 via mock (offline, rule-based) + injected fault (99 bad attempt(s)): drafted 3 item(s). Included validator feedback.
7. **VALIDATE**: Attempt 2: FAILED with 1 error(s): [grounding] Cites 'dog_handbook.md', which was not retrieved.
8. **EXPLAIN**: Attempt 3 via mock (offline, rule-based) + injected fault (99 bad attempt(s)): drafted 3 item(s). Included validator feedback.
9. **VALIDATE**: Attempt 3: FAILED with 1 error(s): [grounding] Cites 'dog_handbook.md', which was not retrieved.
10. **FALLBACK**: All 3 attempts failed validation, so the plan uses the plain scheduler explanations with no AI text (valid=True).
   - `198d96b5` 'Medication' has high priority, is scheduled for 09:00 (once). It is #1 of 3 today: it has the highest priority of the day.
   - `9609d1c7` 'Training session' has medium priority, is scheduled for 11:00 (once). It is #2 of 3 today: 'Medication' comes first because it has higher priority (high). It overlaps with 'Playtime'.
   - `acdee542` 'Playtime' has low priority, is scheduled for 11:00 (once). It is #3 of 3 today: 'Training session' comes first because it has higher priority (medium). It overlaps with 'Training session'.
   - warning [rules] 'Training session' and 'Playtime' overlap.
   - warning [grounding] Explanation cites no source.
   - warning [grounding] Explanation cites no source.
   - warning [grounding] Explanation cites no source.
   - warning [safety] Medication or vet-related item: human review required.
   - warning [safety] Medication or vet-related item: human review required.
- **Outcome:** ok=True, used_fallback=True, needs_human=True, attempts=3

### Agent run 2026-11-18 01:32:27: plan for 2026-11-18
- **Request:** (none)
- **Explainer:** mock (offline, rule-based)
1. **PLAN**: Request '': covering no pets on 2026-11-18 (no pet named, so all pets)
2. **ACT**: Tool build_daily_schedule -> 0 task(s): none. Tool conflict_warnings -> 0 warning(s).
3. **DONE**: Nothing to plan, so no retrieval or explanation was needed.
- **Outcome:** ok=True, used_fallback=False, needs_human=False, attempts=0

### Agent run 2026-11-18 01:34:47: plan for 2026-11-18
- **Request:** Plan a day around max's vet appointment
- **Explainer:** mock (offline, rule-based)
1. **PLAN**: Request "Plan a day around max's vet appointment": covering Max on 2026-11-18 (pets named in the request)
2. **ACT**: Tool build_daily_schedule -> 1 task(s): Morning walk. Tool conflict_warnings -> 0 warning(s).
3. **RETRIEVE**: Per-task retrieval: Morning walk -> exercise.md (0.258). Request retrieval: vet_visits.md, vet_visits.md.
4. **EXPLAIN**: Attempt 1 via mock (offline, rule-based): drafted 1 item(s).
5. **VALIDATE**: Attempt 1: passed (0 warning(s), needs_human=False).
   - `48c77ca8` 'Morning walk' has medium priority, is scheduled for 01:32 (daily). It is #1 of 1 today: it's the only task. Guidance: In hot weather, walk early in the morning or in the evening and bring water. [exercise.md]
- **Outcome:** ok=True, used_fallback=False, needs_human=False, attempts=1

### Agent run 2026-11-18 01:35:19: plan for 2026-11-18
- **Request:** should jax eat tacos
- **Explainer:** mock (offline, rule-based)
1. **PLAN**: Request 'should jax eat tacos': covering Jax on 2026-11-18 (pets named in the request)
2. **ACT**: Tool build_daily_schedule -> 1 task(s): Morning walk. Tool conflict_warnings -> 0 warning(s).
3. **RETRIEVE**: Per-task retrieval: Morning walk -> exercise.md (0.258). Request retrieval: feeding.md.
4. **EXPLAIN**: Attempt 1 via mock (offline, rule-based): drafted 1 item(s).
5. **VALIDATE**: Attempt 1: passed (0 warning(s), needs_human=False).
   - `ccf00fe2` 'Morning walk' has medium priority, is scheduled for 01:58 (daily). It is #1 of 1 today: it's the only task. Guidance: In hot weather, walk early in the morning or in the evening and bring water. [exercise.md]
- **Outcome:** ok=True, used_fallback=False, needs_human=False, attempts=1

