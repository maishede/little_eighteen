import threading
import pvrhino
import pyaudio
import struct
import logging
import asyncio
import os
import sys

# 尝试导入配置，如果失败（比如单独运行时路径不对），提供一些默认处理
try:
    from app.config import PICOVOICE_ACCESS_KEY, RHINO_CONTEXT_PATH, MICROPHONE_INDEX
    from app.utils.regex_command import CommandExecutor
except ImportError:
    # 仅用于调试时的 fallback，防止导入报错
    PICOVOICE_ACCESS_KEY = os.getenv("PICOVOICE_ACCESS_KEY", "")
    RHINO_CONTEXT_PATH = "robot_context_pi.rhn"  # 假设在当前目录
    MICROPHONE_INDEX = -1
    CommandExecutor = object


class RhinoVoiceService:
    def __init__(self, command_executor):
        self.logger = logging.getLogger("RhinoVoice")
        self.executor = command_executor
        self._running = False
        self._thread = None
        self.rhino = None
        self.pa = None
        self.stream = None
        self.is_smart_mode = False

        # 检查 Key
        if not PICOVOICE_ACCESS_KEY:
            self.logger.error("未配置 PICOVOICE_ACCESS_KEY，语音服务无法启动")
            return

        # 检查模型文件
        if not os.path.exists(RHINO_CONTEXT_PATH):
            self.logger.error(f"Rhino 模型文件未找到: {RHINO_CONTEXT_PATH}")
            return

        try:
            self.rhino = pvrhino.create(
                access_key=PICOVOICE_ACCESS_KEY,
                context_path=RHINO_CONTEXT_PATH,
                sensitivity=0.5,
                endpoint_duration_sec=1.0,
                require_endpoint=True
            )
            self.logger.info(f"Rhino 初始化成功。上下文: {self.rhino.context_info}")
        except Exception as e:
            self.logger.error(f"Rhino 初始化失败: {e}")

    def start(self):
        if not self.rhino:
            self.logger.error("Rhino 未初始化，无法启动服务")
            return
        if self._running:
            return

        self._running = True
        self.pa = pyaudio.PyAudio()

        try:
            # 调试：列出麦克风设备，方便排查
            # self._list_audio_devices()

            self.stream = self.pa.open(
                rate=self.rhino.sample_rate,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=self.rhino.frame_length,
                input_device_index=MICROPHONE_INDEX if MICROPHONE_INDEX >= 0 else None
            )
            self._thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._thread.start()
            self.logger.info("Rhino 离线语音监听已启动")
        except Exception as e:
            self.logger.error(f"麦克风打开失败: {e}")
            self._running = False

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

        if self.stream:
            self.stream.close()
        if self.pa:
            self.pa.terminate()
        if self.rhino:
            self.rhino.delete()
        self.logger.info("Rhino 服务已停止")

    def _listen_loop(self):
        while self._running:
            try:
                # 1. 读取音频
                pcm = self.stream.read(self.rhino.frame_length, exception_on_overflow=False)
                pcm = struct.unpack_from("h" * self.rhino.frame_length, pcm)

                # 2. Rhino 推理
                is_finalized = self.rhino.process(pcm)

                if is_finalized:
                    inference = self.rhino.get_inference()
                    if inference.is_understood:
                        intent = inference.intent
                        slots = inference.slots
                        self.logger.info(f"✅ 识别成功 - 意图: [{intent}] | 参数: {slots}")
                        self._handle_intent(intent, slots)
                    else:
                        # 没听懂（不在语法树内）
                        pass
                        # self.logger.debug("未能理解指令")
            except Exception as e:
                if self._running:  # 只有在运行时才报错，避免停止时的正常IOError
                    self.logger.error(f"监听循环异常: {e}")

    def _handle_intent(self, intent, slots):
        """将 Intent 映射为小车指令"""
        cmd_to_send = None

        # === 模式切换 ===
        if intent == "system" and "mode" in slots:
            mode = slots["mode"]
            if mode == "smart":
                self.is_smart_mode = True
                self.logger.info(">>> 切换到：智能模式 (Cloud)")
            elif mode in ["normal", "manual"]:
                self.is_smart_mode = False
                self.logger.info(">>> 切换到：离线指令模式")
            return

        if self.is_smart_mode:
            self.logger.info("忽略离线指令（当前为智能模式）")
            return

        # === 运动指令映射 ===
        if intent == "move":
            if not slots:
                cmd_to_send = "stop"
            elif "direction" in slots:
                direction = slots["direction"]
                # 兼容你 regex_command.py 的指令集
                if direction in ["forward", "back", "left", "right"]:
                    cmd_to_send = f"move_{direction}"
            elif "turn_action" in slots and "turn_direction" in slots:
                turn_dir = slots["turn_direction"]
                cmd_to_send = f"turn_{turn_dir}"

        # === 提交指令到执行器 ===
        if cmd_to_send:
            self.logger.info(f"🚀 发送指令到执行器: {cmd_to_send}")
            try:
                # 获取当前事件循环
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        self.executor.add_command(cmd_to_send),
                        loop
                    )
                else:
                    self.logger.warning("Event loop is not running, cannot send async command.")
            except RuntimeError:
                # 在调试模式下，可能没有全局 loop，或者是在非 Async 环境运行
                # 这里的 MockExecutor 应该处理同步调用，或者忽略错误
                pass

    def _list_audio_devices(self):
        """调试用：打印音频设备列表"""
        print("--- Available Audio Devices ---")
        for i in range(self.pa.get_device_count()):
            info = self.pa.get_device_info_by_index(i)
            print(f"Index {i}: {info['name']} (Input Channels: {info['maxInputChannels']})")
        print("-------------------------------")


# ==========================================
#               调试入口
# ==========================================
if __name__ == "__main__":
    import time

    # 1. 设置日志格式
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger("DebugMain")


    # 2. 模拟 CommandExecutor (Mock)
    #    这样我们就不需要在树莓派上真实驱动电机，也不需要运行 FastAPI
    class MockCommandExecutor:
        async def add_command(self, command: str):
            print(f"\n[MOCK EXECUTOR] 收到指令: >>>>> {command} <<<<<\n")


    # 3. 准备 Asyncio 环境
    #    因为 VoiceService 内部使用了 asyncio.run_coroutine_threadsafe
    #    我们需要在后台起一个 loop 来模拟 FastAPI 的运行环境
    loop = asyncio.new_event_loop()


    def start_loop(loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()


    t_loop = threading.Thread(target=start_loop, args=(loop,), daemon=True)
    t_loop.start()

    # 4. 检查环境变量 (方便你在 IDE 或终端直接跑)
    #    如果 app/config.py 读取失败，这里可以手动硬编码用于测试
    if not PICOVOICE_ACCESS_KEY:
        logger.warning("警告: 未检测到 PICOVOICE_ACCESS_KEY，请确保 .env 文件存在或手动在代码中填入")
        # PICOVOICE_ACCESS_KEY = "你的_Key_填在这里"

    # 5. 启动服务
    logger.info("正在启动 Rhino 语音服务调试...")
    logger.info(f"加载模型路径: {RHINO_CONTEXT_PATH}")

    mock_executor = MockCommandExecutor()
    service = RhinoVoiceService(mock_executor)

    if service.rhino:
        service.start()
        print("\n" + "=" * 50)
        print("🎤 监听中... 请对着麦克风说话")
        print("尝试指令: 'Move forward', 'Turn left', 'Switch to smart mode'")
        print("按 Ctrl+C 退出")
        print("=" * 50 + "\n")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n停止服务...")
            service.stop()
            loop.call_soon_threadsafe(loop.stop)
            print("再见。")
    else:
        logger.error("服务初始化失败，请检查 Key 和模型路径。")