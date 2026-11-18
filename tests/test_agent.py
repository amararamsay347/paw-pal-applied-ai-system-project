import json
from datetime import date

import pytest

from agent import (ClaudeExplainer, MockExplainer, PlanningAgent, make_explainer, parse_plan_json,
                   record_decision, write_trace)
from pawpal_system import Owner
from sample_data import SAMPLE_DAY, build_sample_owner


@pytest.fixture
def owner():
    return build_sample_owner()


class ScriptedExplainer:
    """Test double: runs a function per call and records the feedback it was given."""

    name = "scripted"

    def __init__(self, fn):
        self.fn, self.feedbacks = fn, []

    def explain(self, tasks, passages, context, scheduler, feedback=""):
        self.feedbacks.append(feedback)
        return self.fn(len(self.feedbacks), tasks, passages, context, scheduler)


def good(n, tasks, passages, context, scheduler):
    return MockExplainer().explain(tasks, passages, context, scheduler)


def bad(n, tasks, passages, context, scheduler):
    items = good(n, tasks, passages, context, scheduler)
    items[0]["sources"] = ["made_up.md"]
    return items


def test_pet_named_in_request_limits_the_plan(owner):
    result = PlanningAgent(explainer=MockExplainer()).run(owner, SAMPLE_DAY, "Plan Max's day")
    assert {t.pet.name for t in result.tasks} == {"Max"}
    assert result.ok and not result.used_fallback and result.attempts == 1


def test_no_pet_named_covers_all_pets(owner):
    result = PlanningAgent(explainer=MockExplainer()).run(owner, SAMPLE_DAY, "")
    assert {t.pet.name for t in result.tasks} == {"Buddy", "Max", "Joe"}


def test_plan_items_cite_only_retrieved_sources_and_match_scheduler_order(owner):
    result = PlanningAgent(explainer=MockExplainer()).run(owner, SAMPLE_DAY, "Plan Joe's day")
    assert [i["task_id"] for i in result.plan] == [t.id for t in result.tasks]
    assert result.ok
    for item in result.plan:
        assert all(s.endswith(".md") for s in item["sources"])


def test_trace_has_the_agent_steps_in_order(owner):
    result = PlanningAgent(explainer=MockExplainer()).run(owner, SAMPLE_DAY, "Plan Max's day")
    assert [s["step"] for s in result.trace] == ["PLAN", "ACT", "RETRIEVE", "EXPLAIN", "VALIDATE"]


def test_medication_and_vet_items_are_flagged_for_human_review(owner):
    result = PlanningAgent(explainer=MockExplainer()).run(owner, SAMPLE_DAY, "Plan Joe's day")
    assert result.validation.needs_human  # Joe has a Medication task


def test_bad_draft_is_retried_with_validator_feedback(owner):
    explainer = ScriptedExplainer(lambda n, *a: bad(n, *a) if n == 1 else good(n, *a))
    result = PlanningAgent(explainer=explainer).run(owner, SAMPLE_DAY, "Plan Buddy's day")
    assert result.attempts == 2 and result.ok and not result.used_fallback
    assert explainer.feedbacks[0] == ""
    assert "[grounding]" in explainer.feedbacks[1] and "made_up.md" in explainer.feedbacks[1]


def test_persistent_failure_falls_back_to_scheduler_text(owner):
    explainer = ScriptedExplainer(bad)
    result = PlanningAgent(explainer=explainer, max_retries=2).run(owner, SAMPLE_DAY, "Plan Buddy's day")
    assert result.used_fallback and result.attempts == 3 and len(explainer.feedbacks) == 3
    assert all(item["sources"] == [] for item in result.plan)
    assert result.ok  # the deterministic plan itself is valid
    assert result.trace[-1]["step"] == "FALLBACK"


def test_explainer_exception_counts_as_failed_attempt(owner):
    def boom(n, *a):
        raise RuntimeError("API down")

    result = PlanningAgent(explainer=ScriptedExplainer(boom), max_retries=1).run(owner, SAMPLE_DAY, "Plan Max's day")
    assert result.used_fallback and result.attempts == 2


def test_plan_missing_a_task_fails_validation(owner):
    explainer = ScriptedExplainer(lambda n, *a: good(n, *a)[:-1])  # drops the last task
    result = PlanningAgent(explainer=explainer, max_retries=0).run(owner, SAMPLE_DAY, "Plan Joe's day")
    assert result.used_fallback
    assert any("missing task" in s["summary"] for s in result.trace)


def test_nothing_to_plan_returns_empty_ok_plan():
    result = PlanningAgent(explainer=MockExplainer()).run(Owner(name="Empty", age=1), date(2026, 1, 1), "")
    assert result.plan == [] and result.ok and result.attempts == 0


def test_unmatched_task_gets_no_citation_and_a_warning(owner):
    result = PlanningAgent(explainer=MockExplainer()).run(owner, SAMPLE_DAY, "Plan Joe's day")
    playtime = next(i for i in result.plan if i["explanation"].startswith("'Playtime'"))
    assert playtime["sources"] == []
    assert any(w.check == "grounding" for w in result.validation.warnings)


# ---- Claude explainer (fake client, no network) ----
class FakeClient:
    def __init__(self, text):
        self.text, self.calls = text, []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        block = type("B", (), {"type": "text", "text": self.text})()
        return type("R", (), {"content": [block]})()


def test_claude_explainer_parses_fenced_json_and_sends_feedback(owner):
    agent = PlanningAgent(explainer=MockExplainer())
    tasks = PlanningAgent(explainer=MockExplainer()).run(owner, SAMPLE_DAY, "Plan Max's day").tasks
    reply = "```json\n" + json.dumps([{"task_id": t.id, "explanation": "ok", "sources": []} for t in tasks]) + "\n```"
    client = FakeClient(reply)
    explainer = ClaudeExplainer(model="test-model", client=client)
    items = explainer.explain(tasks, {}, [], agent.scheduler, feedback="[grounding] fix it")
    assert [i["task_id"] for i in items] == [t.id for t in tasks]
    sent = json.loads(client.calls[0]["messages"][0]["content"])
    assert sent["validator_feedback_fix_these"] == "[grounding] fix it"
    assert client.calls[0]["model"] == "test-model"


def test_claude_reply_that_is_not_json_becomes_a_failed_attempt(owner):
    explainer = ClaudeExplainer(model="m", client=FakeClient("Sure! Here is your plan."))
    result = PlanningAgent(explainer=explainer, max_retries=0).run(owner, SAMPLE_DAY, "Plan Max's day")
    assert result.used_fallback


@pytest.mark.parametrize("text", ["not json", '{"a": 1}'])
def test_parse_plan_json_rejects_bad_replies(text):
    with pytest.raises(ValueError):
        parse_plan_json(text)


def test_make_explainer_uses_mock_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert isinstance(make_explainer(), MockExplainer)


# ---- tracing ----
def test_trace_and_decision_are_written_to_log_file(owner, tmp_path):
    log = tmp_path / "ai_interactions.md"
    result = PlanningAgent(explainer=MockExplainer()).run(owner, SAMPLE_DAY, "Plan Max's day")
    write_trace(result, log)
    record_decision(result, "approved", log)
    text = log.read_text(encoding="utf-8")
    assert "Agent Reasoning Traces" in text and "**PLAN**" in text and "**VALIDATE**" in text
    assert "Human decision" in text and "approved" in text
