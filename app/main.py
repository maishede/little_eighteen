import sys
from pathlib import Path

# 获取当前脚本所在的目录，并向上一级找到项目的根目录
project_root = str(Path(__file__).resolve().parents[1])
sys.path.append(project_root)

from fastapi import FastAPI, Request, UploadFile, File, WebSocket
from fastapi.responses import JSONResponse
from services.asr import ws_asr_server
import uvicorn
from app.utils.regex_commend import CommandHandler
import threading

app = FastAPI()
handle = CommandHandler()


@app.websocket("/asr")
async def asr(websocket: WebSocket):
    print("get websocket")
    await ws_asr_server(websocket)


@app.get("/health")
async def health():
    return JSONResponse({"status": "alive"})


@app.post("/cmd")
async def cmd(request: Request):
    data = await request.json()
    text = data.get("text")
    print(text)
    handle.handle_text(text)
    return JSONResponse({})


if __name__ == '__main__':
    executor_thread = threading.Thread(target=handle.execute_commands)
    executor_thread.start()

    uvicorn.run(app, host="0.0.0.0", port=8000)
