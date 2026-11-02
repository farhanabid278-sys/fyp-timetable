"""Seed a realistic demo dataset modelled on the university's real
Winter 2026 timetable sheet (BS Computer Science department scope:
a handful of sections, ~10 teachers, theory + lab courses).

Run:  python manage.py seed_demo
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from scheduler.models import (
    Assignment,
    Course,
    Room,
    Section,
    Teacher,
    TeacherUnavailability,
)

TEACHERS = [
    ("Dr. Ibrar Hussain", "Professor"),
    ("Dr. Saad", "Associate Professor"),
    ("Dr. Imran", "Assistant Professor"),
    ("Dr. Shahid", "Assistant Professor"),
    ("Dr. Ayesha", "Assistant Professor"),
    ("Dr. Faisal", "Assistant Professor"),
    ("Dr. M. Jamil", "Lecturer"),
    ("Dr. Zeeshan", "Lecturer"),
    ("Dr. M. Tariq", "Lecturer"),
    ("Dr. M. Arslan", "Lecturer"),
]

ROOMS = [
    ("CS-214", 40, Room.RoomType.CLASS),
    ("CS-216", 45, Room.RoomType.CLASS),
    ("CS-220", 60, Room.RoomType.CLASS),
    ("CS-225", 60, Room.RoomType.CLASS),
    ("LR-1", 48, Room.RoomType.LAB),
    ("LR-2", 48, Room.RoomType.LAB),
]

SECTIONS = [
    # name, program, semester, size, shift
    ("BS(CS)-1st-M1", "BS(CS)", 1, 45, Section.Shift.MORNING),
    ("BS(CS)-3rd-M1", "BS(CS)", 3, 42, Section.Shift.MORNING),
    ("BS(CS)-5th-E1", "BS(CS)", 5, 40, Section.Shift.EVENING),
    ("BS(CS)-7th-M1", "BS(CS)", 7, 38, Section.Shift.MORNING),
    ("BS(CS)-7th-E1", "BS(CS)", 7, 36, Section.Shift.EVENING),
]

COURSES = [
    # code, title, sessions/week, requires_lab, periods per session
    ("CS-101", "Introduction to Computing", 3, False, 1),
    ("CS-102", "Programming Fundamentals", 3, False, 1),
    ("CS-102L", "Programming Fundamentals Lab", 1, True, 2),
    ("CS-207", "Data Structures", 3, False, 1),
    ("CS-207L", "Data Structures Lab", 1, True, 2),
    ("CS-211", "Digital Logic Design", 2, False, 1),
    ("CS-311", "Computer Networks", 3, False, 1),
    ("CS-315", "Operating Systems", 3, False, 1),
    ("CS-409", "Compiler Construction", 2, False, 1),
    ("CS-411", "Artificial Intelligence", 3, False, 1),
    ("CS-413", "Final Year Project — I", 1, False, 1),
    ("SE-402", "Software Project Management", 2, False, 1),
]

# (course_code, section_name, teacher_name)
ASSIGNMENTS = [
    ("CS-101", "BS(CS)-1st-M1", "Dr. M. Jamil"),
    ("CS-102", "BS(CS)-1st-M1", "Dr. Zeeshan"),
    ("CS-102L", "BS(CS)-1st-M1", "Dr. Zeeshan"),
    ("CS-207", "BS(CS)-3rd-M1", "Dr. Imran"),
    ("CS-207L", "BS(CS)-3rd-M1", "Dr. M. Tariq"),
    ("CS-211", "BS(CS)-3rd-M1", "Dr. Shahid"),
    ("CS-311", "BS(CS)-5th-E1", "Dr. Saad"),
    ("CS-315", "BS(CS)-5th-E1", "Dr. Faisal"),
    ("CS-409", "BS(CS)-7th-M1", "Dr. Ibrar Hussain"),
    ("CS-411", "BS(CS)-7th-M1", "Dr. Ayesha"),
    ("CS-413", "BS(CS)-7th-M1", "Dr. Ibrar Hussain"),
    ("SE-402", "BS(CS)-7th-M1", "Dr. M. Arslan"),
    ("CS-409", "BS(CS)-7th-E1", "Dr. Ibrar Hussain"),
    ("CS-411", "BS(CS)-7th-E1", "Dr. Ayesha"),
    ("SE-402", "BS(CS)-7th-E1", "Dr. M. Arslan"),
]

# (teacher_name, day Mon=0..Fri=4, period) — examples of real availability rules
UNAVAILABLE = [
    ("Dr. Ayesha", 4, 1), ("Dr. Ayesha", 4, 2),   # Friday early periods off
    ("Dr. Ibrar Hussain", 0, 1),                   # Monday first period off
    ("Dr. Saad", 2, 7),                            # Wednesday evening first period off
]


class Command(BaseCommand):
    help = "Seed demo data modelled on the real Winter 2026 department timetable."

    @transaction.atomic
    def handle(self, *args, **options):
        teachers = {}
        for name, designation in TEACHERS:
            slug = name.lower().replace(" ", ".").replace("dr.", "dr")
            teachers[name], _ = Teacher.objects.get_or_create(
                name=name,
                defaults={"designation": designation, "email": f"{slug}@uni.example.edu"},
            )
        rooms = {}
        for name, capacity, rtype in ROOMS:
            rooms[name], _ = Room.objects.get_or_create(
                name=name, defaults={"capacity": capacity, "room_type": rtype}
            )
        sections = {}
        for name, program, semester, size, shift in SECTIONS:
            sections[name], _ = Section.objects.get_or_create(
                name=name,
                defaults={"program": program, "semester": semester, "size": size, "shift": shift},
            )
        courses = {}
        for code, title, sessions, lab, duration in COURSES:
            courses[code], _ = Course.objects.get_or_create(
                code=code,
                defaults={"title": title, "sessions_per_week": sessions,
                          "requires_lab": lab, "session_duration": duration},
            )
        created = 0
        for code, section_name, teacher_name in ASSIGNMENTS:
            _, was_created = Assignment.objects.get_or_create(
                course=courses[code], section=sections[section_name],
                defaults={"teacher": teachers[teacher_name]},
            )
            created += int(was_created)
        for teacher_name, day, period in UNAVAILABLE:
            TeacherUnavailability.objects.get_or_create(
                teacher=teachers[teacher_name], day=day, period=period
            )
        self.stdout.write(self.style.SUCCESS(
            f"Seeded: {len(teachers)} teachers, {len(rooms)} rooms, {len(sections)} sections, "
            f"{len(courses)} courses, {Assignment.objects.count()} assignments "
            f"({created} newly created), {len(UNAVAILABLE)} unavailability rules."
        ))
