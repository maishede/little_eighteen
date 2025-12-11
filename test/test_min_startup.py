# -*- coding: utf-8 -*-
import RPi.GPIO as GPIO
import time

# 保持 100Hz，这是树莓派和 L298N 的“黄金频率”
PWM_FREQ = 100

# 四个轮子的 EN 引脚 (根据你之前的测试结果)
EN_PINS = [6, 13, 19, 26]

# 方向引脚 (全部设为前进)
IN_PAIRS = [(18, 23), (24, 25), (12, 16), (20, 21)]


def find_min_startup():
    print(f"--- 🔍 寻找最小起步占空比 (频率: {PWM_FREQ}Hz) ---")
    print("请盯着轮子，当某个轮子开始转动时，记录下屏幕上的数值！")

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.cleanup()

    # 1. 挂挡 (前进)
    for in_a, in_b in IN_PAIRS:
        GPIO.setup(in_a, GPIO.OUT)
        GPIO.setup(in_b, GPIO.OUT)
        GPIO.output(in_a, GPIO.HIGH)
        GPIO.output(in_b, GPIO.LOW)

    # 2. 初始化 PWM
    pwms = []
    for en in EN_PINS:
        GPIO.setup(en, GPIO.OUT)
        p = GPIO.PWM(en, PWM_FREQ)
        p.start(0)
        pwms.append(p)

    try:
        # 3. 极慢加速 (从 10% 开始，避免太久等待)
        print("\n>>> 开始测试 (从 10% 开始)...")
        for dc in range(10, 101, 1):  # 每次增加 1%
            print(f"   当前 PWM: {dc}%")

            for p in pwms:
                p.ChangeDutyCycle(dc)

            # 给电机一点反应时间，稍微长一点
            time.sleep(0.3)

            # 如果到了 60% 还没动，那肯定有问题了
            if dc == 60:
                print("   (如果现在还没动，说明供电不足或负载太重)")

        print(">>> 全速运行")
        time.sleep(1)

    except KeyboardInterrupt:
        print("停止")
    finally:
        for p in pwms:
            p.stop()
        GPIO.cleanup()
        print("测试结束")


if __name__ == "__main__":
    find_min_startup()