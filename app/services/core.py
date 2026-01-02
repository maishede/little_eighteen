# -*- coding: utf-8 -*-
import time
import statistics
import json
import os
import RPi.GPIO as GPIO
from app.config import (
    IN1, IN2, IN3, IN4, IN5, IN6, IN7, IN8,
    HC_SR_04_TRIG, HC_SR_04_ECHO,
    MODE_FORWARD, MODE_BACK, MODE_STOP,
    DEFAULT_TEMPERATURE, DISTANCE_BUFFER_SIZE, HC_SR_04_TIMEOUT,
    EN1, EN2, EN3, EN4, PWM_FREQ, DEFAULT_SPEED, MIN_SPEED_LIMIT,
    CORRECTION_LF, CORRECTION_LB, CORRECTION_RF, CORRECTION_RB,
    RUNTIME_STATE_FILE, DATA_DIR
)

# GPIO 常量
OUT = GPIO.OUT
HIGH = GPIO.HIGH
LOW = GPIO.LOW
IN = GPIO.IN


class MotorControl(object):
    def __init__(self):
        import logging
        import threading
        self.logger = logging.getLogger("MotorControl")
        self._is_real_hardware = True  # 默认为真硬件
        self._save_lock = threading.Lock()  # 文件保存锁，防止并发问题
        try:
            import RPi.GPIO as GPIO_Real
            # 检查是否是模拟环境
            if GPIO_Real.RPI_REVISION == 0:
                self.logger.warning("⚠️ 检测到 RPi.GPIO 模拟环境（非树莓派），电机将不会实际运行")
                self._is_real_hardware = False
            else:
                self._is_real_hardware = True
                self.logger.info(f"✅ 检测到树莓派硬件 (Revision: {GPIO_Real.RPI_REVISION})")
        except:
            self._is_real_hardware = False
            self.logger.warning("⚠️ RPi.GPIO 导入失败或非树莓派环境")

        GPIO.cleanup()
        GPIO.setmode(GPIO.BCM)
        # 设置电机控制引脚
        for pin in [IN1, IN2, IN3, IN4, IN5, IN6, IN7, IN8]:
            GPIO.setup(pin, OUT)
            GPIO.output(pin, LOW)

        self.en_pins = [EN1, EN2, EN3, EN4]
        self.pwms = []
        for pin in self.en_pins:
            GPIO.setup(pin, OUT)
            pwm = GPIO.PWM(pin, PWM_FREQ)  # 创建 PWM
            pwm.start(0)  # 初始占空比 0
            self.pwms.append(pwm)

        # 映射 PWM 到具体轮子 (根据测试结果: 6->LF, 13->LB, 19->RB, 26->RF)
        self.pwm_lf = self.pwms[0]  # EN1
        self.pwm_lb = self.pwms[1]  # EN2
        self.pwm_rb = self.pwms[2]  # EN3
        self.pwm_rf = self.pwms[3]  # EN4

        # 设置超声波传感器引脚
        GPIO.setup(HC_SR_04_TRIG, OUT)
        GPIO.setup(HC_SR_04_ECHO, IN)

        # 加载保存的速度
        saved_speed = self._load_speed()
        self._current_speed = max(MIN_SPEED_LIMIT, saved_speed)

        self.stop()  # 初始化时停车

        # 打印初始化信息
        speed_source = "从运行时状态加载" if saved_speed != DEFAULT_SPEED else "使用默认值"
        self.logger.info("=" * 50)
        self.logger.info("MotorControl 初始化完成")
        self.logger.info(f"  当前速度: {self._current_speed}% ({speed_source})")
        self.logger.info(f"  PWM 频率: {PWM_FREQ} Hz")
        self.logger.info(f"  最小速度限制: {MIN_SPEED_LIMIT}%")
        self.logger.info("  GPIO 引脚配置:")
        self.logger.info(f"    IN1={IN1}, IN2={IN2} -> 左前电机")
        self.logger.info(f"    IN3={IN3}, IN4={IN4} -> 右前电机")
        self.logger.info(f"    IN5={IN5}, IN6={IN6} -> 左后电机")
        self.logger.info(f"    IN7={IN7}, IN8={IN8} -> 右后电机")
        self.logger.info(f"    EN1={EN1} (LF), EN2={EN2} (LB), EN3={EN3} (RB), EN4={EN4} (RF)")
        self.logger.info(f"  超声波: TRIG={HC_SR_04_TRIG}, ECHO={HC_SR_04_ECHO}")
        self.logger.info("=" * 50)

    def _load_speed(self) -> int:
        """从文件加载保存的速度"""
        try:
            # 检查是否有旧文件需要迁移
            old_settings_file = os.path.join(DATA_DIR, 'settings.json')
            if os.path.exists(old_settings_file) and not os.path.exists(RUNTIME_STATE_FILE):
                self.logger.info("检测到旧版本 settings.json，正在迁移到 runtime_state.json...")
                try:
                    with open(old_settings_file, 'r', encoding='utf-8') as f:
                        old_data = json.load(f)
                    # 保存到新文件
                    self._save_speed(old_data.get('speed', DEFAULT_SPEED))
                    # 删除旧文件
                    os.remove(old_settings_file)
                    self.logger.info("迁移完成，旧文件已删除")
                except Exception as migrate_error:
                    self.logger.warning(f"迁移失败: {migrate_error}，将直接从旧文件读取")
                    # 迁移失败则直接读取旧文件
                    with open(old_settings_file, 'r', encoding='utf-8') as f:
                        state = json.load(f)
                        speed = state.get('speed', DEFAULT_SPEED)
                        speed = max(MIN_SPEED_LIMIT, min(100, speed))
                        return speed

            # 从新文件读取
            if os.path.exists(RUNTIME_STATE_FILE):
                with open(RUNTIME_STATE_FILE, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    speed = state.get('speed', DEFAULT_SPEED)
                    # 确保速度在有效范围内
                    speed = max(MIN_SPEED_LIMIT, min(100, speed))
                    self.logger.info(f"从运行时状态加载速度: {speed}%")
                    return speed
        except Exception as e:
            self.logger.warning(f"加载运行时状态失败: {e}，使用默认值")
        return DEFAULT_SPEED

    def _save_speed(self, speed: int):
        """保存速度到文件（带锁，防止并发问题）"""
        with self._save_lock:  # 使用锁确保只有一个线程能写入文件
            try:
                # 确保 data 目录存在
                os.makedirs(DATA_DIR, exist_ok=True)

                # 读取现有状态
                state = {}
                if os.path.exists(RUNTIME_STATE_FILE):
                    with open(RUNTIME_STATE_FILE, 'r', encoding='utf-8') as f:
                        state = json.load(f)

                # 只在值真正变化时才写入（避免不必要的 I/O）
                if state.get('speed') == speed:
                    return

                # 更新速度
                state['speed'] = speed

                # 保存到文件
                with open(RUNTIME_STATE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(state, f, indent=2, ensure_ascii=False)

                self.logger.info(f"速度已保存到运行时状态: {speed}%")
            except Exception as e:
                self.logger.error(f"保存运行时状态失败: {e}")

        self._distance_detection_enabled = True  # 内部控制距离检测是否开启
        self.temperature = DEFAULT_TEMPERATURE
        self.distance_buffer = []
        self.buffer_size = DISTANCE_BUFFER_SIZE

    def cleanup(self):
        """清理GPIO引脚状态"""
        self.stop()
        for pwm in self.pwms:
            pwm.stop()
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

    def set_speed(self, speed: int):
        safe_speed = max(MIN_SPEED_LIMIT, min(100, speed))
        self._current_speed = safe_speed
        self._apply_speed()
        # 保存速度到文件
        self._save_speed(safe_speed)

    def get_speed(self):
        return self._current_speed

    def _apply_speed(self):
        speed_lf = self._current_speed * CORRECTION_LF
        speed_lb = self._current_speed * CORRECTION_LB
        speed_rf = self._current_speed * CORRECTION_RF
        speed_rb = self._current_speed * CORRECTION_RB

        # 应用到 PWM 对象
        self.pwm_lf.ChangeDutyCycle(speed_lf)
        self.pwm_lb.ChangeDutyCycle(speed_lb)
        self.pwm_rf.ChangeDutyCycle(speed_rf)
        self.pwm_rb.ChangeDutyCycle(speed_rb)

        self.logger.debug(f"应用速度: LF={speed_lf:.1f}%, LB={speed_lb:.1f}%, RF={speed_rf:.1f}%, RB={speed_rb:.1f}%")

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
                GPIO.output(motor_in1, HIGH)
                GPIO.output(motor_in2, LOW)
            else:  # 左侧电机，正常前进
                GPIO.output(motor_in1, LOW)
                GPIO.output(motor_in2, HIGH)
        elif mode == MODE_BACK:
            if is_right_motor:  # 如果是右侧电机，后退时实际需要反转信号
                GPIO.output(motor_in1, LOW)
                GPIO.output(motor_in2, HIGH)
            else:  # 左侧电机，正常后退
                GPIO.output(motor_in1, HIGH)
                GPIO.output(motor_in2, LOW)
        elif mode == MODE_STOP:
            GPIO.output(motor_in1, LOW)
            GPIO.output(motor_in2, LOW)

    def _control_motor_pair(self, in1, in2, mode):
        self.__set_motor_state(in1, in2, mode)

    # --- 单独电机控制方法 (用于调试) ---
    def control_left_front(self, mode):
        """单独控制左前电机"""
        self.__set_motor_state(IN7, IN8, mode)

    def control_right_front(self, mode):
        self.__set_motor_state(IN1, IN2, mode)

    def control_left_back(self, mode):
        self.__set_motor_state(IN5, IN6, mode)

    def control_right_back(self, mode):
        self.__set_motor_state(IN3, IN4, mode)

    # --- 公共运动方法 (麦克纳姆轮运动逻辑) ---
    def move_forward(self):
        """小车向前直行"""
        self.logger.debug(f"move_forward 被调用, 当前速度: {self._current_speed}")
        if not self._is_real_hardware:
            self.logger.warning("⚠️ 非真实硬件环境，电机不会实际运行")

        self._control_motor_pair(IN1, IN2, MODE_FORWARD)
        self._control_motor_pair(IN3, IN4, MODE_FORWARD)
        self._control_motor_pair(IN5, IN6, MODE_FORWARD)
        self._control_motor_pair(IN7, IN8, MODE_FORWARD)
        self._apply_speed()

    def move_back(self):
        """小车向后直行"""
        self._control_motor_pair(IN1, IN2, MODE_BACK)
        self._control_motor_pair(IN3, IN4, MODE_BACK)
        self._control_motor_pair(IN5, IN6, MODE_BACK)
        self._control_motor_pair(IN7, IN8, MODE_BACK)
        self._apply_speed()

    def move_left(self):  # 平移向左 (横向移动)
        """
        麦克纳姆轮左平移：
        左前轮：后退
        左后轮：前进
        右前轮：前进
        右后轮：后退
        """
        self._control_motor_pair(IN1, IN2, MODE_FORWARD)
        self._control_motor_pair(IN3, IN4, MODE_BACK)
        self._control_motor_pair(IN5, IN6, MODE_FORWARD)
        self._control_motor_pair(IN7, IN8, MODE_BACK)
        self._apply_speed()

    def move_right(self):  # 平移向右 (横向移动)
        """
        麦克纳姆轮右平移：
        左前轮：前进
        左后轮：后退
        右前轮：后退
        右后轮：前进
        """
        self._control_motor_pair(IN1, IN2, MODE_BACK)
        self._control_motor_pair(IN3, IN4, MODE_FORWARD)
        self._control_motor_pair(IN5, IN6, MODE_BACK)
        self._control_motor_pair(IN7, IN8, MODE_FORWARD)
        self._apply_speed()

    def turn_left(self):  # 原地左转
        """
        原地左转：
        左侧所有轮子：后退
        右侧所有轮子：前进
        """
        self._control_motor_pair(IN1, IN2, MODE_FORWARD)
        self._control_motor_pair(IN3, IN4, MODE_FORWARD)
        self._control_motor_pair(IN5, IN6, MODE_BACK)
        self._control_motor_pair(IN7, IN8, MODE_BACK)
        self._apply_speed()

    def turn_right(self):  # 原地右转
        """
        原地右转：
        左侧所有轮子：前进
        右侧所有轮子：后退
        """
        self._control_motor_pair(IN1, IN2, MODE_BACK)
        self._control_motor_pair(IN3, IN4, MODE_BACK)
        self._control_motor_pair(IN5, IN6, MODE_FORWARD)
        self._control_motor_pair(IN7, IN8, MODE_FORWARD)
        self._apply_speed()

    # --- 斜向移动 (修正后的麦克纳姆轮逻辑，基于所有轮子方向校正) ---
    def move_left_forward(self):  # 左前斜向
        self._control_motor_pair(IN1, IN2, MODE_STOP)
        self._control_motor_pair(IN3, IN4, MODE_FORWARD)
        self._control_motor_pair(IN5, IN6, MODE_STOP)
        self._control_motor_pair(IN7, IN8, MODE_BACK)
        self._apply_speed()

    def move_right_forward(self):  # 右前斜向
        self._control_motor_pair(IN1, IN2, MODE_BACK)
        self._control_motor_pair(IN3, IN4, MODE_STOP)
        self._control_motor_pair(IN5, IN6, MODE_FORWARD)
        self._control_motor_pair(IN7, IN8, MODE_STOP)
        self._apply_speed()

    def move_left_back(self):  # 左后斜向
        self._control_motor_pair(IN1, IN2, MODE_FORWARD)
        self._control_motor_pair(IN3, IN4, MODE_STOP)
        self._control_motor_pair(IN5, IN6, MODE_BACK)
        self._control_motor_pair(IN7, IN8, MODE_STOP)
        self._apply_speed()

    def move_right_back(self):  # 右后斜向
        self._control_motor_pair(IN1, IN2, MODE_STOP)
        self._control_motor_pair(IN3, IN4, MODE_STOP)
        self._control_motor_pair(IN5, IN6, MODE_STOP)
        self._control_motor_pair(IN7, IN8, MODE_FORWARD)
        self._apply_speed()

    def stop(self):
        """停止所有电机，将所有控制引脚置低"""
        for pin in [IN1, IN2, IN3, IN4, IN5, IN6, IN7, IN8]:
            GPIO.output(pin, LOW)
        for pwm in self.pwms:
            pwm.ChangeDutyCycle(0)

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

        while GPIO.input(HC_SR_04_ECHO) == 0:
            if time.time() > timeout_start:
                return -1
            pulse_start_time = time.time()

        # 等待 ECHO 信号变为低电平 (结束时间)
        timeout_end = time.time() + HC_SR_04_TIMEOUT

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

        print("调试右前电机：前进 1秒")
        mc.control_right_front(MODE_FORWARD)
        time.sleep(1)
        mc.stop()
        time.sleep(0.5)

        print("调试左后电机：前进 1秒")
        mc.control_left_back(MODE_FORWARD)
        time.sleep(1)
        mc.stop()
        time.sleep(0.5)

        print("调试右后电机：前进 1秒")
        mc.control_right_back(MODE_FORWARD)
        time.sleep(1)
        mc.stop()
        time.sleep(0.5)

    print("程序退出。")
