# -*- coding: utf-8 -*-
"""
纯数学方法的音频检测器
不使用深度学习，仅用信号处理算法
"""
import numpy as np
import logging
from typing import Optional
from collections import deque

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    np = None
    NUMPY_AVAILABLE = False


class MathVoiceDetector:
    """
    纯数学方法的人声检测器

    使用方法：
    1. 能量阈值 - 过滤低音量
    2. 过零率 - 区分人声和噪音
    3. 频谱分析 - 检测人声频率范围
    """

    def __init__(
        self,
        energy_threshold: float = 0.01,
        zcr_threshold: float = 0.1,
        voice_band_low: int = 300,   # 人声频率下限 Hz
        voice_band_high: int = 3400, # 人声频率上限 Hz
        sample_rate: int = 16000,
        logger: Optional[logging.Logger] = None
    ):
        self.logger = logger or logging.getLogger(__name__)
        self.energy_threshold = energy_threshold
        self.zcr_threshold = zcr_threshold
        self.voice_band_low = voice_band_low
        self.voice_band_high = voice_band_high
        self.sample_rate = sample_rate

        # 自适应噪声底噪
        self.noise_floor = 0.0
        self.adaptation_rate = 0.05

        # 历史数据（用于平滑）
        self.energy_history = deque(maxlen=10)
        self.zcr_history = deque(maxlen=10)

    def is_speech(self, audio_data) -> bool:
        """
        综合判断是否为人声

        Args:
            audio_data: 音频数据（归一化到 [-1, 1]）

        Returns:
            True 检测为人声，False 为噪音
        """
        if not NUMPY_AVAILABLE or np is None:
            return True  # 无 numpy 时默认通过

        # 转换为 numpy 数组
        audio = np.array(audio_data, dtype=np.float32)
        if len(audio.shape) > 1:
            audio = audio.flatten()

        # 1. 过零率检测（关键：电机噪音是低频，过零率极低）
        zcr = self._compute_zero_crossing_rate(audio)

        # 2. 频谱分析（检查是否包含人声频率 300-3400Hz）
        has_voice_band = self._check_voice_frequency_band(audio)

        # 综合判断（针对电机噪音场景优化，无能量阈值）：
        # - 过零率在人声范围内（0.05-0.5）
        # - 频谱包含人声频率成分
        #
        # 电机噪音特征：低频 + 过零率极低
        # 人声特征：中频(300-3400Hz) + 适中过零率

        is_voice = (
            0.05 < zcr < 0.5 and    # 过零率在合理范围
            has_voice_band           # 包含人声频率
        )

        return is_voice

    def _compute_energy(self, audio: np.ndarray) -> float:
        """计算能量（RMS）"""
        return float(np.sqrt(np.mean(audio ** 2)))

    def _compute_zero_crossing_rate(self, audio: np.ndarray) -> float:
        """
        计算过零率（Zero Crossing Rate）

        人声的过零率通常在 0.05-0.5 之间
        纯噪音（如电机声）过零率很低或很高
        """
        # 检测符号变化
        sign_changes = np.diff(np.sign(audio))
        zcr = np.sum(sign_changes != 0) / len(sign_changes)
        return float(zcr)

    def _check_voice_frequency_band(self, audio: np.ndarray) -> bool:
        """
        检查音频是否包含人声频率成分 (300-3400Hz)

        使用简单的频谱分析方法
        """
        try:
            # FFT
            fft = np.fft.rfft(audio)
            freqs = np.fft.rfftfreq(len(audio), 1 / self.sample_rate)
            magnitude = np.abs(fft)

            # 计算人声频段的能量
            voice_mask = (freqs >= self.voice_band_low) & (freqs <= self.voice_band_high)
            voice_energy = np.sum(magnitude[voice_mask])

            # 计算总能量
            total_energy = np.sum(magnitude)

            # 如果人声频段能量占比超过 30%，认为包含人声
            return (voice_energy / max(total_energy, 1e-10)) > 0.3

        except Exception as e:
            self.logger.debug(f"频谱分析失败: {e}")
            return True  # 失败时默认通过

    def _update_noise_floor(self, energy: float):
        """
        更新噪声底噪估计

        使用较低能量值来估计环境噪声
        """
        if energy < self.noise_floor:
            self.noise_floor = (self.noise_floor * (1 - self.adaptation_rate) +
                               energy * self.adaptation_rate)
        elif energy < self.noise_floor * 2:
            self.noise_floor = (self.noise_floor * (1 - self.adaptation_rate * 0.5) +
                               energy * (self.adaptation_rate * 0.5))

    def get_noise_floor(self) -> float:
        """获取当前噪声底噪"""
        return self.noise_floor


class SimpleNoiseFilter:
    """
    简单噪音过滤器 - 纯数学方法

    基于以下原理：
    1. 能量阈值 - 过滤静音
    2. 过零率 - 区分周期性和随机噪音
    """

    def __init__(
        self,
        energy_threshold: float = 0.02,
        max_energy_threshold: float = 0.8,
        logger: Optional[logging.Logger] = None
    ):
        self.energy_threshold = energy_threshold
        self.max_energy_threshold = max_energy_threshold
        self.logger = logger or logging.getLogger(__name__)

        # 统计数据
        self.total_frames = 0
        self.noise_frames = 0

    def is_noise(self, audio_data) -> bool:
        """
        判断是否为噪音

        Args:
            audio_data: 音频数据

        Returns:
            True 为噪音，False 为有效信号
        """
        if not NUMPY_AVAILABLE or np is None:
            return False

        audio = np.array(audio_data, dtype=np.float32)
        if len(audio.shape) > 1:
            audio = audio.flatten()

        # 1. 能量过低 → 静音/噪音
        energy = np.sqrt(np.mean(audio ** 2))
        if energy < self.energy_threshold:
            return True

        # 2. 能量过高 → 可能是噪音（如碰撞声）
        if energy > self.max_energy_threshold:
            return True

        # 3. 过零率检测
        sign_changes = np.diff(np.sign(audio))
        zcr = np.sum(sign_changes != 0) / len(sign_changes)

        # 电机噪音通常是低频，过零率很低
        if zcr < 0.02:
            self.noise_frames += 1
            return True

        # 更新统计
        self.total_frames += 1

        return False

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "total_frames": self.total_frames,
            "noise_frames": self.noise_frames,
            "noise_ratio": self.noise_frames / max(self.total_frames, 1)
        }


def test_math_detector():
    """测试纯数学检测器"""
    import time
    try:
        from pvrecorder import PvRecorder
    except ImportError:
        print("需要安装 pvrecorder")
        return

    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    detector = MathVoiceDetector(
        energy_threshold=0.02,
        zcr_threshold=0.1,
        voice_band_low=300,
        voice_band_high=3400
    )

    print("\n纯数学语音检测器测试")
    print("=" * 50)
    print("原理：")
    print("1. 能量阈值 - 过滤低音量")
    print("2. 过零率 - 区分人声(0.05-0.5)和噪音(<0.02)")
    print("3. 频谱分析 - 检查是否包含人声频率(300-3400Hz)")
    print("=" * 50)

    # 列出麦克风
    devices = PvRecorder.get_available_devices()
    print("\n可用麦克风:")
    for i, dev in enumerate(devices):
        print(f"  [{i}] {dev}")

    try:
        mic_index = int(input("\n选择麦克风索引: "))
    except ValueError:
        mic_index = -1

    recorder = PvRecorder(device_index=mic_index, frame_length=512)
    recorder.start()

    print("\n开始监听... 说话时观察输出")
    print("按 Ctrl+C 退出\n")

    speech_count = 0
    noise_count = 0

    try:
        while True:
            pcm = recorder.read()
            audio = np.array(pcm, dtype=np.int16).astype(np.float32) / 32768.0

            is_noise = SimpleNoiseFilter().is_noise(audio)
            is_speech = not is_noise and detector.is_speech(audio)

            if is_speech:
                print("🎤", end="", flush=True)
                speech_count += 1
            else:
                print(".", end="", flush=True)
                noise_count += 1

    except KeyboardInterrupt:
        print(f"\n\n统计: 语音={speech_count}, 噪音/静音={noise_count}")

    finally:
        recorder.stop()
        recorder.delete()


if __name__ == "__main__":
    test_math_detector()
