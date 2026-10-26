from django.test import TestCase
from django.urls import reverse

from .models import Course


def course_data(**overrides):
    data = {
        "name": "微積分",
        "weekday": 1,
        "start_period": 2,
        "end_period": 3,
        "classroom": "A101",
        "teacher": "王老師",
    }
    data.update(overrides)
    return data


class TimetableViewTests(TestCase):
    def test_shows_course(self):
        Course.objects.create(**course_data())
        response = self.client.get(reverse("timetable"))
        self.assertContains(response, "微積分")
        self.assertContains(response, "A101")
        self.assertContains(response, "09:10–11:00")
        self.assertContains(response, 'rowspan="2"')

    def test_course_across_lunch_spans_lunch_row(self):
        Course.objects.create(**course_data(start_period=4, end_period=5))
        response = self.client.get(reverse("timetable"))
        self.assertContains(response, 'rowspan="3"')


class CourseCreateTests(TestCase):
    def test_create(self):
        response = self.client.post(reverse("course_create"), course_data())
        self.assertRedirects(response, reverse("timetable"))
        self.assertEqual(Course.objects.count(), 1)

    def test_end_before_start_rejected(self):
        response = self.client.post(
            reverse("course_create"), course_data(start_period=5, end_period=3)
        )
        self.assertContains(response, "結束節次不能早於開始節次")
        self.assertEqual(Course.objects.count(), 0)

    def test_conflict_rejected(self):
        Course.objects.create(**course_data())
        response = self.client.post(
            reverse("course_create"),
            course_data(name="線性代數", start_period=3, end_period=4),
        )
        self.assertContains(response, "時間衝突")
        self.assertEqual(Course.objects.count(), 1)

    def test_adjacent_and_other_day_allowed(self):
        Course.objects.create(**course_data())
        self.client.post(reverse("course_create"), course_data(name="英文", start_period=4, end_period=4))
        self.client.post(reverse("course_create"), course_data(name="物理", weekday=2))
        self.assertEqual(Course.objects.count(), 3)


class CourseUpdateTests(TestCase):
    def test_update_without_self_conflict(self):
        course = Course.objects.create(**course_data())
        response = self.client.post(
            reverse("course_update", args=[course.pk]),
            course_data(name="微積分（二）", end_period=4, teacher="李老師"),
        )
        self.assertRedirects(response, reverse("timetable"))
        course.refresh_from_db()
        self.assertEqual(course.name, "微積分（二）")
        self.assertEqual(course.end_period, 4)
        self.assertEqual(course.teacher, "李老師")

    def test_update_into_conflict_rejected(self):
        Course.objects.create(**course_data())
        other = Course.objects.create(**course_data(name="化學", weekday=2))
        response = self.client.post(
            reverse("course_update", args=[other.pk]), course_data(name="化學", weekday=1)
        )
        self.assertContains(response, "時間衝突")
        other.refresh_from_db()
        self.assertEqual(other.weekday, 2)


class CourseDeleteTests(TestCase):
    def test_get_shows_confirmation_without_deleting(self):
        course = Course.objects.create(**course_data())
        response = self.client.get(reverse("course_delete", args=[course.pk]))
        self.assertContains(response, "確定要刪除")
        self.assertTrue(Course.objects.filter(pk=course.pk).exists())

    def test_post_deletes(self):
        course = Course.objects.create(**course_data())
        response = self.client.post(reverse("course_delete", args=[course.pk]))
        self.assertRedirects(response, reverse("timetable"))
        self.assertFalse(Course.objects.exists())
