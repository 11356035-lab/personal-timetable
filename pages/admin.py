from django.contrib import admin

from .models import Course, CourseTime, Enrollment


class CourseTimeInline(admin.TabularInline):
    model = CourseTime
    extra = 0
    min_num = 1


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    inlines = [CourseTimeInline]
    list_display = ["code", "name", "class_name", "teacher", "time_label", "classroom", "credits", "category"]
    list_filter = ["class_name", "category"]
    search_fields = ["code", "name", "teacher", "classroom"]

    @admin.display(description="上課時間")
    def time_label(self, course):
        return course.time_label()

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("times")


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ["course", "created_at"]
    search_fields = ["course__code", "course__name"]
