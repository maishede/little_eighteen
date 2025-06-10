# app/main.py
import sys
import time
from pathlib import Path
import threading
import uvicorn
import cv2
from fastapi import FastAPI, Request, WebSocket, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from contextlib import asynccontextmanager
import os

# --- 路径调整开始 (保持不变) ---
current_file_path = Path(__file__).resolve()
current_app_dir = current_file_path.parent
project_root = current_app_dir.parent
sys.path.append(str(project_root))

# 导入配置和优化后的模块
from app.config import CAMERA_INDEX, CAMERA_FPS, CAMERA_RESOLUTION, APP_HOST, APP_PORT
from app.services.core import MotorControl
from app.utils.regex_commend import CommandExecutor, VoiceCommandParser

# 初始化MotorControl和CommandExecutor实例 (保持不变)
motor_controller = MotorControl()
command_executor = CommandExecutor(motor_controller)
voice_parser = VoiceCommandParser()


# --- 应用生命周期管理 (将 @asynccontextmanager async def lifespan 移动到 FastAPI 实例之前) ---
# 确保在创建 FastAPI 实例时，lifespan 函数已经定义
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("应用启动中...")
    command_executor.start_threads()
    yield
    print("应用关闭中...")
    command_executor.stop_threads()
    print("应用已关闭。")


# FastAPI 应用实例 - 只创建一次，并在这里传入 lifespan！
app = FastAPI(lifespan=lifespan)  # <--- 修正：将 lifespan 在这里传入

# 静态文件和模板挂载 (保持不变)
static_files_dir = project_root / "static"
templates_dir = project_root / "templates"

print("\n--- DEBUGGING PATHS & STATIC FILES ---")
print(f"Current File Path (main.py): {current_file_path}")
print(f"Current App Directory: {current_app_dir}")
print(f"Calculated Project Root: {project_root}")
print(f"sys.path: {sys.path}")

print(f"\nAttempting to mount static files from: {static_files_dir}")
print(f"Does static_files_dir exist?: {static_files_dir.exists()}")
print(f"Is static_files_dir a directory?: {static_files_dir.is_dir()}")

if not static_files_dir.exists():
    print(f"CRITICAL ERROR: Directory '{static_files_dir}' does not exist.")
elif not static_files_dir.is_dir():
    print(f"CRITICAL ERROR: Path '{static_files_dir}' is not a directory.")
else:
    print(f"\nContents of '{static_files_dir}' (first 10 items):")
    static_file_count = 0
    try:
        for item in static_files_dir.iterdir():
            print(f"  - {item.name} {'(dir)' if item.is_dir() else '(file)'} | Full Path: {item}")
            if item.name == "styles.css":
                print(f"    - styles.css exists?: {item.exists()}")
                print(f"    - styles.css is file?: {item.is_file()}")
            if item.name == "script.js":
                print(f"    - script.js exists?: {item.exists()}")
                print(f"    - script.js is file?: {item.is_file()}")
            if item.name == "svgs" and item.is_dir():
                print(f"    - Contents of svgs/ (first 5 items):")
                for j, svg_item in enumerate(item.iterdir()):
                    if j >= 5: break
                    print(
                        f"      - {svg_item.name} {'(dir)' if svg_item.is_dir() else '(file)'} | Full Path: {svg_item}")
            static_file_count += 1
            if static_file_count >= 10:
                print("  ... (more items)")
                break
    except Exception as e:
        print(f"Error listing contents of {static_files_dir}: {e}")

print(f"\nAttempting to load templates from: {templates_dir}")
print(f"Does templates_dir exist?: {templates_dir.exists()}")
print(f"Is templates_dir a directory?: {templates_dir.is_dir()}")
if not templates_dir.exists():
    print(f"CRITICAL ERROR: Directory '{templates_dir}' does not exist.")
elif not templates_dir.is_dir():
    print(f"CRITICAL ERROR: Path '{templates_dir}' is not a directory.")
else:
    index_html_path = templates_dir / "index.html"
    print(f"  - Looking for index.html at: {index_html_path}")
    print(f"    - index.html exists?: {index_html_path.exists()}")
    print(f"    - index.html is file?: {index_html_path.is_file()}")

print("\n--- END DEBUGGING PATHS & STATIC FILES ---\n")

# 在这里挂载静态文件和模板
app.mount("/static", StaticFiles(directory=str(static_files_dir)), name="static")
templates = Jinja2Templates(directory=str(templates_dir))


# --- 请求体模型 (保持不变) ---
class ControlCommand(BaseModel):
    direction: str


class VoiceText(BaseModel):
    text: str


# --- 视频流相关全局变量 (保持不变) ---
video_cap_lock = threading.Lock()
camera_capture: cv2.VideoCapture | None = None


# --- 视频流生成器 (保持不变) ---
def generate_frames():
    global camera_capture
    with video_cap_lock:
        if camera_capture is None or not camera_capture.isOpened():
            print(f"正在打开摄像头 {CAMERA_INDEX}...")
            camera_capture = cv2.VideoCapture(CAMERA_INDEX)
            if not camera_capture.isOpened():
                print("无法打开摄像头！")
                yield b''
                return
            camera_capture.set(cv2.CAP_PROP_FPS, CAMERA_FPS)
            camera_capture.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_RESOLUTION[0])
            camera_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_RESOLUTION[1])
            print(f"摄像头已打开: 分辨率 {CAMERA_RESOLUTION[0]}x{CAMERA_RESOLUTION[1]}, FPS: {CAMERA_FPS}")
    try:
        while True:
            with video_cap_lock:
                if camera_capture is None or not camera_capture.isOpened():
                    break
                success, frame = camera_capture.read()
            if not success:
                print("读取摄像头帧失败，尝试重新打开...")
                with video_cap_lock:
                    if camera_capture:
                        camera_capture.release()
                    camera_capture = cv2.VideoCapture(CAMERA_INDEX)
                    if not camera_capture.isOpened():
                        print("重新打开摄像头失败！")
                        break
                    camera_capture.set(cv2.CAP_PROP_FPS, CAMERA_FPS)
                    camera_capture.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_RESOLUTION[0])
                    camera_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_RESOLUTION[1])
                continue
            ret, buffer = cv2.imencode('.jpg', frame)
            if not ret:
                print("编码帧失败！")
                continue
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(1 / CAMERA_FPS)
    except Exception as e:
        print(f"视频流生成错误: {e}")
    finally:
        with video_cap_lock:
            if camera_capture:
                camera_capture.release()
                camera_capture = None
            print("摄像头资源已释放。")


@app.post("/camera/start")
async def start_camera():
    return StreamingResponse(generate_frames(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.post("/camera/stop")
async def stop_camera():
    global camera_capture
    with video_cap_lock:
        if camera_capture and camera_capture.isOpened():
            camera_capture.release()
            camera_capture = None
            print("摄像头已手动关闭。")
            return JSONResponse({"status": "ok", "message": "Camera stopped."})
        print("摄像头未运行或已关闭。")
        return JSONResponse({"status": "ok", "message": "Camera already stopped or not active."})


# --- 路由定义 (保持不变) ---
@app.websocket("/asr")
async def asr(websocket: WebSocket):
    print("ASR WebSocket 连接建立")
    try:
        while True:
            data = await websocket.receive_text()
            print(f"收到语音文本: {data}")
            parsed_command = voice_parser.parse(data)
            if parsed_command:
                command_executor.add_command(parsed_command)
                await websocket.send_text(f"已接收命令: {parsed_command}")
            else:
                await websocket.send_text("未识别出有效命令")
    except Exception as e:
        print(f"ASR WebSocket 错误: {e}")
    finally:
        print("ASR WebSocket 连接关闭")


@app.get("/health")
async def health():
    return JSONResponse({"status": "alive"})


@app.post("/control")
async def control(command: ControlCommand):
    print(f"收到控制命令: {command.direction}")
    command_executor.add_command(command.direction)
    return JSONResponse({"status": "ok", "received_command": command.direction})


@app.post("/cmd")
async def cmd(voice_text: VoiceText):
    print(f"收到文本命令: {voice_text.text}")
    parsed_command = voice_parser.parse(voice_text.text)
    if parsed_command:
        command_executor.add_command(parsed_command)
        return JSONResponse({"status": "ok", "parsed_command": parsed_command})
    return JSONResponse({"status": "no_command_parsed", "message": "未能解析出有效命令"})


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


if __name__ == '__main__':
    # Uvicorn 会自动从 app 实例中找到 lifespan 定义
    uvicorn.run(app, host=APP_HOST, port=APP_PORT)  # <--- 修正：从这里移除 lifespan=lifespan
