## personal-timetable
個人課表維護系統（Django）。採「固定課程資料 + 加退選」的方式：課程資料由系統預先匯入，使用者只能加選、退選既有課程，不能修改課程內容。

### 功能
- **我的課表**：一開始是空白的。選擇年級後，自動加入該年級的必修課（專必、通必、一般），之後可以自由加退選。
- **課表總覽**：依年級顯示該班所有課程（必修、選修），已加選的課以深色標示。
- **課程清單**：可依班級篩選，每門課右側有「加選」或「退選」按鈕。
  - 不能重複加選；和已選課程時間衝突時會擋下，並說明和哪門課衝突。
  - 退選前有確認頁，只刪除選課紀錄，不會刪除課程資料。
- 加選、退選、選年級都使用 POST 並有 CSRF 保護。
- 選課紀錄存在 SQLite，重新整理網頁或重新啟動 Django 都會保留。

## 啟動專案（約 3 分鐘）

### 1. 安裝 uv（電腦已有 uv 可略過）
Windows PowerShell：
```
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```
安裝完請關掉終端機再重新開啟，讓 `uv` 指令生效。

### 2. 下載專案並啟動
```
git clone <本專案網址>
cd personal-timetable
uv sync
uv run python manage.py migrate
uv run python manage.py import_courses
uv run python manage.py runserver
```

開啟 http://127.0.0.1:8000/

- `uv sync` 會自動安裝 Django；電腦沒有 Python 3.12 以上時，uv 也會自動下載。
- `import_courses` 會從 `Data/courses.csv` 匯入 69 門課程，重複執行不會產生重複資料。
- 不需要建立任何帳號。

## Demo 流程
1. **我的課表**：一開始是空白的，按「五專資管一年甲班」→ 自動加入 15 門必修課。
2. **課表總覽**：切換到一年級，可以看到選修課「運算思維」（星期三第 8–9 節）沒有被加入。
3. **課程清單** → 篩選一年級 → 加選「運算思維」→ 回到我的課表，課程出現在星期三。
4. **時間衝突**：課程清單篩選五年級，「資訊系統專案設計(二)」A–H 組（星期一第 5–7 節）都顯示灰色的「時間衝突」按鈕，滑鼠移上去會看到是與一年級的「會計學(上)實習」（星期一第 5–6 節）衝突。
5. **退選**：在課程清單按「退選」→ 確認頁 →「確定退選」→ 課表上的課程消失。
6. **資料保留**：重新整理網頁，或在終端機按 Ctrl+C 停止後再 `runserver`，選課紀錄仍在。
7. **重新開始**：我的課表 →「重新選擇年級」→ 選一個年級 → 確認後會清空並加入新年級的必修課。

## 課程資料
- `Data/courses.csv`：系統匯入用的課程資料（UTF-8，可用 Excel 開啟編輯）。
  - 一個上課時段一行；同一門課分好幾天上時，寫成多行並使用相同的課程代碼（例如數學一 `IM108`）。
  - 修改後重新執行 `uv run python manage.py import_courses` 即可更新。
- `Data/資管課程.xlsx`：原始課程資料。
- 課程資料也可以在 Django admin（http://127.0.0.1:8000/admin/）管理，需先用 `uv run python manage.py createsuperuser` 建立管理員帳號。

## 執行測試
```
uv run python manage.py test pages
```

## 個人 Git 操作筆記

### 帳戶確認
Win+R
control /name Microsoft.CredentialManager
如果有找到 git:https://github.com 或類似的 GitHub 認證 展開後點選 移除

Vscode Ctrl+Shift+"~"
git push origin main

### 上傳檔案
git status
確認哪些檔案被修改。

git add Test/app.py
git add README.md
告訴 Git 要提交這支 Python 程式。

git add -A
把所有變更加入暫存區（包含刪除和新增的檔案）

git commit -m "Update Python code"
記錄這一次的修改。

git push origin main
將本機已提交的修改上傳到 GitHub。
