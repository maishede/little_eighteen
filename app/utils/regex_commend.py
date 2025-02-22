import sys
from pathlib import Path

# 获取当前脚本所在的目录，并向上一级找到项目的根目录
project_root = str(Path(__file__).resolve().parents[2])
sys.path.append(project_root)

import re
from app.services.core import MotorControl, FORWARD, BACK, STOP
from queue import Queue


class CommandHandler:
    def __init__(self):
        self.patterns = {
            'forward': ['前进', '向前'],
            'left': ['左转', '向左'],
            'right': ['右转', '向右'],
            'back': ['后退', '退后', '撤退'],
            'faster': ['加速', '快一点'],
            'lower': ['减速', '慢一点']
        }
        self.control = MotorControl()
        self.compiled_patterns = {cmd: re.compile("|".join(self.patterns[cmd])) for cmd in self.patterns}
        self.command_queue = Queue()

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
        while True:
            cmd = self.command_queue.get()
            method = getattr(self, cmd)
            if method:
                method()
            self.command_queue.task_done()

    def forward(self):
        self.control.move_forward()

    def left(self):
        self.control.turn_left_forward()

    def right(self):
        self.control.turn_right_forward()

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
