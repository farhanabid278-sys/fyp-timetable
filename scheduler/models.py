from django.db import models

from .constants import DAYS, PERIOD_TIMES


class Teacher(models.Model):
    user = models.OneToOneField(
        "auth.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="teacher_profile",
        help_text="Optional login account linked to this teacher (portal access)",
    )
    name = models.CharField(max_length=120)
    email = models.EmailField(unique=True, blank=True, null=True)
    designation = models.CharField(max_length=80, blank=True, help_text="e.g. Professor, Assistant Professor, Lecturer")
    max_sessions_per_week = models.PositiveIntegerField(default=12)

    def __str__(self):
        return self.name


class Room(models.Model):
    class RoomType(models.TextChoices):
        CLASS = "CLASS", "Classroom"
        LAB = "LAB", "Lab"

    name = models.CharField(max_length=40, unique=True, help_text="e.g. CS-214, LR-1")
    capacity = models.PositiveIntegerField()
    room_type = models.CharField(max_length=10, choices=RoomType.choices, default=RoomType.CLASS)

    def __str__(self):
        return f"{self.name} ({self.get_room_type_display()}, {self.capacity})"


class Section(models.Model):
    """A student cohort, e.g. BS(CS)-7th-M1 (program, semester, shift group)."""

    class Shift(models.TextChoices):
        MORNING = "MORNING", "Morning"
        EVENING = "EVENING", "Evening"

    name = models.CharField(max_length=40, unique=True, help_text="e.g. BS(CS)-7th-M1")
    program = models.CharField(max_length=40, help_text="e.g. BS(CS), BS(SE)")
    semester = models.PositiveIntegerField()
    size = models.PositiveIntegerField(help_text="Number of students")
    shift = models.CharField(max_length=10, choices=Shift.choices, default=Shift.MORNING)

    def __str__(self):
        return self.name


class Course(models.Model):
    code = models.CharField(max_length=20, unique=True, help_text="e.g. CS-311")
    title = models.CharField(max_length=160)
    sessions_per_week = models.PositiveIntegerField(default=3, help_text="Class meetings per week")
    session_duration = models.PositiveIntegerField(default=1, help_text="Consecutive periods per meeting (labs are usually 2)")
    requires_lab = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.code} — {self.title}"


class Assignment(models.Model):
    """One teaching assignment: this teacher teaches this course to this section."""

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="assignments")
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name="assignments")
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="assignments")
    for_generation = models.BooleanField(
        default=True,
        help_text="Include in automatic generation. Imported historical assignments are kept as reference data with this off.",
    )

    class Meta:
        unique_together = ("course", "section")

    def __str__(self):
        return f"{self.course.code} → {self.section.name} by {self.teacher.name}"


class TeacherUnavailability(models.Model):
    """A (day, period) when a teacher cannot teach."""

    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name="unavailability")
    day = models.IntegerField(choices=DAYS)
    period = models.PositiveIntegerField(help_text="Period number, see PERIOD_TIMES")

    class Meta:
        unique_together = ("teacher", "day", "period")
        verbose_name_plural = "Teacher unavailability"

    def __str__(self):
        start, end = PERIOD_TIMES.get(self.period, ("?", "?"))
        return f"{self.teacher.name} unavailable {self.get_day_display()} {start}-{end}"


class Timetable(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"

    name = models.CharField(max_length=120, help_text="e.g. Winter 2026 — Generated 1")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    generation_seconds = models.FloatField(null=True, blank=True)
    solver_status = models.CharField(max_length=40, blank=True)

    def __str__(self):
        return f"{self.name} [{self.get_status_display()}]"


class ScheduledClass(models.Model):
    """One placed class meeting inside a generated timetable."""

    timetable = models.ForeignKey(Timetable, on_delete=models.CASCADE, related_name="entries")
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="scheduled_classes")
    session_number = models.PositiveIntegerField(help_text="1..sessions_per_week for the assignment")
    periods_count = models.PositiveIntegerField(default=1, help_text="Consecutive periods this meeting occupies, starting at 'period'")
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="scheduled_classes")
    day = models.IntegerField(choices=DAYS)
    period = models.PositiveIntegerField()

    class Meta:
        ordering = ["day", "period"]
        unique_together = ("timetable", "assignment", "session_number")

    @property
    def start_time(self):
        return PERIOD_TIMES.get(self.period, ("?", "?"))[0]

    @property
    def end_time(self):
        last = self.period + self.periods_count - 1
        return PERIOD_TIMES.get(last, ("?", "?"))[1]

    @property
    def occupied_periods(self):
        return list(range(self.period, self.period + self.periods_count))

    def __str__(self):
        return (
            f"{self.get_day_display()} P{self.period} {self.start_time}-{self.end_time}: "
            f"{self.assignment.course.code} {self.assignment.section.name} in {self.room.name}"
        )
