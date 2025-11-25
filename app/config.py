# -*- coding: utf-8 -*-
import os

# GPIO 引脚配置 (使用您原有值)
GPIO_IN1 = 18
GPIO_IN2 = 23
GPIO_IN3 = 24
GPIO_IN4 = 25
GPIO_IN5 = 12
GPIO_IN6 = 16
GPIO_IN7 = 20
GPIO_IN8 = 21

# IN1 = 20
IN1 = GPIO_IN1
# IN2 = 21
IN2 = GPIO_IN2
# IN3 = 12
IN3 = GPIO_IN3
# IN4 = 16
IN4 = GPIO_IN4
# IN5 = 18
IN5 = GPIO_IN5
# IN6 = 23
IN6 = GPIO_IN6
# IN7 = 24
IN7 = GPIO_IN7
# IN8 = 25
IN8 = GPIO_IN8

EN1 = 6
EN2 = 13
EN3 = 19
EN4 = 26

HC_SR_04_TRIG = 4
HC_SR_04_ECHO = 17

# HC-SR04 传感器配置
DEFAULT_TEMPERATURE = 20  # 默认温度为20度
DISTANCE_BUFFER_SIZE = 5  # 缓冲区大小
DISTANCE_DETECTION_THRESHOLD = 20  # 距离小于此值时停车
HC_SR_04_TIMEOUT = 0.03  # HC-SR04 超时时间，单位秒
DISTANCE_MONITOR_INTERVAL = 0.1  # 距离检测间隔

# 运动模式常量
MODE_FORWARD = 1
MODE_BACK = 2
MODE_STOP = 3

# 摄像头配置
CAMERA_INDEX = 0  # 摄像头设备索引，通常为0
CAMERA_FPS = 30  # 摄像头帧率
CAMERA_RESOLUTION = (640, 480)  # 摄像头分辨率
# CAMERA_RESOLUTION = (320, 240)  # 摄像头分辨率

# WebSocket ASR 服务地址 (如果使用外部服务)
ASR_SERVER_URL = os.getenv("ASR_SERVER_URL", "ws://localhost:8001/ws")  # 示例，按需修改

# FastAPI 应用配置
APP_HOST = "0.0.0.0"
APP_PORT = 8000

# 命令执行间隔 (如果需要限制命令执行速度)
COMMAND_EXECUTION_INTERVAL = 0.05

# --- 日志配置 (新增) ---
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs')
LOG_FILE_NAME = 'robot_app.log'
LOG_MAX_BYTES = 50 * 1024 * 1024  # 50 MB
LOG_BACKUP_COUNT = 5  # 保留 5 份历史日志
LOG_LEVEL = 'INFO'  # 日志级别，可以是 DEBUG, INFO, WARNING, ERROR, CRITICAL
