"""Constraint-based timetable generation with Google OR-Tools CP-SAT.

Hard constraints (a generated timetable violates none of these):
  1. Every session of every assignment is placed exactly once.
  2. No teacher teaches two classes in the same (day, period).
  3. No room hosts two classes in the same (day, period).
  4. No section attends two classes in the same (day, period).
  5. A teacher is never placed in a (day, period) marked unavailable.
  6. Room capacity >= section size, and lab courses only go to lab rooms
     (theory courses only to classrooms).
  7. Classes only use the periods of the section's shift
     (morning sections: periods 1-6, evening sections: 7-13).
  8. The sessions of one assignment fall on different days (spread over
     the week) whenever the number of sessions allows it.
  9. A teacher's total weekly sessions never exceed their maximum.
 10. A session occupies `session_duration` consecutive periods inside the
     shift (labs typically 2) — clashes are checked on every occupied period.

Soft objective: prefer earlier periods within the shift (minimise the sum
of start periods), which packs classes compactly.
"""
from collections import defaultdict

from ortools.sat.python import cp_model

from ..constants import DAY_INDEXES, SHIFT_PERIODS
from ..models import Assignment, Room, TeacherUnavailability


class SolveResult:
    def __init__(self, status, placements=None, seconds=0.0, message=""):
        self.status = status  # "OPTIMAL" / "FEASIBLE" / "INFEASIBLE" / "ERROR"
        self.placements = placements or []  # list of dicts for ScheduledClass
        self.seconds = seconds
        self.message = message

    @property
    def ok(self):
        return self.status in ("OPTIMAL", "FEASIBLE")


def _start_options(assignment, unavailable):
    """All (day, start_period, occupied_periods) a session may use."""
    periods = SHIFT_PERIODS[assignment.section.shift]
    dur = max(1, assignment.course.session_duration)
    options = []
    for d in DAY_INDEXES:
        for i, start in enumerate(periods):
            occupied = periods[i:i + dur]
            if len(occupied) < dur:
                continue
            if any((assignment.teacher_id, d, p) in unavailable for p in occupied):
                continue
            options.append((d, start, tuple(occupied)))
    return options


def generate_timetable(time_limit_seconds=30.0):
    """Build and solve the CP-SAT model from the current database state."""
    assignments = list(
        Assignment.objects.filter(for_generation=True)
        .select_related("course", "teacher", "section").all()
    )
    rooms = list(Room.objects.all())
    if not assignments:
        return SolveResult("ERROR", message="No teaching assignments exist yet. Add data in the admin first.")
    if not rooms:
        return SolveResult("ERROR", message="No rooms exist yet. Add rooms in the admin first.")

    unavailable = set(
        TeacherUnavailability.objects.values_list("teacher_id", "day", "period")
    )

    eligible_rooms = {}
    for a in assignments:
        need_type = Room.RoomType.LAB if a.course.requires_lab else Room.RoomType.CLASS
        ok_rooms = [r for r in rooms if r.capacity >= a.section.size and r.room_type == need_type]
        if not ok_rooms:
            return SolveResult(
                "ERROR",
                message=f"No suitable room for {a} (needs {need_type}, capacity >= {a.section.size}).",
            )
        eligible_rooms[a.id] = ok_rooms

    model = cp_model.CpModel()
    # One bool var per (assignment, session, day, start_period, room) option.
    options = {}  # (aid, session) -> list of (key, day, start, occupied, room_id)
    x = {}
    for a in assignments:
        starts = _start_options(a, unavailable)
        if not starts:
            return SolveResult("ERROR", message=f"No free slot exists for {a} under the current rules.")
        opts = []
        for s in range(1, a.course.sessions_per_week + 1):
            for (d, start, occupied) in starts:
                for r in eligible_rooms[a.id]:
                    key = (a.id, s, d, start, r.id)
                    x[key] = model.NewBoolVar(f"x_{a.id}_{s}_{d}_{start}_{r.id}")
                    opts.append((key, d, start, occupied, r.id))
            # Constraint 1: each session placed exactly once.
            model.Add(sum(x[k] for (k, *_rest) in opts if k[1] == s) == 1)
        options[a.id] = opts
        # Constraint 8: sessions of one assignment on different days.
        if a.course.sessions_per_week > 1:
            for d in DAY_INDEXES:
                model.Add(sum(x[k] for (k, dd, *_r) in opts if dd == d) <= 1)

    by_id = {a.id: a for a in assignments}

    def add_no_overlap(key_fn):
        groups = defaultdict(list)
        for (key, d, start, occupied, rid) in [o for opts in options.values() for o in opts]:
            aid = key[0]
            for p in occupied:
                groups[key_fn(by_id[aid], rid, d, p)].append(x[key])
        for vars_ in groups.values():
            uniq = list(dict.fromkeys(vars_))
            if len(uniq) > 1:
                model.Add(sum(uniq) <= 1)

    add_no_overlap(lambda a, rid, d, p: (a.teacher_id, d, p))   # teacher clash
    add_no_overlap(lambda a, rid, d, p: (rid, d, p))            # room clash
    add_no_overlap(lambda a, rid, d, p: (a.section_id, d, p))   # section clash

    # Constraint 9: teacher weekly load cap (counts sessions, not periods).
    teacher_vars = defaultdict(list)
    for opts in options.values():
        for (key, *_rest) in opts:
            teacher_vars[by_id[key[0]].teacher_id].append(x[key])
    teachers = {a.teacher_id: a.teacher for a in assignments}
    for tid, vars_ in teacher_vars.items():
        model.Add(sum(vars_) <= teachers[tid].max_sessions_per_week)

    # Soft objective: earlier start periods preferred.
    model.Minimize(sum(k[3] * var for k, var in x.items()))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_seconds)
    solver.parameters.num_search_workers = 8
    status_code = solver.Solve(model)
    status_name = solver.StatusName(status_code)

    if status_code not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return SolveResult(
            status_name,
            seconds=solver.WallTime(),
            message="No valid timetable exists for the current data and rules. "
                    "Relax a rule, add rooms, or reduce sessions and try again.",
        )

    room_by_id = {r.id: r for r in rooms}
    placements = []
    for (aid, s, d, start, rid), var in x.items():
        if solver.Value(var):
            placements.append(
                {
                    "assignment": by_id[aid],
                    "session_number": s,
                    "periods_count": max(1, by_id[aid].course.session_duration),
                    "room": room_by_id[rid],
                    "day": d,
                    "period": start,
                }
            )
    placements.sort(key=lambda pl: (pl["day"], pl["period"]))
    return SolveResult(status_name, placements=placements, seconds=solver.WallTime())


def _class_identity(entry):
    """Identity of the real-world class an entry belongs to.

    Combined classes (same course + teacher + room + slot, several sections)
    are ONE class, not a clash — entries sharing this identity are merged
    before clash counting.
    """
    return (entry.assignment.course_id, entry.assignment.teacher_id, entry.room_id, entry.day)


def validate_timetable(timetable):
    """Count hard-constraint violations in a saved timetable.

    Multi-period entries occupy every period in their range, and combined
    classes count once. A correct generated timetable has all zeros.
    """
    entries = list(timetable.entries.select_related(
        "assignment__teacher", "assignment__section", "assignment__course", "room"
    ))
    violations = {
        "teacher_clashes": 0,
        "room_clashes": 0,
        "section_clashes": 0,
        "capacity_or_type": 0,
        "teacher_unavailable": 0,
        "total_entries": len(entries),
    }

    def count_clashes(resource_fn):
        # resource key -> set of distinct class identities using it per period
        usage = defaultdict(set)
        for e in entries:
            for p in e.occupied_periods:
                usage[(resource_fn(e), e.day, p)].add(_class_identity(e))
        return sum(len(ids) - 1 for ids in usage.values() if len(ids) > 1)

    violations["teacher_clashes"] = count_clashes(lambda e: e.assignment.teacher_id)
    violations["room_clashes"] = count_clashes(lambda e: e.room_id)
    violations["section_clashes"] = count_clashes(lambda e: e.assignment.section_id)

    unavailable = set(TeacherUnavailability.objects.values_list("teacher_id", "day", "period"))
    for e in entries:
        need_type = Room.RoomType.LAB if e.assignment.course.requires_lab else Room.RoomType.CLASS
        if e.room.capacity < e.assignment.section.size or e.room.room_type != need_type:
            violations["capacity_or_type"] += 1
        if any((e.assignment.teacher_id, e.day, p) in unavailable for p in e.occupied_periods):
            violations["teacher_unavailable"] += 1
    return violations


def can_place(entry, day, start, room):
    """True if `entry` could sit at (day, start, room) without clashing
    with the rest of its timetable or the teacher's availability."""
    timetable = entry.timetable
    others = [
        e for e in timetable.entries.select_related(
            "assignment__teacher", "assignment__section", "assignment__course", "room"
        ) if e.pk != entry.pk
    ]
    unavailable = set(TeacherUnavailability.objects.values_list("teacher_id", "day", "period"))
    a = entry.assignment
    occupied = list(range(start, start + entry.periods_count))
    periods = SHIFT_PERIODS[a.section.shift]
    if any(p not in periods for p in occupied):
        return False
    if room.capacity < a.section.size:
        return False
    need_type = Room.RoomType.LAB if a.course.requires_lab else Room.RoomType.CLASS
    if room.room_type != need_type:
        return False
    if any((a.teacher_id, day, p) in unavailable for p in occupied):
        return False
    for e in others:
        if e.day != day or not (set(occupied) & set(e.occupied_periods)):
            continue
        same_class = _class_identity(e) == (a.course_id, a.teacher_id, room.id, day)
        if e.room_id == room.id and not same_class:
            return False
        if e.assignment.teacher_id == a.teacher_id and e.assignment.course_id != a.course_id:
            return False
        if e.assignment.section_id == a.section_id and e.assignment.course_id != a.course_id:
            return False
    return True


def find_alternatives(entry, limit=12):
    """Clash-free alternative placements for one scheduled class.

    Used for manual rescheduling: when a room/teacher becomes unavailable,
    suggest other (day, start_period, room) options that keep the rest of
    the timetable valid. Returns a list of dicts with room/day/period.
    """
    timetable = entry.timetable
    others = [
        e for e in timetable.entries.select_related(
            "assignment__teacher", "assignment__section", "assignment__course", "room"
        ) if e.pk != entry.pk
    ]
    unavailable = set(TeacherUnavailability.objects.values_list("teacher_id", "day", "period"))
    a = entry.assignment
    dur = entry.periods_count
    periods = SHIFT_PERIODS[a.section.shift]

    def clash_free(day, start, room):
        occupied = list(range(start, start + dur))
        if any(p not in periods for p in occupied):
            return False
        if any((a.teacher_id, day, p) in unavailable for p in occupied):
            return False
        for e in others:
            if e.day != day:
                continue
            overlap = set(occupied) & set(e.occupied_periods)
            if not overlap:
                continue
            same_class = _class_identity(e) == (a.course_id, a.teacher_id, room.id, day)
            if e.room_id == room.id and not same_class:
                return False
            if e.assignment.teacher_id == a.teacher_id and e.assignment.course_id != a.course_id:
                return False
            if e.assignment.section_id == a.section_id and e.assignment.course_id != a.course_id:
                return False
        return True

    suggestions = []
    rooms = sorted(
        (r for r in Room.objects.all()
         if r.capacity >= a.section.size
         and r.room_type == (Room.RoomType.LAB if a.course.requires_lab else Room.RoomType.CLASS)),
        key=lambda r: r.name,
    )
    for day in DAY_INDEXES:
        for i, start in enumerate(periods):
            if i + dur > len(periods):
                continue
            for room in rooms:
                if (day, start, room.id) == (entry.day, entry.period, entry.room_id):
                    continue
                if clash_free(day, start, room):
                    suggestions.append({"day": day, "period": start, "room": room})
                    if len(suggestions) >= limit:
                        return suggestions
    return suggestions
