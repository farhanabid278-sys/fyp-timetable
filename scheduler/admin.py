from django.contrib import admin

from .models import (
    Assignment,
    Course,
    Room,
    ScheduledClass,
    Section,
    Teacher,
    TeacherUnavailability,
    Timetable,
)


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ("name", "designation", "email", "max_sessions_per_week")
    search_fields = ("name",)


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("name", "room_type", "capacity")
    list_filter = ("room_type",)


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("name", "program", "semester", "size", "shift")
    list_filter = ("program", "semester", "shift")


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "sessions_per_week", "requires_lab")
    search_fields = ("code", "title")


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("course", "section", "teacher")
    list_filter = ("course", "section", "teacher")


@admin.register(TeacherUnavailability)
class TeacherUnavailabilityAdmin(admin.ModelAdmin):
    list_display = ("teacher", "day", "period")
    list_filter = ("teacher", "day")


@admin.register(Timetable)
class TimetableAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "created_at", "solver_status", "generation_seconds")
    list_filter = ("status",)


@admin.register(ScheduledClass)
class ScheduledClassAdmin(admin.ModelAdmin):
    list_display = ("timetable", "assignment", "room", "day", "period")
    list_filter = ("timetable", "day", "room")
