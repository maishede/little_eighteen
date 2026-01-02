import threading
import pvrhino
import logging
import asyncio
import os
import sys
from pathlib import Path
from pvrecorder import PvRecorder

# numpy 是可选依赖（仅 VAD 需要）
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    np = None
    NUMPY_AVAILABLE = False

# === 路径与配置加载 ===
current_file_path = Path(__file__).resolve()
project_root = current_file_path.parent.parent.parent

try:
    from app.config import (
        PICOVOICE_ACCESS_KEY, RHINO_CONTEXT_PATH, RHINO_MODEL_PATH, MICROPHONE_INDEX,
        RHINO_SENSITIVITY, RHINO_ENDPOINT_DURATION, RHINO_REQUIRE_ENDPOINT,
        VAD_ENABLED, VAD_AGGRESSIVENESS, VAD_FRAME_DURATION,
        VAD_MIN_SPEECH_DURATION, VAD_MIN_SILENCE_DURATION,
        VOICE_DIAGNOSTICS_ENABLED, NOISE_THRESHOLD_DB
    )
    from app.utils.regex_command import CommandExecutor
    from app.utils.vad_processor import VADProcessor, NoiseFilter, WEBRTC_VAD_AVAILABLE
    from app.utils.voice_diagnostics import VoiceDiagnostics
except ImportError:
    # 调试 Fallback
    import os

    PICOVOICE_ACCESS_KEY = os.getenv("PICOVOICE_ACCESS_KEY", "")
    RHINO_CONTEXT_PATH = str(project_root / 'models' / 'little_18_zh_raspberry-pi_v4_0_0.rhn')
    RHINO_MODEL_PATH = str(project_root / 'models' / 'rhino_params_zh.pv')
    MICROPHONE_INDEX = int(os.getenv("MICROPHONE_INDEX", 11))
    RHINO_SENSITIVITY = 0.5
    RHINO_ENDPOINT_DURATION = 0.5
    RHINO_REQUIRE_ENDPOINT = True
    VAD_ENABLED = False
    VAD_AGGRESSIVENESS = 2
    VAD_FRAME_DURATION = 30
    VAD_MIN_SPEECH_DURATION = 300
    VAD_MIN_SILENCE_DURATION = 500
    VOICE_DIAGNOSTICS_ENABLED = False
    NOISE_THRESHOLD_DB = 50.0
    CommandExecutor = object
    VADProcessor = None
    NoiseFilter = None
    WEBRTC_VAD_AVAILABLE = False
    VoiceDiagnostics = None


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
            '左后': 'move_left_back', '右后': 'move_right_back',
        }

        # VAD 和噪音过滤
        self.vad_processor: VADProcessor = None
        self.noise_filter: NoiseFilter = None
        self.diagnostics: VoiceDiagnostics = None

        # VAD 状态
        self._vad_enabled = VAD_ENABLED
        self._speech_buffer = []  # 存储检测到的语音帧
        self._last_speech_time = 0

        # 诊断统计
        self._recognition_count = 0
        self._noise_rejection_count = 0

        if not PICOVOICE_ACCESS_KEY:
            self.logger.error("未配置 PICOVOICE_ACCESS_KEY")
            return

        try:
            self.rhino = pvrhino.create(
                access_key=PICOVOICE_ACCESS_KEY,
                context_path=RHINO_CONTEXT_PATH,
                model_path=RHINO_MODEL_PATH,
                sensitivity=RHINO_SENSITIVITY,
                endpoint_duration_sec=RHINO_ENDPOINT_DURATION,
                require_endpoint=RHINO_REQUIRE_ENDPOINT
            )
            self.logger.info(f"Rhino 初始化成功")
            self.logger.info(f"  灵敏度: {RHINO_SENSITIVITY}")
            self.logger.info(f"  端点检测: {RHINO_ENDPOINT_DURATION}s")
            self.logger.info(f"  需要端点: {RHINO_REQUIRE_ENDPOINT}")
        except Exception as e:
            self.logger.error(f"Rhino 初始化失败: {e}")

        # 初始化 VAD
        if VAD_ENABLED:
            if WEBRTC_VAD_AVAILABLE:
                try:
                    self.vad_processor = VADProcessor(
                        aggressiveness=VAD_AGGRESSIVENESS,
                        frame_duration_ms=VAD_FRAME_DURATION,
                        min_speech_duration_ms=VAD_MIN_SPEECH_DURATION,
                        min_silence_duration_ms=VAD_MIN_SILENCE_DURATION,
                        logger=self.logger
                    )
                    self.noise_filter = NoiseFilter(energy_threshold=0.01)
                    self.logger.info(f"VAD 已启用 (敏感度: {VAD_AGGRESSIVENESS})")
                except Exception as e:
                    self.logger.warning(f"VAD 初始化失败: {e}，将禁用 VAD")
                    self._vad_enabled = False
            else:
                self.logger.warning("webrtcvad 未安装，VAD 功能不可用")
                self.logger.warning("安装方法: pip install webrtcvad")
                self._vad_enabled = False

        # 初始化诊断工具
        if VOICE_DIAGNOSTICS_ENABLED and VoiceDiagnostics:
            try:
                self.diagnostics = VoiceDiagnostics(
                    microphone_index=MICROPHONE_INDEX,
                    logger=self.logger
                )
                self.diagnostics.start()
                # 测量背景噪音
                self.diagnostics.measure_background_noise(1000)
            except Exception as e:
                self.logger.warning(f"诊断工具初始化失败: {e}")

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

        # 停止诊断工具
        if self.diagnostics:
            self.diagnostics.stop()

        # 打印统计信息
        if self._vad_enabled:
            self.logger.info("=" * 50)
            self.logger.info("语音识别统计:")
            self.logger.info(f"  识别次数: {self._recognition_count}")
            self.logger.info(f"  噪音过滤: {self._noise_rejection_count}")
            if self.vad_processor:
                stats = self.vad_processor.get_stats()
                self.logger.info(f"  语音帧比例: {stats['speech_ratio']*100:.1f}%")
            self.logger.info("=" * 50)

        self.logger.info("Rhino 服务已停止")

    def _listen_loop(self):
        """监听循环（支持 VAD）"""
        while self._running:
            try:
                pcm = self.recorder.read()

                # VAD 预处理：如果启用了 VAD，先进行语音检测
                if self._vad_enabled and self.vad_processor and NUMPY_AVAILABLE and np is not None:
                    # 将 PCM 数据转换为 VAD 所需的帧格式
                    audio_array = np.array(pcm, dtype=np.int16)

                    # VAD 处理（按帧处理）
                    frame_size = int(self.vad_processor.frame_duration_ms * 16)  # 16kHz
                    should_process = False

                    for i in range(0, len(audio_array), frame_size):
                        frame_bytes = bytes(audio_array[i:i + frame_size].tobytes())

                        if len(frame_bytes) < frame_size * 2:
                            break

                        # VAD 检测
                        vad_result = self.vad_processor.process_frame(frame_bytes)

                        # 噪音过滤
                        audio_normalized = audio_array[i:i + frame_size].astype(np.float32) / 32768.0
                        is_noise = self.noise_filter.is_noise(audio_normalized)

                        if vad_result.is_speech and not is_noise:
                            should_process = True
                            self._speech_buffer.append(pcm)

                            # 检测到足够长的静音，处理语音
                            if vad_result.silence_duration_ms >= self.vad_processor.min_silence_duration_ms:
                                if self._speech_buffer:
                                    # 处理累积的语音帧
                                    for speech_pcm in self._speech_buffer:
                                        self._process_audio_frame(speech_pcm)
                                    self._speech_buffer.clear()
                                    self.vad_processor.reset()
                        elif not vad_result.is_speech and is_noise:
                            self._noise_rejection_count += 1

                    if not should_process:
                        continue

                # 直接处理（无 VAD 或 VAD 检测到语音）
                is_finalized = self.rhino.process(pcm)

                if is_finalized:
                    inference = self.rhino.get_inference()
                    if inference.is_understood:
                        intent = inference.intent
                        slots = inference.slots
                        self._recognition_count += 1
                        self.logger.info(f"✅ 语音识别: 意图=[{intent}] 参数={slots}")
                        self._handle_intent(intent, slots)
            except Exception as e:
                if self._running:
                    self.logger.error(f"监听循环异常: {e}")

    def _process_audio_frame(self, pcm):
        """处理单个音频帧"""
        is_finalized = self.rhino.process(pcm)

        if is_finalized:
            inference = self.rhino.get_inference()
            if inference.is_understood:
                intent = inference.intent
                slots = inference.slots
                self._recognition_count += 1
                self.logger.info(f"✅ 语音识别: 意图=[{intent}] 参数={slots}")
                self._handle_intent(intent, slots)

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
                    future = asyncio.run_coroutine_threadsafe(
                        self.executor.add_command(cmd_to_send),
                        self._main_loop
                    )
                    # 【关键修复】添加回调来处理潜在错误
                    future.add_done_callback(self._command_callback)
                except Exception as e:
                    self.logger.error(f"❌ 指令发送失败: {e}")
                    # 【关键修复】发送失败时尝试恢复避障检测状态
                    if hasattr(self.executor, 'control'):
                        self.executor.control.distance_detection_enabled = True
                        self.logger.warning("⚠️ 由于指令发送失败，已强制恢复避障检测")
            else:
                self.logger.error("❌ 严重错误: 主线程 Event Loop 未运行或丢失，无法发送指令！")

    def _command_callback(self, future):
        """命令执行完成后的回调处理"""
        try:
            future.result()  # 这会抛出任何在协程中发生的异常
        except Exception as e:
            self.logger.error(f"❌ 命令执行回调异常: {e}")


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