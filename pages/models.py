import re

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

# 每一節課的上下課時間
PERIODS = {
    1: ("08:10", "09:00"),
    2: ("09:10", "10:00"),
    3: ("10:10", "11:00"),
    4: ("11:10", "12:00"),
    5: ("13:30", "14:20"),
    6: ("14:25", "15:15"),
    7: ("15:25", "16:15"),
    8: ("16:20", "17:10"),
    9: ("17:15", "18:05"),
}
MAX_PERIOD = max(PERIODS)

PERIOD_CHOICES = [(number, f"第 {number} 節") for number in PERIODS]


class Weekday(models.IntegerChoices):
    MONDAY = 1, "星期一"
    TUESDAY = 2, "星期二"
    WEDNESDAY = 3, "星期三"
    THURSDAY = 4, "星期四"
    FRIDAY = 5, "星期五"


class Course(models.Model):
    # 選年級時自動加入的選修別
    REQUIRED_CATEGORIES = ("專必", "通必", "一般")

    code = models.CharField("課程代碼", max_length=20, unique=True)
    name = models.CharField("課程名稱", max_length=100)
    class_name = models.CharField("班級", max_length=50, blank=True)
    classroom = models.CharField("教室", max_length=50, blank=True)
    teacher = models.CharField("授課教師", max_length=50, blank=True)
    credits = models.DecimalField("學分", max_digits=3, decimal_places=1, default=0)
    category = models.CharField("選修別", max_length=10, blank=True)

    class Meta:
        verbose_name = "課程"
        verbose_name_plural = "課程"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} {self.name}"

    @property
    def is_required(self):
        return self.category in self.REQUIRED_CATEGORIES

    @property
    def is_group_choice(self):
        """名稱結尾是「(A組)」這種分組課，同時段多組只能選一組"""
        return re.search(r"\(\w組\)$", self.name) is not None

    def time_label(self):
        return "、".join(str(time) for time in self.times.all())

    def overlaps(self, other):
        """任一個上課時段重疊就算衝突"""
        return any(mine.overlaps(theirs) for mine in self.times.all() for theirs in other.times.all())


class CourseTime(models.Model):
    """上課時段；一門課可以分好幾天上，例如星期一、星期三各兩節"""

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="times", verbose_name="課程")
    weekday = models.PositiveSmallIntegerField("星期", choices=Weekday.choices, default=Weekday.MONDAY)
    start_period = models.PositiveSmallIntegerField("開始節次", choices=PERIOD_CHOICES, default=1)
    end_period = models.PositiveSmallIntegerField("結束節次", choices=PERIOD_CHOICES, default=1)

    class Meta:
        verbose_name = "上課時段"
        verbose_name_plural = "上課時段"
        ordering = ["weekday", "start_period"]
        constraints = [
            models.CheckConstraint(
                condition=Q(start_period__gte=1, end_period__lte=MAX_PERIOD),
                name="coursetime_period_range",
            ),
            models.CheckConstraint(
                condition=Q(end_period__gte=F("start_period")),
                name="coursetime_end_after_start",
            ),
        ]

    def __str__(self):
        return f"{self.get_weekday_display()} {self.period_label()}"

    @property
    def start_time(self):
        return PERIODS[self.start_period][0]

    @property
    def end_time(self):
        return PERIODS[self.end_period][1]

    def period_label(self):
        if self.start_period == self.end_period:
            return f"第 {self.start_period} 節"
        return f"第 {self.start_period}–{self.end_period} 節"

    def overlaps(self, other):
        """同一天且節次區間有重疊"""
        return (
            self.weekday == other.weekday
            and self.start_period <= other.end_period
            and other.start_period <= self.end_period
        )


class Enrollment(models.Model):
    """選課紀錄；每門課最多一筆，退選只刪這筆，不動課程本身"""

    # 有人選的課不能被刪掉
    course = models.OneToOneField(
        Course, on_delete=models.PROTECT, related_name="enrollment", verbose_name="課程"
    )
    created_at = models.DateTimeField("加選時間", auto_now_add=True)

    class Meta:
        verbose_name = "選課紀錄"
        verbose_name_plural = "選課紀錄"
        ordering = ["course__code"]

    def __str__(self):
        return str(self.course)

    def clean(self):
        # 課程還沒填時交給欄位驗證處理
        if self.course_id is None:
            return

        others = Enrollment.objects.exclude(pk=self.pk)
        if others.filter(course_id=self.course_id).exists():
            raise ValidationError(f"已經加選過「{self.course.name}」。")

        conflicts = [
            enrollment.course
            for enrollment in others.select_related("course").prefetch_related("course__times")
            if enrollment.course.overlaps(self.course)
        ]
        if conflicts:
            details = "、".join(f"「{course.name}」（{course.time_label()}）" for course in conflicts)
            raise ValidationError(f"時間衝突：與 {details} 重疊。")
