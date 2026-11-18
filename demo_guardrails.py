"""Show the validators catching bad AI plans. Run:  python demo_guardrails.py

Uses a small fixed owner and hand-written plans (no LLM), so the output is the same every run.
"""
from datetime import date, datetime, time

from pawpal_system import Owner, Pet, Priority, Task, TimeSlot
from validators import validate_plan

DAY = date(2026, 10, 1)


def build_owner():
    owner = Owner(name="Alice", age=30, schedule=[TimeSlot(time(8, 0), time(17, 0))])
    max_ = Pet(name="Max", breed="Labrador", age=3)
    owner.add_pet(max_)
    tasks = {
        "walk": Task("Morning walk", datetime(2026, 10, 1, 9, 0), Priority.MEDIUM, duration_minutes=30),
        "meds": Task("Antibiotic", datetime(2026, 10, 1, 13, 0), Priority.HIGH, duration_minutes=10,
                     description="medication"),
        "night": Task("Night walk", datetime(2026, 10, 1, 20, 0), Priority.LOW, duration_minutes=30),
    }
    for t in tasks.values():
        max_.add_task(t)
    return owner, tasks


def show(title, plan, owner, retrieved):
    result = validate_plan(plan, owner, DAY, retrieved)
    print(f"=== {title}")
    for item in plan:
        print(f"  plan item: task={owner_name(owner, item['task_id'])!r} sources={item.get('sources')} "
              f"text={item['explanation']!r}")
    print(f"  -> ok={result.ok}  needs_human={result.needs_human}")
    for issue in result.issues:
        print(f"     {issue.severity.upper():7} [{issue.check}] {issue.message}")
    if not result.issues:
        print("     (no issues)")
    print()


def owner_name(owner, task_id):
    return next((t.name for t in owner.get_all_tasks() if t.id == task_id), task_id)


if __name__ == "__main__":
    owner, t = build_owner()
    retrieved = {"exercise.md", "medication.md"}

    show("1. Clean plan",
         [{"task_id": t["walk"].id, "explanation": "Labs need 30-60 min of activity a day [exercise.md]",
           "sources": ["exercise.md"]}], owner, retrieved)

    show("2. Hallucinated source",
         [{"task_id": t["walk"].id, "explanation": "Walk twice daily [dog_handbook.md]",
           "sources": ["dog_handbook.md"]}], owner, retrieved)

    show("3. Task outside the owner's availability (08:00-17:00)",
         [{"task_id": t["night"].id, "explanation": "A late walk helps [exercise.md]",
           "sources": ["exercise.md"]}], owner, retrieved)

    show("4. Unsafe medication advice",
         [{"task_id": t["meds"].id, "explanation": "If you miss it, double the dose [medication.md]",
           "sources": ["medication.md"]}], owner, retrieved)

    show("5. Safe medication item (passes, but a human must review)",
         [{"task_id": t["meds"].id,
           "explanation": "Antibiotics must be given for the full course [medication.md]",
           "sources": ["medication.md"]}], owner, retrieved)
