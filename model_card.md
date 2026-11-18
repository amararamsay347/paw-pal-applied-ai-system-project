# Model Card: PawPal+ AI Plan Assistant

## 1. System Overview

**Base project:** PawPal+ (Modules 1–3), a Streamlit pet-care scheduler that sorts, filters and prioritizes tasks across pets, detects overlaps, handles recurring tasks and saves to `data.json`.

**What was added in this project:**
- **RAG:** `retriever.py` searches 5 short guides in `kb/` with TF-IDF keyword matching and returns passages with their source file.
- **Agent:** `agent.py` runs plan, act (scheduler tools), retrieve, explain, validate, retry, fallback, and records a trace of each step in `ai_interactions.md`.
- **Guardrails:** `validators.py` checks rules, grounding and safety.
- **Human checkpoint:** the owner approves or rejects the plan in the app.
- **Evaluation:** `eval_retrieval.py` measures retrieval accuracy on 12 labelled questions.

**Intended use:** helping one pet owner plan a day of care tasks, with cited explanations.
**Not intended for:** veterinary or medical decisions, dosing, diagnosis, or anything where nobody reviews the output.

## 2. How I Used AI During Development

I used Claude Code (an AI coding assistant) throughout this project, and it wrote most of the code and documentation at my direction. I want to be clear about that split.

**What I asked the AI to do:**
- Read my existing PawPal+ code and draft the system architecture diagram as a Mermaid file.
- Write the README to match the assignment's required sections.
- Build the retriever and knowledge base, then the validators, then the agent, and wire the agent into the Streamlit app.
- Write the tests and the evaluation script, and run them.
- Read the grading rubric and submission checklist screenshots I pasted and tell me what was done and what was missing.

**What I did myself:**
- I decided the direction and the priorities, for example asking for the cheap rubric points first, then asking to implement the agent, diagram update and README update.
- When I did not understand how to implement the features, I said so ("how am I supposed to implement these features"), and asked the AI to break it into steps.
- I asked for proof that the system works and not only that it looks like it works, which led to the evaluation set and the guardrail demo.
- I reported what I learned from the results (the RAG works, but only on word matches, and the scores are generally low) and had it written into the testing summary.

**How the AI's work was checked:** the AI ran the test suite (87 passing, 1 expected failure), ran the demo scripts and showed the output, ran the real Streamlit app through Streamlit's test harness, and I reviewed the results and the rubric status before moving on. The README labels which outputs came from the offline mock explainer and which parts have not been run live.

## 3. One Suggestion I Accepted

**The AI broke the work into small steps and recommended a simple keyword (TF-IDF) retriever instead of a vector database.** After I said I was confused about implementation, the AI proposed: knowledge base, then retriever, then validators, then agent, then wiring into the app, and proposed pure-Python TF-IDF instead of Chroma or FAISS. I accepted this ("yes") and we started with the knowledge base and retriever.

**Why it was good:** it gave me something working and testable at each step, with no extra dependencies, and the output was deterministic so tests could check it. **How it was checked:** the retriever was run on real queries and 10 unit tests were written for it. Its weaknesses also became visible quickly, which let me measure them (see sections 5 and 6) instead of hiding them behind a more complicated system.

## 4. One Suggestion I Rejected or Revised

I revised two of the AI's own earlier designs after checking them against reality.

**1. The first system diagram was revised to match the code.** The first diagram showed Chroma/FAISS, reranking, an `ingest.py` script and a run log, none of which existed. After checking the rubric, which requires the diagram to match the actual implementation, I had the diagram rewritten so that every box maps to a real file. I had the AI correct a smaller error too: the knowledge base is read when the agent is created, not at app startup.

**2. The retrieval query was revised after a bug showed up in the end-to-end demo.** The agent's first version searched with the task name plus the pet's breed. Running the demo showed breed words took over: a Golden Retriever's "Breakfast" cited the grooming guide, and a Beagle's "Medication" cited the exercise guide. The unit tests had not caught this. The query was changed to the task name only, and the same demo then retrieved `feeding.md` and `medication.md`.


## 5. Testing and Results

**What was measured** (run `python -m pytest` and `python eval_retrieval.py` to reproduce):

| Check | Result |
|---|---|
| Full test suite | 87 passed, 1 expected failure (`xfail`) |
| Retrieval, direct questions (words overlap the guides) | right file ranked first for 6 of 6 |
| Retrieval, paraphrased questions | right file ranked first for 2 of 6 |
| Retrieval overall | 8 of 12 (67%) |
| Validator demo (`demo_guardrails.py`) | caught a made-up citation, a task outside availability and dose-changing advice; flagged a safe medication item for human review |
| Agent demo (`demo_agent.py`) | normal run passed first try; injected bad draft was retried and passed; persistent failure fell back to scheduler text |

**What I observed:**
- Retrieval scores are low (best matches 0.2–0.4) and do not tell right from wrong: a wrong result scored 0.272 while a correct one scored 0.174.
- The grounding check cannot tell whether a cited source is relevant, only that it was retrieved. A grooming task cited `vet_visits.md`.
- The demo runs use an offline mock explainer. **The Claude explainer has not been run against the live API.**
- Cases 2 and 3 of the agent demo use a deliberately injected fault, so they show the guardrails working and are not natural failures.

**What the testing showed me:** the system works well when a question shares words with the guides and badly when it is worded differently (6 of 6 versus 2 of 6). That gap only appeared once I built a labelled evaluation set with paraphrased questions, because my first retriever tests all used questions that overlapped with the text and passed. What surprised me most was that a wrong answer could score higher than a right one, so I cannot use the score to decide when to trust a result, and the validators and the human have to catch bad retrievals. Running the agent end to end also found a bug (the breed words) that the unit tests missed. Next I would test with a much larger and more varied question set, try embeddings for synonyms, run the real Claude explainer, and add a check that a citation is actually relevant to the task.

## 6. Biases and Limitations

**Known limitations:**
- **Keyword retrieval:** "sick dog meds" does not find the medication guide because no words match.
- **Tiny, self-written knowledge base:** 5 files, written for this project from general pet-care knowledge, not reviewed by a veterinarian.
- **Dogs dominate the guides:** the exercise guide is only about dogs, and feeding and grooming mention cats briefly; other animals have no coverage.
- **Keyword safety check:** it misses words not on its list (for example "veterinarian") and does not understand negation, so "never change the dose" would be flagged as dose-changing advice.
- **Small evaluation set:** 12 questions written by me, with the AI's help, so the accuracy numbers are rough.
- **Scheduler limits:** comparisons ignore the date, tasks that run past midnight are not handled, monthly recurrence can drift.
- **Approval is only logged:** approving a plan does not change `data.json`.

**Who this could serve badly:** owners of cats, exotic pets, or pets with special medical needs, because the knowledge base mostly covers healthy adult dogs and has nothing on those cases. A question phrased differently from the guides (for example "sick dog meds") can silently miss the relevant guidance and return an unrelated passage, with a score that looks plausible.

**What could go wrong if the output is trusted without reading it:** a medication or vet item could carry a loosely related citation that looks authoritative. The system only warns about these items. It does not check whether the cited passage actually applies, and the guides are general pet-care text, not medical advice.

**How my own choices shape the results:** I decided what went into the knowledge base and wrote the test questions, so the system is tuned to the topics and wording I thought of. The direct questions I wrote overlapped with the guide text, which made the first results look better than they were.

**What I would change first:** replace the keyword retrieval with embeddings and a bigger evaluation set, have a vet-reviewed knowledge base, and add a check that a citation is relevant to the task, not only that it was retrieved.

## 7. Misuse and Safeguards

**Safeguards built in:** validators block dose-changing advice and uncited sources, medication and vet items always show a review notice, Approve is disabled while errors remain, and a deterministic fallback replaces failing AI text.

**How it could be misused or over-trusted:**
- Someone could treat the plan's explanations as veterinary advice. The guides are general and unreviewed.
- Someone could approve a medication plan without reading it because the plan "passed validation". Passing only means the checks I wrote did not fire.
- The safety check is a keyword list, so differently worded advice about doses or skipping medication could get through.
- The offline mock explainer produces templated text that can look like an AI answer even though it is rule-based.

**What the safeguards do not cover:** whether a citation is relevant to the task, whether advice is medically correct for a particular pet, and anything the keyword list does not recognize. **What I would add:** a relevance check on citations, a veterinarian-reviewed knowledge base, a stronger safety check than keywords, and a clearer on-screen label showing when the explainer is the offline mock.

## 8. Reflection

I was confused at the start about how to even add RAG and an agent to my project, so the biggest thing I learned is that it's way easier when you break it into small steps and test each one. The part that has to be exactly right, like the schedule and the conflicts, stays as normal code. The AI part only explains the plan and cites where the info came from.

I also learned that "my tests pass" doesn't mean it actually works. My retriever passed all the tests I wrote first, but when I tested it with questions worded differently it only got 2 out of 6. It only works when the words match, and the scores are pretty low. I also didn't find the breed bug until I ran the whole agent from start to finish.

