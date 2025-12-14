import threading
import pvrhino
import logging
import asyncio
import os
import sys
from pathlib import Path
from pvrecorder import PvRecorder

# === 路径与配置加载 ===
current_file_path = Path(__file__).resolve()
project_root = current_file_path.parent.parent.parent

try:
    from app.config import PICOVOICE_ACCESS_KEY, RHINO_CONTEXT_PATH, RHINO_MODEL_PATH, MICROPHONE_INDEX
    from app.utils.regex_command import CommandExecutor
except ImportError:
    # 调试 Fallback
    import os

    PICOVOICE_ACCESS_KEY = os.getenv("PICOVOICE_ACCESS_KEY", "")
    RHINO_CONTEXT_PATH = str(project_root / 'models' / 'little_18_zh_raspberry-pi_v4_0_0.rhn')
    RHINO_MODEL_PATH = str(project_root / 'models' / 'rhino_params_zh.pv')
    MICROPHONE_INDEX = int(os.getenv("MICROPHONE_INDEX", 11))  # 默认为你测出的 11
    CommandExecutor = object


class RhinoVoiceService:
    def __init__(self, command_executor):
        print(f"DEBUG: RhinoVoiceService 正在初始化... MIC_INDEX={MICROPHONE_INDEX}")
        self.logger = logging.getLogger("RhinoVoice")
        self.executor = command_executor
        self._running = False
        self._thread = None
        self.rhino = None
        self.recorder = None
        self.is_smart_mode = False

        # 1. 定义中文指令映射表 (关键修改)
        # 格式: { '语音动作': 'CommandExecutor指令' }
        self.cmd_map = {
            '前进': 'move_forward',
            '向前': 'move_forward',
            '后退': 'move_back',
            '向后': 'move_back',
            '左转': 'turn_left',
            '右转': 'turn_right',
            '左移': 'move_left',
            '右移': 'move_right',
            '停止': 'stop',
            '停': 'stop',
            # 如果模型里有斜向移动，也可以加在这里
            '左前': 'move_left_forward',
            '右前': 'move_right_forward',
        }

        if not PICOVOICE_ACCESS_KEY:
            self.logger.error("未配置 PICOVOICE_ACCESS_KEY")
            return

        try:
            self.rhino = pvrhino.create(
                access_key=PICOVOICE_ACCESS_KEY,
                context_path=RHINO_CONTEXT_PATH,
                model_path=RHINO_MODEL_PATH,
                sensitivity=0.5,
                endpoint_duration_sec=1.0,
                require_endpoint=True
            )
            self.logger.info(f"Rhino 初始化成功")
        except Exception as e:
            self.logger.error(f"Rhino 初始化失败: {e}")

    def start(self):
        if not self.rhino: return
        if self._running: return

        self._running = True
        try:
            self.recorder = PvRecorder(
                device_index=MICROPHONE_INDEX,
                frame_length=self.rhino.frame_length
            )
            self.recorder.start()

            self._thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._thread.start()
            self.logger.info(f"Rhino 监听启动 (Device Index: {self.recorder.selected_device})")
        except Exception as e:
            self.logger.error(f"录音设备启动失败: {e}")
            self._running = False

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

        if self.recorder:
            self.recorder.stop()
            self.recorder.delete()
        if self.rhino:
            self.rhino.delete()
        self.logger.info("Rhino 服务已停止")

    def _listen_loop(self):
        while self._running:
            try:
                pcm = self.recorder.read()
                is_finalized = self.rhino.process(pcm)

                if is_finalized:
                    inference = self.rhino.get_inference()
                    if inference.is_understood:
                        intent = inference.intent
                        slots = inference.slots
                        # 打印原始识别结果
                        self.logger.info(f"✅ 语音识别: 意图=[{intent}] 参数={slots}")
                        self._handle_intent(intent, slots)
                    else:
                        # 没听懂 (可选：打印一下方便调试)
                        # self.logger.debug("未能理解指令")
                        pass
            except Exception as e:
                if self._running:
                    self.logger.error(f"监听循环异常: {e}")

    def _handle_intent(self, intent, slots):
        """核心逻辑：将中文意图映射为代码指令"""
        cmd_to_send = None
        action = slots.get('action')  # 获取动作槽位

        # ----------------------------------------------------
        # 1. 处理系统控制 / 模式切换 (假设你的模型有这个意图)
        # ----------------------------------------------------
        if intent == 'system_control' or action in ['智能模式', '普通模式']:
            if action == '智能模式':
                self.is_smart_mode = True
                self.logger.info(">>> 🔄 切换到：智能模式 (等待云端接入)")
                # 这里可以加一行语音播报
            elif action == '普通模式':
                self.is_smart_mode = False
                self.logger.info(">>> 🔄 切换到：离线指令模式")
            return

        # 如果是智能模式，暂不处理离线运动指令
        if self.is_smart_mode:
            self.logger.info(f"忽略本地指令 '{action}' (当前处于智能模式)")
            return

        # ----------------------------------------------------
        # 2. 处理运动控制 (基于你的日志 car_control)
        # ----------------------------------------------------
        if intent == 'car_control':
            if action in self.cmd_map:
                cmd_to_send = self.cmd_map[action]
            else:
                self.logger.warning(f"⚠️ 未知动作: {action}，请在 cmd_map 中添加映射")

        # ----------------------------------------------------
        # 3. 发送指令给执行器
        # ----------------------------------------------------
        if cmd_to_send:
            self.logger.info(f"🚀 [执行映射] '{action}' -> '{cmd_to_send}'")
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 这里真正触发电机
                    asyncio.run_coroutine_threadsafe(
                        self.executor.add_command(cmd_to_send),
                        loop
                    )
                else:
                    self.logger.warning("Event loop 未运行，无法发送指令")
            except RuntimeError:
                pass


# ==========================================
#               调试入口
# ==========================================
if __name__ == "__main__":
    import time

    # 设置日志格式
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


    # 模拟 CommandExecutor (为了看日志)
    class MockCommandExecutor:
        async def add_command(self, command: str):
            # 这行日志证明集成成功！
            print(f"\n⚡⚡⚡ [后台执行器收到指令]: {command} ⚡⚡⚡\n")


    # 启动 Loop
    loop = asyncio.new_event_loop()
    threading.Thread(target=lambda: (asyncio.set_event_loop(loop), loop.run_forever()), daemon=True).start()

    print("启动服务...")
    service = RhinoVoiceService(MockCommandExecutor())
    service.start()

    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        service.stop()