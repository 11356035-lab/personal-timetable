from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import DeleteView, ListView, TemplateView

from .models import PERIODS, Course, CourseTime, Enrollment, Weekday


def class_names():
    """依課程代碼的順序列出班級（一年級在前），中文字排序會亂掉"""
    names = Course.objects.order_by("code").values_list("class_name", flat=True)
    return list(dict.fromkeys(name for name in names if name))


def timetable_rows(times, enrolled_ids=()):
    """把上課時段排成課表；每格是那一節的課程清單，跨多節的課每一節都各佔一格。
    有給 enrolled_ids 時標記已加選的課，並排在那格的最前面"""
    slots = {}
    for time in times.select_related("course").order_by("course__code"):
        time.course.is_enrolled = time.course.pk in enrolled_ids
        for period in range(time.start_period, time.end_period + 1):
            slots.setdefault((time.weekday, period), []).append(time.course)
    for cell in slots.values():
        cell.sort(key=lambda course: not course.is_enrolled)

    rows = []
    for period, (start_time, end_time) in PERIODS.items():
        rows.append({
            "period": period,
            "start_time": start_time,
            "end_time": end_time,
            "cells": [slots.get((weekday, period), []) for weekday, _ in Weekday.choices],
        })
    return rows


class TimetableView(TemplateView):
    template_name = "pages/timetable.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 只排已加選的課
        context["weekdays"] = Weekday.choices
        context["rows"] = timetable_rows(CourseTime.objects.filter(course__enrollment__isnull=False))
        context["has_courses"] = Enrollment.objects.exists()
        context["class_names"] = class_names()
        return context


class TimetablePrintView(TimetableView):
    template_name = "pages/timetable_print.html"


def redirect_back(request):
    """回到課程清單原本的篩選；next 只接受本站網址"""
    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(next_url)
    return redirect("course_list")


class CourseListView(ListView):
    model = Course
    template_name = "pages/course_list.html"

    def get_queryset(self):
        courses = super().get_queryset().prefetch_related("times")
        self.selected_class = self.request.GET.get("class", "")
        if self.selected_class:
            courses = courses.filter(class_name=self.selected_class)
        return courses

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        enrolled = list(Course.objects.filter(enrollment__isnull=False).prefetch_related("times"))

        # 標記每門課的狀態：已加選、和已選的哪門課衝突
        for course in context["course_list"]:
            course.is_enrolled = course in enrolled
            course.conflict = None
            if not course.is_enrolled:
                course.conflict = next((other for other in enrolled if other.overlaps(course)), None)

        context["class_names"] = class_names()
        context["selected_class"] = self.selected_class
        context["enrolled_count"] = len(enrolled)
        context["enrolled_credits"] = sum(course.credits for course in enrolled)
        return context


class EnrollView(View):
    http_method_names = ["post"]

    def post(self, request, pk):
        course = get_object_or_404(Course, pk=pk)
        enrollment = Enrollment(course=course)
        try:
            enrollment.full_clean()
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            enrollment.save()
            messages.success(request, f"已加選「{course.name}」。")
        return redirect_back(request)


class DropView(DeleteView):
    """GET 顯示確認頁，POST 才真的退選；只刪選課紀錄，課程本身不動"""

    template_name = "pages/drop_confirm.html"

    def get_object(self, queryset=None):
        return get_object_or_404(Enrollment.objects.select_related("course"), course_id=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["next"] = self.request.GET.get("next", reverse("course_list"))
        return context

    def form_valid(self, form):
        self.object.delete()
        messages.success(self.request, f"已退選「{self.object.course.name}」。")
        return redirect_back(self.request)


class OverviewView(TemplateView):
    """課表總覽：某個班級的所有課程，必修、選修都排進去"""

    template_name = "pages/overview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        names = class_names()
        selected = self.request.GET.get("class") or (names[0] if names else "")
        if names and selected not in names:
            raise Http404("沒有這個班級")

        enrolled_ids = set(Enrollment.objects.values_list("course_id", flat=True))
        context["weekdays"] = Weekday.choices
        context["rows"] = timetable_rows(CourseTime.objects.filter(course__class_name=selected), enrolled_ids)
        context["class_names"] = names
        context["selected_class"] = selected
        return context


class SelectClassView(View):
    """選年級：清空目前的課表，再自動加入該班的必修課。
    課表已經有課時，GET 先顯示確認頁；POST 才真的執行"""

    def get_courses(self, class_name):
        courses = Course.objects.filter(class_name=class_name).prefetch_related("times")
        if not class_name or not courses.exists():
            raise Http404("沒有這個班級")
        return courses

    def get(self, request):
        class_name = request.GET.get("class", "")
        courses = self.get_courses(class_name)
        return render(request, "pages/select_class_confirm.html", {
            "class_name": class_name,
            "required_count": sum(1 for course in courses if course.is_required and not course.is_group_choice),
            "enrolled": Course.objects.filter(enrollment__isnull=False),
        })

    @transaction.atomic
    def post(self, request):
        class_name = request.POST.get("class", "")
        courses = self.get_courses(class_name)

        Enrollment.objects.all().delete()
        added, skipped, groups = [], [], []
        for course in courses:
            if not course.is_required:
                continue
            # 分組課同時段多組只能選一組，留給學生自己選
            if course.is_group_choice:
                groups.append(course)
                continue
            enrollment = Enrollment(course=course)
            try:
                enrollment.full_clean()
            except ValidationError:
                skipped.append(course)
            else:
                enrollment.save()
                added.append(course)

        messages.success(request, f"已加入{class_name}的 {len(added)} 門必修課。")
        if groups:
            # 「資訊系統專案設計(二)(A組)」→「資訊系統專案設計(二)」
            group_names = "、".join(dict.fromkeys(f"「{course.name.rsplit('(', 1)[0]}」" for course in groups))
            messages.info(request, f"{group_names}有分組，請到課程清單自行加選一組。")
        if skipped:
            names = "、".join(f"「{course.name}」" for course in skipped)
            messages.warning(request, f"{names}和其他必修課時間衝突，沒有加入。")
        return redirect("timetable")
