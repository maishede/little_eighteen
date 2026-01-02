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

# ================= 语音控制配置 =================
PICOVOICE_ACCESS_KEY = os.getenv("PICOVOICE_ACCESS_KEY", "")
RHINO_CONTEXT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'models',
                                  'little_18_zh_raspberry-pi_v4_0_0.rhn')
RHINO_MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'models', 'rhino_params_zh.pv')
# 麦克风设备索引，如果插了USB麦克风通常是 1 或 2，-1 表示默认
MICROPHONE_INDEX = int(os.getenv("MICROPHONE_INDEX", -1))

# ================= 语音识别优化参数 =================
# Rhino 灵敏度 (0.0 - 1.0)，越高越敏感但更容易误触发
RHINO_SENSITIVITY = float(os.getenv("RHINO_SENSITIVITY", 0.5))
# 说话结束检测时间（秒），越短响应越快但可能中断说话
RHINO_ENDPOINT_DURATION = float(os.getenv("RHINO_ENDPOINT_DURATION", 0.5))
# 是否需要检测到明确的说话结束（True 延迟更高但更准确）
RHINO_REQUIRE_ENDPOINT = os.getenv("RHINO_REQUIRE_ENDPOINT", "true").lower() == "true"

# ================= VAD（语音活动检测）配置 =================
# 是否启用 VAD 进行人声检测
VAD_ENABLED = os.getenv("VAD_ENABLED", "true").lower() == "true"
# VAD 敏感度 (0-3)，0 最敏感（容易误触发），3 最不敏感（需要大声说话）
VAD_AGGRESSIVENESS = int(os.getenv("VAD_AGGRESSIVENESS", 2))
# VAD 帧长度（毫秒），支持 10, 20, 30
VAD_FRAME_DURATION = int(os.getenv("VAD_FRAME_DURATION", 30))
# 最小语音长度（毫秒），短于此长度认为是噪音
VAD_MIN_SPEECH_DURATION = int(os.getenv("VAD_MIN_SPEECH_DURATION", 300))
# 最小静音长度（毫秒），检测到静音多久后认为说话结束
VAD_MIN_SILENCE_DURATION = int(os.getenv("VAD_MIN_SILENCE_DURATION", 500))

# ================= 语音诊断配置 =================
VOICE_DIAGNOSTICS_ENABLED = os.getenv("VOICE_DIAGNOSTICS_ENABLED", "false").lower() == "true"
# 噪音阈值（分贝），高于此值认为是噪音环境
NOISE_THRESHOLD_DB = float(os.getenv("NOISE_THRESHOLD_DB", 50.0))

# ================= 网络配置 =================
NETWORK_WAIT_SECONDS = int(os.getenv("NETWORK_WAIT_SECONDS", "15"))
