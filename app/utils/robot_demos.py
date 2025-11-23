# -*- coding: utf-8 -*-
import time
import threading
import logging
from queue import Empty
import asyncio
from app.utils.regex_command import CommandExecutor  # 导入 CommandExecutor


class RobotDemos:
    """
    负责执行各种预设的机器人演示功能。
    它通过 CommandExecutor 将命令添加到小车的执行队列。
    """

    def __init__(self, command_executor: CommandExecutor, logger: logging.Logger):
        self.executor = command_executor
        self.logger = logger
        self._demo_task = None
        self._stop_demo_event = asyncio.Event()  # 用于向演示线程发送停止信号

    async def start_demo(self, demo_name: str):
        """
        启动一个指定的演示功能。
        :param demo_name: 演示功能的名称 (对应 _run_xxx_demo 方法的 xxx 部分)
        :return: True if started, False otherwise
        """
        # if self._is_demo_running:
        #     self.logger.warning(f"演示功能 '{self._current_demo_name}' 正在运行，无法启动 '{demo_name}'。")
        #     return False
        #
        # demo_method_name = f"_run_{demo_name}_demo"
        # if not hasattr(self, demo_method_name) or not callable(getattr(self, demo_method_name)):
        #     self.logger.error(f"未找到演示功能或它不是一个可调用方法: {demo_name}")
        #     return False
        #
        # self._is_demo_running = True
        # self._current_demo_name = demo_name  # 记录当前运行的演示名称
        # self._stop_demo_event.clear()  # 启动新演示前清空停止事件
        #
        # self._current_demo_thread = threading.Thread(target=getattr(self, demo_method_name), daemon=True)
        # self._current_demo_thread.start()
        # self.logger.info(f"演示功能 '{demo_name}' 已启动。")
        # return True
        if self._demo_task and not self._demo_task.done():
            self.logger.warning(f"演示正在运行，无法启动 {demo_name}")
            return False

        method_name = f"_run_{demo_name}_demo"
        if not hasattr(self, method_name):
            self.logger.error(f"未找到演示: {demo_name}")
            return False

        self._stop_demo_event.clear()
        # 创建异步任务
        self._demo_task = asyncio.create_task(getattr(self, method_name)())
        self.logger.info(f"演示 '{demo_name}' 已启动。")
        return True

    async def stop_demo(self):
        """
        停止当前正在运行的演示功能。
        """
        # if self._is_demo_running:
        #     self.logger.info(f"停止演示功能 '{self._current_demo_name}'。")
        #     self._stop_demo_event.set()  # 发送停止信号给演示线程
        #     # 立即发送停止命令到 CommandExecutor 的队列，以中断当前小车动作
        #     self.executor.add_command("stop")  # CommandExecutor 自身的 add_command 会处理优先级
        #     if self._current_demo_thread and self._current_demo_thread.is_alive():
        #         self._current_demo_thread.join(timeout=2)  # 等待演示线程优雅地退出
        #     self._is_demo_running = False
        #     self._current_demo_name = None
        #     self.logger.info("演示功能已停止。")
        #     return True
        # self.logger.info("没有正在运行的演示功能。")
        # return False
        if self._demo_task and not self._demo_task.done():
            self.logger.info("正在停止演示...")
            self._stop_demo_event.set()  # 设置停止标志
            await self.executor.add_command("stop")

            try:
                # 等待任务取消或完成
                await asyncio.wait_for(self._demo_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

            self.logger.info("演示已停止。")
            return True
        return False

    async def _execute_demo_sequence(self, sequence):
        """
        通用辅助方法，用于执行一系列 (command, duration) 对组成的演示序列。
        在每个步骤中检查停止信号，确保演示可被中断。
        :param sequence: 包含 (command_string, duration_seconds) 元组的列表。
        """
        # for cmd, duration in sequence:
        #     # 检查是否有停止信号或主程序正在关闭
        #     if not self._is_demo_running or self._stop_demo_event.is_set():
        #         self.logger.info("演示序列被中断。")
        #         break
        #
        #     self.executor.add_command(cmd)  # 将命令加入到 CommandExecutor 的队列
        #
        #     # 等待当前命令执行指定时长，同时保持可中断性
        #     start_time = time.time()
        #     while time.time() - start_time < duration:
        #         if not self._is_demo_running or self._stop_demo_event.is_set():
        #             self.logger.info("演示序列等待期间被中断。")
        #             break
        #         # 检查 CommandExecutor 队列中是否有优先级更高的命令（如 stop）
        #         # 注意：直接访问 executor.command_queue.queue[0] 可能会有竞态条件或违反封装
        #         # 更好的方式是依赖 executor.add_command("stop") 自身的清除队列逻辑
        #         # 这里我们假设只要 self._stop_demo_event 被设置，就代表外部干预了
        #         time.sleep(0.05)  # 小休眠以避免忙等待，并允许其他线程运行
        #
        #     # 如果是因为中断而跳出循环，则不再继续执行后续命令
        #     if not self._is_demo_running or self._stop_demo_event.is_set():
        #         break
        #
        # # 确保演示结束时小车停止
        # self.executor.add_command("stop")
        # self._is_demo_running = False  # 演示完成，重置状态
        # self._stop_demo_event.clear()  # 重置停止事件
        for cmd, duration in sequence:
            if self._stop_demo_event.is_set():
                break

            await self.executor.add_command(cmd)

            # 使用 await sleep，支持中途打断
            try:
                # 将等待切分为小块，以便更快响应停止信号
                elapsed = 0
                step = 0.1
                while elapsed < duration:
                    if self._stop_demo_event.is_set():
                        break
                    await asyncio.sleep(step)
                    elapsed += step
            except asyncio.CancelledError:
                break

        await self.executor.add_command("stop")

    # --- 具体的演示功能实现 ---

    # --- 绘制数字 (横平竖直笔画) ---

    async def _run_digit_0_demo(self):
        # self.logger.info("正在执行数字 '0' 演示。")
        # # 假设小车从数字的“左下角”开始绘制
        # move_dist = 1.5  # 单笔画移动时长 (秒)
        # sequence = [
        #     ("move_forward", move_dist),  # 向上绘制左边
        #     ("move_right", move_dist),  # 向右绘制上边
        #     ("move_back", move_dist),  # 向下绘制右边
        #     ("move_left", move_dist),  # 向左绘制下边
        #     # 绘制完后，移动到下一个数字的起始位置或回到中心
        #     ("move_forward", move_dist / 2),  # 稍微向上移动，为下一个数字做准备
        # ]
        # self._execute_demo_sequence(sequence)
        # self.logger.info("数字 '0' 演示完成。")
        move_dist = 1.5
        sequence = [
            ("move_forward", move_dist),
            ("move_right", move_dist),
            ("move_back", move_dist),
            ("move_left", move_dist),
            ("move_forward", move_dist / 2),
        ]
        await self._execute_demo_sequence(sequence)

    async def _run_digit_1_demo(self):
        # self.logger.info("正在执行数字 '1' 演示。")
        # # 假设小车从数字的“底部中心”开始绘制
        # move_dist = 2.0  # 垂直笔画移动时长
        # sequence = [
        #     ("move_forward", move_dist),  # 向上绘制垂直笔画
        #     ("move_back", move_dist / 2),  # 回到数字中心高度
        # ]
        # self._execute_demo_sequence(sequence)
        # self.logger.info("数字 '1' 演示完成。")
        move_dist = 1.0
        sequence = [
            ("move_forward", move_dist),
            ("move_right", move_dist),
            ("move_back", move_dist),
            ("move_left", move_dist),
            ("move_back", move_dist),
            ("move_forward", move_dist),
            ("move_right", move_dist),
            ("move_back", move_dist),
            ("move_left", move_dist),
            ("move_forward", move_dist / 2),
        ]
        await self._execute_demo_sequence(sequence)

    def _run_digit_2_demo(self):
        self.logger.info("正在执行数字 '2' 演示。")
        move_dist = 1.0
        diag_dist = 1.5  # 对角线移动时长 (比直行长一些)
        sequence = [
            # 顶部横线
            ("move_right", move_dist),
            # 右上角到左下角的斜线
            ("move_left_back", diag_dist),
            # 底部横线
            ("move_right", move_dist),
            # 调整位置回到大致中心
            ("move_forward", move_dist / 2),
            ("move_left", move_dist / 2)
        ]
        self._execute_demo_sequence(sequence)
        self.logger.info("数字 '2' 演示完成。")

    def _run_digit_3_demo(self):
        self.logger.info("正在执行数字 '3' 演示。")
        move_dist = 1.0
        diag_dist = 1.5
        sequence = [
            # 顶部横线
            ("move_right", move_dist),
            # 右上到中部的弧线 (近似)
            ("move_left_back", diag_dist / 2),
            ("move_left", move_dist / 2),  # 调整到中间
            ("move_right", move_dist / 2),
            # 中部到右下的弧线 (近似)
            ("move_left_back", diag_dist / 2),
            ("move_back", move_dist / 2),  # 调整到底部
            ("move_left", move_dist / 2)  # 回到大致中心
        ]
        self._execute_demo_sequence(sequence)
        self.logger.info("数字 '3' 演示完成。")

    def _run_digit_4_demo(self):
        self.logger.info("正在执行数字 '4' 演示。")
        move_dist = 1.0
        sequence = [
            # 左上到中间的斜线
            ("move_right_back", move_dist * 1.5),
            # 中间横线
            ("move_right", move_dist),
            # 从顶部垂直向下
            ("move_forward", move_dist * 1.5),
            ("move_back", move_dist / 2),  # 回到中心
            ("move_left", move_dist / 2)
        ]
        self._execute_demo_sequence(sequence)
        self.logger.info("数字 '4' 演示完成。")

    def _run_digit_5_demo(self):
        self.logger.info("正在执行数字 '5' 演示。")
        move_dist = 1.0
        diag_dist = 1.5
        sequence = [
            # 顶部横线
            ("move_right", move_dist),
            # 向下垂直 (右上到右上)
            ("move_back", move_dist),
            # 底部曲线 (近似)
            ("move_left_back", diag_dist / 2),
            ("move_left", move_dist),
            ("move_forward", move_dist / 2),  # 回到中心
        ]
        self._execute_demo_sequence(sequence)
        self.logger.info("数字 '5' 演示完成。")

    def _run_digit_6_demo(self):
        self.logger.info("正在执行数字 '6' 演示。")
        move_dist = 1.0
        diag_dist = 1.5
        sequence = [
            # 顶部向左的横线
            ("move_left", move_dist),
            # 左侧垂直向下
            ("move_back", move_dist),
            # 底部圆环 (近似)
            ("move_right", move_dist),
            ("move_forward", move_dist),
            ("move_left", move_dist / 2),  # 结束在中心
        ]
        self._execute_demo_sequence(sequence)
        self.logger.info("数字 '6' 演示完成。")

    def _run_digit_7_demo(self):
        self.logger.info("正在执行数字 '7' 演示。")
        # 假设小车从数字的“左上角”开始绘制
        move_dist = 1.5  # 横向笔画移动时长
        diag_dist = 2.0  # 对角线笔画移动时长
        sequence = [
            ("move_right", move_dist),  # 绘制顶部横线
            ("move_left_back", diag_dist),  # 绘制右斜向下笔画
            ("move_forward", move_dist / 2),  # 稍微向上移动，为下一个数字做准备
            ("move_left", move_dist / 2),
        ]
        self._execute_demo_sequence(sequence)
        self.logger.info("数字 '7' 演示完成。")

    def _run_digit_8_demo(self):
        self.logger.info("正在执行数字 '8' 演示。")
        move_dist = 1.0
        # 绘制两个近似的方形
        sequence = [
            # 顶部方形
            ("move_forward", move_dist),
            ("move_right", move_dist),
            ("move_back", move_dist),
            ("move_left", move_dist),
            # 移动到下方方形的起始位置
            ("move_back", move_dist),
            # 底部方形
            ("move_forward", move_dist),
            ("move_right", move_dist),
            ("move_back", move_dist),
            ("move_left", move_dist),
            ("move_forward", move_dist / 2),  # 回到中心
        ]
        self._execute_demo_sequence(sequence)
        self.logger.info("数字 '8' 演示完成。")

    def _run_digit_9_demo(self):
        self.logger.info("正在执行数字 '9' 演示。")
        move_dist = 1.0
        diag_dist = 1.5
        sequence = [
            # 顶部圆环 (近似)
            ("move_right", move_dist),
            ("move_back", move_dist),
            ("move_left", move_dist),
            ("move_forward", move_dist),
            # 右侧垂直向下
            ("move_back", move_dist),
            ("move_left", move_dist / 2),  # 结束在中心
        ]
        self._execute_demo_sequence(sequence)
        self.logger.info("数字 '9' 演示完成。")

    # --- 蟹步舞 ---
    async def _run_crab_walk_demo(self):
        # self.logger.info("正在执行蟹步舞演示。")
        # dance_step_duration = 0.4
        # num_wiggles = 5  # 左右摇摆次数
        # sequence = []
        # for _ in range(num_wiggles):
        #     sequence.append(("move_left", dance_step_duration))
        #     sequence.append(("move_right", dance_step_duration))
        # self._execute_demo_sequence(sequence)
        # self.logger.info("蟹步舞演示完成。")
        self.logger.info("蟹步舞")
        step = 0.4
        seq = []
        for _ in range(5):
            seq.append(("move_left", step))
            seq.append(("move_right", step))
        await self._execute_demo_sequence(seq)

    # --- 方步 ---
    def _run_box_step_demo(self):
        self.logger.info("正在执行方步演示。")
        step_duration = 1.5  # 每边持续时长
        sequence = [
            ("move_forward", step_duration),
            ("move_left", step_duration),
            ("move_back", step_duration),
            ("move_right", step_duration),
        ]
        self._execute_demo_sequence(sequence)
        self.logger.info("方步演示完成。")

    # --- S 形曲线 ---
    def _run_s_curve_demo(self):
        self.logger.info("正在执行 S 形曲线演示。")
        segment_forward_duration = 1.2
        segment_turn_duration = 0.7  # 调整此值以控制曲线弧度

        sequence = [
            ("move_forward", segment_forward_duration),
            ("turn_left", segment_turn_duration),
            ("move_forward", segment_forward_duration),
            ("turn_right", segment_turn_duration),
            ("move_forward", segment_forward_duration),
        ]
        self._execute_demo_sequence(sequence)
        self.logger.info("S 形曲线演示完成。")

    # --- Z 形曲线 ---
    def _run_z_curve_demo(self):
        self.logger.info("正在执行 Z 形曲线演示。")
        straight_duration = 1.5
        turn_duration = 1.0  # 90度转弯时长

        sequence = [
            ("move_forward", straight_duration),
            ("turn_right", turn_duration),  # 第一个直角转弯
            ("move_forward", straight_duration),
            ("turn_left", turn_duration),  # 第二个直角转弯
            ("move_forward", straight_duration),
        ]
        self._execute_demo_sequence(sequence)
        self.logger.info("Z 形曲线演示完成。")

    # --- 原地高速旋转 ---
    def _run_spin_fast_demo(self):
        self.logger.info("正在执行原地高速旋转演示。")
        spin_duration_per_direction = 0.8  # 单向旋转时长
        num_spins = 3  # 旋转圈数 (近似)

        sequence = []
        for _ in range(num_spins):
            sequence.append(("turn_left", spin_duration_per_direction))
            sequence.append(("turn_right", spin_duration_per_direction))
        self._execute_demo_sequence(sequence)
        self.logger.info("原地高速旋转演示完成。")
