# PawPal+ — Agentic, Retrieval-Grounded Pet Care Planner

## Original Project (Modules 1–3): PawPal+

This project extends **PawPal+**, the Streamlit pet-care scheduler I built in Modules 1–3. The original goal was to help a busy owner stay consistent with pet care: track tasks (walks, feeding, meds, grooming) across several pets, respect the owner's available time and task priorities, and produce a daily plan that explains why each task landed where it did. It could sort and filter tasks, detect overlapping tasks across pets, handle recurring tasks (daily, weekly, biweekly, monthly), save data to `data.json`, and ship with an automated pytest suite.

## Title and Summary

**PawPal+ with Agentic Workflow, RAG and Validation** adds an AI layer on top of that deterministic scheduler. In the new **AI Plan Assistant** the owner picks a day and optionally types a request ("Plan Max's day"). A **planning agent** calls the existing `Scheduler` as tools, a **retriever** finds pet-care guidance for each task, and an explainer writes cited explanations. Automated **validators** check the result, with retries and a deterministic fallback, and a **human** approves or rejects the plan.

**Why it matters:** pet care involves medication and vet timing, where a confident but wrong AI answer can hurt an animal. Grounding answers in retrieved sources, checking them with rules, and keeping the owner in the loop makes the AI useful without trusting it blindly.

> **Status:** everything described below is implemented and tested. The explainer has two modes: a `ClaudeExplainer` (used when `ANTHROPIC_API_KEY` is set) and an offline `MockExplainer` (the default). **All outputs shown in this README were produced by the offline mock explainer.** The Claude path is covered by unit tests with a fake client but has **not been run against the live API**.

## Architecture Overview

The diagram is in [`diagrams/system_diagram_rag_agent.mmd`](diagrams/system_diagram_rag_agent.mmd) (the older class diagram is `diagrams/uml_final.mmd`). Every box in it maps to a file. Data flows in four stages:

1. **Input** — The owner uses the Streamlit forms (`app.py`, data loaded from `data.json`) and, in the AI Plan Assistant, picks a date and optionally types a request.
2. **Process** — `PlanningAgent.run` in `agent.py` works in steps and records each one in a trace:
   - **PLAN:** choose the pets named in the request, otherwise all pets.
   - **ACT:** call the scheduler as tools (`build_daily_schedule`, `conflict_warnings`). The scheduler decides which tasks are planned and in what order.
   - **RETRIEVE:** `retriever.py` searches the paragraphs in `kb/*.md` with TF-IDF keyword matching. The query is the task name, and the request is searched separately. Each hit keeps its source file for citation.
   - **EXPLAIN:** an explainer writes a cited explanation for each task (`ClaudeExplainer` or the offline `MockExplainer`).
3. **Validation** — `validators.py` checks the draft: *rules* (task exists, occurs on that day, still pending, inside the owner's availability, none missing), *grounding* (every citation was actually retrieved), and *safety* (advice that changes a medicine dose is an error, and medication or vet items set `needs_human`). Overlapping tasks and uncited explanations are warnings. On errors the agent re-runs EXPLAIN with the error text as feedback, up to 2 more times, then **falls back** to the plain `Scheduler.explain_choice` text with no AI-written content.
4. **Human checkpoint and output** — The owner sees the plan, citations, warnings and a notice for medication or vet items, then clicks **Approve** or **Reject** (Approve is disabled while errors remain). The plan, the agent's reasoning trace and the human decision are written to `ai_interactions.md`. Approving does not change `data.json`.

**Testing is involved at four points:** pytest unit tests (scheduler, retriever, validators and the agent with fake explainers); `eval_retrieval.py`, which measures retrieval accuracy on 12 labelled questions; `demo_guardrails.py`, which runs the validators on good and bad plans; and `demo_agent.py`, which runs the whole agent end to end.

### Key files

| File | Role |
|------|------|
| `pawpal_system.py` | Logic layer: `Owner`, `Pet`, `Task`, `TimeSlot`, `Reminder`, `Scheduler`, JSON save/load |
| `app.py` | Streamlit UI |
| `main.py` | CLI demo (1 owner, 3 pets, 8 tasks) |
| `display.py` | Terminal tables, colors, emojis |
| `agent.py` | `PlanningAgent` (plan, act, retrieve, explain, validate, retry, fallback), explainers, trace logging |
| `retriever.py` | TF-IDF retriever over the paragraphs in `kb/` |
| `kb/*.md` | Knowledge base: feeding, medication, exercise, grooming, vet visits |
| `validators.py` | Rules, grounding and safety checks on an AI plan |
| `eval_retrieval.py` | Retrieval accuracy on 12 labelled questions |
| `demo_agent.py`, `demo_guardrails.py`, `sample_data.py` | Runnable demos and the sample owner |
| `ai_interactions.md` | Saved agent reasoning traces and human decisions |
| `tests/` | `test_pawpal.py`, `test_retriever.py`, `test_retrieval_eval.py`, `test_validators.py`, `test_agent.py` |
| `diagrams/` | `uml_final.mmd` (classes), `system_diagram_rag_agent.mmd` (AI system) |

## Setup Instructions

1. **Install Python 3.10+** and open a terminal in the project folder.
2. **Create and activate a virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate      # Windows: .venv\Scripts\activate
   ```
3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
4. **Run the web app**
   ```bash
   streamlit run app.py
   ```
5. **Or run the CLI demo**
   ```bash
   python main.py
   ```
6. **Run the tests**
   ```bash
   python -m pytest
   ```
7. **Try the AI layer.** In the app, scroll to **AI Plan Assistant**, pick a date, optionally type a request such as `Plan Max's day`, and click **Generate AI plan**. Or run the end-to-end demo from the terminal (add `--log` to also save the traces to `ai_interactions.md`):
   ```bash
   python demo_agent.py
   python demo_guardrails.py
   python eval_retrieval.py
   ```
8. **(Optional) Use Claude instead of the offline mock.** Install the SDK and set a key, then restart. The explainer is chosen automatically, and the app shows which one was used.
   ```bash
   pip install anthropic
   export ANTHROPIC_API_KEY=...     # Windows PowerShell: $env:ANTHROPIC_API_KEY="..."
   ```
   The model defaults to `claude-opus-5-5` and can be changed with `PAWPAL_MODEL`. This path has not been run against the live API yet.

Pet and task data is saved to `data.json` in the folder you launch from; delete it to reset. Agent and validator log lines go to `pawpal.log`.

## Sample Interactions

These come from the working scheduler (`python main.py`, owner available 08:00–17:00). They are the deterministic core the agent calls as tools.

**1. Input:** Generate the plan for Oct 01.
**Output:**
```
Daily plan for October 01 (inside 08:00-17:00 availability):
  1. 14:00 Vet appointment (Max) - 'Vet appointment' has highest priority, is scheduled for 14:00 (once). It is #1 of 6 today: it has the highest priority of the day. It overlaps with 'Grooming'.
  2. 11:00 Training session (Joe) - 'Training session' has medium priority, is scheduled for 11:00 (once). It is #2 of 6 today: 'Vet appointment' comes first because it has higher priority (highest). It overlaps with 'Brushing', 'Playtime'.
  ...
```

**2. Input:** Check Oct 01 for double-booking.
**Output:**
```
🚨 4 scheduling conflict(s):
  • Conflict (same start time, different pets): 'Brushing' (Buddy, 11:00) and 'Training session' (Joe, 11:00)
  • Conflict (same start time, different pets): 'Brushing' (Buddy, 11:00) and 'Playtime' (Joe, 11:00)
  • Conflict (same start time, same pet): 'Training session' (Joe, 11:00) and 'Playtime' (Joe, 11:00)
  • Conflict (overlap, same pet): 'Vet appointment' (Max, 14:00) and 'Grooming' (Max, 14:30)
```

**3. Input:** Find the next free slot for tasks of 30, 120 and 180 minutes, asking at Oct 01 11:00.
**Output:**
```
   30 min, asking at Oct 01 11:00 -> Oct 01 11:30
  120 min, asking at Oct 01 11:00 -> Oct 01 11:30
  180 min, asking at Oct 01 11:00 -> Oct 02 08:30
```

**4. Input:** Complete the daily "Breakfast" task.
**Output:** the task is marked done and the next one is created on Oct 02 08:00 (daily, pending).

### Retrieval step (RAG), from `python retriever.py "<question>"`

This is the retriever's real output. It returns passages and sources, not a generated answer. The agent will use these passages to write cited explanations.

**5. Input:** "does my pet need to fast before surgery at the vet"
**Output (good match):**
```
[vet_visits.md] score=0.418
  Some procedures require fasting. For example, a pet may need to skip food for 8 to 12 hours before surgery or certain blood tests. Always ask the clinic what to do about the morning meal and medications before the visit.

[exercise.md] score=0.282
  Pets recovering from surgery or illness may be restricted from exercise. Follow the vet's instructions for rest.
```

**6. Input:** "sick dog meds"
**Output (miss):**
```
[exercise.md] score=0.167
  Puppies and senior dogs should have shorter, gentler sessions. ...

[feeding.md] score=0.154
  Avoid hard exercise for about one hour before and after a large meal. ...
```
The relevant `medication.md` passages are not returned, because the question shares no words with them ("meds" vs "medication", "sick" vs "antibiotics"). This is the main limit of keyword retrieval.

**7. Input:** "quarterly corporate tax filing deadlines"
**Output:** no results. The score cutoff drops unrelated chunks instead of returning junk.

### Guardrail examples (validators), from `python demo_guardrails.py`

The validators in `validators.py` check an AI-proposed plan before a person sees it. These runs use hand-written plans for a fixed owner (available 08:00–17:00), so the output is the same every time. Errors fail the plan. Warnings and `needs_human` are shown to the person approving it.

**Case 1: clean plan**
- **Input:** "Morning walk", explanation cites `exercise.md`, which was retrieved.
- **Behavior:** all three checks pass.
- **Result:** `ok=True needs_human=False`, no issues.

**Case 2: hallucinated source**
- **Input:** "Walk twice daily [dog_handbook.md]", but only `exercise.md` and `medication.md` were retrieved.
- **Behavior:** the grounding check sees a citation that was never retrieved.
- **Result:** `ok=False` with `ERROR [grounding] Cites 'dog_handbook.md', which was not retrieved.`

**Case 3: task outside availability**
- **Input:** "Night walk" at 20:00, but the owner is only available 08:00–17:00.
- **Behavior:** the rules check compares the task to the owner's `TimeSlot`s.
- **Result:** `ok=False` with `ERROR [rules] 'Night walk' is outside the owner's available time.`

**Case 4: unsafe medication advice**
- **Input:** "If you miss it, double the dose [medication.md]"
- **Behavior:** the safety check blocks advice that changes a dose, and also flags the item for a human.
- **Result:** `ok=False needs_human=True` with `ERROR [safety] Explanation changes a dose or schedule of a medicine.`

**Case 5: safe medication item**
- **Input:** "Antibiotics must be given for the full course [medication.md]"
- **Behavior:** nothing is wrong, but medication items always need human review.
- **Result:** `ok=True needs_human=True` with `WARNING [safety] Medication or vet-related item: human review required.`

The checks are covered by 17 tests in `tests/test_validators.py`. They are keyword-based, so they only catch the words they know (for example "vet" and "medication", but not "veterinarian").

### Retrieval before/after

The first retriever ranked generic words as matches. Two real failures, and the result after I added common words (`give`, `should`, `often`, `them`...) to the stopword list and stripped "-ing" endings:

| Query | Before | After |
|---|---|---|
| "my dog is on antibiotics, when should I give them" | top hit was a vet-visit sentence ("Treat vet appointments as the highest priority...", score 0.172); the antibiotics paragraph was second | top hit is `medication.md`: "Antibiotics must be given for the full prescribed course..." (score 0.23) |
| "how often should I feed my puppy" | top hit was from `medication.md` (the test failed) | top hit is `feeding.md` (the test passes) |

This was a hand fix for the queries I tried. It did not fix paraphrases: on the 12-question evaluation set (`python eval_retrieval.py`), direct questions score 6/6 but paraphrases only 2/6. The knowledge base is five custom documents in `kb/` (feeding, medication, exercise, grooming, vet visits), and each retrieved passage keeps its source file so it can be cited.

### End-to-end agent runs, from `python demo_agent.py`

Command: `python demo_agent.py` (add `--log` to save the traces to `ai_interactions.md`). The same flow runs from the **AI Plan Assistant** in the app. These runs use the sample owner in `sample_data.py` (plan day Oct 01, owner available 08:00–17:00) and the **offline mock explainer**, so they are repeatable. Output below is trimmed (the demo also prints a plan summary for each run).

**Run 1: normal request**
- **Input:** `Plan Max's day`
- **Output:**
```
1. PLAN      Request "Plan Max's day": covering Max on 2026-10-01 (pets named in the request)
2. ACT       Tool build_daily_schedule -> 2 task(s): Vet appointment, Grooming. Tool conflict_warnings -> 4 warning(s).
3. RETRIEVE  Per-task retrieval: Vet appointment -> vet_visits.md (0.375); Grooming -> vet_visits.md (0.217). Request retrieval: medication.md, vet_visits.md.
4. EXPLAIN   Attempt 1 via mock (offline, rule-based): drafted 2 item(s).
5. VALIDATE  Attempt 1: passed (3 warning(s), needs_human=True).

  14:00 Vet appointment (Max)
      'Vet appointment' has highest priority, is scheduled for 14:00 (once). It is #1 of 2 today: it has the highest priority of the day. It overlaps with 'Grooming'. Guidance: Treat vet appointments as the highest priority on the schedule, and do not overlap them with other tasks. [vet_visits.md]
  14:30 Grooming (Max)
      'Grooming' has low priority, is scheduled for 14:30 (once). It is #2 of 2 today: 'Vet appointment' comes first because it has higher priority (highest). It overlaps with 'Vet appointment'. Guidance: Plan extra time around a vet appointment. [vet_visits.md]

Result: ok=True used_fallback=False needs_human=True attempts=1
-> HUMAN CHECKPOINT: medication/vet items need the owner's review before approving.
```
The scheduler picked and ordered the tasks, retrieval attached a cited guideline to each, the plan passed validation, and the vet item was flagged for the human.

**Run 2: validator rejects a bad draft and the agent retries (injected fault)**
- **Input:** `Plan Buddy's day`. A deliberately faulty explainer wrapper makes the *first* draft cite `dog_handbook.md`, a file that was never retrieved.
- **Output:**
```
3. RETRIEVE  Per-task retrieval: Breakfast -> feeding.md (0.212); Evening walk -> exercise.md (0.258); Brushing -> grooming.md (0.327). ...
4. EXPLAIN   Attempt 1 ... + injected fault (1 bad attempt(s)): drafted 3 item(s).
5. VALIDATE  Attempt 1: FAILED with 1 error(s): [grounding] Cites 'dog_handbook.md', which was not retrieved.
6. EXPLAIN   Attempt 2 ... : drafted 3 item(s). Included validator feedback.
7. VALIDATE  Attempt 2: passed (0 warning(s), needs_human=False).

  08:00 Breakfast (Buddy)
      'Breakfast' has high priority, is scheduled for 08:00 (daily). It is #1 of 3 today: ... Guidance: Most adult dogs do well with two meals a day, roughly 8 to 12 hours apart, for example breakfast at 8:00 and dinner at 18:00. [feeding.md]

Result: ok=True used_fallback=False needs_human=False attempts=2
```
The grounding guardrail blocked an unsupported citation and the retry (given the error text) produced a valid plan.

**Run 3: every attempt fails and the agent falls back (injected fault)**
- **Input:** `Plan Joe's day`, with an explainer that always cites a made-up source.
- **Output:**
```
3. RETRIEVE  Per-task retrieval: Medication -> medication.md (0.217); Training session -> exercise.md (0.379); Playtime -> no match. ...
5. VALIDATE  Attempt 1: FAILED with 1 error(s): [grounding] Cites 'dog_handbook.md', which was not retrieved.
7. VALIDATE  Attempt 2: FAILED with 1 error(s): [grounding] Cites 'dog_handbook.md', which was not retrieved.
9. VALIDATE  Attempt 3: FAILED with 1 error(s): [grounding] Cites 'dog_handbook.md', which was not retrieved.
10. FALLBACK  All 3 attempts failed validation, so the plan uses the plain scheduler explanations with no AI text (valid=True).

  09:00 Medication (Joe)
      'Medication' has high priority, is scheduled for 09:00 (once). It is #1 of 3 today: it has the highest priority of the day.
  ...
Result: ok=True used_fallback=True needs_human=True attempts=3
-> HUMAN CHECKPOINT: medication/vet items need the owner's review before approving.
```
The owner still gets a correct plan, just without AI-written text. "Playtime" shows that retrieval can find nothing for a task (no citation, so a warning).

Each run's full step-by-step trace is saved in [`ai_interactions.md`](ai_interactions.md) (the three runs above were saved with `--log`). Runs started from the app also log the human's Approve or Reject there.

**What these runs do not show:** the explainer here is rule-based, so the *wording* is not generated by an LLM. The real Claude explainer has not been run against the live API.

## Design Decisions

- **Deterministic scheduler as the tool layer.** Ordering, overlap detection and availability fitting are plain Python, so they are testable and always correct. The AI proposes and explains but never edits data directly.
- **Stateless `Scheduler` over `Owner.get_all_tasks()`.** One source of truth, and planning happens across all pets at once.
- **RAG instead of relying on the model's memory.** Pet-care advice should cite sources the owner can inspect. Trade-off: retrieval quality now limits answer quality, and the knowledge base needs curating.
- **Validation before the human.** Cheap rule checks catch unknown or missing tasks, tasks outside availability, citations that were never retrieved, and dose-changing advice, so the owner only reviews plans that already pass. Trade-off: extra attempts when a draft fails.
- **Human approval is mandatory, and medication or vet items always get a warning.** Approve is disabled while errors remain. Slower than full automation, but medication-related mistakes are costly.
- **Deterministic fallback.** After 3 failed attempts the plan uses the scheduler's own explanations with no AI text, so the owner always gets a correct plan.
- **The agent is a fixed pipeline, not an open-ended loop.** PLAN, ACT, RETRIEVE, EXPLAIN and VALIDATE always run in that order, and only the explainer step is retried. This keeps the agent testable and its trace readable. Trade-off: it cannot decide to call tools in a different order or re-query the retriever on its own.
- **The explainer is swappable (offline mock or Claude).** The app and tests work with no API key. Trade-off: the mock's text is templated, and the Claude path is only tested with a fake client.
- **Retrieval is TF-IDF, not embeddings.** No extra dependencies and fully deterministic, but it only matches words (see the evaluation numbers below). The per-task query is the task name only, because adding the breed made breed words dominate ("Breakfast" for a Golden Retriever retrieved the grooming guide).
- **JSON file persistence** with atomic writes. Simple and dependency-free, at the cost of one owner per file.
- **Known scheduler trade-offs:** time comparisons ignore the date, tasks past midnight aren't handled, three simultaneous tasks give three pairwise warnings, and monthly recurrence can drift (Jan 31 → Feb 28 → Mar 28).

## Testing Summary

### Reliability results (summary)

- **Automated tests:** `python -m pytest` gives **87 passed, 1 expected failure (`xfail`)**. The xfail is the paraphrase-accuracy target, marked on purpose as a known retrieval weakness. The suite covers the scheduler, retriever, retrieval evaluation, validators (17 tests) and the agent (17 tests, using fake explainers and a fake Claude client).
- **Measured retrieval accuracy** (`python eval_retrieval.py`, 12 labelled questions): the right file was ranked first for **8 of 12 (67%)**. It was **6 of 6 (100%)** for questions that share words with the guides and only **2 of 6 (33%)** for paraphrased questions. Average top score was 0.349 for direct questions and 0.213 for paraphrases.
- **Confidence scores are not reliable here:** a wrong result scored 0.272 for "my cat's fur is getting tangled" (it returned a feeding chunk), higher than a correct result at 0.174 for "my puppy is hungry...". So the score can't be used to decide when to trust retrieval. The validators and the human checkpoint have to catch these cases, not a score threshold.
- **Logging:** every miss is written to `eval_failures.log` with the question, expected file and what was returned (for example `'sick dog meds'` got exercise, feeding and grooming). One question ("can I give the pills with dinner") returned a single wrong chunk.
- **Human evaluation:** I read the top results for each question to confirm the labels and to see why misses happened (no shared words, or a generic word like "dinner" pulling in the feeding guide).

How the numbers are guarded: `tests/test_retrieval_eval.py` fails if direct-question accuracy drops below 100% or overall accuracy drops below 65%, and marks the paraphrase target (80%) as an expected failure until the retriever is improved. The eval set is small (12 questions) and I wrote it myself, so treat the percentages as rough, not precise.

### Details

Before the AI layer was added, two display tests failed with a `ModuleNotFoundError` at `display.py:7` because `tabulate` was not installed in my Python. After `pip install tabulate wcwidth` (both are in `requirements.txt`) they pass. The whole suite was re-run after that and gives the 87 passed above.

- **What worked:** the scheduling logic tests cover sorting (including empty and tied times), recurrence (daily, weekly, biweekly, monthly, year-end and short-month rollover), conflict detection across pets (touching and completed tasks are not conflicts), empty owners and pets, filtering, completion, explanations, and the JSON save/load round trip including missing or corrupt files.
- **Retriever (RAG) tests:** `tests/test_retriever.py` adds 10 tests, all passing. They check that five different questions (antibiotics, feeding a puppy, walking a beagle, brushing a Golden Retriever, fasting before surgery) return the right knowledge-base file first, that unrelated or empty queries return nothing, that `k` limits results and scores come back in descending order, and that each hit carries a citable source file.
- **What worked:** retrieval returns the right source when the question shares words with the text. It is also deterministic and easy to test.
- **What didn't:**
  - **Retrieval only matches words.** It uses TF-IDF keyword matching, not meaning. I tried "sick dog meds" and it did not return `medication.md` at all (top hits were exercise, feeding and grooming chunks at 0.15–0.17), because the question shares no words with the medication text.
  - **Scores are generally low.** Even the best matches only scored about 0.23–0.42 (for example 0.386 for the Golden Retriever brushing question, 0.418 for the surgery fasting question), and weaker or partly relevant hits scored 0.1–0.2. Each chunk is a short paragraph and a query shares only a few words with it, so the score is not a reliable confidence value. I set a 0.05 cutoff by trying a few queries, so it is a guess and not a tuned value.
  - **Generic words caused wrong results.** My first version ranked a vet-visit sentence above the antibiotics paragraph, and "how often should I feed my puppy" returned a medication chunk. Adding common words like "give" and "should" to the stopword list and stripping "-ing" endings fixed both queries, but this was a hand fix for the examples I tried.
  - **Vague queries retrieve poorly.** "Plan Max's day, he is a labrador puppy" ranked a medication chunk first. The agent will need to build its query from the pet's actual tasks and details, not the raw request.
  - **Retrieval can attach a wrong or loosely related citation, and the validators cannot catch it.** The grounding check only verifies that a cited file was retrieved, not that it fits the task. In the demo, "Grooming" for Max cites `vet_visits.md` (a grooming mention inside the vet guide), and "Evening walk" cites a hot-weather tip even though the weather is not mentioned. The human checkpoint is the only guard for this.
  - **The safety check is a keyword list.** It misses words that are not on the list (for example "veterinarian"), and it does not understand negation, so guidance that says "never change the dose" would be flagged as dose-changing advice.
  - **Not covered yet:** the Claude explainer has not been run against the live API (only tested with a fake client). Date-ignoring comparisons and past-midnight tasks in the scheduler are known limitations without tests.
- **Agent and guardrail tests:** `tests/test_agent.py` checks that a named pet limits the plan, that the trace steps run in order, that a bad draft is retried with the validator's error text, that persistent failure falls back to scheduler text, that an explainer exception or a plan missing a task counts as a failed attempt, that the Claude reply parser handles fenced and invalid JSON, and that traces and human decisions are written to the log file.
- **What I learned:** edge cases (month ends, ties, back-to-back tasks) are where bugs hide in the scheduler. For RAG, "the tests pass" is not the same as "retrieval is good": my first tests used queries that share words with the text, so only the labelled evaluation (with paraphrases) showed the weakness. Running the agent end to end exposed a bug the unit tests missed: adding the breed to the retrieval query made breed words dominate, so a Golden Retriever's breakfast cited the grooming guide. Mocking the explainer kept the agent tests deterministic, and measuring retrieval separately from generation made it clear where problems come from. Embeddings would likely help with synonyms and give more meaningful scores.

## Reflection

Building PawPal+ taught me to design the system first and let AI do the part that needs language, not the part that needs correctness. Exact logic (time overlaps, recurrence) belongs in tested code, while AI is better for interpreting requests and explaining choices. The riskiest part of an AI feature is a confident answer nobody checks, so grounding, automated validation and a human decision matter as much as the model. My graded responsible-AI reflection (how I collaborated with AI, a suggestion I accepted and one I rejected or revised, and the system's limitations) is in [`model_card.md`](model_card.md).

---