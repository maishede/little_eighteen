# -*- coding: utf-8 -*-
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
from pydantic import BaseModel # 引入 Pydantic 模型
from contextlib import asynccontextmanager # 用于管理应用生命周期

# 获取项目根目录并添加到 sys.path
project_root = str(Path(__file__).resolve().parents[1])
sys.path.append(project_root)

# 导入配置和优化后的模块
from app.config import CAMERA_INDEX, CAMERA_FPS, CAMERA_RESOLUTION, APP_HOST, APP_PORT, ASR_SERVER_URL
from app.services.core import MotorControl
from app.utils.regex_commend import CommandExecutor, VoiceCommandParser # 引入 CommandExecutor 和 VoiceCommandParser

# 初始化MotorControl和CommandExecutor实例
# MotorControl应该是一个单例或者全局可访问的，确保所有操作都在同一个GPIO实例上
motor_controller = MotorControl()
command_executor = CommandExecutor(motor_controller)
voice_parser = VoiceCommandParser() # 语音命令解析器

# FastAPI 应用实例
app = FastAPI()

# 挂载静态文件和模板
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# --- 应用生命周期管理 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 应用生命周期管理
    在应用启动时启动后台线程，在应用关闭时停止并清理资源
    """
    print("应用启动中...")
    command_executor.start_threads() # 启动命令执行和距离监控线程
    yield
    print("应用关闭中...")
    command_executor.stop_threads() # 停止所有后台线程并清理GPIO
    print("应用已关闭。")

app = FastAPI(lifespan=lifespan) # 将lifespan上下文管理器应用到FastAPI实例


# --- 请求体模型 ---
class ControlCommand(BaseModel):
    direction: str

class VoiceText(BaseModel):
    text: str

# --- 视频流相关全局变量 ---
# 线程安全的摄像头捕获对象
# 使用threading.Lock来确保对cap的访问是线程安全的，虽然在单个generate_frames函数中不太明显，但为了潜在的未来扩展
video_cap_lock = threading.Lock()
# 将摄像头对象作为全局变量，以便在需要时进行启停
camera_capture: cv2.VideoCapture | None = None


# --- 视频流生成器 ---
def generate_frames():
    global camera_capture

    # 惰性初始化摄像头，仅当需要时才打开
    with video_cap_lock:
        if camera_capture is None or not camera_capture.isOpened():
            print(f"正在打开摄像头 {CAMERA_INDEX}...")
            camera_capture = cv2.VideoCapture(CAMERA_INDEX)
            if not camera_capture.isOpened():
                print("无法打开摄像头！")
                yield b'' # 返回空帧表示失败
                return
            camera_capture.set(cv2.CAP_PROP_FPS, CAMERA_FPS)
            camera_capture.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_RESOLUTION[0])
            camera_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_RESOLUTION[1])
            print(f"摄像头已打开: 分辨率 {CAMERA_RESOLUTION[0]}x{CAMERA_RESOLUTION[1]}, FPS: {CAMERA_FPS}")

    try:
        while True:
            # camera_capture 可能在其他地方被关闭，需要检查
            with video_cap_lock:
                if camera_capture is None or not camera_capture.isOpened():
                    break # 如果摄像头已关闭，则退出循环

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
                continue # 继续下一次循环尝试读取

            ret, buffer = cv2.imencode('.jpg', frame)
            if not ret:
                print("编码帧失败！")
                continue

            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(1 / CAMERA_FPS) # 控制帧率
    except Exception as e:
        print(f"视频流生成错误: {e}")
    finally:
        # 在生成器结束时，释放摄像头资源
        with video_cap_lock:
            if camera_capture:
                camera_capture.release()
                camera_capture = None
            print("摄像头资源已释放。")


@app.post("/camera/start")
async def start_camera():
    """启动视频流"""
    # 每次请求都创建一个新的生成器，确保流的独立性
    return StreamingResponse(generate_frames(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.post("/camera/stop")
async def stop_camera():
    """停止视频流"""
    global camera_capture
    with video_cap_lock:
        if camera_capture and camera_capture.isOpened():
            camera_capture.release()
            camera_capture = None
            print("摄像头已手动关闭。")
            return JSONResponse({"status": "ok", "message": "Camera stopped."})
        print("摄像头未运行或已关闭。")
        return JSONResponse({"status": "ok", "message": "Camera already stopped or not active."})


# --- 路由定义 ---
@app.websocket("/asr")
async def asr(websocket: WebSocket):
    """
    语音识别 WebSocket 端点
    此处需要集成实际的 ASR 服务，例如连接到 Vosk 或其他语音识别服务的 WebSocket
    """
    print("ASR WebSocket 连接建立")
    # 示例：假设客户端发送文本，我们解析后发命令
    # 实际应从客户端接收音频数据，发送到 ASR 服务，接收识别结果
    try:
        while True:
            data = await websocket.receive_text()
            print(f"收到语音文本: {data}")
            # 这里应将接收到的音频数据发送给 ASR 服务
            # 假设这里是接收到 ASR 服务的识别结果
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
async def control(command: ControlCommand): # 使用 Pydantic 模型
    """接收来自前端的控制命令"""
    print(f"收到控制命令: {command.direction}")
    # 将命令添加到命令执行队列
    command_executor.add_command(command.direction)
    return JSONResponse({"status": "ok", "received_command": command.direction})


@app.post("/cmd") # 此路由用于测试或接收已解析的文本命令，非前端直接调用
async def cmd(voice_text: VoiceText): # 使用 Pydantic 模型
    """接收文本并解析为命令（模拟语音识别的输出）"""
    print(f"收到文本命令: {voice_text.text}")
    parsed_command = voice_parser.parse(voice_text.text)
    if parsed_command:
        command_executor.add_command(parsed_command)
        return JSONResponse({"status": "ok", "parsed_command": parsed_command})
    return JSONResponse({"status": "no_command_parsed", "message": "未能解析出有效命令"})


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """渲染主页面"""
    return templates.TemplateResponse("index.html", {"request": request})


if __name__ == '__main__':
    # Uvicorn 运行 FastAPI 应用
    uvicorn.run(app, host=APP_HOST, port=APP_PORT)