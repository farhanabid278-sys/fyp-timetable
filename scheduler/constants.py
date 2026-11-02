"""Academic calendar constants.

Days and period timings are taken from the university's real Winter 2026
timetable sheet (Department of Computer Science, UAF): Monday-Friday,
13 periods from 08:00 to 18:20.
"""

DAYS = [
    (0, "Monday"),
    (1, "Tuesday"),
    (2, "Wednesday"),
    (3, "Thursday"),
    (4, "Friday"),
]
DAY_NAMES = dict(DAYS)
DAY_INDEXES = [d for d, _ in DAYS]

# period -> (start, end), exactly as printed in the Winter 2026 sheet headers
PERIOD_TIMES = {
    1: ("08:00", "08:50"),
    2: ("08:50", "09:40"),
    3: ("09:40", "10:30"),
    4: ("10:30", "11:20"),
    5: ("11:20", "12:10"),
    6: ("12:10", "13:00"),
    7: ("13:00", "13:50"),
    8: ("13:50", "14:35"),
    9: ("14:35", "15:20"),
    10: ("15:20", "16:05"),
    11: ("16:05", "16:50"),
    12: ("16:50", "17:35"),
    13: ("17:35", "18:20"),
}

# Sections study in one shift, like the M (morning) / E (evening) sections
# in the real timetable.
SHIFT_PERIODS = {
    "MORNING": [1, 2, 3, 4, 5, 6],
    "EVENING": [7, 8, 9, 10, 11, 12, 13],
}
