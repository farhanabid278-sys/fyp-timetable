# University Timetable Management System

**Final Year Project Report — BS Computer Science (7th Semester)**
Student: Farhan
Department of Computer Science

---

## Abstract

Preparing a university timetable by hand is slow and error-prone: courses, teachers, classrooms and student sections must be combined into a weekly schedule without any teacher, room or section being double-booked. This project presents a web-based University Timetable Management System that generates timetables automatically using constraint programming. The system is built with Python and Django, stores academic data in a relational database, and uses the Google OR-Tools CP-SAT solver to find schedules that satisfy all mandatory (hard) constraints while preferring compact, early-in-the-day placements. Administrators manage teachers, courses, rooms, sections and teacher availability through a web interface, generate and review timetables, edit individual classes with clash-checked manual moves and automatic reschedule suggestions, and publish the final timetable to teacher and student portals. The system was evaluated in two ways: (1) on a curated department dataset it produced an optimal timetable of 34 classes in about 2 seconds with zero hard-constraint violations; (2) the department's real Winter 2026 timetable (931 class entries, imported automatically from the official spreadsheet) was validated by the system, which detected a small number of genuine double-bookings in the manually prepared schedule — demonstrating the practical value of automated checking.

## 1. Introduction

### 1.1 Background
Every semester, a university department must assign each course's weekly sessions to days, time periods and rooms, taught by specific teachers to specific student sections. The number of combinations grows explosively, and a manual scheduler working in a spreadsheet cannot reliably check every rule for every class.

### 1.2 Problem statement
Manual timetable preparation (a) takes days of effort, (b) produces clashes that are discovered late by students and teachers, (c) makes changes painful because the effect of moving one class is hard to trace, and (d) gives no measurable guarantee about schedule quality.

### 1.3 Objectives
1. Model the timetable problem formally as a constraint satisfaction/optimisation problem.
2. Generate complete timetables automatically with zero violations of mandatory constraints.
3. Detect and report every clash type (teacher, room, section, capacity, room type, availability).
4. Support controlled manual editing with automatic, clash-free reschedule suggestions.
5. Publish timetables to teacher and student portals, with print/PDF export.
6. Evaluate the approach on both a curated dataset and the department's real timetable data.

### 1.4 Scope
The first version covers one department: teacher, course, classroom/lab and section management; timetable generation; conflict detection; review, editing and publication; and timetable viewing/export. A realistic working dataset contains 10–20 teachers, 15–30 courses, 5–10 rooms and several sections; the system was additionally stress-tested by importing the full real department timetable (151 teachers, 111 courses, 45 rooms, 72 sections, 931 class entries). Fee management, attendance, examinations and multi-campus scheduling are out of scope.

## 2. Background and Related Concepts

Timetabling is a classic NP-hard combinatorial problem. Three families of techniques are commonly used: (1) heuristic and metaheuristic search (genetic algorithms, simulated annealing, tabu search), which find good solutions but cannot prove optimality or guarantee that all hard constraints hold; (2) graph colouring formulations, which handle simple clash rules but struggle with richer constraints such as room capacity and availability; and (3) constraint programming / SAT-based solving, where the problem is declared as variables, domains and constraints and a solver searches systematically. This project uses approach (3) — the CP-SAT solver from Google OR-Tools — because it can both find valid schedules quickly and prove optimality for the chosen objective on department-sized instances, and because hard constraints are guaranteed by construction rather than checked afterwards.

## 3. Requirement Analysis

### 3.1 Functional requirements
- FR1: The administrator can manage teachers, courses, rooms, sections, assignments and teacher unavailability.
- FR2: The system generates a complete timetable from the stored data and rules.
- FR3: The system validates any timetable and reports violations by type.
- FR4: The administrator can move a class manually; the move is rejected if it introduces a clash.
- FR5: The system suggests clash-free alternative slots for a class.
- FR6: A timetable with violations cannot be published.
- FR7: Teachers and students can view their own published timetables; a printable/PDF view is provided.

### 3.2 Non-functional requirements
- NFR1: Generation for a department dataset completes in seconds.
- NFR2: The interface is usable without training (standard web forms and grids).
- NFR3: The system runs on a single machine for demonstration and can be moved to PostgreSQL for production without code changes.

### 3.3 Scheduling rules (constraints)
Hard constraints: every session placed exactly once; no teacher, room or section double-booking; teacher availability respected; room capacity at least the section size; lab (practical) courses only in labs and theory courses only in classrooms; classes only inside the section's shift (morning periods 1–6, evening periods 7–13, mirroring the department's M/E sections); the sessions of one course spread over different days; teacher weekly load within the allowed maximum; a session occupies its full duration in consecutive periods (practicals typically 2 periods).
Soft objective: prefer earlier periods within the shift, producing compact schedules.

## 4. System Design

### 4.1 Architecture
A three-layer web architecture: (1) presentation layer — Django templates with Bootstrap (dashboard, generation form, timetable grids, portals, evaluation page); (2) application layer — Django views plus a scheduling service containing the CP-SAT model, the validator and the reschedule-suggestion engine; (3) data layer — relational database (SQLite for development, PostgreSQL configurable for production). Data entry uses the Django admin.

### 4.2 Database design
Main entities: Teacher (optionally linked to a login account), Room (capacity, classroom/lab), Section (program, semester, size, shift), Course (weekly sessions, periods per session, lab requirement), Assignment (course–teacher–section, with a flag controlling inclusion in automatic generation), TeacherUnavailability (teacher, day, period), Timetable (name, draft/published status, solver metadata), and ScheduledClass (timetable, assignment, session number, room, day, start period, number of periods).

### 4.3 Constraint model
For every assignment and every weekly session, the model creates one Boolean variable per feasible placement (day, start period, room). A placement is feasible only if all its occupied periods lie inside the section's shift and none coincides with a teacher-unavailability slot. Constraints enforce: exactly one placement per session; at most one class per teacher/room/section in any occupied period; sessions of an assignment on distinct days; and the teacher load cap. The objective minimises the sum of start periods. The validator re-checks any stored timetable independently — multi-period entries occupy their whole range, and combined classes (same course, teacher and room taught to several sections together) are counted once, so they are not falsely reported as clashes.

### 4.4 Import of real data
The department's official timetable is a room/day spreadsheet grid whose cells contain free text (course code, section(s), teacher) and whose repeated consecutive cells denote multi-period sessions. An import tool parses this grid: it merges consecutive identical cells into sessions of at most two periods, extracts course codes (with theory/practical suffixes), section names and teacher names with regular expressions, normalises everything into the database entities, and stores the result as a published timetable. Cells that cannot be parsed (for example, a teacher name with no course) are counted and reported rather than silently dropped.

## 5. Implementation

### 5.1 Tools and technologies
Python; Django (web framework, ORM, admin, authentication); Google OR-Tools CP-SAT (constraint solving); SQLite/PostgreSQL (database); HTML, CSS, JavaScript and Bootstrap (interface); openpyxl (spreadsheet import); Git (version control).

### 5.2 Main modules
- `scheduler/models.py` — data model described in §4.2.
- `scheduler/constants.py` — working days and the 13 daily period timings, taken from the department's real Winter 2026 sheet (08:00–18:20).
- `scheduler/services/solver.py` — CP-SAT generation, independent validator, clash check for manual moves (`can_place`), and the alternative-slot engine (`find_alternatives`).
- `scheduler/views.py` and templates — dashboard, generation, timetable grid with publish action, print/PDF view, teacher portal, student portal, move/suggest pages, evaluation page.
- `scheduler/management/commands/seed_demo.py` — curated demo dataset modelled on the real timetable.
- `scheduler/management/commands/import_sheet.py` — real timetable importer (§4.4).
- `verify_run.py` and `scheduler/tests.py` — automated end-to-end and unit checks.

### 5.3 Key workflows
Generation: administrator presses Generate → the service builds the CP-SAT model from the database → the solver returns a placement set → the timetable is saved as a draft with solver status and time → the validator's zero-violation report is shown → the administrator publishes it. Rescheduling: if a room or teacher becomes unavailable, the administrator opens a class, views clash-free suggestions computed against the rest of the timetable, and applies one with a single click; fully manual moves are also accepted but clash-checked before saving.

## 6. Testing and Evaluation

### 6.1 Method
Three levels of testing were used: automated unit tests (Django test framework), an end-to-end verification script (generate → validate → load every page), and a real-data study (import and validation of the official Winter 2026 timetable).

### 6.2 Results — generated timetable (curated dataset)
Dataset: 10 teachers, 6 rooms, 5 sections, 12 courses, 15 assignments (34 weekly sessions, including 2-period lab sessions). Result: solver status OPTIMAL in ~2.0 s; violations — teacher clashes 0, room clashes 0, section clashes 0, capacity/room-type 0, unavailable-teacher placements 0. All web pages returned successfully and the publish workflow (including blocking publication of invalid timetables) behaved as specified. The three automated unit tests (zero-violation generation, multi-period lab placement, suggestion engine) all pass.

### 6.3 Results — real department timetable (imported)
The importer processed the official spreadsheet (three sheets) and stored 931 class entries from 575 sessions, covering 151 teachers, 111 courses, 45 rooms, 72 sections and 626 course–section assignments; 62 cells could not be parsed (mostly teacher names recorded without a course) and were reported. Validating this manually prepared timetable against the system's rules found 9 teacher double-bookings and 19 section double-bookings (room double-bookings: 0). A further group of room-type mismatches is expected because the spreadsheet does not record room types or capacities, so practical classes held in ordinary rooms are flagged by the strict lab rule; this is reported as a data limitation, not a scheduling error. These findings demonstrate the central claim of the project: even a carefully prepared manual timetable contains real clashes that an automated checker finds immediately.

### 6.4 Discussion
CP-SAT solved the department-sized generation problem to proven optimality in seconds, and the same rule engine served generation, validation, manual editing and suggestions — one source of truth for what a "valid timetable" means. The main limitations are that imported historical assignments are kept as reference data (excluded from generation until curated, e.g. teacher load limits and room capacities are not recorded in the source sheet), and that the objective is a simple compactness measure rather than a full preference model.

## 7. Conclusion and Future Work

The project delivers a working University Timetable Management System that generates clash-free timetables automatically, validates any timetable against explicit rules, supports safe manual rescheduling, and publishes schedules to teacher and student portals. Future work: curate the imported dataset (room capacities/types, teacher load limits) so the full department can be re-generated automatically; richer soft constraints (teacher preferences, gap minimisation per section); multi-period sessions longer than two periods with room-specific rules; examination timetabling; and notifications when a published timetable changes.

## References

1. Google OR-Tools — CP-SAT Solver documentation. https://developers.google.com/optimization/cp/cp_solver
2. Django documentation. https://docs.djangoproject.com/
3. Burke, E. K., & Petrovic, S. (2002). Recent research directions in automated timetabling. European Journal of Operational Research, 140(2), 266–280.
4. Schaerf, A. (1999). A survey of automated timetabling. Artificial Intelligence Review, 13(2), 87–127.
5. Department of Computer Science — Official Class Timetable, Winter Semester 2026 (source spreadsheet for the real-data study).

---

*Appendix — running the system:* see `README.md` in the project folder (installation, seed data, generation, verification commands).
