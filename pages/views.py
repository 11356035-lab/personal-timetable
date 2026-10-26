from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, TemplateView, UpdateView

from .forms import CourseForm
from .models import PERIODS, Course


class TimetableView(TemplateView):
    template_name = "pages/timetable.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        weekdays = Course.Weekday.choices

        # slots[(星期, 節次)] = 那一格的課；跨多節的課每一節都各佔一格
        slots = {}
        for course in Course.objects.all():
            for period in range(course.start_period, course.end_period + 1):
                slots[(course.weekday, period)] = course

        rows = []
        for period, (start_time, end_time) in PERIODS.items():
            cells = [slots.get((weekday, period)) for weekday, _ in weekdays]
            rows.append({
                "period": period,
                "start_time": start_time,
                "end_time": end_time,
                "cells": cells,
            })

        context["weekdays"] = weekdays
        context["rows"] = rows
        return context


class TimetablePrintView(TimetableView):
    template_name = "pages/timetable_print.html"


class CourseCreateView(SuccessMessageMixin, CreateView):
    model = Course
    form_class = CourseForm
    success_url = reverse_lazy("timetable")
    success_message = "已新增課程「%(name)s」。"


class CourseUpdateView(SuccessMessageMixin, UpdateView):
    model = Course
    form_class = CourseForm
    success_url = reverse_lazy("timetable")
    success_message = "已更新課程「%(name)s」。"


class CourseDeleteView(SuccessMessageMixin, DeleteView):
    model = Course
    success_url = reverse_lazy("timetable")

    def get_success_message(self, cleaned_data):
        return f"已刪除課程「{self.object.name}」。"
