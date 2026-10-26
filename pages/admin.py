from django.contrib import admin

from .forms import CourseForm
from .models import Course


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    # 用同一個表單，admin 裡新增也會檢查時間衝突
    form = CourseForm
    list_display = ["name", "weekday", "start_period", "end_period", "classroom", "teacher"]
    list_filter = ["weekday"]
    search_fields = ["name", "teacher", "classroom"]
