import csv
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from pages.models import Course, CourseTime

DEFAULT_CSV = Path(settings.BASE_DIR) / "Data" / "courses.csv"

# CSV 欄位名稱 → Course 欄位
COURSE_COLUMNS = {
    "班級": "class_name",
    "科目名稱": "name",
    "授課教師": "teacher",
    "教室": "classroom",
    "學分": "credits",
    "選修別": "category",
}
# CSV 欄位名稱 → CourseTime 欄位；一門課分幾天上就寫幾行，課程代碼相同
TIME_COLUMNS = {
    "星期": "weekday",
    "開始節次": "start_period",
    "結束節次": "end_period",
}
COLUMNS = {"課程代碼", *COURSE_COLUMNS, *TIME_COLUMNS}


class Command(BaseCommand):
    help = (
        "從 CSV 匯入固定課程資料；以課程代碼比對，已存在的課程會更新，重複執行也不會產生重複資料。"
        "同一門課有多個上課時段時，每個時段一行、課程代碼相同。"
    )

    def add_arguments(self, parser):
        parser.add_argument("csv_path", nargs="?", default=DEFAULT_CSV, type=Path)

    @transaction.atomic
    def handle(self, *args, csv_path, **options):
        if not csv_path.exists():
            raise CommandError(f"找不到課程資料檔：{csv_path}")

        # utf-8-sig：用 Excel 存的 CSV 開頭會有 BOM
        with csv_path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            missing = set(COLUMNS) - set(reader.fieldnames or [])
            if missing:
                raise CommandError(f"CSV 缺少欄位：{'、'.join(sorted(missing))}")
            # 依課程代碼分組；第 1 行是標題，資料從第 2 行開始
            groups = {}
            for line, row in enumerate(reader, start=2):
                row = {column: (value or "").strip() for column, value in row.items()}
                groups.setdefault(row["課程代碼"], []).append((line, row))

        created = updated = 0
        for code, rows in groups.items():
            first_line, first_row = rows[0]
            for line, row in rows[1:]:
                if any(row[column] != first_row[column] for column in COURSE_COLUMNS):
                    raise CommandError(f"第 {line} 行（{code}）的課程資料與第 {first_line} 行不一致。")

            course = Course.objects.filter(code=code).first() or Course(code=code)
            for column, field in COURSE_COLUMNS.items():
                setattr(course, field, first_row[column])
            self.validate(course, first_line, code)

            is_new = course.pk is None
            course.save()
            if is_new:
                created += 1
            else:
                updated += 1

            # 上課時段整批換成 CSV 裡的
            course.times.all().delete()
            for line, row in rows:
                time = CourseTime(course=course, **{field: row[column] for column, field in TIME_COLUMNS.items()})
                self.validate(time, line, code)
                time.save()

        self.stdout.write(self.style.SUCCESS(f"課程匯入完成：新增 {created} 門，更新 {updated} 門。"))

    def validate(self, obj, line, code):
        try:
            obj.full_clean()
        except ValidationError as error:
            raise CommandError(f"第 {line} 行（{code}）資料有誤：{error.messages}") from error
