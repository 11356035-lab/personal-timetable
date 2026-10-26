from django.urls import path

from . import views

urlpatterns = [
    path("", views.TimetableView.as_view(), name="timetable"),
    path("print/", views.TimetablePrintView.as_view(), name="timetable_print"),
    path("courses/new/", views.CourseCreateView.as_view(), name="course_create"),
    path("courses/<int:pk>/edit/", views.CourseUpdateView.as_view(), name="course_update"),
    path("courses/<int:pk>/delete/", views.CourseDeleteView.as_view(), name="course_delete"),
]
