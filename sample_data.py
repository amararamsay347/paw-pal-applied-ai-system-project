"""Sample owner used by the demos and tests (same data as the CLI demo in main.py)."""
from datetime import date, datetime, time

from pawpal_system import Frequency, Owner, Pet, Priority, Task, TimeSlot

SAMPLE_DAY = date(2026, 10, 1)


def build_sample_owner() -> Owner:
    owner = Owner(name="Alice", age=30, schedule=[TimeSlot(time(8, 0), time(17, 0))])
    buddy = Pet(name="Buddy", breed="Golden Retriever", age=5)
    max_ = Pet(name="Max", breed="Labrador", age=3)
    joe = Pet(name="Joe", breed="Beagle", age=4)
    for pet in (buddy, max_, joe):
        owner.add_pet(pet)

    def at(h, m=0):
        return datetime(2026, 10, 1, h, m)

    buddy.add_task(Task(name="Evening walk", time=at(16), priority=Priority.MEDIUM, duration_minutes=30))
    buddy.add_task(Task(name="Breakfast", time=at(8), priority=Priority.HIGH, duration_minutes=30,
                        frequency=Frequency.DAILY))
    buddy.add_task(Task(name="Brushing", time=at(11), priority=Priority.LOW, duration_minutes=30))
    max_.add_task(Task(name="Vet appointment", time=at(14), priority=Priority.HIGHEST, duration_minutes=60))
    max_.add_task(Task(name="Grooming", time=at(14, 30), priority=Priority.LOW, duration_minutes=45))
    joe.add_task(Task(name="Medication", time=at(9), priority=Priority.HIGH, duration_minutes=15))
    joe.add_task(Task(name="Training session", time=at(11), priority=Priority.MEDIUM, duration_minutes=30))
    joe.add_task(Task(name="Playtime", time=at(11), priority=Priority.LOW, duration_minutes=30))
    return owner
