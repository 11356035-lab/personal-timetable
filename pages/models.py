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


class Course(models.Model):
    class Weekday(models.IntegerChoices):
        MONDAY = 1, "星期一"
        TUESDAY = 2, "星期二"
        WEDNESDAY = 3, "星期三"
        THURSDAY = 4, "星期四"
        FRIDAY = 5, "星期五"

    name = models.CharField("課程名稱", max_length=100)
    weekday = models.PositiveSmallIntegerField(
        "星期", choices=Weekday.choices, default=Weekday.MONDAY
    )
    start_period = models.PositiveSmallIntegerField("開始節次", choices=PERIOD_CHOICES, default=1)
    end_period = models.PositiveSmallIntegerField("結束節次", choices=PERIOD_CHOICES, default=1)
    classroom = models.CharField("教室", max_length=50, blank=True)
    teacher = models.CharField("授課教師", max_length=50, blank=True)

    class Meta:
        verbose_name = "課程"
        verbose_name_plural = "課程"
        ordering = ["weekday", "start_period"]
        constraints = [
            models.CheckConstraint(
                condition=Q(start_period__gte=1, end_period__lte=MAX_PERIOD),
                name="course_period_range",
            ),
            models.CheckConstraint(
                condition=Q(end_period__gte=F("start_period")),
                name="course_end_after_start",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def start_time(self):
        return PERIODS[self.start_period][0]

    @property
    def end_time(self):
        return PERIODS[self.end_period][1]

    @property
    def place(self):
        """教室和教師，中間空一格；沒填的不顯示"""
        return " ".join(part for part in (self.classroom, self.teacher) if part)

    def period_label(self):
        if self.start_period == self.end_period:
            return f"第 {self.start_period} 節"
        return f"第 {self.start_period}–{self.end_period} 節"
