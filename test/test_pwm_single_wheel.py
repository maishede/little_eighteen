# -*- coding: utf-8 -*-
import RPi.GPIO as GPIO
import time

# ================= 硬件定义 =================
# 根据你刚才确认的顺序
EN_CONFIG = [
    {"pin": 6, "name": "GPIO 6 (预期: 左前)"},
    {"pin": 13, "name": "GPIO 13 (预期: 左后)"},
    {"pin": 19, "name": "GPIO 19 (预期: 右后)"},
    {"pin": 26, "name": "GPIO 26 (预期: 右前)"}
]

# 所有的 IN 引脚 (方向接口) - 只有全开，车才能动
ALL_IN_PINS = [18, 23, 24, 25, 12, 16, 20, 21]

# 测试的速度档位
SPEED_STEPS = [0, 30, 60, 100]


def test_speed_steps():
    print("========================================")
    print("      EN 接口速度阶梯测试 (0-30-60-100)      ")
    print("========================================")

    # 1. 初始化
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.cleanup()

    # 2. 激活所有方向引脚 (设置为前进)
    print(">>> [Step 1] 挂入前进挡 (所有方向引脚激活)...")
    for i in range(0, len(ALL_IN_PINS), 2):
        pin_a = ALL_IN_PINS[i]
        pin_b = ALL_IN_PINS[i + 1]
        GPIO.setup(pin_a, GPIO.OUT)
        GPIO.setup(pin_b, GPIO.OUT)
        # 前进逻辑: High/Low
        GPIO.output(pin_a, GPIO.HIGH)
        GPIO.output(pin_b, GPIO.LOW)

    # 3. 逐个测试 EN 引脚的速度变化
    print(">>> [Step 2] 开始轮询测试速度变化...")

    for item in EN_CONFIG:
        en_pin = item['pin']
        name = item['name']

        print(f"\n👉 当前测试: {name}")

        GPIO.setup(en_pin, GPIO.OUT)
        pwm = GPIO.PWM(en_pin, 100)  # 100Hz
        pwm.start(0)

        # 遍历速度档位
        for speed in SPEED_STEPS:
            print(f"   ⚙️  速度设定: {speed}%")
            pwm.ChangeDutyCycle(speed)

            # 留出观察时间：0%和30%可能不明显，给1.5秒；高速给2秒
            wait_time = 2.0
            time.sleep(wait_time)

        # 停止当前引脚
        pwm.stop()
        GPIO.output(en_pin, GPIO.LOW)
        print(f"   ✅ {name} 测试结束")
        time.sleep(1)  # 间隔

    # 4. 清理
    GPIO.cleanup()
    print("\n========================================")
    print("测试结束")


if __name__ == "__main__":
    try:
        test_speed_steps()
    except KeyboardInterrupt:
        GPIO.cleanup()
        print("\n强制退出")