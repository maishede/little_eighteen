# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv

# 加载 .env 文件
# override=True 表示如果系统环境变量里有同名变量，优先使用 .env 里的
load_dotenv(override=True)

# ================= GPIO 配置 =================
# 方向引脚
IN1 = int(os.getenv("GPIO_IN1", 18))
IN2 = int(os.getenv("GPIO_IN2", 23))
IN3 = int(os.getenv("GPIO_IN3", 24))
IN4 = int(os.getenv("GPIO_IN4", 25))
IN5 = int(os.getenv("GPIO_IN5", 12))
IN6 = int(os.getenv("GPIO_IN6", 16))
IN7 = int(os.getenv("GPIO_IN7", 20))
IN8 = int(os.getenv("GPIO_IN8", 21))

# PWM 调速引脚 (EN)
EN1 = int(os.getenv("GPIO_EN1", 6))
EN2 = int(os.getenv("GPIO_EN2", 13))
EN3 = int(os.getenv("GPIO_EN3", 19))
EN4 = int(os.getenv("GPIO_EN4", 26))

# 超声波传感器
HC_SR_04_TRIG = int(os.getenv("HC_SR04_TRIG", 4))
HC_SR_04_ECHO = int(os.getenv("HC_SR04_ECHO", 17))

# ================= 运动与传感器参数 =================
DEFAULT_TEMPERATURE = 20
DISTANCE_BUFFER_SIZE = 5
HC_SR_04_TIMEOUT = 0.03
DISTANCE_MONITOR_INTERVAL = 0.1

# 距离检测阈值 (旧逻辑保留，新逻辑用下面的动态参数)
DISTANCE_DETECTION_THRESHOLD = 20

# PWM 配置
PWM_FREQ = int(os.getenv("PWM_FREQ", 100))
DEFAULT_SPEED = int(os.getenv("DEFAULT_SPEED", 50))
MIN_SPEED_LIMIT = int(os.getenv("MIN_SPEED_LIMIT", 20))

# 动态避障参数
OBSTACLE_BASE_DISTANCE = int(os.getenv("OBSTACLE_BASE_DISTANCE", 10))
OBSTACLE_SPEED_FACTOR = float(os.getenv("OBSTACLE_SPEED_FACTOR", 0.4))

# 电机微调校准 (0.0 - 1.0)
CORRECTION_LF = float(os.getenv("CORRECTION_LF", 1.0))
CORRECTION_LB = float(os.getenv("CORRECTION_LB", 1.0))
CORRECTION_RF = float(os.getenv("CORRECTION_RF", 1.0))
CORRECTION_RB = float(os.getenv("CORRECTION_RB", 1.0))

# 运动模式常量
MODE_FORWARD = 1
MODE_BACK = 2
MODE_STOP = 3

# ================= 摄像头配置 =================
CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", 0))
CAMERA_FPS = int(os.getenv("CAMERA_FPS", 30))
CAMERA_RESOLUTION = (
    int(os.getenv("CAMERA_WIDTH", 640)),
    int(os.getenv("CAMERA_HEIGHT", 480))
)

# ================= Web 服务配置 =================
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", 8000))

# WebSocket ASR (旧版保留)
ASR_SERVER_URL = os.getenv("ASR_SERVER_URL", "ws://localhost:8001/ws")

# 命令执行间隔
COMMAND_EXECUTION_INTERVAL = 0.05

# ================= 日志配置 =================
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs')
LOG_FILE_NAME = 'robot_app.log'
LOG_MAX_BYTES = 50 * 1024 * 1024
LOG_BACKUP_COUNT = 5
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ================= 🤖 LLM 智能体配置 =================
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "gpt-3.5-turbo")
