# -*- coding: utf-8 -*-
import re
import time
import threading
from queue import Queue
from app.services.core import MotorControl
from app.config import (
    DISTANCE_DETECTION_THRESHOLD, DISTANCE_MONITOR_INTERVAL, COMMAND_EXECUTION_INTERVAL
)


class CommandExecutor:
    """
    负责接收并执行来自前端的精确命令。
    不处理语音识别或正则表达式解析。
    """

    def __init__(self, motor_control: MotorControl):
        self.control = motor_control
        self.command_queue = Queue()
        self._running = True  # 控制命令执行和距离监控线程的生命周期
        self._distance_monitor_thread = None
        self._command_executor_thread = None

    def start_threads(self):
        """启动命令执行和距离监控线程"""
        if not self._command_executor_thread or not self._command_executor_thread.is_alive():
            self._command_executor_thread = threading.Thread(target=self._execute_commands_loop, daemon=True)
            self._command_executor_thread.start()
            print("命令执行模块已启动")

        if not self._distance_monitor_thread or not self._distance_monitor_thread.is_alive():
            self._distance_monitor_thread = threading.Thread(target=self._distance_monitor_loop, daemon=True)
            self._distance_monitor_thread.start()
            print("距离检测模块已启动")

    def stop_threads(self):
        """停止所有后台线程"""
        self._running = False
        # 清空队列，防止线程阻塞
        with self.command_queue.mutex:
            self.command_queue.queue.clear()
        self.command_queue.put(None)  # 发送哨兵值，解除execute_commands_loop的阻塞

        if self._command_executor_thread and self._command_executor_thread.is_alive():
            self._command_executor_thread.join(timeout=1)
            print("命令执行模块已停止")
        if self._distance_monitor_thread and self._distance_monitor_thread.is_alive():
            self._distance_monitor_thread.join(timeout=1)
            print("距离检测模块已停止")
        self.control.stop()  # 确保停止所有电机
        self.control.cleanup()  # 清理GPIO

    def add_command(self, command: str):
        """将命令添加到队列"""
        self.command_queue.put(command)
        print(f"命令 '{command}' 已加入队列")

    def _execute_commands_loop(self):
        """命令执行循环"""
        while self._running:
            cmd = self.command_queue.get()
            if cmd is None:  # 哨兵值，用于停止线程
                break
            print(f"正在执行命令: {cmd}")
            # 根据命令字符串调用 MotorControl 相应方法
            try:
                # 禁用距离检测，以免在转弯或平移时误触停止
                if cmd in ["turn_left", "turn_right", "move_left", "move_right", "move_left_forward",
                           "move_right_forward", "move_left_back", "move_right_back"]:
                    self.control.distance_detection_enabled = False
                    getattr(self.control, cmd)()
                    time.sleep(COMMAND_EXECUTION_INTERVAL)  # 适当的执行时间
                    self.control.stop()  # 停止当前运动，以便执行下一个命令或防止一直转
                    self.control.distance_detection_enabled = True  # 重新开启
                elif cmd == "stop":
                    self.control.stop()
                    self.control.distance_detection_enabled = True  # 停止后确保检测开启
                else:
                    getattr(self.control, cmd)()  # 直接调用如 forward, back 等方法
                    # 对于持续运动的命令，可以不立即停止，或者设置一个短时间间隔
                    time.sleep(COMMAND_EXECUTION_INTERVAL)
            except AttributeError:
                print(f"错误: 不支持的命令 '{cmd}'")
            except Exception as e:
                print(f"执行命令 '{cmd}' 时发生错误: {e}")
            finally:
                self.command_queue.task_done()
                # 确保在执行完命令后，如果不是stop，也给一个短暂停顿，防止快速切换命令导致抖动
                # if cmd != "stop":
                #     time.sleep(0.01) # 微小延迟，避免CPU空转，同时给GPIO一个缓冲

    def _distance_monitor_loop(self):
        """距离监控循环"""
        while self._running:
            dist = self.control.measure_distance()
            if dist is not None and dist != -1:  # -1 表示测量失败
                print(f"距离: {dist}cm")
                if 0 < dist < DISTANCE_DETECTION_THRESHOLD:
                    print(f"检测到障碍物 ({dist}cm < {DISTANCE_DETECTION_THRESHOLD}cm), 发送停止命令!")
                    self.command_queue.put("stop")  # 强制停止
            time.sleep(DISTANCE_MONITOR_INTERVAL)  # 按照配置间隔检测


class VoiceCommandParser:
    """
    负责解析语音文本到精确命令。
    可以根据需要扩展复杂的自然语言处理。
    """

    def __init__(self):
        self.patterns = {
            "forward": ['前进', '向前走'],
            "back": ['后退', '退后', '往后'],
            "move_left": ['左平移', '向左平移', '左移'],
            "move_right": ['右平移', '向右平移', '右移'],
            "turn_left": ['左转', '原地左转'],
            "turn_right": ['右转', '原地右转'],
            "move_left_forward": ['左前', '左前斜向'],
            "move_right_forward": ['右前', '右前斜向'],
            "move_left_back": ['左后', '左后斜向'],
            "move_right_back": ['右后', '右后斜向'],
            "stop": ['停止', '停', '暂停', '别动'],
            # "faster": ['加速', '快一点'], # 如果需要，在MotorControl中实现对应的逻辑
            # "lower": ['减速', '慢一点'],
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


if __name__ == "__main__":
    # 仅作为测试 CommandExecutor 和 VoiceCommandParser
    # 在实际应用中，MotorControl 实例应是唯一的
    with MotorControl() as mc_test:
        executor = CommandExecutor(mc_test)
        parser = VoiceCommandParser()
        executor.start_threads()  # 启动执行和监控线程

        test_voice_texts = [
            "小车前进", "请停止", "向左平移", "原地右转", "左前", "别动", "右后"
        ]

        for text in test_voice_texts:
            print(f"\n模拟语音输入: '{text}'")
            parsed_cmd = parser.parse(text)
            if parsed_cmd:
                executor.add_command(parsed_cmd)
            time.sleep(0.5)  # 给一点时间让命令执行

        # 等待所有命令执行完毕（可选）
        executor.command_queue.join()
        print("\n所有模拟命令执行完毕。")

        # 模拟距离检测触发停止
        print("\n模拟触发距离检测停止...")
        mc_test.distance_detection_enabled = True  # 确保检测开启
        # 假设距离检测模块会自动put "stop"
        time.sleep(2)  # 等待距离检测线程发挥作用

        executor.stop_threads()
        print("程序退出。")
