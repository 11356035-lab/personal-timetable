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

        # starts[(星期, 節次)] = 從這格開始的課；covered = 被跨節課程佔掉、不用畫的格子
        starts = {}
        covered = set()
        for course in Course.objects.all():
            starts[(course.weekday, course.start_period)] = course
            for period in range(course.start_period + 1, course.end_period + 1):
                covered.add((course.weekday, period))

        rows = []
        for period, (start_time, end_time) in PERIODS.items():
            cells = []
            for weekday, _ in weekdays:
                key = (weekday, period)
                if key in covered:
                    continue
                course = starts.get(key)
                rowspan = 1
                if course:
                    rowspan = course.period_span
                    # 跨過午休的課，要多佔午休那一列
                    if course.start_period <= 4 < course.end_period:
                        rowspan += 1
                cells.append({"course": course, "rowspan": rowspan})
            rows.append({
                "period": period,
                "start_time": start_time,
                "end_time": end_time,
                "cells": cells,
            })
            if period == 4:
                # 午休列：被跨午休課程佔掉的那幾天不用畫
                lunch_days = [
                    weekday for weekday, _ in weekdays
                    if (weekday, 5) not in covered
                ]
                rows.append({"is_lunch": True, "cells": lunch_days})

        context["weekdays"] = weekdays
        context["rows"] = rows
        return context


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
