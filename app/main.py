import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, UploadFile, Form, Request, BackgroundTasks, Depends, Header, HTTPException, status
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
import re
import uuid
import threading

app = FastAPI()
security = HTTPBasic()

# 讀取環境變數
USERNAME = os.getenv("APP_USER")
PASSWORD = os.getenv("APP_PASS")

if not USERNAME or not PASSWORD:
    raise RuntimeError("請設定 APP_USER 與 APP_PASS 環境變數")

# 驗證函式
def verify(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, USERNAME)
    correct_password = secrets.compare_digest(credentials.password, PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="帳號或密碼錯誤",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

UPLOAD_DIR = "uploads"
TRASH_DIR = os.path.join(UPLOAD_DIR, "trash")
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(TRASH_DIR, exist_ok=True)

# --- 安全輔助：防止路徑穿越與非法檔名 ---
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_date(date: str) -> bool:
    """確認日期為合法的 YYYY-MM-DD 格式。"""
    if not DATE_RE.match(date):
        return False
    try:
        datetime.strptime(date, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def sanitize_description(description: str) -> str:
    """移除空白、路徑分隔符、控制字元與 HTML/JS 敏感字元，避免路徑穿越與 XSS。"""
    cleaned = description.replace(" ", "")
    cleaned = re.sub(r"[/\\]", "", cleaned)
    cleaned = cleaned.replace("..", "")
    cleaned = re.sub(r"[\x00-\x1f]", "", cleaned)
    # 移除會破壞 HTML 屬性 / JS 字串的字元（防 XSS）
    cleaned = cleaned.translate(str.maketrans("", "", "\"'`<>"))
    return cleaned


def safe_join(base_dir: str, filename: str):
    """把 filename 解析到 base_dir 內；若試圖跳脫目錄則回傳 None。"""
    base = os.path.realpath(base_dir)
    target = os.path.realpath(os.path.join(base_dir, filename))
    if target == base or not target.startswith(base + os.sep):
        return None
    return target


def csrf_protect(x_requested_with: str = Header(default=None)) -> str:
    """要求自訂 Header，避免跨站請求偽造（CSRF）。"""
    if x_requested_with != "XMLHttpRequest":
        raise HTTPException(status_code=403, detail="CSRF 驗證失敗")
    return x_requested_with


VERSION = "dev"
for _path in ["/app/version.txt", "version.txt"]:
    if os.path.exists(_path):
        VERSION = open(_path).read().strip()
        break

templates = Jinja2Templates(directory="templates")

STATIC_DIR = Path(__file__).parent / "static"

# PWA：服務 Worker 與 Web App Manifest
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/manifest.webmanifest")
def pwa_manifest():
    return FileResponse(STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js", include_in_schema=False)
def pwa_service_worker():
    return FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript")

def get_lang(request: Request) -> str:
    """根據瀏覽器 Accept-Language 判斷語言"""
    lang_header = request.headers.get("accept-language", "")
    return "zh" if lang_header.startswith("zh") else "en"

# 進度追蹤字典
transcoding_progress = {}

@app.get("/")
def index(request: Request, username: str = Depends(verify)):
    files = os.listdir(UPLOAD_DIR)
    files = [f for f in files if f.endswith(".mp3")]
    files.sort(reverse=True)
    trash_count = len([f for f in os.listdir(TRASH_DIR) if f.endswith(".mp3")])
    return templates.TemplateResponse("index.html", {
        "request": request,
        "files": files,
        "trash_count": trash_count,
        "version": VERSION,
        "lang": get_lang(request)
    })

@app.post("/upload")
async def upload_file(
    file: UploadFile,
    username: str = Depends(verify),
    csrf: str = Depends(csrf_protect),
    date: str = Form(...),
    description: str = Form(...),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    # 產生新檔名
    if not validate_date(date):
        raise HTTPException(status_code=400, detail="日期格式錯誤")

    safe_description = sanitize_description(description)
    filename = f"{date}_{safe_description}.mp3"
    output_path = safe_join(UPLOAD_DIR, filename)
    if output_path is None:
        raise HTTPException(status_code=400, detail="檔名不合法")

    # 臨時檔名不要使用使用者上傳的檔名，改用隨機名稱
    temp_path = os.path.join(UPLOAD_DIR, "temp_" + uuid.uuid4().hex)

    # 檢查檔案大小
    file.file.seek(0, 2)  # 移到末尾
    size = file.file.tell()
    file.file.seek(0)  # 恢復
    if size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"檔案過大，最大 {MAX_FILE_SIZE // 1024 // 1024}MB")

    # 保存臨時文件
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 添加背景任務進行轉檔
    background_tasks.add_task(transcode_audio, temp_path, output_path, filename)

    return RedirectResponse("/", status_code=303)

@app.post("/edit")
async def edit_file(
    username: str = Depends(verify),
    csrf: str = Depends(csrf_protect),
    old_filename: str = Form(...),
    date: str = Form(...),
    description: str = Form(...)
):
    """編輯錄音的日期和說明"""
    old_path = safe_join(UPLOAD_DIR, old_filename)
    if old_path is None or not os.path.exists(old_path):
        raise HTTPException(status_code=404, detail="檔案不存在")

    if not validate_date(date):
        raise HTTPException(status_code=400, detail="日期格式錯誤")

    safe_description = sanitize_description(description)
    new_filename = f"{date}_{safe_description}.mp3"
    new_path = safe_join(UPLOAD_DIR, new_filename)
    if new_path is None:
        raise HTTPException(status_code=400, detail="檔名不合法")

    if new_path != old_path and os.path.exists(new_path):
        raise HTTPException(status_code=400, detail="同名檔案已存在")

    os.rename(old_path, new_path)
    return JSONResponse({"status": "ok", "filename": new_filename})

@app.post("/delete")
async def delete_file(username: str = Depends(verify), csrf: str = Depends(csrf_protect), filename: str = Form(...)):
    """移到回收站"""
    src = safe_join(UPLOAD_DIR, filename)
    if src is None or not os.path.exists(src):
        raise HTTPException(status_code=404, detail="檔案不存在")
    dst = safe_join(TRASH_DIR, filename)
    if dst is None:
        raise HTTPException(status_code=400, detail="檔名不合法")
    shutil.move(src, dst)
    return JSONResponse({"status": "ok"})

@app.get("/trash")
def trash_page(request: Request, username: str = Depends(verify)):
    """回收站頁面"""
    files = os.listdir(TRASH_DIR)
    files = [f for f in files if f.endswith(".mp3")]
    files.sort(reverse=True)
    return templates.TemplateResponse("trash.html", {
        "request": request,
        "files": files,
        "version": VERSION,
        "lang": get_lang(request)
    })

@app.post("/trash/restore")
async def restore_file(username: str = Depends(verify), csrf: str = Depends(csrf_protect), filename: str = Form(...)):
    """從回收站還原"""
    src = safe_join(TRASH_DIR, filename)
    if src is None or not os.path.exists(src):
        raise HTTPException(status_code=404, detail="檔案不存在")
    dst = safe_join(UPLOAD_DIR, filename)
    if dst is None:
        raise HTTPException(status_code=400, detail="檔名不合法")
    if os.path.exists(dst):
        raise HTTPException(status_code=400, detail="還原目標已存在同名檔案")
    shutil.move(src, dst)
    return JSONResponse({"status": "ok"})

@app.post("/trash/delete")
async def permanent_delete(username: str = Depends(verify), csrf: str = Depends(csrf_protect), filename: str = Form(...)):
    """永久刪除"""
    path = safe_join(TRASH_DIR, filename)
    if path is None or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="檔案不存在")
    os.remove(path)
    return JSONResponse({"status": "ok"})

def transcode_audio(temp_path: str, output_path: str, filename: str):
    """轉檔工作"""
    try:
        transcoding_progress[filename] = {"status": "轉碼中", "progress": 0}
        
        subprocess.run([
            "ffmpeg",
            "-y",
            "-nostdin",
            "-i", temp_path,
            "-vn",
            "-ar", "44100",
            "-ac", "2",
            "-b:a", "320k",
            output_path
        ], check=True)

        transcoding_progress[filename] = {"status": "完成", "progress": 100}
    except Exception as e:
        transcoding_progress[filename] = {"status": "失敗", "error": str(e)}
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        # 30 秒後清除進度記錄（用 Timer，避免佔用執行緒）
        threading.Timer(30.0, transcoding_progress.pop, args=(filename, None)).start()

@app.get("/files/{filename}")
def get_file(filename: str, username: str = Depends(verify)):
    path = safe_join(UPLOAD_DIR, filename)
    if path is None or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="檔案不存在")
    return FileResponse(path)

@app.get("/progress/{filename}")
def get_progress(filename: str, username: str = Depends(verify)):
    """獲取轉檔進度"""
    if filename in transcoding_progress:
        return transcoding_progress[filename]
    return {"status": "未知", "progress": 0}
