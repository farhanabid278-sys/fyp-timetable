from collections import defaultdict

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .constants import DAYS, PERIOD_TIMES, SHIFT_PERIODS
from .models import (
    Assignment,
    Course,
    Room,
    ScheduledClass,
    Section,
    Teacher,
    Timetable,
)
from .services.solver import (
    can_place,
    find_alternatives,
    generate_timetable,
    validate_timetable,
)


def dashboard(request):
    latest = Timetable.objects.order_by("-created_at").first()
    context = {
        "counts": {
            "Teachers": Teacher.objects.count(),
            "Courses": Course.objects.count(),
            "Rooms": Room.objects.count(),
            "Sections": Section.objects.count(),
            "Assignments": Assignment.objects.count(),
        },
        "timetables": Timetable.objects.order_by("-created_at")[:10],
        "latest": latest,
        "latest_violations": validate_timetable(latest) if latest else None,
    }
    return render(request, "scheduler/dashboard.html", context)


def generate(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if not name:
            count = Timetable.objects.count() + 1
            name = f"Generated Timetable {count}"
        result = generate_timetable(time_limit_seconds=30.0)
        if not result.ok:
            messages.error(request, f"Generation failed ({result.status}): {result.message}")
            return redirect("scheduler:generate")
        with transaction.atomic():
            timetable = Timetable.objects.create(
                name=name,
                solver_status=result.status,
                generation_seconds=round(result.seconds, 3),
            )
            ScheduledClass.objects.bulk_create(
                [ScheduledClass(timetable=timetable, **p) for p in result.placements]
            )
        messages.success(
            request,
            f"Timetable generated ({result.status}) in {result.seconds:.2f}s "
            f"with {len(result.placements)} classes and zero hard-constraint violations.",
        )
        return redirect("scheduler:timetable_detail", pk=timetable.pk)
    return render(request, "scheduler/generate.html")


def _grid_for_section(timetable, section):
    """day -> period -> entry / "CONT" / None grid for one section."""
    entries = (
        timetable.entries.filter(assignment__section=section)
        .select_related("assignment__course", "assignment__teacher", "room")
    )
    by_slot = {}
    for e in entries:
        by_slot[(e.day, e.period)] = e
        for p in e.occupied_periods[1:]:
            by_slot[(e.day, p)] = "CONT"
    periods = SHIFT_PERIODS[section.shift]
    rows = []
    for day, day_name in DAYS:
        cells = [by_slot.get((day, p)) for p in periods]
        rows.append({"day": day_name, "cells": cells})
    headers = [(p, PERIOD_TIMES[p][0], PERIOD_TIMES[p][1]) for p in periods]
    return headers, rows


def _grid_for_teacher(timetable, teacher):
    """day -> period -> entry / "CONT" / None grid for one teacher (all periods)."""
    entries = (
        timetable.entries.filter(assignment__teacher=teacher)
        .select_related("assignment__course", "assignment__section", "room")
    )
    by_slot = {}
    for e in entries:
        by_slot[(e.day, e.period)] = e
        for p in e.occupied_periods[1:]:
            by_slot[(e.day, p)] = "CONT"
    periods = sorted(PERIOD_TIMES)
    rows = []
    for day, day_name in DAYS:
        cells = [by_slot.get((day, p)) for p in periods]
        rows.append({"day": day_name, "cells": cells})
    headers = [(p, PERIOD_TIMES[p][0], PERIOD_TIMES[p][1]) for p in periods]
    return headers, rows


def timetable_detail(request, pk):
    timetable = get_object_or_404(Timetable, pk=pk)
    sections = Section.objects.order_by("name")
    section_id = request.GET.get("section")
    section = sections.filter(pk=section_id).first() if section_id else sections.first()
    headers, rows = ([], [])
    if section:
        headers, rows = _grid_for_section(timetable, section)
    section_entries = []
    if section:
        section_entries = (
            timetable.entries.filter(assignment__section=section)
            .select_related("assignment__course", "assignment__teacher", "room")
            .order_by("day", "period")
        )
    context = {
        "timetable": timetable,
        "sections": sections,
        "section": section,
        "headers": headers,
        "rows": rows,
        "section_entries": section_entries,
        "violations": validate_timetable(timetable),
    }
    return render(request, "scheduler/timetable_detail.html", context)


@require_POST
def publish(request, pk):
    timetable = get_object_or_404(Timetable, pk=pk)
    violations = validate_timetable(timetable)
    hard = sum(v for k, v in violations.items() if k != "total_entries")
    if hard:
        messages.error(request, f"Cannot publish: this timetable has {hard} hard-constraint violation(s).")
    else:
        timetable.status = Timetable.Status.PUBLISHED
        timetable.save(update_fields=["status"])
        messages.success(request, "Timetable published. Teachers and students can now view it.")
    return redirect("scheduler:timetable_detail", pk=pk)


def _published_or_latest(request):
    published = Timetable.objects.filter(status=Timetable.Status.PUBLISHED).order_by("-created_at")
    tt_id = request.GET.get("timetable")
    if tt_id:
        return get_object_or_404(Timetable, pk=tt_id), published
    return published.first(), published


def teacher_portal(request):
    timetable, published = _published_or_latest(request)
    teachers = Teacher.objects.order_by("name")
    teacher_id = request.GET.get("teacher")
    teacher = None
    if request.user.is_authenticated and hasattr(request.user, "teacher_profile"):
        teacher = request.user.teacher_profile
    if teacher_id:
        teacher = teachers.filter(pk=teacher_id).first() or teacher
    if teacher is None:
        teacher = teachers.first()
    headers, rows = ([], [])
    if timetable and teacher:
        headers, rows = _grid_for_teacher(timetable, teacher)
    return render(request, "scheduler/teacher_portal.html", {
        "timetable": timetable, "published": published,
        "teachers": teachers, "teacher": teacher,
        "headers": headers, "rows": rows,
    })


def student_portal(request):
    timetable, published = _published_or_latest(request)
    sections = Section.objects.order_by("name")
    section_id = request.GET.get("section")
    section = sections.filter(pk=section_id).first() if section_id else sections.first()
    headers, rows = ([], [])
    if timetable and section:
        headers, rows = _grid_for_section(timetable, section)
    return render(request, "scheduler/student_portal.html", {
        "timetable": timetable, "published": published,
        "sections": sections, "section": section,
        "headers": headers, "rows": rows,
    })


def entry_move(request, pk, entry_pk):
    timetable = get_object_or_404(Timetable, pk=pk)
    entry = get_object_or_404(ScheduledClass, pk=entry_pk, timetable=timetable)
    if request.method == "POST":
        try:
            day = int(request.POST["day"])
            period = int(request.POST["period"])
            room = get_object_or_404(Room, pk=request.POST["room"])
        except (KeyError, ValueError):
            messages.error(request, "Invalid move values.")
            return redirect("scheduler:entry_move", pk=pk, entry_pk=entry_pk)
        if can_place(entry, day, period, room):
            entry.day, entry.period, entry.room = day, period, room
            entry.save(update_fields=["day", "period", "room"])
            messages.success(request, "Class moved successfully — no clashes introduced.")
            return redirect("scheduler:timetable_detail", pk=pk)
        messages.error(
            request,
            "That slot is not free: it would clash with another class, the room/section "
            "rules, or the teacher's availability. Try the suggestions page.",
        )
        return redirect("scheduler:entry_suggest", pk=pk, entry_pk=entry_pk)
    return render(request, "scheduler/entry_move.html", {
        "timetable": timetable, "entry": entry,
        "days": DAYS,
        "periods": [(p, PERIOD_TIMES[p][0], PERIOD_TIMES[p][1]) for p in sorted(PERIOD_TIMES)],
        "rooms": Room.objects.order_by("name"),
    })


def entry_suggest(request, pk, entry_pk):
    timetable = get_object_or_404(Timetable, pk=pk)
    entry = get_object_or_404(ScheduledClass, pk=entry_pk, timetable=timetable)
    suggestions = find_alternatives(entry)
    for s in suggestions:
        s["day_name"] = dict(DAYS)[s["day"]]
        s["start"], s["end"] = (
            PERIOD_TIMES[s["period"]][0],
            PERIOD_TIMES[s["period"] + entry.periods_count - 1][1],
        )
    return render(request, "scheduler/entry_suggest.html", {
        "timetable": timetable, "entry": entry, "suggestions": suggestions,
    })


def evaluation(request):
    rows = []
    for t in Timetable.objects.order_by("-created_at"):
        v = validate_timetable(t)
        rows.append({"timetable": t, "violations": v,
                     "hard_total": sum(x for k, x in v.items() if k != "total_entries")})
    return render(request, "scheduler/evaluation.html", {
        "rows": rows,
        "counts": {
            "Teachers": Teacher.objects.count(),
            "Courses": Course.objects.count(),
            "Rooms": Room.objects.count(),
            "Sections": Section.objects.count(),
            "Assignments": Assignment.objects.count(),
        },
    })


def timetable_print(request, pk):
    """Printable view: one grid per section (use the browser's Print → PDF)."""
    timetable = get_object_or_404(Timetable, pk=pk)
    grids = []
    for section in Section.objects.order_by("name"):
        headers, rows = _grid_for_section(timetable, section)
        grids.append({"section": section, "headers": headers, "rows": rows})
    return render(request, "scheduler/timetable_print.html", {"timetable": timetable, "grids": grids})
