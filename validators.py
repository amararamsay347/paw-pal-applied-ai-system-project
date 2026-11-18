"""Automated guardrails for AI-proposed plans. Plain Python, no LLM involved.

An AI plan looks like:
    [{"task_id": "<Task.id>", "explanation": "... [medication.md]", "sources": ["medication.md"]}, ...]

validate_plan() runs three checks and returns a ValidationResult:
  - rules:     ids exist, tasks occur on the day and are pending, fit availability, no duplicates;
               overlapping tasks are reported as warnings (the owner's own data may contain them)
  - grounding: every cited source must be one the retriever actually returned
  - safety:    medication / vet content always goes to a human; dose-changing advice is an error

Errors make a plan fail (the agent retries, then falls back to the plain scheduler).
Warnings and needs_human are shown to the person approving the plan.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date

from pawpal_system import Owner, Scheduler

logger = logging.getLogger("pawpal.validators")

CITATION = re.compile(r"\[([\w\-]+\.md)\]")

# Words that mean a human must look at the plan item.
SENSITIVE = re.compile(
    r"\b(medic\w*|antibiotic\w*|pill\w*|dose\w*|dosage|insulin|surgery|vet|vaccin\w*|prescri\w*)\b",
    re.IGNORECASE,
)
# Advice that changes a dose or schedule of a medicine: never allowed from the AI.
DOSE_CHANGE = re.compile(
    r"\b(double (the )?dose|skip (the |a |your )?(dose|medication)|stop (giving|the) (medication|antibiotic)\w*"
    r"|increase (the )?dos\w*|decrease (the )?dos\w*|reduce (the )?dos\w*|change (the )?dos\w*)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Issue:
    severity: str  # "error" or "warning"
    check: str  # "rules", "grounding" or "safety"
    message: str
    task_id: str | None = None


@dataclass
class ValidationResult:
    issues: list[Issue] = field(default_factory=list)
    needs_human: bool = False

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        """True when there are no errors (warnings and needs_human don't fail a plan)."""
        return not self.errors

    def feedback(self) -> str:
        """Error text to feed back to the agent on a retry."""
        return "\n".join(f"- [{i.check}] {i.message}" for i in self.errors)


def check_rules(plan: list[dict], owner: Owner, day: date, scheduler: Scheduler | None = None) -> list[Issue]:
    scheduler = scheduler or Scheduler()
    issues: list[Issue] = []
    by_id = {t.id: t for t in owner.get_all_tasks()}
    seen: set[str] = set()
    planned = []
    for item in plan:
        tid = item.get("task_id")
        if not tid or tid not in by_id:
            issues.append(Issue("error", "rules", f"Plan refers to unknown task id {tid!r}.", tid))
            continue
        if tid in seen:
            issues.append(Issue("error", "rules", f"Task {by_id[tid].name!r} appears more than once.", tid))
            continue
        seen.add(tid)
        task = by_id[tid]
        planned.append(task)
        if task.completed:
            issues.append(Issue("error", "rules", f"{task.name!r} is already completed.", tid))
        if not task.occurs_on(day):
            issues.append(Issue("error", "rules", f"{task.name!r} does not occur on {day}.", tid))
        if owner.schedule and not scheduler._fits_schedule(task, owner.schedule):
            issues.append(Issue("error", "rules", f"{task.name!r} is outside the owner's available time.", tid))
    for i, a in enumerate(planned):
        for b in planned[i + 1:]:
            if scheduler._overlaps(a, b):
                issues.append(Issue("warning", "rules", f"{a.name!r} and {b.name!r} overlap.", a.id))
    return issues


def check_grounding(plan: list[dict], retrieved_sources: set[str] | list[str]) -> list[Issue]:
    allowed = set(retrieved_sources)
    issues: list[Issue] = []
    for item in plan:
        tid = item.get("task_id")
        cited = set(item.get("sources") or []) | set(CITATION.findall(item.get("explanation", "")))
        for src in sorted(cited - allowed):
            issues.append(Issue("error", "grounding", f"Cites {src!r}, which was not retrieved.", tid))
        if not cited:
            issues.append(Issue("warning", "grounding", "Explanation cites no source.", tid))
    return issues


def check_safety(plan: list[dict], owner: Owner) -> tuple[list[Issue], bool]:
    by_id = {t.id: t for t in owner.get_all_tasks()}
    issues: list[Issue] = []
    needs_human = False
    for item in plan:
        tid = item.get("task_id")
        task = by_id.get(tid)
        text = item.get("explanation", "")
        task_text = f"{task.name} {task.description}" if task else ""
        if DOSE_CHANGE.search(text):
            issues.append(Issue("error", "safety", "Explanation changes a dose or schedule of a medicine.", tid))
        if SENSITIVE.search(text) or SENSITIVE.search(task_text):
            needs_human = True
            issues.append(Issue("warning", "safety", "Medication or vet-related item: human review required.", tid))
    return issues, needs_human


def validate_plan(
    plan: list[dict],
    owner: Owner,
    day: date,
    retrieved_sources: set[str] | list[str],
    scheduler: Scheduler | None = None,
) -> ValidationResult:
    """Run all checks. Never raises on a malformed plan; it reports errors instead."""
    if not isinstance(plan, list) or not all(isinstance(i, dict) for i in plan):
        result = ValidationResult([Issue("error", "rules", "Plan must be a list of objects.")])
        logger.error("validation: malformed plan")
        return result
    safety_issues, needs_human = check_safety(plan, owner)
    result = ValidationResult(
        issues=check_rules(plan, owner, day, scheduler) + check_grounding(plan, retrieved_sources) + safety_issues,
        needs_human=needs_human,
    )
    logger.info("validation: ok=%s errors=%d warnings=%d needs_human=%s",
                result.ok, len(result.errors), len(result.warnings), result.needs_human)
    for issue in result.issues:
        logger.log(logging.ERROR if issue.severity == "error" else logging.WARNING,
                   "validation %s [%s] %s", issue.severity, issue.check, issue.message)
    return result
