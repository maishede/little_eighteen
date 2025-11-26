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
    LOG_DIR, LOG_FILE_NAME, LOG_MAX_BYTES, LOG_BACKUP_COUNT, LOG_LEVEL
)
from app.services.core import MotorControl
from app.utils.regex_command import CommandExecutor, VoiceCommandParser
from app.utils.robot_demos import RobotDemos
from app.utils.camera_streamer import CameraStreamer  # <-- 新增导入 CameraStreamer
from app.network_manager import auto_network_mode
import threading
from app.wifi_setup import router as setup_router

# --- 日志设置 (保持不变) ---
# 确保日志目录存在
os.makedirs(LOG_DIR, exist_ok=True)
log_file_path = os.path.join(LOG_DIR, LOG_FILE_NAME)

# 创建 logger 实例
logger = logging.getLogger("robot_app_logger")
logger.setLevel(LOG_LEVEL)

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

# --- 初始化模块实例为 None (在 lifespan 中初始化) ---
motor_controller: MotorControl = None
command_executor: CommandExecutor = None
voice_parser: VoiceCommandParser = None
robot_demos: RobotDemos = None
# camera_streamer 的初始化调整：不再在 lifespan 中立即尝试打开摄像头
# 而是在 camera_streamer 实例创建后，将 open/start_camera_capture 延迟到 API 调用
camera_streamer: CameraStreamer = None


# --- 应用生命周期管理 (修改这里，不再在启动时尝试打开摄像头) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=auto_network_mode, daemon=True).start()

    global motor_controller, command_executor, voice_parser, robot_demos, camera_streamer
    logger.info("应用启动中...")
    try:
        motor_controller = MotorControl()
        command_executor = CommandExecutor(motor_controller, logger)
        voice_parser = VoiceCommandParser()
        robot_demos = RobotDemos(command_executor, logger)
        # command_executor.start_threads()
        #
        # # CameraStreamer 实例在这里创建，但摄像头本身不会立即打开
        # camera_streamer = CameraStreamer(CAMERA_INDEX, CAMERA_FPS, CAMERA_RESOLUTION, logger)
        #
        # logger.info("电机控制、命令执行模块、演示模块和摄像头流媒体实例初始化成功。")
        # yield  # <-- yield 之前的代码是启动逻辑
        # 启动后台异步任务
        await command_executor.start_tasks()

        camera_streamer = CameraStreamer(CAMERA_INDEX, CAMERA_FPS, CAMERA_RESOLUTION, logger)

        app.include_router(setup_router)
        yield
    except Exception as e:
        logger.error(f"应用启动失败: {e}", exc_info=True)
        logger.critical("应用程序核心服务初始化失败，正在退出！", exc_info=True)
        sys.exit(1)  # 强制退出应用
    finally:
        # logger.info("应用关闭中...")
        # command_executor.stop_threads()
        # # 确保在应用关闭时，如果摄像头处于活动状态，也能被正确释放
        # if camera_streamer:
        #     camera_streamer.stop_camera_capture()
        # logger.info("应用已关闭。")
        logger.info("应用关闭中...")
        await command_executor.stop_tasks()  # 异步停止
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


# --- 摄像头 API 路由 (修改这里) ---
@app.post("/camera/start")  # 这个路由只负责“启动”摄像头服务
async def start_camera_api():
    """启动摄像头后台服务"""
    if not camera_streamer:
        raise HTTPException(status_code=503, detail="Service not initialized")

        # 尝试启动
    if camera_streamer.start_camera_capture():
        return {"status": "success", "message": "Camera started"}
    else:
        # 如果启动失败（例如硬件被占用），返回 500
        raise HTTPException(status_code=500, detail="Failed to open camera hardware")


@app.get("/video_feed")  # 获取视频流
async def video_feed():
    """获取视频流数据"""
    if camera_streamer and camera_streamer.is_streaming_active():
        # 返回 StreamingResponse，使用 multipart/x-mixed-replace 格式
        return StreamingResponse(
            camera_streamer.generate_frames(),
            media_type="multipart/x-mixed-replace; boundary=frame"
        )
    else:
        # 如果摄像头没开，返回 404 或 400，前端会显示占位图
        # 这里返回 204 No Content 或者 404 比较合适，让前端知道没图
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
    # logger.info("ASR WebSocket 连接建立")
    # try:
    #     while True:
    #         data = await websocket.receive_text()
    #         logger.info(f"ASR WebSocket: 收到语音文本: {data}")
    #         parsed_command = voice_parser.parse(data)
    #         if parsed_command:
    #             command_executor.add_command(parsed_command)
    #             await websocket.send_text(f"已接收命令: {parsed_command}")
    #             logger.info(f"ASR WebSocket: 已接收命令: {parsed_command}")
    #         else:
    #             await websocket.send_text("未识别出有效命令")
    #             logger.info("ASR WebSocket: 未识别出有效命令")
    # except Exception as e:
    #     logger.error(f"ASR WebSocket 错误: {e}")
    # finally:
    #     logger.info("ASR WebSocket 连接关闭")
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            cmd = voice_parser.parse(data)
            if cmd:
                await command_executor.add_command(cmd)  # await add_command
                await websocket.send_text(f"执行: {cmd}")
            else:
                await websocket.send_text("未知命令")
    except Exception:
        pass


@app.post("/control")
async def control(command: ControlCommand):
    # logger.info(f"API: 收到控制命令: {command.direction}")
    # command_executor.add_command(command.direction)
    # return JSONResponse({"status": "ok", "received_command": command.direction})
    await command_executor.add_command(command.direction)  # await
    return {"status": "ok", "cmd": command.direction}


@app.post("/cmd")
async def cmd(voice_text: VoiceText):
    # logger.info(f"API: 收到文本命令: {voice_text.text}")
    # parsed_command = voice_parser.parse(voice_text.text)
    # if parsed_command:
    #     command_executor.add_command(parsed_command)
    #     logger.info(f"API: 已解析并添加命令: {parsed_command}")
    #     return JSONResponse({"status": "ok", "parsed_command": parsed_command})
    # logger.info("API: 未能解析出有效命令。")
    # return JSONResponse({"status": "no_command_parsed", "message": "未能解析出有效命令"})
    cmd = voice_parser.parse(voice_text.text)
    if cmd:
        await command_executor.add_command(cmd)  # await
        return {"status": "ok", "cmd": cmd}
    return {"status": "fail"}


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    logger.info("API: 收到根路径请求，返回 index.html。")
    return templates.TemplateResponse("index.html", {"request": request})


# --- 演示功能 API (保持不变) ---
@app.post("/demo/start")
async def start_demo(command: DemoCommand):
    # if robot_demos:
    #     if robot_demos.start_demo(command.demo_name):
    #         return {"status": "success", "message": f"Demo '{command.demo_name}' started."}
    #     else:
    #         raise HTTPException(status_code=409,
    #                             detail=f"Failed to start demo '{command.demo_name}'. Another demo might be running or demo not found.")
    # else:
    #     raise HTTPException(status_code=503, detail="Robot demos module not initialized.")
    # await start_demo
    if await robot_demos.start_demo(command.demo_name):
        return {"status": "success"}
    raise HTTPException(409, "Demo failed to start")


@app.post("/demo/stop")
async def stop_demo():
    # if robot_demos:
    #     if robot_demos.stop_demo():
    #         return {"status": "success", "message": "Demo stopped."}
    #     else:
    #         return {"status": "info", "message": "No demo was running."}
    # else:
    #     raise HTTPException(status_code=503, detail="Robot demos module not initialized.")
    # await stop_demo
    if await robot_demos.stop_demo():
        return {"status": "success"}
    return {"status": "info", "msg": "No demo running"}


@app.get("/health")
async def health():
    logger.info("API: 健康检查请求。")
    return JSONResponse({"status": "alive"})


if __name__ == '__main__':
    logger.info(f"启动 Uvicorn 服务器在 {APP_HOST}:{APP_PORT}")
    uvicorn.run(app, host=APP_HOST, port=APP_PORT)
