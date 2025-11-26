# little_eighteen/app/network_manager.py
import subprocess
import time
import os
from pathlib import Path

AP_SSID = "Little18-Setup"
AP_PASSWORD = "88888888"


def is_connected_to_internet(timeout: int = 8):
    """检测是否能访问外网"""
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", str(timeout), "8.8.8.8"],
            capture_output=True
        )
        return result.returncode == 0
    except:
        return False


def start_softap():
    """启动热点"""
    print("未检测到外网连接，启动配网热点：Little18-Setup")
    subprocess.run(["sudo", "ip", "addr", "flush", "dev", "wlan0"], check=False)
    subprocess.run(["sudo", "systemctl", "start", "hostapd"], check=False)
    subprocess.run(["sudo", "systemctl", "start", "dnsmasq"], check=False)


def stop_softap():
    """关闭热点"""
    subprocess.run(["sudo", "systemctl", "stop", "hostapd"], check=False)
    subprocess.run(["sudo", "systemctl", "stop", "dnsmasq"], check=False)
    subprocess.run(["sudo", "ip", "addr", "flush", "dev", "wlan0"], check=False)


def auto_network_mode():
    """开机自动判断网络模式"""
    time.sleep(12)  # 等待系统尝试连接Wi-Fi

    if is_connected_to_internet():
        print("已连接网络，进入正常模式")
        stop_softap()
    else:
        print("未连接网络，进入配网模式")
        start_softap()