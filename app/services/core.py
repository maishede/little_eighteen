# -*- coding: utf-8 -*-
import time
import statistics
import RPi.GPIO as GPIO
from app.config import (
    IN1, IN2, IN3, IN4, IN5, IN6, IN7, IN8,
    HC_SR_04_TRIG, HC_SR_04_ECHO,
    MODE_FORWARD, MODE_BACK, MODE_STOP,
    DEFAULT_TEMPERATURE, DISTANCE_BUFFER_SIZE, HC_SR_04_TIMEOUT
)

# GPIO 常量
OUT = GPIO.OUT
HIGH = GPIO.HIGH
LOW = GPIO.LOW
IN = GPIO.IN


class MotorControl(object):
    def __init__(self):
        GPIO.cleanup()
        GPIO.setmode(GPIO.BCM)
        # 设置电机控制引脚
        for pin in [IN1, IN2, IN3, IN4, IN5, IN6, IN7, IN8]:
            GPIO.setup(pin, OUT)
            GPIO.output(pin, LOW)
        # 设置超声波传感器引脚
        GPIO.setup(HC_SR_04_TRIG, OUT)
        GPIO.setup(HC_SR_04_ECHO, IN)

        self.stop()  # 初始化时停车

        self._distance_detection_enabled = True  # 内部控制距离检测是否开启
        self.temperature = DEFAULT_TEMPERATURE
        self.distance_buffer = []
        self.buffer_size = DISTANCE_BUFFER_SIZE

    def cleanup(self):
        """清理GPIO引脚状态"""
        self.stop()
        GPIO.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()

    # Property for distance_detection_enabled
    @property
    def distance_detection_enabled(self):
        return self._distance_detection_enabled

    @distance_detection_enabled.setter
    def distance_detection_enabled(self, value: bool):
        self._distance_detection_enabled = value

    # --- 私有电机控制方法 ---
    def __set_motor_state(self, motor_in1, motor_in2, mode):
        """
        根据模式设置单个电机的方向。
        重要：此方法根据传入的 motor_in1 和 motor_in2 来判断左右电机，
        并针对右侧电机（IN5/IN6 或 IN7/IN8）自动反转方向，以校正物理接线。
        """
        is_right_motor = (motor_in1 in [IN5, IN7])  # 检查是否是右侧电机 (IN5, IN7 是右侧电机的第一控制引脚)

        if mode == MODE_FORWARD:
            if is_right_motor:  # 如果是右侧电机，前进时实际需要反转信号
                GPIO.output(motor_in1, LOW)
                GPIO.output(motor_in2, HIGH)
            else:  # 左侧电机，正常前进
                GPIO.output(motor_in1, HIGH)
                GPIO.output(motor_in2, LOW)
        elif mode == MODE_BACK:
            if is_right_motor:  # 如果是右侧电机，后退时实际需要反转信号
                GPIO.output(motor_in1, HIGH)
                GPIO.output(motor_in2, LOW)
            else:  # 左侧电机，正常后退
                GPIO.output(motor_in1, LOW)
                GPIO.output(motor_in2, HIGH)
        elif mode == MODE_STOP:
            GPIO.output(motor_in1, LOW)
            GPIO.output(motor_in2, LOW)

    def _control_motor_pair(self, in1, in2, mode):
        self.__set_motor_state(in1, in2, mode)

    # --- 单独电机控制方法 (用于调试) ---
    def control_left_front(self, mode):
        """单独控制左前电机"""
        self.__set_motor_state(IN1, IN2, mode)

    # def control_left_back(self, mode):
    #     """单独控制左后电机"""
    #     self.__set_motor_state(IN3, IN4, mode)
    #
    # def control_right_front(self, mode):
    #     """单独控制右前电机"""
    #     self.__set_motor_state(IN5, IN6, mode)
    #
    # def control_right_back(self, mode):
    #     """单独控制右后电机"""
    #     self.__set_motor_state(IN7, IN8, mode)
    #
    # # 麦克纳姆轮的四轮控制私有方法 (保持不变)
    # def __left_front_motor(self, mode=MODE_FORWARD):
    #     self.control_left_front(mode)
    #
    # def __left_back_motor(self, mode=MODE_FORWARD):
    #     self.control_left_back(mode)
    #
    # def __right_front_motor(self, mode=MODE_FORWARD):
    #     self.control_right_front(mode)
    #
    # def __right_back_motor(self, mode=MODE_FORWARD):
    #     self.control_right_back(mode)

    # --- 公共运动方法 (麦克纳姆轮运动逻辑) ---
    def move_forward(self):
        """小车向前直行"""
        # self.__left_front_motor(MODE_FORWARD)
        # self.__left_back_motor(MODE_FORWARD)
        # self.__right_front_motor(MODE_FORWARD)
        # self.__right_back_motor(MODE_FORWARD)
        self._control_motor_pair(IN1, IN2, MODE_FORWARD)
        self._control_motor_pair(IN3, IN4, MODE_FORWARD)
        self._control_motor_pair(IN5, IN6, MODE_FORWARD)
        self._control_motor_pair(IN7, IN8, MODE_FORWARD)

    def move_back(self):
        """小车向后直行"""
        # self.__left_front_motor(MODE_BACK)
        # self.__left_back_motor(MODE_BACK)
        # self.__right_front_motor(MODE_BACK)
        # self.__right_back_motor(MODE_BACK)
        self._control_motor_pair(IN1, IN2, MODE_BACK)
        self._control_motor_pair(IN3, IN4, MODE_BACK)
        self._control_motor_pair(IN5, IN6, MODE_BACK)
        self._control_motor_pair(IN7, IN8, MODE_BACK)

    def move_left(self):  # 平移向左 (横向移动)
        """
        麦克纳姆轮左平移：
        左前轮：后退
        左后轮：前进
        右前轮：前进
        右后轮：后退
        """
        # self.__left_front_motor(MODE_BACK)
        # self.__left_back_motor(MODE_FORWARD)
        # self.__right_front_motor(MODE_FORWARD)
        # self.__right_back_motor(MODE_BACK)
        self._control_motor_pair(IN1, IN2, MODE_BACK)
        self._control_motor_pair(IN3, IN4, MODE_FORWARD)
        self._control_motor_pair(IN5, IN6, MODE_FORWARD)
        self._control_motor_pair(IN7, IN8, MODE_BACK)

    def move_right(self):  # 平移向右 (横向移动)
        """
        麦克纳姆轮右平移：
        左前轮：前进
        左后轮：后退
        右前轮：后退
        右后轮：前进
        """
        # self.__left_front_motor(MODE_FORWARD)
        # self.__left_back_motor(MODE_BACK)
        # self.__right_front_motor(MODE_BACK)
        # self.__right_back_motor(MODE_FORWARD)
        self._control_motor_pair(IN1, IN2, MODE_FORWARD)
        self._control_motor_pair(IN3, IN4, MODE_BACK)
        self._control_motor_pair(IN5, IN6, MODE_BACK)
        self._control_motor_pair(IN7, IN8, MODE_FORWARD)

    def turn_left(self):  # 原地左转
        """
        原地左转：
        左侧所有轮子：后退
        右侧所有轮子：前进
        """
        # self.__left_front_motor(MODE_BACK)
        # self.__left_back_motor(MODE_BACK)
        # self.__right_front_motor(MODE_FORWARD)
        # self.__right_back_motor(MODE_FORWARD)
        self._control_motor_pair(IN1, IN2, MODE_BACK)
        self._control_motor_pair(IN3, IN4, MODE_BACK)
        self._control_motor_pair(IN5, IN6, MODE_FORWARD)
        self._control_motor_pair(IN7, IN8, MODE_FORWARD)

    def turn_right(self):  # 原地右转
        """
        原地右转：
        左侧所有轮子：前进
        右侧所有轮子：后退
        """
        # self.__left_front_motor(MODE_FORWARD)
        # self.__left_back_motor(MODE_FORWARD)
        # self.__right_front_motor(MODE_BACK)
        # self.__right_back_motor(MODE_BACK)
        self._control_motor_pair(IN1, IN2, MODE_FORWARD)
        self._control_motor_pair(IN3, IN4, MODE_FORWARD)
        self._control_motor_pair(IN5, IN6, MODE_BACK)
        self._control_motor_pair(IN7, IN8, MODE_BACK)

    # --- 斜向移动 (修正后的麦克纳姆轮逻辑，基于所有轮子方向校正) ---
    def move_left_forward(self):  # 左前斜向
        # self.__left_front_motor(MODE_STOP)
        # self.__left_back_motor(MODE_FORWARD)
        # self.__right_front_motor(MODE_FORWARD)
        # self.__right_back_motor(MODE_STOP)
        self._control_motor_pair(IN1, IN2, MODE_STOP)
        self._control_motor_pair(IN3, IN4, MODE_FORWARD)
        self._control_motor_pair(IN5, IN6, MODE_FORWARD)
        self._control_motor_pair(IN7, IN8, MODE_STOP)

    def move_right_forward(self):  # 右前斜向
        # self.__left_front_motor(MODE_FORWARD)
        # self.__left_back_motor(MODE_STOP)
        # self.__right_front_motor(MODE_STOP)
        # self.__right_back_motor(MODE_FORWARD)
        self._control_motor_pair(IN1, IN2, MODE_FORWARD)
        self._control_motor_pair(IN3, IN4, MODE_STOP)
        self._control_motor_pair(IN5, IN6, MODE_STOP)
        self._control_motor_pair(IN7, IN8, MODE_FORWARD)

    def move_left_back(self):  # 左后斜向
        # self.__left_front_motor(MODE_BACK)
        # self.__left_back_motor(MODE_STOP)
        # self.__right_front_motor(MODE_STOP)
        # self.__right_back_motor(MODE_BACK)
        self._control_motor_pair(IN1, IN2, MODE_BACK)
        self._control_motor_pair(IN3, IN4, MODE_STOP)
        self._control_motor_pair(IN5, IN6, MODE_STOP)
        self._control_motor_pair(IN7, IN8, MODE_BACK)

    def move_right_back(self):  # 右后斜向
        # self.__left_front_motor(MODE_STOP)
        # self.__left_back_motor(MODE_BACK)
        # self.__right_front_motor(MODE_BACK)
        # self.__right_back_motor(MODE_STOP)
        self._control_motor_pair(IN1, IN2, MODE_STOP)
        self._control_motor_pair(IN3, IN4, MODE_BACK)
        self._control_motor_pair(IN5, IN6, MODE_BACK)
        self._control_motor_pair(IN7, IN8, MODE_STOP)

    def stop(self):
        """停止所有电机，将所有控制引脚置低"""
        for pin in [IN1, IN2, IN3, IN4, IN5, IN6, IN7, IN8]:
            GPIO.output(pin, LOW)

    def measure_distance(self):
        """优化后的HC-SR04超声波测距方法，返回厘米，并包含中值滤波。
        如果距离检测被禁用，则返回 None。
        """
        if not self._distance_detection_enabled:
            return None

        GPIO.output(HC_SR_04_TRIG, False)
        time.sleep(0.000002)  # 2微秒低电平，确保清洁的脉冲

        GPIO.output(HC_SR_04_TRIG, True)
        time.sleep(0.00001)  # 10微秒高电平脉冲
        GPIO.output(HC_SR_04_TRIG, False)

        pulse_start_time = time.time()
        pulse_end_time = time.time()

        # 等待 ECHO 信号变为高电平 (起始时间)
        timeout_start = time.time() + HC_SR_04_TIMEOUT
        # while GPIO.input(HC_SR_04_ECHO) == 0 and time.time() < timeout_start:
        #     pulse_start_time = time.time()
        #
        # if time.time() >= timeout_start:
        #     return -1  # 返回-1表示测量失败或超时
        while GPIO.input(HC_SR_04_ECHO) == 0:
            if time.time() > timeout_start:
                return -1
            pulse_start_time = time.time()

        # 等待 ECHO 信号变为低电平 (结束时间)
        timeout_end = time.time() + HC_SR_04_TIMEOUT
        # while GPIO.input(HC_SR_04_ECHO) == 1 and time.time() < timeout_end:
        #     pulse_end_time = time.time()
        #
        # if time.time() >= timeout_end:
        #     return -1  # 返回-1表示测量失败或超时
        while GPIO.input(HC_SR_04_ECHO) == 1:
            if time.time() > timeout_end:
                return -1
            pulse_end_time = time.time()

        pulse_duration = pulse_end_time - pulse_start_time
        # 根据温度调整声速 (米/秒)。声速 = 331.3 + 0.606 * 温度
        speed_of_sound = 331.3 + 0.606 * self.temperature
        distance = pulse_duration * speed_of_sound / 2 * 100  # 距离 = 时间 * 速度 / 2 (往返) * 100 (米转厘米)

        # 将新的距离测量结果添加到缓冲区
        self.distance_buffer.append(distance)
        if len(self.distance_buffer) > self.buffer_size:
            self.distance_buffer.pop(0)  # 移除最早的测量结果，保持缓冲区大小

        # 使用中值滤波减少异常值的影响
        if self.distance_buffer:
            filtered_distance = statistics.median(self.distance_buffer)
            return round(filtered_distance, 2)  # 返回四舍五入到两位小数
        return -1  # 如果缓冲区为空也返回失败


if __name__ == '__main__':
    # 示例用法
    with MotorControl() as mc:
        print("--- 开始重新调试单个电机 ---")
        print("调试左前电机：前进 1秒")
        mc.control_left_front(MODE_FORWARD)
        time.sleep(1)
        mc.stop()  # 停止所有电机，确保干净状态
        time.sleep(0.5)

        print("调试左前电机：后退 1秒")
        mc.control_left_front(MODE_BACK)
        time.sleep(1)
        mc.stop()
        time.sleep(0.5)

        print("调试左后电机：前进 1秒")
        mc.control_left_back(MODE_FORWARD)
        time.sleep(1)
        mc.stop()
        time.sleep(0.5)

        print("调试左后电机：后退 1秒")
        mc.control_left_back(MODE_BACK)
        time.sleep(1)
        mc.stop()
        time.sleep(0.5)

        print("调试右前电机：前进 1秒")
        mc.control_right_front(MODE_FORWARD)
        time.sleep(1)
        mc.stop()
        time.sleep(0.5)

        print("调试右前电机：后退 1秒")
        mc.control_right_front(MODE_BACK)
        time.sleep(1)
        mc.stop()
        time.sleep(0.5)

        print("调试右后电机：前进 1秒")
        mc.control_right_back(MODE_FORWARD)
        time.sleep(1)
        mc.stop()
        time.sleep(0.5)

        print("调试右后电机：后退 1秒")
        mc.control_right_back(MODE_BACK)
        time.sleep(1)
        mc.stop()
        time.sleep(0.5)
        print("--- 单个电机调试结束 ---")

        # 以下是原来的运动测试示例，您可以根据需要保留或删除
        print("\n--- 开始麦克纳姆轮运动测试 ---")
        print("前进")
        mc.move_forward()
        time.sleep(1)
        mc.stop()
        time.sleep(0.5)

        print("后退")
        mc.move_back()
        time.sleep(1)
        mc.stop()
        time.sleep(0.5)

        print("左平移")
        mc.move_left()
        time.sleep(1)
        mc.stop()
        time.sleep(0.5)

        print("右平移")
        mc.move_right()
        time.sleep(1)
        mc.stop()
        time.sleep(0.5)

        print("原地左转")
        mc.turn_left()
        time.sleep(1)
        mc.stop()
        time.sleep(0.5)

        print("原地右转")
        mc.turn_right()
        time.sleep(1)
        mc.stop()
        time.sleep(0.5)

        print("左前斜向")
        mc.move_left_forward()
        time.sleep(1)
        mc.stop()
        time.sleep(0.5)

        print("右前斜向")
        mc.move_right_forward()
        time.sleep(1)
        mc.stop()
        time.sleep(0.5)

        print("左后斜向")
        mc.move_left_back()
        time.sleep(1)
        mc.stop()
        time.sleep(0.5)

        print("右后斜向")
        mc.move_right_back()
        time.sleep(1)
        mc.stop()
        time.sleep(0.5)

        print("测试距离检测 (5秒)")
        mc.distance_detection_enabled = True
        for _ in range(50):  # 测量5秒，每0.1秒一次
            dist = mc.measure_distance()
            if dist is not None and dist != -1:  # 确保不是None和-1
                print(f"Distance: {dist} cm")
            time.sleep(0.1)
        mc.distance_detection_enabled = False  # 禁用检测
        print("--- 麦克纳姆轮运动测试结束 ---")

    print("程序退出。")
