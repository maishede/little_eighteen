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
    MICROPHONE_INDEX = int(os.getenv("MICROPHONE_INDEX", 11))
    CommandExecutor = object


class RhinoVoiceService:
    def __init__(self, command_executor):
        self.logger = logging.getLogger("RhinoVoice")
        self.executor = command_executor
        self._running = False
        self._thread = None
        self.rhino = None
        self.recorder = None
        self.is_smart_mode = False

        # 【关键修复 1】: 在初始化（主线程）时捕获事件循环
        try:
            self._main_loop = asyncio.get_running_loop()
        except RuntimeError:
            self._main_loop = None
            self.logger.warning("初始化时未检测到运行的 Event Loop，可能处于调试模式")

        # 中文指令映射
        self.cmd_map = {
            '前进': 'move_forward', '向前': 'move_forward',
            '后退': 'move_back', '向后': 'move_back',
            '左转': 'turn_left', '右转': 'turn_right',
            '左移': 'move_left', '右移': 'move_right',
            '停止': 'stop', '停': 'stop',
            '左前': 'move_left_forward', '右前': 'move_right_forward',
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
                        self.logger.info(f"✅ 语音识别: 意图=[{intent}] 参数={slots}")
                        self._handle_intent(intent, slots)
            except Exception as e:
                if self._running:
                    self.logger.error(f"监听循环异常: {e}")

    def _handle_intent(self, intent, slots):
        cmd_to_send = None
        action = slots.get('action')

        # 模式切换
        if intent == 'system_control' or action in ['智能模式', '普通模式']:
            if action == '智能模式':
                self.is_smart_mode = True
                self.logger.info(">>> 🔄 切换到：智能模式")
            elif action == '普通模式':
                self.is_smart_mode = False
                self.logger.info(">>> 🔄 切换到：离线指令模式")
            return

        if self.is_smart_mode:
            return

        # 运动控制
        if intent == 'car_control':
            if action in self.cmd_map:
                cmd_to_send = self.cmd_map[action]
            else:
                self.logger.warning(f"⚠️ 未知动作: {action}")

        # 【关键修复 2】: 使用保存的 _main_loop 发送，并打印具体错误
        if cmd_to_send:
            self.logger.info(f"🚀 [执行映射] '{action}' -> '{cmd_to_send}'")

            if self._main_loop and self._main_loop.is_running():
                try:
                    asyncio.run_coroutine_threadsafe(
                        self.executor.add_command(cmd_to_send),
                        self._main_loop
                    )
                    # 注意：这里成功放入队列不代表立即执行，但至少不会报错了
                except Exception as e:
                    self.logger.error(f"❌ 指令发送失败: {e}")
            else:
                self.logger.error("❌ 严重错误: 主线程 Event Loop 未运行或丢失，无法发送指令！")


# ==========================================
#               调试入口
# ==========================================
if __name__ == "__main__":
    import time

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


    class MockCommandExecutor:
        async def add_command(self, command: str):
            print(f"\n⚡⚡⚡ [后台执行器收到指令]: {command} ⚡⚡⚡\n")


    # 手动创建 Loop 供调试使用
    loop = asyncio.new_event_loop()
    threading.Thread(target=lambda: (asyncio.set_event_loop(loop), loop.run_forever()), daemon=True).start()


    # 模拟在 Async 上下文中初始化
    async def init_debug():
        print("启动服务...")
        service = RhinoVoiceService(MockCommandExecutor())
        service.start()
        return service


    future = asyncio.run_coroutine_threadsafe(init_debug(), loop)
    service = future.result()

    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        service.stop()