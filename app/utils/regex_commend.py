import random
import sys
import time
from pathlib import Path

# 获取当前脚本所在的目录，并向上一级找到项目的根目录
project_root = str(Path(__file__).resolve().parents[2])
sys.path.append(project_root)

import re
from app.services.core import MotorControl, FORWARD, BACK, STOP
from queue import Queue


class CommandHandler:
    FORWARD = "forward"
    LEFT = "left"
    RIGHT = "right"
    BACK = "back"
    FASTER = "faster"
    LOWER = "lower"
    STOP = "stop"
    TURNING = "turning"

    START = 1  # 标志某个动作开始执行
    END = 2  # 标志某个动作执行完成

    def __init__(self):
        self.patterns = {
            self.FORWARD: ['前进', '向前'],
            self.LEFT: ['左转', '向左'],
            self.RIGHT: ['右转', '向右'],
            self.BACK: ['后退', '退后', '撤退'],
            self.FASTER: ['加速', '快一点'],
            self.LOWER: ['减速', '慢一点'],
            self.STOP: ['暂停', '停止', '停'],

        }
        self.control = MotorControl()
        self.compiled_patterns = {cmd: re.compile("|".join(self.patterns[cmd])) for cmd in self.patterns}
        self.command_queue = Queue()
        self.running = 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.control.cleanup()

    def handle_text(self, text):
        for cmd, pattern in self.compiled_patterns.items():
            if pattern.search(text):
                print(f"Detected command: {cmd}")
                self.command_queue.put(cmd)
                break

    def execute_commands(self):
        print("开启命令执行模块")
        while True:
            if not self.running:
                continue
            cmd = self.command_queue.get()
            method = getattr(self, cmd)
            if method:
                method()
            self.command_queue.task_done()

    def distince_monitor(self):
        print("开启距离检测模块")
        while True:
            time.sleep(0.05)
            distince = self.control.measure_distance()
            if distince is None:
                continue
            print(f"distince: {distince}cm")
            if 0 < distince < 20:
                # cmd = random.choice([self.LEFT, self.RIGHT])
                # print(f"发送命令: {cmd}")
                # self.command_queue.put(cmd)
                self.command_queue.put("stop")

    def turn_off(self):
        self.running = 0
        self.stop()

    def stop(self):
        self.control.stop()

    def forward(self):
        self.control.move_forward()

    def move_left(self):
        self.control.move_left()

    def move_right(self):
        self.control.move_right()

    def left(self):
        self.control.distance_detection = 0
        self.control.turn_left()
        self.control.distance_detection = 1
        # self.forward()

    def right(self):
        self.control.distance_detection = 0
        self.control.turn_right()
        self.control.distance_detection = 1
        # self.forward()

    def back(self):
        self.control.move_back()

    def faster(self):
        print("Executing faster()")
        # 在这里添加实际执行faster()函数的代码

    def lower(self):
        print("Executing lower()")
        # 在这里添加实际执行lower()函数的代码


# 使用示例
if __name__ == "__main__":
    handler = CommandHandler()
    test_texts = ["让我们向前移动", "请减速", "向左转", "加速前进", "需要后退"]
    for text in test_texts:
        print(f"Handling command: {text}")
        handler.handle_text(text)
