# -*- coding: utf-8 -*-
import json
import asyncio
import traceback

import websockets

ASR_CHUNK_SIZE = "5, 10, 5"
MODE = "2pass"  # offline, online, 2pass
CHUNK_INTERVAL = 10


async def ws_asr_server(websocket_recv):
    """
    转发websocket到asr服务器
    @websocket_recv: 来自用户的websocket
    @websocket_send: 发送给asr服务端的websocket
    """
    async with websockets.connect("ws://192.168.31.157:10096", subprotocols=["binary"], ping_interval=None,
                                  ssl=None) as websocket_send:
        # 发送websocket到asr服务器
        task1 = asyncio.create_task(send_websocket(websocket_recv=websocket_recv, websocket_send=websocket_send))
        # 获取asr服务器返回报文返回给用户
        task2 = asyncio.create_task(recv_websocket(websocket_recv=websocket_recv, websocket_send=websocket_send))
        await asyncio.gather(task1, task2)


async def send_websocket(websocket_recv, websocket_send):
    """
    向asr模型转发用户语音
    @websocket_recv: 用户输入的websocket
    @websocket_send: 发送给asr模型的websocket
    """
    CHUNK_SIZE = [int(i) for i in ASR_CHUNK_SIZE.split(',')]
    # 等待用户输入
    await websocket_recv.accept()
    # 向asr服务端发送初始化信息
    message = json.dumps({"mode": MODE, "chunk_size": CHUNK_SIZE, "chunk_interval": CHUNK_INTERVAL,
                          "wav_name": "microphone", "is_speaking": True, "hotwords": "", "itn": False})
    await websocket_send.send(message)
    try:
        while True:
            # 接收用户字节流信息
            data = await websocket_recv.receive_bytes()
            print(data)
            # 将用户字节流发送给asr服务端
            await websocket_send.send(data)
            # 和前端约定以\n\n作为用户断开标识
            if data.endswith(b"\n\n"):
                message = json.dumps({"is_speaking": False})
                await websocket_send.send(message)
                break
            await asyncio.sleep(0.005)
    except:
        print(traceback.format_exc())


async def recv_websocket(websocket_recv, websocket_send):
    """
    从asr模型获取返回结果
    @websocket_recv: 用户输入的websocket
    @websocket_send: 发送给asr模型的websocket
    """
    online_cache = ""
    try:
        while True:
            # 等待asr服务端返回
            response = await websocket_send.recv()
            response_json = json.loads(response)
            text = response_json.get("text")
            # print(response_json)
            # print(text)
            is_finished = response_json.get("is_final", False)
            mode = response_json.get("mode", None)
            # 只返回2paass-online模式的文本
            if mode and mode == "2pass-online":
                res = {
                    "code": 200,
                    "message": "success",
                    "type": "websocket.send",
                    "data": {"id": 0, "result": text, "is_finished": is_finished},
                    "mode": mode
                }
                online_cache = text
                print(online_cache)
                await websocket_recv.send_json(res)
            # logger.info(f"send user: {json.dumps(res, ensure_ascii=False)}")
            if mode and mode == "2pass-offline":
                if text:
                    last_word = text[-1]
                    if not online_cache.endswith(last_word):
                        res = {
                            "code": 200,
                            "message": "success",
                            "type": "websocket.send",
                            "data": {"id": 0, "result": last_word, "is_finished": is_finished},
                            "mode": mode
                        }
                        print(last_word)
                        await websocket_recv.send_json(res)
            # 当asr服务端终止服务时,向用户发送终止信息
            if is_finished:
                res = {
                    "code": 200,
                    "message": "success",
                    "type": "websocket.send",
                    "data": {"id": 0, "result": "", "is_finished": is_finished},
                    "mode": mode
                }
                await websocket_recv.send_json(res)
                await asyncio.sleep(2)
                # await websocket_recv.close()
                break
    except:
        print(traceback.format_exc())
