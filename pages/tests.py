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
    def test_course_fills_every_period(self):
        Course.objects.create(**course_data())
        response = self.client.get(reverse("timetable"))
        # 第 2–3 節的課，兩格都要顯示
        self.assertContains(response, "<div>王老師</div>", count=2, html=True)
        self.assertContains(response, "<div>A101</div>", count=2, html=True)
        self.assertNotContains(response, "教室：")
        self.assertNotContains(response, "教師：")
        # 格子裡不顯示時間
        self.assertNotContains(response, "09:10–11:00")
        self.assertNotContains(response, "rowspan")

    def test_blank_teacher_and_classroom_not_shown(self):
        Course.objects.create(**course_data(teacher="", classroom=""))
        response = self.client.get(reverse("timetable"))
        self.assertNotContains(response, "<div></div>", html=True)

    def test_cell_links_to_edit_without_buttons(self):
        course = Course.objects.create(**course_data())
        response = self.client.get(reverse("timetable"))
        self.assertContains(response, reverse("course_update", args=[course.pk]), count=2)
        self.assertNotContains(response, reverse("course_delete", args=[course.pk]))

    def test_no_lunch_row(self):
        Course.objects.create(**course_data(start_period=4, end_period=5))
        for url in (reverse("timetable"), reverse("timetable_print")):
            response = self.client.get(url)
            self.assertNotContains(response, "午休")
            self.assertContains(response, "<div>王老師</div>", count=2, html=True)


class TimetablePrintViewTests(TestCase):
    def test_print_page_shows_grid_without_actions(self):
        course = Course.objects.create(**course_data())
        response = self.client.get(reverse("timetable_print"))
        self.assertContains(response, "星期一")
        self.assertContains(response, "第 9 節")
        self.assertContains(response, "<div>王老師</div>", count=2, html=True)
        self.assertNotContains(response, reverse("course_update", args=[course.pk]))
        self.assertNotContains(response, reverse("course_delete", args=[course.pk]))

    def test_timetable_links_to_print_page(self):
        response = self.client.get(reverse("timetable"))
        self.assertContains(response, reverse("timetable_print"))


class CourseCreateTests(TestCase):
    def test_form_defaults(self):
        response = self.client.get(reverse("course_create"))
        self.assertContains(response, '<option value="1" selected>星期一</option>', html=True)
        self.assertContains(response, '<option value="1" selected>第 1 節</option>', count=2, html=True)
        self.assertContains(response, "節次")
        self.assertNotContains(response, "開始節次")
        self.assertNotContains(response, "---------")
        self.assertNotContains(response, "（08:10–09:00）")
        self.assertNotContains(response, "刪除這門課")

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
    def test_edit_page_has_delete_button(self):
        course = Course.objects.create(**course_data())
        response = self.client.get(reverse("course_update", args=[course.pk]))
        self.assertContains(response, "刪除這門課")
        self.assertContains(response, reverse("course_delete", args=[course.pk]))

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
