import time

import RPi.GPIO as GPIO

IN1 = 18
IN2 = 23
IN3 = 24
IN4 = 25
IN5 = 12
IN6 = 16
IN7 = 20
IN8 = 21

OUT = GPIO.OUT
HIGH = GPIO.HIGH
LOW = GPIO.LOW

FORWARD = 1
BACK = 2
STOP = 3


class MotorControl(object):
    def __init__(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(IN1, OUT)
        GPIO.setup(IN2, OUT)
        GPIO.setup(IN3, OUT)
        GPIO.setup(IN4, OUT)
        GPIO.setup(IN5, OUT)
        GPIO.setup(IN6, OUT)
        GPIO.setup(IN7, OUT)
        GPIO.setup(IN8, OUT)
        self.stop()

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
        time.sleep(running_time)
        self.stop()

    def move_back(self, running_time: int = 3):
        self.__left_1(BACK)
        self.__left_2(BACK)
        self.__right_1(BACK)
        self.__right_2(BACK)
        time.sleep(running_time)
        self.stop()

    def turn_left_forward(self, running_time: int = 2):
        self.__left_1(STOP)
        self.__left_2(STOP)
        self.__right_1(FORWARD)
        self.__right_2(FORWARD)
        time.sleep(running_time)
        self.stop()

    def turn_right_forward(self, running_time: int = 2):
        self.__left_1(FORWARD)
        self.__left_2(FORWARD)
        self.__right_1(STOP)
        self.__right_2(STOP)
        time.sleep(running_time)
        self.stop()

    def stop(self):
        [GPIO.output(IN, LOW) for IN in [IN1, IN2, IN3, IN4, IN5, IN6, IN7, IN8]]


if __name__ == '__main__':
    with MotorControl() as mc:
        print("前进")
        mc.move_forward()
        print("后退")
        mc.move_back()
        print("左转")
        mc.turn_left_forward()
        print("右转")
        mc.turn_right_forward()
    # GPIO.cleanup()
