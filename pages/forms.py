from django import forms

from .models import Course


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ["name", "weekday", "start_period", "end_period", "classroom", "teacher"]

    def clean(self):
        cleaned_data = super().clean()
        weekday = cleaned_data.get("weekday")
        start = cleaned_data.get("start_period")
        end = cleaned_data.get("end_period")
        if weekday is None or start is None or end is None:
            return cleaned_data

        if end < start:
            self.add_error("end_period", "結束節次不能早於開始節次。")
            return cleaned_data

        # 同一天、節次區間有重疊就算衝突；修改時要排除自己
        conflicts = Course.objects.filter(
            weekday=weekday,
            start_period__lte=end,
            end_period__gte=start,
        )
        if self.instance.pk:
            conflicts = conflicts.exclude(pk=self.instance.pk)

        if conflicts.exists():
            details = "、".join(
                f"「{course.name}」（{course.period_label()}）" for course in conflicts
            )
            raise forms.ValidationError(f"時間衝突：與 {details} 重疊。")

        return cleaned_data
