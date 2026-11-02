"""End-to-end verification: generate a timetable from seeded data, save it,
validate that it has zero hard-constraint violations, and smoke-test the
web pages with Django's test client. Run after migrate + seed_demo:

    ./venv/bin/python verify_run.py
"""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "timetable_system.settings")
import django

django.setup()

from django.test import Client

from scheduler.models import ScheduledClass, Timetable
from scheduler.services.solver import generate_timetable, validate_timetable

result = generate_timetable(time_limit_seconds=30.0)
print("Solver status:", result.status, "| seconds:", round(result.seconds, 3))
if not result.ok:
    print("FAILED:", result.message)
    raise SystemExit(1)

tt = Timetable.objects.create(
    name="Winter 2026 — Verification Run",
    solver_status=result.status,
    generation_seconds=round(result.seconds, 3),
)
ScheduledClass.objects.bulk_create([ScheduledClass(timetable=tt, **p) for p in result.placements])

violations = validate_timetable(tt)
print("Violations:", violations)
hard = sum(v for k, v in violations.items() if k != "total_entries")
assert hard == 0, f"Expected zero hard violations, got {hard}"
assert violations["total_entries"] == len(result.placements) > 0

client = Client()
for url in ["/", f"/timetable/{tt.pk}/", f"/timetable/{tt.pk}/print/"]:
    resp = client.get(url)
    print("GET", url, "->", resp.status_code)
    assert resp.status_code == 200

print("VERIFICATION PASSED:", violations["total_entries"], "classes scheduled, 0 clashes.")
