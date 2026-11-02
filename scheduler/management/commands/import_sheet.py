"""Import the university's real timetable (.xlsx) into the system.

The sheet is a room/day grid: each cell holds one class as free text
(course code, section name(s), teacher name), and the same class repeated
in consecutive periods is one multi-period session. This command parses
that grid into normalised entities (Teacher, Course, Room, Section,
Assignment) and stores the classes as a published Timetable, so the real
Winter 2026 schedule can be browsed in the teacher/student portals.

Imported assignments are reference data: `for_generation` is False for
them, so automatic generation keeps using the curated dataset until the
department marks imported assignments for generation.

Run:  python manage.py import_sheet data/winter2026.xlsx
"""
import re
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from scheduler.models import (
    Assignment,
    Course,
    Room,
    ScheduledClass,
    Section,
    Teacher,
    Timetable,
)

DAY_MAP = {
    "mon": 0, "monday": 0,
    "tue": 1, "tues": 1, "tuesday": 1,
    "wed": 2, "wednesday": 2,
    "thu": 3, "thur": 3, "thurs": 3, "thursday": 3,
    "fri": 4, "friday": 4,
}
COURSE_RE = re.compile(r"([A-Z]{2,5}-\d{3}(?:-[TP])?)")
SECTION_RE = re.compile(
    r"(BS|MS)\s*\(?([A-Z]{2,4})\)?\s*-\s*(\d+)(?:st|nd|rd|th)(?:\s*-\s*([A-Z]\d))?",
    re.IGNORECASE,
)
TIME_RE = re.compile(r"\d{1,2}:\d{2}")
TIMETABLE_NAME = "Winter 2026 — Imported (Actual)"


def parse_cell(text):
    """Return (course_code, [section names], teacher_name) or None."""
    flat = " ".join(str(text).split())
    m = COURSE_RE.search(flat)
    if not m:
        return None
    course_code = m.group(1).upper()
    rest = flat[m.end():]
    sections = []
    for sm in SECTION_RE.finditer(rest):
        level, prog, sem, suffix = sm.groups()
        name = f"{level.upper()}({prog.upper()})-{int(sem)}"
        if suffix:
            name += f"-{suffix.upper()}"
        if name not in sections:
            sections.append(name)
    if not sections:
        return None
    teacher = SECTION_RE.sub(" ", rest)
    teacher = " ".join(teacher.split(" ,")).strip(" -–,")
    teacher = re.sub(r"\s+VF$", "", teacher).strip()
    if not teacher:
        teacher = "Not Assigned (TBA)"
    return course_code, sections, teacher


def section_meta(name):
    m = SECTION_RE.search(name.replace("(", " (").replace(")", ") "))
    # Parse from the canonical name instead:
    m = re.match(r"(BS|MS)\(([A-Z]{2,4})\)-(\d+)(?:-([A-Z]\d))?", name)
    level, prog, sem, suffix = m.groups()
    shift = Section.Shift.MORNING
    if suffix and suffix.startswith("E"):
        shift = Section.Shift.EVENING
    return f"{level}({prog})", int(sem), shift


class Command(BaseCommand):
    help = "Import a real timetable .xlsx (room/day grid) as a published timetable."

    def add_arguments(self, parser):
        parser.add_argument("xlsx_path")

    @transaction.atomic
    def handle(self, *args, **options):
        path = Path(options["xlsx_path"])
        if not path.exists():
            raise CommandError(f"File not found: {path}")
        wb = openpyxl.load_workbook(path, data_only=True)

        Timetable.objects.filter(name=TIMETABLE_NAME).delete()
        timetable = Timetable.objects.create(
            name=TIMETABLE_NAME, status=Timetable.Status.PUBLISHED,
            solver_status="IMPORTED",
        )

        teachers, rooms, sections, courses = {}, {}, {}, {}
        assignments = {}
        session_counter = Counter()
        course_sessions = defaultdict(Counter)   # assignment key -> weekly sessions
        course_duration = Counter()              # course code -> max chunk length
        entries = []
        stats = Counter()

        def get_teacher(name):
            if name not in teachers:
                teachers[name], _ = Teacher.objects.get_or_create(name=name)
            return teachers[name]

        def get_room(name):
            if name not in rooms:
                rtype = Room.RoomType.LAB if "lab" in name.lower() else Room.RoomType.CLASS
                rooms[name], _ = Room.objects.get_or_create(
                    name=name, defaults={"capacity": 100, "room_type": rtype}
                )
            return rooms[name]

        def get_section(name):
            if name not in sections:
                program, semester, shift = section_meta(name)
                sections[name], _ = Section.objects.get_or_create(
                    name=name,
                    defaults={"program": program, "semester": semester, "size": 40, "shift": shift},
                )
            return sections[name]

        def get_course(code):
            if code not in courses:
                courses[code], _ = Course.objects.get_or_create(
                    code=code,
                    defaults={
                        "title": code,
                        "requires_lab": code.endswith("-P"),
                        "sessions_per_week": 1,
                    },
                )
            return courses[code]

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            # Find the header row: first column cell == "Day".
            header_row = None
            for row in ws.iter_rows(min_row=1, max_row=6):
                if row[0].value and str(row[0].value).strip().lower() == "day":
                    header_row = row[0].row
                    break
            if header_row is None:
                stats["sheets_skipped"] += 1
                continue
            # Period columns: header cells (from column C) containing a time.
            period_cols = []
            for cell in ws[header_row][2:]:
                if cell.value and TIME_RE.search(str(cell.value)):
                    period_cols.append((cell.column, len(period_cols) + 1))
            for row in ws.iter_rows(min_row=header_row + 1, max_row=ws.max_row):
                day_raw = row[0].value
                room_raw = row[1].value if len(row) > 1 else None
                if not day_raw or not room_raw:
                    continue
                day = DAY_MAP.get(str(day_raw).strip().lower())
                if day is None:
                    continue
                room = get_room(" ".join(str(room_raw).split()))
                # Merge consecutive identical cells into runs.
                values = []
                for col, period in period_cols:
                    v = row[col - 1].value
                    values.append((period, None if v is None else " ".join(str(v).split())))
                i = 0
                while i < len(values):
                    period, val = values[i]
                    if not val or val.lower() == "x":
                        i += 1
                        continue
                    j = i
                    while j + 1 < len(values) and values[j + 1][1] == val:
                        j += 1
                    run = values[i:j + 1]
                    parsed = parse_cell(val)
                    if parsed is None:
                        stats["cells_skipped_unparsed"] += 1
                        i = j + 1
                        continue
                    code, section_names, teacher_name = parsed
                    course = get_course(code)
                    teacher = get_teacher(teacher_name)
                    # Split long runs into sessions of at most 2 periods.
                    chunks = [run[k:k + 2] for k in range(0, len(run), 2)]
                    for chunk in chunks:
                        start_period = chunk[0][0]
                        dur = len(chunk)
                        course_duration[code] = max(course_duration[code], dur)
                        for sname in section_names:
                            section = get_section(sname)
                            key = (course.id, section.id)
                            if key not in assignments:
                                assignments[key], _ = Assignment.objects.get_or_create(
                                    course=course, section=section,
                                    defaults={"teacher": teacher, "for_generation": False},
                                )
                            session_counter[key] += 1
                            course_sessions[key][dur] += 1
                            entries.append(ScheduledClass(
                                timetable=timetable,
                                assignment=assignments[key],
                                session_number=session_counter[key],
                                periods_count=dur,
                                room=room, day=day, period=start_period,
                            ))
                        stats["sessions_imported"] += 1
                    i = j + 1

        ScheduledClass.objects.bulk_create(entries)

        # Fill in observed weekly session counts / durations on courses.
        per_course_sessions = defaultdict(int)
        for (course_id, _section_id), count in session_counter.items():
            per_course_sessions[course_id] = max(per_course_sessions[course_id], count)
        for course in courses.values():
            course.sessions_per_week = per_course_sessions.get(course.id, 1)
            course.session_duration = course_duration.get(course.code, 1)
            course.save(update_fields=["sessions_per_week", "session_duration"])

        self.stdout.write(self.style.SUCCESS(
            f"Imported '{TIMETABLE_NAME}': {len(entries)} class entries from "
            f"{stats['sessions_imported']} sessions | {len(teachers)} teachers, "
            f"{len(courses)} courses, {len(rooms)} rooms, {len(sections)} sections, "
            f"{len(assignments)} assignments | skipped unparsed cells: "
            f"{stats['cells_skipped_unparsed']}"
        ))
