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
        if mode == MODE_FORWARD:
            GPIO.output(motor_in1, HIGH)
            GPIO.output(motor_in2, LOW)
        elif mode == MODE_BACK:
            GPIO.output(motor_in1, LOW)
            GPIO.output(motor_in2, HIGH)
        elif mode == MODE_STOP:
            GPIO.output(motor_in1, LOW)
            GPIO.output(motor_in2, LOW)

    def __left_front_motor(self, mode=MODE_FORWARD):
        self.__set_motor_state(IN1, IN2, mode)

    def __left_back_motor(self, mode=MODE_FORWARD):
        self.__set_motor_state(IN3, IN4, mode)

    def __right_front_motor(self, mode=MODE_FORWARD):
        self.__set_motor_state(IN5, IN6, mode)

    def __right_back_motor(self, mode=MODE_FORWARD):
        self.__set_motor_state(IN7, IN8, mode)

    # --- 公共运动方法 ---
    def move_forward(self):
        self.__left_front_motor(MODE_FORWARD)
        self.__left_back_motor(MODE_FORWARD)
        self.__right_front_motor(MODE_FORWARD)
        self.__right_back_motor(MODE_FORWARD)

    def move_back(self):
        self.__left_front_motor(MODE_BACK)
        self.__left_back_motor(MODE_BACK)
        self.__right_front_motor(MODE_BACK)
        self.__right_back_motor(MODE_BACK)

    def move_left(self):  # 平移向左
        self.__left_front_motor(MODE_BACK)  # 左前轮反转
        self.__left_back_motor(MODE_FORWARD)  # 左后轮正转
        self.__right_front_motor(MODE_FORWARD)  # 右前轮正转
        self.__right_back_motor(MODE_BACK)  # 右后轮反转

    def move_right(self):  # 平移向右
        self.__left_front_motor(MODE_FORWARD)  # 左前轮正转
        self.__left_back_motor(MODE_BACK)  # 左后轮反转
        self.__right_front_motor(MODE_BACK)  # 右前轮反转
        self.__right_back_motor(MODE_FORWARD)  # 右后轮正转

    def turn_left(self):  # 原地左转
        self.__left_front_motor(MODE_BACK)
        self.__left_back_motor(MODE_BACK)
        self.__right_front_motor(MODE_FORWARD)
        self.__right_back_motor(MODE_FORWARD)

    def turn_right(self):  # 原地右转
        self.__left_front_motor(MODE_FORWARD)
        self.__left_back_motor(MODE_FORWARD)
        self.__right_front_motor(MODE_BACK)
        self.__right_back_motor(MODE_BACK)

    # --- 斜向移动 (新增) ---
    def move_left_forward(self):  # 左前斜向
        self.__left_front_motor(MODE_STOP)
        self.__left_back_motor(MODE_FORWARD)
        self.__right_front_motor(MODE_FORWARD)
        self.__right_back_motor(MODE_FORWARD)

    def move_right_forward(self):  # 右前斜向
        self.__left_front_motor(MODE_FORWARD)
        self.__left_back_motor(MODE_FORWARD)
        self.__right_front_motor(MODE_STOP)
        self.__right_back_motor(MODE_FORWARD)

    def move_left_back(self):  # 左后斜向
        self.__left_front_motor(MODE_BACK)
        self.__left_back_motor(MODE_BACK)
        self.__right_front_motor(MODE_BACK)
        self.__right_back_motor(MODE_STOP)

    def move_right_back(self):  # 右后斜向
        self.__left_front_motor(MODE_BACK)
        self.__left_back_motor(MODE_STOP)
        self.__right_front_motor(MODE_BACK)
        self.__right_back_motor(MODE_BACK)

    def stop(self):
        """停止所有电机"""
        for pin in [IN1, IN2, IN3, IN4, IN5, IN6, IN7, IN8]:
            GPIO.output(pin, LOW)

    def measure_distance(self):
        """优化后的HC-SR04返回厘米，并包含中值滤波"""
        if not self._distance_detection_enabled:
            return None

        GPIO.output(HC_SR_04_TRIG, False)
        time.sleep(0.000002)  # 等待稳定

        GPIO.output(HC_SR_04_TRIG, True)
        time.sleep(0.00001)
        GPIO.output(HC_SR_04_TRIG, False)

        pulse_start_time = time.time()
        pulse_end_time = time.time()

        # 等待 ECHO 信号变为高电平
        timeout_start = time.time() + HC_SR_04_TIMEOUT
        while GPIO.input(HC_SR_04_ECHO) == 0 and time.time() < timeout_start:
            pulse_start_time = time.time()

        if time.time() >= timeout_start:
            # print("Timeout waiting for start pulse (0->1)")
            return -1  # 返回-1表示测量失败

        # 等待 ECHO 信号变为低电平
        timeout_end = time.time() + HC_SR_04_TIMEOUT
        while GPIO.input(HC_SR_04_ECHO) == 1 and time.time() < timeout_end:
            pulse_end_time = time.time()

        if time.time() >= timeout_end:
            # print("Timeout waiting for end pulse (1->0)")
            return -1  # 返回-1表示测量失败

        pulse_duration = pulse_end_time - pulse_start_time
        speed_of_sound = 331.3 + 0.606 * self.temperature  # 根据温度调整声速 (m/s)
        distance = pulse_duration * speed_of_sound / 2 * 100  # 转换为厘米

        # 将新的距离测量结果添加到缓冲区
        self.distance_buffer.append(distance)
        if len(self.distance_buffer) > self.buffer_size:
            self.distance_buffer.pop(0)  # 移除最早的测量结果

        # 使用中值滤波减少异常值的影响
        if self.distance_buffer:
            filtered_distance = statistics.median(self.distance_buffer)
            return round(filtered_distance, 2)
        return -1  # 如果缓冲区为空也返回失败


if __name__ == '__main__':
    # 示例用法
    with MotorControl() as mc:
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
            if dist is not None:
                print(f"Distance: {dist} cm")
            time.sleep(0.1)
        mc.distance_detection_enabled = False  # 禁用检测
