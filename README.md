## personal-timetable
個人課表維護功能

## 啟動專案
uv sync
uv run python manage.py migrate
uv run python manage.py runserver

開啟 http://127.0.0.1:8000/


## 帳戶確認
Win+R
control /name Microsoft.CredentialManager
如果有找到 git:https://github.com 或類似的 GitHub 認證 展開後點選 移除

Vscode Ctrl+Shift+"~"
git push origin main

## 上傳檔案
git status
確認哪些檔案被修改。

git add Test/app.py
git add README.md
告訴 Git 要提交這支 Python 程式。

git add -A
把所有變更加入暫存區（包含刪除和新增的檔案）

git commit -m "Update Python code"
記錄這一次的修改。


將本機已提交的修改上傳到 GitHub。