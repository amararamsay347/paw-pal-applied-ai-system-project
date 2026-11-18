# PawPal+ — Agentic, Retrieval-Grounded Pet Care Planner

## Original Project (Modules 1–3): PawPal+

This project extends **PawPal+**, the Streamlit pet-care scheduler I built in Modules 1–3. The original goal was to help a busy owner stay consistent with pet care: track tasks (walks, feeding, meds, grooming) across several pets, respect the owner's available time and task priorities, and produce a daily plan that explains why each task landed where it did. It could sort and filter tasks, detect overlapping tasks across pets, handle recurring tasks (daily, weekly, biweekly, monthly), save data to `data.json`, and ship with an automated pytest suite.

## Title and Summary

**PawPal+ with Agentic Workflow, RAG and Validation** adds an AI layer on top of that deterministic scheduler. The owner can ask in plain language ("Plan Max's day, he's on antibiotics"). A **retriever** pulls relevant pet-care facts from a knowledge base, and an **agent** plans, calls the existing `Scheduler` tools, and proposes a plan with cited explanations. Automated **validators** check the result, and a **human** approves it before anything is saved.

**Why it matters:** pet care involves medication and vet timing, where a confident but wrong AI answer can hurt an animal. Grounding answers in retrieved sources, checking them with rules, and keeping the owner in the loop makes the AI useful without trusting it blindly.

> **Status:** the scheduler, UI, persistence and tests are implemented and working. The retriever, agent, and validators are the designed extension shown in the system diagram. Items marked *(planned)* below are not built yet.

## Architecture Overview

The full diagram is in [`diagrams/system_diagram_rag_agent.mmd`](diagrams/system_diagram_rag_agent.mmd) (the older class diagram is `diagrams/uml_final.mmd`). Data flows in four stages:

1. **Input** — The owner uses the Streamlit forms (owner, pets, tasks) and a free-text request.
2. **Process**
   - A *context builder* reads the owner's data through `Owner.get_all_tasks()`.
   - The *retriever* embeds a query built from species, breed, age, task names and the request, and searches a vector store of pet-care documents (top-k, then filter and rerank, keeping source ids).
   - The *agent* loops through plan → act → propose. Its tools are the existing `Scheduler` methods (`build_daily_schedule`, `find_next_available_slot`, `conflict_warnings`, `explain_choice`). It can re-query the retriever if it needs more facts.
3. **Validation** — Three automated checks run in order: *rules* (no conflicts, fits `TimeSlot`s, valid enums and schema), *grounding* (every claim cites a retrieved source), and *safety* (medication and vet advice flagged). A failure retries the agent with feedback up to 2 times, then falls back to the plain deterministic schedule with no AI text.
4. **Human checkpoint and output** — The owner sees the plan, its sources and warnings, and chooses **Approve / Edit / Reject**. Edit uses the existing reschedule/delete panel. Approved plans are saved to `data.json`, with an optional `Reminder`.

**Testing is involved at three points:** pytest unit tests for the scheduler and (planned) validators; a retrieval evaluation set that scores the retriever's hit-rate *(planned)*; and agent regression scenarios with the LLM mocked *(planned)*. A run log of requests, retrieved chunks, validator results and human decisions feeds failures back into new test cases *(planned)*.

### Key files

| File | Role |
|------|------|
| `pawpal_system.py` | Logic layer: `Owner`, `Pet`, `Task`, `TimeSlot`, `Reminder`, `Scheduler`, JSON save/load |
| `app.py` | Streamlit UI |
| `main.py` | CLI demo (1 owner, 3 pets, 8 tasks) |
| `display.py` | Terminal tables, colors, emojis |
| `tests/test_pawpal.py` | Automated tests |
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
7. *(Planned, for the AI layer)* set your model API key as an environment variable, build the knowledge base with the ingest script, then start the app. Pet and task data is saved to `data.json` in the folder you launch from; delete it to reset.

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

*(Planned)* Once the agent exists, add examples showing a free-text request, the retrieved sources, the validated plan, and the human decision, using real logged output rather than invented text.

## Design Decisions

- **Deterministic scheduler as the tool layer.** Ordering, overlap detection and availability fitting are plain Python, so they are testable and always correct. The AI proposes and explains but never edits data directly.
- **Stateless `Scheduler` over `Owner.get_all_tasks()`.** One source of truth, and planning happens across all pets at once.
- **RAG instead of relying on the model's memory.** Pet-care advice should cite sources the owner can inspect. Trade-off: retrieval quality now limits answer quality, and the knowledge base needs curating.
- **Validation before the human.** Cheap rule checks catch conflicts and malformed output so the owner only reviews plans that already pass. Trade-off: extra latency and retries.
- **Human approval is mandatory, and safety-flagged items always go to the human.** Slower than full automation, but medication-related mistakes are costly.
- **Deterministic fallback.** If the agent keeps failing validation, the owner still gets a correct plan.
- **JSON file persistence** with atomic writes. Simple and dependency-free, at the cost of one owner per file.
- **Known scheduler trade-offs:** time comparisons ignore the date, tasks past midnight aren't handled, three simultaneous tasks give three pairwise warnings, and monthly recurrence can drift (Jan 31 → Feb 28 → Mar 28).

## Testing Summary

### Reliability results (summary)

- **Automated tests:** 51 passed, 2 failed, 1 expected failure (`xfail`) in the latest `python -m pytest` run. The 2 failures are an environment problem (below), and the xfail is a known retrieval weakness that is tracked on purpose.
- **Measured retrieval accuracy** (`python eval_retrieval.py`, 12 labelled questions): the right file was ranked first for **8 of 12 (67%)**. It was **6 of 6 (100%)** for questions that share words with the guides and only **2 of 6 (33%)** for paraphrased questions. Average top score was 0.349 for direct questions and 0.213 for paraphrases.
- **Confidence scores are not reliable here:** a wrong result scored 0.272 for "my cat's fur is getting tangled" (it returned a feeding chunk), higher than a correct result at 0.174 for "my puppy is hungry...". So the score can't be used to decide when to trust retrieval. The validators and the human checkpoint have to catch these cases, not a score threshold.
- **Logging:** every miss is written to `eval_failures.log` with the question, expected file and what was returned (for example `'sick dog meds'` got exercise, feeding and grooming). One question ("can I give the pills with dinner") returned a single wrong chunk.
- **Human evaluation:** I read the top results for each question to confirm the labels and to see why misses happened (no shared words, or a generic word like "dinner" pulling in the feeding guide).

How the numbers are guarded: `tests/test_retrieval_eval.py` fails if direct-question accuracy drops below 100% or overall accuracy drops below 65%, and marks the paraphrase target (80%) as an expected failure until the retriever is improved. The eval set is small (12 questions) and I wrote it myself, so treat the percentages as rough, not precise.

### Details

I ran `python -m pytest` before adding the retriever: **38 passed, 2 failed**. Both failures (`test_task_emoji_matches_keywords_and_defaults`, `test_tasks_table_marks_conflicts_and_handles_empty`) are a `ModuleNotFoundError` raised at `display.py:7` in the Python I used, which means a display dependency from `requirements.txt` wasn't installed there. Running `pip install -r requirements.txt` should fix it, but I haven't re-run to confirm.

- **What worked:** the scheduling logic tests cover sorting (including empty and tied times), recurrence (daily, weekly, biweekly, monthly, year-end and short-month rollover), conflict detection across pets (touching and completed tasks are not conflicts), empty owners and pets, filtering, completion, explanations, and the JSON save/load round trip including missing or corrupt files.
- **Retriever (RAG) tests:** `tests/test_retriever.py` adds 10 tests, all passing. They check that five different questions (antibiotics, feeding a puppy, walking a beagle, brushing a Golden Retriever, fasting before surgery) return the right knowledge-base file first, that unrelated or empty queries return nothing, that `k` limits results and scores come back in descending order, and that each hit carries a citable source file.
- **What worked:** retrieval returns the right source when the question shares words with the text. It is also deterministic and easy to test.
- **What didn't:**
  - **Retrieval only matches words.** It uses TF-IDF keyword matching, not meaning. I tried "sick dog meds" and it did not return `medication.md` at all (top hits were exercise, feeding and grooming chunks at 0.15–0.17), because the question shares no words with the medication text.
  - **Scores are generally low.** Even the best matches only scored about 0.23–0.42 (for example 0.386 for the Golden Retriever brushing question, 0.418 for the surgery fasting question), and weaker or partly relevant hits scored 0.1–0.2. Each chunk is a short paragraph and a query shares only a few words with it, so the score is not a reliable confidence value. I set a 0.05 cutoff by trying a few queries, so it is a guess and not a tuned value.
  - **Generic words caused wrong results.** My first version ranked a vet-visit sentence above the antibiotics paragraph, and "how often should I feed my puppy" returned a medication chunk. Adding common words like "give" and "should" to the stopword list and stripping "-ing" endings fixed both queries, but this was a hand fix for the examples I tried.
  - **Vague queries retrieve poorly.** "Plan Max's day, he is a labrador puppy" ranked a medication chunk first. The agent will need to build its query from the pet's actual tasks and details, not the raw request.
  - **Not covered yet:** the agent and validators are not built, so they have no tests. Date-ignoring comparisons and past-midnight tasks in the scheduler are known limitations without tests.
- **What I learned:** edge cases (month ends, ties, back-to-back tasks) are where bugs hide in the scheduler. For RAG, "the tests pass" is not the same as "retrieval is good": my tests used queries that share words with the text, so they can't show how it handles paraphrases. A larger evaluation set with differently worded questions would show this. Moving to embeddings would likely help with synonyms and give more meaningful scores. For the AI layer, the plan is to mock the LLM so tests stay deterministic, and to measure retrieval separately from generation.

## Reflection

Building PawPal+ taught me to design the system first and let AI do the part that needs language, not the part that needs correctness. Exact logic (time overlaps, recurrence) belongs in tested code, while AI is better for interpreting requests and explaining choices. The riskiest part of an AI feature is a confident answer nobody checks, so grounding, automated validation and a human decision matter as much as the model. My graded responsible-AI reflection (how I collaborated with AI, a suggestion I accepted and one I rejected or revised, and the system's limitations) is in [`model_card.md`](model_card.md).

---

*The previous Module 2 README, with the full feature list, persistence notes and complete CLI output, is kept as `README_module2_original.md`.*