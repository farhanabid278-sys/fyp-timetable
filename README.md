# University Timetable Management System — FYP

A web-based system that **generates university timetables automatically** using
constraint programming (Google OR-Tools CP-SAT) instead of manual scheduling.
Built with **Python + Django**, modelled on the real Winter 2026 department
timetable (Mon–Fri, 50-minute periods, 08:00–18:20, morning/evening sections).

## What works in this version (complete build)

- **Data management (Django Admin):** teachers, courses, classrooms/labs,
  sections, teaching assignments, and teacher availability/unavailability.
- **Automated generation (CP-SAT):** one click produces a complete timetable.
- **Hard constraints — a generated timetable violates none of them:**
  no teacher clash, no room clash, no section clash, teacher availability
  respected, room capacity respected, lab courses only in labs, classes only
  inside the section's shift (morning periods 1–6, evening 7–11 & 13), each
  assignment's sessions spread across different days, teacher weekly load cap.
- **Soft objective:** earlier periods preferred, so schedules stay compact.
- **Validation/evaluation:** every timetable page reports clash counts,
  solver status and generation time (evaluation metrics for the FYP report).
- **Publish safety:** a timetable with any hard violation cannot be published.
- **Views & export:** dashboard, per-section timetable grid, and a printable
  all-sections view (browser Print → Save as PDF).
- **Real-data import:** `python manage.py import_sheet data/winter2026.xlsx`
  parses the official Winter 2026 spreadsheet (Dept. of Computer Science, UAF)
  into 931 class entries — 151 teachers, 111 courses, 45 rooms, 72 sections —
  stored as a published timetable (imported assignments are reference data,
  excluded from generation until curated).
- **Teacher & student portals:** published timetables viewable per teacher
  and per section; a teacher can be linked to a login account.
- **Manual editing:** move any class with automatic clash checking, plus
  one-click clash-free reschedule suggestions.
- **Multi-period sessions:** practical/lab classes occupy 2 consecutive
  periods; clash checks cover every occupied period, and combined classes
  (same course/teacher/room, several sections) are not falsely flagged.
- **Evaluation page:** live violation metrics for every timetable, generated
  or imported — the imported manual timetable shows 9 teacher and 19 section
  double-bookings found by the validator.
- **Tests:** `python manage.py test` — generation, lab placement and the
  suggestion engine are covered; `verify_run.py` re-checks everything.
- **Report:** `FYP_REPORT.md` / `FYP_REPORT.docx` — full project report with
  design, constraint model and evaluation results.

## Verified result

Seed data (10 teachers, 6 rooms, 5 sections, 12 courses, 15 assignments):
the solver found an **OPTIMAL** timetable — **34 classes in ~2 seconds with
0 clashes** of every type (including 2-period lab sessions). See
`SAMPLE_OUTPUT.md`. The imported real timetable and full evaluation
results are described in `FYP_REPORT.md`.

## Run it

```bash
cd fyp-timetable
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo        # demo data from the real timetable structure
python manage.py createsuperuser  # for /admin/ data entry
python manage.py runserver
```

Open http://127.0.0.1:8000/ → **Generate Timetable** → view, publish, print.
Re-verify any time with `python verify_run.py`.

Development uses SQLite. For PostgreSQL set `DB_ENGINE=postgresql` plus
`DB_NAME/DB_USER/DB_PASSWORD/DB_HOST` environment variables (and install
`psycopg`) — see `timetable_system/settings.py`.

## Project structure

```
timetable_system/   Django project (settings, urls)
scheduler/          The app
  models.py         Teacher, Room, Section, Course, Assignment,
                    TeacherUnavailability, Timetable, ScheduledClass
  constants.py      Days + period timings from the real Winter 2026 sheet
  services/solver.py  CP-SAT model, hard/soft constraints, validator
  views.py          Dashboard, generate, grid, publish, print/PDF
  management/commands/seed_demo.py   Realistic demo dataset
templates/          Bootstrap UI
verify_run.py       End-to-end check: generate → validate 0 clashes → pages 200
```

## Future work

1. Curate the imported dataset (real room capacities/types, teacher load
   limits) so the whole department can be re-generated automatically.
2. Richer soft constraints: teacher preferences, gap minimisation per section.
3. Sessions longer than 2 periods; examination timetabling.
4. Change notifications when a published timetable is updated.
