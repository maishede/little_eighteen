# app/utils/camera_streamer.py (更新后的文件内容)
import cv2
import threading
import time
import logging
from fastapi.responses import StreamingResponse, JSONResponse


class CameraStreamer:
    """
    负责管理摄像头视频流的类。
    它处理摄像头的打开、关闭、帧捕获和生成器。
    """

    def __init__(self, camera_index: int, fps: int, resolution: tuple, logger: logging.Logger):
        self.camera_index = camera_index
        self.fps = fps
        self.resolution = resolution
        self.logger = logger
        self.cap = None  # OpenCV VideoCapture 对象
        self._is_streaming = False  # 标志：摄像头是否正在捕获和传输流
        self._frame_lock = threading.Lock()  # 锁：保护共享帧数据
        self._current_frame = None  # 最近捕获的帧
        self._stop_event = threading.Event()  # 停止事件，用于线程间通信

        self.logger.info(f"CameraStreamer 实例初始化：Index={camera_index}, FPS={fps}, Resolution={resolution}")

    def start_camera_capture(self) -> bool:
        """
        启动摄像头捕获。
        如果摄像头已在运行或无法打开，则返回 False。
        此方法现在在 API 调用时才执行实际的摄像头打开操作。
        """
        if self._is_streaming:
            self.logger.warning("摄像头已在运行中，无需重复启动。")
            return True

        self.logger.info(f"尝试打开摄像头 {self.camera_index}...")
        try:
            # 尝试打开摄像头
            self.cap = cv2.VideoCapture(self.camera_index)
            if not self.cap.isOpened():
                self.logger.error(f"无法打开摄像头 {self.camera_index}。请检查摄像头连接和权限。")
                self.cap = None
                return False

            # 设置分辨率和帧率
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
            self.cap.set(cv2.CAP_PROP_FPS, self.fps)

            # 验证设置是否成功 (可选，某些摄像头可能不支持所有设置)
            actual_width = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            actual_height = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
            self.logger.info(f"摄像头 {self.camera_index} 实际分辨率: {actual_width}x{actual_height}, 实际帧率: {actual_fps}")

            self._is_streaming = True
            self._stop_event.clear()  # 清除停止事件，表示可以开始
            self.logger.info(f"摄像头 {self.camera_index} 成功启动捕获。")

            # 启动一个独立的线程来连续读取帧，避免阻塞主线程
            self._capture_thread = threading.Thread(target=self._read_frames_loop, daemon=True)
            self._capture_thread.start()
            self.logger.info("摄像头帧读取线程已启动。")
            return True

        except Exception as e:
            self.logger.error(f"启动摄像头 {self.camera_index} 时发生异常: {e}", exc_info=True)
            self.cap = None
            self._is_streaming = False
            return False

    def _read_frames_loop(self):
        """
        在单独的线程中循环读取摄像头帧。
        """
        self.logger.info("进入 _read_frames_loop 循环。")
        while self._is_streaming and not self._stop_event.is_set() and self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret:
                self.logger.warning(f"无法从摄像头 {self.camera_index} 读取帧。可能已断开或停止。")
                self._is_streaming = False  # 停止流
                break  # 退出循环

            with self._frame_lock:
                self._current_frame = frame
            time.sleep(1 / self.fps)  # 控制帧率

        self.logger.info("_read_frames_loop 循环结束。")
        if self.cap:
            self.cap.release()  # 释放摄像头资源
            self.logger.info(f"摄像头 {self.camera_index} 资源已释放。")
        self.cap = None
        self._is_streaming = False
        self._current_frame = None

    def generate_frames(self):
        """
        生成视频流的帧。
        """
        self.logger.info("生成视频帧请求开始。")
        while self._is_streaming and not self._stop_event.is_set():
            with self._frame_lock:
                frame = self._current_frame

            if frame is None:
                # 如果还没有帧，等待一下
                time.sleep(0.01)
                continue

            try:
                # 将帧编码为 JPEG 格式
                ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if not ret:
                    self.logger.error("无法将帧编码为 JPEG 格式。")
                    continue

                # 返回字节流
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            except Exception as e:
                self.logger.error(f"在生成帧时发生异常: {e}", exc_info=True)
                break  # 发生错误时停止生成
        self.logger.info("生成视频帧请求结束。")

    def stop_camera_capture(self) -> bool:
        """
        停止摄像头捕获并释放资源。
        """
        if not self._is_streaming:
            self.logger.warning("摄像头未在运行，无需停止。")
            return False

        self.logger.info(f"尝试停止摄像头 {self.camera_index} 捕获。")
        self._stop_event.set()  # 设置停止事件，通知线程退出循环

        # 等待捕获线程结束 (可选，但推荐)
        if hasattr(self, '_capture_thread') and self._capture_thread.is_alive():
            self.logger.info("等待摄像头捕获线程终止...")
            self._capture_thread.join(timeout=5)  # 最多等待5秒
            if self._capture_thread.is_alive():
                self.logger.warning("摄像头捕获线程未能及时终止。")
            else:
                self.logger.info("摄像头捕获线程已终止。")

        # 确保 cap 被释放 (_read_frames_loop 退出时也会释放)
        if self.cap:
            self.cap.release()
            self.cap = None
            self.logger.info(f"摄像头 {self.camera_index} 资源已最终释放。")

        self._is_streaming = False
        self._current_frame = None
        self.logger.info("摄像头捕获已停止。")
        return True

    def is_streaming_active(self) -> bool:
        """
        检查摄像头流是否正在活跃。
        """
        return self._is_streaming and self.cap is not None and self.cap.isOpened()