from django.urls import path

from . import views

urlpatterns = [
    path("", views.TimetableView.as_view(), name="timetable"),
    path("print/", views.TimetablePrintView.as_view(), name="timetable_print"),
    path("overview/", views.OverviewView.as_view(), name="overview"),
    path("select-class/", views.SelectClassView.as_view(), name="select_class"),
    path("courses/", views.CourseListView.as_view(), name="course_list"),
    path("courses/<int:pk>/enroll/", views.EnrollView.as_view(), name="course_enroll"),
    path("courses/<int:pk>/drop/", views.DropView.as_view(), name="course_drop"),
]
