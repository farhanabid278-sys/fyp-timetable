from django.urls import path

from . import views

app_name = "scheduler"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("generate/", views.generate, name="generate"),
    path("evaluation/", views.evaluation, name="evaluation"),
    path("portal/teacher/", views.teacher_portal, name="teacher_portal"),
    path("portal/student/", views.student_portal, name="student_portal"),
    path("timetable/<int:pk>/", views.timetable_detail, name="timetable_detail"),
    path("timetable/<int:pk>/publish/", views.publish, name="publish"),
    path("timetable/<int:pk>/print/", views.timetable_print, name="timetable_print"),
    path("timetable/<int:pk>/entry/<int:entry_pk>/move/", views.entry_move, name="entry_move"),
    path("timetable/<int:pk>/entry/<int:entry_pk>/suggest/", views.entry_suggest, name="entry_suggest"),
]
