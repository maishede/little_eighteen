# -*- coding: utf-8 -*-
import re
import time
import threading
from queue import Queue, Empty  # 导入 Empty 异常
from app.services.core import MotorControl
from app.config import (
    DISTANCE_DETECTION_THRESHOLD, DISTANCE_MONITOR_INTERVAL, COMMAND_EXECUTION_INTERVAL
)
import logging


class CommandExecutor:
    """
    负责接收并执行来自前端的精确命令。
    不处理语音识别或正则表达式解析。
    """

    def __init__(self, motor_control: MotorControl, logger: logging.Logger):
        self.control = motor_control
        self.command_queue = Queue()
        self._running = True  # 控制命令执行和距离监控线程的生命周期
        self._distance_monitor_thread = None
        self._command_executor_thread = None
        self.logger = logger

        # --- 新增：距离检测宽限期相关属性 ---
        self._distance_monitor_grace_period_active = False  # 标记宽限期是否激活
        self._distance_monitor_grace_period_end_time = 0.0  # 宽限期结束时间戳
        self.GRACE_PERIOD_DURATION = 2.0  # 宽限期持续时长（秒），例如 2 秒足够小车后退一段距离

    def start_threads(self):
        """启动命令执行和距离监控线程"""
        if not self._command_executor_thread or not self._command_executor_thread.is_alive():
            self._command_executor_thread = threading.Thread(target=self._execute_commands_loop, daemon=True)
            self._command_executor_thread.start()
            self.logger.info("命令执行模块已启动")

        if not self._distance_monitor_thread or not self._distance_monitor_thread.is_alive():
            self._distance_monitor_thread = threading.Thread(target=self._distance_monitor_loop, daemon=True)
            self._distance_monitor_thread.start()
            self.logger.info("距离检测模块已启动")

    def stop_threads(self):
        """停止所有后台线程"""
        self._running = False
        # 清空队列，防止线程阻塞
        with self.command_queue.mutex:
            self.command_queue.queue.clear()
        self.command_queue.put(None)  # 发送哨兵值，解除execute_commands_loop的阻塞

        if self._command_executor_thread and self._command_executor_thread.is_alive():
            self._command_executor_thread.join(timeout=1)
            self.logger.info("命令执行模块已停止")
        if self._distance_monitor_thread and self._distance_monitor_thread.is_alive():
            self._distance_monitor_thread.join(timeout=1)
            self.logger.info("距离检测模块已停止")
        self.control.stop()  # 确保停止所有电机
        self.control.cleanup()  # 清理GPIO
        self.logger.info("GPIO 清理完毕。")

    def add_command(self, command: str):
        """将命令添加到队列"""
        if command == "stop":
            with self.command_queue.mutex:
                self.command_queue.queue.clear()  # 清空所有等待中的命令
            self.command_queue.put("stop")  # 只添加停止命令
            self.logger.info("收到停止命令，已清除队列并立即执行停止。")
            # 如果是主动停止，也应清除宽限期，允许立即重新开始距离检测
            self._distance_monitor_grace_period_active = False
        elif command == "move_back":
            # 当收到后退命令时，启动一个宽限期，以便小车能够完成避障动作
            self._distance_monitor_grace_period_active = True
            self._distance_monitor_grace_period_end_time = time.time() + self.GRACE_PERIOD_DURATION
            self.logger.info(f"开启距离检测宽限期，持续 {self.GRACE_PERIOD_DURATION} 秒，应对后退命令。")
            self.command_queue.put(command)
            self.logger.info(f"命令 '{command}' 已加入队列")
        else:
            # 对于其他命令，直接添加到队列末尾
            self.command_queue.put(command)
            self.logger.info(f"命令 '{command}' 已加入队列")

    def _execute_commands_loop(self):
        """命令执行循环"""
        while self._running:
            try:
                cmd = self.command_queue.get(timeout=0.1)  # 增加 timeout 防止在停止时阻塞
            except Empty:
                continue  # 队列为空，继续循环检查运行状态

            if cmd is None:  # 哨兵值，用于停止线程
                break
            self.logger.info(f"正在执行命令: {cmd}")
            try:
                # 针对原地转向命令，特殊处理执行时间
                if cmd in ["turn_left", "turn_right"]:
                    self.control.distance_detection_enabled = False  # 转向时禁用距离检测
                    getattr(self.control, cmd)()
                    time.sleep(1)  # 转向命令执行1秒
                    self.control.stop()  # 转向后停止
                    self.control.distance_detection_enabled = True  # 重新启用距离检测
                elif cmd == "stop":
                    self.control.stop()
                    self.control.distance_detection_enabled = True  # 停止时确保距离检测启用
                else:  # 其他所有运动命令（前进、后退、平移、斜向移动等）
                    getattr(self.control, cmd)()
            except AttributeError:
                self.logger.error(f"错误: 不支持的命令 '{cmd}'")
            except Exception as e:
                self.logger.error(f"执行命令 '{cmd}' 时发生错误: {e}")
            finally:
                self.command_queue.task_done()

    def _distance_monitor_loop(self):
        """距离监控循环"""
        while self._running:
            # --- 新增：检查距离检测宽限期 ---
            if self._distance_monitor_grace_period_active:
                if time.time() < self._distance_monitor_grace_period_end_time:
                    # 如果仍在宽限期内，则跳过距离检测和停止命令发送
                    time.sleep(DISTANCE_MONITOR_INTERVAL)
                    continue  # 跳过当前循环的其余部分，进入下一次迭代
                else:
                    # 宽限期已结束，关闭宽限期标志
                    self._distance_monitor_grace_period_active = False
                    self.logger.info("距离检测宽限期结束，恢复正常检测。")

            dist = self.control.measure_distance()
            if dist is not None and dist != -1:
                # print(f"距离: {dist}cm") # 保持原有的打印方式
                if 0 < dist < DISTANCE_DETECTION_THRESHOLD:
                    self.logger.warning(f"检测到障碍物 ({dist}cm < {DISTANCE_DETECTION_THRESHOLD}cm), 发送停止命令!")
                    self.add_command("stop")  # 调用自身的 add_command，它会清空队列并添加停止
            time.sleep(DISTANCE_MONITOR_INTERVAL)


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
        }
        self.compiled_patterns = {cmd: re.compile("|".join(self.patterns[cmd])) for cmd in self.patterns}

    def parse(self, text: str) -> str | None:
        """从文本中解析出命令"""
        text = text.lower().strip()
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
