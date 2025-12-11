# -*- coding: utf-8 -*-
import re
import time
import threading
import asyncio
from concurrent.futures import ThreadPoolExecutor
# from queue import Queue, Empty  # 导入 Empty 异常
from app.services.core import MotorControl
from app.config import (
    DISTANCE_DETECTION_THRESHOLD, DISTANCE_MONITOR_INTERVAL, COMMAND_EXECUTION_INTERVAL, DISTANCE_MONITOR_INTERVAL,
    OBSTACLE_BASE_DISTANCE, OBSTACLE_SPEED_FACTOR
)
import logging


class CommandExecutor:
    """
    负责接收并执行来自前端的精确命令。
    不处理语音识别或正则表达式解析。
    """

    def __init__(self, motor_control: MotorControl, logger: logging.Logger):
        self.control = motor_control
        self.logger = logger
        self.command_queue = asyncio.Queue()
        self._running = False  # 控制命令执行和距离监控线程的生命周期

        self._command_task = None
        self._monitor_task = None

        # --- 新增：距离检测宽限期相关属性 ---
        self._distance_monitor_grace_period_active = False  # 标记宽限期是否激活
        self._distance_monitor_grace_period_end_time = 0.0  # 宽限期结束时间戳
        self.GRACE_PERIOD_DURATION = 2.0  # 宽限期持续时长（秒），例如 2 秒足够小车后退一段距离

        # 专用线程池用于运行阻塞的 GPIO 测距
        self._executor = ThreadPoolExecutor(max_workers=1)

    async def start_tasks(self):
        """启动命令执行和距离监控线程"""
        self._running = True
        if self._command_task is None or self._command_task.done():
            self._command_task = asyncio.create_task(self._execute_commands_loop())
            # self._command_executor_thread = threading.Thread(target=self._execute_commands_loop, daemon=True)
            # self._command_executor_thread.start()
            self.logger.info("异步命令执行模块已启动")

        if self._monitor_task is None or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(self._distance_monitor_loop())
            self.logger.info("异步距离检测模块已启动")

    async def stop_tasks(self):
        """停止所有后台线程"""
        self._running = False
        # 清空队列，防止线程阻塞
        await self.command_queue.put(None)
        if self._command_task:
            try:
                await asyncio.wait_for(self._command_task, timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        self.control.stop()
        self.control.cleanup()
        self._executor.shutdown(wait=False)
        self.logger.info("所有后台任务已停止，GPIO 已清理。")

    async def add_command(self, command: str):
        """将命令添加到队列"""
        if command == "stop":
            # 清空队列：asyncio queue 没有 clear 方法，需要手动排空
            while not self.command_queue.empty():
                try:
                    self.command_queue.get_nowait()
                    self.command_queue.task_done()
                except asyncio.QueueEmpty:
                    break

            await self.command_queue.put("stop")
            self.logger.info("收到停止命令，已清除队列并排队停止。")
            self._distance_monitor_grace_period_active = False

        elif command == "move_back":
            self._distance_monitor_grace_period_active = True
            self._distance_monitor_grace_period_end_time = time.time() + self.GRACE_PERIOD_DURATION
            self.logger.info(f"开启距离检测宽限期 {self.GRACE_PERIOD_DURATION}s")
            await self.command_queue.put(command)
        else:
            await self.command_queue.put(command)
            self.logger.debug(f"命令 '{command}' 已加入队列")

    async def _execute_commands_loop(self):
        """命令执行循环"""
        while self._running:
            try:
                # 等待命令
                cmd = await self.command_queue.get()

                if cmd is None:  # 停止信号
                    self.command_queue.task_done()
                    break

                self.logger.info(f"执行: {cmd}")

                if cmd in ["turn_left", "turn_right"]:
                    self.control.distance_detection_enabled = False
                    # 使用 getattr 获取同步方法，直接调用（因为只是 GPIO 电平切换，非常快）
                    getattr(self.control, cmd)()
                    # 关键优化：使用非阻塞 sleep
                    await asyncio.sleep(1)
                    self.control.stop()
                    self.control.distance_detection_enabled = True

                elif cmd == "stop":
                    self.control.stop()
                    self.control.distance_detection_enabled = True
                else:
                    if hasattr(self.control, cmd):
                        getattr(self.control, cmd)()
                    else:
                        self.logger.error(f"未知命令: {cmd}")

                self.command_queue.task_done()

            except Exception as e:
                self.logger.error(f"命令执行错误: {e}")
                await asyncio.sleep(0.1)

    async def _distance_monitor_loop(self):
        """距离监控循环"""
        loop = asyncio.get_running_loop()

        while self._running:
            # 宽限期检查
            if self._distance_monitor_grace_period_active:
                if time.time() < self._distance_monitor_grace_period_end_time:
                    await asyncio.sleep(DISTANCE_MONITOR_INTERVAL)
                    continue
                else:
                    self._distance_monitor_grace_period_active = False
                    self.logger.info("宽限期结束")

            try:
                # 关键优化：将阻塞的 measure_distance 放入线程池运行
                # 这样不会卡死 Web 服务
                dist = await loop.run_in_executor(self._executor, self.control.measure_distance)

                if dist is not None and dist != -1:
                    # 计算动态阈值
                    current_speed = self.control.get_speed()
                    # 公式：动态阈值 = 10cm + (速度 * 0.4)
                    dynamic_threshold = OBSTACLE_BASE_DISTANCE + (current_speed * OBSTACLE_SPEED_FACTOR)

                    if 0 < dist < dynamic_threshold:
                        self.logger.warning(
                            f"障碍物 {dist}cm < 动态阈值 {dynamic_threshold:.1f}cm (速度:{current_speed})! 紧急停车!")
                        await self.add_command("stop")
            except Exception as e:
                self.logger.error(f"测距错误: {e}")

            await asyncio.sleep(DISTANCE_MONITOR_INTERVAL)


class VoiceCommandParser:
    """
    负责解析语音文本到精确命令。
    可以根据需要扩展复杂的自然语言处理。
    """

    def __init__(self):
        self.patterns = {
            "move_forward": ['前进', '向前走'],
            "move_back": ['后退', '退后', '往后'],
            "move_left": ['左平移', '向左平移', '左移'],
            "move_right": ['右平移', '向右平移', '右移'],
            "turn_left": ['左转', '原地左转'],
            "turn_right": ['右转', '原地右转'],
            "move_left_forward": ['左前', '左前斜向'],
            "move_right_forward": ['右前', '右前斜向'],
            "move_left_back": ['左后', '左后斜向'],
            "move_right_back": ['右后', '右后斜向'],
            "stop": ['停止', '停', '暂停', '别动'],
            "SYSTEM_SWITCH_SMART": ['切换智能模式', '进入智能模式', '变身', '打开大脑'],
            "SYSTEM_SWITCH_NORMAL": ['退出智能模式', '关闭大脑', '变回普通模式', '指令模式']
        }
        self.compiled_patterns = {cmd: re.compile("|".join(self.patterns[cmd])) for cmd in self.patterns}

    def parse(self, text: str):
        """从文本中解析出命令"""
        text = text.lower().strip()
        if not text:
            return None
        for cmd, pattern in self.compiled_patterns.items():
            if pattern.search(text):
                print(f"语音检测到命令: {cmd}")
                return cmd
        return None


# `if __name__ == "__main__":` 块保持不变或根据您的测试需求进行调整
# 需要导入 sys
import sys

if __name__ == "__main__":
    test_logger = logging.getLogger("test_logger")
    test_logger.setLevel(logging.INFO)
    test_logger.addHandler(logging.StreamHandler(sys.stdout))

    with MotorControl() as mc_test:
        executor = CommandExecutor(mc_test, test_logger)
        parser = VoiceCommandParser()
        executor.start_threads()

        print("\n--- 模拟手动命令 ---")
        executor.add_command("move_forward")
        time.sleep(0.5)
        executor.add_command("stop")
        time.sleep(1)
        executor.add_command("turn_left")  # Turn for 1 second
        time.sleep(1.5)  # Wait for turn to complete and stop

        print("\n--- 模拟语音命令 ---")
        test_voice_texts = [
            "小车前进", "请停止", "向左平移", "原地右转", "左前", "别动", "右后"
        ]

        for text in test_voice_texts:
            print(f"\n模拟语音输入: '{text}'")
            parsed_cmd = parser.parse(text)
            if parsed_cmd:
                executor.add_command(parsed_cmd)
            time.sleep(0.5)

        executor.command_queue.join()
        test_logger.info("\n所有模拟命令执行完毕。")

        test_logger.info("\n模拟触发距离检测停止...")
        # 模拟距离检测，假设 MotorControl 会调用 add_command("stop")
        mc_test.distance_detection_enabled = True
        # 这里无法直接模拟 MotorControl 内部的 distance_monitor_loop，
        # 只是示意当它检测到时会调用 add_command("stop")
        # 实际测试需要真实传感器触发
        time.sleep(2)  # 留出时间让距离监控线程运行

        executor.stop_threads()
        test_logger.info("程序退出。")
