"""End-to-end demo of the planning agent. Run:  python demo_agent.py [--log]

Three runs on the sample owner (see sample_data.py):
  1. Normal run          - retrieval + explanation pass validation first time
  2. Retry (injected)    - the first draft cites a source that was never retrieved; the validator
                           rejects it and the agent retries with feedback
  3. Fallback (injected) - the explainer keeps citing bogus sources, so the agent falls back to the
                           plain scheduler explanations

Cases 2 and 3 use a deliberately faulty explainer (clearly labelled) so the guardrails can be seen
working. Uses the real Claude explainer if ANTHROPIC_API_KEY is set, otherwise the offline mock.
With --log, each run's trace is appended to ai_interactions.md.
"""
import sys

from agent import AgentResult, PlanningAgent, make_explainer, setup_logging, write_trace
from sample_data import SAMPLE_DAY, build_sample_owner


class FaultyExplainer:
    """DEMO ONLY: wraps a real explainer and corrupts its output to exercise the guardrails."""

    def __init__(self, inner, bad_attempts: int):
        self.inner, self.bad_attempts, self.calls = inner, bad_attempts, 0
        self.name = f"{inner.name} + injected fault ({bad_attempts} bad attempt(s))"

    def explain(self, tasks, passages, context, scheduler, feedback=""):
        self.calls += 1
        items = self.inner.explain(tasks, passages, context, scheduler, feedback)
        if self.calls <= self.bad_attempts:
            items[0]["sources"] = ["dog_handbook.md"]
            items[0]["explanation"] += " See [dog_handbook.md]"
        return items


def show(title: str, result: AgentResult) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")
    print(f"Request: {result.request!r}   Explainer: {result.explainer}")
    for n, s in enumerate(result.trace, 1):
        print(f"{n}. {s['step']:9} {s['summary']}")
    print("\nPlan:")
    for item in result.plan:
        task = next(t for t in result.tasks if t.id == item["task_id"])
        print(f"  {task.time:%H:%M} {task.name} ({task.pet.name})\n      {item['explanation']}")
    for w in result.validation.warnings:
        print(f"  ! warning [{w.check}] {w.message}")
    print(f"\nResult: ok={result.ok} used_fallback={result.used_fallback} "
          f"needs_human={result.validation.needs_human} attempts={result.attempts}")
    if result.validation.needs_human:
        print("-> HUMAN CHECKPOINT: medication/vet items need the owner's review before approving.")


if __name__ == "__main__":
    log = "--log" in sys.argv
    setup_logging()  # log lines go to pawpal.log
    owner = build_sample_owner()
    real = make_explainer()
    runs = [
        ("CASE 1: normal run", "Plan Max's day", real),
        ("CASE 2: validator rejects a bad draft, agent retries (injected fault)",
         "Plan Buddy's day", FaultyExplainer(real, bad_attempts=1)),
        ("CASE 3: every attempt fails, agent falls back to the scheduler (injected fault)",
         "Plan Joe's day", FaultyExplainer(real, bad_attempts=99)),
    ]
    for title, request, explainer in runs:
        result = PlanningAgent(explainer=explainer).run(owner, SAMPLE_DAY, request)
        show(title, result)
        if log:
            write_trace(result)
    print("\nTraces appended to ai_interactions.md" if log else "\n(run with --log to save traces to ai_interactions.md)")
