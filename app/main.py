import sys
import time
from pathlib import Path

# 获取当前脚本所在的目录，并向上一级找到项目的根目录
project_root = str(Path(__file__).resolve().parents[1])
sys.path.append(project_root)

from fastapi import FastAPI, Request, UploadFile, File, WebSocket
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from services.asr import ws_asr_server
import uvicorn
from app.utils.regex_commend import CommandHandler
import threading
from fastapi.staticfiles import StaticFiles

app = FastAPI()
handle = CommandHandler()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.websocket("/asr")
async def asr(websocket: WebSocket):
    print("get websocket")
    await ws_asr_server(websocket)


@app.get("/health")
async def health():
    return JSONResponse({"status": "alive"})


@app.post("/control")
async def control(request: Request):
    data = await request.json()
    direction = data.get("direction")
    print(direction)
    """
    direction: 
        forward: 向前
        back: 向后
        left: 向左
        right: 向右
        turn_left: 左转
        turn_right: 右转
    """
    if direction == "forward":
        handle.forward()
    elif direction == "back":
        handle.back()
    elif direction == "left":
        handle.left()
    elif direction == "move_left":
        handle.move_left()
    elif direction == "right":
        handle.right()
    elif direction == "move_right":
        handle.move_right()
    elif direction == "stop":
        handle.stop()
    return JSONResponse({"status": "ok"})


@app.post("/cmd")
async def cmd(request: Request):
    data = await request.json()
    text = data.get("text")
    print(text)
    handle.handle_text(text)
    return JSONResponse({})


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


if __name__ == '__main__':
    executor_thread = threading.Thread(target=handle.execute_commands)
    executor_thread.start()
    safe_running_thread = threading.Thread(target=handle.distince_monitor)
    safe_running_thread.start()
    try:
        uvicorn.run(app, host="0.0.0.0", port=8000)
    except KeyboardInterrupt:
        handle.turn_off()
        time.sleep(1)
        sys.exit()
