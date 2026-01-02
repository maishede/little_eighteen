# -*- coding: utf-8 -*-
"""
语音诊断工具
用于分析麦克风输入、噪音水平、语音识别性能
"""
import numpy as np
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional, List
from pvrecorder import PvRecorder


@dataclass
class DiagnosticsReport:
    """诊断报告"""
    timestamp: float
    noise_level_db: float
    is_noisy: bool
    signal_to_noise_ratio: float
    audio_level: float
    clipping_count: int
    recommendation: List[str]


class VoiceDiagnostics:
    """语音诊断工具"""

    def __init__(self, microphone_index: int = -1, logger: Optional[logging.Logger] = None):
        self.microphone_index = microphone_index
        self.logger = logger or logging.getLogger(__name__)

        # 诊断参数
        self.sample_rate = 16000  # 采样率
        self.noise_threshold_db = 50.0  # 噪音阈值（分贝）
        self.clipping_threshold = 0.95  # 削波阈值

        # 统计数据
        self.audio_levels = deque(maxlen=100)  # 最近的音频电平
        self.noise_levels = deque(maxlen=50)  # 最近的噪音水平
        self.clipping_count = 0  # 削波计数
        self.total_samples = 0  # 总样本数

        self.recorder: Optional[PvRecorder] = None

    def start(self):
        """启动诊断"""
        try:
            self.recorder = PvRecorder(device_index=self.microphone_index, frame_length=512)
            self.recorder.start()
            self.logger.info(f"语音诊断已启动 (麦克风: {self.recorder.selected_device})")
        except Exception as e:
            self.logger.error(f"语音诊断启动失败: {e}")
            raise

    def stop(self):
        """停止诊断"""
        if self.recorder:
            self.recorder.stop()
            self.recorder.delete()
            self.recorder = None
            self.logger.info("语音诊断已停止")

    def calculate_db(self, audio_data: np.ndarray) -> float:
        """计算音频的分贝值"""
        # 避免除零
        rms = np.sqrt(np.mean(audio_data ** 2))
        if rms < 1e-10:
            return -100.0

        # 参考值：16-bit PCM 的最大值
        ref = 32768.0
        db = 20 * np.log10(rms / ref)
        return max(-100.0, min(0.0, db))

    def calculate_snr(self, signal_db: float, noise_db: float) -> float:
        """计算信噪比 (SNR)"""
        if noise_db < -90:
            return 100.0  # 静音环境
        return signal_db - noise_db

    def detect_clipping(self, audio_data: np.ndarray) -> int:
        """检测音频削波"""
        clipping = np.abs(audio_data) > (self.clipping_threshold * 32768)
        return int(np.sum(clipping))

    def analyze_audio_chunk(self, audio_data: np.ndarray) -> dict:
        """分析单个音频块"""
        # 转换为 numpy 数组并归一化
        audio_normalized = np.array(audio_data, dtype=np.float32) / 32768.0

        # 计算各种指标
        audio_level = np.sqrt(np.mean(audio_normalized ** 2))  # RMS 电平
        db = self.calculate_db(audio_normalized * 32768)
        clipping = self.detect_clipping(audio_normalized)

        # 更新统计
        self.audio_levels.append(audio_level)
        self.clipping_count += clipping
        self.total_samples += len(audio_data)

        return {
            "audio_level": audio_level,
            "db": db,
            "clipping": clipping,
            "samples": len(audio_data)
        }

    def measure_background_noise(self, duration_ms: int = 1000) -> float:
        """测量背景噪音水平"""
        if not self.recorder:
            raise RuntimeError("诊断器未启动")

        self.logger.info(f"正在测量背景噪音 ({duration_ms}ms)...")
        noise_readings = []
        start_time = time.time()

        while (time.time() - start_time) * 1000 < duration_ms:
            pcm = self.recorder.read()
            audio_normalized = np.array(pcm, dtype=np.float32) / 32768.0
            db = self.calculate_db(audio_normalized * 32768)
            noise_readings.append(db)

        avg_noise = np.mean(noise_readings)
        self.noise_levels.append(avg_noise)
        self.logger.info(f"背景噪音水平: {avg_noise:.1f} dB")

        return avg_noise

    def generate_report(self, signal_level: float = 0.0) -> DiagnosticsReport:
        """生成诊断报告"""
        current_time = time.time()

        # 获取最近的噪音水平
        noise_db = self.noise_levels[-1] if self.noise_levels else -60.0
        signal_db = 20 * np.log10(signal_level * 32768) if signal_level > 1e-10 else -60.0

        # 计算信噪比
        snr = self.calculate_snr(signal_db, noise_db)

        # 判断是否为噪音环境
        is_noisy = noise_db > self.noise_threshold_db

        # 获取最近的音频电平
        avg_audio_level = np.mean(self.audio_levels) if self.audio_levels else 0.0

        # 生成建议
        recommendations = []
        if is_noisy:
            recommendations.append(f"环境噪音较高 ({noise_db:.1f}dB)，建议：")
            recommendations.append("  1. 远离噪音源（如电机、风扇）")
            recommendations.append("  2. 使用指向性麦克风或降噪麦克风")
            recommendations.append("  3. 增加 VAD 敏感度 (VAD_AGGRESSIVENESS)")

        if self.clipping_count > 100:
            recommendations.append("检测到音频削波，建议：")
            recommendations.append("  1. 降低麦克风增益或远离麦克风")
            recommendations.append("  2. 检查麦克风是否有 AGC（自动增益控制）")

        if snr < 10:
            recommendations.append(f"信噪比较低 ({snr:.1f}dB)，建议：")
            recommendations.append("  1. 靠近麦克风说话")
            recommendations.append("  2. 减少背景噪音")
            recommendations.append("  3. 考虑使用噪音抑制算法")

        if not recommendations:
            recommendations.append("音频环境良好！")

        return DiagnosticsReport(
            timestamp=current_time,
            noise_level_db=noise_db,
            is_noisy=is_noisy,
            signal_to_noise_ratio=snr,
            audio_level=avg_audio_level,
            clipping_count=self.clipping_count,
            recommendation=recommendations
        )

    def print_report(self, report: DiagnosticsReport):
        """打印诊断报告"""
        self.logger.info("=" * 50)
        self.logger.info("📊 语音诊断报告")
        self.logger.info("=" * 50)
        self.logger.info(f"背景噪音: {report.noise_level_db:.1f} dB " +
                         ("🔴 (噪音较高)" if report.is_noisy else "🟢 (正常)"))
        self.logger.info(f"信噪比: {report.signal_to_noise_ratio:.1f} dB")
        self.logger.info(f"音频电平: {report.audio_level:.3f}")
        self.logger.info(f"削波次数: {report.clipping_count}")
        self.logger.info("\n建议:")
        for rec in report.recommendation:
            self.logger.info(f"  {rec}")
        self.logger.info("=" * 50)

    def reset_stats(self):
        """重置统计数据"""
        self.audio_levels.clear()
        self.noise_levels.clear()
        self.clipping_count = 0
        self.total_samples = 0
        self.logger.info("统计数据已重置")


def list_microphones():
    """列出所有可用的麦克风设备"""
    try:
        devices = PvRecorder.get_available_devices()
        print("\n🎤 可用麦克风设备:")
        print("-" * 50)
        for i, device in enumerate(devices):
            print(f"  [{i}] {device}")
        print("-" * 50)
        return devices
    except Exception as e:
        print(f"无法获取麦克风列表: {e}")
        return []


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 列出可用麦克风
    list_microphones()

    print("\n开始语音诊断...")
    print("请保持安静，程序将测量背景噪音...\n")

    diagnostics = VoiceDiagnostics(microphone_index=-1)

    try:
        diagnostics.start()

        # 测量背景噪音
        diagnostics.measure_background_noise(duration_ms=2000)

        # 生成报告
        report = diagnostics.generate_report()
        diagnostics.print_report(report)

    finally:
        diagnostics.stop()
