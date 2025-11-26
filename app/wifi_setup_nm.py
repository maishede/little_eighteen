# little_eighteen/app/wifi_setup_nm.py
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
import subprocess
from app.network_manager_nm import deactivate_hotspot
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/setup")
async def setup_page():
    return """
    <!DOCTYPE html>
    <html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Little18 配网</title>
    <style>
        body{font-family:Arial;background:#667eea;color:white;text-align:center;padding:50px}
        .box{background:rgba(255,255,255,0.15);padding:40px;border-radius:20px;max-width:90%;margin:0 auto}
        input,button{padding:15px;margin:10px;width:80%;border:none;border-radius:10px;font-size:16px}
        button{background:white;color:#667eea;font-weight:bold}
        h1{font-size:38px}
    </style></head>
    <body>
        <div class="box">
            <h1>Little18</h1>
            <p>请配置要连接的Wi-Fi</p>
            <form action="/setup/connect" method="post">
                <input name="ssid" placeholder="WiFi名称" required>
                <input name="password" type="password" placeholder="密码（无密码可留空）">
                <button type="submit">立即连接</button>
            </form>
            <p style="margin-top:30px;font-size:14px">热点密码：88888888</p>
        </div>
    </body></html>
    """


@router.post("/setup/connect")
async def connect_wifi(ssid: str = Form(), password: str = Form("")):
    try:
        # 创建新连接
        cmd = [
            "nmcli", "device", "wifi", "connect", ssid,
            "password", password,
            "ifname", "wlan0"
        ]
        if not password:
            cmd.remove("password")
            cmd.remove(password)

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            deactivate_hotspot()  # 关闭热点
            logger.info(f"成功连接到 {ssid}，热点已关闭")
            return HTMLResponse("""
                <h2>连接成功！</h2>
                <p>正在重连，请稍后访问你的局域网IP：192.168.31.250</p>
                <script>setTimeout(()=>location.href='/', 15000)</script>
            """)
        else:
            return HTMLResponse(f"<h2>连接失败</h2><pre>{result.stderr}</pre>")
    except Exception as e:
        logger.error(f"配网失败: {e}")
        return HTMLResponse(f"<h2>错误</h2><p>{e}</p>")