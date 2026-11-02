from django.core.management import call_command
from django.test import TestCase

from .models import ScheduledClass, Timetable
from .services.solver import find_alternatives, generate_timetable, validate_timetable


class SolverTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")

    def test_generation_has_zero_violations(self):
        result = generate_timetable(time_limit_seconds=30.0)
        self.assertTrue(result.ok, result.message)
        tt = Timetable.objects.create(
            name="Test TT", solver_status=result.status,
            generation_seconds=round(result.seconds, 3),
        )
        ScheduledClass.objects.bulk_create(
            [ScheduledClass(timetable=tt, **p) for p in result.placements]
        )
        v = validate_timetable(tt)
        hard = sum(x for k, x in v.items() if k != "total_entries")
        self.assertEqual(hard, 0)
        self.assertGreater(v["total_entries"], 0)

    def test_lab_sessions_are_multi_period(self):
        result = generate_timetable(time_limit_seconds=30.0)
        self.assertTrue(result.ok, result.message)
        lab_placements = [
            p for p in result.placements if p["assignment"].course.requires_lab
        ]
        self.assertTrue(lab_placements)
        self.assertTrue(all(p["periods_count"] == 2 for p in lab_placements))

    def test_alternatives_are_offered(self):
        result = generate_timetable(time_limit_seconds=30.0)
        self.assertTrue(result.ok, result.message)
        tt = Timetable.objects.create(name="Test TT 2", solver_status=result.status)
        ScheduledClass.objects.bulk_create(
            [ScheduledClass(timetable=tt, **p) for p in result.placements]
        )
        entry = tt.entries.first()
        suggestions = find_alternatives(entry)
        self.assertIsInstance(suggestions, list)
