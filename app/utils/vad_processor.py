# -*- coding: utf-8 -*-
"""
语音活动检测 (VAD) 处理器
使用 WebRTC VAD 进行人声检测，过滤车轮噪音
"""
import logging
import time
from collections import deque
from typing import Optional, Tuple, List
from dataclasses import dataclass

# numpy 是可选依赖
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    np = None
    NUMPY_AVAILABLE = False

try:
    import webrtcvad
    WEBRTC_VAD_AVAILABLE = True
except ImportError:
    WEBRTC_VAD_AVAILABLE = False
    webrtcvad = None


@dataclass
class VADResult:
    """VAD 检测结果"""
    is_speech: bool
    confidence: float  # 0.0 - 1.0
    speech_duration_ms: float
    silence_duration_ms: float


class VADProcessor:
    """
    语音活动检测处理器

    功能：
    1. 检测是否为人声（过滤车轮噪音等环境噪音）
    2. 检测说话开始和结束
    3. 提供连续语音/静音时长统计
    """

    def __init__(
        self,
        aggressiveness: int = 2,
        frame_duration_ms: int = 30,
        min_speech_duration_ms: int = 300,
        min_silence_duration_ms: int = 500,
        logger: Optional[logging.Logger] = None
    ):
        """
        初始化 VAD 处理器

        Args:
            aggressiveness: VAD 敏感度 (0-3)
                0: 最敏感，容易检测到语音，但可能误触发
                1: 较敏感
                2: 中等（推荐）
                3: 最不敏感，需要大声说话
            frame_duration_ms: 帧长度（毫秒），支持 10, 20, 30
            min_speech_duration_ms: 最小语音长度，短于此长度认为是噪音
            min_silence_duration_ms: 最小静音长度，用于判断说话结束
        """
        if not WEBRTC_VAD_AVAILABLE:
            raise ImportError("webrtcvad 未安装，请运行: pip install webrtcvad")

        self.logger = logger or logging.getLogger(__name__)

        # VAD 参数
        self.aggressiveness = max(0, min(3, aggressiveness))
        self.frame_duration_ms = frame_duration_ms
        self.min_speech_duration_ms = min_speech_duration_ms
        self.min_silence_duration_ms = min_silence_duration_ms

        # 创建 VAD 对象
        self.vad = webrtcvad.Vad(aggressiveness)
        self.frame_size = int(self.frame_duration_ms * 16)  # 16kHz 采样率

        # 状态跟踪
        self.is_speaking = False
        self.speech_start_time: Optional[float] = None
        self.silence_start_time: Optional[float] = None

        # 统计数据
        self.speech_frames = 0
        self.silence_frames = 0
        self.total_frames = 0

        # 历史数据（用于平滑）
        self.recent_results = deque(maxlen=5)  # 保存最近 5 帧的结果

        self.logger.info(f"VAD 初始化: 敏感度={self.aggressiveness}, 帧长={self.frame_duration_ms}ms")

    def process_frame(self, audio_data: bytes) -> VADResult:
        """
        处理一帧音频数据

        Args:
            audio_data: 音频数据 (bytes)，必须是正确的帧长度

        Returns:
            VADResult: VAD 检测结果
        """
        # 检查帧长度
        if len(audio_data) != self.frame_size * 2:  # 16-bit = 2 bytes
            self.logger.warning(f"音频帧长度不正确: 期望 {self.frame_size * 2}, 实际 {len(audio_data)}")
            return VADResult(is_speech=False, confidence=0.0,
                           speech_duration_ms=0.0, silence_duration_ms=0.0)

        # 使用 VAD 检测
        is_speech = self.vad.is_speech(audio_data, self.sample_rate)

        # 更新统计
        self.total_frames += 1
        if is_speech:
            self.speech_frames += 1
        else:
            self.silence_frames += 1

        # 平滑处理（基于历史结果）
        self.recent_results.append(is_speech)
        smoothed_speech = self.smooth_results()

        # 计算置信度
        confidence = self.calculate_confidence()

        # 更新状态
        current_time = time.time()
        speech_duration = 0.0
        silence_duration = 0.0

        if smoothed_speech:
            if not self.is_speaking:
                # 检测到语音开始
                self.speech_start_time = current_time
                self.is_speaking = True
                self.logger.debug("检测到语音开始")

            speech_duration = (current_time - self.speech_start_time) * 1000 if self.speech_start_time else 0
            self.silence_start_time = None
        else:
            if self.is_speaking:
                # 检测到静音
                if self.silence_start_time is None:
                    self.silence_start_time = current_time

                silence_duration = (current_time - self.silence_start_time) * 1000

                # 如果静音时间足够长，认为说话结束
                if silence_duration >= self.min_silence_duration_ms:
                    speech_duration = (self.silence_start_time - self.speech_start_time) * 1000 if self.speech_start_time else 0

                    # 只有过足够长的语音才算有效
                    if speech_duration >= self.min_speech_duration_ms:
                        self.logger.debug(f"检测到语音结束，持续 {speech_duration:.0f}ms")
                    else:
                        self.logger.debug(f"忽略短语音 ({speech_duration:.0f}ms < {self.min_speech_duration_ms}ms)")

                    self.is_speaking = False
                    self.speech_start_time = None

        return VADResult(
            is_speech=smoothed_speech,
            confidence=confidence,
            speech_duration_ms=speech_duration,
            silence_duration_ms=silence_duration
        )

    @property
    def sample_rate(self) -> int:
        """采样率"""
        return 16000

    def smooth_results(self) -> bool:
        """
        平滑 VAD 结果（基于历史帧）
        如果最近的帧中大多数是语音，则认为是语音
        """
        if not self.recent_results:
            return False

        speech_count = sum(1 for r in self.recent_results if r)
        return speech_count > len(self.recent_results) // 2

    def calculate_confidence(self) -> float:
        """
        计算置信度
        基于最近的语音帧比例
        """
        if not self.recent_results:
            return 0.0

        speech_ratio = sum(1 for r in self.recent_results if r) / len(self.recent_results)
        return speech_ratio

    def reset(self):
        """重置 VAD 状态"""
        self.is_speaking = False
        self.speech_start_time = None
        self.silence_start_time = None
        self.speech_frames = 0
        self.silence_frames = 0
        self.total_frames = 0
        self.recent_results.clear()
        self.logger.debug("VAD 状态已重置")

    def get_stats(self) -> dict:
        """获取统计信息"""
        speech_ratio = self.speech_frames / self.total_frames if self.total_frames > 0 else 0
        return {
            "total_frames": self.total_frames,
            "speech_frames": self.speech_frames,
            "silence_frames": self.silence_frames,
            "speech_ratio": speech_ratio,
            "is_speaking": self.is_speaking
        }

    def should_trigger_asr(self) -> bool:
        """
        判断是否应该触发 ASR 识别

        条件：
        1. 检测到足够长的语音（超过 min_speech_duration_ms）
        2. 检测到足够长的静音（超过 min_silence_duration_ms）
        """
        return (
            not self.is_speaking and
            self.speech_start_time is not None and
            self.silence_start_time is not None
        )


class NoiseFilter:
    """
    噪音过滤器

    功能：
    1. 基于能量阈值过滤低能量噪音
    2. 基于频谱分析识别电机噪音特征
    """

    def __init__(
        self,
        energy_threshold: float = 0.01,
        logger: Optional[logging.Logger] = None
    ):
        """
        初始化噪音过滤器

        Args:
            energy_threshold: 能量阈值，低于此值认为是噪音
        """
        self.logger = logger or logging.getLogger(__name__)
        self.energy_threshold = energy_threshold

        # 自适应阈值
        self.noise_floor = 0.0
        self.adaptation_rate = 0.1

    def is_noise(self, audio_data) -> bool:
        """
        判断音频是否为噪音

        Args:
            audio_data: 音频数据 (归一化到 [-1, 1])，支持 numpy 数组或列表

        Returns:
            True 如果是噪音，False 如果是有效语音
        """
        # 兼容 numpy 和原生 Python
        if NUMPY_AVAILABLE and np is not None and hasattr(audio_data, '__array__'):
            # 使用 numpy 加速
            energy = float(np.mean(audio_data ** 2))

            # 频谱分析（简单的过零率）
            zero_crossing_rate = float(np.mean(np.diff(np.sign(audio_data)) != 0))
        else:
            # 使用纯 Python 实现
            energy = sum(x * x for x in audio_data) / len(audio_data)

            # 计算过零率
            sign_changes = sum(1 for i in range(1, len(audio_data))
                             if (audio_data[i] >= 0) != (audio_data[i-1] >= 0))
            zero_crossing_rate = sign_changes / len(audio_data)

        # 更新噪音底噪估计
        if energy < self.noise_floor:
            self.noise_floor = self.noise_floor * (1 - self.adaptation_rate) + energy * self.adaptation_rate
        elif energy < self.noise_floor * 2:
            self.noise_floor = self.noise_floor * (1 - self.adaptation_rate * 0.5) + energy * (self.adaptation_rate * 0.5)

        # 判断是否低于能量阈值
        is_below_threshold = energy < max(self.energy_threshold, self.noise_floor * 3)

        # 电机噪音通常有较低的过零率和持续的能量
        is_motor_noise = (energy > self.noise_floor * 2) and (zero_crossing_rate < 0.1)

        return is_below_threshold or is_motor_noise

    def get_noise_floor(self) -> float:
        """获取当前噪音底噪估计"""
        return self.noise_floor


def test_vad():
    """测试 VAD 功能"""
    import sys
    from pvrecorder import PvRecorder

    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    if not WEBRTC_VAD_AVAILABLE:
        print("错误: webrtcvad 未安装")
        print("请运行: pip install webrtcvad")
        return

    print("VAD 测试程序")
    print("=" * 50)

    # 列出麦克风
    devices = PvRecorder.get_available_devices()
    for i, dev in enumerate(devices):
        print(f"[{i}] {dev}")

    try:
        mic_index = int(input("\n选择麦克风索引: "))
    except ValueError:
        mic_index = -1

    # 初始化
    vad = VADProcessor(
        aggressiveness=2,
        frame_duration_ms=30,
        min_speech_duration_ms=300,
        min_silence_duration_ms=500
    )
    noise_filter = NoiseFilter(energy_threshold=0.01)

    # 启动麦克风
    recorder = PvRecorder(device_index=mic_index, frame_length=512)  # 512 samples = 32ms @ 16kHz
    recorder.start()

    print("\n开始监听... 说话时观察输出")
    print("按 Ctrl+C 退出\n")

    try:
        speech_buffer = []

        while True:
            pcm = recorder.read()

            # 转换为需要的帧长度
            frame_size = int(30 * 16)  # 30ms @ 16kHz
            for i in range(0, len(pcm), frame_size * 2):
                frame_bytes = bytes(pcm[i:i + frame_size * 2])

                if len(frame_bytes) < frame_size * 2:
                    break

                # VAD 检测
                result = vad.process_frame(frame_bytes)

                # 噪音过滤
                audio_array = np.frombuffer(frame_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                is_noise = noise_filter.is_noise(audio_array)

                # 输出结果
                if result.is_speech and not is_noise:
                    speech_buffer.append(frame_bytes)
                    print("🎤 ", end="", flush=True)
                else:
                    if speech_buffer:
                        duration = len(speech_buffer) * 30
                        if duration >= vad.min_speech_duration_ms:
                            print(f"\n✅ 检测到语音，持续 {duration}ms")
                        speech_buffer.clear()

                    if is_noise:
                        print("🔇", end="", flush=True)
                    else:
                        print(".", end="", flush=True)

    except KeyboardInterrupt:
        print("\n\n统计信息:")
        stats = vad.get_stats()
        print(f"  总帧数: {stats['total_frames']}")
        print(f"  语音帧: {stats['speech_frames']} ({stats['speech_ratio']*100:.1f}%)")
        print(f"  静音帧: {stats['silence_frames']}")
        print(f"  噪音底噪: {noise_filter.get_noise_floor():.6f}")

    finally:
        recorder.stop()
        recorder.delete()


if __name__ == "__main__":
    test_vad()
