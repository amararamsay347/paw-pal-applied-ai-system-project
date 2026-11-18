from datetime import date, datetime, time

import pytest

from pawpal_system import Frequency, Owner, Pet, Priority, Task, TimeSlot
from validators import validate_plan

DAY = date(2026, 10, 1)


def make_task(name, hour, minute=0, duration=30, **kw):
    return Task(name=name, time=datetime(2026, 10, 1, hour, minute), priority=Priority.MEDIUM,
                duration_minutes=duration, **kw)


@pytest.fixture
def world():
    owner = Owner(name="Alice", age=30, schedule=[TimeSlot(time(8, 0), time(17, 0))])
    pet = Pet(name="Max", breed="Lab", age=3)
    owner.add_pet(pet)
    t = {
        "walk": make_task("Walk", 9),
        "brush": make_task("Brushing", 11),
        "groom": make_task("Grooming", 11, 15),  # overlaps Brushing
        "meds": make_task("Antibiotic dose", 13, description="medication"),
        "late": make_task("Night walk", 20),  # outside 08:00-17:00
        "tomorrow": Task(name="Tomorrow walk", time=datetime(2026, 10, 2, 9), priority=Priority.LOW),
        "done": make_task("Done task", 10, completed=True),
    }
    for task in t.values():
        pet.add_task(task)
    return owner, t


def item(task, explanation="Good for the day [exercise.md]", sources=("exercise.md",)):
    return {"task_id": task.id, "explanation": explanation, "sources": list(sources)}


def run(plan, owner, sources=("exercise.md",)):
    return validate_plan(plan, owner, DAY, set(sources))


def test_clean_plan_passes_with_no_issues(world):
    owner, t = world
    result = run([item(t["walk"])], owner)
    assert result.ok and not result.issues and not result.needs_human


def test_unknown_task_id_is_error(world):
    owner, _ = world
    result = run([{"task_id": "nope", "explanation": "x [exercise.md]", "sources": ["exercise.md"]}], owner)
    assert not result.ok
    assert "unknown task id" in result.errors[0].message


def test_duplicate_task_is_error(world):
    owner, t = world
    assert not run([item(t["walk"]), item(t["walk"])], owner).ok


def test_completed_task_is_error(world):
    owner, t = world
    assert not run([item(t["done"])], owner).ok


def test_task_not_on_day_is_error(world):
    owner, t = world
    assert not run([item(t["tomorrow"])], owner).ok


def test_task_outside_availability_is_error(world):
    owner, t = world
    result = run([item(t["late"])], owner)
    assert not result.ok
    assert "available time" in result.errors[0].message


def test_overlap_is_warning_not_error(world):
    owner, t = world
    result = run([item(t["brush"]), item(t["groom"])], owner)
    assert result.ok
    assert any("overlap" in w.message for w in result.warnings)


def test_back_to_back_tasks_do_not_warn(world):
    owner, t = world
    t["groom"].reschedule(datetime(2026, 10, 1, 11, 30))  # starts exactly when Brushing ends
    assert not run([item(t["brush"]), item(t["groom"])], owner).warnings


def test_citing_unretrieved_source_is_error(world):
    owner, t = world
    result = run([item(t["walk"], "see [made_up.md]", ["made_up.md"])], owner)
    assert not result.ok
    assert any(i.check == "grounding" and "made_up.md" in i.message for i in result.errors)


def test_citation_in_text_only_is_also_checked(world):
    owner, t = world
    result = run([{"task_id": t["walk"].id, "explanation": "see [made_up.md]", "sources": []}], owner)
    assert not result.ok


def test_missing_citation_is_warning(world):
    owner, t = world
    result = run([{"task_id": t["walk"].id, "explanation": "just because", "sources": []}], owner)
    assert result.ok
    assert any(i.check == "grounding" for i in result.warnings)


def test_medication_task_needs_human(world):
    owner, t = world
    result = run([item(t["meds"])], owner)
    assert result.ok and result.needs_human


def test_vet_mention_in_explanation_needs_human(world):
    owner, t = world
    assert run([item(t["walk"], "Ask the vet first [exercise.md]")], owner).needs_human


def test_dose_changing_advice_is_error(world):
    owner, t = world
    result = run([item(t["meds"], "You can double the dose if missed [exercise.md]")], owner)
    assert not result.ok
    assert any(i.check == "safety" for i in result.errors)


def test_malformed_plan_is_reported_not_raised(world):
    owner, _ = world
    assert not run("not a plan", owner).ok
    assert not run([1, 2], owner).ok


def test_empty_plan_is_ok(world):
    owner, _ = world
    assert run([], owner).ok


def test_feedback_lists_errors_for_retry(world):
    owner, t = world
    result = run([item(t["late"])], owner)
    assert "[rules]" in result.feedback()
