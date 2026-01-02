# -*- coding: utf-8 -*-
"""
智能音频采样系统

基于事件触发的音频采样，避免持续录音的资源消耗。
采样策略：
1. 触发式采样：仅在特定事件（小车运动、语音命令）时采样
2. 短时录音：每次只录制 1-3 秒的音频片段
3. 分类存储：按类别存储到不同目录
4. 循环缓冲：限制每个类别的样本数量
"""
import os
import time
import json
import wave
import logging
from datetime import datetime
from typing import Optional, Literal
from collections import defaultdict
from threading import Lock
from dataclasses import dataclass, asdict

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    np = None
    NUMPY_AVAILABLE = False


@dataclass
class SampleMetadata:
    """样本元数据"""
    timestamp: str
    sample_type: str  # motor, wheel_noise, speech, mixed, background
    duration: float
    command: Optional[str] = None  # 触发的命令
    speed: Optional[int] = None  # 当前速度
    distance: Optional[float] = None  # 当前测距值
    notes: str = ""


class AudioSampler:
    """
    智能音频采样器

    使用方式：
    1. 运动时采样：小车开始运动时自动采样环境音+运动音
    2. 语音时采样：检测到语音命令时采样
    3. 手动采样：通过 API 手动触发采样
    """

    # 采样类别
    TYPE_MOTOR = "motor"  # 纯电机噪音（原地转动）
    TYPE_WHEEL = "wheel_noise"  # 麦克纳姆轮移动噪音
    TYPE_SPEECH = "speech"  # 人声（静止状态）
    TYPE_MIXED = "mixed"  # 混合音（运动中说话）
    TYPE_BACKGROUND = "background"  # 背景噪音

    def __init__(
        self,
        sample_dir: str = None,
        max_samples_per_type: int = 20,
        sample_duration: float = 2.0,
        sample_rate: int = 16000,
        logger: Optional[logging.Logger] = None
    ):
        """
        初始化采样器

        Args:
            sample_dir: 样本存储目录
            max_samples_per_type: 每种类别最大样本数（超出后删除最旧的）
            sample_duration: 每次采样时长（秒）
            sample_rate: 采样率 Hz
        """
        self.logger = logger or logging.getLogger(__name__)
        self.sample_dir = sample_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'data', 'audio_samples'
        )
        self.max_samples_per_type = max_samples_per_type
        self.sample_duration = sample_duration
        self.sample_rate = sample_rate
        self._lock = Lock()

        # 确保目录存在
        os.makedirs(self.sample_dir, exist_ok=True)
        for sample_type in [self.TYPE_MOTOR, self.TYPE_WHEEL, self.TYPE_SPEECH,
                           self.TYPE_MIXED, self.TYPE_BACKGROUND]:
            os.makedirs(os.path.join(self.sample_dir, sample_type), exist_ok=True)

        # 采样状态
        self._is_sampling = False
        self._recorder = None

        # 元数据索引
        self._metadata_file = os.path.join(self.sample_dir, 'metadata.json')
        self._metadata = self._load_metadata()

        self.logger.info(f"音频采样器初始化完成")
        self.logger.info(f"  采样目录: {self.sample_dir}")
        self.logger.info(f"  每类最大样本数: {max_samples_per_type}")
        self.logger.info(f"  采样时长: {sample_duration}秒")
        self._log_sample_counts()

    def _load_metadata(self) -> dict:
        """加载元数据索引"""
        try:
            if os.path.exists(self._metadata_file):
                with open(self._metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            self.logger.warning(f"加载元数据失败: {e}")
        return defaultdict(list)

    def _save_metadata(self):
        """保存元数据索引"""
        try:
            with open(self._metadata_file, 'w', encoding='utf-8') as f:
                json.dump(dict(self._metadata), f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"保存元数据失败: {e}")

    def _log_sample_counts(self):
        """记录当前样本统计"""
        counts = {}
        for sample_type in [self.TYPE_MOTOR, self.TYPE_WHEEL, self.TYPE_SPEECH,
                           self.TYPE_MIXED, self.TYPE_BACKGROUND]:
            type_dir = os.path.join(self.sample_dir, sample_type)
            if os.path.exists(type_dir):
                counts[sample_type] = len([f for f in os.listdir(type_dir)
                                         if f.endswith('.wav')])
        self.logger.info(f"当前样本统计: {counts}")

    def _get_next_filename(self, sample_type: str) -> str:
        """获取下一个可用的文件名"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
        return os.path.join(self.sample_dir, sample_type, f"{timestamp}.wav")

    def _cleanup_old_samples(self, sample_type: str):
        """清理最旧的样本（超出限制时）"""
        type_dir = os.path.join(self.sample_dir, sample_type)
        if not os.path.exists(type_dir):
            return

        files = sorted([f for f in os.listdir(type_dir) if f.endswith('.wav')])

        while len(files) > self.max_samples_per_type:
            oldest = files.pop(0)
            oldest_path = os.path.join(type_dir, oldest)

            # 删除音频文件
            try:
                os.remove(oldest_path)
                self.logger.debug(f"删除旧样本: {oldest}")

                # 从元数据中移除
                if sample_type in self._metadata:
                    self._metadata[sample_type] = [
                        m for m in self._metadata[sample_type]
                        if m.get('filename') != oldest
                    ]
            except Exception as e:
                self.logger.error(f"删除样本失败: {e}")

        self._save_metadata()

    def _save_audio(self, audio_data: list, filename: str):
        """
        保存音频到 WAV 文件

        Args:
            audio_data: PCM 音频数据（int16 列表）
            filename: 目标文件路径
        """
        try:
            with wave.open(filename, 'wb') as wf:
                wf.setnchannels(1)  # 单声道
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(self.sample_rate)
                wf.writeframes(bytes(audio_data))
            return True
        except Exception as e:
            self.logger.error(f"保存音频失败: {e}")
            return False

    def record_sample(
        self,
        audio_data: list,
        sample_type: str,
        command: Optional[str] = None,
        speed: Optional[int] = None,
        distance: Optional[float] = None,
        notes: str = ""
    ) -> Optional[str]:
        """
        录制并保存一个音频样本

        Args:
            audio_data: PCM 音频数据（int16 列表）
            sample_type: 样本类型
            command: 触发的命令（如果有）
            speed: 当前速度（如果有）
            distance: 当前测距值（如果有）
            notes: 备注

        Returns:
            保存的文件路径，失败返回 None
        """
        with self._lock:
            # 验证样本类型
            valid_types = [self.TYPE_MOTOR, self.TYPE_WHEEL, self.TYPE_SPEECH,
                          self.TYPE_MIXED, self.TYPE_BACKGROUND]
            if sample_type not in valid_types:
                self.logger.error(f"无效的样本类型: {sample_type}")
                return None

            # 生成文件名
            filename = self._get_next_filename(sample_type)
            relative_filename = os.path.relpath(filename, self.sample_dir)

            # 保存音频
            duration = len(audio_data) / self.sample_rate
            if not self._save_audio(audio_data, filename):
                return None

            # 创建元数据
            metadata = SampleMetadata(
                timestamp=datetime.now().isoformat(),
                sample_type=sample_type,
                duration=duration,
                command=command,
                speed=speed,
                distance=distance,
                notes=notes
            )
            metadata_dict = asdict(metadata)
            metadata_dict['filename'] = relative_filename

            # 添加到索引
            if sample_type not in self._metadata:
                self._metadata[sample_type] = []
            self._metadata[sample_type].append(metadata_dict)

            # 清理旧样本
            self._cleanup_old_samples(sample_type)

            self._save_metadata()

            self.logger.info(
                f"样本已保存: {sample_type} ({duration:.2f}s) -> {relative_filename}"
            )
            return filename

    def get_statistics(self) -> dict:
        """获取采样统计信息"""
        stats = {
            'total_samples': 0,
            'by_type': {},
            'storage_size_mb': 0
        }

        for sample_type in [self.TYPE_MOTOR, self.TYPE_WHEEL, self.TYPE_SPEECH,
                           self.TYPE_MIXED, self.TYPE_BACKGROUND]:
            type_dir = os.path.join(self.sample_dir, sample_type)
            if os.path.exists(type_dir):
                files = [f for f in os.listdir(type_dir) if f.endswith('.wav')]
                stats['by_type'][sample_type] = len(files)
                stats['total_samples'] += len(files)

                # 计算存储大小
                for f in files:
                    stats['storage_size_mb'] += os.path.getsize(
                        os.path.join(type_dir, f)
                    ) / (1024 * 1024)

        stats['storage_size_mb'] = round(stats['storage_size_mb'], 2)
        return stats

    def clear_samples(self, sample_type: Optional[str] = None):
        """
        清空样本

        Args:
            sample_type: 要清空的类型，None 表示清空所有
        """
        with self._lock:
            if sample_type:
                types = [sample_type]
            else:
                types = [self.TYPE_MOTOR, self.TYPE_WHEEL, self.TYPE_SPEECH,
                        self.TYPE_MIXED, self.TYPE_BACKGROUND]

            for stype in types:
                type_dir = os.path.join(self.sample_dir, stype)
                if os.path.exists(type_dir):
                    for f in os.listdir(type_dir):
                        if f.endswith('.wav'):
                            try:
                                os.remove(os.path.join(type_dir, f))
                            except Exception as e:
                                self.logger.error(f"删除文件失败: {e}")
                    self._metadata[stype] = []

            self._save_metadata()
            self.logger.info(f"已清空样本: {sample_type or '全部'}")


class SamplingController:
    """
    采样控制器 - 集成到语音服务中

    负责根据事件自动触发采样
    """

    def __init__(
        self,
        sampler: AudioSampler,
        recorder=None,
        logger: Optional[logging.Logger] = None
    ):
        """
        初始化控制器

        Args:
            sampler: 音频采样器实例
            recorder: PvRecorder 实例（用于获取音频数据）
            logger: 日志记录器
        """
        self.sampler = sampler
        self.recorder = recorder
        self.logger = logger or logging.getLogger(__name__)

        # 状态跟踪
        self._is_moving = False
        self._last_command = None
        self._last_speed = 50

    def set_recorder(self, recorder):
        """设置录音器"""
        self.recorder = recorder

    def on_command_start(self, command: str, speed: int = None):
        """
        命令开始时触发采样

        Args:
            command: 执行的命令
            speed: 当前速度
        """
        if not self.recorder:
            return

        self._last_command = command
        if speed:
            self._last_speed = speed

        # 确定采样类型
        if command in ['turn_left', 'turn_right']:
            sample_type = AudioSampler.TYPE_MOTOR
            self._is_moving = True
        elif command in ['move_left', 'move_right']:
            sample_type = AudioSampler.TYPE_WHEEL
            self._is_moving = True
        elif command in ['move_forward', 'move_back',
                        'move_left_forward', 'move_right_forward',
                        'move_left_back', 'move_right_back']:
            sample_type = AudioSampler.TYPE_WHEEL
            self._is_moving = True
        else:
            return

        # 触发采样
        self._trigger_sample(sample_type, command, speed)

    def on_voice_detected(self, audio_data: list):
        """
        检测到语音时触发采样

        Args:
            audio_data: 音频数据
        """
        if self._is_moving:
            sample_type = AudioSampler.TYPE_MIXED
        else:
            sample_type = AudioSampler.TYPE_SPEECH

        self.sampler.record_sample(
            audio_data,
            sample_type,
            command=self._last_command,
            speed=self._last_speed,
            notes="语音检测触发"
        )

    def on_stop(self):
        """停止时重置状态"""
        self._is_moving = False
        self._last_command = None

    def _trigger_sample(self, sample_type: str, command: str, speed: int = None):
        """
        触发一次采样（在后台线程中执行）

        由于不能阻塞主线程，这个方法应该在单独的线程中调用
        """
        if not self.recorder:
            return

        try:
            # 采集指定时长的音频
            frames = int(self.sampler.sample_duration * self.sampler.sample_rate)
            audio_data = []

            # 使用 read() 读取音频
            start_time = time.time()
            while time.time() - start_time < self.sampler.sample_duration:
                pcm = self.recorder.read()
                audio_data.extend(pcm)

            # 保存样本
            self.sampler.record_sample(
                audio_data[:frames],
                sample_type,
                command=command,
                speed=speed,
                notes="命令触发采样"
            )

        except Exception as e:
            self.logger.error(f"采样失败: {e}")


if __name__ == "__main__":
    # 测试代码
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("\n音频采样系统测试")
    print("=" * 50)

    sampler = AudioSampler(
        max_samples_per_type=5,
        sample_duration=2.0
    )

    print("\n当前统计:")
    stats = sampler.get_statistics()
    print(json.dumps(stats, indent=2, ensure_ascii=False))

    # 模拟采样（生成随机数据）
    if NUMPY_AVAILABLE:
        print("\n模拟采样...")
        for i in range(3):
            # 生成随机音频数据
            audio = np.random.randint(-1000, 1000, size=int(2.0 * 16000), dtype=np.int16)
            audio_list = audio.tolist()

            sampler.record_sample(
                audio_list,
                AudioSampler.TYPE_WHEEL,
                command=f"move_right",
                speed=50,
                notes=f"测试样本 {i+1}"
            )

    print("\n更新后统计:")
    stats = sampler.get_statistics()
    print(json.dumps(stats, indent=2, ensure_ascii=False))

    print("\n样本目录结构:")
    for root, dirs, files in os.walk(sampler.sample_dir):
        level = root.replace(sampler.sample_dir, '').count(os.sep)
        indent = ' ' * 2 * level
        print(f'{indent}{os.path.basename(root)}/')
        subindent = ' ' * 2 * (level + 1)
        for file in files[:3]:  # 只显示前3个文件
            print(f'{subindent}{file}')
        if len(files) > 3:
            print(f'{subindent}... and {len(files) - 3} more')

    print("\n测试完成！")
