# little_eighteen/app/network_manager_nm.py
import subprocess
import time
import threading
import logging

HOTSPOT_NAME = "Little18-Hotspot"
NORMAL_WIFI = "preconfigured"  # 你的连接名，就是 preconfigured.nmconnection 的 id
logger = logging.getLogger(__name__)

# 导入配置
from app.config import NETWORK_WAIT_SECONDS

def is_internet_reachable():
    """检测是否能访问外网"""
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "3", "8.8.8.8"],
            capture_output=True, text=True
        )
        return result.returncode == 0
    except:
        return False

def activate_hotspot():
    """激活热点"""
    logger.info("未检测到外网，激活配网热点：Little18-Setup")
    subprocess.run(["nmcli", "connection", "up", HOTSPOT_NAME], check=False)

def deactivate_hotspot():
    """关闭热点"""
    subprocess.run(["nmcli", "connection", "down", HOTSPOT_NAME], check=False)

def auto_network_mode():
    """开机后自动判断网络模式"""
    time.sleep(NETWORK_WAIT_SECONDS)  # 使用配置的等待时间

    if is_internet_reachable():
        logger.info("已连接外网，保持正常模式")
        deactivate_hotspot()
    else:
        logger.warning("无法访问外网，启动配网热点模式")
        activate_hotspot()

# 导出函数供 main.py 调用
def start_network_watcher():
    thread = threading.Thread(target=auto_network_mode, daemon=True)
    thread.start()