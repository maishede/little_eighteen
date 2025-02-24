import time
import statistics

import RPi.GPIO as GPIO

IN1 = 18
IN2 = 23
IN3 = 24
IN4 = 25
IN5 = 12
IN6 = 16
IN7 = 20
IN8 = 21
HC_SR_04_TRIG = 4
HC_SR_04_ECHO = 17

OUT = GPIO.OUT
HIGH = GPIO.HIGH
LOW = GPIO.LOW
IN = GPIO.IN

FORWARD = 1
BACK = 2
STOP = 3


class MotorControl(object):
    def __init__(self):
        GPIO.cleanup()
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(IN1, OUT)
        GPIO.setup(IN2, OUT)
        GPIO.setup(IN3, OUT)
        GPIO.setup(IN4, OUT)
        GPIO.setup(IN5, OUT)
        GPIO.setup(IN6, OUT)
        GPIO.setup(IN7, OUT)
        GPIO.setup(IN8, OUT)
        GPIO.setup(HC_SR_04_TRIG, OUT)
        GPIO.setup(HC_SR_04_ECHO, IN)
        self.stop()

        self.distance_detection = 1  # 0:关闭;1:开启

        self.temperature = 20  # 默认温度为20度
        self.distance_buffer = []  # 用于存储最近几次的距离测量结果
        self.buffer_size = 5  # 缓冲区大小，即平滑处理时考虑的测量次数

    def cleanup(self):
        GPIO.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()

    def __left_1(self, mode=FORWARD):
        if mode == FORWARD:
            GPIO.output(IN1, HIGH)
            GPIO.output(IN2, LOW)
        elif mode == BACK:
            GPIO.output(IN1, LOW)
            GPIO.output(IN2, HIGH)
        elif mode == STOP:
            GPIO.output(IN1, LOW)
            GPIO.output(IN2, LOW)

    def __left_2(self, mode=FORWARD):
        if mode == FORWARD:
            GPIO.output(IN3, HIGH)
            GPIO.output(IN4, LOW)
        elif mode == BACK:
            GPIO.output(IN3, LOW)
            GPIO.output(IN4, HIGH)
        elif mode == STOP:
            GPIO.output(IN3, LOW)
            GPIO.output(IN4, LOW)

    def __right_1(self, mode=FORWARD):
        if mode == FORWARD:
            GPIO.output(IN5, LOW)
            GPIO.output(IN6, HIGH)
        elif mode == BACK:
            GPIO.output(IN5, HIGH)
            GPIO.output(IN6, LOW)
        elif mode == STOP:
            GPIO.output(IN5, LOW)
            GPIO.output(IN6, LOW)

    def __right_2(self, mode=FORWARD):
        if mode == FORWARD:
            GPIO.output(IN7, LOW)
            GPIO.output(IN8, HIGH)
        elif mode == BACK:
            GPIO.output(IN7, HIGH)
            GPIO.output(IN8, LOW)
        elif mode == STOP:
            GPIO.output(IN7, LOW)
            GPIO.output(IN8, LOW)

    def move_forward(self, running_time: int = 3):
        self.__left_1(FORWARD)
        self.__left_2(FORWARD)
        self.__right_1(FORWARD)
        self.__right_2(FORWARD)
        # time.sleep(running_time)
        # self.stop()

    def move_back(self, running_time: int = 3):
        self.__left_1(BACK)
        self.__left_2(BACK)
        self.__right_1(BACK)
        self.__right_2(BACK)
        # time.sleep(running_time)
        # self.stop()

    def move_left(self, running_time: int = 3):
        self.__left_1(BACK)
        self.__left_2(FORWARD)
        self.__right_1(FORWARD)
        self.__right_2(BACK)
        # time.sleep(running_time)
        # self.stop()

    def move_right(self, running_time: int = 3):
        self.__left_1(FORWARD)
        self.__left_2(BACK)
        self.__right_1(BACK)
        self.__right_2(FORWARD)
        # time.sleep(running_time)
        # self.stop()

    def turn_left(self, running_time: int = 1):
        self.__left_1(BACK)
        self.__left_2(BACK)
        self.__right_1(FORWARD)
        self.__right_2(FORWARD)
        # time.sleep(running_time)
        # self.stop()

    def turn_right(self, running_time: int = 1):
        self.__left_1(FORWARD)
        self.__left_2(FORWARD)
        self.__right_1(BACK)
        self.__right_2(BACK)
        # time.sleep(running_time)
        # self.stop()

    def test(self, running_time: int = 3):
        self.__right_1(FORWARD)
        self.__left_1(STOP)
        self.__right_2(STOP)
        self.__left_2(BACK)

    def measure_distance(self):
        if not self.distance_detection:
            return None
        """优化后的HC-SR04返回厘米"""
        GPIO.output(HC_SR_04_TRIG, True)
        time.sleep(0.00001)
        GPIO.output(HC_SR_04_TRIG, False)

        timeout = time.time() + 0.03  # 超时时间为30ms
        pulse_start = 0
        pulse_end = 0

        while GPIO.input(HC_SR_04_ECHO) == 0 and time.time() < timeout:
            pulse_start = time.time()

        if time.time() >= timeout:
            print("Timeout waiting for start pulse")
            return -1  # 返回-1表示测量失败

        timeout = time.time() + 0.03  # 重置超时时间

        while GPIO.input(HC_SR_04_ECHO) == 1 and time.time() < timeout:
            pulse_end = time.time()

        if time.time() >= timeout:
            print("Timeout waiting for end pulse")
            return -1  # 返回-1表示测量失败

        pulse_duration = pulse_end - pulse_start
        speed_of_sound = 331.3 + 0.606 * self.temperature  # 根据温度调整声速
        distance = pulse_duration * speed_of_sound / 2 * 100
        distance = round(distance, 2)

        # 将新的距离测量结果添加到缓冲区
        self.distance_buffer.append(distance)
        if len(self.distance_buffer) > self.buffer_size:
            self.distance_buffer.pop(0)  # 移除最早的测量结果

        # 使用中值滤波减少异常值的影响
        filtered_distance = statistics.median(self.distance_buffer)

        return filtered_distance

    def stop(self):
        [GPIO.output(IN, LOW) for IN in [IN1, IN2, IN3, IN4, IN5, IN6, IN7, IN8]]


if __name__ == '__main__':
    with MotorControl() as mc:
        print("前进")
        mc.move_forward()
        print("后退")
        mc.move_back()
        print("左转")
        mc.turn_left()
        print("右转")
        mc.turn_right()
    # GPIO.cleanup()
