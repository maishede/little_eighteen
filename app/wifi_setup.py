# little_eighteen/app/wifi_setup.py
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
import subprocess
from app.network_manager import stop_softap
import time

router = APIRouter(prefix="/setup")


@router.get("/", response_class=HTMLResponse)
async def setup_page(request: Request):
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Little18 配网</title>
        <style>
            body{font-family:Arial;background:linear-gradient(135deg,#667eea,#764ba2);color:white;text-align:center;padding:50px}
            .box{background:rgba(255,255,255,0.1);padding:30px;border-radius:20px;max-width:400px;margin:0 auto;box-shadow:0 10px 30px rgba(0,0,0,0.3)}
            input,button{padding:15px;margin:10px;width:90%;border:none;border-radius:10px;font-size:16px}
            button{background:#fff;color:#667eea;font-weight:bold}
            h1{font-size:36px;margin-bottom:30px}
        </style>
    </head>
    <body>
        <div class="box">
            <h1>Little18</h1>
            <p>请配置要连接的Wi-Fi</p>
            <form action="/setup/connect" method="post">
                <input name="ssid" placeholder="WiFi名称" required>
                <input name="password" type="password" placeholder="WiFi密码（可留空）">
                <button type="submit">连接</button>
            </form>
            <p style="margin-top:30px;font-size:12px;">密码：88888888</p>
        </div>
    </body>
    </html>
    """


@router.post("/connect")
async def connect_wifi(ssid: str = Form(), password: str = Form("")):
    config = f'''
network={{
    ssid="{ssid}"
    psk="{password}"
    key_mgmt=WPA-PSK
}}
'''
    try:
        with open("/etc/wpa_supplicant/wpa_supplicant.conf", "a") as f:
            f.write(config)

        subprocess.run(["sudo", "wpa_cli", "-i", "wlan0", "reconfigure"], check=False)

        stop_softap()  # 关闭热点

        return HTMLResponse("""
        <h2>正在连接 Wi-Fi...</h2>
        <p>成功后将自动重启服务（约30秒）</p>
        <script>
            setTimeout(() => location.href = '/', 30000);
        </script>
        """)
    except Exception as e:
        return HTMLResponse(f"<h2>保存失败：{e}</h2>")