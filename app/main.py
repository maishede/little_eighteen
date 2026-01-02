# app/main.py (更新后的文件内容)
import sys
import time
import asyncio
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
import logging
from logging.handlers import RotatingFileHandler

# --- 路径调整开始 (保持不变) ---
current_file_path = Path(__file__).resolve()
current_app_dir = current_file_path.parent
project_root = current_app_dir.parent
sys.path.append(str(project_root))

# 导入配置和优化后的模块
from app.config import (
    CAMERA_INDEX, CAMERA_FPS, CAMERA_RESOLUTION, APP_HOST, APP_PORT,
    LOG_DIR, LOG_FILE_NAME, LOG_MAX_BYTES, LOG_BACKUP_COUNT, LOG_LEVEL,
    LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_NAME
)
from app.services.core import MotorControl
from app.utils.regex_command import CommandExecutor, VoiceCommandParser
from app.utils.robot_demos import RobotDemos
from app.utils.camera_streamer import CameraStreamer

from app.network_manager_nm import start_network_watcher
from app.wifi_setup_nm import router as setup_router
from app.services.llm_agent import SmartCarAgent
from app.services.voice_service import RhinoVoiceService

IS_SMART_MODE = False

# --- 日志设置 (保持不变) ---
# 确保日志目录存在
os.makedirs(LOG_DIR, exist_ok=True)
log_file_path = os.path.join(LOG_DIR, LOG_FILE_NAME)

# 创建 logger 实例
logger = logging.getLogger()
logger.setLevel(LOG_LEVEL)

if logger.hasHandlers():
    logger.handlers.clear()

# 创建一个 RotatingFileHandler，用于按大小切割日志文件
file_handler = RotatingFileHandler(
    log_file_path,
    maxBytes=LOG_MAX_BYTES,
    backupCount=LOG_BACKUP_COUNT,
    encoding='utf-8'
)

# 创建一个 StreamHandler，用于将日志输出到控制台
console_handler = logging.StreamHandler(sys.stdout)

# 定义日志格式
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# 添加处理器到 logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

# --- 初始化模块实例为 None (在 lifespan 中初始化) ---
motor_controller: MotorControl = None
command_executor: CommandExecutor = None
voice_parser: VoiceCommandParser = None
robot_demos: RobotDemos = None
# camera_streamer 的初始化调整：不再在 lifespan 中立即尝试打开摄像头
# 而是在 camera_streamer 实例创建后，将 open/start_camera_capture 延迟到 API 调用
camera_streamer: CameraStreamer = None
llm_agent: SmartCarAgent = None
rhino_service: RhinoVoiceService = None


# --- 应用生命周期管理 (修改这里，不再在启动时尝试打开摄像头) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动网络自动切换
    start_network_watcher()

    global motor_controller, command_executor, voice_parser, robot_demos, camera_streamer, llm_agent, rhino_service
    logger.info("应用启动中...")
    try:
        motor_controller = MotorControl()
        command_executor = CommandExecutor(motor_controller, logger)
        voice_parser = VoiceCommandParser()
        robot_demos = RobotDemos(command_executor, logger)
        # 启动后台异步任务
        await command_executor.start_tasks()

        camera_streamer = CameraStreamer(CAMERA_INDEX, CAMERA_FPS, CAMERA_RESOLUTION, logger)

        app.include_router(setup_router)  # 加上这行
        llm_agent = SmartCarAgent(
            motor=motor_controller,
            api_key=LLM_API_KEY,
            base_url=LLM_BASE_URL,
            model_name=LLM_MODEL_NAME
        )
        try:
            logger.info("正在启动离线语音服务 (Rhino)...")
            rhino_service = RhinoVoiceService(command_executor)
            rhino_service.start()
        except Exception as e:
            logger.error(f"语音服务启动失败: {e}")
        yield
    except Exception as e:
        logger.error(f"应用启动失败: {e}", exc_info=True)
        logger.critical("应用程序核心服务初始化失败，正在退出！", exc_info=True)
        sys.exit(1)  # 强制退出应用
    finally:
        logger.info("应用关闭中...")
        await command_executor.stop_tasks()  # 异步停止
        if rhino_service:
            rhino_service.stop()
        if camera_streamer:
            camera_streamer.stop_camera_capture()
        logger.info("再见。")


# FastAPI 应用实例
app = FastAPI(lifespan=lifespan)

# 静态文件和模板挂载 (保持不变)
static_files_dir = project_root / "static"
templates_dir = project_root / "templates"
app.mount("/static", StaticFiles(directory=str(static_files_dir)), name="static")
templates = Jinja2Templates(directory=str(templates_dir))

# 调试信息可以保留或移除 (保持不变)
logger.debug("\n--- DEBUGGING PATHS & STATIC FILES ---")
logger.debug(f"Current File Path (main.py): {current_file_path}")
logger.debug(f"Current App Directory: {current_app_dir}")
logger.debug(f"Calculated Project Root: {project_root}")
logger.debug(f"sys.path: {sys.path}")

logger.debug(f"\nAttempting to mount static files from: {static_files_dir}")
logger.debug(f"Does static_files_dir exist?: {static_files_dir.exists()}")
logger.debug(f"Is static_files_dir a directory?: {static_files_dir.is_dir()}")

if not static_files_dir.exists():
    logger.error(f"CRITICAL ERROR: Directory '{static_files_dir}' does not exist.")
elif not static_files_dir.is_dir():
    logger.error(f"CRITICAL ERROR: Path '{static_files_dir}' is not a directory.")
else:
    logger.debug(f"\nContents of '{static_files_dir}' (first 10 items):")
    static_file_count = 0
    try:
        for item in static_files_dir.iterdir():
            logger.debug(f"  - {item.name} {'(dir)' if item.is_dir() else '(file)'} | Full Path: {item}")
            if item.name == "styles.css":
                logger.debug(f"    - styles.css exists?: {item.exists()}")
                logger.debug(f"    - styles.css is file?: {item.is_file()}")
            if item.name == "script.js":
                logger.debug(f"    - script.js exists?: {item.is_file()}")
            if item.name == "svgs" and item.is_dir():
                logger.debug(f"    - Contents of svgs/ (first 5 items):")
                for j, svg_item in enumerate(item.iterdir()):
                    if j >= 5: break
                    logger.debug(
                        f"      - {svg_item.name} {'(dir)' if svg_item.is_dir() else '(file)'} | Full Path: {svg_item}")
            static_file_count += 1
            if static_file_count >= 10:
                logger.debug("  ... (more items)")
                break
    except Exception as e:
        logger.error(f"Error listing contents of {static_files_dir}: {e}")

logger.debug(f"\nAttempting to load templates from: {templates_dir}")
logger.debug(f"Does templates_dir exist?: {templates_dir.exists()}")
logger.debug(f"Is templates_dir a directory?: {templates_dir.is_dir()}")
if not templates_dir.exists():
    logger.error(f"CRITICAL ERROR: Directory '{templates_dir}' does not exist.")
elif not templates_dir.is_dir():
    logger.error(f"CRITICAL ERROR: Path '{templates_dir}' is not a directory.")
else:
    index_html_path = templates_dir / "index.html"
    logger.debug(f"  - Looking for index.html at: {index_html_path}")
    logger.debug(f"    - index.html exists?: {index_html_path.exists()}")
    logger.debug(f"    - index.html is file?: {index_html_path.is_file()}")

logger.debug("\n--- END DEBUGGING PATHS & STATIC FILES ---\n")


# 在这里挂载静态文件和模板 (保持不变)


# --- 请求体模型 (保持不变) ---
class ControlCommand(BaseModel):
    direction: str


class VoiceText(BaseModel):
    text: str


class DemoCommand(BaseModel):
    demo_name: str


class SpeedCommand(BaseModel):
    speed: int


# --- 摄像头 API 路由 (修改这里) ---
@app.post("/camera/start")  # 这个路由只负责"启动"摄像头服务
async def start_camera_api():
    """启动摄像头后台服务"""
    if not camera_streamer:
        raise HTTPException(status_code=503, detail="Service not initialized")

    if camera_streamer.start_camera_capture():
        return {"status": "success", "message": "Camera started"}
    else:
        raise HTTPException(status_code=500, detail="Failed to open camera hardware")


@app.get("/video_feed")  # 获取视频流
async def video_feed():
    """获取视频流数据"""
    if camera_streamer and camera_streamer.is_streaming_active():
        return StreamingResponse(
            camera_streamer.generate_frames(),
            media_type="multipart/x-mixed-replace; boundary=frame"
        )
    else:
        return JSONResponse(status_code=404, content={"message": "Camera not running"})


@app.post("/camera/stop")
async def stop_camera_api():
    """停止摄像头服务"""
    if camera_streamer:
        camera_streamer.stop_camera_capture()
    return {"status": "success", "message": "Camera stopped"}


# --- 其他路由定义 (保持不变) ---
@app.websocket("/asr")
async def asr(websocket: WebSocket):
    global IS_SMART_MODE
    await websocket.accept()
    try:
        while True:
            text = await websocket.receive_text()
            logger.info(f"收到语音文本: {text}")
            cmd = voice_parser.parse(text)
            if cmd == "SYSTEM_SWITCH_SMART":
                IS_SMART_MODE = True
                await websocket.send_text("已切换到：智能模式 (Cloud AI)")
                continue  # 跳过后续处理

            elif cmd == "SYSTEM_SWITCH_NORMAL":
                IS_SMART_MODE = False
                await websocket.send_text("已切换到：指令模式 (Offline)")
                continue
            if not IS_SMART_MODE:
                if cmd:
                    await command_executor.add_command(cmd)  # await add_command
                    await websocket.send_text(f"执行: {cmd}")
                else:
                    await websocket.send_text("未知命令")
            else:
                # === 在线智能模式 ===
                # 不再进行正则匹配，直接把整句话扔给 LLM
                await websocket.send_text("正在思考...")

                # 这里可以接入 Cloud ASR (如果是音频流的话)
                # 目前假设 text 已经是文本

                response = await llm_agent.process_command(text)
                await websocket.send_text(f"AI回复: {response}")
    except Exception as e:
        logger.error(f"ASR WebSocket 错误: {e}")


@app.post("/control")
async def control(command: ControlCommand):
    await command_executor.add_command(command.direction)
    return {"status": "ok", "cmd": command.direction}


@app.post("/cmd")
async def cmd(voice_text: VoiceText):
    cmd = voice_parser.parse(voice_text.text)
    if cmd:
        await command_executor.add_command(cmd)
        return {"status": "ok", "cmd": cmd}
    return {"status": "fail"}


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    logger.info("API: 收到根路径请求，返回 index.html。")
    return templates.TemplateResponse("index.html", {"request": request})


# --- 演示功能 API (保持不变) ---
@app.post("/demo/start")
async def start_demo(command: DemoCommand):
    if await robot_demos.start_demo(command.demo_name):
        return {"status": "success"}
    raise HTTPException(409, "Demo failed to start")


@app.post("/demo/stop")
async def stop_demo():
    if await robot_demos.stop_demo():
        return {"status": "success"}
    return {"status": "info", "msg": "No demo running"}


@app.post("/control/speed")
async def adjust_speed(cmd: SpeedCommand):
    """调整小车速度"""
    if motor_controller:
        motor_controller.set_speed(cmd.speed)
        return {"status": "success", "current_speed": motor_controller.get_speed()}
    return JSONResponse(status_code=503, content={"error": "Controller not initialized"})


@app.get("/control/speed")
async def get_speed():
    """获取当前速度"""
    if motor_controller:
        return {"status": "success", "current_speed": motor_controller.get_speed()}
    return JSONResponse(status_code=503, content={"error": "Controller not initialized"})


@app.get("/health")
async def health():
    logger.info("API: 健康检查请求。")
    return JSONResponse({"status": "alive"})


# --- 音频采样 API ---
@app.get("/audio/samples/stats")
async def get_audio_sample_stats():
    """获取音频采样统计信息"""
    if rhino_service and rhino_service.sampler:
        stats = rhino_service.sampler.get_statistics()
        return JSONResponse({"status": "success", "data": stats})
    return JSONResponse({"status": "error", "message": "Audio sampler not enabled"}, status_code=503)


@app.post("/audio/samples/clear")
async def clear_audio_samples(sample_type: str = None):
    """清空音频样本

    Args:
        sample_type: 要清空的样本类型 (motor, wheel_noise, speech, mixed, background)
                     None 表示清空所有类型
    """
    if rhino_service and rhino_service.sampler:
        rhino_service.sampler.clear_samples(sample_type)
        return JSONResponse({
            "status": "success",
            "message": f"Cleared samples: {sample_type or 'all'}"
        })
    return JSONResponse({"status": "error", "message": "Audio sampler not enabled"}, status_code=503)


if __name__ == '__main__':
    logger.info(f"启动 Uvicorn 服务器在 {APP_HOST}:{APP_PORT}")
    uvicorn.run(app, host=APP_HOST, port=APP_PORT)
