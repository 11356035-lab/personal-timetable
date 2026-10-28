import io
import tempfile
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import ProtectedError
from django.test import Client, TestCase
from django.urls import reverse

from .management.commands.import_courses import DEFAULT_CSV
from .models import Course, Enrollment


def course_data(**overrides):
    data = {
        "code": "IM101",
        "name": "微積分",
        "weekday": 1,
        "start_period": 2,
        "end_period": 3,
        "classroom": "A101",
        "teacher": "王老師",
    }
    data.update(overrides)
    return data


def create_course(times=None, **data):
    """建立課程和上課時段；沒給 times 時用 data 裡的星期、節次當唯一時段"""
    time = (data.pop("weekday"), data.pop("start_period"), data.pop("end_period"))
    course = Course.objects.create(**data)
    for weekday, start_period, end_period in times or [time]:
        course.times.create(weekday=weekday, start_period=start_period, end_period=end_period)
    return course


def enrolled_course(**data):
    course = create_course(**data)
    Enrollment.objects.create(course=course)
    return course


class TimetableViewTests(TestCase):
    def test_course_fills_every_period(self):
        enrolled_course(**course_data())
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
        enrolled_course(**course_data(teacher="", classroom=""))
        response = self.client.get(reverse("timetable"))
        self.assertNotContains(response, "<div></div>", html=True)

    def test_starts_empty(self):
        create_course(**course_data())
        response = self.client.get(reverse("timetable"))
        self.assertNotContains(response, "微積分")
        self.assertContains(response, "目前還沒有加選任何課程")
        self.assertContains(response, reverse("course_list"))

    def test_enroll_then_drop_updates_timetable(self):
        course = create_course(**course_data())
        self.client.post(reverse("course_enroll", args=[course.pk]))
        self.assertContains(self.client.get(reverse("timetable")), "<div>王老師</div>", count=2, html=True)
        self.client.post(reverse("course_drop", args=[course.pk]))
        self.assertNotContains(self.client.get(reverse("timetable")), '<div class="fw-bold">微積分</div>', html=True)

    def test_multi_day_course_on_every_day(self):
        enrolled_course(**course_data(times=[(1, 3, 4), (3, 3, 4)]))
        response = self.client.get(reverse("timetable"))
        self.assertContains(response, '<div class="fw-bold">微積分</div>', count=4, html=True)

    def test_no_course_editing(self):
        enrolled_course(**course_data())
        response = self.client.get(reverse("timetable"))
        self.assertNotContains(response, "新增課程")
        self.assertNotContains(response, "/edit/")

    def test_no_lunch_row(self):
        enrolled_course(**course_data(start_period=4, end_period=5))
        for url in (reverse("timetable"), reverse("timetable_print")):
            response = self.client.get(url)
            self.assertNotContains(response, "午休")
            self.assertContains(response, "<div>王老師</div>", count=2, html=True)


class TimetablePrintViewTests(TestCase):
    def test_print_page_shows_grid(self):
        enrolled_course(**course_data())
        response = self.client.get(reverse("timetable_print"))
        self.assertContains(response, "星期一")
        self.assertContains(response, "第 9 節")
        self.assertContains(response, "<div>王老師</div>", count=2, html=True)

    def test_timetable_links_to_print_page(self):
        response = self.client.get(reverse("timetable"))
        self.assertContains(response, reverse("timetable_print"))


class EnrollmentRuleTests(TestCase):
    def setUp(self):
        self.course = create_course(**course_data())

    def enroll(self, course):
        enrollment = Enrollment(course=course)
        enrollment.full_clean()
        enrollment.save()
        return enrollment

    def test_duplicate_rejected(self):
        self.enroll(self.course)
        with self.assertRaisesMessage(ValidationError, "已經加選過「微積分」"):
            self.enroll(self.course)

    def test_conflict_rejected(self):
        self.enroll(self.course)
        other = create_course(**course_data(code="IM102", name="線性代數", start_period=3, end_period=4))
        with self.assertRaisesMessage(ValidationError, "時間衝突：與 「微積分」（星期一 第 2–3 節） 重疊"):
            self.enroll(other)

    def test_adjacent_and_other_day_allowed(self):
        self.enroll(self.course)
        self.enroll(create_course(**course_data(code="IM102", name="英文", start_period=4, end_period=4)))
        self.enroll(create_course(**course_data(code="IM103", name="物理", weekday=2)))
        self.assertEqual(Enrollment.objects.count(), 3)

    def test_conflict_on_second_time_slot(self):
        math = create_course(**course_data(code="IM102", name="數學", times=[(1, 5, 6), (3, 3, 4)]))
        self.enroll(math)
        other = create_course(**course_data(code="IM103", name="會計", weekday=3, start_period=4, end_period=5))
        with self.assertRaisesMessage(ValidationError, "「數學」（星期一 第 5–6 節、星期三 第 3–4 節）"):
            self.enroll(other)

    def test_enrolled_course_cannot_be_deleted(self):
        self.enroll(self.course)
        with self.assertRaises(ProtectedError):
            self.course.delete()


class ImportCoursesTests(TestCase):
    HEADER = "課程代碼,班級,科目名稱,授課教師,星期,開始節次,結束節次,教室,學分,選修別\n"

    def write_csv(self, body):
        f = tempfile.NamedTemporaryFile("w", suffix=".csv", encoding="utf-8-sig", delete=False)
        with f:
            f.write(self.HEADER + body)
        self.addCleanup(Path(f.name).unlink)
        return f.name

    def test_project_csv_imports(self):
        call_command("import_courses", stdout=io.StringIO())
        lines = DEFAULT_CSV.read_text(encoding="utf-8-sig").splitlines()[1:]
        self.assertEqual(Course.objects.count(), len({line.split(",")[0] for line in lines}))
        course = Course.objects.get(code="IM104")
        self.assertEqual(course.name, "程式設計(一)(上)")
        self.assertEqual(course.teacher, "林宏仁")
        self.assertEqual(course.time_label(), "星期一 第 1–2 節")
        # 數學一分兩天上
        self.assertEqual(Course.objects.get(code="IM108").time_label(), "星期一 第 3–4 節、星期三 第 3–4 節")

    def test_reimport_updates_without_duplicates(self):
        path = self.write_csv("X1,甲班,舊名稱,王老師,1,1,2,A101,2.5,專必\n")
        call_command("import_courses", path, stdout=io.StringIO())
        path = self.write_csv("X1,甲班,新名稱,王老師,1,1,2,A101,2.5,專必\n")
        call_command("import_courses", path, stdout=io.StringIO())
        course = Course.objects.get()
        self.assertEqual(course.name, "新名稱")
        self.assertEqual(str(course.credits), "2.5")

    def test_rows_with_same_code_become_time_slots(self):
        path = self.write_csv("X1,甲班,數學,王老師,1,3,4,A101,4,通必\nX1,甲班,數學,王老師,3,3,4,A101,4,通必\n")
        call_command("import_courses", path, stdout=io.StringIO())
        self.assertEqual(Course.objects.get().time_label(), "星期一 第 3–4 節、星期三 第 3–4 節")
        # 重新匯入時，時段整批換掉
        path = self.write_csv("X1,甲班,數學,王老師,2,1,2,A101,4,通必\n")
        call_command("import_courses", path, stdout=io.StringIO())
        self.assertEqual(Course.objects.get().time_label(), "星期二 第 1–2 節")

    def test_inconsistent_rows_rejected(self):
        path = self.write_csv("X1,甲班,數學,王老師,1,3,4,A101,4,通必\nX1,甲班,數學,李老師,3,3,4,A101,4,通必\n")
        with self.assertRaisesMessage(CommandError, "第 3 行（X1）的課程資料與第 2 行不一致"):
            call_command("import_courses", path)
        self.assertFalse(Course.objects.exists())

    def test_invalid_row_rejected(self):
        path = self.write_csv("X1,甲班,課程,王老師,1,5,3,A101,1,專必\n")
        with self.assertRaisesMessage(CommandError, "第 2 行（X1）資料有誤"):
            call_command("import_courses", path)
        self.assertFalse(Course.objects.exists())


class CourseListViewTests(TestCase):
    def setUp(self):
        self.course = create_course(**course_data(class_name="一年甲班", credits=2))
        self.other = create_course(
            **course_data(code="IM201", name="經濟學", class_name="二年甲班", start_period=3, end_period=4)
        )
        self.free = create_course(**course_data(code="IM202", name="物理", class_name="二年甲班", weekday=2))

    def test_lists_courses_with_enroll_buttons(self):
        response = self.client.get(reverse("course_list"))
        self.assertContains(response, "IM101")
        self.assertContains(response, "星期一 第 2–3 節")
        self.assertContains(response, reverse("course_enroll", args=[self.course.pk]))
        self.assertContains(response, "csrfmiddlewaretoken")

    def test_filter_by_class(self):
        response = self.client.get(reverse("course_list"), {"class": "二年甲班"})
        self.assertNotContains(response, "微積分")
        self.assertContains(response, "經濟學")
        # 班級依年級排列
        self.assertLess(response.content.decode().index("一年甲班"), response.content.decode().index("二年甲班"))

    def test_shows_drop_and_conflict_status(self):
        Enrollment.objects.create(course=self.course)
        response = self.client.get(reverse("course_list"))
        self.assertContains(response, reverse("course_drop", args=[self.course.pk]))
        self.assertContains(response, "與「微積分」時間衝突")
        self.assertNotContains(response, reverse("course_enroll", args=[self.other.pk]))
        self.assertContains(response, reverse("course_enroll", args=[self.free.pk]))
        self.assertContains(response, "已選 1 門、2 學分")


class EnrollViewTests(TestCase):
    def setUp(self):
        self.course = create_course(**course_data())

    def test_post_enrolls_and_shows_on_timetable(self):
        response = self.client.post(reverse("course_enroll", args=[self.course.pk]), follow=True)
        self.assertRedirects(response, reverse("course_list"))
        self.assertContains(response, "已加選「微積分」")
        self.assertTrue(Enrollment.objects.filter(course=self.course).exists())

    def test_get_not_allowed(self):
        response = self.client.get(reverse("course_enroll", args=[self.course.pk]))
        self.assertEqual(response.status_code, 405)
        self.assertFalse(Enrollment.objects.exists())

    def test_duplicate_rejected(self):
        Enrollment.objects.create(course=self.course)
        response = self.client.post(reverse("course_enroll", args=[self.course.pk]), follow=True)
        self.assertContains(response, "已經加選過「微積分」")
        self.assertContains(response, "alert-danger")
        self.assertEqual(Enrollment.objects.count(), 1)

    def test_conflict_rejected(self):
        Enrollment.objects.create(course=self.course)
        other = create_course(**course_data(code="IM102", name="線性代數", start_period=3, end_period=4))
        response = self.client.post(reverse("course_enroll", args=[other.pk]), follow=True)
        self.assertContains(response, "時間衝突")
        self.assertFalse(Enrollment.objects.filter(course=other).exists())

    def test_returns_to_filtered_list(self):
        next_url = reverse("course_list") + "?class=%E4%B8%80%E5%B9%B4%E7%94%B2%E7%8F%AD"
        response = self.client.post(reverse("course_enroll", args=[self.course.pk]), {"next": next_url})
        self.assertRedirects(response, next_url)

    def test_external_next_ignored(self):
        response = self.client.post(
            reverse("course_enroll", args=[self.course.pk]), {"next": "https://evil.example.com/"}
        )
        self.assertRedirects(response, reverse("course_list"))

    def test_csrf_required(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(reverse("course_enroll", args=[self.course.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Enrollment.objects.exists())

    def test_unknown_course_404(self):
        response = self.client.post(reverse("course_enroll", args=[999]))
        self.assertEqual(response.status_code, 404)


class DropViewTests(TestCase):
    def setUp(self):
        self.course = create_course(**course_data())
        Enrollment.objects.create(course=self.course)

    def test_get_shows_confirmation_without_dropping(self):
        response = self.client.get(reverse("course_drop", args=[self.course.pk]))
        self.assertContains(response, "確定要退選")
        self.assertContains(response, "csrfmiddlewaretoken")
        self.assertTrue(Enrollment.objects.exists())

    def test_post_drops_but_keeps_course(self):
        response = self.client.post(reverse("course_drop", args=[self.course.pk]), follow=True)
        self.assertRedirects(response, reverse("course_list"))
        self.assertContains(response, "已退選「微積分」")
        self.assertFalse(Enrollment.objects.exists())
        self.assertTrue(Course.objects.filter(pk=self.course.pk).exists())

    def test_not_enrolled_404(self):
        other = create_course(**course_data(code="IM102", name="英文", weekday=2))
        response = self.client.post(reverse("course_drop", args=[other.pk]))
        self.assertEqual(response.status_code, 404)

    def test_csrf_required(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(reverse("course_drop", args=[self.course.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Enrollment.objects.exists())


class SelectClassTests(TestCase):
    def setUp(self):
        def make(code, name, category, **overrides):
            return create_course(**course_data(code=code, name=name, class_name="一年甲班", category=category, **overrides))

        self.major = make("IM101", "程式設計", "專必", weekday=1)
        self.general = make("IM102", "國文", "通必", weekday=2)
        self.pe = make("IM103", "體育", "一般", weekday=3)
        self.elective = make("IM104", "運算思維", "專選", weekday=4)
        self.group_a = make("IM105", "專案設計(A組)", "專必", weekday=5)
        self.group_b = make("IM106", "專案設計(B組)", "專必", weekday=5)
        self.other_class = create_course(**course_data(code="IM201", name="經濟學", class_name="二年甲班", category="專必"))

    def select(self, class_name="一年甲班", **kwargs):
        return self.client.post(reverse("select_class"), {"class": class_name}, **kwargs)

    def enrolled_codes(self):
        return set(Enrollment.objects.values_list("course__code", flat=True))

    def test_empty_timetable_shows_class_buttons(self):
        response = self.client.get(reverse("timetable"))
        self.assertContains(response, 'name="class" value="一年甲班"')
        self.assertContains(response, 'name="class" value="二年甲班"')
        self.assertNotContains(response, "重新選擇年級")

    def test_select_adds_required_courses_only(self):
        response = self.select(follow=True)
        self.assertRedirects(response, reverse("timetable"))
        self.assertEqual(self.enrolled_codes(), {"IM101", "IM102", "IM103"})
        self.assertContains(response, "已加入一年甲班的 3 門必修課")
        self.assertContains(response, "「專案設計」有分組，請到課程清單自行加選一組")
        self.assertContains(response, "重新選擇年級")

    def test_select_replaces_existing_courses(self):
        Enrollment.objects.create(course=self.other_class)
        self.select()
        self.assertEqual(self.enrolled_codes(), {"IM101", "IM102", "IM103"})

    def test_conflicting_required_course_skipped(self):
        create_course(**course_data(code="IM107", name="會計", class_name="一年甲班", category="專必", weekday=1))
        response = self.select(follow=True)
        self.assertNotIn("IM107", self.enrolled_codes())
        self.assertContains(response, "「會計」和其他必修課時間衝突，沒有加入")

    def test_get_shows_confirmation_without_changes(self):
        Enrollment.objects.create(course=self.other_class)
        response = self.client.get(reverse("select_class"), {"class": "一年甲班"})
        self.assertContains(response, "將自動加入此年級的 3 門必修課")
        self.assertContains(response, "目前課表上的 1 門課會先全部退選")
        self.assertContains(response, "csrfmiddlewaretoken")
        self.assertEqual(self.enrolled_codes(), {"IM201"})

    def test_unknown_class_404(self):
        self.assertEqual(self.select("不存在的班").status_code, 404)
        self.assertEqual(self.client.get(reverse("select_class"), {"class": "不存在的班"}).status_code, 404)

    def test_csrf_required(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(reverse("select_class"), {"class": "一年甲班"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Enrollment.objects.exists())


class OverviewViewTests(TestCase):
    def setUp(self):
        self.calc = create_course(**course_data(class_name="一年甲班", category="專必"))
        create_course(**course_data(code="IM102", name="選修課", class_name="一年甲班", category="專選", weekday=2))
        create_course(**course_data(code="IM201", name="經濟學", class_name="二年甲班"))

    def test_defaults_to_first_class_with_all_courses(self):
        response = self.client.get(reverse("overview"))
        self.assertContains(response, '<div class="fw-bold">微積分</div>', count=2, html=True)
        self.assertContains(response, '<div class="fw-bold">選修課</div>', count=2, html=True)
        self.assertNotContains(response, "經濟學")

    def test_select_other_class(self):
        response = self.client.get(reverse("overview"), {"class": "二年甲班"})
        self.assertContains(response, '<div class="fw-bold">經濟學</div>', count=2, html=True)
        self.assertNotContains(response, "微積分")

    def test_shared_slot_shows_count(self):
        for code, group in (("IM103", "A"), ("IM104", "B"), ("IM105", "C")):
            create_course(**course_data(code=code, name=f"專題({group}組)", class_name="一年甲班", weekday=5))
        response = self.client.get(reverse("overview"))
        self.assertContains(response, "等 3 門", count=2)

    def test_enrolled_highlighted_first(self):
        other = create_course(**course_data(code="IM103", name="同時段", class_name="一年甲班"))
        Enrollment.objects.create(course=other)
        response = self.client.get(reverse("overview"))
        # 已選的課排在格子最前面，並標成 enrolled
        self.assertContains(response, '<div class="fw-bold">同時段</div>', count=2, html=True)
        self.assertContains(response, 'class="course enrolled"', count=2)

    def test_unknown_class_404(self):
        response = self.client.get(reverse("overview"), {"class": "不存在的班"})
        self.assertEqual(response.status_code, 404)

