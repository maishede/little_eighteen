# -*- coding: utf-8 -*-
"""
音频样本分析工具

用于分析采集到的音频样本，提取特征信息：
- 频谱分析（FFT）
- 过零率（ZCR）
- 能量分析
- 人声频段占比
"""
import os
import wave
import logging
import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from collections import defaultdict

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    print("警告: numpy 未安装，部分功能不可用")


@dataclass
class AudioFeatures:
    """音频特征"""
    filename: str
    sample_type: str
    duration: float
    zcr: float  # 过零率
    energy: float  # 能量（RMS）
    voice_band_ratio: float  # 人声频段能量占比
    dominant_freq: float  # 主频率
    spectral_centroid: float  # 频谱质心


class AudioSampleAnalyzer:
    """音频样本分析器"""

    def __init__(self, sample_dir: str, sample_rate: int = 16000):
        """
        初始化分析器

        Args:
            sample_dir: 样本目录
            sample_rate: 采样率 Hz
        """
        self.sample_dir = sample_dir
        self.sample_rate = sample_rate
        self.logger = logging.getLogger(__name__)

        # 频率范围
        self.voice_band_low = 300  # 人声频率下限 Hz
        self.voice_band_high = 3400  # 人声频率上限 Hz

    def load_wav(self, filepath: str) -> Optional[List[int]]:
        """加载 WAV 文件"""
        try:
            with wave.open(filepath, 'rb') as wf:
                frames = wf.getnframes()
                audio_data = wf.readframes(frames)
                # 转换为 int16 数组
                import struct
                audio = [struct.unpack('<h', audio_data[i:i+2])[0]
                        for i in range(0, len(audio_data), 2)]
                return audio
        except Exception as e:
            self.logger.error(f"加载 WAV 失败: {e}")
            return None

    def compute_zcr(self, audio: List[int]) -> float:
        """计算过零率"""
        if not NUMPY_AVAILABLE:
            return 0.0

        arr = np.array(audio, dtype=np.float32)
        # 归一化到 [-1, 1]
        arr = arr / 32768.0
        sign_changes = np.diff(np.sign(arr))
        zcr = np.sum(sign_changes != 0) / len(sign_changes)
        return float(zcr)

    def compute_energy(self, audio: List[int]) -> float:
        """计算能量（RMS）"""
        if not NUMPY_AVAILABLE:
            return 0.0

        arr = np.array(audio, dtype=np.float32)
        # 归一化到 [-1, 1]
        arr = arr / 32768.0
        rms = np.sqrt(np.mean(arr ** 2))
        return float(rms)

    def compute_frequency_features(self, audio: List[int]) -> Dict[str, float]:
        """计算频率相关特征"""
        if not NUMPY_AVAILABLE:
            return {
                'voice_band_ratio': 0.0,
                'dominant_freq': 0.0,
                'spectral_centroid': 0.0
            }

        arr = np.array(audio, dtype=np.float32)
        if len(arr.shape) > 1:
            arr = arr.flatten()

        # FFT
        fft = np.fft.rfft(arr)
        freqs = np.fft.rfftfreq(len(arr), 1 / self.sample_rate)
        magnitude = np.abs(fft)

        # 计算人声频段能量
        voice_mask = (freqs >= self.voice_band_low) & (freqs <= self.voice_band_high)
        voice_energy = np.sum(magnitude[voice_mask])
        total_energy = np.sum(magnitude)
        voice_band_ratio = voice_energy / max(total_energy, 1e-10)

        # 主频率
        dominant_freq = freqs[np.argmax(magnitude)]

        # 频谱质心（频谱重心）
        spectral_centroid = np.sum(freqs * magnitude) / max(total_energy, 1e-10)

        return {
            'voice_band_ratio': float(voice_band_ratio),
            'dominant_freq': float(dominant_freq),
            'spectral_centroid': float(spectral_centroid)
        }

    def analyze_file(self, filepath: str, sample_type: str) -> Optional[AudioFeatures]:
        """分析单个音频文件"""
        audio = self.load_wav(filepath)
        if audio is None:
            return None

        duration = len(audio) / self.sample_rate
        zcr = self.compute_zcr(audio)
        energy = self.compute_energy(audio)

        freq_features = self.compute_frequency_features(audio)

        return AudioFeatures(
            filename=os.path.basename(filepath),
            sample_type=sample_type,
            duration=duration,
            zcr=zcr,
            energy=energy,
            voice_band_ratio=freq_features['voice_band_ratio'],
            dominant_freq=freq_features['dominant_freq'],
            spectral_centroid=freq_features['spectral_centroid']
        )

    def analyze_all(self) -> Dict[str, List[AudioFeatures]]:
        """分析所有样本文件"""
        results = defaultdict(list)

        sample_types = ['motor', 'wheel_noise', 'speech', 'mixed', 'background']

        for sample_type in sample_types:
            type_dir = os.path.join(self.sample_dir, sample_type)
            if not os.path.exists(type_dir):
                continue

            for filename in os.listdir(type_dir):
                if not filename.endswith('.wav'):
                    continue

                filepath = os.path.join(type_dir, filename)
                features = self.analyze_file(filepath, sample_type)
                if features:
                    results[sample_type].append(features)

        return dict(results)

    def generate_report(self, results: Dict[str, List[AudioFeatures]]) -> str:
        """生成分析报告"""
        report = []
        report.append("=" * 80)
        report.append("音频样本分析报告")
        report.append("=" * 80)
        report.append("")

        for sample_type, features_list in results.items():
            if not features_list:
                continue

            report.append(f"【{sample_type}】共 {len(features_list)} 个样本")
            report.append("-" * 60)

            # 计算统计值
            zcr_list = [f.zcr for f in features_list]
            energy_list = [f.energy for f in features_list]
            voice_ratio_list = [f.voice_band_ratio for f in features_list]
            dominant_freq_list = [f.dominant_freq for f in features_list]

            if NUMPY_AVAILABLE:
                report.append(f"  过零率 (ZCR):")
                report.append(f"    范围: {min(zcr_list):.4f} - {max(zcr_list):.4f}")
                report.append(f"    平均: {np.mean(zcr_list):.4f} ± {np.std(zcr_list):.4f}")

                report.append(f"  能量 (RMS):")
                report.append(f"    范围: {min(energy_list):.6f} - {max(energy_list):.6f}")
                report.append(f"    平均: {np.mean(energy_list):.6f} ± {np.std(energy_list):.6f}")

                report.append(f"  人声频段占比:")
                report.append(f"    范围: {min(voice_ratio_list):.4f} - {max(voice_ratio_list):.4f}")
                report.append(f"    平均: {np.mean(voice_ratio_list):.4f} ± {np.std(voice_ratio_list):.4f}")

                report.append(f"  主频率:")
                report.append(f"    范围: {min(dominant_freq_list):.1f} - {max(dominant_freq_list):.1f} Hz")
                report.append(f"    平均: {np.mean(dominant_freq_list):.1f} ± {np.std(dominant_freq_list):.1f} Hz")

            report.append("")

            # 详细样本列表
            report.append("  样本详情:")
            for i, f in enumerate(features_list[:5]):  # 只显示前5个
                report.append(f"    [{i+1}] {f.filename}")
                report.append(f"        ZCR={f.zcr:.4f}, Energy={f.energy:.4f}, "
                            f"Voice={f.voice_band_ratio:.2%}, Freq={f.dominant_freq:.0f}Hz")

            if len(features_list) > 5:
                report.append(f"    ... 还有 {len(features_list) - 5} 个样本")

            report.append("")

        report.append("=" * 80)

        # 分类建议
        report.append("【分析建议】")
        report.append("-" * 60)

        if 'motor' in results and results['motor']:
            motor_zcr = np.mean([f.zcr for f in results['motor']])
            report.append(f"电机噪音 ZCR 范围: {motor_zcr:.4f}")

        if 'wheel_noise' in results and results['wheel_noise']:
            wheel_zcr = np.mean([f.zcr for f in results['wheel_noise']])
            report.append(f"麦克纳姆轮噪音 ZCR 范围: {wheel_zcr:.4f}")

        if 'speech' in results and results['speech']:
            speech_zcr = np.mean([f.zcr for f in results['speech']])
            speech_voice = np.mean([f.voice_band_ratio for f in results['speech']])
            report.append(f"人声 ZCR 范围: {speech_zcr:.4f}")
            report.append(f"人声频段占比: {speech_voice:.2%}")

        report.append("")
        report.append("根据这些特征，可以调整 math_voice_detector.py 中的阈值参数。")
        report.append("=" * 80)

        return "\n".join(report)

    def save_results(self, results: Dict[str, List[AudioFeatures]], output_file: str):
        """保存分析结果到 JSON"""
        data = {}
        for sample_type, features_list in results.items():
            data[sample_type] = [
                {
                    'filename': f.filename,
                    'duration': f.duration,
                    'zcr': f.zcr,
                    'energy': f.energy,
                    'voice_band_ratio': f.voice_band_ratio,
                    'dominant_freq': f.dominant_freq,
                    'spectral_centroid': f.spectral_centroid
                }
                for f in features_list
            ]

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self.logger.info(f"分析结果已保存到: {output_file}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python audio_sample_analyzer.py <样本目录>")
        print("示例: python audio_sample_analyzer.py data/audio_samples")
        sys.exit(1)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    sample_dir = sys.argv[1]

    if not os.path.exists(sample_dir):
        print(f"错误: 目录不存在: {sample_dir}")
        sys.exit(1)

    analyzer = AudioSampleAnalyzer(sample_dir)

    print(f"\n正在分析样本目录: {sample_dir}")
    print("这可能需要几分钟...\n")

    results = analyzer.analyze_all()

    if not results:
        print("未找到任何音频样本")
        sys.exit(0)

    # 打印报告
    report = analyzer.generate_report(results)
    print(report)

    # 保存结果
    output_file = os.path.join(sample_dir, 'analysis_results.json')
    analyzer.save_results(results, output_file)
