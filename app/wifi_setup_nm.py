# little_eighteen/app/wifi_setup_nm.py  （终极户外无网直控版）
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
import subprocess
from app.network_manager_nm import deactivate_hotspot
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/setup")

# 1. 手动访问 /setup 才显示配网页面
@router.get("/")
async def setup_page():
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <title>Little18 配网</title>
        <style>
            body{font-family:Arial;background:linear-gradient(135deg,#667eea,#764ba2);color:white;text-align:center;padding:50px}
            .box{background:rgba(255,255,255,0.15);padding:40px;border-radius:20px;max-width:90%;margin:auto;box-shadow:0 10px 30px rgba(0,0,0,0.3);backdrop-filter:blur(10px)}
            input,button{padding:16px;margin:12px;width:85%;border:none;border-radius:12px;font-size:17px}
            button{background:white;color:#667eea;font-weight:bold}
            a{color:#fff;text-decoration:underline;margin-top:30px;display:block}
        </style>
    </head>
    <body>
        <div class="box">
            <h1>Little18 配网</h1>
            <p>请配置要连接的Wi-Fi</p>
            <form action="/setup/connect" method="post">
                <input name="ssid" placeholder="WiFi名称" required>
                <input name="password" type="password" placeholder="密码（可留空）">
                <button type="submit">立即连接</button>
            </form>
            <br>
            <a href="/">直接控制小车（无网模式）</a>
        </div>
    </body>
    </html>
    """)

# 2. 配网逻辑不变
@router.post("/connect")
async def connect_wifi(ssid: str = Form(), password: str = Form("")):
    try:
        cmd = ["nmcli", "device", "wifi", "connect", ssid]
        if password:
            cmd += ["password", password]
        cmd += ["ifname", "wlan0"]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            deactivate_hotspot()
            return HTMLResponse("""
                <h2>连接成功！热点即将关闭</h2>
                <p>请连接新Wi-Fi，访问原IP控制</p>
                <script>setTimeout(() => location.href='/', 15000)</script>
            """)
        else:
            return HTMLResponse(f"<h2>连接失败</h2><pre>{result.stderr}</pre><br><a href='/setup'>返回</a>")
    except Exception as e:
        return HTMLResponse(f"<h2>错误</h2><p>{e}</p><br><a href='/setup'>返回</a>")