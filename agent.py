"""Planning agent: plan -> act (scheduler tools) -> retrieve (RAG) -> explain -> validate -> retry/fallback.

The scheduler stays the source of truth for WHICH tasks are planned and in what order.
The retriever finds guidance passages for each task. An "explainer" turns tasks + passages into
cited explanations. The validators check the result; on errors the explainer is re-run with the
validator feedback (up to max_retries), and if it still fails the agent falls back to the plain
deterministic scheduler explanations (no AI text). A person approves the plan in the UI.

Explainers:
  - MockExplainer   offline and deterministic (default when no API key is available)
  - ClaudeExplainer calls the Claude API; used when ANTHROPIC_API_KEY is set and `anthropic` is installed

Every run keeps a step-by-step trace that is written to ai_interactions.md.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Protocol

from pawpal_system import Owner, Scheduler, Task
from retriever import Retriever
from validators import Issue, ValidationResult, validate_plan

logger = logging.getLogger("pawpal.agent")

TRACE_LOG = Path(__file__).parent / "ai_interactions.md"
TRACE_HEADING = "## Agent Reasoning Traces (RAG + validation agent)"
MIN_SCORE = 0.1  # retrieval hits below this are ignored
DEFAULT_MODEL = "claude-opus-5-5"


# ---------------------------------------------------------------- explainers
class Explainer(Protocol):
    name: str

    def explain(self, tasks: list[Task], passages: dict[str, list[dict]], context: list[dict],
                scheduler: Scheduler, feedback: str = "") -> list[dict]: ...


def first_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s", text.strip())[0]


class MockExplainer:
    """Offline, rule-based. Cites the best retrieved passage for each task, or says none was found."""

    name = "mock (offline, rule-based)"

    def explain(self, tasks, passages, context, scheduler, feedback=""):
        items = []
        for task in tasks:
            base = scheduler.explain_choice(task, tasks)
            hits = passages.get(task.id, [])
            if hits:
                hit = hits[0]
                text = f"{base} Guidance: {first_sentence(hit['text'])} [{hit['source']}]"
                sources = [hit["source"]]
            else:
                text = f"{base} No matching guidance was found in the knowledge base."
                sources = []
            items.append({"task_id": task.id, "explanation": text, "sources": sources})
        return items


CLAUDE_SYSTEM = (
    "You write short explanations for a pet owner's daily plan. Use ONLY the guidance passages "
    "provided. Cite each passage you use as [file.md] inside the explanation and list those files in "
    "sources. If no passage applies to a task, cite nothing. Never advise changing, skipping, doubling "
    "or stopping a medication dose. Return only a JSON array with one object per task, in the given "
    "order, with keys: task_id, explanation, sources."
)


def parse_plan_json(text: str) -> list[dict]:
    """Parse the model's reply into a list of plan items. Raises ValueError if it isn't one."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"reply was not valid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError("reply must be a JSON array")
    return data


class ClaudeExplainer:
    """Asks Claude to write cited explanations. Needs ANTHROPIC_API_KEY (or another SDK credential)."""

    def __init__(self, model: str | None = None, client=None):
        self.model = model or os.environ.get("PAWPAL_MODEL", DEFAULT_MODEL)
        if client is None:
            import anthropic  # imported lazily so the app works without the package

            client = anthropic.Anthropic()
        self.client = client
        self.name = f"claude ({self.model})"

    def explain(self, tasks, passages, context, scheduler, feedback=""):
        payload = {
            "tasks": [
                {
                    "task_id": t.id, "name": t.name, "pet": t.pet.name if t.pet else None,
                    "breed": t.pet.breed if t.pet else None, "time": f"{t.time:%H:%M}",
                    "priority": t.priority.name.lower(),
                    "scheduler_reason": scheduler.explain_choice(t, tasks),
                    "passages": [{"source": h["source"], "text": h["text"]} for h in passages.get(t.id, [])],
                }
                for t in tasks
            ],
            "general_passages": [{"source": h["source"], "text": h["text"]} for h in context],
        }
        if feedback:
            payload["validator_feedback_fix_these"] = feedback
        response = self.client.messages.create(
            model=self.model, max_tokens=4000, output_config={"effort": "low"},
            system=CLAUDE_SYSTEM, messages=[{"role": "user", "content": json.dumps(payload)}],
        )
        return parse_plan_json("".join(b.text for b in response.content if b.type == "text"))


def make_explainer() -> Explainer:
    """Claude when a key and the SDK are available, otherwise the offline mock."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return ClaudeExplainer()
        except ImportError:
            logger.warning("ANTHROPIC_API_KEY is set but the 'anthropic' package is not installed; using mock")
    return MockExplainer()


# --------------------------------------------------------------------- agent
@dataclass
class AgentResult:
    day: date
    request: str
    explainer: str
    run_id: str
    tasks: list[Task] = field(default_factory=list)
    plan: list[dict] = field(default_factory=list)
    validation: ValidationResult = field(default_factory=ValidationResult)
    used_fallback: bool = False
    attempts: int = 0
    trace: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.validation.ok


def _coverage_issues(plan: list[dict], tasks: list[Task]) -> list[Issue]:
    present = {i.get("task_id") for i in plan if isinstance(i, dict)}
    return [Issue("error", "rules", f"Plan is missing task {t.name!r}.", t.id) for t in tasks if t.id not in present]


class PlanningAgent:
    def __init__(self, scheduler: Scheduler | None = None, retriever: Retriever | None = None,
                 explainer: Explainer | None = None, max_retries: int = 2):
        self.scheduler = scheduler or Scheduler()
        self.retriever = retriever or Retriever()
        self.explainer = explainer or make_explainer()
        self.max_retries = max_retries

    def run(self, owner: Owner, day: date, request: str = "") -> AgentResult:
        result = AgentResult(day=day, request=request, explainer=self.explainer.name,
                             run_id=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        def step(name: str, summary: str) -> None:
            result.trace.append({"step": name, "summary": summary})
            logger.info("agent %s: %s", name, summary)

        # 1. PLAN: decide which pets to cover from the request
        named = [p for p in owner.pets if p.name.lower() in request.lower()]
        pets = named or owner.pets
        step("PLAN", f"Request {request!r}: covering {', '.join(p.name for p in pets) or 'no pets'} "
                     f"on {day:%Y-%m-%d} " + ("(pets named in the request)" if named else "(no pet named, so all pets)"))

        # 2. ACT: use the scheduler as tools
        plan_tasks = self.scheduler.build_daily_schedule(owner, day)
        result.tasks = [t for t in plan_tasks if any(t.pet is p for p in pets)]
        warnings = self.scheduler.conflict_warnings(owner, day)
        step("ACT", f"Tool build_daily_schedule -> {len(result.tasks)} task(s): "
                    f"{', '.join(t.name for t in result.tasks) or 'none'}. "
                    f"Tool conflict_warnings -> {len(warnings)} warning(s).")
        if not result.tasks:
            step("DONE", "Nothing to plan, so no retrieval or explanation was needed.")
            return result

        # 3. RETRIEVE: guidance for each task, plus the request itself
        passages = {}
        for t in result.tasks:
            # Task name (plus description) only: adding the breed made breed words dominate the match,
            # e.g. "Breakfast Golden Retriever" retrieved the grooming guide.
            query = f"{t.name} {t.description}".strip()
            passages[t.id] = self.retriever.retrieve(query, k=2, min_score=MIN_SCORE)
        context = self.retriever.retrieve(request, k=2, min_score=MIN_SCORE) if request.strip() else []
        retrieved_sources = {h["source"] for hits in passages.values() for h in hits} | {h["source"] for h in context}
        found = "; ".join(
            f"{t.name} -> {passages[t.id][0]['source']} ({passages[t.id][0]['score']})" if passages[t.id]
            else f"{t.name} -> no match" for t in result.tasks
        )
        step("RETRIEVE", f"Per-task retrieval: {found}. Request retrieval: "
                         f"{', '.join(h['source'] for h in context) or 'no match'}.")

        # 4-5. EXPLAIN then VALIDATE, retrying with validator feedback
        feedback = ""
        for attempt in range(1, self.max_retries + 2):
            result.attempts = attempt
            try:
                draft = self.explainer.explain(result.tasks, passages, context, self.scheduler, feedback)
                step("EXPLAIN", f"Attempt {attempt} via {self.explainer.name}: drafted {len(draft)} item(s)."
                                + (" Included validator feedback." if feedback else ""))
                validation = validate_plan(draft, owner, day, retrieved_sources, self.scheduler)
                validation.issues.extend(_coverage_issues(draft, result.tasks))
            except Exception as exc:  # explainer or API failure counts as a failed attempt
                logger.error("agent explain failed on attempt %d: %s", attempt, exc)
                step("EXPLAIN", f"Attempt {attempt} via {self.explainer.name} failed: {exc}")
                draft = []
                validation = ValidationResult([Issue("error", "rules", f"Explainer failed: {exc}")])
            if validation.ok:
                step("VALIDATE", f"Attempt {attempt}: passed ({len(validation.warnings)} warning(s), "
                                 f"needs_human={validation.needs_human}).")
                result.plan, result.validation = draft, validation
                break
            feedback = validation.feedback()
            step("VALIDATE", f"Attempt {attempt}: FAILED with {len(validation.errors)} error(s): "
                             + " | ".join(f"[{i.check}] {i.message}" for i in validation.errors))
        else:
            # 6. FALLBACK: deterministic scheduler text, no AI-written content
            result.used_fallback = True
            result.plan = [{"task_id": t.id, "explanation": self.scheduler.explain_choice(t, result.tasks),
                            "sources": []} for t in result.tasks]
            result.validation = validate_plan(result.plan, owner, day, retrieved_sources, self.scheduler)
            step("FALLBACK", f"All {result.attempts} attempts failed validation, so the plan uses the plain "
                             f"scheduler explanations with no AI text (valid={result.validation.ok}).")
        return result


def setup_logging(path: str = "pawpal.log") -> None:
    """Send agent and validator log lines to a file instead of the console."""
    logging.basicConfig(filename=path, level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")


# ------------------------------------------------------------------- tracing
def format_trace(result: AgentResult) -> str:
    lines = [f"### Agent run {result.run_id}: plan for {result.day:%Y-%m-%d}",
             f"- **Request:** {result.request or '(none)'}",
             f"- **Explainer:** {result.explainer}"]
    lines += [f"{n}. **{s['step']}**: {s['summary']}" for n, s in enumerate(result.trace, 1)]
    for item in result.plan:
        lines.append(f"   - `{item['task_id'][:8]}` {item['explanation']}")
    for issue in result.validation.warnings:
        lines.append(f"   - warning [{issue.check}] {issue.message}")
    lines.append(f"- **Outcome:** ok={result.ok}, used_fallback={result.used_fallback}, "
                 f"needs_human={result.validation.needs_human}, attempts={result.attempts}")
    return "\n".join(lines) + "\n"


def _append(path: Path, text: str) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    prefix = "" if TRACE_HEADING in existing else (
        f"\n---\n\n{TRACE_HEADING}\n\nEach run's step-by-step reasoning (plan, tool calls, retrieval, "
        "validation, human decision), written by `agent.py`.\n\n")
    with path.open("a", encoding="utf-8") as f:
        f.write(prefix + text + "\n")


def write_trace(result: AgentResult, path: Path = TRACE_LOG) -> None:
    _append(path, format_trace(result))


def record_decision(result: AgentResult, decision: str, path: Path = TRACE_LOG) -> None:
    """Log the human's Approve / Reject for a run."""
    _append(path, f"- **Human decision for run {result.run_id}:** {decision} "
                  f"({datetime.now():%Y-%m-%d %H:%M:%S})")
