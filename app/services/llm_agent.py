# app/services/llm_agent.py
import json
import logging
# 这里推荐使用 OpenAI 格式的 SDK，兼容 DeepSeek, 通义千问等
from openai import OpenAI
from app.services.core import MotorControl

logger = logging.getLogger("llm_agent")


class SmartCarAgent:
    def __init__(self, motor: MotorControl, api_key: str, base_url: str, model_name: str = "gpt-3.5-turbo"):
        self.motor = motor
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name

        # 1. 定义小车的技能 (Function Calling 工具集)
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "move",
                    "description": "控制小车移动",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "direction": {
                                "type": "string",
                                "enum": ["forward", "back", "left", "right", "turn_left", "turn_right"],
                                "description": "移动方向"
                            },
                            "speed": {
                                "type": "integer",
                                "description": "速度百分比 (0-100)，默认50"
                            },
                            "duration": {
                                "type": "number",
                                "description": "持续时间(秒)，默认1秒"
                            }
                        },
                        "required": ["direction"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "stop",
                    "description": "紧急停车"
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_status",
                    "description": "获取传感器状态(距离等)"
                }
            }
        ]

    async def process_command(self, user_text: str):
        """处理用户自然语言指令"""
        logger.info(f"LLM 思考中: {user_text}")

        messages = [
            {"role": "system", "content": "你是一个智能小车助手。请根据用户的模糊指令调用工具控制小车。如果用户只是聊天，请直接回复。"},
            {"role": "user", "content": user_text}
        ]

        try:
            # 2. 请求大模型
            response = self.client.chat.completions.create(
                model=self.model_name,  # 使用配置的模型名称
                messages=messages,
                tools=self.tools,
                tool_choice="auto"
            )

            resp_msg = response.choices[0].message

            # 3. 检查是否有工具调用
            if resp_msg.tool_calls:
                for tool_call in resp_msg.tool_calls:
                    func_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)

                    logger.info(f"LLM 决定执行: {func_name} 参数: {args}")

                    # 4. 映射到 core.py 的动作
                    result = "执行成功"
                    if func_name == "move":
                        direction = args.get("direction")
                        speed = args.get("speed", 50)
                        # 这里需要配合 CommandExecutor 使用，或者直接操控 motor
                        # 为了演示简单，直接用 motor (实际应放入 executor 队列)
                        self.motor.set_speed(speed)

                        method = getattr(self.motor, f"move_{direction}", None)
                        if not method and "turn" in direction:
                            method = getattr(self.motor, direction, None)

                        if method:
                            method()  # 开始动
                            # 注意：这里需要处理持续时间，通常交给 Executor 线程处理
                            # 这里仅做演示
                            import time
                            time.sleep(args.get("duration", 1.0))
                            self.motor.stop()
                        else:
                            result = "未找到对应移动方法"

                    elif func_name == "stop":
                        self.motor.stop()

                    elif func_name == "get_status":
                        dist = self.motor.measure_distance()
                        result = f"前方障碍物距离: {dist} cm"

                    # (可选) 将执行结果反馈给 LLM 进行第二轮对话
                    # ...

                return f"已执行操作: {func_name}"

            else:
                # 只是普通聊天
                return resp_msg.content

        except Exception as e:
            logger.error(f"LLM 错误: {e}")
            return "我的大脑有点短路了..."

    def listen_cloud(self, audio_file_path):
        """调用云端 ASR"""
        with open(audio_file_path, "rb") as audio_file:
            transcript = self.client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        return transcript.text
