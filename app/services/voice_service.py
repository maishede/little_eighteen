import threading
import pvrhino
import pyaudio
import struct
import logging
import asyncio
import os
from app.config import PICOVOICE_ACCESS_KEY, RHINO_CONTEXT_PATH, MICROPHONE_INDEX
from app.utils.regex_command import CommandExecutor


class RhinoVoiceService:
    def __init__(self, command_executor: CommandExecutor):
        self.logger = logging.getLogger("RhinoVoice")
        self.executor = command_executor
        self._running = False
        self._thread = None
        self.rhino = None
        self.pa = None
        self.stream = None

        # 状态标志：是否处于智能模式
        # 在智能模式下，我们可能需要暂停 Rhino 的指令监听，或者改变处理逻辑
        self.is_smart_mode = False

        # 初始化 Rhino
        try:
            if not os.path.exists(RHINO_CONTEXT_PATH):
                self.logger.error(f"Rhino 模型文件未找到: {RHINO_CONTEXT_PATH}")
                return

            self.rhino = pvrhino.create(
                access_key=PICOVOICE_ACCESS_KEY,
                context_path=RHINO_CONTEXT_PATH,
                sensitivity=0.5,
                endpoint_duration_sec=1.0,  # 说完话后静默多久算结束
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

                # 2. 如果是智能模式，这里可以把 PCM 数据转发给云端 API (TODO)
                # 目前逻辑：如果是智能模式，暂时不处理离线指令，或者只处理“切换回普通模式”的指令

                # 3. Rhino 推理
                is_finalized = self.rhino.process(pcm)

                if is_finalized:
                    inference = self.rhino.get_inference()
                    if inference.is_understood:
                        intent = inference.intent
                        slots = inference.slots
                        self.logger.info(f"识别意图: {intent}, 参数: {slots}")
                        self._handle_intent(intent, slots)
                    else:
                        # 没听懂（不是定义的语法）
                        pass
            except Exception as e:
                self.logger.error(f"监听循环异常: {e}")

    def _handle_intent(self, intent, slots):
        """将 Intent 映射为小车指令"""
        cmd_to_send = None

        # === 模式切换指令 ===
        if intent == "system" and "mode" in slots:
            mode = slots["mode"]
            if mode == "smart":
                self.is_smart_mode = True
                self.logger.info("切换到：智能模式 (Cloud)")
                # 这里可以触发音效或TTS反馈
            elif mode in ["normal", "manual"]:
                self.is_smart_mode = False
                self.logger.info("切换到：离线指令模式")
            return

        # 如果在智能模式下，可能屏蔽掉运动指令，或者只允许由 LLM 控制
        if self.is_smart_mode:
            self.logger.info("忽略离线指令（当前为智能模式）")
            return

        # === 运动指令 (映射到 CommandExecutor 支持的字符串) ===
        if intent == "move":
            # 处理 "stop"
            if not slots:  # 有些指令可能没有 slots，比如直接喊 stop
                cmd_to_send = "stop"

            # 处理 "move forward/back/left/right"
            elif "direction" in slots:
                direction = slots["direction"]
                # 映射: forward -> move_forward
                if direction in ["forward", "back", "left", "right"]:
                    cmd_to_send = f"move_{direction}"

            # 处理 "turn left/right"
            elif "turn_action" in slots and "turn_direction" in slots:
                turn_dir = slots["turn_direction"]
                cmd_to_send = f"turn_{turn_dir}"

        # === 提交指令 ===
        if cmd_to_send:
            # 跨线程调用 Async 方法
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self.executor.add_command(cmd_to_send),
                    loop
                )